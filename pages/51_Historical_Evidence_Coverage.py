from pathlib import Path
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.build_evidence_coverage import build_coverage

st.set_page_config(
    page_title="SL-EWRIS | Evidence Coverage",
    page_icon="📋",
    layout="wide"
)

st.title("Historical Publication Evidence Coverage")
st.caption("SL-EWRIS | CBSL Historical Evidence Audit")

st.warning(
    "Report evidence coverage is not independent "
    "source verification or point-in-time readiness."
)

try:
    matrix, details = build_coverage()
except (ValueError, FileNotFoundError, KeyError) as exc:
    st.error(str(exc))
    st.stop()

matrix_df = pd.DataFrame(matrix)
detail_df = pd.DataFrame(details)

st.subheader("1. Overall Evidence Coverage")

identified = int(
    (detail_df["evidence_count"] > 0).sum()
)

consistent = int(
    (
        detail_df["rounded_comparison"]
        == "Consistent at reported precision"
    ).sum()
)

both = int(
    (matrix_df["both_have_report_evidence"] == "Yes").sum()
)

a, b, c, d = st.columns(4)

a.metric("Historical Months", len(matrix_df))
b.metric("Indicator Records", len(detail_df))
c.metric("Report Evidence Identified", identified)
d.metric("Rounded Matches", consistent)

st.metric(
    "Months With Both Report Types",
    both
)

st.progress(
    identified / len(detail_df)
    if len(detail_df) else 0
)

st.caption(
    "Progress measures report references identified. "
    "It does not measure independently verified records."
)

st.divider()
st.subheader("2. Monthly Coverage Matrix")

st.dataframe(
    matrix_df,
    use_container_width=True,
    hide_index=True
)

st.divider()
st.subheader("3. Evidence Details")

indicator = st.selectbox(
    "Select Indicator",
    [
        "All",
        "fx_reserves_usd_bn",
        "usd_lkr"
    ]
)

if indicator == "All":
    filtered = detail_df
else:
    filtered = detail_df[
        detail_df["indicator"] == indicator
    ]

st.dataframe(
    filtered,
    use_container_width=True,
    hide_index=True
)

st.divider()
st.subheader("4. Research Tasks Remaining")

pending = detail_df[
    detail_df["evidence_count"] == 0
]

st.metric(
    "Records Without Identified Report Evidence",
    len(pending)
)

st.dataframe(
    pending[["month", "indicator", "next_action"]],
    use_container_width=True,
    hide_index=True
)

st.divider()
st.subheader("5. Download Research Audit")

st.download_button(
    "Download Coverage Matrix CSV",
    data=matrix_df.to_csv(
        index=False
    ).encode("utf-8-sig"),
    file_name="sl_ewris_evidence_coverage_matrix.csv",
    mime="text/csv"
)

st.download_button(
    "Download Detailed Evidence Audit",
    data=detail_df.to_csv(
        index=False
    ).encode("utf-8-sig"),
    file_name="sl_ewris_evidence_details.csv",
    mime="text/csv"
)

st.caption(
    "Read-only dashboard. "
    "All original research files remain unchanged."
)
