# Published analysis tables

These are complete aggregate outputs for the documented analysis, not samples or customer-level order records. They are committed so reviewers can inspect results without running the pipeline.

| File | Purpose |
|---|---|
| [basket_value_product_comparison.csv](basket_value_product_comparison.csv) | First-order basket value and product diversity cross-comparison |
| [cohort_retention.csv](cohort_retention.csv) | Calendar-month retention by cohort |
| [cohort_retention_matrix.csv](cohort_retention_matrix.csv) | Wide primary-cohort retention matrix |
| [cohort_retention_pooled.csv](cohort_retention_pooled.csv) | Pooled retention by month since first purchase |
| [comparison_by_cohort.csv](comparison_by_cohort.csv) | Group comparisons within acquisition cohorts |
| [customer_comparisons.csv](customer_comparisons.csv) | First-order group comparisons and uncertainty |
| [monthly_kpis.csv](monthly_kpis.csv) | Monthly operating KPIs |
| [reactivation_thresholds.csv](reactivation_thresholds.csv) | Inactive repeat-customer thresholds |
| [repeat_purchase_summary.csv](repeat_purchase_summary.csv) | Elapsed-day repeat purchasing by population and window |
| [rfm_segments.csv](rfm_segments.csv) | RFM segment counts and value |
| [rfm_sensitivity.csv](rfm_sensitivity.csv) | RFM sensitivity to cleaning alternatives |

## Regeneration and definitions

Run `python src/run_pipeline.py` from the repository root after installing dependencies. It regenerates these tables, local detailed CSV/Parquet exports, and `retention.duckdb`. Only the 11 named aggregate CSVs and this README are allowed by `.gitignore`; detailed generated data stay local.

See [metric definitions](../../data_dictionary.md) for populations, time windows, GBP gross purchases and missing-value semantics. Future cohort rates are unobserved rather than zero; small-group comparison rates can be suppressed. No customer-level data sample is included because these aggregate results are sufficient for portfolio review.
