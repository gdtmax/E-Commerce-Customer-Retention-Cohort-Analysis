-- Step 6, DuckDB. Run through src/clean_data.py after the raw audit.
-- All normalization, overlap hashes and header checks use contract version 1.1.
CREATE OR REPLACE TABLE product_roles AS SELECT * FROM read_csv_auto($roles, all_varchar=true);
ALTER TABLE product_roles ADD PRIMARY KEY(stock_code);

CREATE TEMP TABLE resolved_headers AS
SELECT source_sheet, invoice_id,
    CASE WHEN count(DISTINCT customer_id)=1 THEN min(customer_id) END AS resolved_customer_id,
    CASE WHEN count(DISTINCT country)=1 THEN min(country) END AS invoice_country,
    count(DISTINCT country)>1 AS country_conflict,
    count(DISTINCT customer_id)=1 AND count(*) FILTER(WHERE customer_id IS NULL)>0
        AS customer_id_inherited_within_invoice
FROM audit_lines GROUP BY source_sheet,invoice_id;

CREATE OR REPLACE TABLE stg_order_lines AS
WITH flagged AS (
SELECT a.*, coalesce(r.product_role,'unresolved') AS product_role, r.decision_reason AS product_role_reason,
    h.resolved_customer_id, h.invoice_country, h.country_conflict,
    h.customer_id_inherited_within_invoice,
    CASE WHEN proposed_disposition='hold_overlap_conflict' THEN 'conflict'
         WHEN o.overlap_status='identical' THEN 'matching-copy' ELSE 'unique' END AS overlap_status,
    within_version_copy_number>1 AS is_exact_duplicate,
    price_precision_status='representation_noise_candidate' AS price_normalized,
    list_filter([
        CASE WHEN quantity IS NULL THEN 'invalid_quantity' END,
        CASE WHEN unit_price_gbp IS NULL THEN 'invalid_price' END,
        CASE WHEN invoice_timestamp IS NULL THEN 'invalid_date' END,
        CASE WHEN nullif(trim(raw_customer_id),'') IS NOT NULL AND customer_id IS NULL THEN 'invalid_customer_id' END
    ], x -> x IS NOT NULL) AS parse_errors,
    list_filter([
        CASE WHEN proposed_disposition='hold_overlap_conflict' THEN 'overlap_conflict' END,
        CASE WHEN proposed_disposition='exclude_older_overlap_copy' THEN 'overlap_copy' END,
        CASE WHEN within_version_copy_number>1 THEN 'exact_duplicate' END,
        CASE WHEN invoice_timestamp IS NULL OR invoice_timestamp<p.history_start OR invoice_timestamp>=p.cutoff THEN 'outside_reporting_window_or_invalid_date' END,
        CASE WHEN header_conflict THEN 'header_conflict' END,
        CASE WHEN starts_with(a.invoice_id,'C') THEN 'credit_invoice'
             WHEN a.invoice_id IS NULL OR NOT regexp_full_match(a.invoice_id,'[0-9]+') THEN 'invalid_invoice_format' END,
        CASE WHEN quantity IS NULL THEN 'invalid_quantity' WHEN quantity<=0 THEN 'nonpositive_quantity' END,
        CASE WHEN unit_price_gbp IS NULL THEN 'invalid_price' WHEN unit_price_gbp<=0 THEN 'nonpositive_price' END,
        CASE WHEN r.product_role='non_merchandise' THEN 'non_merchandise'
             WHEN coalesce(r.product_role,'unresolved')='unresolved' THEN 'unresolved_product' END
    ], x -> x IS NOT NULL) AS exclusion_reasons
FROM audit_dispositions a
JOIN resolved_headers h ON a.source_sheet=h.source_sheet AND a.invoice_id IS NOT DISTINCT FROM h.invoice_id
LEFT JOIN product_roles r ON a.stock_code=r.stock_code
LEFT JOIN audit_overlap o ON a.invoice_id IS NOT DISTINCT FROM o.invoice_id
CROSS JOIN audit_parameters p
)
SELECT *, len(exclusion_reasons)=0 AS is_eligible_purchase_line,
    coalesce(exclusion_reasons[1],'included') AS primary_disposition,
    quantity*unit_price_gbp AS signed_line_amount_gbp
FROM flagged;
ALTER TABLE stg_order_lines ADD PRIMARY KEY(source_sheet,source_row_number);

CREATE OR REPLACE TABLE fact_order_lines AS
SELECT source_workbook_sha256,source_sheet,source_row_number,invoice_id,stock_code,description,
    quantity,unit_price_gbp,invoice_timestamp,resolved_customer_id AS customer_id,
    invoice_country,price_normalized,signed_line_amount_gbp AS line_sales_gbp
FROM stg_order_lines WHERE is_eligible_purchase_line;
ALTER TABLE fact_order_lines ADD PRIMARY KEY(source_sheet,source_row_number);

CREATE OR REPLACE TABLE fact_orders AS
WITH orders AS (
SELECT invoice_id,min(invoice_timestamp) AS order_timestamp,
    min(resolved_customer_id) AS customer_id, min(invoice_country) AS invoice_country,
    bool_or(customer_id_inherited_within_invoice) AS customer_id_inherited_within_invoice,
    bool_or(country_conflict) AS country_conflict,
    bool_or(header_conflict) AS unresolved_header_conflict,
    sum(signed_line_amount_gbp) AS order_sales_gbp, sum(quantity) AS order_units,
    count(DISTINCT stock_code) AS distinct_products,count(*) AS eligible_line_count
FROM stg_order_lines WHERE is_eligible_purchase_line GROUP BY invoice_id
)
SELECT *,CAST(order_timestamp AS DATE) AS order_date,
    CAST(date_trunc('month',order_timestamp) AS DATE) AS order_month,
    customer_id IS NOT NULL AS is_identified,
    CASE WHEN customer_id IS NOT NULL THEN row_number() OVER(PARTITION BY customer_id ORDER BY order_timestamp,invoice_id) END AS customer_order_sequence
FROM orders;
ALTER TABLE fact_orders ADD PRIMARY KEY(invoice_id);

CREATE OR REPLACE TABLE customer_features AS
WITH history AS (
SELECT customer_id,count(*) AS historical_order_count,sum(order_sales_gbp) AS historical_sales_gbp,
    max(order_timestamp) AS last_order_timestamp
FROM fact_orders WHERE is_identified GROUP BY customer_id
)
SELECT h.*,f.invoice_id AS first_order_id,f.order_timestamp AS first_order_timestamp,
    s.invoice_id AS second_order_id,s.order_timestamp AS second_order_timestamp,
    f.order_month AS cohort_month, f.order_timestamp<$cohort_start::TIMESTAMP AS is_initial_history_customer,
    date_diff('second',f.order_timestamp,s.order_timestamp)/86400.0 AS time_to_second_order_days,
    f.order_sales_gbp AS first_order_sales_gbp,f.distinct_products AS first_order_distinct_products,
    f.invoice_country AS first_order_country,
    date_diff('day',CAST(h.last_order_timestamp AS DATE),$cutoff::DATE) AS recency_days
FROM history h JOIN fact_orders f ON h.customer_id=f.customer_id AND f.customer_order_sequence=1
LEFT JOIN fact_orders s ON h.customer_id=s.customer_id AND s.customer_order_sequence=2;
ALTER TABLE customer_features ADD PRIMARY KEY(customer_id);

CREATE OR REPLACE TABLE customer_month_activity AS
SELECT DISTINCT customer_id,order_month AS activity_month FROM fact_orders WHERE is_identified;
ALTER TABLE customer_month_activity ADD PRIMARY KEY(customer_id,activity_month);

-- Sensitivity data remain views over the complete staging trail.
CREATE OR REPLACE VIEW sensitivity_order_lines_keep_duplicates AS
SELECT * FROM stg_order_lines
WHERE len(list_filter(exclusion_reasons,x -> x<>'exact_duplicate'))=0;
CREATE OR REPLACE VIEW sensitivity_orders_keep_duplicates AS
SELECT invoice_id,min(resolved_customer_id) AS customer_id,min(invoice_timestamp) AS order_timestamp,
    sum(signed_line_amount_gbp) AS order_sales_gbp
FROM sensitivity_order_lines_keep_duplicates GROUP BY invoice_id;
