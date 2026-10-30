from pathlib import Path
from datetime import date
import calendar

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]

HISTORY = (
    ROOT / "outputs" / "cbsl_preparation"
    / "combined_external_review_2014_2025.csv"
)

st.set_page_config(
    page_title="SL-EWRIS | Monthly Monitoring",
    page_icon="📈",
    layout="wide"
)

st.title("Monthly Economic Monitoring")
st.caption("SL-EWRIS | Economic Data Entry and Screening")

st.warning(
    "Research prototype: results are descriptive screening "
    "indicators, not validated financial-crisis predictions. "
    "Entries are temporary and are not saved to SQLite."
)

if "monitoring_entries" not in st.session_state:
    st.session_state.monitoring_entries = {}

if HISTORY.exists():
    history = pd.read_csv(HISTORY)
    history["month"] = history["month"].astype(str)
else:
    history = pd.DataFrame(
        columns=["month", "usd_lkr", "fx_reserves_usd_bn"]
    )
    st.info(
        "Historical external data not found. "
        "Monthly inputs can still be previewed."
    )

st.subheader("1. Enter New Monthly Economic Data")

with st.form("monthly_economic_form"):

    month_date = st.date_input(
        "Reporting month",
        value=date(2026, 1, 1),
        min_value=date(2026, 1, 1),
        max_value=date(2035, 12, 31)
    )

    st.caption(
        "Use the first day of the reporting month. "
        "Only the year and month are used."
    )

    c1, c2 = st.columns(2)

    with c1:
        has_inflation = st.checkbox(
            "Inflation rate available", value=True
        )
        inflation = st.number_input(
            "Headline YoY Inflation (%)",
            value=5.0,
            step=0.1,
            disabled=not has_inflation
        )

        has_fx = st.checkbox(
            "USD/LKR available", value=True
        )
        usd_lkr = st.number_input(
            "Monthly Average USD/LKR",
            min_value=0.01,
            value=310.0,
            step=0.5,
            disabled=not has_fx
        )

    with c2:
        has_wages = st.checkbox(
            "Nominal wage growth available",
            value=True
        )
        wages = st.number_input(
            "Nominal Wage Growth YoY (%)",
            value=0.0,
            step=0.1,
            disabled=not has_wages
        )

        has_reserves = st.checkbox(
            "Foreign reserves available",
            value=True
        )
        reserves = st.number_input(
            "Gross Official Reserves (USD billions)",
            min_value=0.001,
            value=6.0,
            step=0.1,
            disabled=not has_reserves
        )

    source_note = st.text_input(
        "Official source / reference",
        placeholder="CBSL or DCS publication URL / notes"
    )

    submitted = st.form_submit_button(
        "Analyze This Month",
        type="primary"
    )

if submitted:
    month = month_date.strftime("%Y-%m")

    entry = {
        "month": month,
        "inflation_yoy_pct": (
            float(inflation) if has_inflation else None
        ),
        "wage_growth_yoy_pct": (
            float(wages) if has_wages else None
        ),
        "usd_lkr": (
            float(usd_lkr) if has_fx else None
        ),
        "fx_reserves_usd_bn": (
            float(reserves) if has_reserves else None
        ),
        "source_note": source_note.strip(),
        "verification_status": "Unverified user input"
    }

    st.session_state.monitoring_entries[month] = entry

    st.success(
        f"{month} data accepted for temporary analysis."
    )

entries = st.session_state.monitoring_entries

if not entries:
    st.info(
        "Enter a reporting month and click Analyze This Month."
    )
    st.stop()

st.divider()
st.subheader("2. Economic Situation Analysis")

selected_month = st.selectbox(
    "Select entered month",
    sorted(entries.keys(), reverse=True)
)

current = entries[selected_month]

def display(value, suffix="", decimals=2):
    if value is None:
        return "Not available"
    return f"{value:,.{decimals}f}{suffix}"

a, b, c, d = st.columns(4)

a.metric(
    "Inflation YoY",
    display(current["inflation_yoy_pct"], "%")
)
b.metric(
    "Wage Growth YoY",
    display(current["wage_growth_yoy_pct"], "%")
)
c.metric(
    "USD/LKR",
    display(current["usd_lkr"])
)
d.metric(
    "Gross Reserves",
    display(current["fx_reserves_usd_bn"], " bn")
)

st.subheader("3. Purchasing Power Analysis")

inflation = current["inflation_yoy_pct"]
wages = current["wage_growth_yoy_pct"]

if inflation is not None and wages is not None:
    if inflation <= -100:
        st.error("Inflation input must be greater than -100%.")
    else:
        real_wage_growth = (
            (1 + wages / 100) /
            (1 + inflation / 100) - 1
        ) * 100

        st.metric(
            "Estimated Real Wage Growth YoY",
            f"{real_wage_growth:.2f}%"
        )

        if real_wage_growth < 0:
            st.warning(
                "Estimated purchasing power is declining."
            )
        else:
            st.info(
                "Estimated real wage growth is non-negative."
            )

        st.caption(
            "Nominal wage growth and inflation must cover "
            "comparable populations and periods."
        )
else:
    st.info(
        "Inflation and wage growth are both required "
        "for real wage growth calculation."
    )

st.divider()
st.subheader("4. External Financial Stress")

# Monthly comparisons are made ONLY when the previous
# calendar month's observation is available.

previous_month = str(
    pd.Period(selected_month, freq="M") - 1
)

previous = entries.get(previous_month)

if previous is None and not history.empty:
    matching = history[
        history["month"] == previous_month
    ]

    if len(matching) == 1:
        row = matching.iloc[0]
        previous = {
            "usd_lkr": pd.to_numeric(
                row.get("usd_lkr"), errors="coerce"
            ),
            "fx_reserves_usd_bn": pd.to_numeric(
                row.get("fx_reserves_usd_bn"),
                errors="coerce"
            )
        }

def monthly_change(column):
    if previous is None:
        return None

    old = previous.get(column)
    new = current.get(column)

    if (
        new is None
        or old is None
        or pd.isna(old)
        or old <= 0
    ):
        return None

    return (new / float(old) - 1) * 100

fx_change = monthly_change("usd_lkr")
reserve_change = monthly_change("fx_reserves_usd_bn")

x, y = st.columns(2)

x.metric(
    "Monthly USD/LKR Change",
    display(fx_change, "%")
)
y.metric(
    "Monthly Reserve Change",
    display(reserve_change, "%")
)

flags = []

# Illustrative one-month screening thresholds.
if fx_change is not None and fx_change >= 10:
    flags.append("Rapid monthly currency depreciation")

if reserve_change is not None and reserve_change <= -15:
    flags.append("Rapid monthly reserve depletion")

if flags:
    st.warning(
        "Illustrative stress signals: " + "; ".join(flags)
    )
else:
    st.info(
        "No computed monthly threshold exceeded, "
        "or insufficient comparable data."
    )

if previous is None:
    st.caption(
        "Previous calendar month is unavailable. "
        "Monthly changes were not calculated. "
        "A comparison across a multi-month gap "
        "would not be a monthly change."
    )

st.caption(
    "Screening thresholds are exploratory and unvalidated. "
    "The number of flags is not a crisis probability."
)

st.divider()
st.subheader("5. Data Entered During This Session")

temp_df = pd.DataFrame(
    list(entries.values())
).sort_values("month")

st.dataframe(
    temp_df,
    use_container_width=True,
    hide_index=True
)

st.info(
    "Session-only preview. Data are not stored "
    "in the database, and may disappear when "
    "the Streamlit session is restarted."
)

st.caption(
    "All manually entered data are unverified until "
    "checked against official CBSL/DCS sources."
)
