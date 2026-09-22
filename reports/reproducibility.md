# Comprehensive repository review and reproducibility

**Result: passed after fixes.** Review completed 2026-09-22. The GitHub upload folder contains the completed 14-step portfolio, with published aggregate tables, without raw workbooks, detailed local datasets, databases, environments, scratch work, or obsolete scaffolding.

## Issues found and fixed

| Issue | Resolution | Verification |
|---|---|---|
| Missing notebooks could be silently skipped by the full runner | Require every configured notebook before execution | Missing-notebook fixture now fails explicitly |
| Dependency/preflight failures could leave an earlier success record visible | Write a fresh running record first; record the failing stage and failed status | Incomplete-checkout fixture verifies failure record |
| Python optimization could disable analytical assertions | Reject optimized execution in the full runner and regression entry point | Explicit preflight guard; README documents normal execution |
| Empty-month AOV and identification coverage could crash report/chart rendering | Render undefined money as N/A and plot gaps for undefined coverage; exclude undefined coverage from minimum calculation | Actual empty-month SQL fixture is rendered into a report and chart |
| Intake parser accepted nonfinite numbers and could crash on impossible dates | Reject nonfinite values and catch date overflow | NaN, infinity, and extreme date tests |
| Several reports, notebooks, and metric metadata still said later steps were pending | Update completed-stage text and clearly label historical audit/selection checkpoints | Full text review and execution of corrected report generators |
| Two setup links pointed to an obsolete README section | Update the links and check local paths and Markdown anchors | Final upload-directory link check |
| Dashboard counts and adjusted-comparison explanations were hardcoded | Derive customer counts, reactivation count, and comparison explanations from the generated summary | JavaScript fixture and real-browser selector checks |
| File decoding depended on Windows default encoding in some runners/notebooks | Read project text explicitly as UTF-8 | Fresh environment pipeline and notebook execution |
| Working folder contained large local data and redundant placeholders | Create a clean upload snapshot; preserve local data in the original working folder | Full upload-file inventory and Git ignore checks |

No change was made to the established analytical populations, monetary definitions, or metric contract 1.1. The resulting business metrics remained identical.

## Review coverage

The review covered every source script, all seven SQL files, the metric specification and dictionary, the 5,131-code mapping, the combined notebook source and outputs, all report documents and aggregate CSV/JSON files, all six charts, the HTML dashboard, source provenance, dependencies, README, and Git exclusions.

The raw workbook was independently downloaded again and its SHA-256 verified. Generated databases and Parquet files were treated as reproducible local artifacts rather than material to upload. No unrelated files were retained in the upload snapshot.

## Executed checks

1. Created a **new Python 3.12.14 virtual environment** and installed `requirements.txt` from locally cached package distributions. Dependency compatibility passed for 103 installed packages. This tested a clean installation, not an internet package download; transitive versions remain unlocked.
2. Started with **no raw workbook and no generated output tables**. Downloaded the original UCI archive over the network, extracted only the intended workbook, and verified the pinned checksum.
3. Ran **all nine pipeline script stages** in dependency order and **the combined notebook**, clearing old notebook outputs first. All completed successfully.
4. Compared **18 database tables and 2 views** against the previously validated results using schema checks and `EXCEPT ALL` in both directions. Every row and duplicate multiplicity matched.
5. Compared **11 aggregate CSV files and six PNG figures** byte for byte with the validated baseline. All matched.
6. Ran **six portable regression suites** covering parsing, overlap multiplicity, cleaning/header/identity rules, exclusive cutoffs, repeat-window maturity, same-timestamp sensitivity, cohort gaps/future cells, RFM ties and segment precedence, Wilson intervals, cohort standardization/suppression, runner failures, and empty-month rendering.
7. Executed dashboard JavaScript checks, then opened the dashboard in a real browser. Confirmed visible KPI values, switched to the November 2011 cohort with future cells unobserved, switched geography and product-diversity comparisons, and inspected the page layout. All six analytical PNGs were also visually inspected.
8. Parsed every Python file, JSON file, CSV file, and notebook; checked local documentation paths/anchors and HTML links; scanned the upload tree for local machine paths, credential patterns, caches, databases, archives, and unrelated file types. Git inclusion/exclusion behavior was tested using a temporary Git directory outside the deliverable.

## Headline reconciliations

| Measure | Result |
|---|---:|
| Raw source lines | 1,067,371 |
| Eligible merchandise lines | 972,818 |
| Eligible invoices | 38,615 |
| Identified historical customers | 5,821 |
| Complete monthly KPI rows | 24 |
| Cohort grid cells / unobserved future cells | 576 / 276 |
| Mature primary 90-day customers / repeat purchasers | 3,529 / 1,452 |
| 90-day repeat rate | 41.14% |
| Top-decile customers / identified historical sales share | 583 / 63.56% |
| Dormant RFM accounts | 1,530 |

## Upload contents and file decisions

Upload the contents of `ecommerce-customer-retention-final/` into the repository root, preserving `.gitignore` and the directory structure. The original working folder retains local data and is not the clean upload snapshot.

- **Kept:** source code and regression fixtures, SQL, metric definitions, source manifest/instructions, reviewed product mapping, aggregate CSV/JSON evidence, executed notebooks, six charts, HTML dashboard, README, and case study.
- **Excluded:** the 45.6 MB raw workbook, generated DuckDB/Parquet files and detailed processed CSVs, environments, cache/checkpoint files, old ZIP snapshots, and scratch validation utilities.
- **Removed from the upload snapshot:** redundant `.gitkeep` files in populated directories. The final folder instead publishes 11 aggregate CSVs and a data README in `data/processed/`.
- **Documentation cleanup:** removed obsolete Step 4 migration instructions from the public README and corrected stale project status statements.

The preserved synthetic tests are relevant quality evidence. Their names and scenarios are explicit; they are not abandoned development files. Aggregate CSVs, JSON validation summaries, and Markdown reports serve distinct purposes and are retained deliberately.

## Reproduce and inspect

Follow [the README](../README.md). After installing dependencies:

```powershell
python src/check_project.py
python src/run_pipeline.py
```

The first command requires no raw dataset. The second downloads/verifies data, rebuilds results and executes notebooks. Review [the pipeline record](pipeline_run.json) and [the detailed comparisons and file inventory](reproducibility_results.json). Earlier stage summaries retain their individual analytical validation evidence.

## Scope and remaining limitations

No known failing check or unresolved code defect was found within the reviewed fixed-data workflow after these fixes. This is not a mathematical guarantee that all conceivable bugs are absent. Execution was tested on Windows with Python 3.12.14; other operating systems were not run. The dataset remains historical UK retail, customer IDs are accounts, money is gross purchases before credits, and causal campaign outcomes are unobserved.

Narrative business interpretations require editorial review after changing inputs or definitions. Source availability and future dependency resolution can change. The dashboard is HTML, with no Power BI `.pbix` file. No GitHub publication or production campaign deployment was performed.

## Final presentation update

The three original notebooks have been combined into `notebooks/ecommerce_retention_analysis.ipynb`, with a table of contents and all original analytical code. Aggregate CSVs have moved from `reports/` to `data/processed/`; scripts, documentation and dashboard links use the new paths. Historical checks above describe the prior audit; current packaging and re-execution evidence is recorded in `final_delivery_validation.json` and `pipeline_run.json`.
