from pathlib import Path
import sys
import duckdb
sys.dont_write_bytecode=True
sys.path.insert(0,str((Path(__file__).resolve().parents[2]/'src')))
from retention_analysis import build,validate
c=duckdb.connect(':memory:')
c.execute('CREATE TABLE fact_orders(invoice_id VARCHAR,customer_id VARCHAR,order_timestamp TIMESTAMP,order_sales_gbp DECIMAL(24,6),is_identified BOOLEAN)')
rows=[('01','old','2011-01-01',1,True),('02','old','2011-03-01',1,True),
('03','same','2011-03-01',1,True),('04','same','2011-03-01',1,True),('05','same','2011-05-01',1,True),
('06','exact90','2011-04-01',1,True),('07','exact90','2011-06-30',1,True),
('08','end_at_T','2011-04-02',1,True),('09','end_at_T','2011-04-03',1,True),
('10','exact30','2011-05-31',1,True),('11','exact30','2011-06-30',1,True),
('12','late30','2011-05-31',1,True),('13','late30','2011-06-30 00:00:01',1,True),
('14','immature','2011-06-01',1,True),('15','immature','2011-06-02',1,True),
('16',None,'2011-05-01',1,False),('17','outside','2011-07-01',1,True)]
c.executemany('INSERT INTO fact_orders VALUES(?,?,?,?,?)',rows)
p={'history_start':'2011-01-01T00:00:00','cutoff':'2011-07-01T00:00:00','cohort_start':'2011-02-01T00:00:00'}
build(c,p);validate(c,p)
def window(customer,d):return c.execute('SELECT eligible_window,repeated_window FROM customer_repeat_windows WHERE customer_id=? AND window_days=?',[customer,d]).fetchone()
assert window('exact90',90)==(True,True)
assert window('end_at_T',90)==(False,False)
assert window('exact30',30)==(True,True)
assert window('late30',30)==(True,False)
assert window('immature',30)==(False,False)
assert c.execute("SELECT repeated_window,repeated_collapsed_timestamp FROM customer_repeat_windows WHERE customer_id='same' AND window_days=30").fetchone()==(True,False)
assert c.execute("SELECT count(*) FROM customer_repeat_windows WHERE customer_id='outside'").fetchone()[0]==0
assert c.execute("SELECT cohort_size,retained_customers,retention_rate FROM cohort_retention WHERE cohort_month='2011-02-01' AND month_index=0").fetchone()==(0,0,None)
assert c.execute("SELECT retained_customers,retention_rate FROM cohort_retention WHERE cohort_month='2011-03-01' AND month_index=1").fetchone()==(0,0.0)
assert c.execute("SELECT retained_customers,retention_rate FROM cohort_retention WHERE cohort_month='2011-03-01' AND month_index=2").fetchone()==(1,1.0)
assert c.execute("SELECT is_observable,retained_customers,retention_rate FROM cohort_retention WHERE cohort_month='2011-06-01' AND month_index=1").fetchone()==(False,None,None)
assert c.execute("SELECT is_primary_cohort FROM cohort_retention WHERE cohort_month='2011-01-01' LIMIT 1").fetchone()==(False,)
print('PASS: exact 30/90-day boundaries, cutoff equality, early-repeat censoring, same-timestamp sensitivity, initial-history exclusion, empty cohort, observed zero, reactivation after a skipped month, future NULLs and independent full-table verification.')
