-- Step 11. rfm_input_orders is supplied by the runner for the primary or
-- explicitly labeled sensitivity population. All historical customers survive.
CREATE OR REPLACE TABLE rfm_snapshot AS
WITH features AS (
    SELECT customer_id,$cutoff::DATE AS snapshot_date,
        min(order_timestamp) AS first_order_timestamp,max(order_timestamp) AS last_order_timestamp,
        count(*) AS historical_order_count,sum(order_sales_gbp) AS historical_sales_gbp,
        date_diff('day',CAST(max(order_timestamp) AS DATE),$cutoff::DATE) AS recency_days,
        count(*) FILTER(WHERE order_timestamp >= $rfm_start::TIMESTAMP) AS frequency_12m,
        coalesce(sum(order_sales_gbp) FILTER(WHERE order_timestamp >= $rfm_start::TIMESTAMP),0)::DECIMAL(38,6) AS monetary_12m_gbp
    FROM rfm_input_orders
    WHERE customer_id IS NOT NULL AND order_timestamp >= $history_start::TIMESTAMP
      AND order_timestamp < $cutoff::TIMESTAMP
    GROUP BY customer_id
), ranks AS (
    SELECT *,count(*) OVER() AS n,
        rank() OVER(ORDER BY recency_days)-1 AS r_less,count(*) OVER(PARTITION BY recency_days) AS r_equal,
        rank() OVER(ORDER BY frequency_12m)-1 AS f_less,count(*) OVER(PARTITION BY frequency_12m) AS f_equal,
        rank() OVER(ORDER BY monetary_12m_gbp)-1 AS m_less,count(*) OVER(PARTITION BY monetary_12m_gbp) AS m_equal
    FROM features WHERE frequency_12m>=1
), scores AS (
    SELECT customer_id,
        6-(1+least(4,(5*(2*r_less+r_equal))//(2*n))) AS r_score,
        1+least(4,(5*(2*f_less+f_equal))//(2*n)) AS f_score,
        1+least(4,(5*(2*m_less+m_equal))//(2*n)) AS m_score
    FROM ranks
), scored AS (
    SELECT f.*,s.r_score,s.f_score,s.m_score,
        historical_order_count>=2 AND recency_days>90 AS reactivation_candidate
    FROM features f LEFT JOIN scores s USING(customer_id)
)
SELECT *,CASE
    WHEN frequency_12m=0 THEN 'Dormant beyond 12 months'
    WHEN frequency_12m>=2 AND recency_days>90 THEN 'At Risk Repeat'
    WHEN frequency_12m=1 AND recency_days>90 THEN 'Inactive Single-Purchase'
    WHEN frequency_12m>=2 AND recency_days<=90 AND r_score>=4 AND f_score>=4 AND m_score>=4 THEN 'Champions'
    WHEN frequency_12m>=2 AND recency_days<=90 THEN 'Loyal'
    WHEN frequency_12m=1 AND recency_days<=90 AND first_order_timestamp >= $cutoff::TIMESTAMP-INTERVAL '30 days' THEN 'Promising New'
    ELSE 'Recent Occasional' END AS segment
FROM scored;
ALTER TABLE rfm_snapshot ADD PRIMARY KEY(customer_id,snapshot_date);
