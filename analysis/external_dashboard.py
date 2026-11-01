
# ============================================================
# SL-EWRIS — STEP 14
# EXTERNAL SECTOR STREAMLIT DASHBOARD
#
# Displays foreign reserves, USD/LKR movements,
# exchange-rate volatility and data availability.
#
# Does NOT estimate financial-crisis probabilities.
# ============================================================

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from database import connect_database

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]

NAVY = "#142B49"
TEAL = "#0D9488"
AMBER = "#E5A23A"
CORAL = "#E26B69"


# ------------------------------------------------------------
# 1. LOAD EXTERNAL DATA
# ------------------------------------------------------------

def load_external_dashboard_data():

    with connect_database() as connection:

        df = pd.read_sql_query(
            """
            SELECT
                month,
                fx_reserves_usd_bn,
                usd_lkr
            FROM economic_monthly
            ORDER BY month
            """,
            connection
        )

    if df.empty:
        raise ValueError("The economic database is empty.")

    if df["month"].isna().any():
        raise ValueError("Database contains missing months.")

    df["date"] = pd.to_datetime(
        df["month"] + "-01",
        errors="raise"
    )

    if df["date"].duplicated().any():
        raise ValueError("Duplicate months detected.")

    df = df.set_index("date").sort_index()

    # Insert missing calendar months as empty rows.
    # No economic values are invented.
    calendar = pd.date_range(
        df.index.min(),
        df.index.max(),
        freq="MS"
    )

    df = df.reindex(calendar)
    df.index.name = "date"
    df["month"] = df.index.strftime("%Y-%m")

    for column in ["fx_reserves_usd_bn", "usd_lkr"]:

        df[column] = pd.to_numeric(
            df[column],
            errors="raise"
        )

        valid = df[column].dropna()

        if not np.isfinite(valid).all():
            raise ValueError(
                f"Non-finite numbers found in {column}"
            )

        if (valid <= 0).any():
            raise ValueError(
                f"Non-positive observations in {column}"
            )

    return df.reset_index()


# ------------------------------------------------------------
# 2. CALCULATE EXTERNAL INDICATORS
# ------------------------------------------------------------

def calculate_external_dashboard_indicators(df):

    df = df.copy()

    reserves = df["fx_reserves_usd_bn"]
    exchange = df["usd_lkr"]

    # fill_method=None ensures missing observations
    # are never forward-filled before calculation.
    df["reserves_1m_pct"] = (
        reserves.pct_change(
            periods=1,
            fill_method=None
        ) * 100
    )

    df["reserves_3m_pct"] = (
        reserves.pct_change(
            periods=3,
            fill_method=None
        ) * 100
    )

    df["exchange_1m_pct"] = (
        exchange.pct_change(
            periods=1,
            fill_method=None
        ) * 100
    )

    df["exchange_12m_pct"] = (
        exchange.pct_change(
            periods=12,
            fill_method=None
        ) * 100
    )

    df["fx_volatility_3m_pp"] = (
        df["exchange_1m_pct"]
        .rolling(3, min_periods=3)
        .std(ddof=1)
    )

    # Illustrative monitoring conditions.
    df["reserve_warning"] = (
        df["reserves_3m_pct"] <= -10
    )

    df["depreciation_warning"] = (
        df["exchange_12m_pct"] >= 20
    )

    df["volatility_warning"] = (
        df["fx_volatility_3m_pp"] >= 5
    )

    return df


# ------------------------------------------------------------
# 3. CREATE A LINE CHART
# ------------------------------------------------------------

def make_external_chart(
    df,
    column,
    title,
    y_axis,
    color
):

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df[column],
            mode="lines+markers",
            name=title,
            line=dict(
                color=color,
                width=2.5
            ),
            marker=dict(size=4),
            connectgaps=False
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title="",
        yaxis_title=y_axis,
        template="plotly_white",
        height=390,
        margin=dict(
            l=35,
            r=20,
            t=55,
            b=35
        ),
        showlegend=False,
        hovermode="x unified"
    )

    return fig


# ------------------------------------------------------------
# 4. DISPLAY FORMATTED VALUES
# ------------------------------------------------------------

def display_number(value, digits=2, suffix=""):

    if pd.isna(value):
        return "Unavailable"

    return f"{value:,.{digits}f}{suffix}"


def show_last_observation(df, column, label, unit):

    available = df.dropna(subset=[column])

    if available.empty:
        st.metric(label, "Unavailable")
        st.caption("No verified observations stored.")
        return

    last = available.iloc[-1]

    st.metric(
        label,
        display_number(
            last[column],
            suffix=unit
        )
    )

    st.caption(
        f"Last observation: {last['month']}"
    )


# ------------------------------------------------------------
# 5. RENDER STREAMLIT DASHBOARD
# ------------------------------------------------------------

def render_external_dashboard():

    st.divider()

    st.header("External Sector Monitor")

    st.caption(
        "CBSL external-sector indicators | "
        "Descriptive economic monitoring"
    )

    st.info(
        "These indicators describe observed external "
        "economic conditions. They are not validated "
        "probabilities of a national financial crisis."
    )

    try:
        df = load_external_dashboard_data()
        df = calculate_external_dashboard_indicators(df)

    except (
        FileNotFoundError,
        ValueError,
        psycopg.Error
    ) as error:

        st.error(
            f"Unable to load external-sector data: {error}"
        )
        return

    # ----------------------------------------
    # DATA AVAILABILITY
    # ----------------------------------------

    total = len(df)

    reserve_count = int(
        df["fx_reserves_usd_bn"].notna().sum()
    )

    exchange_count = int(
        df["usd_lkr"].notna().sum()
    )

    st.subheader("Data Availability")

    col1, col2, col3 = st.columns(3)

    col1.metric("Stored months", total)

    col2.metric(
        "Reserve observations",
        reserve_count
    )

    col3.metric(
        "Exchange-rate observations",
        exchange_count
    )

    if reserve_count == 0 and exchange_count == 0:

        st.warning(
            "No verified external-sector observations "
            "have been imported. Add the monthly CBSL "
            "data using import_external_indicators.py."
        )

        return

    # ----------------------------------------
    # DATE RANGE
    # ----------------------------------------

    first_year = int(df["date"].dt.year.min())
    last_year = int(df["date"].dt.year.max())

    start_year, end_year = st.slider(
        "Historical display period",
        min_value=first_year,
        max_value=last_year,
        value=(first_year, last_year),
        key="external_dashboard_year_range"
    )

    selected = df[
        df["date"].dt.year.between(
            start_year, end_year
        )
    ].copy()

    # ----------------------------------------
    # LATEST AVAILABLE OBSERVATIONS
    # ----------------------------------------

    st.subheader("Latest Available Indicators")

    left, right = st.columns(2)

    with left:
        show_last_observation(
            df,
            "fx_reserves_usd_bn",
            "Gross Official Reserves",
            " USD bn"
        )

    with right:
        show_last_observation(
            df,
            "usd_lkr",
            "USD/LKR Exchange Rate",
            " LKR"
        )

    # ----------------------------------------
    # FOREIGN RESERVE CHART
    # ----------------------------------------

    st.subheader("Foreign Exchange Reserves")

    if selected["fx_reserves_usd_bn"].notna().any():

        reserve_chart = make_external_chart(
            selected,
            "fx_reserves_usd_bn",
            "Gross Official Reserves",
            "USD billions",
            NAVY
        )

        st.plotly_chart(
            reserve_chart,
            use_container_width=True,
            key="external_reserves_chart"
        )

    else:
        st.info(
            "No reserve observations are available "
            "in the selected period."
        )

    # ----------------------------------------
    # EXCHANGE RATE CHART
    # ----------------------------------------

    st.subheader("USD/LKR Exchange Rate")

    if selected["usd_lkr"].notna().any():

        exchange_chart = make_external_chart(
            selected,
            "usd_lkr",
            "USD/LKR Exchange Rate",
            "LKR per USD",
            TEAL
        )

        st.plotly_chart(
            exchange_chart,
            use_container_width=True,
            key="external_exchange_chart"
        )

    else:
        st.info(
            "No exchange-rate observations are "
            "available in the selected period."
        )

    # ----------------------------------------
    # LATEST MONTH MONITORING ASSESSMENT
    # ----------------------------------------

    st.subheader("Latest Month Assessment")

    latest = df.iloc[-1]
    month = latest["month"]

    st.caption(
        f"Assessment month: {month}"
    )

    checks = [
        (
            "Three-month reserve change",
            "reserves_3m_pct",
            "reserve_warning",
            "Decline of at least 10%"
        ),
        (
            "Annual USD/LKR change",
            "exchange_12m_pct",
            "depreciation_warning",
            "Depreciation of at least 20%"
        ),
        (
            "Three-month FX volatility",
            "fx_volatility_3m_pp",
            "volatility_warning",
            "Standard deviation of at least 5 pp"
        ),
    ]

    rows = []

    for (
        label,
        value_column,
        warning_column,
        threshold
    ) in checks:

        value = latest[value_column]

        if pd.isna(value):
            status = "Unavailable"

        elif bool(latest[warning_column]):
            status = "Warning"

        else:
            status = "No threshold breach"

        rows.append({
            "Indicator": label,
            "Value": display_number(
                value,
                suffix="%" if "volatility" not in
                value_column else " pp"
            ),
            "Monitoring Status": status,
            "Illustrative Threshold": threshold
        })

    assessment = pd.DataFrame(rows)

    st.dataframe(
        assessment,
        use_container_width=True,
        hide_index=True
    )

    assessed = sum(
        status != "Unavailable"
        for status in assessment["Monitoring Status"]
    )

    st.caption(
        f"{assessed} of 3 monitoring indicators "
        f"could be assessed for {month}."
    )

    if assessed == 0:

        st.warning(
            "External vulnerability cannot currently "
            "be assessed for this reporting month. "
            "Missing values do not mean low risk."
        )

    elif assessed < 3:

        st.warning(
            "The external monitoring assessment is "
            "partial because some observations "
            "or required historical comparisons "
            "are unavailable."
        )

    # ----------------------------------------
    # DATA TABLE AND DOWNLOAD
    # ----------------------------------------

    with st.expander("View external-sector dataset"):

        columns = [
            "month",
            "fx_reserves_usd_bn",
            "usd_lkr",
            "reserves_1m_pct",
            "reserves_3m_pct",
            "exchange_1m_pct",
            "exchange_12m_pct",
            "fx_volatility_3m_pp"
        ]

        st.dataframe(
            selected[columns],
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            label="Download External-Sector CSV",
            data=selected[columns].to_csv(
                index=False
            ).encode("utf-8"),
            file_name="external_sector_monitor.csv",
            mime="text/csv",
            key="download_external_monitor"
        )

    st.caption(
        "Methodology: monthly percentage changes "
        "use the previous month's observation; "
        "annual changes compare with the same "
        "month one year earlier. Missing data "
        "are never automatically filled. "
        "Warning thresholds are illustrative, "
        "not officially calibrated."
    )
