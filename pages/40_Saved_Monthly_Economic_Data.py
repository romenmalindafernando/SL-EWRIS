from datetime import date
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from database import connect_database

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="SL-EWRIS | Saved Monthly Data",
    page_icon="💾",
    layout="wide"
)

st.title("Monthly Economic Data — Neon PostgreSQL Storage")

st.info(
    "This page stores draft monthly observations separately "
    "from the historical research dataset. Saved values are "
    "not automatically verified or used for crisis predictions."
)


def connect():
    con = connect_database()
    return con


def initialize():
    with connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS monthly_economic_drafts (
                month TEXT PRIMARY KEY,
                inflation_yoy_pct REAL,
                nominal_wage_growth_yoy_pct REAL,
                usd_lkr REAL,
                fx_reserves_usd_bn REAL,
                source_note TEXT NOT NULL DEFAULT '',
                verification_status TEXT NOT NULL
                    DEFAULT 'Unverified',
                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,
                CHECK (length(month) = 7),
                CHECK (
                    inflation_yoy_pct IS NULL
                    OR inflation_yoy_pct > -100
                ),
                CHECK (
                    nominal_wage_growth_yoy_pct IS NULL
                    OR nominal_wage_growth_yoy_pct > -100
                ),
                CHECK (
                    usd_lkr IS NULL OR usd_lkr > 0
                ),
                CHECK (
                    fx_reserves_usd_bn IS NULL
                    OR fx_reserves_usd_bn > 0
                ),
                CHECK (
                    verification_status = 'Unverified'
                )
            )
        """)


def load_drafts():
    with connect() as con:
        return pd.read_sql_query(
            """
            SELECT *
            FROM monthly_economic_drafts
            ORDER BY month DESC
            """,
            con
        )


def save_draft(record):
    with connect() as con:
        con.execute(
            """
            INSERT INTO monthly_economic_drafts (
                month,
                inflation_yoy_pct,
                nominal_wage_growth_yoy_pct,
                usd_lkr,
                fx_reserves_usd_bn,
                source_note,
                verification_status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'Unverified')

            ON CONFLICT(month) DO UPDATE SET
                inflation_yoy_pct = excluded.inflation_yoy_pct,
                nominal_wage_growth_yoy_pct =
                    excluded.nominal_wage_growth_yoy_pct,
                usd_lkr = excluded.usd_lkr,
                fx_reserves_usd_bn =
                    excluded.fx_reserves_usd_bn,
                source_note = excluded.source_note,
                verification_status = 'Unverified',
                updated_at = CURRENT_TIMESTAMP
            """,
            record
        )


initialize()

st.subheader("1. Enter Monthly Economic Data")

with st.form("sqlite_monthly_entry"):

    reporting_date = st.date_input(
        "Reporting Month",
        value=date(2026, 10, 1),
        min_value=date(2026, 1, 1),
        max_value=date(2035, 12, 31)
    )

    st.caption(
        "The reporting month is the unique identifier. "
        "Saving the same month again replaces its previous "
        "draft values."
    )

    left, right = st.columns(2)

    with left:
        use_inflation = st.checkbox(
            "Inflation Data Available",
            value=True
        )
        inflation = st.number_input(
            "Headline YoY Inflation (%)",
            value=5.0,
            step=0.1,
            disabled=not use_inflation
        )

        use_wages = st.checkbox(
            "Nominal Wage Growth Available",
            value=True
        )
        wage_growth = st.number_input(
            "Nominal Wage Growth YoY (%)",
            value=3.0,
            step=0.1,
            disabled=not use_wages
        )

    with right:
        use_fx = st.checkbox(
            "USD/LKR Data Available",
            value=True
        )
        usd_lkr = st.number_input(
            "Monthly Average USD/LKR",
            min_value=0.01,
            value=310.0,
            step=0.1,
            disabled=not use_fx
        )

        use_reserves = st.checkbox(
            "Foreign Reserves Available",
            value=True
        )
        reserves = st.number_input(
            "Gross Official Reserves (USD billions)",
            min_value=0.001,
            value=6.0,
            step=0.1,
            disabled=not use_reserves
        )

    source_note = st.text_area(
        "Source Notes / Official Reference",
        placeholder="CBSL / DCS source URL, publication details..."
    )

    submitted = st.form_submit_button(
        "Save Monthly Draft to PostgreSQL",
        type="primary"
    )

if submitted:
    month = reporting_date.strftime("%Y-%m")

    record = (
        month,
        float(inflation) if use_inflation else None,
        float(wage_growth) if use_wages else None,
        float(usd_lkr) if use_fx else None,
        float(reserves) if use_reserves else None,
        source_note.strip()
    )

    available = record[1:5]

    if all(value is None for value in available):
        st.error(
            "Please provide at least one economic indicator."
        )

    elif (
        (record[1] is not None and record[1] <= -100)
        or (record[2] is not None and record[2] <= -100)
    ):
        st.error(
            "Inflation and nominal wage growth must be "
            "greater than -100%."
        )

    else:
        try:
            save_draft(record)
            st.success(
                f"{month} successfully saved to PostgreSQL "
                "as Unverified."
            )

        except psycopg.Error as exc:
            st.error(f"Database error: {exc}")

st.divider()
st.subheader("2. Saved Monthly Records")

try:
    data = load_drafts()
except psycopg.Error as exc:
    st.error(f"Unable to read drafts: {exc}")
    st.stop()

if data.empty:
    st.warning("No monthly drafts saved yet.")
    st.stop()

st.metric("Total Saved Months", len(data))

st.dataframe(
    data,
    use_container_width=True,
    hide_index=True
)

st.divider()
st.subheader("3. View a Saved Month")

selected_month = st.selectbox(
    "Select Month",
    data["month"].tolist()
)

selected = data.loc[
    data["month"] == selected_month
].iloc[0]

c1, c2, c3, c4 = st.columns(4)

def show_number(value, suffix="", digits=2):
    if pd.isna(value):
        return "Unavailable"
    return f"{value:,.{digits}f}{suffix}"

c1.metric(
    "Inflation",
    show_number(selected["inflation_yoy_pct"], "%")
)

c2.metric(
    "Nominal Wage Growth",
    show_number(
        selected["nominal_wage_growth_yoy_pct"], "%"
    )
)

c3.metric(
    "USD/LKR",
    show_number(selected["usd_lkr"])
)

c4.metric(
    "Gross Reserves",
    show_number(selected["fx_reserves_usd_bn"], " bn")
)

inflation_value = selected["inflation_yoy_pct"]
wage_value = selected["nominal_wage_growth_yoy_pct"]

if pd.notna(inflation_value) and pd.notna(wage_value):
    real_growth = (
        (1 + wage_value / 100)
        / (1 + inflation_value / 100)
        - 1
    ) * 100

    st.metric(
        "Estimated Real Wage Growth",
        f"{real_growth:.2f}%"
    )

    st.caption(
        "This comparison is meaningful only when the "
        "wage and inflation series cover comparable "
        "periods and populations."
    )

st.write(
    "**Verification Status:**",
    selected["verification_status"]
)

st.write(
    "**Source Notes:**",
    selected["source_note"] or "Not provided"
)

st.caption(
    "This page does not modify economic_monthly. "
    "It does not automatically treat draft values "
    "as officially verified or generate crisis probabilities."
)
