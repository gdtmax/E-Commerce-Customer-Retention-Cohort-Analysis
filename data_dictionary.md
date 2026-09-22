# Data Dictionary and Metric Definitions

**Specification version 1.1, 2026-09-22.** Step 6 implements staging, eligible order lines, orders, customer history features, and monthly customer activity. Step 7 implements the monthly KPI table. Steps 8-9 implement purchase histories, repeat windows and cohort retention. Steps 10-12 implement the figures, RFM snapshot, observed value and customer-group comparisons. Step 2 intake counts are not final metric results.

The source is the unchanged UCI Online Retail II workbook identified in [`data/raw/source_manifest.json`](data/raw/source_manifest.json). Selection evidence is in [`reports/dataset_selection.md`](reports/dataset_selection.md). Shared parameters are recorded in [`src/metric_spec.json`](src/metric_spec.json), and worked examples are in [`reports/metric_examples.md`](reports/metric_examples.md).

## 1. Reporting dates and units

| Parameter | Contract |
|---|---|
| Currency | GBP; do not convert values to imply a Vietnamese source |
| Raw coverage | 2009-12-01 07:45:00 through 2011-12-09 12:50:00 |
| Analysis history start, inclusive (`H`) | 2009-12-01 00:00:00 |
| Analysis cutoff, exclusive (`T`) | 2011-12-01 00:00:00 |
| Main order population | Eligible purchase invoices with `H <= order_timestamp < T` |
| Complete monthly reporting periods | December 2009 through November 2011, inclusive |
| Primary first-observed cohort start (`C`) | 2010-03-01 00:00:00 |
| Initial history period | December 2009 through February 2010; retained in customer histories and monthly KPIs, excluded from headline acquisition-cohort comparisons |
| RFM measurement start, inclusive (`W`) | 2010-12-01 00:00:00; frequency and monetary value use `[W, T)` |
| RFM reference date | 2011-12-01; recency uses calendar-date subtraction |
| Repeat-purchase windows | 30, 60, and 90 elapsed days; 180 days is supplementary |
| Timestamp handling | Source wall-clock timestamps without timezone conversion; the source does not establish a timezone |
| Day arithmetic | One elapsed day means 24 hours of source timestamp arithmetic; do not add inferred timezone/DST corrections |

The cutoff is deliberately fixed at the start of the last partial month. December 2011 source rows remain in raw/staging data but do not enter the main metrics. A later partial-period appendix must use a separately named cutoff and must not silently change the primary measures.

The initial history period reduces one source of acquisition bias but cannot prove that later customers are genuinely new. Always say **first observed purchase**. These coverage choices assume the published extract is continuous; unexplained date gaps discovered in Step 5 must be resolved or documented before publication. Counts of customers eligible under this specification will differ from the broader Step 2 screen, which used the latest raw timestamp.

## 2. Source columns and normalization

**Source grain:** one recorded invoice line. There is no source order-item identifier. An invoice can contain multiple products and repeated product codes; `(Invoice, StockCode)` is not a unique line key.

Preserve all eight decoded source values alongside normalized values in staging. Source-row provenance must survive every exclusion decision. Use `NULL` for missing normalized values, never an invented customer ID.

| Workbook column | Normalized field | Logical type | Meaning and rule |
|---|---|---|---|
| `Invoice` | `invoice_id` | Text | Invoice reference. Trim outer whitespace and uppercase letters; retain the full code, including `C`. Do not remove prefixes or use numeric conversion. Blank or malformed IDs are audited. |
| `StockCode` | `stock_code` | Text | Source item/code reference. Trim and uppercase; retain letters and leading zeros present in the source. It is not a product category. |
| `Description` | `description` | Nullable text | Item description. Trim outer whitespace; preserve the original wording in a separate raw value. Missing descriptions do not alone invalidate an otherwise classified merchandise line. |
| `Quantity` | `quantity` | Signed integer | Recorded units. Accept only finite, exactly integral numbers; do not round fractional quantities into units. Nonpositive values do not qualify as purchases. |
| `InvoiceDate` | `invoice_timestamp` | Timestamp, seconds, no timezone | Decode the workbook's Excel 1900 date system. Round serial-date numerical noise to the nearest second; preserve the raw serial for traceability. Invalid dates are excluded and audited. |
| `Price` | `unit_price_gbp` | Exact decimal, up to 6 fractional digits | Source unit price. Parse from source numeric text with decimal arithmetic. Apply the explicit version 1.1 normalization below; preserve raw values and flags. Nonfinite or unsupported excess precision values are quarantined. Nonpositive prices do not qualify as purchases. |
| `Customer ID` | `customer_id` | Nullable text | Source customer/account identifier. Accept positive integral numeric representations and normalize, for example, `12345.0` to `12345`. Nonintegral or malformed IDs are quarantined; blank values remain null. Do not treat the IDs as verified people. |
| `Country` | `country` | Nullable text | Source country label. Trim outer whitespace; preserve labels such as `EIRE`. Blank and literal `Unspecified` map to unknown for segmentation, while their original values remain available. Do not infer cities or silently modernize geographic labels. |

Use exact decimal arithmetic for money throughout SQL and Python. Logical monetary totals use precision sufficient for 18 integer digits and 6 fractional digits, or a wider exact type. Do not round each line before aggregation. Display money to two decimal places using half-up rounding; calculations retain full accepted precision. Percentages are stored as fractions in `[0, 1]` and displayed as percentages.

### Version 1.1 price normalization

The Step 5 audit found 112,879 Excel-serialized prices with tiny decimal tails; the maximum deviation from a six-decimal value was 3e-12 GBP. Parse as Decimal. Accept half-up normalization to six decimals only when absolute deviation is at most 1e-9 GBP, preserving `raw_price` and `price_normalized`. Larger deviations or nonfinite/out-of-range values remain invalid. This replaces version 1.0's strict rejection of every extra decimal place; it does not change positivity, date windows, customer populations, or monetary aggregation. Normalized prices also participate in invoice multiset and duplicate comparisons.

## 3. Lineage and table grains

| Planned table/view | Grain and key | Purpose |
|---|---|---|
| `raw_order_lines` | One physical Excel data row; key `(source_sheet, source_row_number)` within the pinned workbook | Preserve source values and the workbook checksum; Excel row 1 is the header and data starts at row 2 |
| `stg_order_lines` | One source row, same lineage key | Normalized values, parse flags, code classification, overlap decisions, duplicate decisions, and exclusion reasons |
| `fact_order_lines` | One retained, eligible merchandise line; stable key inherited from its source row | Positive purchase amounts and unit counts; `invoice_id` is a many-to-one link to `fact_orders` |
| `fact_orders` | One eligible invoice; key `invoice_id` | Order timestamps, resolved customer, country, basket totals, and attribution status |
| `customer_features` | One nonmissing customer with an eligible historical purchase before `T`; key `customer_id` | Full observed history, first order, cohort, last order, and historical value |
| `customer_month_activity` | One customer per purchasing month; key `(customer_id, activity_month)` | Deduplicated customer presence used for cohort calculations |
| `monthly_kpis` | One calendar month in the reporting range | Business totals, identified customer counts, coverage, and trends |
| `cohort_retention` | One first-observed cohort month and month index; key `(cohort_month, month_index)` | Cohort sizes, retained-customer counts, observation flags, and retention rates |
| `rfm_snapshot` | One historical customer per snapshot date; key `(customer_id, snapshot_date)` | Trailing-year RFM features, scores, segments, and inactivity flags |

DuckDB stores the raw, staging, fact-order-line, fact-order, customer-feature and customer-month-activity tables. `monthly_kpis` is materialized in Step 7; `cohort_retention` is materialized in Step 9; `rfm_snapshot` is materialized in Step 11, with all historical customers retained. `product_roles` is the reviewed code lookup; two sensitivity views preserve within-sheet duplicate variants. Run `src/clean_data.py` after the audit to rebuild the Step 6 tables. A product lookup may be added where it improves analysis, but must not invent a native category taxonomy. When joining order headers to lines, do not sum duplicated header totals. Aggregate at the declared grain before combining measures.

Required staging metadata consists of `source_workbook_sha256` (text), `source_sheet` (text), `source_row_number` (integer), `product_role` (one of the three documented classification labels), `overlap_status` (unique/matching-copy/conflict/resolved), `is_exact_duplicate` (boolean), `parse_errors` and `exclusion_reasons` (collections of reason codes), and `is_eligible_purchase_line` (boolean). Preserve every applicable reason rather than making overlapping reason counts appear additive. At invoice level retain flags for inherited customer identity, unknown/conflicting country, and unresolved header conflict. The Step 6 staging table implements these fields, plus `primary_disposition` for an additive waterfall and `price_normalized` for monetary provenance. `is_eligible_purchase_line` includes the primary reporting-window restriction. All applicable exclusion reasons are preserved, even where they overlap.

## 4. Worksheet overlap and repeated rows

Apply these rules before financial aggregation, customer sequencing, or cohort assignment:

1. Normalize valid values while retaining originals and lineage. For cross-sheet comparisons, build an invoice payload as a **multiset** of its eight normalized source fields. Counts of identical lines are part of that payload; sheet name and row number are not.
2. If an invoice occurs in only one worksheet, retain that worksheet's version for further processing, including invoices in the overlapping date range. Do not remove all December 2010 rows from one sheet by date alone.
3. If an invoice occurs in both sheets with identical payloads, keep its version from `Year 2010-2011` and mark all rows of the older version `overlap_copy`. Do not combine the two versions.
4. If the payloads differ, mark the invoice `overlap_conflict` and hold both versions out of primary metrics until a documented resolution is recorded. No automatic latest-version assumption is allowed for conflicting payloads. The unresolved count and candidate monetary exposure must be reported.
5. Within the retained invoice version, rows identical on all eight normalized fields are treated as duplicate exports in the primary analysis. Keep the earliest source row, mark later occurrences `exact_duplicate`, and record the count and amount affected. This is an explicit assumption because the source lacks line IDs. A sensitivity calculation retaining these within-sheet repeats is required for sales, AOV, and monetary segmentation before final conclusions.

Never deduplicate on invoice or product code alone. Never add the Step 2 within-sheet and cross-sheet duplicate counts as if they were mutually exclusive. Steps 5 and 6 audit the consequences of this policy; any revised resolution must be logged with a version change before metrics are released.

## 5. Transaction eligibility, codes, and customer assignment

### Product-code classification

Maintain a documented mapping from `stock_code` to `merchandise`, `non_merchandise`, or `unresolved`, with the rule or evidence used. A normal-looking code is only a classification candidate, not proof of merchandise. Postage, fees, discounts, manual adjustments, and accounting entries must not be included as merchandise merely because their quantities and prices are positive. Unknown special codes remain `unresolved` until audited. The versioned mapping is `src/product_roles.csv`, with one entry for every source code, source-description evidence and decision reasons. Its scope and limitations are documented in `reports/cleaning_report.md`.

### Valid invoice header

- A purchase invoice has a numeric-only normalized ID matching `^[0-9]+$`, a valid single timestamp, and no unresolved overlap conflict. `C`-prefixed references are cancellation/credit records; other reference formats are held for review and do not become purchases automatically.
- If the retained invoice has multiple timestamps, malformed nonblank customer IDs, or more than one nonmissing normalized customer ID, quarantine the invoice pending review. Do not arbitrarily pick a timestamp or customer. Invalid timestamp rows also prevent a valid single header until resolved.
- If there is exactly one valid nonmissing customer ID and other lines have blank IDs, assign that ID to the invoice; flag the inheritance as `customer_id_inherited_within_invoice`. If all IDs are missing, the invoice remains unidentified.
- A country disagreement does not manufacture a second customer or automatically invalidate sales. Use the unique known country if there is exactly one; otherwise set invoice country to unknown and flag the conflict. Retain provenance of the inference.

### Eligible purchase lines and invoices

A purchase line must belong to a valid invoice, survive overlap and duplicate handling, have a nonblank classified merchandise code, a valid positive integer quantity, and a valid strictly positive price. `line_sales_gbp = quantity * unit_price_gbp`.

An eligible purchase invoice contains at least one such line. Basket value and units include only eligible merchandise lines. Non-merchandise and invalid lines stay in the audit trail with separate exposure measures; they do not contribute to the basket. Thus a valid invoice can remain eligible after a fee or adjustment line is excluded. The existence of any unresolved classification must be disclosed in the final coverage audit; material unresolved exposure must be resolved before business conclusions.

There is no order-fulfillment status in this dataset. Call these **eligible purchase invoices**, not verified delivered or completed orders.

| Population | Inclusion | Use |
|---|---|---|
| `all_orders` | Eligible invoices in `[H, T)`, including invoices with no customer ID | Overall orders, gross merchandise sales, AOV |
| `identified_orders` | `all_orders` with a resolved nonmissing customer ID | Active customers, purchase histories, repeat purchasing, cohorts, RFM, customer value |
| `primary_cohort_customers` | Customers whose first eligible observed purchase in full `[H, T)` history is on or after `C` | Headline cohort comparisons and fixed-window repeat rates |

Never assign all missing customer IDs to one synthetic customer. Count unidentified sales in overall totals where eligible, and report customer-linkage coverage beside customer analytics.

### Cancellation, credit, and return treatment

`C`-prefixed invoices and nonpositive quantity/price lines are excluded from positive purchase measures. They remain available in staging for separate audit. A negative merchandise quantity with a positive price can contribute to a separately labeled **observed merchandise credit magnitude** (`abs(quantity * price)`), after the same overlap and classification checks, dated by its own record timestamp.

Do not strip `C` and assume a match to the original purchase. There is no verified purchase-to-refund linkage at this step. A later credit does not retroactively remove a historical purchase event under the primary gross-purchase definition. This limitation must accompany spending-based segments. Do not label positive sales minus credits as profit, settled cash, or verified net revenue.

## 6. Required derived fields

### Invoice-level fields (`fact_orders`)

| Field | Definition |
|---|---|
| `invoice_id` | Unique retained purchase invoice reference |
| `order_timestamp` | Validated common timestamp of the retained invoice |
| `order_date` / `order_month` | Calendar date / first day of the timestamp's calendar month |
| `customer_id` / `is_identified` | Resolved invoice-level customer ID / whether it is nonmissing |
| `invoice_country` | Resolved known country or null |
| `order_sales_gbp` | Sum of eligible merchandise `line_sales_gbp` within this invoice |
| `order_units` | Sum of eligible merchandise quantities |
| `distinct_products` | Count of distinct merchandise `stock_code` values on eligible lines |
| `eligible_line_count` | Retained eligible line count, not the quantity sum |
| `customer_order_sequence` | For identified invoices, order by timestamp ascending, then invoice ID ascending using ordinal text order; starts at 1 |

### Customer-level fields (`customer_features`)

| Field | Definition |
|---|---|
| `first_order_id`, `first_order_timestamp` | First identified eligible invoice in `[H, T)` using the deterministic order above |
| `second_order_id`, `second_order_timestamp` | Second distinct eligible invoice, if observed before `T`; otherwise null |
| `last_order_timestamp` | Latest eligible timestamp before `T` |
| `cohort_month` | First day of the first observed purchase month |
| `is_initial_history_customer` | First observed purchase is before `C` |
| `historical_order_count` | Distinct eligible invoices across full `[H, T)` history |
| `historical_sales_gbp` | Eligible gross merchandise sales across full `[H, T)` history; not predicted CLV |
| `time_to_second_order_days` | Exact elapsed seconds from first to second purchase divided by 86,400; null if no second invoice |
| `first_order_sales_gbp`, `first_order_distinct_products` | Basket features from the deterministic first invoice only |
| `first_order_country` | Country of that first invoice, including unknown; do not backfill it from future purchases |
| `recency_days` | `date(T) - date(last_order_timestamp)`; a purchase on 2011-11-30 has recency 1 |

Two different invoices at the same timestamp count as separate observed invoices and produce a zero-day repeat interval. Flag this situation for a sensitivity check that collapses same-customer, same-timestamp invoices. Never treat repeated item rows as separate purchases.

## 7. Monthly KPI definitions

For a calendar month `m`, let `A_m` be `all_orders` in that month and `I_m` its identified subset. Use a calendar spine so empty observed months appear with zero counts. Undefined ratios are `NULL`, not zero.

| Metric | Exact definition | Unit / denominator |
|---|---|---|
| `orders` | Number of invoices in `A_m` | Invoices |
| `gross_merchandise_sales_gbp` | Sum of `order_sales_gbp` in `A_m` | GBP; before credit adjustments, excluding classified non-merchandise lines |
| `average_order_value_gbp` | Gross merchandise sales divided by `orders` | GBP per invoice; null for zero orders |
| `active_customers` | Distinct nonmissing customer IDs in `I_m` | Purchasing customer accounts, not app/site active users |
| `new_observed_customers` | Active customers whose first observed eligible purchase month equals `m` | Customers |
| `returning_customers` | Active customers whose first observed purchase month is earlier than `m` | Customers |
| `returning_customer_share` | Returning customers divided by active customers | Fraction; null for zero active customers |
| `identified_order_share` | Number of invoices in `I_m` divided by `orders` | Fraction |
| `identified_sales_share` | Sales in `I_m` divided by sales in `A_m` | Fraction; null if denominator is zero |
| `sales_mom_growth` | `(sales_m - sales_previous_calendar_month) / sales_previous_calendar_month` | Fraction; null for first month or zero prior sales |

New and returning customer counts are disjoint and sum to active customers. A customer who buys twice during their first observed month remains a new observed customer for that month, even though their second order is a repeat purchase. Returning-customer share is not a retention rate.

For reports, replace the broad label “revenue” with **gross merchandise sales (GBP)**. It is a transparent source-derived proxy; the data does not establish all accounting components necessary to claim company revenue or profit.

## 8. Fixed-window repeat purchasing

For each customer in `primary_cohort_customers`, let `t1` be the first eligible observed purchase and `t2` the next distinct eligible invoice, if any. For a window of `D` days:

```text
eligible_D = (t1 + D days < T)
repeated_D = eligible_D AND (t2 exists) AND (t2 <= t1 + D days)
repeat_purchase_rate_D = count(repeated_D) / count(eligible_D)
```

The eligibility comparison is strictly `< T` because the upper event boundary is inclusive while the data cutoff is exclusive. A second invoice exactly `D` elapsed days after the first counts; a customer whose window ends exactly at `T` is not eligible. Use timestamps, not rounded day differences, to decide inclusion.

Rules:

- Exclude incomplete-window customers from **both** numerator and denominator, even if they already repurchased.
- Publish eligible counts and repeat counts beside each rate. A zero denominator produces null.
- Each window normally has its own eligible population. When comparing 30/60/90-day progression, also calculate a labeled common-population view using only 90-day-eligible customers; otherwise rates need not be monotonic.
- Segment rates use the same formula within the first-order segment. Do not filter the second order to the first-order country, product, or basket band.
- Full-history customers first seen before `C` may be shown in a separately labeled sensitivity appendix; they are not silently mixed into the headline denominator.

For time-to-second-order summaries, use the common 90-day-eligible population and only customers with `t2 <= t1 + 90 days`. Label the median **“median days to second order among customers who repeated within 90 days”** and report the number of such customers and the 90-day repeat rate beside it. Do not assign 90 days or zero to nonrepeaters, or claim this conditional median describes all customers.

## 9. Monthly cohort retention

Assign each identified customer to their first observed purchase month using full history. The main heatmap starts with March 2010 cohorts; initial-history cohorts may appear in a separate labeled appendix.

```text
month_index = 12 * (year(activity_month) - year(cohort_month))
              + month(activity_month) - month(cohort_month)
cohort_size = distinct customers first observed in cohort_month
retained_customers_k = distinct cohort customers with >= 1 purchase in month k
retention_rate_k = retained_customers_k / cohort_size
```

- Month 0 is the first observed purchase calendar month and is 100% for nonempty cohorts.
- One customer contributes at most once per cohort-month cell, regardless of invoice count.
- A cell is observable only when the target month's end-exclusive boundary is `<= T`. Target months beginning at or after `T` are unobserved: set retained count and rate to null.
- Observed cells with no purchases have retained count 0 and rate 0. A cohort with no customers has no rate.
- This is purchasing in a specific month, not continuous survival or “ever returned by month k.” A customer may disappear for a month and return later; retention need not decrease monotonically.
- Pooled Month-k retention is `sum(retained_customers_k) / sum(cohort_size)` over fully observed, in-scope cohorts. Never average cohort percentages without weighting or include immature cohorts in that denominator.
- Month 1 is a calendar-month measure, not a 30-day repeat-purchase measure.

## 10. Customer value and concentration

Historical customer sales and frequency use all identified eligible invoices in `[H, T)`, including initial-history customers. Label them as observed history. Comparisons across acquisition cohorts must also show tenure or use a fixed-window value measure; longer observation naturally allows more purchases.

For the optional `customer_sales_90d`, use primary-cohort customers eligible for the 90-day window and sum their eligible invoice sales for `t1 <= timestamp <= t1 + 90 days`, including the first invoice. Its mean is a fixed-window historical measure, not a lifetime forecast.

For a top-10% customer concentration chart, rank all historical identified customers by `historical_sales_gbp` descending and then `customer_id` in ordinal text order. Select exactly `ceil(0.10 * N)` customers. Divide their historical sales by sales of **all identified historical customers**. Disclose the tie rule and identified-sales coverage; do not divide by unidentified-inclusive total sales. Never present the ranking as a recommendation to allocate budget without testing incremental value.

## 11. RFM snapshot and segments

The snapshot is as of `T`. Include all historical identified customers in the snapshot table. Calculate:

- **R:** `recency_days` from full eligible history.
- **F:** distinct eligible invoices in `[W, T)`.
- **M:** eligible gross merchandise sales in `[W, T)`.

Customers with `F = 0` have `M = 0`, null R/F/M scores, and segment `Dormant beyond 12 months`. They remain in the snapshot and are reported separately. Calculate score distributions only among customers with `F >= 1`. These trailing-year values are intentionally different from full-history customer value.

### Ties and scoring

For a measure value `x` among `N` scorable customers, let `L` be the number of values strictly below `x` and `E` the number equal to `x`. Define:

```text
ascending_score(x) = 1 + min(4, floor(5 * (2 * L + E) / (2 * N)))
R_score = 6 - ascending_score(recency_days)
F_score = ascending_score(frequency_12m)
M_score = ascending_score(monetary_12m_gbp)
```

Identical values receive identical scores; groups need not have equal sizes and not all five scores must occur. If all values tie, each receives score 3. Do not split ties arbitrarily using `NTILE` or customer ID. Store scores separately; an `RFM_code` can concatenate them for display but must not be used as a numerical average.

### Segment assignment: first matching rule wins

| Priority | Segment | Condition |
|---|---|---|
| 1 | `Dormant beyond 12 months` | `F = 0` |
| 2 | `At Risk Repeat` | `F >= 2` and `recency_days > 90` |
| 3 | `Inactive Single-Purchase` | `F = 1` and `recency_days > 90` |
| 4 | `Champions` | `F >= 2`, `recency_days <= 90`, and each of R/F/M scores is at least 4 |
| 5 | `Loyal` | `F >= 2` and `recency_days <= 90` |
| 6 | `Promising New` | `F = 1`, `recency_days <= 90`, and `first_order_timestamp >= T - 30 days` |
| 7 | `Recent Occasional` | All remaining scorable customers |

“Single-Purchase” refers to the trailing year, not necessarily the customer's entire history. Segment labels are operational rules, not verified loyalty, psychological intent, or confirmed churn. Segment monetary contribution uses M and the total trailing-year identified sales denominator; do not mix it with full-history concentration.

For an explicit reactivation candidate flag, use `historical_order_count >= 2 AND recency_days > 90`, including dormant customers. The 90-day threshold is a starting business rule, not a learned truth. Report customer counts and historical sales for 60-, 90-, and 120-day thresholds before recommending a campaign. Customer contact details and marketing consent are unavailable; the project proposes an analysis, not an executable mailing list.

## 12. First-order comparisons and uncertainty

Freeze comparison features at the first eligible invoice:

| Feature | Groups |
|---|---|
| First-order basket value | `Under GBP 50`: `0 < x < 50`; `GBP 50–<100`: `50 <= x < 100`; `GBP 100–<250`: `100 <= x < 250`; `GBP 250+`: `x >= 250` |
| First-order product diversity | `1 product`; `2–5 products`; `6+ products`, based on distinct merchandise codes |
| First-order geography | `United Kingdom`, `Other known country`, `Unknown`; individual countries only where sample sizes support comparison |

Value bands are predefined descriptive cutoffs, not optimal thresholds or inferred wholesale labels. If a band is too small, disclose it rather than adjusting boundaries to obtain a favorable result.

Use the 90-day eligible primary-cohort population for the main comparison. Report eligible `n`, repeated `x`, the raw fraction `x/n`, and a 95% Wilson interval. Groups with `n < 100` have counts but no headline percentage, interval, ranking, or recommendation based on their rate. The threshold is a reporting convention, not a guarantee of statistical power. Unknown geography is a visible coverage group, not a country to target.

For published groups, with `p = x/n` and `z = 1.959963984540054`:

```text
center = (p + z*z/(2*n)) / (1 + z*z/n)
half_width = z * sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
interval = [max(0, center-half_width), min(1, center+half_width)]
```

Acquisition-month mix can explain raw differences. Show counts and rates by first-observed month where supported. Any descriptive standardized comparison must use the same shared cohort months for all compared groups, at least 20 eligible customers per group-month cell, and fixed weights proportional to the pooled eligible customers in those shared months. If no usable shared set exists, do not publish an adjusted ranking. Do not attach the raw Wilson interval to a standardized rate. Country and basket associations remain noncausal, even after this adjustment.

## 13. Validation and change control

The implementation must verify:

- One retained header per invoice and traceable source rows for every retained/excluded line.
- All primary timestamps lie in `[H, T)`; all primary cohort first purchases lie in `[C, T)`.
- Identified orders/sales never exceed overall orders/sales under the same scope.
- Monthly new plus returning customers equals active customers.
- Repeat numerator is at most its eligible denominator; common-population 30/60/90-day rates are nondecreasing.
- Cohort Month 0 equals cohort size; unobserved cells are null; observed empty cells are zero.
- Customer historical sales reconcile to identified order sales; RFM M reconciles to identified sales within `[W, T)`.
- Each historical customer has exactly one snapshot segment, including dormant customers.
- Duplicate, unresolved-code, missing-ID, and conflicting-invoice effects appear in the coverage audit.

Worked boundary cases are specified in [`reports/metric_examples.md`](reports/metric_examples.md). Steps 5–6 must populate the product-code mapping and investigate invoice conflicts before primary results are accepted. Their existence is a declared implementation dependency, not an undefined metric formula.

Version changes must state the old rule, new rule, evidence, and affected outputs here. Update [`src/metric_spec.json`](src/metric_spec.json), the examples, SQL, Python, and dashboard calculations together; never silently change a denominator to match an expected result.

| Version | Change |
|---|---|
| 1.1 | Accept bounded six-decimal normalization for demonstrated Excel serialization tails, with raw-value preservation and correction flags. Recompute payload matching with accepted prices. Implement the reviewed product mapping, quarantine unresolved headers, and materialize Step 6 base tables; no headline metric denominators changed. |
| 1.0 | Initial Step 3 contract: dates, source mappings, grains, transaction rules, metric formulas, RFM segmentation, and comparison conventions |

## Steps 5-6 implementation note

The [raw-data audit](reports/data_quality_report.md) is a historical Step 5 snapshot under version 1.0. Its provisional price scenario is now accepted explicitly in version 1.1. The raw table and workbook remain unchanged. [The cleaning report](reports/cleaning_report.md) records the implemented decisions, table counts, additive exclusion waterfall, coverage and validation. Original audit counts remain available for comparison.

Unresolved product roles and conflicting invoice headers are excluded with reasons, not guessed. The source date-gap limitation remains documented; the pipeline creates no synthetic purchases. The eligible order tables represent gross purchase events and do not establish verified purchase-to-credit linkage. Downstream business conclusions must retain these limitations.

## Step 7 implementation note

[The monthly report](reports/monthly_kpis_report.md) and [SQL](sql/02_monthly_kpis.sql) implement the existing KPI definitions for all 24 complete calendar months. `month` is a DATE primary key. In addition to defined KPIs, the physical table retains identified/unidentified order counts and sales, plus previous-calendar-month sales, to expose the ratio denominators. Monetary sums use DECIMAL(38,6). AOV uses Decimal division with half-up rounding to six stored decimals, displayed to two; percentage ratios use DOUBLE fractions and null for zero denominators. This is an implementation detail and does not change the metric formulas or population. Run `src/monthly_kpis.py` after cleaning to refresh the table and exported outputs.

## Steps 8-9 implementation note

Run `src/retention_analysis.py` after cleaning. `customer_purchase_history` has one identified invoice, its deterministic sequence and previous-invoice gap. `customer_repeat_windows` has one customer per 30/60/90-day window, eligibility/repeat flags, a primary-cohort flag and the same-timestamp sensitivity variant. `repeat_purchase_summary` has one row per window and population (`own_window` or `common_90_day`). All customer populations derive their first purchase from complete eligible history.

`cohort_retention` uses a full calendar grid: all 24 source reporting cohort months crossed with month indices 0-23. Initial-history cohorts are retained with `is_primary_cohort=false`. It stores activity month, cohort size, `is_observable`, nullable retained count and nullable rate. Future counts/rates are null; empty cohorts have size zero and null rates. `cohort_retention_pooled` sums counts and cohort sizes over observable primary cohorts only. Indices with no mature primary cohorts have zero eligible counts and null rates. Neither cohort rates nor own-window repeat rates are required to decline/increase monotonically. Only the repeat counts for the common 90-day population must be nondecreasing across 30/60/90 days.

See [the Steps 8-9 report](reports/retention_analysis.md) for exact populations, output files, conditional-median interpretation and validation. These stages implement version 1.1 without changing formulas or denominators. The optional 180-day supplement is not included in the primary deliverable.

## Steps 10-12 implementation note

`sql/05_rfm_segments.sql` materializes the specified snapshot. `rfm_keep_duplicates` and `rfm_exclude_extreme` recompute the same scoring/segment rules for sensitivity inputs. Dormant scores remain NULL. All money inputs and sums remain exact Decimal; plotted shares use floating-point presentation values.

`customer_value` contains historical rank, observed tenure and nullable 90-day sales. `customer_comparison_population` freezes first-invoice values for the 90-day-eligible primary population. SQL uses the existing bands; Python applies Wilson intervals, sample thresholds and cohort standardization. A joint value-by-diversity table is a descriptive supplementary comparison with the same n>=100 reporting rule.

For standardization, full-population publishable groups define the comparison. Shared months must contain at least 20 eligible customers for every compared group. The n>=100 publishing guard also applies to the total shared population per group: if any group falls below it, standardized rates for that feature are suppressed rather than changing groups after inspecting outcomes. This is a conservative implementation of the existing small-sample rule. Raw intervals are not attached to adjusted rates. Exact shared month lists and weights remain in the summary.

[The customer analysis report](reports/customer_value_and_segments.md) and [cohort visualization report](reports/cohort_visualization.md) explain results and limitations. The local dashboard uses the same aggregate results. These stages do not change metric contract 1.1. Campaign recommendations are hypotheses awaiting evaluation; no actual uplift or predicted lifetime value is claimed.
