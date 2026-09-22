# Project brief and agreed analytical scope

This preserves the original planning decisions. The current completion record and execution instructions are in the [README](../README.md). All 14 steps are complete; optional 180-day expansion was not required.

## Business context

A fictional Vietnam-focused marketplace, inspired by the business model of platforms such as Shopee and Lazada, wants to understand how much of its customer activity comes from repeat purchasing. Management is concerned that growth may rely heavily on acquiring new customers and running promotions. This concern is a scenario to investigate, not an established finding.

The analysis uses the UK retailer's transaction history to demonstrate methods relevant to this business scenario. Findings describe the observed retailer; recommendations for a Vietnam marketplace would require local validation. The project is independent and is not affiliated with Shopee or Lazada.

The Vietnam context describes the intended business application. The selected dataset is historical UK gift retail and includes wholesale customers. It is not represented as modern Vietnamese marketplace behavior. No simulated data or synthetic marketplace fields have been added.

## Primary business question

**How can an e-commerce marketplace prioritize customer retention initiatives using evidence about repeat purchasing, cohort performance, and observed customer value?**

## Intended audience and decisions

| Audience | Decision the analysis should support |
|---|---|
| Growth and CRM teams | Which customer groups should be prioritized for a second-purchase or reactivation campaign? |
| Commercial teams | Which first-order basket characteristics are associated with stronger subsequent purchasing? |
| Business managers | How much customer activity comes from new versus returning buyers, and which retention metrics should be monitored? |
| Portfolio reviewers | Can the analyst define metrics, prepare reliable data, write substantial SQL, analyze customer behavior, and communicate actionable conclusions? |

## Analytical questions

| # | Question | Intended output | Dependency |
|---|---|---|---|
| 1 | How do monthly orders, gross merchandise sales, purchasing customers, and average order value change over time? | Monthly KPI table and trend charts | Reliable order dates, identifiers, and monetary fields |
| 2 | How much monthly customer activity comes from new versus returning buyers? | Customer composition table and chart | Stable customer identifiers and purchase history |
| 3 | What proportion of eligible customers place another order within 30, 60, and 90 days of their first observed purchase? | Repeat-purchase rates and time-to-second-order analysis | Sufficient follow-up time for each window |
| 4 | How does monthly purchasing retention differ across first-purchase cohorts? | Cohort retention table and heatmap | Sufficient historical coverage and stable customer identifiers |
| 5 | How do repeat-purchase outcomes differ by first-order basket value, item diversity, or customer country? | One or more segment comparisons | Validated basket measures, adequate group sizes, and comparable observation periods |
| 6 | How do customers differ in recency, frequency, and monetary value, and how concentrated are observed merchandise sales? | RFM segments and customer sales-concentration analysis | A fixed analysis date and reliable customer-level measures |
| 7 | Which previously purchasing customers could be considered candidates for reactivation? | Explainable inactivity rules and candidate segment sizes | Purchase-frequency evidence and a documented inactivity threshold |
| 8 | Which retention actions are supported by the evidence, and how should their effects be evaluated? | Prioritized recommendations with measurement plans | Validated findings from the preceding analyses |

## Scope and boundaries

### Core scope

- Audit and clean customer transaction data, documenting important decisions.
- Build analysis-ready tables with explicit row granularity and relationships.
- Use SQL for monthly KPIs, customer purchase histories, repeat purchasing, cohort retention, and RFM features or segments.
- Use Python/Pandas to inspect data, validate outputs, explore customer behavior, and create explanatory visualizations.
- Assess historical customer value using observed purchases and gross merchandise sales contribution.
- Translate supported findings into CRM, loyalty, cross-sell, or reactivation proposals with measurable outcomes.
- Publish documented SQL, notebooks, charts, and an English case study in a reproducible repository.

### Data-dependent scope

- First-order basket value, item diversity, and country comparisons depend on reliable derived measures and adequate group sizes. The selected source has no native categories, discounts, payment, delivery, or city/district fields.
- A 180-day repeat-purchase window may be added if sufficient follow-up is available.
- A compact local browser dashboard summarizes validated results. A Power BI Desktop execution environment was not established, so no .pbix deliverable is claimed. The portable dashboard is the completed supplementary format for this project.

### Outside the initial scope

- Predictive lifetime-value or churn models, complex machine learning, and production campaign deployment.
- Claims that discounts, categories, or delivery experiences cause retention changes without a suitable causal design.
- Claims of realized revenue uplift or retention improvement from recommendations that have not been implemented and evaluated.

## Measurement principles

The authoritative formulas and treatment rules are defined in [the data dictionary](../data_dictionary.md). The main choices are:

- **Reporting cutoff:** use transactions before 2011-12-01, excluding the partial final month from all headline metrics.
- **Cohort history:** use all observed history from December 2009; headline first-observed cohort comparisons start in March 2010 after an initial history period.
- **Sales scope:** report gross merchandise sales from eligible positive purchase invoices, with unidentified sales included in overall totals and customer-linked coverage disclosed separately.
- **RFM:** use a 2011-12-01 snapshot with trailing-12-month frequency and monetary value, tie-preserving scores, and a separate dormant group.

The following measurement principles continue to apply:

1. **Order grain:** Count distinct valid orders. Multiple items within one order must not count as multiple repeat purchases.
2. **Observed history:** A customer's first order in the dataset may not be their first-ever purchase. Cohort labels and conclusions will reflect the coverage available.
3. **Different retention measures:** Purchasing during a particular cohort month and purchasing again at any point within a fixed number of days are different measures and will be labeled separately.
4. **Complete observation windows:** Fixed-window repeat rates will include only customers with sufficient follow-up. Unobserved future cohort months will remain missing, not become zero retention.
5. **Transaction treatment:** Cancellations, refunds, returns, discounts, taxes, and shipping will be handled using documented rules supported by the dataset. Revenue labels will state what is included.
6. **RFM reference date:** Recency will use a documented analysis date. Segmentation rules will account for tied values and the actual purchase-frequency distribution.
7. **Value and inactivity:** Observed revenue is a historical measure. Inactivity-based segments indicate candidates for investigation, not confirmed permanent churn.
8. **Fair comparisons:** Segment comparisons will consider group size, acquisition timing, and observation length. Descriptive associations will not be presented as causal effects.

