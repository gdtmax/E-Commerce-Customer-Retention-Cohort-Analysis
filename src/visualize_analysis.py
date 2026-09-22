"""Step 10 and Steps 11-12 figures. Use validated database outputs only."""
import json
from pathlib import Path
import duckdb
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from retention_analysis import validate,records

ROOT=Path(__file__).resolve().parents[1]


def save(fig,name):
    fig.savefig(ROOT/'images'/name,dpi=170,bbox_inches='tight');plt.close(fig)


def cohort_figures(con):
    rows=records(con,'SELECT * FROM cohort_retention WHERE is_primary_cohort ORDER BY cohort_month,month_index')
    cohorts=sorted({r['cohort_month'] for r in rows})
    max_index=max(r['month_index'] for r in rows if r['is_observable'])
    matrix=np.full((len(cohorts),max_index+1),np.nan);sizes={}
    for r in rows:
        sizes[r['cohort_month']]=r['cohort_size']
        if r['month_index']<=max_index and r['is_observable'] and r['retention_rate'] is not None:
            matrix[cohorts.index(r['cohort_month']),r['month_index']]=r['retention_rate']
    cmap=plt.colormaps['Blues'].copy();cmap.set_bad('#e4e7eb')
    fig,ax=plt.subplots(figsize=(15,10),layout='constrained')
    im=ax.imshow(np.ma.masked_invalid(matrix),vmin=0,vmax=1,cmap=cmap,aspect='auto')
    ax.set_yticks(range(len(cohorts)),[f'{m:%Y-%m}  (n={sizes[m]})' for m in cohorts])
    ax.set_xticks(range(max_index+1));ax.set_xlabel('Calendar months since first observed purchase')
    ax.set_ylabel('First-observed cohort and customer count')
    for i,j in np.ndindex(matrix.shape):
        if np.isfinite(matrix[i,j]):ax.text(j,i,f'{matrix[i,j]:.0%}',ha='center',va='center',fontsize=7,color='white' if matrix[i,j]>.55 else '#14283a')
    fig.colorbar(im,ax=ax,format=PercentFormatter(1),label='Purchasing retention')
    ax.set_title('Calendar-month purchasing retention | primary cohorts\nGray = not yet observable; zero = observed with no purchase. Cutoff: 2011-12-01',pad=15)
    save(fig,'cohort_retention_heatmap.png')
    repeat=records(con,'SELECT * FROM repeat_purchase_summary ORDER BY population,window_days')
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained',sharey=True)
    for ax,pop,title in zip(axes,['own_window','common_90_day'],['Each window has its own mature population','Same 90-day-mature population']):
        subset=[r for r in repeat if r['population']==pop]
        heights=[r['repeat_purchase_rate'] for r in subset]
        ax.bar([30,60,90],heights,width=17,color='#146C94')
        for r in subset:ax.text(r['window_days'],r['repeat_purchase_rate']+.015,f"{r['repeat_purchase_rate']:.2%}\nn={r['eligible_customers']:,}",ha='center',fontsize=10)
        ax.set_xticks([30,60,90],['30 days','60 days','90 days']);ax.set_ylim(0,.6);ax.yaxis.set_major_formatter(PercentFormatter(1));ax.set_title(title,fontsize=11)
        ax.grid(axis='y',alpha=.15);ax.spines[['top','right']].set_visible(False)
    axes[0].set_ylabel('Customers with a second invoice within the window')
    fig.suptitle('Fixed-window repeat purchases | first observed from March 2010')
    save(fig,'repeat_purchase_windows.png')
    return {'observed_cells_plotted':int(np.isfinite(matrix).sum()),'masked_cells':int(np.isnan(matrix).sum()),'cohorts':len(cohorts),'maximum_month_index':max_index}


def customer_figures(con,summary):
    rows=summary['rfm_segments'];names=[r['segment'] for r in rows]
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained',sharey=True)
    axes[0].barh(names,[r['customers'] for r in rows],color='#146C94');axes[0].invert_yaxis()
    axes[1].barh(names,[r['monetary_share'] for r in rows],color='#c46b27')
    axes[0].set_xlabel('Historical customers');axes[1].set_xlabel('Share of trailing-12-month identified sales')
    axes[1].xaxis.set_major_formatter(PercentFormatter(1));axes[1].set_xlim(0,1)
    for i,r in enumerate(rows):
        axes[0].text(r['customers']+10,i,str(r['customers']),va='center',fontsize=9)
        axes[1].text(r['monetary_share']+.01,i,f"{r['monetary_share']:.1%}",va='center',fontsize=9)
    for ax in axes:ax.spines[['top','right']].set_visible(False)
    fig.suptitle('RFM segments as of 2011-12-01 | dormant customers retained')
    save(fig,'rfm_segments.png')
    values=records(con,'SELECT * FROM customer_value ORDER BY historical_sales_rank')
    sales=np.array([float(r['historical_sales_gbp']) for r in values]);n=len(sales)
    x=np.r_[0,np.arange(1,n+1)/n];y=np.r_[0,np.cumsum(sales)/sales.sum()]
    fig,ax=plt.subplots(figsize=(8,5),layout='constrained');ax.plot(x,y,color='#146C94',linewidth=2);ax.plot([0,1],[0,1],'--',color='#aaaaaa',label='Equal contribution reference')
    k=summary['concentration']['top_customer_count'];share=summary['concentration']['top_customer_sales_share']
    ax.scatter([k/n],[share],color='#c46b27',zorder=3);ax.annotate(f'Top {k} customers: {share:.2%} of sales',xy=(k/n,share),xytext=(.26,.45),arrowprops={'arrowstyle':'->'})
    ax.set(xlim=(0,1),ylim=(0,1),xlabel='Customers, ranked by historical sales descending',ylabel='Cumulative share of identified historical sales',title='Observed customer sales concentration | full history')
    ax.xaxis.set_major_formatter(PercentFormatter(1));ax.yaxis.set_major_formatter(PercentFormatter(1));ax.grid(alpha=.15);ax.legend(loc='lower right')
    save(fig,'customer_value_concentration.png')
    features=['first_order_value_band','first_order_product_band','first_order_geography']
    fig,axes=plt.subplots(1,3,figsize=(16,5),layout='constrained',sharex=True)
    for ax,feature,title in zip(axes,features,['First-order value','First-order product diversity','First-order geography']):
        rows=[r for r in summary['comparisons'] if r['feature']==feature]
        ax.set_yticks(range(len(rows)),[f"{r['group']}\n(n={r['eligible_customers']:,})" for r in rows]);ax.set_ylim(len(rows)-.5,-.5)
        for i,r in enumerate(rows):
            if not r['publishable']:ax.text(.02,i,'Rate suppressed: n < 100',va='center',fontsize=9,color='#666666');continue
            p=r['repeat_rate_90d'];ax.errorbar(p,i,xerr=[[p-r['wilson_low']],[r['wilson_high']-p]],fmt='o',color='#146C94',capsize=4)
        ax.set_xlim(0,.8);ax.xaxis.set_major_formatter(PercentFormatter(1));ax.set_title(title);ax.grid(axis='x',alpha=.15);ax.spines[['top','right']].set_visible(False)
        ax.set_xlabel('90-day repeat rate; raw 95% Wilson interval')
    fig.suptitle('First-order differences | complete 90-day observation, primary cohorts\nDescriptive associations; raw intervals do not adjust for cohort mix',fontsize=13)
    save(fig,'customer_group_comparisons.png')


def main():
    spec=json.loads((ROOT/'src/metric_spec.json').read_text(encoding="utf-8"))
    params={'history_start':spec['history_start_inclusive'],'cutoff':spec['analysis_cutoff_exclusive'],'cohort_start':spec['primary_cohort_start_inclusive']}
    summary=json.loads((ROOT/'reports/customer_analysis_summary.json').read_text(encoding="utf-8"))
    with duckdb.connect(str(ROOT/'data/processed/retention.duckdb'),read_only=True) as con:
        checks=validate(con,params)
        plotted=cohort_figures(con);customer_figures(con,summary)
    (ROOT/'reports/visualization_validation.json').write_text(json.dumps({'step':10,'validation':checks,'heatmap':plotted,
        'interpretation':'Gray is unobserved; every displayed numeric cell is independently validated. Repeat populations are separately labeled.'},indent=2)+'\n')
    print('Saved five analysis figures; cohort and repeat data revalidated before plotting.')


if __name__=='__main__':main()
