# Steps 8-9 - Repeat Purchasing and Cohort Retention

**Status:** both steps complete under metric contract 1.1. Source: historical UK Online Retail II; eligible identified purchase invoices before 2011-12-01. Main first-observed cohorts begin 2010-03-01. Full history from 2009-12-01 is retained to establish first purchases.

## Reproduce and outputs

After the documented cleaning stage, run `python src/retention_analysis.py` from the project root. It executes [customer behavior SQL](../sql/03_customer_behavior.sql) and [cohort SQL](../sql/04_cohort_retention.sql), validates results against independent Python invoice histories, and rebuilds five tables in a single transaction. Failed validation rolls back the rebuild. Parquet exports follow commit; rerun after an interrupted export. Rebuild after cleaning changes. Input and SQL fingerprints are in [the validation summary](retention_summary.json).

The tables are `customer_purchase_history` (one identified invoice), `customer_repeat_windows` (one customer/window), `repeat_purchase_summary` (one population/window), `cohort_retention` (one cohort/month index), and `cohort_retention_pooled` (one month index). All have primary keys and matching local Parquet exports. Tracked aggregate CSVs: [repeat rates](../data/processed/repeat_purchase_summary.csv), [cohort cells](../data/processed/cohort_retention.csv), [pooled cohorts](../data/processed/cohort_retention_pooled.csv), and [primary cohort matrix](../data/processed/cohort_retention_matrix.csv). Customer-level outputs stay in ignored processed data.

## Step 8: behavior and fixed-window repeats

There are **35,751 identified invoices** belonging to **5,821 customers**. Across unequal full observed histories, **1,647 customers have one purchase** and **4,174 have at least two**. These counts are descriptive; they are not a comparable fixed-window rate. **4,127 customers** fall in the main first-observed cohort scope; **1,694 earlier customers** remain in history but are excluded from headline repeat denominators.

For D days, eligibility requires `first purchase + D days < cutoff`. A second distinct invoice at or before that inclusive window end counts. Incomplete windows are excluded from both numerator and denominator, even if a second purchase is already observed. Dates use source timestamps; no day rounding is used for eligibility. Two different invoices at the same timestamp count in the primary definition.

| Population | Days | Eligible customers | Incomplete windows | Repeated | Repeat rate | Rate collapsing equal timestamps |
|---|---:|---:|---:|---:|---:|---:|
| common_90_day | 30 | 3,529 | 598 | 690 | 19.55% | 19.52% |
| common_90_day | 60 | 3,529 | 598 | 1,158 | 32.81% | 32.79% |
| common_90_day | 90 | 3,529 | 598 | 1,452 | 41.14% | 41.14% |
| own_window | 30 | 3,935 | 192 | 794 | 20.18% | 20.10% |
| own_window | 60 | 3,714 | 413 | 1,246 | 33.55% | 33.47% |
| own_window | 90 | 3,529 | 598 | 1,452 | 41.14% | 41.14% |

`own_window` allows each duration its own mature population. `common_90_day` uses the same 90-day-mature customers for 30/60/90-day comparisons; its repeat counts must be nondecreasing. Neither population includes the initial-history cohorts. The last column collapses same-customer/same-timestamp invoices into one occasion, then looks for the next later timestamp; it keeps the same denominators. It is a sensitivity calculation, not a change to the primary definition.

Among the **1,452** primary customers who repeated within 90 days and had a complete 90-day window, the **conditional median time to second invoice is 32.00 days**. Their corresponding 90-day repeat rate is **41.14%**. This median describes those repeaters only; nonrepeaters are not assigned zero or 90 days. Same-timestamp repeats may contribute zero-day intervals.

## Step 9: calendar-month cohort retention

The complete table contains **576 cells**, covering all 24 first-purchase calendar months and month indices 0-23. The main matrix contains the 21 cohorts from March 2010 onward. Earlier cohorts are retained in the long table with `is_primary_cohort=false`.

Each customer contributes once per activity month, regardless of invoice count. Month 0 equals cohort size and has 100% retention for nonempty cohorts. A cell is observable only when its target month's end-exclusive boundary is at or before the cutoff. Observable months without purchases are zero; future counts and rates are null. Empty cohort rates are also null. Blank CSV matrix cells represent undefined/unobserved rates, not zero retention. See the long table's observation flag and cohort size to distinguish them.

Selected pooled results below sum retained customers and cohort sizes over **mature primary cohorts only**. This avoids averaging percentages or treating immature cohorts as failures. Each month index can have a different contributing cohort population.

| Month index | Mature nonempty cohorts | Eligible customers | Retained | Pooled purchasing retention |
|---|---:|---:|---:|---:|
| 0 | 21 | 4,127 | 4,127 | 100.00% |
| 1 | 20 | 3,935 | 814 | 20.69% |
| 2 | 19 | 3,714 | 756 | 20.36% |
| 3 | 18 | 3,526 | 673 | 19.09% |
| 6 | 15 | 3,210 | 558 | 17.38% |
| 12 | 9 | 2,541 | 462 | 18.18% |
| 18 | 3 | 990 | 170 | 17.17% |
| 20 | 1 | 441 | 94 | 21.32% |
| 21 | 0 | 0 | 0 | N/A |
| 23 | 0 | 0 | 0 | N/A |

Month 1 measures a purchase in the next calendar month and is different from a repeat within 30 elapsed days. Monthly purchasing retention is not continuous survival: a customer may skip a month and return, so cohort rates need not fall monotonically.

## Limits, verification and next step

Both analyses use identified accounts and first observed purchases, not verified new people. Missing identity, quarantined headers, unresolved manual/sample/image entries, the gross-purchase/credit policy and source trading-date gaps remain relevant. Apparent differences across cohorts are descriptive and may reflect changing acquisition mix, seasonality or coverage. No causal campaign effect or business improvement is established.

Every customer-window flag and every cohort cell was checked against independent Python histories built directly from invoices. Sequence/gap checks, denominator checks, common-population monotonicity, same-timestamp sensitivity, Month 0, future nulls and maturity-weighted pooling passed. Synthetic SQL cases checked exact window boundaries, a window ending at the cutoff, incomplete-window repeaters, an empty cohort, an observed zero-purchase cell, and a skipped month followed by return. CSV and Parquet exports were reconciled to database rows.

For completed downstream work, see [cohort visualization](cohort_visualization.md), [RFM and customer comparisons](customer_value_and_segments.md), and the [final case study](case_study.md).
