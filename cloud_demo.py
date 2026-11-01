"""SL-EWRIS custom cloud frontend backed by Neon PostgreSQL."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from database import DatabaseConnection, connect_database

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'public_data'
ASSETS = ROOT / 'assets'
MODEL_OUTPUT = ROOT / 'outputs' / 'machine_learning'

st.set_page_config(page_title='SL-EWRIS | Economic Intelligence', page_icon='\U0001F4CA', layout='wide', initial_sidebar_state='expanded')

from ui.cloud_theme import apply_cloud_theme
apply_cloud_theme()


st.markdown('''<style>
.stApp {background:linear-gradient(135deg,#f7fbfd 0%,#ffffff 50%,#edf8f5 100%);color:#173650}
[data-testid="stSidebar"] {background:linear-gradient(160deg,#f2faf9,#f7fbfd)!important;border-right:1px solid #dceae9}
[data-testid="stMetric"] {background:linear-gradient(135deg,#fff,#e8f7f4);border:1px solid #d1e8e3;border-radius:16px;padding:16px;min-height:125px;overflow:visible}
[data-testid="stMetricLabel"] *,[data-testid="stMetricValue"] * {white-space:normal!important;overflow-wrap:anywhere!important;line-height:1.35!important}
[data-testid="stMetricValue"] * {font-size:clamp(18px,2.2vw,29px)!important;color:#173650!important}
[data-testid="stMetricLabel"] * {color:#087e78!important}
[data-testid="stSidebar"] div.stButton button {border-radius:12px;min-height:43px;justify-content:flex-start}
[data-testid="stSidebar"] div.stButton button[kind="primary"] {background:#ddf3ef;color:#08796f;border-color:#a5dad0}
.block-container {padding-top:1.6rem;max-width:1350px}
</style>''',unsafe_allow_html=True)

LABELS = {
    'month':'Reporting Month', 'headline_yoy_pct':'Annual Headline Inflation (%)',
    'food_yoy_pct':'Food Inflation (%)', 'nonfood_yoy_pct':'Non-Food Inflation (%)',
    'ccpi_linked_jan2019_100':'Linked CCPI Index (Jan 2019 = 100)',
    'public_nominal_jan2019_100':'Public Nominal Wage Index',
    'informal_nominal_jan2019_100':'Informal Nominal Wage Index',
    'public_real_ncpi_raw':'Public Real Wage Index (NCPI-based)',
    'informal_real_ncpi_raw':'Informal Real Wage Index (NCPI-based)',
    'fx_reserves_usd_bn':'Foreign Reserves (USD Billion)',
    'usd_lkr':'USD/LKR Exchange Rate',
}

def read_dataframe(query: str) -> pd.DataFrame:
    with connect_database(initialize_schema=False) as connection:
        result = connection.execute(query)
        columns = [column.name for column in result.description or ()]
        rows = result.fetchall()
    return pd.DataFrame.from_records(rows, columns=columns)


@st.cache_data(ttl=600, max_entries=1, show_spinner=False)
def load_data() -> pd.DataFrame:
    df = read_dataframe('SELECT * FROM economic_monthly ORDER BY month')
    if 'month' in df:
        df['date'] = pd.to_datetime(df['month']+'-01',errors='coerce')
    for col in df.columns.difference(['month','date']):
        df[col] = pd.to_numeric(df[col],errors='coerce')
    return df

@st.cache_data(ttl=300, max_entries=1, show_spinner=False)
def load_model():
    summary_path=MODEL_OUTPUT/'model_summary.json'
    if not summary_path.is_file(): return {},pd.DataFrame(),pd.DataFrame()
    try:
        summary=json.loads(summary_path.read_text(encoding='utf-8'))
        scores_path = MODEL_OUTPUT/'test_scores.csv'
        predictions_path = MODEL_OUTPUT/'test_predictions.csv'
        scores=pd.read_csv(scores_path) if scores_path.is_file() else pd.DataFrame()
        preds=pd.read_csv(predictions_path) if predictions_path.is_file() else pd.DataFrame()
        return summary,scores,preds
    except (ValueError, OSError, json.JSONDecodeError):
        return {},pd.DataFrame(),pd.DataFrame()


def metric(label, val, col):
    with col: st.metric(label,val)

menu=['Overview','Monthly Data','Economic Trends','Risk Analysis','Data Quality']
icons=['overview.png','monthly.png','trends.png','risk.png','quality.png']
from ui.cloud_sidebar import render_cloud_sidebar, render_project_navigation
render_cloud_sidebar()
render_project_navigation()

page=st.session_state.cloud_tab
frame=load_data()
summary,scores,preds=load_model() if page in {'Overview', 'Risk Analysis'} else ({},pd.DataFrame(),pd.DataFrame())
st.title(page)
if frame.empty:
    st.error('Historical public data snapshot is unavailable. Rebuild the deployment package from the validated local database.')
    st.stop()

usable=frame.dropna(subset=['date'])
min_month=usable.date.min().date()
max_month=usable.date.max().date()

if page=='Overview':
    st.caption('Historical economic intelligence | Sri Lanka | Research prototype')
    cs=st.columns(4)
    latest=usable.iloc[-1]
    metric('Latest Historical Month',str(latest['month']),cs[0])
    metric('Months in Dataset',str(len(frame)),cs[1])
    if 'headline_yoy_pct' in frame:
        recent=frame.dropna(subset=['headline_yoy_pct'])
        val=f"{recent['headline_yoy_pct'].iloc[-1]:.2f}%" if len(recent) else 'N/A'
    else: val='N/A'
    metric('Latest Historical Inflation',val,cs[2])
    metric('Forecasting Model',str(summary.get('selected_model','Not published')),cs[3])
    st.info('Salary is a scenario, not a national observed salary series. The risk-pressure indicators are illustrative, not validated crisis probabilities.')
    st.subheader('Explore the Data')
    left,right=st.columns(2)
    with left: start=st.date_input('From date',value=min_month,min_value=min_month,max_value=max_month,format='YYYY/MM/DD')
    with right: end=st.date_input('To date',value=max_month,min_value=min_month,max_value=max_month,format='YYYY/MM/DD')
    if start>end: st.warning('Start date must precede end date.')
    else:
        subset=usable[(usable.date.dt.date>=start)&(usable.date.dt.date<=end)]
        if 'headline_yoy_pct' in subset:
            fig=go.Figure()
            fig.add_trace(go.Scatter(x=subset.date,y=subset.headline_yoy_pct,mode='lines',line=dict(color='#0D9488',width=3),name='Headline inflation'))
            fig.update_layout(template='plotly_white',height=370,margin=dict(t=25,b=10,l=5,r=5),yaxis_title='YoY inflation (%)')
            st.plotly_chart(fig, width="stretch")
        st.dataframe(subset.drop(columns=['date']).rename(columns=LABELS),hide_index=True,width="stretch")

elif page=='Monthly Data':
    st.caption('Published historical records from Neon PostgreSQL.')
    st.dataframe(frame.drop(columns=['date']).rename(columns=LABELS),hide_index=True,width="stretch",height=510)
    st.download_button('Download public historical CSV',data=frame.drop(columns=['date']).to_csv(index=False).encode('utf-8'),file_name='sl_ewris_public_history.csv',mime='text/csv')
    with st.expander('Enter monthly data', expanded=False):
        from frontend_entry import render_monthly_entry
        render_monthly_entry()

elif page=='Economic Trends':
    st.caption('Historical relationships and indicators, not causal claims.')
    available=[
        col for col in [
            'headline_yoy_pct',
            'food_yoy_pct',
            'nonfood_yoy_pct',
            'public_nominal_jan2019_100',
            'informal_nominal_jan2019_100',
            'public_real_ncpi_raw',
            'informal_real_ncpi_raw',
        ]
        if col in frame and frame[col].notna().any()
    ]
    if not available:
        st.warning('No chart-ready numeric series found.')
    else:
        chosen=st.selectbox('Economic indicator',available,format_func=lambda x:LABELS.get(x,x))
        chart_data=usable.dropna(subset=[chosen])
        fig=go.Figure(go.Scatter(x=chart_data.date,y=chart_data[chosen],mode='lines',line=dict(color='#0D9488',width=3),name=LABELS.get(chosen,chosen)))
        fig.update_layout(template='plotly_white',height=440,margin=dict(t=25,b=10,l=5,r=5),yaxis_title=LABELS.get(chosen,chosen))
        st.plotly_chart(fig, width="stretch")
        st.caption('For source provenance, refer to the accompanying academic report and official CBSL/DCS source tables.')

elif page=='Risk Analysis':
    st.caption('Intermediate-level historical inflation forecasting and descriptive inflation-pressure monitoring.')
    forecast=summary.get('next_month_forecast') or {}
    pressure=summary.get('inflation_pressure') or {}
    cols=st.columns(4)
    rate=forecast.get('forecast_inflation_yoy_pct')
    metric(f"Archived Forecast ({forecast.get('forecast_month','N/A')})",f'{float(rate):.2f}%' if isinstance(rate,(float,int)) else 'Not available',cols[0])
    metric('Inflation Pressure',str(pressure.get('status','Not available')),cols[1])
    metric('Selected Model',str(summary.get('selected_model','Not available')),cols[2])
    selected=summary.get('selected_model')
    selected_score=scores[scores['model']==selected] if 'model' in scores else pd.DataFrame()
    rmse=f"{float(selected_score.iloc[0]['RMSE_pp']):.2f} pp" if not selected_score.empty and 'RMSE_pp' in selected_score else 'N/A'
    metric('Historical Test RMSE',rmse,cols[3])
    st.caption('Archived forecast month: '+str(forecast.get('forecast_month','N/A'))+' | Saved historical model output, not a live forecast or current inflation reading.')
    if {'month','model','actual','prediction'}.issubset(preds.columns):
        subset=preds[preds.model==selected].copy()
        subset['month']=pd.to_datetime(subset['month'],errors='coerce')
        subset=subset.dropna(subset=['month']).sort_values('month')
        if len(subset):
            fig=go.Figure()
            for col,label,color in [('actual','Observed inflation','#142B49'),('prediction','Model forecast','#0D9488')]:
                fig.add_trace(go.Scatter(x=subset.month,y=subset[col],mode='lines+markers',name=label,line=dict(color=color)))
            fig.update_layout(template='plotly_white',height=380,yaxis_title='Inflation (%)')
            st.plotly_chart(fig, width="stretch")
    if not scores.empty: st.dataframe(scores.rename(columns={'model':'Model','RMSE_pp':'RMSE (percentage points)','MAE_pp':'MAE (percentage points)','Bias_pp':'Bias (percentage points)'}),hide_index=True,width="stretch")
    st.warning('Research limitation: Inflation pressure is a rule-based descriptor, NOT a nationally validated crisis warning or crisis probability. Backtests are historical and do not certify prospective performance.')

elif page=='Data Quality':
    st.caption('Coverage, completeness, and consistency checks on the public historical snapshot.')
    st.metric('Historical Months',len(frame))
    duplicates=int(frame.month.duplicated().sum())
    st.metric('Duplicate Months',duplicates)
    expected=pd.date_range(usable.date.min(),usable.date.max(),freq='MS')
    missing=expected.difference(pd.DatetimeIndex(usable.date))
    st.metric('Missing Calendar Months',len(missing))
    missing_counts=frame.drop(columns=['month','date']).isna().sum().rename('Missing observations').reset_index().rename(columns={'index':'Indicator'})
    missing_counts['Indicator']=missing_counts['Indicator'].map(lambda x:LABELS.get(x,x))
    st.dataframe(missing_counts,hide_index=True,width="stretch")
    st.info('This audit does not independently verify the values against original CBSL/DCS releases or their point-in-time publication dates.')

st.divider()
st.caption('SL-EWRIS | Sri Lanka economic research prototype | Public demo is read-only; no server-side data entry or user accounts.')
