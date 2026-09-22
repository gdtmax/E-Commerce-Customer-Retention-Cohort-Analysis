-- Step 8. Full histories before T, followed by explicit primary-cohort filters.
CREATE OR REPLACE TABLE customer_purchase_history AS
WITH sequenced AS (
    SELECT invoice_id,customer_id,order_timestamp,order_sales_gbp,
        row_number() OVER(PARTITION BY customer_id ORDER BY order_timestamp,invoice_id) AS purchase_sequence,
        lag(order_timestamp) OVER(PARTITION BY customer_id ORDER BY order_timestamp,invoice_id) AS previous_order_timestamp
    FROM fact_orders WHERE is_identified
      AND order_timestamp >= $history_start::TIMESTAMP AND order_timestamp < $cutoff::TIMESTAMP
)
SELECT *,date_diff('second',previous_order_timestamp,order_timestamp)/86400.0 AS days_since_previous_order
FROM sequenced;
ALTER TABLE customer_purchase_history ADD PRIMARY KEY(invoice_id);

CREATE OR REPLACE TABLE customer_repeat_windows AS
WITH customers AS (
    SELECT customer_id,min(order_timestamp) AS first_order_timestamp,
        min(order_timestamp) FILTER(WHERE purchase_sequence=2) AS second_order_timestamp,
        count(*) AS historical_order_count
    FROM customer_purchase_history GROUP BY customer_id
), occasions AS (
    SELECT h.customer_id,min(h.order_timestamp) AS next_distinct_timestamp
    FROM customer_purchase_history h JOIN customers c USING(customer_id)
    WHERE h.order_timestamp>c.first_order_timestamp GROUP BY h.customer_id
), grid AS (
    SELECT c.*,o.next_distinct_timestamp,w.window_days,
        CAST(date_trunc('month',c.first_order_timestamp) AS DATE) AS cohort_month,
        c.first_order_timestamp >= $cohort_start::TIMESTAMP AS is_primary_cohort,
        c.first_order_timestamp+w.window_days*INTERVAL '1 day' AS window_end,
        c.first_order_timestamp+90*INTERVAL '1 day'<$cutoff::TIMESTAMP AS eligible_common_90d
    FROM customers c LEFT JOIN occasions o USING(customer_id)
    CROSS JOIN (VALUES(30),(60),(90)) w(window_days)
)
SELECT *,window_end<$cutoff::TIMESTAMP AS eligible_window,
    window_end<$cutoff::TIMESTAMP AND coalesce(second_order_timestamp<=window_end,false) AS repeated_window,
    eligible_common_90d AND coalesce(second_order_timestamp<=window_end,false) AS repeated_common_90d,
    window_end<$cutoff::TIMESTAMP AND coalesce(next_distinct_timestamp<=window_end,false) AS repeated_collapsed_timestamp,
    eligible_common_90d AND coalesce(next_distinct_timestamp<=window_end,false) AS repeated_collapsed_common_90d,
    date_diff('second',first_order_timestamp,second_order_timestamp)/86400.0 AS days_to_second_order
FROM grid;
ALTER TABLE customer_repeat_windows ADD PRIMARY KEY(customer_id,window_days);

CREATE OR REPLACE TABLE repeat_purchase_summary AS
WITH populations AS (
    SELECT *, 'own_window' AS population,eligible_window AS eligible,repeated_window AS repeated,
        repeated_collapsed_timestamp AS repeated_collapsed
    FROM customer_repeat_windows WHERE is_primary_cohort
    UNION ALL
    SELECT *, 'common_90_day',eligible_common_90d,repeated_common_90d,repeated_collapsed_common_90d
    FROM customer_repeat_windows WHERE is_primary_cohort
), counts AS (
    SELECT population,window_days,count(*) AS primary_customers,
        count(*) FILTER(WHERE eligible) AS eligible_customers,
        count(*) FILTER(WHERE NOT eligible) AS incomplete_window_customers,
        count(*) FILTER(WHERE repeated) AS repeat_customers,
        count(*) FILTER(WHERE repeated_collapsed) AS repeat_customers_collapsed_timestamp
    FROM populations GROUP BY population,window_days
)
SELECT *,repeat_customers::DOUBLE/nullif(eligible_customers,0) AS repeat_purchase_rate,
    repeat_customers_collapsed_timestamp::DOUBLE/nullif(eligible_customers,0) AS collapsed_timestamp_repeat_rate
FROM counts ORDER BY population,window_days;
ALTER TABLE repeat_purchase_summary ADD PRIMARY KEY(population,window_days);
