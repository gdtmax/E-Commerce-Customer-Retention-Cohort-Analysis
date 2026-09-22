-- Step 7. DuckDB; run with src/monthly_kpis.py.
-- Inputs: validated fact_orders and customer_features from Step 6.
-- money_ratio uses Decimal division and half-up rounding to six stored decimals.
CREATE OR REPLACE TABLE monthly_kpis AS
WITH calendar AS (
    SELECT CAST(month AS DATE) AS month
    FROM generate_series($history_start::TIMESTAMP,
                         $cutoff::TIMESTAMP - INTERVAL '1 month',
                         INTERVAL '1 month') AS dates(month)
), scoped_orders AS (
    SELECT * FROM fact_orders
    WHERE order_timestamp >= $history_start::TIMESTAMP
      AND order_timestamp < $cutoff::TIMESTAMP
), order_totals AS (
    SELECT order_month AS month, count(*) AS orders,
        sum(order_sales_gbp) AS gross_merchandise_sales_gbp,
        count(*) FILTER (WHERE is_identified) AS identified_orders,
        sum(CASE WHEN is_identified THEN order_sales_gbp ELSE 0 END) AS identified_sales_gbp
    FROM scoped_orders GROUP BY order_month
), customer_presence AS (
    -- Deduplicate purchase presence before counting new/returning customers.
    SELECT DISTINCT o.order_month AS month, o.customer_id, c.cohort_month
    FROM scoped_orders o JOIN customer_features c USING(customer_id)
    WHERE o.is_identified
), customer_totals AS (
    SELECT month,count(*) AS active_customers,
        count(*) FILTER (WHERE cohort_month=month) AS new_observed_customers,
        count(*) FILTER (WHERE cohort_month<month) AS returning_customers
    FROM customer_presence GROUP BY month
), filled AS (
    SELECT calendar.month,coalesce(o.orders,0) AS orders,
        coalesce(o.gross_merchandise_sales_gbp,0)::DECIMAL(38,6) AS gross_merchandise_sales_gbp,
        coalesce(o.identified_orders,0) AS identified_orders,
        coalesce(o.identified_sales_gbp,0)::DECIMAL(38,6) AS identified_sales_gbp,
        coalesce(c.active_customers,0) AS active_customers,
        coalesce(c.new_observed_customers,0) AS new_observed_customers,
        coalesce(c.returning_customers,0) AS returning_customers
    FROM calendar LEFT JOIN order_totals o USING(month)
    LEFT JOIN customer_totals c USING(month)
), previous AS (
    SELECT *,lag(gross_merchandise_sales_gbp) OVER (ORDER BY month) AS previous_month_sales_gbp
    FROM filled
)
SELECT *,orders-identified_orders AS unidentified_orders,
    gross_merchandise_sales_gbp-identified_sales_gbp AS unidentified_sales_gbp,
    CAST(money_ratio(CAST(gross_merchandise_sales_gbp AS VARCHAR),CAST(orders AS VARCHAR)) AS DECIMAL(24,6)) AS average_order_value_gbp,
    returning_customers::DOUBLE/nullif(active_customers,0) AS returning_customer_share,
    identified_orders::DOUBLE/nullif(orders,0) AS identified_order_share,
    identified_sales_gbp/nullif(gross_merchandise_sales_gbp,0) AS identified_sales_share,
    (gross_merchandise_sales_gbp-previous_month_sales_gbp)/nullif(previous_month_sales_gbp,0) AS sales_mom_growth
FROM previous ORDER BY month;
ALTER TABLE monthly_kpis ADD PRIMARY KEY(month);
