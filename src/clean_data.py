"""Step 6: rebuild traceable analytical tables under metric contract 1.1.

Run python src/audit_data.py first, then python src/clean_data.py.
The reviewed product_roles.csv is a versioned input, not inferred afresh per run.
"""
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import re
import duckdb
from audit_data import prepare_audit, json_value, sha256

ROOT = Path(__file__).resolve().parents[1]
TABLES = ['stg_order_lines', 'fact_order_lines', 'fact_orders', 'customer_features', 'customer_month_activity']


def records(con, sql):
    cursor = con.execute(sql)
    return [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]


def validate(con, expected_rows, history_start, cutoff):
    """Fail before committing if grain, scope, lineage or money reconciliations fail."""
    checks = {
        'all_source_rows_preserved': con.execute('SELECT count(*) FROM stg_order_lines').fetchone()[0] == expected_rows,
        'raw_values_preserved': con.execute('''SELECT count(*) FROM (
            (SELECT * FROM raw_order_lines EXCEPT SELECT source_sheet,source_row_number,source_workbook_sha256,
            raw_invoice,raw_stock_code,raw_description,raw_quantity,raw_invoice_date,raw_price,raw_customer_id,raw_country FROM stg_order_lines)
            UNION ALL
            (SELECT source_sheet,source_row_number,source_workbook_sha256,raw_invoice,raw_stock_code,raw_description,
            raw_quantity,raw_invoice_date,raw_price,raw_customer_id,raw_country FROM stg_order_lines EXCEPT SELECT * FROM raw_order_lines))''').fetchone()[0] == 0,
        'one_product_mapping_per_code': con.execute('SELECT count(*) FROM (SELECT DISTINCT stock_code FROM stg_order_lines EXCEPT SELECT stock_code FROM product_roles)').fetchone()[0] == 0,
        'positive_merchandise_only': con.execute("SELECT count(*) FROM stg_order_lines WHERE is_eligible_purchase_line AND (product_role<>'merchandise' OR quantity<=0 OR unit_price_gbp<=0 OR header_conflict OR NOT regexp_full_match(invoice_id,'[0-9]+'))").fetchone()[0] == 0,
        'complete_reporting_window': con.execute('SELECT count(*) FROM fact_orders WHERE order_timestamp<? OR order_timestamp>=?', [history_start,cutoff]).fetchone()[0] == 0,
        'no_orphan_lines': con.execute('SELECT count(*) FROM fact_order_lines l LEFT JOIN fact_orders o USING(invoice_id) WHERE o.invoice_id IS NULL').fetchone()[0] == 0,
        'line_order_money_reconciles': con.execute('SELECT (SELECT sum(line_sales_gbp) FROM fact_order_lines)=(SELECT sum(order_sales_gbp) FROM fact_orders)').fetchone()[0],
        'customer_money_reconciles': con.execute('SELECT (SELECT sum(historical_sales_gbp) FROM customer_features)=(SELECT sum(order_sales_gbp) FROM fact_orders WHERE is_identified)').fetchone()[0],
        'customer_order_counts_reconcile': con.execute('SELECT (SELECT sum(historical_order_count) FROM customer_features)=(SELECT count(*) FROM fact_orders WHERE is_identified)').fetchone()[0],
        'customer_order_sequence_contiguous': con.execute('SELECT count(*) FROM (SELECT customer_id FROM fact_orders WHERE is_identified GROUP BY customer_id HAVING min(customer_order_sequence)<>1 OR max(customer_order_sequence)<>count(*))').fetchone()[0] == 0,
        'first_order_not_backfilled': con.execute('''SELECT count(*) FROM customer_features c JOIN fact_orders o ON c.first_order_id=o.invoice_id
            WHERE c.first_order_country IS DISTINCT FROM o.invoice_country OR c.first_order_sales_gbp<>o.order_sales_gbp
            OR c.first_order_timestamp<>o.order_timestamp OR o.customer_order_sequence<>1''').fetchone()[0] == 0,
        'activity_matches_orders': con.execute('''SELECT count(*) FROM (
            (SELECT customer_id,activity_month FROM customer_month_activity EXCEPT SELECT customer_id,order_month FROM fact_orders WHERE is_identified)
            UNION ALL (SELECT customer_id,order_month FROM fact_orders WHERE is_identified EXCEPT SELECT customer_id,activity_month FROM customer_month_activity))''').fetchone()[0] == 0,
        'unknown_customers_not_invented': con.execute("SELECT count(*) FROM fact_orders WHERE is_identified IS DISTINCT FROM (customer_id IS NOT NULL)").fetchone()[0] == 0,
        'same_sheet_sensitivity_superset': con.execute('SELECT (SELECT count(*) FROM sensitivity_order_lines_keep_duplicates)>=(SELECT count(*) FROM fact_order_lines)').fetchone()[0],
    }
    if not all(checks.values()):
        raise AssertionError({k:v for k,v in checks.items() if not v})
    return checks


def main():
    spec = json.loads((ROOT/'src/metric_spec.json').read_text(encoding="utf-8"))
    assert spec['specification_version']=='1.1', 'Cleaning requires contract 1.1.'
    assert spec['purchase_scope']['price_normalization']['maximum_absolute_deviation_gbp']=='0.000000001'
    manifest = json.loads((ROOT/'data/raw/source_manifest.json').read_text(encoding="utf-8"))
    raw = ROOT/manifest['local_workbook']
    assert sha256(raw)==manifest['workbook_sha256'], 'Raw source changed.'
    db=ROOT/'data/processed/retention.duckdb'
    assert db.exists(), 'Run src/audit_data.py first.'
    with duckdb.connect(str(db)) as con:
        con.execute('SET threads=4')
        assert con.execute('SELECT count(*) FROM raw_order_lines').fetchone()[0]==manifest['raw_row_count']
        assert con.execute('SELECT DISTINCT source_workbook_sha256 FROM raw_order_lines').fetchall()==[(manifest['workbook_sha256'],)]
        sections=dict(prepare_audit(con))
        # Step 5 remains a strict historical audit. Step 6 recomputes multiset
        # comparisons after the explicitly accepted price normalization.
        setup=sections['setup'].replace('CAST(audit_price(raw_price)', 'CAST(audit_review_price(raw_price)')
        con.execute(setup)
        print('Normalized source and recomputed invoice payload comparisons.',flush=True)
        params={'roles':str(ROOT/'src/product_roles.csv'), 'cohort_start':spec['primary_cohort_start_inclusive'], 'cutoff':spec['analysis_cutoff_exclusive']}
        con.execute('BEGIN TRANSACTION')
        try:
            sql=(ROOT/'sql/01b_clean_data.sql').read_text(encoding="utf-8")
            for statement in sql.split(';'):
                if not statement.strip(): continue
                names=set(re.findall(r'\$([a-z_]+)',statement))
                con.execute(statement,{k:params[k] for k in names}) if names else con.execute(statement)
            role_values=con.execute("SELECT count(*) FROM product_roles WHERE product_role NOT IN ('merchandise','non_merchandise','unresolved') OR product_role IS NULL").fetchone()[0]
            assert role_values==0
            checks=validate(con,manifest['raw_row_count'],spec['history_start_inclusive'],spec['analysis_cutoff_exclusive'])
            con.execute('COMMIT')
        except Exception:
            con.execute('ROLLBACK')
            raise
        print('Built analytical tables; all validation gates passed.',flush=True)
        results={
            'table_counts':{table:con.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in TABLES},
            'waterfall':records(con,"SELECT primary_disposition,count(*) AS rows,sum(candidate_positive_gbp) candidate_positive_gbp FROM stg_order_lines GROUP BY primary_disposition ORDER BY primary_disposition"),
            'overlapping_reasons':records(con,'SELECT reason,count(*) AS rows FROM stg_order_lines,unnest(exclusion_reasons) t(reason) GROUP BY reason ORDER BY reason'),
            'product_roles':records(con,'SELECT product_role,count(*) codes FROM product_roles GROUP BY product_role ORDER BY product_role'),
            'unresolved_exposure':records(con,"""SELECT stock_code,count(*) AS rows,sum(candidate_positive_gbp) candidate_positive_gbp FROM stg_order_lines
                WHERE product_role='unresolved' AND len(list_filter(exclusion_reasons,x -> x<>'unresolved_product'))=0
                GROUP BY stock_code ORDER BY candidate_positive_gbp DESC"""),
            'coverage':records(con,'SELECT is_identified,count(*) orders,sum(order_sales_gbp) gross_merchandise_sales_gbp FROM fact_orders GROUP BY is_identified ORDER BY is_identified'),
            'normalization':records(con,'SELECT price_precision_status,count(*) AS rows,count(*) FILTER(WHERE is_eligible_purchase_line) eligible_rows FROM stg_order_lines GROUP BY price_precision_status'),
            'duplicates_sensitivity':records(con,"""SELECT 'primary' scenario,count(*) orders,sum(order_sales_gbp) sales_gbp FROM fact_orders
                UNION ALL SELECT 'keep_within_sheet_duplicates',count(*),sum(order_sales_gbp) FROM sensitivity_orders_keep_duplicates"""),
            'same_timestamp_sensitivity':records(con,"""SELECT (SELECT count(*) FROM fact_orders WHERE is_identified) identified_invoices,
                (SELECT count(*) FROM (SELECT DISTINCT customer_id,order_timestamp FROM fact_orders WHERE is_identified)) distinct_customer_timestamp_occasions"""),
            'extreme_purchase_sensitivity':records(con,"""SELECT 'retain_all_eligible' scenario,count(*) orders,sum(order_sales_gbp) sales_gbp FROM fact_orders
                UNION ALL SELECT 'exclude_541431_for_sensitivity_only',count(*),sum(order_sales_gbp) FROM fact_orders WHERE invoice_id<>'541431'"""),
            'header_quarantine':records(con,"SELECT count(DISTINCT (source_sheet,invoice_id)) invoice_versions,count(*) AS rows FROM stg_order_lines WHERE header_conflict"),
        }
        for row in results['duplicates_sensitivity']:
            row['aov_gbp']=(row['sales_gbp']/Decimal(row['orders'])).quantize(Decimal('0.000001'),rounding=ROUND_HALF_UP)
        assert sum(row['rows'] for row in results['waterfall'])==manifest['raw_row_count']
        for table in TABLES:
            target=str(ROOT/f'data/processed/{table}.parquet').replace("'","''")
            con.execute(f"COPY {table} TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        for key,query in [('cleaning_exclusion_waterfall','SELECT primary_disposition,count(*) AS rows,sum(candidate_positive_gbp) candidate_positive_gbp FROM stg_order_lines GROUP BY 1'),
                          ('cleaning_quarantined_invoices','SELECT source_sheet,invoice_id,count(*) AS rows FROM stg_order_lines WHERE header_conflict GROUP BY 1,2')]:
            target=str(ROOT/f'data/processed/{key}.csv').replace("'","''")
            con.execute(f"COPY ({query}) TO '{target}' (HEADER,DELIMITER ',')")
    assert sha256(raw)==manifest['workbook_sha256']
    out={'step':6,'contract_version':'1.1','source_sha256':manifest['workbook_sha256'],
         'product_mapping_sha256':sha256(ROOT/'src/product_roles.csv'),
         'definition':'Eligible positive merchandise purchases in [2009-12-01,2011-12-01); gross sales, not net revenue',
         'validation':checks,'results':results}
    (ROOT/'reports/cleaning_summary.json').write_text(json.dumps(out,indent=2,default=json_value)+'\n',encoding='utf-8')
    print('Saved five Parquet tables, exclusion evidence, and reports/cleaning_summary.json.')


if __name__=='__main__':
    main()
