from pathlib import Path
import sqlite3
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.preliminary_risk_score import calculate_risk

DB = ROOT / "database" / "economic_risk.db"
HISTORY = (
    ROOT / "outputs/cbsl_preparation"
    / "combined_external_review_2014_2025.csv"
)

st.set_page_config(
    page_title="SL-EWRIS | Economic Risk",
    page_icon="📊",
    layout="wide"
)

st.title("Economic Risk Screening Dashboard")

st.warning(
    "Experimental Economic Pressure Score. "
    "This is not a validated financial-crisis "
    "prediction model or crisis probability."
)

if not DB.exists():
    st.error("SQLite database not found.")
    st.stop()

with sqlite3.connect(DB, timeout=15) as con:

    tables = {
        r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }

    if "monthly_economic_drafts" not in tables:
        st.error("Monthly draft table is missing.")
        st.stop()

    drafts = pd.read_sql_query(
        "SELECT * FROM monthly_economic_drafts",
        con
    )

if drafts.empty:
    st.info("Enter monthly economic data in Step 40 first.")
    st.stop()

drafts["month"] = drafts["month"].astype(str)

required = {
    "month",
    "inflation_yoy_pct",
    "nominal_wage_growth_yoy_pct",
    "usd_lkr",
    "fx_reserves_usd_bn"
}

if not required.issubset(drafts.columns):
    st.error("Required draft indicators are missing.")
    st.stop()


def to_number(value):
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return None
    return float(number)


def fmt(value, suffix=""):
    if value is None or pd.isna(value):
        return "Unavailable"
    return f"{float(value):,.2f}{suffix}"


st.subheader("1. Select Reporting Month")

selected_month = st.selectbox(
    "Select Monthly Economic Record",
    sorted(drafts["month"].unique(), reverse=True)
)

current = drafts.loc[
    drafts["month"] == selected_month
].iloc[0]

st.caption(
    "Selected record: Unverified user-entered SQLite draft."
)

st.divider()
st.subheader("2. Economic Indicators")

a, b, c, d = st.columns(4)

a.metric(
    "Inflation YoY",
    fmt(to_number(current["inflation_yoy_pct"]), "%")
)
b.metric(
    "Wage Growth YoY",
    fmt(
        to_number(current["nominal_wage_growth_yoy_pct"]),
        "%"
    )
)
c.metric(
    "USD/LKR",
    fmt(to_number(current["usd_lkr"]))
)
d.metric(
    "Foreign Reserves",
    fmt(
        to_number(current["fx_reserves_usd_bn"]),
        " USD bn"
    )
)

# Build comparison data in memory only.
# Historical records are retrospective candidate data.
# New observations remain unverified drafts.
monthly = {}

if HISTORY.exists():
    historical = pd.read_csv(HISTORY)

    needed = {
        "month", "usd_lkr", "fx_reserves_usd_bn"
    }

    if needed.issubset(historical.columns):
        for _, row in historical.iterrows():
            month = str(row["month"])

            if month <= "2025-12":
                monthly[month] = {
                    "usd_lkr": to_number(row["usd_lkr"]),
                    "fx_reserves_usd_bn":
                        to_number(row["fx_reserves_usd_bn"])
                }

for _, row in drafts.iterrows():

    month = str(row["month"])

    if month >= "2026-01":
        monthly[month] = {
            "usd_lkr": to_number(row["usd_lkr"]),
            "fx_reserves_usd_bn":
                to_number(row["fx_reserves_usd_bn"])
        }

comparison_month = str(
    pd.Period(selected_month, freq="M") - 3
)

previous = monthly.get(comparison_month, {})

st.divider()
st.subheader("3. Three-Month Economic Changes")

result = calculate_risk(
    inflation=to_number(current["inflation_yoy_pct"]),
    wage_growth=to_number(
        current["nominal_wage_growth_yoy_pct"]
    ),
    usd_lkr=to_number(current["usd_lkr"]),
    usd_lkr_3m_ago=previous.get("usd_lkr"),
    reserves=to_number(current["fx_reserves_usd_bn"]),
    reserves_3m_ago=previous.get("fx_reserves_usd_bn")
)

x, y, z = st.columns(3)

x.metric(
    "Currency Change (3M)",
    fmt(result["currency_change_3m"], "%")
)
y.metric(
    "Reserve Change (3M)",
    fmt(result["reserve_change_3m"], "%")
)
z.metric(
    "Estimated Real Wage Growth",
    fmt(result["real_wage_growth"], "%")
)

st.caption(
    f"Comparison month: {comparison_month}. "
    "Changes are calculated only when the exact "
    "three-month-prior observation is available."
)

st.divider()
st.subheader("4. Preliminary Economic Pressure Score")

available = result["available"]
triggered = result["triggered"]
score = result["score"]

left, middle, right = st.columns(3)

left.metric("Available Indicators", f"{available}/4")
middle.metric("Triggered Indicators", triggered)

if score is None:
    right.metric("Pressure Score", "Unavailable")
    st.warning(
        "At least three valid indicators are required "
        "to calculate a combined score."
    )
else:
    right.metric("Pressure Score", f"{score:.1f}/100")
    st.progress(max(0, min(1, score / 100)))

    st.write(
        f"{triggered} of {available} available indicators "
        "exceeded their experimental thresholds."
    )

    if available < 4:
        st.warning(
            "Partial indicator coverage. This score "
            "cannot be compared directly with a score "
            "using a different set of indicators."
        )

st.caption(
    "This score measures the proportion of available "
    "indicators crossing thresholds. It is not an "
    "estimated probability of economic crisis."
)

st.divider()
st.subheader("5. Individual Economic Stress Signals")

rows = []

for signal in result["signals"]:

    triggered_value = signal["triggered"]

    if triggered_value is None:
        status = "Insufficient Data"
    elif triggered_value:
        status = "Threshold Exceeded"
    else:
        status = "Threshold Not Exceeded"

    rows.append({
        "Indicator": signal["indicator"],
        "Calculated Value": signal["value"],
        "Research Threshold": signal["threshold"],
        "Status": status
    })

st.dataframe(
    pd.DataFrame(rows),
    use_container_width=True,
    hide_index=True
)

st.divider()
st.subheader("6. Research Limitations")

st.info(
    "Historical comparison values come from a "
    "retrospective dataset. Current draft values "
    "are not independently verified. "
    "The score is intended for exploratory "
    "monitoring rather than historical predictive claims."
)

st.write(
    "Before using this framework for crisis prediction, "
    "the project needs publication-aware backtesting, "
    "threshold calibration, sensitivity analysis, "
    "false-alarm evaluation and out-of-sample validation."
)

st.caption(
    "SL-EWRIS | Preliminary Economic Risk Screening | "
    "Read-only dashboard"
)
