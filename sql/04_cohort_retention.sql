-- Step 9. Calendar-month purchasing retention, not continuous survival.
-- Build the full 24x24 grid, retaining future cells as NULL rather than zero.
CREATE OR REPLACE TABLE cohort_retention AS
WITH calendar AS (
    SELECT CAST(month AS DATE) AS cohort_month
    FROM generate_series($history_start::TIMESTAMP,$cutoff::TIMESTAMP-INTERVAL '1 month',INTERVAL '1 month') d(month)
), customers AS (
    SELECT customer_id,CAST(date_trunc('month',min(order_timestamp)) AS DATE) AS cohort_month
    FROM customer_purchase_history GROUP BY customer_id
), sizes AS (
    SELECT cohort_month,count(*) AS cohort_size FROM customers GROUP BY cohort_month
), activity AS (
    SELECT DISTINCT customer_id,CAST(date_trunc('month',order_timestamp) AS DATE) AS activity_month
    FROM customer_purchase_history
), retained AS (
    SELECT c.cohort_month,a.activity_month,count(*) AS retained_customers
    FROM customers c JOIN activity a USING(customer_id) GROUP BY c.cohort_month,a.activity_month
), grid AS (
    SELECT c.cohort_month,coalesce(s.cohort_size,0) AS cohort_size,
        k.month_index,CAST(c.cohort_month+k.month_index*INTERVAL '1 month' AS DATE) AS activity_month,
        c.cohort_month >= $cohort_start::DATE AS is_primary_cohort
    FROM calendar c LEFT JOIN sizes s USING(cohort_month)
    CROSS JOIN range(0,date_diff('month',$history_start::DATE,$cutoff::DATE)) k(month_index)
), observed AS (
    SELECT g.*,g.activity_month+INTERVAL '1 month'<=$cutoff::TIMESTAMP AS is_observable,
        r.retained_customers AS actual_count
    FROM grid g LEFT JOIN retained r USING(cohort_month,activity_month)
)
SELECT cohort_month,month_index,activity_month,cohort_size,is_primary_cohort,is_observable,
    CASE WHEN is_observable THEN coalesce(actual_count,0) END AS retained_customers,
    CASE WHEN is_observable THEN coalesce(actual_count,0)::DOUBLE/nullif(cohort_size,0) END AS retention_rate
FROM observed ORDER BY cohort_month,month_index;
ALTER TABLE cohort_retention ADD PRIMARY KEY(cohort_month,month_index);

CREATE OR REPLACE TABLE cohort_retention_pooled AS
SELECT month_index,count(*) FILTER(WHERE is_observable AND cohort_size>0) AS mature_cohorts,
    coalesce(sum(cohort_size) FILTER(WHERE is_observable),0) AS eligible_customers,
    coalesce(sum(retained_customers) FILTER(WHERE is_observable),0) AS retained_customers,
    sum(retained_customers) FILTER(WHERE is_observable)::DOUBLE /
        nullif(sum(cohort_size) FILTER(WHERE is_observable),0) AS retention_rate
FROM cohort_retention WHERE is_primary_cohort GROUP BY month_index ORDER BY month_index;
ALTER TABLE cohort_retention_pooled ADD PRIMARY KEY(month_index);
