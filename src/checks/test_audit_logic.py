"""Small synthetic checks for the audit's nontrivial overlap and parsing logic."""
from pathlib import Path
import sys
import duckdb

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "src"))
from audit_data import prepare_audit, RAW_COLUMNS, quantity_text, price_text, customer_text, review_price_text, price_issue

assert quantity_text("1.5") is None
assert price_text("0.1234567") is None
assert price_text("19.99") == "19.990000"
assert customer_text("12345.0") == "12345"
assert customer_text("12.5") is None

assert price_text("2.5499999999999998") is None
assert review_price_text("2.5499999999999998") == "2.550000"
assert price_issue("2.5499999999999998") == "representation_noise_candidate"
assert review_price_text("0.1234567") is None
assert price_issue("not a price") == "invalid_or_out_of_range"
rows = []
positions = {"Year 2009-2010": 2, "Year 2010-2011": 2}
def add(sheet, invoice, qty="1", customer="12345", stamp="40513", code="12345"):
    row_number = positions[sheet]
    positions[sheet] += 1
    rows.append((sheet, row_number, "synthetic", invoice, code, "EXAMPLE PRODUCT", qty, stamp, "2.00", customer, "United Kingdom"))

for sheet in positions:
    add(sheet, "100")
    add(sheet, "100")
add("Year 2009-2010", "200", qty="1")
add("Year 2010-2011", "200", qty="2")
add("Year 2010-2011", "300", stamp="40513")
add("Year 2010-2011", "300", stamp="40514")
add("Year 2010-2011", "400", customer="12.5")
add("Year 2010-2011", "500", code="12345")
add("Year 2010-2011", "500", code="23456", customer="")
add("Year 2010-2011", "600", customer="12345")
add("Year 2010-2011", "600", customer="54321")

with duckdb.connect(":memory:") as con:
    fields = ["source_sheet VARCHAR", "source_row_number BIGINT", "source_workbook_sha256 VARCHAR"] + [f"{name} VARCHAR" for name in RAW_COLUMNS]
    con.execute("CREATE TABLE raw_order_lines (" + ",".join(fields) + ")")
    con.executemany("INSERT INTO raw_order_lines VALUES (" + ",".join("?" for _ in fields) + ")", rows)
    sections = prepare_audit(con)
    con.execute(dict(sections)["setup"])
    assert con.execute("SELECT invoice_id, overlap_status FROM audit_overlap ORDER BY invoice_id").fetchall() == [("100", "identical"), ("200", "conflict")]
    disposition = dict(con.execute("SELECT proposed_disposition,count(*) FROM audit_dispositions WHERE invoice_id='100' GROUP BY 1").fetchall())
    assert disposition == {"exclude_older_overlap_copy": 2, "exclude_within_version_duplicate": 1, "retain_for_step_6_review": 1}
    assert con.execute("SELECT count(*) FROM audit_dispositions WHERE invoice_id='200' AND proposed_disposition='hold_overlap_conflict'").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM audit_dispositions WHERE invoice_id IN ('300','400','600') AND header_conflict").fetchone()[0] == 5
    assert con.execute("SELECT distinct_known_customers,missing_or_invalid_customer_rows,invalid_customer_rows FROM audit_invoice_versions WHERE invoice_id='500'").fetchone() == (1,1,0)
    assert con.execute("SELECT count(*) FROM raw_order_lines").fetchone()[0] == len(rows)
    for name, query in sections:
        if name != "setup":
            con.execute(query).fetchall()
print("PASS: exact parsing, multiset overlap, conflicting versions, duplicate precedence, header conflicts, missing-ID inheritance, every audit SQL query, and raw-row preservation.")
