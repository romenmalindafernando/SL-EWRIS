from pathlib import Path
import pandas as pd
import numpy as np
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT / "outputs/cbsl_preparation"
    / "combined_external_review_2014_2025.csv"
)

st.set_page_config(
    page_title="SL-EWRIS | Historical Lead Time",
    page_icon="📉",
    layout="wide"
)

st.title("Historical Early-Warning Signal Evaluation")

st.warning(
    "Retrospective research analysis only. "
    "This is NOT a real-time backtest, "
    "validated crisis predictor, or measured "
    "public-warning lead time."
)

st.info(
    "Reference event: Sri Lanka's external "
    "debt-service suspension announcement "
    "on 12 April 2022."
)

st.markdown(
    "[Historical event reference — IMF]"
    "(https://www.elibrary.imf.org/view/"
    "journals/002/2023/116/article-A001-en.xml)"
)

if not SOURCE.exists():
    st.error("Historical source CSV is missing.")
    st.stop()

df = pd.read_csv(SOURCE)

required = {
    "month",
    "usd_lkr",
    "fx_reserves_usd_bn"
}

if not required.issubset(df.columns):
    st.error(
        f"Missing columns: {sorted(required-set(df.columns))}"
    )
    st.stop()

df = df[
    ["month", "usd_lkr", "fx_reserves_usd_bn"]
].copy()

try:
    df["period"] = pd.PeriodIndex(
        df["month"].astype(str),
        freq="M"
    )
except (ValueError, TypeError):
    st.error("Reporting-month format is invalid.")
    st.stop()

if df["period"].duplicated().any():
    st.error("Duplicate reporting months detected.")
    st.stop()

df["usd_lkr"] = pd.to_numeric(
    df["usd_lkr"],
    errors="coerce"
)

df["fx_reserves_usd_bn"] = pd.to_numeric(
    df["fx_reserves_usd_bn"],
    errors="coerce"
)

df = df.sort_values("period").set_index("period")

# Exact three-calendar-month comparisons.
prior_index = df.index - 3

prior_fx = (
    df["usd_lkr"]
    .reindex(prior_index)
    .to_numpy(dtype=float)
)

prior_reserves = (
    df["fx_reserves_usd_bn"]
    .reindex(prior_index)
    .to_numpy(dtype=float)
)

current_fx = df["usd_lkr"].to_numpy(dtype=float)
current_reserves = (
    df["fx_reserves_usd_bn"]
    .to_numpy(dtype=float)
)

with np.errstate(divide="ignore", invalid="ignore"):

    df["fx_change_3m_pct"] = np.where(
        (current_fx > 0) & (prior_fx > 0),
        (current_fx / prior_fx - 1) * 100,
        np.nan
    )

    df["reserve_change_3m_pct"] = np.where(
        (current_reserves > 0)
        & (prior_reserves > 0),
        (current_reserves / prior_reserves - 1) * 100,
        np.nan
    )

st.subheader("1. Research Configuration")

a, b, c = st.columns(3)

with a:
    currency_limit = st.slider(
        "Currency Pressure Threshold (%)",
        1, 30, 10
    )

with b:
    reserve_limit = st.slider(
        "Reserve Depletion Threshold (%)",
        1, 50, 20
    )

with c:
    lookback = st.slider(
        "Pre-event window (months)",
        3, 24, 12
    )

event_month = pd.Period("2022-04", freq="M")

# Exclude the event month itself to avoid
# treating simultaneous effects as warnings.
start_period = event_month - lookback
last_pre_event = event_month - 1

df["currency_available"] = (
    df["fx_change_3m_pct"].notna()
)

df["reserve_available"] = (
    df["reserve_change_3m_pct"].notna()
)

df["currency_signal"] = (
    df["currency_available"]
    & (df["fx_change_3m_pct"] >= currency_limit)
)

df["reserve_signal"] = (
    df["reserve_available"]
    & (df["reserve_change_3m_pct"] <= -reserve_limit)
)

df["available_count"] = (
    df["currency_available"].astype(int)
    + df["reserve_available"].astype(int)
)

df["signal_count"] = (
    df["currency_signal"].astype(int)
    + df["reserve_signal"].astype(int)
)

df["month"] = df.index.astype(str)

window = df[
    (df.index >= start_period)
    & (df.index <= last_pre_event)
].copy()

st.divider()
st.subheader("2. Pre-Event Signal Analysis")

complete = window[
    window["available_count"] == 2
]

any_signal = window[
    window["signal_count"] >= 1
]

multiple_signals = window[
    window["signal_count"] == 2
]

a, b, c, d = st.columns(4)

a.metric(
    "Months in Window",
    len(window)
)

b.metric(
    "Comparable Months",
    len(complete)
)

c.metric(
    "Months With Any Signal",
    len(any_signal)
)

d.metric(
    "Months With Both Signals",
    len(multiple_signals)
)

if len(window) != lookback:
    st.warning(
        "Not all months in the selected pre-event "
        "window are represented in the dataset."
    )

if any_signal.empty:
    st.warning(
        "No retrospective stress signals were "
        "detected in the selected window."
    )
else:
    first = any_signal.index.min()
    last = any_signal.index.max()

    first_lead = (
        event_month.ordinal - first.ordinal
    )

    last_lead = (
        event_month.ordinal - last.ordinal
    )

    x, y = st.columns(2)

    x.metric(
        "First Flagged Reporting Month",
        str(first)
    )

    y.metric(
        "Reporting-Month Lead",
        f"{first_lead} months"
    )

    st.write(
        f"First flagged month: **{first}**. "
        f"Last flagged month: **{last}**. "
        f"The last flagged reporting month was "
        f"{last_lead} calendar month(s) "
        "before the reference event month."
    )

    st.warning(
        "Reporting-month lead is not actual "
        "warning availability lead. Historical "
        "release dates are not yet verified."
    )

st.divider()
st.subheader("3. Monthly Warning Timeline")

if not window.empty:

    timeline = window[
        ["month", "signal_count"]
    ].set_index("month")

    st.bar_chart(timeline)

    details = window[
        [
            "month",
            "fx_change_3m_pct",
            "reserve_change_3m_pct",
            "currency_signal",
            "reserve_signal",
            "available_count",
            "signal_count"
        ]
    ]

    st.dataframe(
        details,
        use_container_width=True,
        hide_index=True
    )

st.divider()
st.subheader("4. Outside-Window Historical Signals")

outside = df[
    df.index < start_period
].copy()

outside_complete = outside[
    outside["available_count"] == 2
]

outside_flagged = outside_complete[
    outside_complete["signal_count"] >= 1
]

a, b = st.columns(2)

a.metric(
    "Earlier Comparable Months",
    len(outside_complete)
)

b.metric(
    "Earlier Flagged Months",
    len(outside_flagged)
)

st.caption(
    "These are historical signals outside the "
    "selected pre-event window. They are NOT "
    "automatically false alarms. Other crises, "
    "different event definitions and warning "
    "horizons have not been evaluated."
)

if not outside_flagged.empty:
    st.dataframe(
        outside_flagged[
            [
                "month",
                "fx_change_3m_pct",
                "reserve_change_3m_pct",
                "signal_count"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )

st.divider()
st.subheader("5. Export Evaluation Results")

if not window.empty:
    export = window.reset_index(drop=True)

    st.download_button(
        "Download Pre-Event Analysis CSV",
        data=export.to_csv(
            index=False
        ).encode("utf-8-sig"),
        file_name=(
            "sl_ewris_pre_event_lead_time.csv"
        ),
        mime="text/csv"
    )

st.divider()
st.subheader("6. Research Limitations")

st.write(
    "The analysis evaluates historical observations "
    "against an April 2022 event reference. "
    "It does not establish real-time predictability."
)

st.write(
    "An observation for March 2022 could have "
    "been published after March ended. "
    "Its reporting month alone cannot prove "
    "that it was known before 12 April 2022."
)

st.write(
    "False-positive rates, sensitivity, specificity, "
    "precision and recall cannot be defensibly "
    "calculated from this single illustrative "
    "event-window analysis."
)

st.write(
    "Thresholds were not independently calibrated. "
    "A valid predictive evaluation will require "
    "point-in-time observations, explicit crisis "
    "labels, suitable comparison periods and "
    "out-of-sample testing."
)

st.caption(
    "SL-EWRIS | Descriptive Historical "
    "Lead-Time Evaluation"
)
