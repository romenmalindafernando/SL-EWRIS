from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]

HISTORY = (
    ROOT / "outputs"
    / "cbsl_preparation"
    / "combined_external_review_2014_2025.csv"
)

st.set_page_config(
    page_title="SL-EWRIS | Sensitivity Analysis",
    page_icon="📊",
    layout="wide"
)

st.title("Risk Threshold Sensitivity Analysis")

st.caption(
    "SL-EWRIS | Historical External Sector Screening"
)

st.warning(
    "Retrospective sensitivity analysis only. "
    "Thresholds are experimental and not calibrated "
    "to predict financial crises."
)

if not HISTORY.is_file():
    st.error(
        "Historical external-sector CSV not found. "
        "Complete the previous extraction steps first."
    )
    st.stop()

df = pd.read_csv(HISTORY)

required = {
    "month",
    "usd_lkr",
    "fx_reserves_usd_bn"
}

missing = required - set(df.columns)

if missing:
    st.error(f"Missing columns: {sorted(missing)}")
    st.stop()

df = df[
    ["month", "usd_lkr", "fx_reserves_usd_bn"]
].copy()

try:
    df["period"] = pd.PeriodIndex(
        df["month"].astype(str),
        freq="M"
    )
except ValueError:
    st.error("Historical month values are invalid.")
    st.stop()

if df["period"].duplicated().any():
    st.error(
        "Duplicate reporting months found. "
        "Resolve duplicates before analysis."
    )
    st.stop()

df["usd_lkr"] = pd.to_numeric(
    df["usd_lkr"], errors="coerce"
)

df["fx_reserves_usd_bn"] = pd.to_numeric(
    df["fx_reserves_usd_bn"],
    errors="coerce"
)

df = df.sort_values("period").set_index("period")

# Compare with the EXACT month three months earlier,
# not simply three rows earlier.
previous_periods = df.index - 3

previous_fx = df["usd_lkr"].reindex(
    previous_periods
).to_numpy()

previous_reserves = df[
    "fx_reserves_usd_bn"
].reindex(previous_periods).to_numpy()

current_fx = df["usd_lkr"].to_numpy()
current_reserves = df[
    "fx_reserves_usd_bn"
].to_numpy()

with np.errstate(divide="ignore", invalid="ignore"):
    fx_change = np.where(
        (current_fx > 0) & (previous_fx > 0),
        (current_fx / previous_fx - 1) * 100,
        np.nan
    )

    reserve_change = np.where(
        (current_reserves > 0)
        & (previous_reserves > 0),
        (current_reserves / previous_reserves - 1) * 100,
        np.nan
    )

df["fx_change_3m_pct"] = fx_change
df["reserves_change_3m_pct"] = reserve_change

df["month"] = df.index.astype(str)

st.subheader("1. Select Experimental Thresholds")

left, right = st.columns(2)

with left:
    currency_threshold = st.slider(
        "Currency Depreciation Threshold (%)",
        min_value=1,
        max_value=30,
        value=10,
        step=1
    )

with right:
    reserve_threshold = st.slider(
        "Reserve Depletion Threshold (%)",
        min_value=1,
        max_value=50,
        value=20,
        step=1
    )

st.caption(
    "Currency signal: 3-month USD/LKR increase "
    "at least the selected threshold. "
    "Reserve signal: 3-month reserves decline "
    "at least the selected threshold."
)

def classify(data, currency_limit, reserve_limit):
    output = data.copy()

    output["currency_available"] = (
        output["fx_change_3m_pct"].notna()
    )

    output["reserve_available"] = (
        output["reserves_change_3m_pct"].notna()
    )

    output["currency_signal"] = (
        output["currency_available"]
        & (
            output["fx_change_3m_pct"]
            >= currency_limit
        )
    )

    output["reserve_signal"] = (
        output["reserve_available"]
        & (
            output["reserves_change_3m_pct"]
            <= -reserve_limit
        )
    )

    output["available_count"] = (
        output["currency_available"].astype(int)
        + output["reserve_available"].astype(int)
    )

    output["signal_count"] = (
        output["currency_signal"].astype(int)
        + output["reserve_signal"].astype(int)
    )

    output["screening_status"] = np.select(
        [
            output["available_count"] < 2,
            output["signal_count"] == 2,
            output["signal_count"] == 1,
        ],
        [
            "Insufficient data",
            "Both thresholds exceeded",
            "One threshold exceeded",
        ],
        default="No threshold exceeded"
    )

    return output


result = classify(
    df,
    currency_threshold,
    reserve_threshold
)

complete = result[
    result["available_count"] == 2
]

one_signal = int(
    (complete["signal_count"] == 1).sum()
)

both_signals = int(
    (complete["signal_count"] == 2).sum()
)

no_signal = int(
    (complete["signal_count"] == 0).sum()
)

st.divider()
st.subheader("2. Historical Screening Results")

a, b, c, d = st.columns(4)

a.metric(
    "Comparable Months",
    len(complete)
)

b.metric(
    "No Threshold Exceeded",
    no_signal
)

c.metric(
    "One Signal",
    one_signal
)

d.metric(
    "Both Signals",
    both_signals
)

if not complete.empty:
    st.metric(
        "Months With Any Signal",
        one_signal + both_signals
    )

st.caption(
    "Months without both valid three-month comparisons "
    "are excluded from these counts, not treated "
    "as months with no economic pressure."
)

st.subheader("3. Historical Signal Timeline")

timeline = result[
    ["month", "signal_count"]
].set_index("month")

st.bar_chart(timeline)

st.divider()

st.subheader("4. Focus on the 2020-2022 Period")

crisis_period = result[
    (result["month"] >= "2020-01")
    & (result["month"] <= "2022-12")
]

st.dataframe(
    crisis_period[
        [
            "month",
            "fx_change_3m_pct",
            "reserves_change_3m_pct",
            "currency_signal",
            "reserve_signal",
            "screening_status"
        ]
    ],
    use_container_width=True,
    hide_index=True
)

st.caption(
    "These are retrospective observations. "
    "A signal before 2022 is not proof that the "
    "2022 crisis was predictable in real time."
)

st.divider()

st.subheader("5. Sensitivity Across Threshold Combinations")

currency_levels = [5, 8, 10, 12, 15]
reserve_levels = [10, 15, 20, 25, 30]

comparison_rows = []

for currency in currency_levels:
    for reserves in reserve_levels:

        test = classify(
            df,
            currency,
            reserves
        )

        usable = test[
            test["available_count"] == 2
        ]

        comparison_rows.append({
            "Currency Threshold (%)": currency,
            "Reserve Threshold (%)": reserves,
            "Both Signals (Months)": int(
                (usable["signal_count"] == 2).sum()
            ),
            "Any Signal (Months)": int(
                (usable["signal_count"] >= 1).sum()
            ),
            "Comparable Months": len(usable)
        })

comparison = pd.DataFrame(comparison_rows)

matrix = comparison.pivot(
    index="Currency Threshold (%)",
    columns="Reserve Threshold (%)",
    values="Both Signals (Months)"
)

st.write(
    "**Number of historical months exceeding both "
    "currency and reserve thresholds**"
)

st.dataframe(
    matrix,
    use_container_width=True
)

st.caption(
    "The matrix counts retrospective stress signals. "
    "It does not measure forecast accuracy."
)

st.subheader("6. All Tested Threshold Combinations")

st.dataframe(
    comparison,
    use_container_width=True,
    hide_index=True
)

st.download_button(
    "Download Sensitivity Results",
    data=comparison.to_csv(
        index=False
    ).encode("utf-8-sig"),
    file_name="sl_ewris_threshold_sensitivity.csv",
    mime="text/csv"
)

st.divider()

st.subheader("7. Research Interpretation")

st.write(
    "Changing screening thresholds changes how many "
    "historical months are flagged. "
    "A lower threshold may detect more stress months "
    "but may also create more false alarms."
)

st.write(
    "This analysis does not establish which threshold "
    "is optimal. Selecting thresholds requires a "
    "defined target event, appropriate historical "
    "validation and independent evaluation."
)

st.info(
    "The complete four-indicator risk-scoring model "
    "is not recalibrated here. This page specifically "
    "examines the sensitivity of two external-sector "
    "stress signals."
)

st.caption(
    "SL-EWRIS Capstone | Retrospective Sensitivity Analysis"
)
