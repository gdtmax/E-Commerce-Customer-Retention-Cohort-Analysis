"""Rebuild all analytical outputs and execute the combined notebook, in order."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
STEPS = [
    "download_dataset.py", "profile_dataset.py", "audit_data.py",
    "clean_data.py", "monthly_kpis.py", "retention_analysis.py",
    "customer_analysis.py", "visualize_analysis.py", "build_dashboard.py",
]
NOTEBOOKS = ["ecommerce_retention_analysis.ipynb"]


def preflight(include_notebooks=True):
    """Do not report success for an incomplete checkout or disabled assertions."""
    if not __debug__ or os.environ.get("PYTHONOPTIMIZE", "0") not in ("", "0"):
        raise RuntimeError("Run without -O or PYTHONOPTIMIZE; validation assertions must remain enabled.")
    required = [ROOT / "src" / name for name in STEPS]
    required += [ROOT / "src/metric_spec.json", ROOT / "src/product_roles.csv",
                 ROOT / "data/raw/source_manifest.json"]
    if include_notebooks:
        required += [ROOT / "notebooks" / name for name in NOTEBOOKS]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        raise FileNotFoundError("Required project files missing: " + ", ".join(missing))
    for name in ["data/processed", "reports", "images", "dashboard"]:
        (ROOT / name).mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-notebooks", action="store_true",
                        help="Rebuild tables/charts/dashboard without executing notebooks.")
    args = parser.parse_args()
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    report = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.platform(),
        "packages": {},
        "notebooks_requested": not args.skip_notebooks, "steps": [], "status": "running",
        "scope": "Computed outputs are regenerated; narrative reports require editorial review when inputs change.",
    }
    (ROOT / "reports").mkdir(parents=True, exist_ok=True)
    record = ROOT / "reports/pipeline_run.json"
    record.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    current_step = "preflight"
    try:
        preflight(not args.skip_notebooks)
        report["packages"] = {p: importlib.metadata.version(p) for p in
                              ["duckdb", "numpy", "pandas", "openpyxl", "matplotlib", "jupyterlab", "ipykernel"]}
        for script in STEPS:
            current_step = script
            print(f"\n=== {script} ===", flush=True)
            start = time.monotonic()
            subprocess.run([sys.executable, str(ROOT / "src" / script)], cwd=ROOT, check=True)
            report["steps"].append({"name": script, "status": "passed",
                                    "seconds": round(time.monotonic() - start, 2)})
        if not args.skip_notebooks:
            import nbformat
            from nbclient import NotebookClient
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            subprocess.run([sys.executable, "-m", "ipykernel", "install", "--sys-prefix",
                            "--name", "retention-analysis", "--display-name",
                            "Python (retention-analysis)"], check=True)
            for name in NOTEBOOKS:
                path = ROOT / "notebooks" / name
                current_step = name
                print(f"\n=== {path.name} ===", flush=True)
                start = time.monotonic()
                notebook = nbformat.read(path, as_version=4)
                for cell in notebook.cells:
                    if cell.cell_type == "code":
                        cell.outputs = []
                        cell.execution_count = None
                NotebookClient(notebook, timeout=300, kernel_name="retention-analysis",
                               resources={"metadata": {"path": str(path.parent)}}).execute()
                nbformat.write(notebook, path)
                report["steps"].append({"name": path.name, "status": "passed",
                                        "seconds": round(time.monotonic() - start, 2)})
        report["status"] = "passed"
    except BaseException as exc:
        report["status"] = "failed"
        report["failed_step"] = current_step
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (ROOT / "reports/pipeline_run.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("\nPipeline completed. See reports/pipeline_run.json.", flush=True)


if __name__ == "__main__":
    main()
