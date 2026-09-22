# Step 10 - Cohort Validation and Visualization

**Status: complete.** The executed [cohort notebook](../notebooks/ecommerce_retention_analysis.ipynb) independently verifies invoice histories, repeat windows and every cohort cell, then displays the figures below. The plotting runner is `python src/visualize_analysis.py`; run customer analysis first for the additional Step 11-12 figures.

![Cohort purchasing retention](../images/cohort_retention_heatmap.png)

The chart shows March 2010-November 2011 first-observed cohorts, including cohort sizes. Month 0 is 100% for each nonempty cohort. Gray means the target month is beyond the reporting cutoff; it is not zero. All observable primary-cohort cells are plotted through Month 20; higher indices are unobservable for every primary cohort and remain in the exported table. The initial three history cohorts remain outside this main chart.

Customers can skip months and return, so a row need not decline monotonically. Cohorts also encounter different seasonal periods: a higher later cell does not establish improved retention caused by a business intervention. The relatively small December 2010 and January 2011 cohorts are visibly labeled; their percentages warrant caution.

![Fixed-window repeats](../images/repeat_purchase_windows.png)

The left panel uses each duration's own mature population; the right panel holds the 90-day-mature population fixed. The latter rates are 19.55%, 32.81% and 41.14% for 30/60/90 days. Calendar Month 1 is not a 30-day repeat window. A purchase exactly at the inclusive elapsed-day boundary counts only if the whole window is observed before the exclusive cutoff.

The [validation record](visualization_validation.json) records the actual plotted/masked cells and independent checks. Both data validation and notebook execution passed. Labels show denominators, fraction axes are displayed as percentages, and unobserved cells remain masked. The heatmap colors encode 0-100% consistently across cohorts.

Source/exclusion limitations in the [retention report](retention_analysis.md) still apply. This stage supplies validated descriptive figures; no acquisition-campaign effect is inferred.
