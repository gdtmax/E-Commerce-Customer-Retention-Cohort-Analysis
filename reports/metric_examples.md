# Step 3 — Worked Metric and Boundary Examples

**Specification:** version 1.1 in [`data_dictionary.md`](../data_dictionary.md), with parameters in [`src/metric_spec.json`](../src/metric_spec.json).

Every transaction and customer below is **synthetic teaching data**, not an observed result from the source workbook. These examples define expected behavior for the later SQL/Python implementation. They do not constitute a completed analysis pipeline.

## 1. Item rows, invoices, and missing identity

Suppose the eligible August orders are:

| Invoice | Customer | Basket sales | History |
|---|---|---:|---|
| A01 | A | GBP 30 | A's first observed order, August 2 |
| A02 | A | GBP 70 | A's second order, August 20 |
| B02 | B | GBP 50 | B first purchased in July |
| U01 | Missing | GBP 50 | No customer identity |

Expected August outputs:

- Orders = 4; gross merchandise sales = GBP 200; AOV = GBP 50.
- Active customers = 2, new observed customers = 1, returning customers = 1.
- Returning-customer share = 1/2 = 50%.
- Identified-order share = 3/4 = 75%; identified-sales share = 150/200 = 75%.
- A is classified as new observed for August even though A02 is a repeat purchase.
- U01 contributes no synthetic customer to the customer count.

If A01 contains six eligible item lines, it is still one invoice and one purchase occasion. If a separate qualifying merchandise credit for GBP 10 appears, positive gross sales remain GBP 200 under the primary definition; the observed credit magnitude is reported separately. No verified net revenue or purchase-to-credit linkage is implied.

## 2. Within-invoice customer inheritance and header conflicts

An invoice with customer IDs `[12345, missing, 12345]` receives customer ID `12345`, with an inheritance flag. An invoice with `[missing, missing]` stays unidentified. An invoice with `[12345, 54321]` is quarantined until resolved; it is not split into two purchases or assigned to the first customer found.

A country disagreement can produce an unknown invoice country while preserving otherwise eligible sales. A conflict in invoice timestamps prevents a valid invoice header until reviewed.

## 3. Cross-sheet and within-sheet duplicates

Suppose invoice X has exactly the same two identical item rows in both worksheets:

1. Compare the full invoice payload, including multiplicity: both versions contain the same row twice.
2. Keep the `Year 2010-2011` version; the older version's two rows are overlap copies.
3. Under the primary within-sheet rule, keep one of the retained identical rows.
4. Under the required within-sheet sensitivity, keep both retained rows; never restore the older worksheet copy.

If the two versions disagree on quantity, price, customer, or another normalized source field, X is an overlap conflict pending review. A unique invoice appearing only in the older worksheet remains eligible for processing even during the overlapping December dates.

## 4. Exact fixed-window boundaries

Use `T = 2011-12-01 00:00:00`, with an exclusive cutoff.

| First order (`t1`) | Second order (`t2`) | Window | Expected result |
|---|---|---:|---|
| 2011-10-31 00:00:00 | 2011-11-30 00:00:00 | 30 days | Eligible and repeated: `t2 = t1 + 30 days < T` |
| 2011-10-31 00:00:00 | 2011-11-30 00:00:01 | 30 days | Eligible but not repeated within 30 days |
| 2011-11-01 00:00:00 | 2011-11-02 00:00:00 | 30 days | Ineligible: the full window ends exactly at `T`, despite an observed repeat |
| 2011-11-20 00:00:00 | 2011-11-21 00:00:00 | 30 days | Ineligible: incomplete follow-up; exclude from both numerator and denominator |
| 2011-10-01 09:00:00 | A different invoice at 2011-10-01 09:00:00 | 30 days | Eligible and repeated at zero elapsed days; also flag for same-timestamp sensitivity |

All these first orders are in the primary cohort range. An order at exactly `T` is outside every primary analysis even if present in the workbook.

## 5. A repeat-rate denominator with censored customers

Consider three customers whose first observed purchases are in the primary cohort range:

| Customer | First order | Second order |
|---|---|---|
| A | 2011-08-31 10:00:00 | 2011-11-29 10:00:00 |
| B | 2011-09-02 00:00:00 | 2011-09-03 00:00:00 |
| C | 2011-09-01 00:00:00 | None before `T` |

For 90 days, A and C are eligible. A repeats exactly at the 90-day boundary. B's 90-day window ends exactly at `T`, so B is excluded despite an early second purchase. The 90-day rate is **1/2 = 50%**, not 2/3.

The conditional median days to second purchase among 90-day repeaters is 90 days, based on A alone. It must be displayed with the repeater count of 1 and eligible count of 2; it does not describe C's unobserved waiting time. This miniature example is for formula verification and is below the project's headline segment-size threshold.

## 6. Cohort months and unobserved cells

Two customers first buy in January 2011. A buys again in February and April; B buys again in April.

| Target month | Month index | Retained customers | Rate |
|---|---:|---:|---:|
| January | 0 | 2 | 100% |
| February | 1 | 1 | 50% |
| March | 2 | 0 | 0% |
| April | 3 | 2 | 100% |

The increase in April is valid: the metric measures purchasing in that month, not uninterrupted survival. Ten April orders from A would still contribute only one retained customer.

For the November 2011 cohort, Month 0 is observed. Month 1 corresponds to December 2011 and is null because December is not complete at the primary cutoff. It is not zero and does not enter pooled Month-1 denominators.

If two mature cohorts have sizes 2 and 8 with Month-1 retained counts of 1 and 2, their pooled retention is `(1+2)/(2+8) = 30%`. The unweighted average of 50% and 25%, or 37.5%, is not the pooled customer rate.

## 7. RFM recency, tied scores, and segment precedence

- A last purchase dated 2011-11-30 gives recency 1 at the 2011-12-01 snapshot.
- A customer with no purchase in `[2010-12-01, 2011-12-01)` has F = 0, M = 0, null scores, and segment `Dormant beyond 12 months`, even if there were older purchases.
- For five scorable customers with frequency values `[1, 1, 2, 5, 5]`, the defined ascending scores are `[2, 2, 3, 5, 5]`. Equal frequencies keep equal scores; score groups need not have equal counts.
- If all five values are identical, their scores are all 3. Recency reverses the ascending score; frequency and money do not.
- A customer with F = 2 and recency 91 is `At Risk Repeat`, even if monetary spending is high.
- A customer with F = 2, recency 90, and scores all 3 is `Loyal`; the inactivity rule uses strictly greater than 90.
- An F = 1 customer first observed within the final 30 elapsed days is `Promising New`. An older customer with a single recent trailing-year invoice is `Recent Occasional`.

These labels are rules for analysis and discussion, not verified psychological states or confirmed churn.

## 8. Bands, small groups, and concentration

A first basket of exactly GBP 50 belongs to `GBP 50–<100`; exactly GBP 100 belongs to `GBP 100–<250`; exactly GBP 250 belongs to `GBP 250+`. Two distinct products belong to `2–5 products`; six belong to `6+ products`. Later basket values must not change these first-order labels.

A segment with 99 eligible customers has counts but no headline rate or interval. A segment with 100 eligible customers and 20 repeaters has an unadjusted rate of 20% and an approximate 95% Wilson interval of **13.3%–28.9%**. This interval is not evidence of causality and is not the interval for a cohort-standardized rate.

With 11 identified historical customers, the top-10% concentration calculation selects `ceil(1.1) = 2` customers. Ties in historical sales are broken by ordinal customer-ID text order. The denominator is identified historical customer sales, not all sales including unidentified invoices.

## 9. Step 3 validation status

The examples' date boundaries, denominators, weighted retention, tied-score arithmetic, band edges, and Wilson interval were checked with an independent standard-library calculation during Step 3. Source workbook and Step 2 profile checksums were unchanged. These checks validate the specification examples; production SQL/Python reconciliation remains part of the corresponding implementation steps.

## Version 1.1 - Price serialization examples

These are deterministic normalization examples, not business findings:

- `2.5499999999999998` becomes exact Decimal `2.550000`, with `price_normalized=true`; its 2e-16 GBP deviation is within 1e-9.
- `0.55000000000000004` becomes `0.550000` with the correction flag.
- `19.99` becomes `19.990000` without a correction flag; formatting alone is not a value change.
- `0.1234567` is rejected: its 3e-7 deviation exceeds the tolerance.
- `-1.00` is exactly parseable but cannot be a positive purchase price.
- Raw price text remains unchanged in staging. Line amounts multiply accepted exact decimals before aggregation.
