"""Adversarial small fixture for actual Step 6 SQL; no production data mutations."""
from pathlib import Path
import csv
import re
import sys
import tempfile
import duckdb
from decimal import Decimal
sys.dont_write_bytecode=True
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'src'))
from audit_data import prepare_audit,RAW_COLUMNS

rows=[]
def add(invoice,code='12345',qty='1',price='2.00',customer='12345',stamp='40513',sheet='Year 2010-2011',country='United Kingdom'):
    rows.append((sheet,len(rows)+2,'fixture',invoice,code,'DESCRIPTIVE ITEM',qty,stamp,price,customer,country))

# Same invoice multiset after accepted price normalization; keep newer version.
add('100',price='2.5499999999999998',sheet='Year 2009-2010')
add('100',price='2.55')
add('100',price='2.55')  # Deliberately different multiplicity: whole invoice conflict.
add('101',sheet='Year 2009-2010');add('101');add('102');add('102')
add('103',customer='');add('103',code='23456') # Recover identity within invoice.
add('104',customer='');add('105',code='FEE');add('106',code='UNKNOWN')
add('107',stamp='40878');add('108',price='0.1234567');add('109',qty='-1')
add('C110');add('111',stamp='40513');add('111',stamp='40514')
add('112',customer='12.5');add('113',customer='12345');add('113',customer='54321')
add('114',country='France');add('114',code='23456',country='Germany')
add('115',price='2.5499999999999998');add('116',price='0')
add('117',price='2.5499999999999998',sheet='Year 2009-2010');add('117',price='2.55')
with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d, duckdb.connect(':memory:') as con:
    p=Path(d)/'roles.csv'
    with p.open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['stock_code','product_role','decision_reason'])
        w.writerows([['12345','merchandise','fixture'],['23456','merchandise','fixture'],['FEE','non_merchandise','fixture'],['UNKNOWN','unresolved','fixture']])
    con.execute('CREATE TABLE raw_order_lines(source_sheet VARCHAR,source_row_number BIGINT,source_workbook_sha256 VARCHAR,'+','.join(x+' VARCHAR' for x in RAW_COLUMNS)+')')
    con.executemany('INSERT INTO raw_order_lines VALUES('+','.join('?' for _ in range(11))+')',rows)
    setup=dict(prepare_audit(con))['setup'].replace('CAST(audit_price(raw_price)','CAST(audit_review_price(raw_price)')
    con.execute(setup)
    params={'roles':str(p),'cohort_start':'2010-03-01','cutoff':'2011-12-01'}
    for stmt in (root/'sql/01b_clean_data.sql').read_text(encoding="utf-8").split(';'):
        if not stmt.strip():continue
        names=set(re.findall(r'\$([a-z_]+)',stmt))
        con.execute(stmt,{k:params[k] for k in names}) if names else con.execute(stmt)
    assert con.execute('SELECT count(*) FROM stg_order_lines').fetchone()[0]==len(rows)
    assert {x[0] for x in con.execute('SELECT invoice_id FROM fact_orders').fetchall()}=={'101','102','103','104','114','115','117'}
    assert con.execute("SELECT customer_id,customer_id_inherited_within_invoice FROM fact_orders WHERE invoice_id='103'").fetchone()==('12345',True)
    assert con.execute("SELECT invoice_country,country_conflict FROM fact_orders WHERE invoice_id='114'").fetchone()==(None,True)
    assert con.execute("SELECT customer_id,customer_order_sequence FROM fact_orders WHERE invoice_id='104'").fetchone()==(None,None)
    assert con.execute("SELECT order_sales_gbp FROM fact_orders WHERE invoice_id='102'").fetchone()[0]==Decimal('2')
    assert con.execute("SELECT order_sales_gbp FROM sensitivity_orders_keep_duplicates WHERE invoice_id='102'").fetchone()[0]==Decimal('4')
    assert con.execute("SELECT price_normalized,line_sales_gbp FROM fact_order_lines WHERE invoice_id='115'").fetchone()==(True,Decimal('2.55'))
    assert con.execute("SELECT count(*) FROM fact_order_lines WHERE invoice_id='117'").fetchone()[0]==1
    assert con.execute('SELECT first_order_id,second_order_id,time_to_second_order_days FROM customer_features').fetchone()==('101','102',0.0)
print('PASS: actual cleaning SQL handles overlap multiplicity, accepted price matching, duplicate sensitivity, unknown IDs, within-invoice ID inheritance, country conflicts, header conflicts, invalid money, cutoff, roles, credits, and tied invoice sequencing.')
