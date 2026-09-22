from pathlib import Path
import sys
from decimal import Decimal
import duckdb
sys.dont_write_bytecode=True
sys.path.insert(0,str((Path(__file__).resolve().parents[2]/'src')))
from monthly_kpis import build,get_rows,validate,money_ratio
c=duckdb.connect(':memory:')
c.execute('CREATE TABLE fact_orders(invoice_id VARCHAR,order_timestamp TIMESTAMP,order_month DATE,customer_id VARCHAR,order_sales_gbp DECIMAL(24,6),is_identified BOOLEAN)')
c.execute("""INSERT INTO fact_orders VALUES
('1','2010-01-01','2010-01-01','A',10,true),
('2','2010-01-05','2010-01-01','A',20,true),
('3','2010-01-06','2010-01-01',NULL,30,false),
('4','2010-03-01','2010-03-01','A',40,true),
('5','2010-03-02','2010-03-01','B',60,true),
('6','2010-04-03','2010-04-01',NULL,50,false),
('7','2010-05-01','2010-05-01','C',999,true)""")
c.execute("CREATE TABLE customer_features AS SELECT customer_id,min(order_month) cohort_month FROM fact_orders WHERE is_identified GROUP BY customer_id")
build(c,'2010-01-01','2010-05-01');r=get_rows(c)
assert len(r)==4
assert (r[0]['orders'],r[0]['active_customers'],r[0]['new_observed_customers'],r[0]['returning_customers'])==(3,1,1,0)
assert r[0]['gross_merchandise_sales_gbp']==Decimal(60)
assert r[0]['average_order_value_gbp']==Decimal(20)
assert r[0]['sales_mom_growth'] is None
assert r[1]['orders']==0 and r[1]['gross_merchandise_sales_gbp']==0
assert r[1]['average_order_value_gbp'] is None and r[1]['identified_sales_share'] is None
assert r[1]['sales_mom_growth']==-1
assert r[2]['sales_mom_growth'] is None
assert (r[2]['new_observed_customers'],r[2]['returning_customers'])==(1,1)
assert r[3]['orders']==1 and r[3]['active_customers']==0 and r[3]['returning_customer_share'] is None
assert r[3]['identified_sales_share']==0 and r[3]['sales_mom_growth']==-.5
c.execute("DELETE FROM fact_orders WHERE invoice_id='7'")
validate(c,r,'2010-01-01','2010-05-01')
assert money_ratio('1.000001','2')=='0.500001'
assert money_ratio('1','0') is None
print('PASS: actual monthly SQL handles empty calendar month, new customer repeat purchases, returning customer, unidentified-only month, zero denominators, first month, prior calendar month, cutoff exclusion and Decimal half-up rounding.')
