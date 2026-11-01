from pathlib import Path
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.audit_vintage_freshness import (
    read_ledger,
    make_snapshot,
    DECISION_DATES
)

st.set_page_config(
    page_title="SL-EWRIS | Historical Data Freshness",
    page_icon="🕒",
    layout="wide"
)

st.title("Historical Evidence Coverage & Data Freshness")

st.warning(
    "This is a historical evidence-readiness audit, "
    "not an economic crisis prediction."
)

try:
    rows, valid, rejected = read_ledger()
except (FileNotFoundError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

st.subheader("1. Evidence Coverage")

a, b, c = st.columns(3)

a.metric("Total Ledger Records", len(rows))
b.metric("Structurally Eligible", len(valid))
c.metric("Pending / Rejected", len(rejected))

st.caption(
    "Structurally eligible means marked Verified "
    "and passing format, unit and date checks. "
    "Official source contents are not automatically checked."
)

st.divider()

st.subheader("2. Data Freshness Settings")

max_age = st.slider(
    "Maximum acceptable observation age (months)",
    min_value=0,
    max_value=12,
    value=3,
    step=1
)

st.caption(
    "Age is measured using reporting months, "
    "not the number of days since publication."
)

st.subheader("3. Historical Decision-Date Audit")

audit = [
    make_snapshot(day, valid, max_age)
    for day in DECISION_DATES
]

audit_df = pd.DataFrame(audit)

st.dataframe(
    audit_df,
    use_container_width=True,
    hide_index=True
)

st.divider()

st.subheader("4. Individual Historical Snapshot")

day = st.selectbox(
    "Select Historical Decision Date",
    DECISION_DATES
)

selected = audit_df[
    audit_df["decision_date"] == day
].iloc[0]

a, b = st.columns(2)

a.metric(
    "Latest USD/LKR Month",
    selected["usd_lkr_month"] or "Unavailable"
)

b.metric(
    "Latest Reserve Month",
    selected["reserves_month"] or "Unavailable"
)

c, d = st.columns(2)

c.metric(
    "USD/LKR Age (months)",
    str(selected["usd_lkr_age_months"])
    if selected["usd_lkr_age_months"] != ""
    else "Unavailable"
)

d.metric(
    "Reserve Age (months)",
    str(selected["reserves_age_months"])
    if selected["reserves_age_months"] != ""
    else "Unavailable"
)

st.write(
    "**Common Reporting Month:**",
    "Yes" if selected["same_reporting_month"] else "No"
)

st.write(
    "**Both Indicators Fresh:**",
    "Yes" if selected["both_fresh"] else "No"
)

st.write(
    "**Three-Month Baselines Available:**",
    (
        "Yes"
        if (
            selected["usd_lkr_3m_ready"]
            and selected["reserves_3m_ready"]
        )
        else "No"
    )
)

if selected["assessment_ready"]:
    st.success(
        "Structurally ready for an external-sector "
        "comparison, subject to independent source audit."
    )
else:
    st.warning(
        "Not ready for a complete historical "
        "external-sector assessment."
    )

st.write("**Audit Finding:**", selected["status"])

st.divider()

st.subheader("5. Download Audit Report")

st.download_button(
    "Download Data Freshness Audit",
    data=audit_df.to_csv(
        index=False
    ).encode("utf-8-sig"),
    file_name="sl_ewris_historical_freshness_audit.csv",
    mime="text/csv"
)

st.caption(
    "Read-only dashboard. No historical data, "
    "publication records, or PostgreSQL tables were modified."
)
