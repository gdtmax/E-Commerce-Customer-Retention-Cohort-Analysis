"""Build, independently validate, export and report Step 7 monthly KPIs.

Run from any working directory: python src/monthly_kpis.py
Prerequisite: src/clean_data.py completed under the current metric contract.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext
import hashlib
import json
from pathlib import Path
import csv

import duckdb
from audit_data import json_value, sha256

ROOT = Path(__file__).resolve().parents[1]


def money_ratio(numerator, denominator):
    if numerator is None or denominator is None or Decimal(denominator)==0:
        return None
    with localcontext() as context:
        context.prec=50
        return format((Decimal(numerator)/Decimal(denominator)).quantize(Decimal('0.000001'),rounding=ROUND_HALF_UP),'f')


def build(con, history_start, cutoff):
    con.create_function('money_ratio',money_ratio,['VARCHAR','VARCHAR'],'VARCHAR',null_handling='special')
    sql=(ROOT/'sql/02_monthly_kpis.sql').read_text(encoding='utf-8')
    create,alter=sql.split('ALTER TABLE',1)
    con.execute(create,{'history_start':history_start,'cutoff':cutoff})
    con.execute('ALTER TABLE'+alter)


def get_rows(con):
    result=con.execute('SELECT * FROM monthly_kpis ORDER BY month')
    names=[d[0] for d in result.description]
    return [dict(zip(names,row)) for row in result.fetchall()]


def validate(con, rows, history_start, cutoff):
    """Independent Python aggregation from invoices; no reuse of customer features."""
    start=date.fromisoformat(history_start[:10]); end=date.fromisoformat(cutoff[:10])
    months=[]; month=start
    while month<end:
        months.append(month)
        month=date(month.year+(month.month==12),month.month%12+1,1)
    assert [r['month'] for r in rows]==months
    buckets=defaultdict(list); first={}
    invoices=con.execute('SELECT invoice_id,order_timestamp,customer_id,order_sales_gbp FROM fact_orders ORDER BY order_timestamp,invoice_id').fetchall()
    for invoice,stamp,customer,sales in invoices:
        assert start<=stamp.date()<end
        m=stamp.date().replace(day=1)
        buckets[m].append((invoice,customer,sales))
        if customer is not None:first.setdefault(customer,m)
    previous=None
    for row in rows:
        m=row['month']; orders=buckets[m]
        sales=sum((o[2] for o in orders),Decimal(0))
        identified=[o for o in orders if o[1] is not None]
        linked_sales=sum((o[2] for o in identified),Decimal(0))
        active={o[1] for o in identified}; new=sum(first[c]==m for c in active)
        expected={'orders':len(orders),'gross_merchandise_sales_gbp':sales,
                  'identified_orders':len(identified),'identified_sales_gbp':linked_sales,
                  'unidentified_orders':len(orders)-len(identified),'unidentified_sales_gbp':sales-linked_sales,
                  'active_customers':len(active),'new_observed_customers':new,'returning_customers':len(active)-new,
                  'previous_month_sales_gbp':previous,
                  'average_order_value_gbp':None if not orders else (sales/len(orders)).quantize(Decimal('0.000001'),rounding=ROUND_HALF_UP)}
        for key,value in expected.items():assert row[key]==value,(m,key,row[key],value)
        ratios={'returning_customer_share':None if not active else (len(active)-new)/len(active),
                'identified_order_share':None if not orders else len(identified)/len(orders),
                'identified_sales_share':None if not sales else float(linked_sales/sales),
                'sales_mom_growth':None if previous is None or previous==0 else float((sales-previous)/previous)}
        for key,value in ratios.items():
            assert (row[key] is None if value is None else row[key] is not None and abs(row[key]-value)<1e-12),(m,key)
        assert row['new_observed_customers']+row['returning_customers']==row['active_customers']
        previous=sales
    assert sum(r['orders'] for r in rows)==len(invoices)
    assert sum(r['new_observed_customers'] for r in rows)==len(first)
    assert sum(r['gross_merchandise_sales_gbp'] for r in rows)==sum((o[3] for o in invoices),Decimal(0))
    return {'calendar_complete':True,'all_monthly_counts_and_money_match_independent_python':True,
            'all_ratios_and_previous_calendar_month_match':True,'new_plus_returning_equals_active':True,
            'orders_and_sales_reconcile_to_invoices':True,'new_customers_reconcile_to_distinct_customers':True}


def display_money(value):
    if value is None:
        return 'N/A'
    return f"{Decimal(value).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP):,.2f}"


def percent(value):
    return 'N/A' if value is None else f'{value:.1%}'


def write_report(rows,summary):
    total=summary['totals']; peak=max(rows,key=lambda r:r['gross_merchandise_sales_gbp'])
    covered=[r for r in rows if r['identified_sales_share'] is not None]
    low=min(covered,key=lambda r:r['identified_sales_share']) if covered else None
    coverage_note=(f"Identified-sales coverage was lowest in **{low['month']:%Y-%m}: {percent(low['identified_sales_share'])}**."
                   if low else "Identified-sales coverage is undefined because no sales were observed.")
    monthly='\n'.join('| {} | {:,} | {} | {} | {:,} | {:,} | {:,} | {} | {} |'.format(
        r['month'].strftime('%Y-%m'),r['orders'],display_money(r['gross_merchandise_sales_gbp']),
        display_money(r['average_order_value_gbp']),r['active_customers'],r['new_observed_customers'],r['returning_customers'],
        percent(r['identified_sales_share']),percent(r['sales_mom_growth'])) for r in rows)
    text=f'''# Step 7 - Monthly Operating KPIs

**Status:** complete. **Scope:** eligible positive merchandise invoices from December 2009 through November 2011, GBP, contract 1.1. The partial December 2011 is excluded.

## Run and inspect

After the audit and cleaning commands in the [README](../README.md), run `python src/monthly_kpis.py`. This executes [02_monthly_kpis.sql](../sql/02_monthly_kpis.sql), validates every month against independent Python invoice aggregation, and replaces the DuckDB `monthly_kpis` table. It exports `data/processed/monthly_kpis.parquet`, the small tracked [monthly CSV](../data/processed/monthly_kpis.csv), [validation summary](monthly_kpis_summary.json), and the chart below. SQL uses a registered Decimal division helper for AOV and should be executed through the runner.

The runner verifies the raw workbook and product-mapping hashes against the cleaning summary, checks cleaned counts and totals, and records an input-table fingerprint. Rebuild cleaning first after changing its inputs or rules. If export is interrupted after database commit, rerun this command to refresh all outputs. Other analysis tables are not refreshed by this command.

## Definitions

- **Orders:** distinct eligible invoices, including unidentified invoices. Sum invoice totals once; never multiply header totals by joined item rows.
- **Gross merchandise sales:** sum of eligible positive merchandise sales, before credit adjustments. This does not establish net revenue, profit or settled cash.
- **AOV:** sales divided by orders. Exact Decimal sums feed Decimal division; the stored ratio is half-up rounded to six decimals and displayed to two. Counts and money totals retain their exact values.
- **Active customers:** distinct identified purchasing accounts in a month. **New observed:** first eligible purchase falls in that month. **Returning:** first purchase was earlier. Several purchases in a customer's first month still count as one new customer.
- **Returning-customer share:** returning / active customers; this is customer composition, not a retention rate.
- **Identification coverage:** identified orders / all orders and identified sales / all sales. Unidentified transactions contribute to overall sales but do not create a customer identity.
- **Sales MoM growth:** sales / previous calendar month's sales minus one. The first month and a zero previous-sales denominator yield null. Growth ratios and shares use floating point; money totals use Decimal.
- A calendar spine retains all reporting months. An empty observed month gets zero counts/sales and null zero-denominator ratios. Monthly active customers cannot be summed to obtain unique customers over the whole period.

## Reconciled period totals

| Measure | Result |
|---|---:|
| Complete reporting months | {len(rows)} |
| Eligible invoices | {total['orders']:,} |
| Gross merchandise sales (GBP) | {display_money(total['gross_merchandise_sales_gbp'])} |
| Period AOV, total sales / total orders (GBP) | {display_money(total['average_order_value_gbp'])} |
| Distinct identified customers | {total['distinct_customers']:,} |
| Identified-order coverage | {percent(total['identified_order_share'])} |
| Identified-sales coverage | {percent(total['identified_sales_share'])} |

Period AOV and coverage use period numerators and denominators, not an unweighted average of monthly percentages. Exact six-decimal money is retained in the CSV/JSON and database.

## Monthly results

| Month | Orders | Gross sales GBP | AOV GBP | Active customers | New observed | Returning | Identified sales | Sales MoM |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{monthly}

The CSV also includes identified/unidentified order and sales amounts, previous-month sales, returning-customer share and identified-order share.

![Monthly operating indicators](../images/monthly_kpis.png)

## Observations and interpretation limits

- The highest observed monthly gross sales were **{display_money(peak['gross_merchandise_sales_gbp'])} GBP in {peak['month']:%Y-%m}**, with **{peak['orders']:,} invoices**. This ranks the available months and does not establish why sales changed.
- {coverage_note} Customer behavior results cover identified transactions and may not represent unidentified buyers.
- December 2009 is the beginning of observed history. Its buyers are classified as first observed, even if they bought before the extract. Changes in new/returning composition therefore partly reflect accumulated observation history.
- The Step 6 exclusions remain in force: unresolved manual/sample/image exposure was GBP 338,725.57, and conflicting invoice headers were quarantined. Missing IDs, wholesale orders, source date gaps and unverified refund linkage limit interpretation. Invoice 541431 remains in January 2011 under the documented gross-purchase policy; its GBP 77,183.60 value can affect that month's AOV.

## Verification and next step

All 24 monthly rows matched independent Python aggregation from the cleaned invoices, including exact sales, customer composition, coverage ratios and prior-calendar-month growth. Period counts and money reconcile to Step 6. Synthetic cases cover an empty month, repeated purchases by a new customer, a returning customer, unidentified-only activity, zero denominators and exclusion of the cutoff month. CSV and Parquet outputs were checked against the database.

For completed downstream findings, see [repeat purchasing and cohorts](retention_analysis.md), [customer segments](customer_value_and_segments.md), and the [final case study](case_study.md).
'''
    (ROOT/'reports/monthly_kpis_report.md').write_text(text,encoding='utf-8')


def draw_chart(rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    dates=[r['month'] for r in rows]
    fig,axes=plt.subplots(3,1,figsize=(11,9),sharex=True,layout='constrained')
    axes[0].plot(dates,[float(r['gross_merchandise_sales_gbp'])/1000 for r in rows],color='#146C94',marker='o',markersize=3)
    axes[0].set_ylabel('Gross sales (GBP thousands)')
    axes[1].plot(dates,[r['new_observed_customers'] for r in rows],label='New observed',color='#146C94')
    axes[1].plot(dates,[r['returning_customers'] for r in rows],label='Returning',color='#C46B27')
    axes[1].set_ylabel('Purchasing customers');axes[1].legend(loc='upper left',ncol=2)
    axes[2].plot(dates,[float('nan') if r['identified_sales_share'] is None else 100*r['identified_sales_share'] for r in rows],label='Identified sales',color='#146C94')
    axes[2].plot(dates,[float('nan') if r['identified_order_share'] is None else 100*r['identified_order_share'] for r in rows],label='Identified orders',color='#65823C')
    axes[2].set_ylabel('Identification coverage (%)');axes[2].set_ylim(0,105);axes[2].legend(loc='lower left',ncol=2)
    axes[2].xaxis.set_major_locator(mdates.MonthLocator(interval=3));axes[2].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    for ax in axes:ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Monthly operating KPIs | UCI Online Retail II\nEligible merchandise purchases, Dec 2009-Nov 2011',fontsize=14)
    fig.savefig(ROOT/'images/monthly_kpis.png',dpi=160);plt.close(fig)


def main():
    spec=json.loads((ROOT/'src/metric_spec.json').read_text(encoding="utf-8"))
    clean=json.loads((ROOT/'reports/cleaning_summary.json').read_text(encoding="utf-8"))
    assert spec['specification_version']==clean['contract_version']
    assert sha256(ROOT/'data/raw/online_retail_II.xlsx')==clean['source_sha256']
    assert sha256(ROOT/'src/product_roles.csv')==clean['product_mapping_sha256']
    with duckdb.connect(str(ROOT/'data/processed/retention.duckdb')) as con:
        for table in ['fact_orders','customer_features']:
            assert con.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==clean['results']['table_counts'][table]
        expected=sum(Decimal(r['gross_merchandise_sales_gbp']) for r in clean['results']['coverage'])
        assert con.execute('SELECT sum(order_sales_gbp) FROM fact_orders').fetchone()[0]==expected
        con.execute('BEGIN TRANSACTION')
        try:
            build(con,spec['history_start_inclusive'],spec['analysis_cutoff_exclusive'])
            rows=get_rows(con)
            checks=validate(con,rows,spec['history_start_inclusive'],spec['analysis_cutoff_exclusive'])
            con.execute('COMMIT')
        except Exception:
            con.execute('ROLLBACK');raise
        fingerprint=hashlib.sha256()
        for table,order in [('fact_orders','invoice_id'),('customer_features','customer_id')]:
            for row in con.execute(f'SELECT * FROM {table} ORDER BY {order}').fetchall():
                fingerprint.update((json.dumps(row,default=json_value)+'\n').encode())
        target=str(ROOT/'data/processed/monthly_kpis.parquet').replace("'","''")
        con.execute(f"COPY (SELECT * FROM monthly_kpis ORDER BY month) TO '{target}' (FORMAT PARQUET)")
        assert con.execute('SELECT * FROM read_parquet(?) ORDER BY month',[str(ROOT/'data/processed/monthly_kpis.parquet')]).fetchall()==con.execute('SELECT * FROM monthly_kpis ORDER BY month').fetchall()
        checks['parquet_matches_database']=True
    with (ROOT/'data/processed/monthly_kpis.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    orders=sum(r['orders'] for r in rows);sales=sum(r['gross_merchandise_sales_gbp'] for r in rows)
    totals={'orders':orders,'gross_merchandise_sales_gbp':sales,'average_order_value_gbp':money_ratio(str(sales),str(orders)),
            'distinct_customers':sum(r['new_observed_customers'] for r in rows),
            'identified_order_share':sum(r['identified_orders'] for r in rows)/orders,
            'identified_sales_share':float(sum(r['identified_sales_gbp'] for r in rows)/sales)}
    summary={'step':7,'contract_version':spec['specification_version'],'reporting_months':len(rows),
             'source_sha256':clean['source_sha256'],'input_tables_sha256':fingerprint.hexdigest(),
             'sql_sha256':sha256(ROOT/'sql/02_monthly_kpis.sql'),'validation':checks,'totals':totals}
    (ROOT/'reports/monthly_kpis_summary.json').write_text(json.dumps(summary,indent=2,default=json_value)+'\n',encoding='utf-8')
    draw_chart(rows);write_report(rows,summary)
    print(json.dumps(summary,indent=2,default=json_value))
    print('Step 7 complete: database, Parquet, CSV, report, validation summary and chart updated.')


if __name__=='__main__':main()
