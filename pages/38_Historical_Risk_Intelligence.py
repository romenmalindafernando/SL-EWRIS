from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]

RISK_FILE = (
    ROOT / "outputs/external_risk_analysis"
    / "external_risk_indicators_2014_2025.csv"
)

VINTAGE_FILE = (
    ROOT / "outputs/external_risk_analysis"
    / "historical_vintage_snapshots_v1.csv"
)

FALLBACK_FILE = (
    ROOT / "outputs/external_risk_analysis"
    / "historical_information_snapshots.csv"
)

st.set_page_config(
    page_title="SL-EWRIS | Historical Risk Intelligence",
    page_icon="📊",
    layout="wide"
)

st.title("Historical Economic Risk Intelligence")
st.caption(
    "Sri Lanka | Retrospective external-sector screening "
    "and historical publication evidence"
)

st.info(
    "This dashboard identifies historical financial-stress "
    "patterns. It does not provide a validated financial "
    "crisis probability or prediction."
)

if not RISK_FILE.exists():
    st.error(
        "Historical risk analysis is missing. Run "
        "analysis/external_risk_screening.py first."
    )
    st.stop()

df = pd.read_csv(RISK_FILE)
df["month"] = df["month"].astype(str)

required = [
    "month",
    "fx_reserves_usd_bn",
    "usd_lkr",
    "screening_status",
    "screening_flags_count",
    "reserves_change_12m_pct",
    "fx_change_3m_pct",
]

missing = set(required) - set(df.columns)

if missing:
    st.error(f"Missing data columns: {sorted(missing)}")
    st.stop()

df = df.sort_values("month")

st.subheader("Historical external-sector indicators")

first_month, last_month = df["month"].iloc[[0, -1]]

selected_month = st.selectbox(
    "Select reporting month",
    options=df["month"].tolist(),
    index=len(df) - 1,
    key="history_month_selector"
)

selected = df.loc[
    df["month"] == selected_month
].iloc[0]

a, b, c = st.columns(3)

a.metric(
    "Gross official reserves",
    f"${selected['fx_reserves_usd_bn']:.3f} bn"
)

b.metric(
    "USD/LKR monthly average",
    f"{selected['usd_lkr']:.2f}"
)

c.metric(
    "Retrospective stress flags",
    str(int(selected["screening_flags_count"]))
)

st.write(
    "**Screening assessment:**",
    selected["screening_status"]
)

st.caption(
    "Thresholds are illustrative and have not been "
    "statistically calibrated. Gross reserves may include "
    "assets that are not readily usable."
)

st.divider()

st.subheader("Foreign reserve trends")

chart_data = df.set_index("month")[
    ["fx_reserves_usd_bn"]
]

st.line_chart(
    chart_data,
    y_label="USD billions",
    x_label="Reporting month"
)

st.subheader("USD/LKR exchange-rate trends")

st.line_chart(
    df.set_index("month")[["usd_lkr"]],
    y_label="LKR per USD",
    x_label="Reporting month"
)

st.divider()

st.subheader("Historical warning signals")

start, end = st.select_slider(
    "Historical period",
    options=df["month"].tolist(),
    value=("2020-01", "2022-12"),
    key="risk_period_slider"
)

period = df[
    (df["month"] >= start)
    & (df["month"] <= end)
]

st.dataframe(
    period[
        [
            "month",
            "fx_reserves_usd_bn",
            "usd_lkr",
            "reserves_change_12m_pct",
            "fx_change_3m_pct",
            "screening_flags_count",
            "screening_status"
        ]
    ],
    use_container_width=True,
    hide_index=True
)

st.caption(
    "These flags use the retrospective compiled dataset, "
    "not verified historical publication vintages."
)

st.divider()

st.subheader("Publication-aware historical replay")

if VINTAGE_FILE.exists():
    replay = pd.read_csv(
        VINTAGE_FILE,
        dtype=str,
        keep_default_na=False
    )
    source_name = "Historical vintage ledger"

elif FALLBACK_FILE.exists():
    replay = pd.read_csv(
        FALLBACK_FILE,
        dtype=str,
        keep_default_na=False
    )
    source_name = "Initial publication-aware replay"

else:
    replay = None
    source_name = ""

if replay is None:
    st.warning(
        "No historical replay output found. "
        "Run the publication-aware replay script."
    )

else:
    st.caption(f"Data source: {source_name}")

    if "decision_date" not in replay.columns:
        st.error("Replay file has no decision_date column.")

    else:
        decision_date = st.selectbox(
            "Choose historical decision date",
            sorted(replay["decision_date"].unique()),
            key="historical_decision_selector"
        )

        snapshot = replay[
            replay["decision_date"] == decision_date
        ]

        st.dataframe(
            snapshot,
            use_container_width=True,
            hide_index=True
        )

        st.caption(
            "Only evidence that passed the replay's "
            "eligibility checks is displayed as available. "
            "Those checks do not independently authenticate "
            "historical CBSL source documents."
        )

st.divider()

st.subheader("Data quality and research limitations")

st.write(
    "The retrospective datasets contain complete monthly "
    "candidate observations for 2014–2025. Historical "
    "publication dates remain incomplete, so the stress "
    "signals must not be described as proven advance warnings."
)

st.write(
    "A validated crisis-warning model will additionally "
    "require data-vintage verification, sensitivity analysis, "
    "false-alarm assessment and broader validation evidence."
)

st.caption(
    "SL-EWRIS | Statistics and Computer Science Capstone"
)
