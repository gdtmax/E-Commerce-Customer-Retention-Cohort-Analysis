# Raw Data — Online Retail II

This folder holds the unchanged source workbook for the project. No cleaning has been applied.

## Source and attribution

Chen, D. (2012). *Online Retail II* [Dataset]. UCI Machine Learning Repository. [https://doi.org/10.24432/C5CG6D](https://doi.org/10.24432/C5CG6D).

- [Dataset page](https://archive.ics.uci.edu/dataset/502/online+retail+ii)
- [Official ZIP download](https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip)
- [CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/)
- Accessed: 2026-09-21

Keep attribution and the license link with distributed data and derived material, and indicate future transformations. No endorsement by the creator or UCI is implied.

## Expected file

```text
data/raw/online_retail_II.xlsx
```

- Size: 45,622,278 bytes.
- Worksheets: `Year 2009-2010` and `Year 2010-2011`.
- SHA-256: `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`.

The GitHub upload folder omits this workbook; restore it using the command below. Git excludes the workbook through the root `.gitignore`. The source instructions and [`source_manifest.json`](source_manifest.json) remain versioned. Raw source data keeps its own license regardless of any future project-code license.

## Restore the workbook after cloning

With Python 3.10 or later, run from the project root:

```bash
python src/download_dataset.py
```

This uses the standard library, requires internet access only if the workbook is absent, and verifies the pinned SHA-256. A different existing file is not overwritten.

Alternatively, download the ZIP from UCI, extract `online_retail_II.xlsx`, and place that file directly in this folder. Do not put it inside an extra nested directory. Verify it in PowerShell:

```powershell
Get-FileHash -LiteralPath 'data/raw/online_retail_II.xlsx' -Algorithm SHA256
```

If the source changes and the checksum differs, review the new version and regenerate the assessment before updating the pinned checksum.

## Reproduce the feasibility profile

```bash
python src/profile_dataset.py
```

This recreates `reports/dataset_profile.json`. It does not modify the workbook or produce cleaned analysis tables. Both sheets must be inspected together because their date ranges overlap. See [`reports/dataset_selection.md`](../../reports/dataset_selection.md) for the selection decision and limitations.
