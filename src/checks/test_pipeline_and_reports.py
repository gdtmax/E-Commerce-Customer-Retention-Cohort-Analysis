"""Regression checks for missing notebooks, failed runs, and empty-month display."""
from pathlib import Path
import json
import runpy
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
import run_pipeline
import monthly_kpis
from profile_dataset import number, timestamp

assert number('nan') is None and number('inf') is None
assert timestamp('nan') is None and timestamp('1e300') is None
assert monthly_kpis.display_money(None) == 'N/A'

with tempfile.TemporaryDirectory() as folder:
    temporary = Path(folder)
    with patch.object(run_pipeline, 'ROOT', temporary), patch.object(sys, 'argv', ['run_pipeline.py']):
        try:
            run_pipeline.main()
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('Incomplete checkout incorrectly passed.')
        log = json.loads((temporary / 'reports/pipeline_run.json').read_text())
        assert log['status'] == 'failed' and log['failed_step'] == 'preflight'
    # Obtain the real SQL empty-month fixture, then exercise report/chart rendering.
    fixture = runpy.run_path(str(ROOT / 'src/checks/test_monthly_kpis.py'))
    rows = fixture['r']
    (temporary / 'images').mkdir()
    summary = {'totals': {'orders': 6, 'gross_merchandise_sales_gbp': '210',
                         'average_order_value_gbp': '35', 'distinct_customers': 2,
                         'identified_order_share': 4/6, 'identified_sales_share': 130/210}}
    with patch.object(monthly_kpis, 'ROOT', temporary):
        monthly_kpis.draw_chart(rows)
        monthly_kpis.write_report(rows, summary)
    assert (temporary / 'images/monthly_kpis.png').is_file()
    assert 'N/A' in (temporary / 'reports/monthly_kpis_report.md').read_text(encoding='utf-8')

with tempfile.TemporaryDirectory() as folder:
    temporary = Path(folder)
    # All script inputs exist; the combined notebook is missing.
    files = [temporary / 'src' / n for n in run_pipeline.STEPS]
    files += [temporary / 'src/metric_spec.json', temporary / 'src/product_roles.csv',
              temporary / 'data/raw/source_manifest.json']
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    with patch.object(run_pipeline, 'ROOT', temporary):
        try:
            run_pipeline.preflight()
        except FileNotFoundError as exc:
            assert 'ecommerce_retention_analysis.ipynb' in str(exc)
        else:
            raise AssertionError('Missing notebook incorrectly passed.')
print('PASS: failed-run status, missing notebooks, nonfinite input, and empty-month report/chart rendering.')
