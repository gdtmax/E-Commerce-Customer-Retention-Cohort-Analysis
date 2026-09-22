# Step 5 - Raw Data Quality Audit

**Historical audit checkpoint:** this report preserves Step 5 findings and proposed decisions. They were implemented in [Step 6](cleaning_report.md); all project steps are now complete.

**Audit date:** 2026-09-22. **Result:** Step 5 complete; proceed to Step 6 with the decisions below. Finding data problems is an audit result, not evidence that cleaning is complete.

## Scope, provenance, and reproduction

The full UCI Online Retail II workbook was audited: **1,067,371 item rows**, comprising 525,461 rows in `Year 2009-2010` and 541,910 in `Year 2010-2011`. Source data run from 2009-12-01 07:45 to 2011-12-09 12:50. The workbook SHA-256 was verified before and after execution:

`bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`

Run `python src/audit_data.py` from the project root after installing the pinned dependencies. The runner executes [01_data_quality.sql](../sql/01_data_quality.sql), saves [machine-readable results](data_quality_summary.json), and creates five evidence CSVs in `data/processed/`. Open [the executed audit notebook](../notebooks/ecommerce_retention_analysis.ipynb) to review them. See [README setup instructions](../README.md#reproduce-the-project).

The only persistent database table created by the audit stage is `raw_order_lines`: original eight source fields stored as text, plus worksheet, physical Excel row number, and workbook checksum. Blank source cells become SQL NULL. Sheet and row form a unique primary key. Parsed values, invoice versions, and proposed dispositions are temporary audit tables; no original rows were deleted, prices overwritten, customer IDs imputed, or analytical tables built. SQL uses Python-registered exact parsers and must be run through the documented runner.

Unless stated otherwise, counts below cover both worksheets and all source dates, before any deduplication. Issue counts overlap and must not be added together. The source contains 53,628 distinct raw invoice IDs, 5,942 known customer IDs, and 5,131 normalized stock codes; these are not eligible order or customer counts.

## 1. Missing identity, descriptions, and field validity

| Check | Observed result | Step 6 treatment |
|---|---:|---|
| Missing Customer ID | 243,007 rows (22.77%) | Exclude unidentified invoices from customer retention; retain otherwise eligible sales in overall coverage. Never combine unknown IDs into one customer. |
| Missing Description | 4,382 rows | Review code-level descriptions; do not infer merchandise eligibility from a missing or vague description. |
| Other six native fields missing | 0 rows each | Continue to validate parsed values and business meaning. |
| Invalid dates / nonintegral quantities / malformed nonblank customer IDs | 0 / 0 / 0 | Preserve the validation checks in cleaning. |
| Literal `Unspecified` country | 756 rows | Represent as unknown geography. |

There are 8,939 invoice worksheet versions with no known customer ID. No invoice version contains both a valid ID and a missing ID, so the planned within-invoice inheritance rule would recover **zero** IDs in this source. No invoice version has multiple known customer IDs or countries. Across invoices, 13 customers have multiple known countries; that does not by itself invalidate their identity. Freeze first-order geography as specified.

## 2. Duplicates and overlapping worksheets

An invoice's cross-sheet payload is compared as a **multiset of all eight normalized source fields**, including duplicate multiplicity. It is not matched on invoice ID alone. Missing fields and invalid strict prices retain explicit representations in the comparison. Source lineage is excluded from the payload.

| Sequential proposed disposition | Rows | Candidate positive amount, all dates (GBP) |
|---|---:|---:|
| Prefer the later worksheet for identical overlapping invoices | 22,523 older-sheet rows | 438,852.65 |
| Then retain only the earliest identical row within each retained invoice version | 11,812 additional rows | 57,481.47 |
| Remaining rows for Step 6 review | 1,033,036 | 20,465,198.39 |
| **Reconciliation** | **1,067,371** | Amounts use the provisional scenario defined below |

Exactly **1,088 invoice IDs** appear in both worksheets; all payloads match, representing 45,046 rows across both copies. **No conflicting overlap payloads** were found. The complete evidence is `data/processed/audit_invoice_overlap.csv` (2,176 worksheet-version rows).

Global exact repeated rows after the first occurrence total **34,335**. This equals 22,523 + 11,812 under the documented sequence; do not subtract 34,335 again. Same-sheet identical lines may represent genuine repeated scans, so retain the Step 3 sensitivity analysis that keeps those 11,812 lines. All source rows remain in the locally generated database.

## 3. Monetary precision, cancellations, and sign anomalies

**Precision is a required Step 6 decision.** There are **112,879 rows (10.58%)** whose raw prices fail the strict maximum-six-decimal rule. All are within **0.000000000003 GBP (3e-12)** of a six-decimal value. Examples include `2.5499999999999998` and `0.55000000000000004`. This is consistent with Excel binary-number serialization. No unparseable prices, out-of-range prices, or deviations greater than the audit tolerance were found. The remaining 954,492 prices already satisfy the strict rule.

Discarding every strict precision failure would unnecessarily lose substantial data. Version 1.0 of the metric contract is unchanged. **Proposed Step 6 rule:** preserve raw text, accept a six-decimal half-up normalization only when absolute deviation is at most `1e-9 GBP`, and record a correction flag; quarantine other precision failures. Version and document the accepted rule before implementing cleaned money calculations.

All `candidate_positive_gbp` audit amounts use that **explicit provisional price scenario**, numeric invoice IDs, positive integral quantity, and positive normalized price. They include unresolved stock codes, unknown customers, and header issues. They are neither final merchandise sales nor verified net revenue. Decimal arithmetic is used for multiplication and sums; report displays round to two decimals. Sign checks independently inspect all numeric raw prices, including the tiny-tail cases.

| Check | Rows | Implication |
|---|---:|---|
| Invoice starts with C | 19,494 | Credit/cancellation indicator; exclude from primary positive purchase events. |
| Other nonnumeric invoice format | 6 | Bad-debt adjustment records; not qualifying purchase invoices. |
| Negative quantity | 22,950 | Review credits, stock adjustments, and reversal examples. |
| Zero quantity | 0 | No zero-quantity records found. |
| Negative / zero unit price | 5 / 6,202 | Exclude from positive-purchase lines, retain reasons. |
| C-prefixed invoice with positive quantity | 1 | Prefix rule still excludes it from purchases. |
| Negative quantity without C prefix | 3,457 | Sign and invoice-prefix rules must both be applied. |

No native order-status field exists. Prefix and sign checks are proxies, not verified completed/refunded statuses. Credit matching is not assumed, and historical purchases are not automatically erased after a later credit.

## 4. Invoice headers and exclusion exposure

Across 54,716 worksheet invoice versions, **84 have multiple timestamps**. Detailed versions and counts are in `data/processed/audit_header_issues.csv`. Step 6 must quarantine them under the current contract unless a documented resolution establishes a valid single header; silently taking MIN or MAX would change the rule.

After proposed overlap and within-version duplicate handling, and restricting to `[2009-12-01, 2011-12-01)`, there are **1,007,789 rows for further review**. Their provisional positive amount is **GBP 19,827,390.06**. Within this review population:

- Header-conflict invoices account for **5,721 rows** and **GBP 98,126.33** of candidate positive amount.
- Unidentified invoices account for **227,287 rows** and **GBP 2,969,794.23** of candidate positive amount.
- These groups overlap; their amounts are not additive exclusions. A final row-by-row exclusion waterfall and eligible customer coverage belong to Step 6.

There are **181 customer/timestamp groups containing 363 distinct candidate invoices** in the raw audit scenario. Distinct invoices at the same timestamp are not automatically duplicates. Preserve the documented invoice ordering and later repeat-purchase sensitivity checks.

## 5. Product-code roles and description consistency

The complete inventory `data/processed/audit_product_codes.csv` contains all **5,131** codes, observed descriptions, counts, and provisional amounts. **1,192** codes have multiple descriptions; **353** never have a description. There are **61** codes outside the common five-digit-plus-suffix pattern. Shape alone does not establish merchandise eligibility.

The following is an evidence-based review guide, not a completed production mapping:

| Code examples | Observed evidence | Proposed mapping treatment |
|---|---|---|
| DOT, POST, C2 | DOTCOM POSTAGE, POSTAGE, CARRIAGE | Non-merchandise shipping charges. |
| AMAZONFEE, BANK CHARGES, CRUK | Fee, bank charge, commission descriptions | Non-merchandise fees. |
| ADJUST, ADJUST2, B, D | Adjustment, bad debt, discount descriptions | Non-merchandise accounting adjustments. |
| GIFT_0001_* | Voucher descriptions for several denominations; others lack descriptions | Keep outside merchandise scope pending explicit voucher treatment. |
| TEST001, TEST002 | This is a test product | Exclude test records. |
| M, S | Manual; SAMPLES | Unresolved manual/sample roles; do not classify as merchandise automatically. |
| PADS, DCGSSGIRL, DCGSSBOY, DCGS0076, SP1002 | Cushion pads, party bags, night light, chalkboard | Merchandise candidates despite unusual codes; review the actual descriptions. |
| Blank-description codes, C3, vague DCGS entries | Missing descriptions or only `ebay` | Unresolved; document exclusion and exposure until supported. |

Step 6 must produce an explicit reviewed mapping and record evidence/reasons, including standard-shaped codes with ambiguous descriptions. It must reconcile category exposures after the final mapping. The dataset has no native product category, promotion, delivery, or payment fields; no such fields were invented.

## 6. Date coverage and extreme values

All **25 calendar months** from December 2009 to December 2011 contain records. There are **108 runs of dates with no records** between the observed endpoints. The two longest runs are 11 days each: 2009-12-24 through 2010-01-03, and 2010-12-24 through 2011-01-03. Only one Saturday has records. A trading-calendar explanation is plausible, but cannot prove source completeness. Do not fill absent days with invented orders or assert that every missing day is confirmed business closure. Evidence: `data/processed/audit_date_gaps.csv` and monthly/weekday coverage in the JSON.

The final December 2011 contains only eight observed dates, ending December 9, and **25,526 source rows**. Keep these rows in raw storage but exclude them from headline analysis under the existing exclusive cutoff of **2011-12-01**. Full history from December 2009 remains available; primary first-observed cohort comparisons still start in March 2010.

Quantities range from -80,995 to 80,995; the 99th percentile among positive quantities is 108. Review-scenario unit prices range from GBP -53,594.36 to 38,970.00. The 30 largest absolute line amounts with source rows are in `data/processed/audit_outlier_lines.csv`.

- Invoice **541431**, customer **12346**, on 2011-01-18 contains 74,215 units at GBP 1.04: **GBP 77,183.60**. Credit **C541433** has the opposite quantity shortly afterward. This is a strong reversal candidate, not a verified linked refund. Document its effect in the later value/RFM sensitivity analysis rather than silently deleting it.
- Invoice **581483** has a GBP 168,469.60 positive line and a subsequent matching negative line on **C581484**, both on 2011-12-09. They remain raw evidence but lie outside the headline analysis window.

No automatic winsorization or outlier deletion has been applied. Large wholesale orders are possible in this retailer; magnitude alone is not proof of error.

## 7. Verification of Steps 1-5

| Step | Original requirement | Evidence and verification | Status |
|---|---|---|---|
| 1 | Business scope, audience, questions, outputs | README defines the business scenario, four audiences, eight questions, boundaries, and the 14-step roadmap. Unsupported marketplace questions were explicitly revised after selection. | Complete |
| 2 | Dataset selection, provenance, feasibility, source access | Dataset selection report, source README/manifest, unchanged full workbook, and original feasibility JSON. Workbook checksum and 1,067,371-row totals reconcile. | Complete |
| 3 | Data dictionary and metric definitions | Version 1.0 dictionary, shared metric specification, and synthetic worked examples; observation windows, overlap rules, eligible sales, RFM ties and scope are explicit. Boundary examples were rechecked. New price evidence is documented for a controlled Step 6 revision. | Complete as specification; cleaning implementation pending |
| 4 | Basic repository setup | Original directory architecture, four root files, seven pinned dependencies, working Python 3.12 environment, valid Git ignore rules, and setup instructions. No removed heavyweight scaffolding was restored. | Complete |
| 5 | Audit original data and report issues | Full-source SQL run, raw lineage table, five detailed evidence CSVs, JSON summary, executed notebook, and this report. Missingness, duplicates, dates, prices, statuses/proxies, IDs, product codes, headers and coverage reviewed. | Complete |

Verification includes checksum preservation, sheet/row primary-key uniqueness, source-count reconciliation, duplicate disposition reconciliation, synthetic overlap/conflict/precision checks, notebook execution, readable JSON, local documentation links, English project content, dependency compatibility, and Git inclusion/exclusion behavior. The verification utilities used during development remain outside the project folder to keep the repository lean.

This confirms the deliverables through Step 5. It does **not** certify that the data are clean or every business fact is correct. GitHub has not been connected or updated because no remote URL has been supplied. The executable environment is local validation tooling; users recreate `.venv` from requirements after copying the folder.

## 8. Step 6 handoff

1. Approve through documented project change control and implement the supported price normalization; update the metric contract/specification consistently.
2. Build the product-role mapping from the full inventory, with unknown roles and evidence retained.
3. Apply the established overlap and duplicate sequence with source lineage and reason codes; preserve the within-sheet sensitivity variant.
4. Quarantine unresolved invoice headers, apply transaction/sign/identity rules, and retain missing-ID sales coverage separately.
5. Build the planned analytical tables and an additive exclusion waterfall; reconcile rows, invoices, customers and amounts.
6. Verify complete-period cutoffs and quantify the effect of duplicates, unresolved codes, header conflicts and extreme reversal candidates before publishing customer metrics.

These are the next step's tasks. No cleaned tables, cohort rates, RFM assignments, or business recommendations are claimed by this audit.
