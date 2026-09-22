"""Read-only feasibility profile of the original UCI Online Retail II workbook.

Uses Python 3.10+ standard library only. This is an intake check, not a cleaning
pipeline or a final retention calculation. Run from the repository root:
    python src/profile_dataset.py
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import posixpath
import xml.etree.ElementTree as ET
from zipfile import ZipFile

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
EXPECTED = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate",
            "Price", "Customer ID", "Country"]
ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def shared_strings(archive):
    strings = []
    with archive.open("xl/sharedStrings.xml") as source:
        for _, element in ET.iterparse(source, events=("end",)):
            if element.tag == NS + "si":
                strings.append("".join(t.text or "" for t in element.iter(NS + "t")))
                element.clear()
    return strings


def sheet_rows(archive, path, strings, include_row_numbers=False):
    with archive.open(path) as source:
        context = ET.iterparse(source, events=("start", "end"))
        _, root = next(context)
        for event, element in context:
            if event != "end" or element.tag != NS + "row":
                continue
            values = [""] * 8
            for cell in element.findall(NS + "c"):
                letters = "".join(c for c in cell.attrib["r"] if c.isalpha())
                index = 0
                for letter in letters:
                    index = index * 26 + ord(letter.upper()) - ord("A") + 1
                value = cell.findtext(NS + "v", default="")
                if cell.attrib.get("t") == "s" and value:
                    value = strings[int(value)]
                elif cell.attrib.get("t") == "inlineStr":
                    value = "".join(t.text or "" for t in cell.iter(NS + "t"))
                if index > len(values):
                    values.extend([""] * (index - len(values)))
                values[index - 1] = value
            yield (int(element.attrib["r"]), values) if include_row_numbers else values
            element.clear()
            root.clear()


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def timestamp(value):
    serial = number(value)
    if serial is None:
        return None
    try:
        return datetime(1899, 12, 30) + timedelta(seconds=round(serial * 86400))
    except (OverflowError, ValueError):
        return None


def profile(path):
    flags = Counter()
    monthly = Counter()
    countries = Counter()
    customers = set()
    invoices = set()
    invoice_customers = defaultdict(set)
    candidate_orders = defaultdict(set)
    first_purchase = {}
    sheets = []
    seen_rows = set()
    earliest = latest = None
    max_candidate_date = None
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        properties = workbook.find(NS + "workbookPr")
        if properties is not None and properties.attrib.get("date1904") in ("1", "true"):
            raise ValueError("This profiler expects the Excel 1900 date system.")
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {r.attrib["Id"]: r.attrib["Target"] for r in relationships}
        strings = shared_strings(archive)
        for sheet in workbook.find(NS + "sheets"):
            target = targets[sheet.attrib[REL]]
            sheet_path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
            rows = sheet_rows(archive, sheet_path, strings)
            headers = next(rows)
            if headers != EXPECTED:
                raise ValueError(f"Unexpected columns in {sheet.attrib['name']}: {headers}")
            count = within_duplicates = cross_duplicates = 0
            sheet_seen = set()
            sheet_min = sheet_max = None
            for row in rows:
                if not any(row):
                    flags["fully_empty_rows"] += 1
                    continue
                count += 1
                invoice, stock, description, quantity, date, price, customer, country = row
                # Equality is based on the eight decoded source fields; never drop rows here.
                key = hashlib.sha256(json.dumps(row, ensure_ascii=False).encode("utf-8")).digest()
                within_duplicates += key in sheet_seen
                cross_duplicates += key in seen_rows
                sheet_seen.add(key)
                flags["raw_rows"] += 1
                invoices.add(invoice)
                if customer:
                    customers.add(customer)
                    invoice_customers[invoice].add(customer)
                flags["missing_customer_id_rows"] += not bool(customer)
                flags["missing_description_rows"] += not bool(description.strip())
                cancel = invoice.upper().startswith("C")
                flags["cancellation_prefix_rows"] += cancel
                q = number(quantity)
                p = number(price)
                dt = timestamp(date)
                flags["invalid_quantity_rows"] += q is None
                flags["invalid_price_rows"] += p is None
                flags["invalid_date_rows"] += dt is None
                flags["nonpositive_quantity_rows"] += q is not None and q <= 0
                flags["nonpositive_price_rows"] += p is not None and p <= 0
                countries[country] += 1
                if dt is not None:
                    monthly[dt.strftime("%Y-%m")] += 1
                    earliest = dt if earliest is None else min(earliest, dt)
                    latest = dt if latest is None else max(latest, dt)
                    sheet_min = dt if sheet_min is None else min(sheet_min, dt)
                    sheet_max = dt if sheet_max is None else max(sheet_max, dt)
                # Broad feasibility screen only: special item codes, returns, and
                # invoice conflicts still require the Step 5 audit and Step 6 rules.
                if (customer and invoice and not cancel and dt is not None
                        and q is not None and q > 0 and p is not None and p > 0):
                    flags["candidate_positive_purchase_rows"] += 1
                    candidate_orders[customer].add(invoice)
                    first_purchase[customer] = min(first_purchase.get(customer, dt), dt)
                    max_candidate_date = dt if max_candidate_date is None else max(max_candidate_date, dt)
            seen_rows.update(sheet_seen)
            sheets.append({
                "name": sheet.attrib["name"], "columns": headers, "raw_rows": count,
                "min_timestamp": sheet_min.isoformat(sep=" "),
                "max_timestamp": sheet_max.isoformat(sep=" "),
                "repeated_rows_within_sheet_after_first": within_duplicates,
                "rows_matching_any_prior_sheet": cross_duplicates,
            })
            print(f"Profiled {sheet.attrib['name']}: {count:,} rows", flush=True)
    repeated = sum(len(orders) > 1 for orders in candidate_orders.values())
    return {
        "purpose": "Step 2 feasibility screening, not cleaned data or final business findings",
        "file_name": path.name,
        "file_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "sheets": sheets,
        "raw_flags_nonexclusive": dict(sorted(flags.items())),
        "raw_distinct_nonmissing_customers": len(customers),
        "raw_distinct_invoice_values_including_cancellations": len(invoices),
        "invoices_associated_with_multiple_nonmissing_customer_ids": sum(len(c) > 1 for c in invoice_customers.values()),
        "raw_date_min": earliest.isoformat(sep=" "),
        "raw_date_max": latest.isoformat(sep=" "),
        "raw_rows_by_month": dict(sorted(monthly.items())),
        "raw_country_rows": dict(countries.most_common()),
        "distinct_decoded_source_rows": len(seen_rows),
        "repeated_source_rows_after_first_across_workbook": flags["raw_rows"] - len(seen_rows),
        "candidate_purchase_screen": {
            "rule": "Nonmissing customer and invoice, no C prefix, positive quantity and price, valid date; distinct invoices per customer",
            "caveat": "Uncleaned feasibility counts. Not a cohort retention or fixed-window repeat rate. Special codes and invoice conflicts remain unaudited.",
            "customers": len(candidate_orders),
            "distinct_invoice_values": len(set().union(*candidate_orders.values())),
            "customers_with_multiple_distinct_invoices": repeated,
            "last_candidate_timestamp": max_candidate_date.isoformat(sep=" "),
            "customers_with_at_least_n_days_follow_up_from_first_observed_candidate_purchase": {
                str(days): sum(first <= max_candidate_date - timedelta(days=days) for first in first_purchase.values())
                for days in (30, 60, 90, 180)
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/raw/online_retail_II.xlsx")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/dataset_profile.json")
    args = parser.parse_args()
    result = profile(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved feasibility profile to {args.output}")


if __name__ == "__main__":
    main()
