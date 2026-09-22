"""Step 5: preserve source rows in DuckDB and execute the raw-data audit.

Run from the project root: python src/audit_data.py
Outputs: data/processed/retention.duckdb, audit evidence CSVs, and the report JSON.
No source rows are cleaned or deleted. Only raw_order_lines is replaced on rerun.
"""

import csv
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
import json
from pathlib import Path
import posixpath
import re
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import duckdb
from profile_dataset import EXPECTED, NS, REL, sha256, shared_strings, sheet_rows

ROOT = Path(__file__).resolve().parents[1]
RAW_COLUMNS = ["raw_invoice", "raw_stock_code", "raw_description", "raw_quantity",
               "raw_invoice_date", "raw_price", "raw_customer_id", "raw_country"]


def decimal_value(text):
    try:
        value = Decimal(text.strip())
        return value if value.is_finite() else None
    except (InvalidOperation, AttributeError):
        return None


@lru_cache(maxsize=None)
def quantity_text(text):
    value = decimal_value(text)
    if value is None or value != value.to_integral_value() or abs(value) >= 2**63:
        return None
    return str(int(value))


@lru_cache(maxsize=None)
def price_text(text):
    value = decimal_value(text)
    if value is None or abs(value) >= Decimal("1e18") or value != value.quantize(Decimal("0.000001")):
        return None
    return format(value, ".6f")


@lru_cache(maxsize=None)
def price_issue(text):
    value = decimal_value(text)
    if value is None or abs(value) >= Decimal("1e18"):
        return "invalid_or_out_of_range"
    delta = abs(value - value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
    if delta == 0:
        return "exact_within_six_decimals"
    return "representation_noise_candidate" if delta <= Decimal("0.000000001") else "excess_precision"


@lru_cache(maxsize=None)
def review_price_text(text):
    """Explicit audit scenario only; does not change the Step 3 money contract."""
    if price_issue(text) not in ("exact_within_six_decimals", "representation_noise_candidate"):
        return None
    return format(decimal_value(text).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP), ".6f")


@lru_cache(maxsize=None)
def price_delta_text(text):
    if review_price_text(text) is None:
        return None
    return format(abs(decimal_value(text) - Decimal(review_price_text(text))), "f")


@lru_cache(maxsize=None)
def customer_text(text):
    value = decimal_value(text)
    if value is None or value <= 0 or value != value.to_integral_value():
        return None
    return str(int(value))


@lru_cache(maxsize=None)
def date_text(text):
    value = decimal_value(text)
    try:
        if value is None:
            return None
        seconds = int((value * 86400).to_integral_value(rounding=ROUND_HALF_UP))
        return (datetime(1899, 12, 30) + timedelta(seconds=seconds)).isoformat(sep=" ")
    except (OverflowError, ValueError):
        return None


def prepare_audit(connection):
    """Register exact parsers and return named SQL sections for execution/testing."""
    for name, function in [("audit_quantity", quantity_text), ("audit_price", price_text),
                           ("audit_price_issue", price_issue), ("audit_review_price", review_price_text),
                           ("audit_price_delta", price_delta_text),
                           ("audit_customer", customer_text), ("audit_date", date_text)]:
        connection.create_function(name, function, ["VARCHAR"], "VARCHAR", null_handling="special")
    spec = json.loads((ROOT / "src/metric_spec.json").read_text(encoding="utf-8"))
    connection.execute("CREATE TEMP TABLE audit_parameters(history_start TIMESTAMP, cutoff TIMESTAMP)")
    connection.execute("INSERT INTO audit_parameters VALUES (?, ?)",
                       [spec["history_start_inclusive"], spec["analysis_cutoff_exclusive"]])
    sql = (ROOT / "sql/01_data_quality.sql").read_text(encoding="utf-8")
    parts = re.split(r"^-- audit: ([a-z_]+)\s*$", sql, flags=re.MULTILINE)
    return list(zip(parts[1::2], parts[2::2]))


def json_value(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def main():
    manifest = json.loads((ROOT / "data/raw/source_manifest.json").read_text(encoding="utf-8"))
    source = ROOT / manifest["local_workbook"]
    if sha256(source) != manifest["workbook_sha256"]:
        raise ValueError("Source checksum differs from the pinned workbook.")
    processed = ROOT / "data/processed"
    processed.mkdir(exist_ok=True)
    counts = {}
    with tempfile.TemporaryDirectory(prefix="audit-import-", dir=processed) as directory:
        csv_path = Path(directory) / "source_rows.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as output, ZipFile(source) as archive:
            writer = csv.writer(output)
            writer.writerow(["source_sheet", "source_row_number", "source_workbook_sha256", *RAW_COLUMNS])
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            properties = workbook.find(NS + "workbookPr")
            if properties is not None and properties.attrib.get("date1904") in ("1", "true"):
                raise ValueError("Unexpected Excel date system.")
            relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
            strings = shared_strings(archive)
            for sheet in workbook.find(NS + "sheets"):
                target = targets[sheet.attrib[REL]]
                path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
                rows = sheet_rows(archive, path, strings, include_row_numbers=True)
                header_number, headers = next(rows)
                if header_number != 1 or headers != EXPECTED:
                    raise ValueError(f"Unexpected header: {sheet.attrib['name']}")
                count = 0
                for row_number, values in rows:
                    if len(values) != 8:
                        raise ValueError("Unexpected source row width.")
                    writer.writerow([sheet.attrib["name"], row_number, manifest["workbook_sha256"], *values])
                    count += 1
                counts[sheet.attrib["name"]] = count
                print(f"Preserved {count:,} rows from {sheet.attrib['name']}", flush=True)

        if sum(counts.values()) != manifest["raw_row_count"]:
            raise ValueError("Source row count differs from the pinned workbook.")
        with duckdb.connect(str(processed / "retention.duckdb")) as connection:
            connection.execute("SET threads = 4")
            # All original values stay as text. Normalization is temporary and audit-only.
            connection.execute("CREATE OR REPLACE TABLE raw_order_lines AS SELECT * FROM read_csv(?, header=true, all_varchar=true)", [str(csv_path)])
            connection.execute("ALTER TABLE raw_order_lines ALTER source_row_number TYPE BIGINT")
            connection.execute("ALTER TABLE raw_order_lines ADD PRIMARY KEY(source_sheet, source_row_number)")
            sections = prepare_audit(connection)
            results = {}
            evidence = {"product_codes": "audit_product_codes.csv", "invoice_overlap": "audit_invoice_overlap.csv",
                        "header_issues": "audit_header_issues.csv", "outlier_lines": "audit_outlier_lines.csv",
                        "date_gaps": "audit_date_gaps.csv"}
            for name, query in sections:
                cursor = connection.execute(query)
                if name == "setup":
                    continue
                columns = [column[0] for column in cursor.description]
                rows = cursor.fetchall()
                records = [dict(zip(columns, row)) for row in rows]
                if name in evidence:
                    with (processed / evidence[name]).open("w", newline="", encoding="utf-8") as output:
                        writer = csv.writer(output)
                        writer.writerow(columns)
                        writer.writerows([[json_value(v) if isinstance(v, Decimal) or hasattr(v, "isoformat") else v for v in row] for row in rows])
                    results[name] = {"rows": len(rows), "file": "data/processed/" + evidence[name], "preview": records[:10]}
                else:
                    results[name] = records
                print(f"Completed audit: {name}", flush=True)

    if sha256(source) != manifest["workbook_sha256"]:
        raise ValueError("Original workbook changed unexpectedly.")
    summary = {"step": 5, "source_sha256": manifest["workbook_sha256"], "source_rows": sum(counts.values()),
               "purpose": "Raw-data audit; exposures are not cleaned sales or retention results",
               "money_encoding": "Decimal strings in JSON; GBP. Candidate exposures use an explicit audit scenario: round to six decimals only where absolute raw-price deviation is <= 1e-9 GBP. Strict precision failures remain flagged; this is not an approved cleaning rule or final revenue.",
               "database": "data/processed/retention.duckdb", "results": results}
    (ROOT / "reports/data_quality_summary.json").write_text(json.dumps(summary, indent=2, default=json_value) + "\n", encoding="utf-8")
    print("Saved reports/data_quality_summary.json. Original source unchanged; no cleaned business tables created.")


if __name__ == "__main__":
    main()
