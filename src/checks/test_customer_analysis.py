from pathlib import Path
from datetime import date
from decimal import Decimal
import json,sys
import duckdb
sys.dont_write_bytecode=True
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'src'))
from customer_analysis import build_rfm,validate_rfm,score,segment,comparisons,wilson
spec=json.loads((root/'src/metric_spec.json').read_text(encoding="utf-8"))
c=duckdb.connect(':memory:')
c.execute('CREATE TABLE fact_orders(customer_id VARCHAR,order_timestamp TIMESTAMP,order_sales_gbp DECIMAL(24,6))')
c.executemany('INSERT INTO fact_orders VALUES(?,?,?)',[
('dormant','2010-11-30',5),('boundary','2010-12-01',10),
('r90','2011-01-01',20),('r90','2011-09-02',20),
('r91','2011-01-01',20),('r91','2011-09-01',20),
('new30','2011-11-01',10),('old31','2011-10-31',10),
('tieA','2011-11-20',12),('tieB','2011-11-20',12)])
p={'history_start':'2009-12-01T00:00:00','rfm_start':'2010-12-01T00:00:00','cutoff':'2011-12-01T00:00:00'}
build_rfm(c,p);validate_rfm(c,p)
assert c.execute("SELECT frequency_12m,monetary_12m_gbp,r_score,f_score,m_score,segment FROM rfm_snapshot WHERE customer_id='dormant'").fetchone()==(0,Decimal(0),None,None,None,'Dormant beyond 12 months')
assert c.execute("SELECT frequency_12m FROM rfm_snapshot WHERE customer_id='boundary'").fetchone()[0]==1
assert c.execute("SELECT segment FROM rfm_snapshot WHERE customer_id='r91'").fetchone()[0]=='At Risk Repeat'
assert c.execute("SELECT segment FROM rfm_snapshot WHERE customer_id='r90'").fetchone()[0] in ('Loyal','Champions')
assert c.execute("SELECT segment FROM rfm_snapshot WHERE customer_id='new30'").fetchone()[0]=='Promising New'
assert c.execute("SELECT segment FROM rfm_snapshot WHERE customer_id='old31'").fetchone()[0]=='Recent Occasional'
assert len(set(c.execute("SELECT r_score,f_score,m_score FROM rfm_snapshot WHERE customer_id LIKE 'tie%'").fetchall()))==1
assert score([1]*5,1)==3
assert [score([1,1,2,5,5],x) for x in [1,1,2,5,5]]==[2,2,3,5,5]
lo,hi=wilson(20,100);assert round(lo,3)==.133 and round(hi,3)==.289
population=[]
def add(group,month,n,x):
 for i in range(n):population.append({'first_order_value_band':'GBP 100-<250','first_order_product_band':'6+ products','first_order_geography':group,'cohort_month':date(2010,month,1),'repeated_90d':i<x,'customer_sales_90d':Decimal(100)})
add('United Kingdom',3,80,8);add('United Kingdom',4,20,18)
add('Other known country',3,20,10);add('Other known country',4,80,40)
add('Unknown',3,4,1)
a,m,adjusted=comparisons(population,spec)
geo=[r for r in adjusted if r['feature']=='first_order_geography']
assert len(geo)==2 and all(abs(r['standardized_rate']-.5)<1e-12 for r in geo)
assert [r for r in a if r['group']=='Unknown'][0]['repeat_rate_90d'] is None
population.clear();add('United Kingdom',3,20,10);add('United Kingdom',4,80,40);add('Other known country',3,20,10);add('Other known country',5,80,40)
a,m,adjusted=comparisons(population,spec)
geo=[r for r in adjusted if r['feature']=='first_order_geography']
assert all(r['shared_months']==1 and r['shared_eligible_customers']==20 and r['standardized_rate'] is None for r in geo)
print('PASS: actual RFM SQL boundaries, dormant customers, tie-preserving scores, segment precedence, Wilson example, common-cohort weights and small-sample suppression.')
