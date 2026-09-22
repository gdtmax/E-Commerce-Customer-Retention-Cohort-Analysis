# Step 6 - Cleaning and Analytical Base Tables

**Completed:** 2026-09-22. **Contract:** 1.1. Base tables are built and validated. Downstream findings are available in the [final case study](case_study.md).

## Reproduction

After the [README setup](../README.md#reproduce-the-project), run from the project root:

```powershell
.\.venv\Scripts\python.exe src/audit_data.py
.\.venv\Scripts\python.exe src/clean_data.py
```

Cleaning reads [the versioned product mapping](../src/product_roles.csv), recomputes normalization and invoice payload comparisons, and executes [01b_clean_data.sql](../sql/01b_clean_data.sql). Base tables are replaced in one transaction after validation; failed validation rolls back replacement. Exports and JSON are regenerated after commit. If interrupted during export, rerun cleaning to synchronize outputs. Downstream analyses must be refreshed separately, or use the complete pipeline runner.

The local DuckDB database now contains raw rows, the product lookup, five analytical base tables and two duplicate-sensitivity views. Matching Parquet files are generated for the five base tables. Generated data remain ignored by Git. The [notebook](../notebooks/ecommerce_retention_analysis.ipynb) reviews both stages.

## Implemented decisions

- **Preservation:** original workbook unchanged; all 1,067,371 source rows and eight raw fields survive in staging with sheet, Excel row and workbook hash.
- **Price precision:** contract 1.1 accepts Decimal half-up normalization to six decimals only for deviation <=1e-9 GBP. Raw text and correction flag are retained. This normalizes 112,879 source prices, including 103,693 eligible lines. Other precision failures would be rejected. Payload comparisons use the accepted normalized price.
- **Overlap:** compare complete eight-field invoice multisets, including multiplicity. Keep the later worksheet for identical versions only. Exclude 22,523 older-copy rows; conflicting versions would be quarantined.
- **Duplicates:** keep earliest identical line in retained invoice version. Exclude another 11,812 rows under this precedence; retain a reproducible variant with these repeats for sensitivity analysis.
- **Headers:** quarantine all 84 invoice worksheet versions with multiple timestamps. They contain 5,796 raw rows, of which 5,721 remain after earlier exclusions. No arbitrary timestamp is selected.
- **Transactions:** require numeric invoice IDs, positive quantity and price, and classified merchandise. Credits, fees and unsupported records stay in staging with reasons.
- **Dates:** eligible tables use [2009-12-01,2011-12-01). Initial history remains available; primary cohort comparisons still start in March 2010.
- **Identity:** unknown-ID orders can contribute to overall sales but never become a synthetic customer. Valid within-invoice inheritance is implemented and tested; this source has no IDs recoverable by that rule.
- **Outliers:** no automatic winsorization or deletion. No assumed purchase-to-credit matching. Primary money represents gross purchase events, not verified net revenue.

## Product mapping and limitations

The lookup contains all **5,131 codes**: **4,720 merchandise**, **25 non-merchandise**, **386 unresolved**. Each entry records representative source description, positive-evidence count before the cutoff, and decision reason. Baseline evidence is a descriptive catalogue item on a positive numeric invoice before the cutoff; descriptions and exceptions were screened for fees, vouchers, adjustments, tests and ambiguity. This is an analytical classification, not an independently verified merchant catalogue or native product category.

Pure numeric codes also need review: **22016** is a voucher, **23444** is next-day carriage, and **23574** is a packing charge. They are excluded as non-merchandise. **23702** (High Resolution Image) stays unresolved. Unusual PADS and party-bag codes can qualify based on descriptions. Shape alone is never proof. Missing descriptions without supported pre-cutoff purchase evidence remain unresolved; a missing line description may qualify when the code has supported merchandise evidence elsewhere.

After other eligibility rules, unresolved exposure is:

| Code | Lines | Candidate positive GBP | Decision |
|---|---:|---:|---|
| M | 840 | 338,561.72 | Manual entries cannot be established as merchandise; exclude pending external evidence. |
| S | 3 | 136.85 | Samples have ambiguous purchase meaning; exclude. |
| 23702 | 3 | 27.00 | Ambiguous image item; exclude. |

Total **846 lines / GBP 338,725.57**, about 1.79% of primary sales. This is material enough to disclose with future spending conclusions. Adding it mechanically is not a justified merchandise total. The base tables are ready under the explicitly restricted scope; the meaning of every manual entry remains unknown.

## Additive row reconciliation

All applicable reasons are preserved in `exclusion_reasons`. `primary_disposition` selects the first applicable reason in SQL precedence and makes this table additive. Overlapping flags must not be summed.

| Primary disposition | Rows | Candidate positive GBP |
|---|---:|---:|
| credit_invoice | 18,742 | 0.000000 |
| exact_duplicate | 11,812 | 57481.470000 |
| header_conflict | 5,721 | 98126.330000 |
| included | 972,818 | 18933017.227000 |
| invalid_invoice_format | 6 | 0.000000 |
| non_merchandise | 3,696 | 457520.931000 |
| nonpositive_price | 2,597 | 0.000000 |
| nonpositive_quantity | 3,363 | 0.000000 |
| outside_reporting_window_or_invalid_date | 25,247 | 637808.330000 |
| overlap_copy | 22,523 | 438852.650000 |
| unresolved_product | 846 | 338725.570000 |
| **Total** | **1,067,371** | Includes copies and excluded records |

There are **94,553 excluded rows** and **972,818 eligible lines**. Candidate amounts measure positive-quantity/price numeric-invoice exposure, not net revenue or lost business. The window-exclusion count is 25,247 because duplicates are handled first; the raw final partial month has 25,526 rows. Exact amounts and overlapping flags appear in [the JSON summary](cleaning_summary.json). Detailed CSVs are under `data/processed/`.

## Tables and grains

| Table | Rows |
|---|---:|
| `stg_order_lines` | 1,067,371 |
| `fact_order_lines` | 972,818 |
| `fact_orders` | 38,615 |
| `customer_features` | 5,821 |
| `customer_month_activity` | 24,850 |

- `stg_order_lines`: every source row, raw/normalized fields, identity/header flags, role, all reasons, primary disposition and eligibility.
- `fact_order_lines`: one eligible original line; worksheet/Excel-row key, invoice link, exact decimal money.
- `fact_orders`: one eligible invoice with timestamp, customer/country, basket measures and deterministic customer sequence.
- `customer_features`: one identified customer with first/second/last purchase, first-basket attributes, historical count/value, cohort and recency. These are preparation features, not completed retention findings.
- `customer_month_activity`: one identified customer per purchasing month.

DuckDB enforces the documented primary keys. Five matching `.parquet` files are generated locally. `product_roles` is a lookup table. `sensitivity_order_lines_keep_duplicates` and `sensitivity_orders_keep_duplicates` are views over staging, not extra orders to combine with primary results.

## Coverage and sensitivity

Primary eligible purchases: **38,615 invoices / GBP 18,933,017.227** gross merchandise sales.

- Identified: **35,751 invoices**, **5,821 customers**, **GBP 16,518,355.987**.
- Unidentified: **2,864 invoices / GBP 2,414,661.240**, retained overall but absent from customer histories.
- Keeping eligible within-sheet repeats leaves invoices at 38,615 and increases sales to **GBP 18,988,953.197**, up **GBP 55,935.970**, about 0.30%. AOV changes from approximately GBP 490.30 to GBP 491.75. The [customer report](customer_value_and_segments.md) quantifies monetary-segmentation sensitivity using these views.
- Collapsing customer/timestamp occasions reduces identified invoices from **35,751 to 35,577** occasions. The primary definition retains distinct invoices. The [retention report](retention_analysis.md) quantifies the rate effect.
- Excluding **541431 as a sensitivity only** removes GBP 77,183.60: 38,614 orders and GBP 18,855,833.627. Primary tables keep it. An apparent credit counterpart is not verified refund linkage.

These are preparation checks, not retention findings or marketing recommendations. Source date gaps, wholesale mix, first-observed acquisition, and missing status/category/discount fields remain limitations.

## Validation and handoff

**14 runner checks passed:** source-row and raw-value preservation, mapping coverage, positive-merchandise scope, reporting dates, no orphan lines, exact line/order money, exact customer/identified-order money, customer order counts, contiguous sequences, first-order provenance, monthly activity agreement, missing-ID handling and duplicate-sensitivity inclusion.

Small synthetic cases exercised the actual SQL for payload multiplicity conflicts, accepted price matching, duplicate sensitivity, ID inheritance, timestamp/customer/country conflicts, invalid precision, credits, exclusive cutoff and tied invoice sequencing. The notebook was executed and exported-table counts, English content, documentation links and workbook hash were checked before delivery.

**Step 6 is complete under contract 1.1.** Rebuild cleaning after raw, mapping, specification or SQL changes, then refresh downstream outputs. All subsequent steps are complete; see the [current README](../README.md).
