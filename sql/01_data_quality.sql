-- Step 5 raw-data audit. Dialect: DuckDB 1.4.5.
-- Run with python src/audit_data.py; it loads source rows and registers exact parsers.
-- Input: raw_order_lines, one row per original Excel data row, with sheet/row lineage.
-- No source rows are removed. Temporary tables below describe issues and proposed
-- dispositions only. Candidate amounts use a provisional six-decimal price scenario
-- accepting only deviations <= 1e-9 GBP. Strict failures remain flagged.
-- These amounts are uncleaned exposure, not revenue or an approved cleaning rule.
-- Named sections are executed in order by the small Python runner.

-- audit: setup
CREATE OR REPLACE TEMP TABLE audit_lines AS
WITH parsed AS (
    SELECT *,
        NULLIF(upper(trim(raw_invoice)), '') AS invoice_id,
        NULLIF(upper(trim(raw_stock_code)), '') AS stock_code,
        NULLIF(trim(raw_description), '') AS description,
        CAST(audit_quantity(raw_quantity) AS BIGINT) AS quantity,
        CAST(audit_price(raw_price) AS DECIMAL(24,6)) AS unit_price_gbp,
        CAST(audit_review_price(raw_price) AS DECIMAL(24,6)) AS review_unit_price_gbp,
        audit_price_issue(raw_price) AS price_precision_status,
        CAST(audit_price_delta(raw_price) AS DECIMAL(38,18)) AS price_review_delta_gbp,
        CAST(audit_date(raw_invoice_date) AS TIMESTAMP) AS invoice_timestamp,
        audit_customer(raw_customer_id) AS customer_id,
        NULLIF(NULLIF(trim(raw_country), ''), 'Unspecified') AS country,
        sha256(to_json([coalesce(raw_invoice,''), coalesce(raw_stock_code,''),
            coalesce(raw_description,''), coalesce(raw_quantity,''),
            coalesce(raw_invoice_date,''), coalesce(raw_price,''),
            coalesce(raw_customer_id,''), coalesce(raw_country,'')])) AS raw_signature
    FROM raw_order_lines
), signed AS (
    SELECT *, sha256(to_json([
        coalesce(invoice_id,''), coalesce(stock_code,''), coalesce(description,''),
        coalesce(CAST(quantity AS VARCHAR), 'INVALID:' || coalesce(raw_quantity,'')),
        coalesce(CAST(invoice_timestamp AS VARCHAR), 'INVALID:' || coalesce(raw_invoice_date,'')),
        coalesce(CAST(unit_price_gbp AS VARCHAR), 'INVALID:' || coalesce(raw_price,'')),
        coalesce(customer_id, CASE WHEN nullif(trim(raw_customer_id),'') IS NULL THEN '' ELSE 'INVALID:' || raw_customer_id END),
        coalesce(country,'')])) AS normalized_signature,
        CASE WHEN regexp_full_match(invoice_id, '[0-9]+') AND quantity > 0 AND review_unit_price_gbp > 0
             THEN quantity * review_unit_price_gbp ELSE 0::DECIMAL(38,6) END AS candidate_positive_gbp
    FROM parsed
)
SELECT *, row_number() OVER (
    PARTITION BY source_sheet, invoice_id, normalized_signature ORDER BY source_row_number
) AS within_version_copy_number
FROM signed;

CREATE OR REPLACE TEMP TABLE audit_invoice_versions AS
WITH payload_counts AS (
    SELECT source_sheet, invoice_id, normalized_signature, count(*) AS copies
    FROM audit_lines GROUP BY ALL
), payloads AS (
    SELECT source_sheet, invoice_id,
        sha256(to_json(list(struct_pack(signature := normalized_signature, copies := copies)
            ORDER BY normalized_signature))) AS payload_hash
    FROM payload_counts GROUP BY source_sheet, invoice_id
)
SELECT a.source_sheet, a.invoice_id, p.payload_hash,
    count(*) AS source_rows,
    count(DISTINCT invoice_timestamp) AS distinct_timestamps,
    count(*) FILTER (WHERE invoice_timestamp IS NULL) AS invalid_date_rows,
    count(DISTINCT customer_id) AS distinct_known_customers,
    count(*) FILTER (WHERE customer_id IS NULL) AS missing_or_invalid_customer_rows,
    count(*) FILTER (WHERE nullif(trim(raw_customer_id),'') IS NOT NULL AND customer_id IS NULL) AS invalid_customer_rows,
    count(DISTINCT country) AS distinct_known_countries,
    sum(candidate_positive_gbp) AS candidate_positive_gbp
FROM audit_lines a JOIN payloads p ON a.source_sheet = p.source_sheet AND a.invoice_id IS NOT DISTINCT FROM p.invoice_id
GROUP BY a.source_sheet, a.invoice_id, p.payload_hash;

CREATE OR REPLACE TEMP TABLE audit_overlap AS
SELECT invoice_id,
    CASE WHEN count(DISTINCT payload_hash) = 1 THEN 'identical' ELSE 'conflict' END AS overlap_status,
    sum(source_rows) AS source_rows_both_versions,
    sum(candidate_positive_gbp) AS candidate_positive_gbp_both_versions
FROM audit_invoice_versions
GROUP BY invoice_id HAVING count(DISTINCT source_sheet) > 1;

CREATE OR REPLACE TEMP VIEW audit_dispositions AS
SELECT a.*,
    CASE
        WHEN o.overlap_status = 'conflict' THEN 'hold_overlap_conflict'
        WHEN o.overlap_status = 'identical' AND a.source_sheet = 'Year 2009-2010' THEN 'exclude_older_overlap_copy'
        WHEN a.within_version_copy_number > 1 THEN 'exclude_within_version_duplicate'
        ELSE 'retain_for_step_6_review'
    END AS proposed_disposition,
    (v.distinct_timestamps <> 1 OR v.invalid_date_rows > 0 OR v.distinct_known_customers > 1 OR v.invalid_customer_rows > 0) AS header_conflict,
    v.distinct_known_customers AS invoice_known_customers
FROM audit_lines a
LEFT JOIN audit_overlap o ON a.invoice_id IS NOT DISTINCT FROM o.invoice_id
JOIN audit_invoice_versions v ON a.source_sheet = v.source_sheet AND a.invoice_id IS NOT DISTINCT FROM v.invoice_id;

-- audit: source_inventory
SELECT source_sheet, count(*) AS rows, min(source_row_number) AS first_excel_row,
    max(source_row_number) AS last_excel_row, count(DISTINCT source_row_number) AS distinct_row_numbers,
    min(invoice_timestamp) AS first_timestamp, max(invoice_timestamp) AS last_timestamp,
    count(DISTINCT source_workbook_sha256) AS workbook_hashes
FROM audit_lines GROUP BY source_sheet ORDER BY source_sheet;

-- audit: missing_fields
SELECT 'Invoice' AS field, count(*) FILTER (WHERE nullif(trim(raw_invoice),'') IS NULL) AS missing_rows FROM audit_lines
UNION ALL SELECT 'StockCode', count(*) FILTER (WHERE nullif(trim(raw_stock_code),'') IS NULL) FROM audit_lines
UNION ALL SELECT 'Description', count(*) FILTER (WHERE description IS NULL) FROM audit_lines
UNION ALL SELECT 'Quantity', count(*) FILTER (WHERE nullif(trim(raw_quantity),'') IS NULL) FROM audit_lines
UNION ALL SELECT 'InvoiceDate', count(*) FILTER (WHERE nullif(trim(raw_invoice_date),'') IS NULL) FROM audit_lines
UNION ALL SELECT 'Price', count(*) FILTER (WHERE nullif(trim(raw_price),'') IS NULL) FROM audit_lines
UNION ALL SELECT 'Customer ID', count(*) FILTER (WHERE nullif(trim(raw_customer_id),'') IS NULL) FROM audit_lines
UNION ALL SELECT 'Country', count(*) FILTER (WHERE nullif(trim(raw_country),'') IS NULL) FROM audit_lines;

-- audit: quality_flags
SELECT count(*) AS raw_rows,
    count(*) FILTER (WHERE quantity IS NULL) AS invalid_or_nonintegral_quantity_rows,
    count(*) FILTER (WHERE unit_price_gbp IS NULL) AS invalid_or_excess_precision_price_rows,
    count(*) FILTER (WHERE invoice_timestamp IS NULL) AS invalid_date_rows,
    count(*) FILTER (WHERE nullif(trim(raw_customer_id),'') IS NOT NULL AND customer_id IS NULL) AS malformed_customer_rows,
    count(*) FILTER (WHERE starts_with(invoice_id, 'C')) AS cancellation_prefix_rows,
    count(*) FILTER (WHERE NOT regexp_full_match(invoice_id, '[0-9]+') AND NOT starts_with(invoice_id,'C')) AS other_invoice_format_rows,
    count(*) FILTER (WHERE quantity < 0) AS negative_quantity_rows,
    count(*) FILTER (WHERE quantity = 0) AS zero_quantity_rows,
    count(*) FILTER (WHERE TRY_CAST(raw_price AS DOUBLE) < 0) AS negative_price_rows,
    count(*) FILTER (WHERE TRY_CAST(raw_price AS DOUBLE) = 0) AS zero_price_rows,
    count(*) FILTER (WHERE starts_with(invoice_id,'C') AND quantity > 0) AS positive_quantity_cancellation_rows,
    count(*) FILTER (WHERE NOT starts_with(invoice_id,'C') AND quantity < 0) AS negative_quantity_without_c_prefix_rows,
    count(*) FILTER (WHERE country IS NULL) AS unknown_country_rows,
    count(*) FILTER (WHERE invoice_timestamp >= (SELECT cutoff FROM audit_parameters)) AS partial_final_month_rows,
    count(*) - count(DISTINCT raw_signature) AS raw_repeated_rows_after_first,
    count(*) - count(DISTINCT normalized_signature) AS normalized_repeated_rows_after_first,
    count(DISTINCT invoice_id) AS distinct_invoice_ids,
    count(DISTINCT customer_id) AS distinct_known_customers,
    count(DISTINCT stock_code) AS distinct_stock_codes
FROM audit_lines;

-- audit: price_precision_review
SELECT price_precision_status, count(*) AS rows,
    max(price_review_delta_gbp) AS maximum_absolute_review_delta_gbp,
    min(raw_price) AS example_raw_price
FROM audit_lines GROUP BY price_precision_status ORDER BY price_precision_status;

-- audit: overlap_summary
SELECT overlap_status, count(*) AS invoices, sum(source_rows_both_versions) AS rows_both_versions,
    sum(candidate_positive_gbp_both_versions) AS candidate_positive_gbp_both_versions
FROM audit_overlap GROUP BY overlap_status ORDER BY overlap_status;

-- audit: invoice_overlap
SELECT o.invoice_id, o.overlap_status, v.source_sheet, v.source_rows, v.payload_hash,
    v.distinct_timestamps, v.distinct_known_customers, v.candidate_positive_gbp
FROM audit_overlap o JOIN audit_invoice_versions v USING(invoice_id)
ORDER BY o.overlap_status, o.invoice_id, v.source_sheet;

-- audit: proposed_dispositions
SELECT proposed_disposition, count(*) AS rows,
    sum(candidate_positive_gbp) AS candidate_positive_gbp_all_dates,
    sum(CASE WHEN invoice_timestamp >= p.history_start AND invoice_timestamp < p.cutoff THEN candidate_positive_gbp ELSE 0 END) AS candidate_positive_gbp_main_period
FROM audit_dispositions CROSS JOIN audit_parameters p
GROUP BY proposed_disposition ORDER BY proposed_disposition;

-- audit: header_summary
SELECT count(*) AS invoice_versions,
    count(*) FILTER (WHERE distinct_timestamps > 1) AS multiple_timestamp_versions,
    count(*) FILTER (WHERE distinct_known_customers > 1) AS multiple_customer_versions,
    count(*) FILTER (WHERE distinct_known_countries > 1) AS multiple_country_versions,
    count(*) FILTER (WHERE distinct_known_customers = 0) AS unidentified_versions,
    count(*) FILTER (WHERE distinct_known_customers = 1 AND missing_or_invalid_customer_rows > 0 AND invalid_customer_rows = 0) AS versions_with_inheritable_missing_ids
FROM audit_invoice_versions;

-- audit: header_issues
SELECT * FROM audit_invoice_versions
WHERE distinct_timestamps <> 1 OR invalid_date_rows > 0 OR distinct_known_customers > 1
    OR invalid_customer_rows > 0 OR distinct_known_countries > 1
ORDER BY invoice_id, source_sheet;

-- audit: retained_review_exposure
SELECT count(*) AS rows_after_proposed_overlap_and_duplicate_handling,
    count(*) FILTER (WHERE header_conflict) AS rows_in_header_conflicts,
    sum(CASE WHEN header_conflict THEN candidate_positive_gbp ELSE 0 END) AS header_conflict_candidate_gbp,
    sum(candidate_positive_gbp) AS candidate_positive_gbp,
    sum(CASE WHEN invoice_known_customers = 0 THEN candidate_positive_gbp ELSE 0 END) AS unidentified_candidate_gbp,
    count(*) FILTER (WHERE invoice_known_customers = 0) AS rows_in_unidentified_invoices
FROM audit_dispositions
WHERE proposed_disposition = 'retain_for_step_6_review'
    AND invoice_timestamp >= (SELECT history_start FROM audit_parameters)
    AND invoice_timestamp < (SELECT cutoff FROM audit_parameters);

-- audit: monthly_coverage
SELECT strftime(invoice_timestamp, '%Y-%m') AS month, count(*) AS source_rows,
    count(DISTINCT CAST(invoice_timestamp AS DATE)) AS observed_days,
    min(invoice_timestamp) AS first_timestamp, max(invoice_timestamp) AS last_timestamp,
    count(*) FILTER (WHERE customer_id IS NULL) AS missing_or_invalid_customer_rows
FROM audit_lines GROUP BY month ORDER BY month;

-- audit: date_gaps
WITH bounds AS (SELECT min(CAST(invoice_timestamp AS DATE)) AS first_day, max(CAST(invoice_timestamp AS DATE)) AS last_day FROM audit_lines),
calendar AS (SELECT CAST(day AS DATE) AS day FROM bounds, generate_series(first_day,last_day,INTERVAL '1 day') AS dates(day)),
missing AS (SELECT day FROM calendar WHERE day NOT IN (SELECT DISTINCT CAST(invoice_timestamp AS DATE) FROM audit_lines WHERE invoice_timestamp IS NOT NULL)),
islands AS (SELECT day, day - CAST(row_number() OVER (ORDER BY day) AS INTEGER) AS group_key FROM missing)
SELECT min(day) AS gap_start, max(day) AS gap_end, count(*) AS days_without_records
FROM islands GROUP BY group_key ORDER BY days_without_records DESC, gap_start;

-- audit: weekday_coverage
SELECT dayofweek(day) AS weekday_sunday_zero, count(*) AS observed_dates
FROM (SELECT DISTINCT CAST(invoice_timestamp AS DATE) AS day FROM audit_lines)
GROUP BY weekday_sunday_zero ORDER BY weekday_sunday_zero;

-- audit: product_codes
SELECT stock_code, count(*) AS source_rows, count(DISTINCT description) AS distinct_descriptions,
    string_agg(DISTINCT description, ' | ' ORDER BY description) AS observed_descriptions,
    regexp_full_match(stock_code, '[0-9]{5}[A-Z]{0,2}') AS standard_code_shape,
    count(*) FILTER (WHERE description IS NULL) AS missing_description_rows,
    sum(candidate_positive_gbp) AS candidate_positive_gbp_raw,
    count(DISTINCT CASE WHEN quantity > 0 AND review_unit_price_gbp > 0 THEN customer_id END) AS candidate_known_customers
FROM audit_lines GROUP BY stock_code ORDER BY stock_code;

-- audit: special_codes
SELECT stock_code, count(*) AS source_rows,
    string_agg(DISTINCT description, ' | ' ORDER BY description) AS observed_descriptions,
    sum(candidate_positive_gbp) AS candidate_positive_gbp_raw
FROM audit_lines WHERE NOT regexp_full_match(stock_code, '[0-9]{5}[A-Z]{0,2}')
GROUP BY stock_code ORDER BY candidate_positive_gbp_raw DESC, stock_code;

-- audit: product_consistency
SELECT count(*) FILTER (WHERE n_descriptions > 1) AS codes_with_multiple_descriptions,
    count(*) FILTER (WHERE n_descriptions = 0) AS codes_without_any_description
FROM (SELECT stock_code, count(DISTINCT description) AS n_descriptions FROM audit_lines GROUP BY stock_code);

-- audit: customer_country_consistency
SELECT count(*) AS known_customers,
    count(*) FILTER (WHERE countries > 1) AS customers_with_multiple_known_countries
FROM (SELECT customer_id, count(DISTINCT country) AS countries FROM audit_lines WHERE customer_id IS NOT NULL GROUP BY customer_id);

-- audit: amount_distribution
SELECT min(quantity) AS minimum_quantity, max(quantity) AS maximum_quantity,
    min(review_unit_price_gbp) AS minimum_unit_price_gbp, max(review_unit_price_gbp) AS maximum_unit_price_gbp,
    quantile_cont(quantity, 0.99) FILTER (WHERE quantity > 0) AS positive_quantity_p99,
    quantile_cont(review_unit_price_gbp, 0.99) FILTER (WHERE review_unit_price_gbp > 0) AS positive_price_p99,
    max(candidate_positive_gbp) AS largest_raw_positive_line_gbp
FROM audit_lines;

-- audit: outlier_lines
SELECT source_sheet, source_row_number, invoice_id, stock_code, description,
    quantity, raw_price, unit_price_gbp, review_unit_price_gbp, invoice_timestamp, customer_id, candidate_positive_gbp
FROM audit_lines
ORDER BY abs(coalesce(quantity * review_unit_price_gbp,0)) DESC, source_sheet, source_row_number
LIMIT 30;

-- audit: same_timestamp_invoices
WITH events AS (
    SELECT DISTINCT customer_id, invoice_id, invoice_timestamp FROM audit_lines
    WHERE customer_id IS NOT NULL AND regexp_full_match(invoice_id,'[0-9]+')
        AND quantity > 0 AND review_unit_price_gbp > 0
), grouped AS (
    SELECT customer_id, invoice_timestamp, count(*) AS invoices FROM events GROUP BY customer_id, invoice_timestamp HAVING count(*) > 1
)
SELECT count(*) AS customer_timestamp_groups, coalesce(sum(invoices),0) AS invoices_in_groups FROM grouped;
