-- Step 11 value measures and Step 12 frozen first-order comparison features.
CREATE OR REPLACE TABLE customer_value AS
WITH values_90 AS (
    SELECT c.customer_id,sum(o.order_sales_gbp) AS customer_sales_90d
    FROM customer_features c JOIN fact_orders o USING(customer_id)
    WHERE c.first_order_timestamp >= $cohort_start::TIMESTAMP
      AND c.first_order_timestamp+INTERVAL '90 days'<$cutoff::TIMESTAMP
      AND o.order_timestamp>=c.first_order_timestamp
      AND o.order_timestamp<=c.first_order_timestamp+INTERVAL '90 days'
    GROUP BY c.customer_id
)
SELECT c.customer_id,c.cohort_month,c.first_order_timestamp,c.historical_order_count,c.historical_sales_gbp,
    date_diff('day',CAST(c.first_order_timestamp AS DATE),$cutoff::DATE) AS observed_tenure_days,
    row_number() OVER(ORDER BY c.historical_sales_gbp DESC,c.customer_id) AS historical_sales_rank,
    v.customer_sales_90d
FROM customer_features c LEFT JOIN values_90 v USING(customer_id);
ALTER TABLE customer_value ADD PRIMARY KEY(customer_id);

CREATE OR REPLACE TABLE customer_comparison_population AS
SELECT c.customer_id,c.cohort_month,c.first_order_id,c.first_order_sales_gbp,
    c.first_order_distinct_products,c.first_order_country,r.repeated_window AS repeated_90d,
    v.customer_sales_90d,
    CASE WHEN c.first_order_sales_gbp<50 THEN 'Under GBP 50'
         WHEN c.first_order_sales_gbp<100 THEN 'GBP 50-<100'
         WHEN c.first_order_sales_gbp<250 THEN 'GBP 100-<250' ELSE 'GBP 250+' END AS first_order_value_band,
    CASE WHEN c.first_order_distinct_products=1 THEN '1 product'
         WHEN c.first_order_distinct_products<=5 THEN '2-5 products' ELSE '6+ products' END AS first_order_product_band,
    CASE WHEN c.first_order_country='United Kingdom' THEN 'United Kingdom'
         WHEN c.first_order_country IS NULL THEN 'Unknown' ELSE 'Other known country' END AS first_order_geography
FROM customer_features c JOIN customer_repeat_windows r USING(customer_id)
JOIN customer_value v USING(customer_id)
WHERE r.window_days=90 AND r.is_primary_cohort AND r.eligible_window;
ALTER TABLE customer_comparison_population ADD PRIMARY KEY(customer_id);
