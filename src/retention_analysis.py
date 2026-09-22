"""Steps 8-9: build and independently verify repeat-purchase/cohort tables."""
from collections import defaultdict
from datetime import datetime,timedelta,date
from decimal import Decimal
import csv
import hashlib
import json
from pathlib import Path
import re
from statistics import median
import duckdb
from audit_data import sha256,json_value

ROOT=Path(__file__).resolve().parents[1]
TABLES=['customer_purchase_history','customer_repeat_windows','repeat_purchase_summary','cohort_retention','cohort_retention_pooled']


def records(con,query):
    cur=con.execute(query);names=[x[0] for x in cur.description]
    return [dict(zip(names,row)) for row in cur.fetchall()]


def build(con,params):
    for file in ['03_customer_behavior.sql','04_cohort_retention.sql']:
        for statement in (ROOT/'sql'/file).read_text(encoding='utf-8').split(';'):
            if not statement.strip():continue
            names=set(re.findall(r'\$([a-z_]+)',statement))
            con.execute(statement,{k:params[k] for k in names}) if names else con.execute(statement)


def month_add(month,index):
    n=month.year*12+month.month-1+index
    return date(n//12,n%12+1,1)


def validate(con,params):
    """Reconstruct all purchase windows and cohort cells from invoice-level rows."""
    H,T,C=(datetime.fromisoformat(params[k]) for k in ['history_start','cutoff','cohort_start'])
    histories=defaultdict(list)
    for invoice,customer,stamp in con.execute('SELECT invoice_id,customer_id,order_timestamp FROM fact_orders ORDER BY order_timestamp,invoice_id').fetchall():
        if customer is not None and H<=stamp<T:histories[customer].append((stamp,invoice))
    sql_history=records(con,'SELECT * FROM customer_purchase_history')
    assert len(sql_history)==sum(map(len,histories.values()))
    for row in sql_history:
        h=histories[row['customer_id']];i=row['purchase_sequence']-1
        assert (row['order_timestamp'],row['invoice_id'])==h[i]
        previous=None if i==0 else h[i-1][0]
        assert row['previous_order_timestamp']==previous
        assert row['days_since_previous_order']==(None if previous is None else (h[i][0]-previous).total_seconds()/86400)
    windows=records(con,'SELECT * FROM customer_repeat_windows')
    assert len(windows)==3*len(histories)
    expected={}
    for row in windows:
        h=histories[row['customer_id']];first=h[0][0];second=h[1][0] if len(h)>1 else None
        nxt=next((x[0] for x in h if x[0]>first),None)
        d=row['window_days'];end=first+timedelta(days=d);eligible=end<T;common=first+timedelta(days=90)<T
        repeat=second is not None and second<=end;collapsed=nxt is not None and nxt<=end
        values={'first_order_timestamp':first,'second_order_timestamp':second,'next_distinct_timestamp':nxt,
                'historical_order_count':len(h),'cohort_month':first.date().replace(day=1),'is_primary_cohort':first>=C,
                'window_end':end,'eligible_window':eligible,'eligible_common_90d':common,
                'repeated_window':eligible and repeat,'repeated_common_90d':common and repeat,
                'repeated_collapsed_timestamp':eligible and collapsed,'repeated_collapsed_common_90d':common and collapsed,
                'days_to_second_order':None if second is None else (second-first).total_seconds()/86400}
        for k,v in values.items():assert row[k]==v,(row['customer_id'],d,k)
        expected[(row['customer_id'],d)]=values
    summaries=records(con,'SELECT * FROM repeat_purchase_summary ORDER BY population,window_days')
    for row in summaries:
        own=row['population']=='own_window';ek='eligible_window' if own else 'eligible_common_90d'
        rk='repeated_window' if own else 'repeated_common_90d';sk='repeated_collapsed_timestamp' if own else 'repeated_collapsed_common_90d'
        pop=[v for (c,d),v in expected.items() if d==row['window_days'] and v['is_primary_cohort']]
        n=sum(v[ek] for v in pop);x=sum(v[rk] for v in pop);y=sum(v[sk] for v in pop)
        assert (row['primary_customers'],row['eligible_customers'],row['incomplete_window_customers'],row['repeat_customers'],row['repeat_customers_collapsed_timestamp'])==(len(pop),n,len(pop)-n,x,y)
        assert row['repeat_purchase_rate']==(x/n if n else None)
        assert row['collapsed_timestamp_repeat_rate']==(y/n if n else None)
    common=[r for r in summaries if r['population']=='common_90_day']
    assert len({r['eligible_customers'] for r in common})<=1
    assert [r['repeat_customers'] for r in common]==sorted(r['repeat_customers'] for r in common)
    groups=defaultdict(set);active=defaultdict(set)
    for customer,h in histories.items():
        cohort=h[0][0].date().replace(day=1);groups[cohort].add(customer)
        for stamp,_ in h:active[(cohort,stamp.date().replace(day=1))].add(customer)
    cells=records(con,'SELECT * FROM cohort_retention')
    nmonths=(T.year-H.year)*12+T.month-H.month
    assert len(cells)==nmonths*nmonths
    for row in cells:
        cohort=row['cohort_month'];target=month_add(cohort,row['month_index']);observed=month_add(target,1)<=T.date()
        n=len(groups[cohort]);x=len(active[(cohort,target)]) if observed else None
        assert row['activity_month']==target and row['is_observable']==observed
        assert row['is_primary_cohort']==(cohort>=C.date()) and row['cohort_size']==n
        assert row['retained_customers']==x
        assert row['retention_rate']==(x/n if observed and n else None)
        if row['month_index']==0:assert x==n
    for row in records(con,'SELECT * FROM cohort_retention_pooled'):
        selected=[x for x in cells if x['month_index']==row['month_index'] and x['is_primary_cohort'] and x['is_observable']]
        n=sum(x['cohort_size'] for x in selected);x=sum(x['retained_customers'] for x in selected)
        assert row['eligible_customers']==n and row['retained_customers']==x
        assert row['mature_cohorts']==sum(x['cohort_size']>0 for x in selected)
        assert row['retention_rate']==(x/n if n else None)
    return {'invoice_sequences_and_interpurchase_gaps':True,'every_customer_window_matches_python':True,
            'repeat_denominators_and_timestamp_sensitivity':True,'common_population_counts_nondecreasing':True,
            'every_cohort_cell_matches_invoice_sets':True,'month_zero_and_future_nulls':True,
            'maturity_weighted_pooled_rates':True}


def pct(x):return 'N/A' if x is None else f'{x:.2%}'


def report(summary):
    r=summary['repeat_purchase'];p=summary['pooled_cohorts'];d=summary['description']
    table='\n'.join(f"| {x['population']} | {x['window_days']} | {x['eligible_customers']:,} | {x['incomplete_window_customers']:,} | {x['repeat_customers']:,} | {pct(x['repeat_purchase_rate'])} | {pct(x['collapsed_timestamp_repeat_rate'])} |" for x in r)
    pooled='\n'.join(f"| {x['month_index']} | {x['mature_cohorts']} | {x['eligible_customers']:,} | {x['retained_customers']:,} | {pct(x['retention_rate'])} |" for x in p if x['month_index'] in [0,1,2,3,6,12,18,20,21,23])
    text=f'''# Steps 8-9 - Repeat Purchasing and Cohort Retention

**Status:** both steps complete under metric contract 1.1. Source: historical UK Online Retail II; eligible identified purchase invoices before 2011-12-01. Main first-observed cohorts begin 2010-03-01. Full history from 2009-12-01 is retained to establish first purchases.

## Reproduce and outputs

After the documented cleaning stage, run `python src/retention_analysis.py` from the project root. It executes [customer behavior SQL](../sql/03_customer_behavior.sql) and [cohort SQL](../sql/04_cohort_retention.sql), validates results against independent Python invoice histories, and rebuilds five tables in a single transaction. Failed validation rolls back the rebuild. Parquet exports follow commit; rerun after an interrupted export. Rebuild after cleaning changes. Input and SQL fingerprints are in [the validation summary](retention_summary.json).

The tables are `customer_purchase_history` (one identified invoice), `customer_repeat_windows` (one customer/window), `repeat_purchase_summary` (one population/window), `cohort_retention` (one cohort/month index), and `cohort_retention_pooled` (one month index). All have primary keys and matching local Parquet exports. Tracked aggregate CSVs: [repeat rates](../data/processed/repeat_purchase_summary.csv), [cohort cells](../data/processed/cohort_retention.csv), [pooled cohorts](../data/processed/cohort_retention_pooled.csv), and [primary cohort matrix](../data/processed/cohort_retention_matrix.csv). Customer-level outputs stay in ignored processed data.

## Step 8: behavior and fixed-window repeats

There are **{d['identified_invoices']:,} identified invoices** belonging to **{d['customers']:,} customers**. Across unequal full observed histories, **{d['one_purchase_customers']:,} customers have one purchase** and **{d['multiple_purchase_customers']:,} have at least two**. These counts are descriptive; they are not a comparable fixed-window rate. **{d['primary_customers']:,} customers** fall in the main first-observed cohort scope; **{d['initial_history_customers']:,} earlier customers** remain in history but are excluded from headline repeat denominators.

For D days, eligibility requires `first purchase + D days < cutoff`. A second distinct invoice at or before that inclusive window end counts. Incomplete windows are excluded from both numerator and denominator, even if a second purchase is already observed. Dates use source timestamps; no day rounding is used for eligibility. Two different invoices at the same timestamp count in the primary definition.

| Population | Days | Eligible customers | Incomplete windows | Repeated | Repeat rate | Rate collapsing equal timestamps |
|---|---:|---:|---:|---:|---:|---:|
{table}

`own_window` allows each duration its own mature population. `common_90_day` uses the same 90-day-mature customers for 30/60/90-day comparisons; its repeat counts must be nondecreasing. Neither population includes the initial-history cohorts. The last column collapses same-customer/same-timestamp invoices into one occasion, then looks for the next later timestamp; it keeps the same denominators. It is a sensitivity calculation, not a change to the primary definition.

Among the **{d['repeaters_within_90_days']:,}** primary customers who repeated within 90 days and had a complete 90-day window, the **conditional median time to second invoice is {format(d['conditional_median_days_to_second'], '.2f') if d['conditional_median_days_to_second'] is not None else 'N/A'} days**. Their corresponding 90-day repeat rate is **{pct(d['repeat_rate_90d'])}**. This median describes those repeaters only; nonrepeaters are not assigned zero or 90 days. Same-timestamp repeats may contribute zero-day intervals.

## Step 9: calendar-month cohort retention

The complete table contains **{summary['table_counts']['cohort_retention']:,} cells**, covering all 24 first-purchase calendar months and month indices 0-23. The main matrix contains the 21 cohorts from March 2010 onward. Earlier cohorts are retained in the long table with `is_primary_cohort=false`.

Each customer contributes once per activity month, regardless of invoice count. Month 0 equals cohort size and has 100% retention for nonempty cohorts. A cell is observable only when its target month's end-exclusive boundary is at or before the cutoff. Observable months without purchases are zero; future counts and rates are null. Empty cohort rates are also null. Blank CSV matrix cells represent undefined/unobserved rates, not zero retention. See the long table's observation flag and cohort size to distinguish them.

Selected pooled results below sum retained customers and cohort sizes over **mature primary cohorts only**. This avoids averaging percentages or treating immature cohorts as failures. Each month index can have a different contributing cohort population.

| Month index | Mature nonempty cohorts | Eligible customers | Retained | Pooled purchasing retention |
|---|---:|---:|---:|---:|
{pooled}

Month 1 measures a purchase in the next calendar month and is different from a repeat within 30 elapsed days. Monthly purchasing retention is not continuous survival: a customer may skip a month and return, so cohort rates need not fall monotonically.

## Limits, verification and next step

Both analyses use identified accounts and first observed purchases, not verified new people. Missing identity, quarantined headers, unresolved manual/sample/image entries, the gross-purchase/credit policy and source trading-date gaps remain relevant. Apparent differences across cohorts are descriptive and may reflect changing acquisition mix, seasonality or coverage. No causal campaign effect or business improvement is established.

Every customer-window flag and every cohort cell was checked against independent Python histories built directly from invoices. Sequence/gap checks, denominator checks, common-population monotonicity, same-timestamp sensitivity, Month 0, future nulls and maturity-weighted pooling passed. Synthetic SQL cases checked exact window boundaries, a window ending at the cutoff, incomplete-window repeaters, an empty cohort, an observed zero-purchase cell, and a skipped month followed by return. CSV and Parquet exports were reconciled to database rows.

For completed downstream work, see [cohort visualization](cohort_visualization.md), [RFM and customer comparisons](customer_value_and_segments.md), and the [final case study](case_study.md).
'''
    (ROOT/'reports/retention_analysis.md').write_text(text,encoding='utf-8')


def main():
    spec=json.loads((ROOT/'src/metric_spec.json').read_text(encoding="utf-8"));clean=json.loads((ROOT/'reports/cleaning_summary.json').read_text(encoding="utf-8"))
    assert spec['specification_version']==clean['contract_version']
    assert sha256(ROOT/'data/raw/online_retail_II.xlsx')==clean['source_sha256']
    assert sha256(ROOT/'src/product_roles.csv')==clean['product_mapping_sha256']
    params={'history_start':spec['history_start_inclusive'],'cutoff':spec['analysis_cutoff_exclusive'],'cohort_start':spec['primary_cohort_start_inclusive']}
    assert spec['repeat_purchase']['primary_windows_days']==[30,60,90]
    assert spec['repeat_purchase']['common_population_window_days']==90
    with duckdb.connect(str(ROOT/'data/processed/retention.duckdb')) as con:
        assert con.execute('SELECT count(*) FROM fact_orders').fetchone()[0]==clean['results']['table_counts']['fact_orders']
        assert con.execute('SELECT sum(order_sales_gbp) FROM fact_orders').fetchone()[0]==sum(Decimal(x['gross_merchandise_sales_gbp']) for x in clean['results']['coverage'])
        con.execute('BEGIN TRANSACTION')
        try:
            build(con,params);checks=validate(con,params);con.execute('COMMIT')
        except Exception:con.execute('ROLLBACK');raise
        fingerprint=hashlib.sha256()
        for row in con.execute('SELECT * FROM fact_orders ORDER BY invoice_id').fetchall():fingerprint.update((json.dumps(row,default=json_value)+'\n').encode())
        for table in TABLES:
            path=ROOT/f'data/processed/{table}.parquet'
            con.execute("COPY (SELECT * FROM "+table+") TO '"+str(path).replace("'","''")+"' (FORMAT PARQUET)")
            assert con.execute(f'SELECT count(*) FROM ((SELECT * FROM {table} EXCEPT ALL SELECT * FROM read_parquet(?)) UNION ALL (SELECT * FROM read_parquet(?) EXCEPT ALL SELECT * FROM {table}))',[str(path),str(path)]).fetchone()[0]==0
        for table in TABLES[2:]:
            rows=records(con,f'SELECT * FROM {table} ORDER BY '+('population,window_days' if table=='repeat_purchase_summary' else 'cohort_month,month_index' if table=='cohort_retention' else 'month_index'))
            with (ROOT/f'data/processed/{table}.csv').open('w',encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
        cells=records(con,'SELECT * FROM cohort_retention WHERE is_primary_cohort ORDER BY cohort_month,month_index')
        matrix={}
        for row in cells:
            entry=matrix.setdefault(row['cohort_month'],{'cohort_month':row['cohort_month'],'cohort_size':row['cohort_size']})
            entry[f"month_{row['month_index']}"]=row['retention_rate']
        with (ROOT/'data/processed/cohort_retention_matrix.csv').open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=next(iter(matrix.values())));w.writeheader();w.writerows(matrix.values())
        counts={t:con.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in TABLES}
        desc=records(con,"""SELECT count(*) customers,count(*) FILTER(WHERE historical_order_count=1) one_purchase_customers,
            count(*) FILTER(WHERE historical_order_count>=2) multiple_purchase_customers,
            count(*) FILTER(WHERE is_primary_cohort) primary_customers,
            count(*) FILTER(WHERE NOT is_primary_cohort) initial_history_customers
            FROM customer_repeat_windows WHERE window_days=90""")[0]
        times=[row[0] for row in con.execute('SELECT days_to_second_order FROM customer_repeat_windows WHERE window_days=90 AND is_primary_cohort AND repeated_window').fetchall()]
        desc.update(identified_invoices=counts['customer_purchase_history'],repeaters_within_90_days=len(times),conditional_median_days_to_second=median(times) if times else None,
                    repeat_rate_90d=con.execute("SELECT repeat_purchase_rate FROM repeat_purchase_summary WHERE population='own_window' AND window_days=90").fetchone()[0])
        checks['all_parquet_values_match_database']=True
        summary={'steps':[8,9],'contract_version':spec['specification_version'],'parameters':params,'source_sha256':clean['source_sha256'],
                 'fact_orders_sha256':fingerprint.hexdigest(),'sql_sha256':{f:sha256(ROOT/'sql'/f) for f in ['03_customer_behavior.sql','04_cohort_retention.sql']},
                 'validation':checks,'table_counts':counts,'description':desc,
                 'repeat_purchase':records(con,'SELECT * FROM repeat_purchase_summary ORDER BY population,window_days'),
                 'pooled_cohorts':records(con,'SELECT * FROM cohort_retention_pooled ORDER BY month_index')}
    (ROOT/'reports/retention_summary.json').write_text(json.dumps(summary,indent=2,default=json_value)+'\n',encoding='utf-8')
    report(summary)
    print(json.dumps({'tables':counts,'description':desc,'repeat_purchase':summary['repeat_purchase'],'validation':checks},indent=2,default=json_value))


if __name__=='__main__':main()
