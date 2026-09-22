"""Steps 11-12: RFM, observed customer value and eligible 90-day comparisons."""
from bisect import bisect_left,bisect_right
from collections import defaultdict
from datetime import datetime,timedelta
from decimal import Decimal
import csv
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median
import duckdb
from audit_data import json_value,sha256
from monthly_kpis import money_ratio
from retention_analysis import records

ROOT=Path(__file__).resolve().parents[1]
FEATURES={'first_order_value_band':['Under GBP 50','GBP 50-<100','GBP 100-<250','GBP 250+'],
          'first_order_product_band':['1 product','2-5 products','6+ products'],
          'first_order_geography':['United Kingdom','Other known country','Unknown']}


def execute_sql(con,text,params):
    for statement in text.split(';'):
        if not statement.strip():continue
        keys=set(re.findall(r'\$([a-z_]+)',statement))
        con.execute(statement,{k:params[k] for k in keys}) if keys else con.execute(statement)


def build_rfm(con,params,source='fact_orders',target='rfm_snapshot'):
    assert source in ['fact_orders','sensitivity_orders_keep_duplicates','extreme_input']
    assert target in ['rfm_snapshot','rfm_keep_duplicates','rfm_exclude_extreme']
    con.execute(f'CREATE OR REPLACE TEMP VIEW rfm_input_orders AS SELECT * FROM {source}')
    sql=(ROOT/'sql/05_rfm_segments.sql').read_text(encoding="utf-8").replace('rfm_snapshot',target)
    execute_sql(con,sql,params)


def score(sorted_values,value):
    left=bisect_left(sorted_values,value);equal=bisect_right(sorted_values,value)-left
    return 1+min(4,5*(2*left+equal)//(2*len(sorted_values)))


def segment(f,r,first,T,rs,fs,ms):
    if f==0:return 'Dormant beyond 12 months'
    if f>=2 and r>90:return 'At Risk Repeat'
    if f==1 and r>90:return 'Inactive Single-Purchase'
    if f>=2 and r<=90 and min(rs,fs,ms)>=4:return 'Champions'
    if f>=2 and r<=90:return 'Loyal'
    if f==1 and r<=90 and first>=T-timedelta(days=30):return 'Promising New'
    return 'Recent Occasional'


def validate_rfm(con,params,source='fact_orders',target='rfm_snapshot'):
    H,W,T=(datetime.fromisoformat(params[k]) for k in ['history_start','rfm_start','cutoff'])
    customers=defaultdict(list)
    for customer,stamp,sales in con.execute(f'SELECT customer_id,order_timestamp,order_sales_gbp FROM {source}').fetchall():
        if customer is not None and H<=stamp<T:customers[customer].append((stamp,sales))
    expected={}
    for customer,orders in customers.items():
        stamps=[x[0] for x in orders];recent=[x for x in orders if x[0]>=W]
        expected[customer]={'first_order_timestamp':min(stamps),'last_order_timestamp':max(stamps),
            'historical_order_count':len(orders),'historical_sales_gbp':sum((x[1] for x in orders),Decimal(0)),
            'recency_days':(T.date()-max(stamps).date()).days,'frequency_12m':len(recent),
            'monetary_12m_gbp':sum((x[1] for x in recent),Decimal(0))}
    values={k:sorted(x[k] for x in expected.values() if x['frequency_12m']>0) for k in ['recency_days','frequency_12m','monetary_12m_gbp']}
    actual=records(con,f'SELECT * FROM {target}')
    assert len(actual)==len(expected)
    for row in actual:
        e=expected[row['customer_id']]
        for k,v in e.items():assert row[k]==v,(target,row['customer_id'],k)
        scores=[None,None,None] if e['frequency_12m']==0 else [6-score(values['recency_days'],e['recency_days']),score(values['frequency_12m'],e['frequency_12m']),score(values['monetary_12m_gbp'],e['monetary_12m_gbp'])]
        assert [row[k] for k in ['r_score','f_score','m_score']]==scores
        assert row['segment']==segment(e['frequency_12m'],e['recency_days'],e['first_order_timestamp'],T,*scores)
        assert row['reactivation_candidate']==(e['historical_order_count']>=2 and e['recency_days']>90)
        assert row['snapshot_date']==T.date()
    return True


def wilson(x,n,z=1.959963984540054):
    if n==0:return None,None
    p=x/n;den=1+z*z/n;center=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return max(0,center-half),min(1,center+half)


def comparisons(population,spec):
    threshold=spec['comparison']['headline_minimum_eligible_customers']
    month_min=spec['comparison']['shared_cohort_minimum_customers_per_group_month']
    totals=[];monthly=[];adjusted=[]
    for feature,labels in FEATURES.items():
        groups={label:[r for r in population if r[feature]==label] for label in labels}
        published=[label for label,rows in groups.items() if len(rows)>=threshold]
        for label,rows in groups.items():
            n=len(rows);x=sum(r['repeated_90d'] for r in rows);ok=n>=threshold
            lo,hi=wilson(x,n,spec['comparison']['confidence_z']) if ok else (None,None)
            total=sum((r['customer_sales_90d'] for r in rows),Decimal(0))
            totals.append({'feature':feature,'group':label,'eligible_customers':n,'repeat_customers':x,
                'publishable':ok,'repeat_rate_90d':x/n if ok else None,'wilson_low':lo,'wilson_high':hi,
                'mean_observed_sales_90d_gbp':money_ratio(str(total),str(n)) if ok else None,
                'median_observed_sales_90d_gbp':median([r['customer_sales_90d'] for r in rows]) if ok else None})
        months=sorted({r['cohort_month'] for r in population})
        cells={(label,m):[r for r in groups[label] if r['cohort_month']==m] for label in labels for m in months}
        for (label,m),rows in cells.items():
            n=len(rows);x=sum(r['repeated_90d'] for r in rows)
            monthly.append({'feature':feature,'group':label,'cohort_month':m,'eligible_customers':n,'repeat_customers':x,
                            'repeat_rate_90d':x/n if n>=month_min and label in published else None})
        common=[m for m in months if len(published)>=2 and all(len(cells[(label,m)])>=month_min for label in published)]
        denominator=sum(len(cells[(label,m)]) for m in common for label in published)
        weights={m:sum(len(cells[(label,m)]) for label in published)/denominator for m in common}
        shared_totals={label:sum(len(cells[(label,m)]) for m in common) for label in published}
        shared_publishable=bool(common) and all(n>=threshold for n in shared_totals.values())
        for label in published:
            standardized=sum(weights[m]*sum(r['repeated_90d'] for r in cells[(label,m)])/len(cells[(label,m)]) for m in common) if shared_publishable else None
            n=sum(len(cells[(label,m)]) for m in common)
            x=sum(sum(r['repeated_90d'] for r in cells[(label,m)]) for m in common)
            adjusted.append({'feature':feature,'group':label,'shared_months':len(common),'shared_eligible_customers':n,
                'shared_unadjusted_rate':x/n if n>=threshold else None,'standardized_rate':standardized,
                'cohort_months':[m.isoformat() for m in common],
                'weights':{m.isoformat():w for m,w in weights.items()},
                'status':('Available: descriptive common-cohort standardization' if shared_publishable else 'Suppressed: a shared-cohort group has fewer than 100 customers' if common else 'Unavailable: no shared months with minimum group counts')})
        assert sum(len(x) for x in groups.values())==len(population)
        if weights:assert abs(sum(weights.values())-1)<1e-12
    return totals,monthly,adjusted


def concentration(rows):
    ranked=sorted(rows,key=lambda r:(-r['historical_sales_gbp'],r['customer_id']))
    n=math.ceil(len(ranked)*.1);total=sum((r['historical_sales_gbp'] for r in ranked),Decimal(0))
    top=sum((r['historical_sales_gbp'] for r in ranked[:n]),Decimal(0))
    return {'customers':len(ranked),'top_customer_count':n,'identified_historical_sales_gbp':total,
            'top_customer_sales_gbp':top,'top_customer_sales_share':float(top/total) if total else None}


def export_csv(path,rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    spec=json.loads((ROOT/'src/metric_spec.json').read_text(encoding="utf-8"));retention=json.loads((ROOT/'reports/retention_summary.json').read_text(encoding="utf-8"))
    clean=json.loads((ROOT/'reports/cleaning_summary.json').read_text(encoding="utf-8"))
    assert spec['specification_version']==retention['contract_version']==clean['contract_version']
    assert sha256(ROOT/'data/raw/online_retail_II.xlsx')==clean['source_sha256']
    assert sha256(ROOT/'src/product_roles.csv')==clean['product_mapping_sha256']
    params={'history_start':spec['history_start_inclusive'],'cutoff':spec['analysis_cutoff_exclusive'],
            'rfm_start':spec['rfm']['measurement_start_inclusive'],'cohort_start':spec['primary_cohort_start_inclusive']}
    with duckdb.connect(str(ROOT/'data/processed/retention.duckdb')) as con:
        fingerprint=hashlib.sha256()
        for row in con.execute('SELECT * FROM fact_orders ORDER BY invoice_id').fetchall():fingerprint.update((json.dumps(row,default=json_value)+'\n').encode())
        assert fingerprint.hexdigest()==retention['fact_orders_sha256'],'Run Steps 8-9 after cleaning changes.'
        con.execute('BEGIN TRANSACTION')
        try:
            build_rfm(con,params)
            build_rfm(con,params,'sensitivity_orders_keep_duplicates','rfm_keep_duplicates')
            con.execute("CREATE TEMP VIEW extreme_input AS SELECT * FROM fact_orders WHERE invoice_id<>'541431'")
            build_rfm(con,params,'extreme_input','rfm_exclude_extreme')
            execute_sql(con,(ROOT/'sql/06_customer_comparisons.sql').read_text(encoding="utf-8"),params)
            for source,target in [('fact_orders','rfm_snapshot'),('sensitivity_orders_keep_duplicates','rfm_keep_duplicates'),('extreme_input','rfm_exclude_extreme')]:validate_rfm(con,params,source,target)
            # Independent first-order feature and fixed-window value checks.
            values=records(con,'SELECT * FROM customer_value ORDER BY historical_sales_rank')
            population=records(con,'SELECT * FROM customer_comparison_population ORDER BY customer_id')
            invoices=defaultdict(list)
            for row in records(con,'SELECT * FROM fact_orders WHERE is_identified ORDER BY order_timestamp,invoice_id'):invoices[row['customer_id']].append(row)
            T=datetime.fromisoformat(params['cutoff']);C=datetime.fromisoformat(params['cohort_start'])
            assert len(values)==len(invoices)
            for index,row in enumerate(values,1):
                orders=invoices[row['customer_id']];first=orders[0]['order_timestamp']
                sales90=sum((o['order_sales_gbp'] for o in orders if o['order_timestamp']<=first+timedelta(days=90)),Decimal(0)) if first>=C and first+timedelta(days=90)<T else None
                assert row['customer_sales_90d']==sales90
                assert row['historical_sales_gbp']==sum((o['order_sales_gbp'] for o in orders),Decimal(0))
                assert row['historical_sales_rank']==index
                assert row['observed_tenure_days']==(T.date()-first.date()).days
            assert [r['customer_id'] for r in values]==[r['customer_id'] for r in sorted(values,key=lambda r:(-r['historical_sales_gbp'],r['customer_id']))]
            assert len(population)==sum(r['customer_sales_90d'] is not None for r in values)
            for row in population:
                orders=invoices[row['customer_id']];first=orders[0]
                assert row['first_order_id']==first['invoice_id'] and row['first_order_country']==first['invoice_country']
                assert row['first_order_sales_gbp']==first['order_sales_gbp'] and row['first_order_distinct_products']==first['distinct_products']
                assert row['repeated_90d']==(len(orders)>1 and orders[1]['order_timestamp']<=first['order_timestamp']+timedelta(days=90))
                v=first['order_sales_gbp'];n=first['distinct_products']
                assert row['first_order_value_band']==('Under GBP 50' if v<50 else 'GBP 50-<100' if v<100 else 'GBP 100-<250' if v<250 else 'GBP 250+')
                assert row['first_order_product_band']==('1 product' if n==1 else '2-5 products' if n<=5 else '6+ products')
            con.execute('COMMIT')
        except Exception:con.execute('ROLLBACK');raise
        primary=records(con,'SELECT * FROM rfm_snapshot ORDER BY customer_id')
        segments=records(con,"""SELECT segment,count(*) AS customers,sum(monetary_12m_gbp) AS monetary_12m_gbp,
            sum(historical_sales_gbp) AS historical_sales_gbp,median(recency_days) AS median_recency_days,
            median(frequency_12m) AS median_frequency_12m FROM rfm_snapshot GROUP BY segment ORDER BY customers DESC""")
        total_m=sum(r['monetary_12m_gbp'] for r in primary)
        assert total_m==con.execute('SELECT sum(order_sales_gbp) FROM fact_orders WHERE is_identified AND order_timestamp>=?',[params['rfm_start']]).fetchone()[0]
        for row in segments:row['customer_share']=row['customers']/len(primary);row['monetary_share']=float(row['monetary_12m_gbp']/total_m)
        sensitivity=[]
        for name,table in [('keep_within_sheet_duplicates','rfm_keep_duplicates'),('exclude_invoice_541431','rfm_exclude_extreme')]:
            alternative=records(con,f'SELECT * FROM {table}');mapping={r['customer_id']:r for r in alternative}
            common=[r for r in primary if r['customer_id'] in mapping]
            sensitivity.append({'scenario':name,'customers':len(alternative),'customers_removed':len(primary)-len(common),
                'm_score_changes_common_customers':sum(r['m_score']!=mapping[r['customer_id']]['m_score'] for r in common),
                'segment_changes_common_customers':sum(r['segment']!=mapping[r['customer_id']]['segment'] for r in common),
                'monetary_12m_gbp':sum(r['monetary_12m_gbp'] for r in alternative),**concentration(alternative)})
        reactivation=[]
        for d in spec['reactivation']['sensitivity_thresholds_days_exclusive']:
            chosen=[r for r in primary if r['historical_order_count']>=2 and r['recency_days']>d]
            reactivation.append({'recency_threshold_days_exclusive':d,'customers':len(chosen),'historical_sales_gbp':sum((r['historical_sales_gbp'] for r in chosen),Decimal(0))})
        comparison,by_month,standardized=comparisons(population,spec)
        cross=[]
        for value_band in FEATURES['first_order_value_band']:
            for product_band in FEATURES['first_order_product_band']:
                subset=[r for r in population if r['first_order_value_band']==value_band and r['first_order_product_band']==product_band]
                n=len(subset);x=sum(r['repeated_90d'] for r in subset);ok=n>=spec['comparison']['headline_minimum_eligible_customers']
                lo,hi=wilson(x,n) if ok else (None,None)
                cross.append({'first_order_value_band':value_band,'first_order_product_band':product_band,'eligible_customers':n,
                              'repeat_customers':x,'repeat_rate_90d':x/n if ok else None,'wilson_low':lo,'wilson_high':hi})
        assert sum(r['eligible_customers'] for r in cross)==len(population)
        outputs={'rfm_segments':segments,'reactivation_thresholds':reactivation,'rfm_sensitivity':sensitivity,
                 'customer_comparisons':comparison,'comparison_by_cohort':by_month,'basket_value_product_comparison':cross}
        for file,rows in outputs.items():export_csv(ROOT/f'data/processed/{file}.csv',rows)
        tables=['rfm_snapshot','rfm_keep_duplicates','rfm_exclude_extreme','customer_value','customer_comparison_population']
        for table in tables:
            path=ROOT/f'data/processed/{table}.parquet'
            con.execute("COPY "+table+" TO '"+str(path).replace("'","''")+"' (FORMAT PARQUET)")
            assert con.execute(f'SELECT count(*) FROM ((SELECT * FROM {table} EXCEPT ALL SELECT * FROM read_parquet(?)) UNION ALL (SELECT * FROM read_parquet(?) EXCEPT ALL SELECT * FROM {table}))',[str(path),str(path)]).fetchone()[0]==0
        summary={'steps':[11,12],'contract_version':spec['specification_version'],'parameters':params,'fact_orders_sha256':fingerprint.hexdigest(),
            'sql_sha256':{f:sha256(ROOT/'sql'/f) for f in ['05_rfm_segments.sql','06_customer_comparisons.sql']},
            'validation':{'all_primary_and_sensitivity_rfm_features_match_python':True,'tie_scores_and_segments_match_python':True,
                'trailing_year_money_reconciles':True,'historical_value_and_rank_reconcile':True,'every_90_day_value_matches_invoices':True,
                'first_order_features_frozen':True,'repeat_outcomes_match_invoices':True,'comparison_populations_exhaustive':True,'parquet_values_match_database':True},
            'table_counts':{t:con.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in tables},
            'concentration':concentration(primary),'rfm_segments':segments,'reactivation':reactivation,'sensitivity':sensitivity,
            'comparison_population':len(population),'basket_value_product_comparison':cross,'comparisons':comparison,'cohort_standardization':standardized,
            'fixed_window_value':{'customers':len(population),'median_sales_90d_gbp':median(r['customer_sales_90d'] for r in population),
                                  'mean_sales_90d_gbp':money_ratio(str(sum(r['customer_sales_90d'] for r in population)),str(len(population)))}}
    (ROOT/'reports/customer_analysis_summary.json').write_text(json.dumps(summary,indent=2,default=json_value)+'\n',encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ['table_counts','concentration','rfm_segments','sensitivity','comparisons','cohort_standardization']},indent=2,default=json_value))


if __name__=='__main__':main()
