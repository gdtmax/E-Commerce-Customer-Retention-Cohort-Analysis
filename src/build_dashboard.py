"""Rebuild the portable, aggregate-only executive dashboard; no hosting needed."""
import json
from pathlib import Path
import duckdb
from audit_data import json_value
from retention_analysis import records

ROOT=Path(__file__).resolve().parents[1]


def main():
    summary=json.loads((ROOT/'reports/customer_analysis_summary.json').read_text(encoding="utf-8"))
    retention=json.loads((ROOT/'reports/retention_summary.json').read_text(encoding="utf-8"))
    with duckdb.connect(str(ROOT/'data/processed/retention.duckdb'),read_only=True) as con:
        cohorts=records(con,'SELECT * FROM cohort_retention WHERE is_primary_cohort ORDER BY cohort_month,month_index')
    payload=json.dumps({'analysis':summary,'retention':retention,'cohorts':cohorts},default=json_value).replace('</',r'<\/')
    html='''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Customer retention review</title>
<style>
:root{font-family:Segoe UI,Arial,sans-serif;color:#18303c;background:#f3f6f7;font-size:16px}*{box-sizing:border-box}body{margin:0}header{background:#153e4c;color:white;padding:40px max(5%,calc((100% - 1180px)/2));}h1{font-size:36px;margin:6px 0 12px}h2{margin-top:0;font-size:25px}p{line-height:1.65}main{max-width:1180px;margin:24px auto;padding:0 18px}nav{display:flex;gap:24px;margin-top:22px;flex-wrap:wrap}nav a{color:#bde5ef}a{color:#126885}section{background:white;border:1px solid #dce5e8;border-radius:10px;padding:26px;margin:22px 0}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{background:white;border:1px solid #dce5e8;border-radius:10px;padding:20px}.number{font-size:30px;font-weight:650;margin:12px 0}.muted{color:#58707a;font-size:14px}.note{border-left:4px solid #c46b27;padding:10px 16px;background:#fff7ec}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:12px;border-bottom:1px solid #e4eaed;white-space:nowrap}th{background:#edf3f5}label{font-weight:600;margin-right:12px}select{padding:9px;border:1px solid #a5bbc4;border-radius:5px;font:inherit;margin-bottom:18px;max-width:100%}img{width:100%;height:auto;margin:12px 0}footer{color:#58707a;font-size:14px;padding:12px 0 35px}.status{font-size:13px;letter-spacing:1px;text-transform:uppercase;color:#bde5ef}@media(max-width:700px){.cards{grid-template-columns:1fr}h1{font-size:29px}section{padding:18px}header{padding:28px 18px}}
</style></head><body><header><div class="status">Historical customer analytics | UCI Online Retail II</div><h1>Customer retention review</h1><p>Who returns, how customer value is concentrated, and which differences merit a test.<br>Snapshot: 1 December 2011. Currency: GBP. Historical UK retail, including wholesale activity.</p><nav><a href="#cohorts">Cohorts</a><a href="#segments">RFM &amp; value</a><a href="#differences">First-order differences</a><a href="../reports/case_study.md">Case study</a></nav></header>
<main><div class="cards"><div class="card"><span>Historical identified customers</span><div class="number" id="customers"></div><div class="muted">Includes dormant accounts; not verified individual people.</div></div><div class="card"><span>90-day repeat purchase rate</span><div class="number" id="repeat"></div><div class="muted" id="repeatN"></div></div><div class="card"><span>Top 10% share of historical sales</span><div class="number" id="concentration"></div><div class="muted"><span id="topCount"></span> customers; identified gross purchases only.</div></div></div>
<section id="cohorts"><h2>Purchasing retention by cohort</h2><p>Choose the month of first observed purchase. A customer can skip a month and return later. Gray heatmap cells and blank future rates are unobserved, not zero retention.</p><label for="cohort">First-observed cohort</label><select id="cohort"></select><div class="scroll" id="cohortTable"></div><details><summary>View full primary-cohort heatmap</summary><img src="../images/cohort_retention_heatmap.png" alt="Cohort retention heatmap with gray unobserved cells"></details><p class="muted">Calendar-month retention differs from elapsed-day repeat purchasing. <a href="../data/processed/cohort_retention.csv">Download cohort table</a></p></section>
<section id="segments"><h2>RFM and observed value</h2><p>Recency uses full history. Frequency and monetary value use the last 12 months. Customers inactive throughout that year remain in the dormant segment.</p><div class="scroll" id="rfmTable"></div><details><summary>View customer concentration</summary><img src="../images/customer_value_concentration.png" alt="Cumulative historical customer sales concentration"></details><p class="note">Segment labels are operational rules. Historical spending is not predicted lifetime value or guaranteed recoverable sales. The 90-day reactivation rule identifies <span id="reactivationCount"></span> repeat-history accounts for investigation.</p></section>
<section id="differences"><h2>First-order differences</h2><p>All groups use complete 90-day follow-up and first-observed cohorts from March 2010. Rates for groups with fewer than 100 customers are suppressed. Intervals are raw 95% Wilson intervals.</p><label for="feature">Compare by</label><select id="feature"><option value="first_order_value_band">First-order value</option><option value="first_order_product_band">First-order product diversity</option><option value="first_order_geography">First-order geography</option></select><div class="scroll" id="comparisonTable"></div><p class="note" id="mixNote"></p><p>Higher first-basket value is associated with more repeat purchasing. Geography differences are weak and change ordering after cohort weighting. Test interventions with randomized holdouts before allocating budget based on these patterns.</p><p><a href="../data/processed/customer_comparisons.csv">Download group results</a> &middot; <a href="../reports/customer_value_and_segments.md">Read evidence and proposed tests</a></p></section>
<footer>Gross positive merchandise purchases before credits. Missing identity, unresolved manual entries, header exclusions and source coverage limit generalization. No campaign uplift is claimed. This portable dashboard contains aggregate data only; it is not a Power BI file.</footer></main>
<script id="data" type="application/json">PAYLOAD</script><script>
const data=JSON.parse(document.getElementById('data').textContent), a=data.analysis;
const fmt=n=>Number(n).toLocaleString('en-GB'), pct=n=>n===null?'Not available':(100*n).toFixed(2)+'%', gbp=n=>Number(n).toLocaleString('en-GB',{minimumFractionDigits:2,maximumFractionDigits:2});
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
function table(id,heads,rows){document.getElementById(id).innerHTML='<table><thead><tr>'+heads.map(x=>'<th>'+esc(x)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(x=>'<td>'+esc(x)+'</td>').join('')+'</tr>').join('')+'</tbody></table>';}
document.getElementById('customers').textContent=fmt(a.concentration.customers);
document.getElementById('topCount').textContent=fmt(a.concentration.top_customer_count);
document.getElementById('reactivationCount').textContent=fmt(a.reactivation.find(x=>x.recency_threshold_days_exclusive===90).customers);
document.getElementById('concentration').textContent=pct(a.concentration.top_customer_sales_share);
const repeat=data.retention.repeat_purchase.find(x=>x.population==='own_window'&&x.window_days===90);
document.getElementById('repeat').textContent=pct(repeat.repeat_purchase_rate);
document.getElementById('repeatN').textContent=fmt(repeat.repeat_customers)+' / '+fmt(repeat.eligible_customers)+' mature primary-cohort customers.';
const cohort=document.getElementById('cohort');
for(const m of [...new Set(data.cohorts.map(x=>x.cohort_month))]){const o=document.createElement('option');o.value=m;o.textContent=m.slice(0,7);cohort.appendChild(o);}
function renderCohort(){table('cohortTable',['Month index','Calendar month','Cohort size','Purchasing customers','Retention'],data.cohorts.filter(x=>x.cohort_month===cohort.value).map(x=>[x.month_index,x.activity_month.slice(0,7),fmt(x.cohort_size),x.retained_customers===null?'Not yet observed':fmt(x.retained_customers),x.is_observable?pct(x.retention_rate):'Not yet observed']));}
cohort.addEventListener('change',renderCohort);renderCohort();
table('rfmTable',['Segment','Customers','Trailing-year sales GBP','Share of trailing-year sales'],a.rfm_segments.map(x=>[x.segment,fmt(x.customers),gbp(x.monetary_12m_gbp),pct(x.monetary_share)]));
const feature=document.getElementById('feature');
function renderComparisons(){table('comparisonTable',['Group','Eligible n','Repeated x','90-day repeat rate','95% interval'],a.comparisons.filter(x=>x.feature===feature.value).map(x=>[x.group,fmt(x.eligible_customers),fmt(x.repeat_customers),x.publishable?pct(x.repeat_rate_90d):'Suppressed: n < 100',x.publishable?pct(x.wilson_low)+' to '+pct(x.wilson_high):'Suppressed']));
const adjusted=a.cohort_standardization.filter(x=>x.feature===feature.value);
document.getElementById('mixNote').textContent=adjusted.map(x=>x.group+': '+x.status+'; shared n='+fmt(x.shared_eligible_customers)+', months='+x.shared_months+(x.standardized_rate===null?'':', standardized rate='+pct(x.standardized_rate))).join(' | ');}
feature.addEventListener('change',renderComparisons);renderComparisons();
</script></body></html>'''.replace('PAYLOAD',payload)
    (ROOT/'dashboard/index.html').write_text(html,encoding='utf-8')
    print('Saved dashboard/index.html; open directly in a browser, keeping the project folder together.')


if __name__=='__main__':main()
