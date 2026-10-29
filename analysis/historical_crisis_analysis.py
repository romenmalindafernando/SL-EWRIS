
# ============================================================
# SL-EWRIS — STEP 16
# HISTORICAL ECONOMIC STRESS ANALYSIS: 2020–2023
#
# Uses verified CBSL/DCS observations stored in SQLite.
# Retrospective descriptive analysis ONLY.
# Not a validated financial-crisis prediction model.
# ============================================================

from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "database" / "economic_risk.db"
OUTPUT = ROOT / "outputs" / "historical_crisis"

OUTPUT.mkdir(parents=True, exist_ok=True)

NAVY = "#142B49"
AMBER = "#E5A23A"
TEAL = "#0D9488"
VIOLET = "#7C70D6"
CORAL = "#E26B69"


# ------------------------------------------------------------
# 1. LOAD MONTHLY ECONOMIC DATA
# ------------------------------------------------------------

def load_data():

    if not DATABASE.exists():
        raise FileNotFoundError(
            "Database not found. Run seed_database.py first."
        )

    with sqlite3.connect(DATABASE) as conn:

        df = pd.read_sql_query(
            """
            SELECT
                month,
                headline_yoy_pct,
                food_yoy_pct,
                nonfood_yoy_pct,
                public_real_ncpi_raw,
                informal_real_ncpi_raw,
                fx_reserves_usd_bn,
                usd_lkr
            FROM economic_monthly
            ORDER BY month
            """,
            conn
        )

    if df.empty:
        raise ValueError("The database contains no data.")

    if df["month"].isna().any():
        raise ValueError("Missing observation dates.")

    if df["month"].duplicated().any():
        raise ValueError("Duplicate observation months.")

    valid_month = df["month"].astype(str).str.fullmatch(
        r"\d{4}-(0[1-9]|1[0-2])"
    )

    if not valid_month.all():
        raise ValueError("Invalid YYYY-MM date format.")

    df["date"] = pd.to_datetime(
        df["month"] + "-01",
        format="%Y-%m-%d"
    )

    df = df.set_index("date").sort_index()

    # Maintain calendar-month spacing for lag calculations.
    full_dates = pd.date_range(
        df.index.min(),
        df.index.max(),
        freq="MS"
    )

    df = df.reindex(full_dates)
    df.index.name = "date"
    df["month"] = df.index.strftime("%Y-%m")

    numerical = [
        "headline_yoy_pct",
        "food_yoy_pct",
        "nonfood_yoy_pct",
        "public_real_ncpi_raw",
        "informal_real_ncpi_raw",
        "fx_reserves_usd_bn",
        "usd_lkr",
    ]

    for col in numerical:

        df[col] = pd.to_numeric(
            df[col],
            errors="raise"
        )

        if not np.isfinite(df[col].dropna()).all():
            raise ValueError(
                f"Invalid non-finite values in {col}"
            )

    for col in [
        "public_real_ncpi_raw",
        "informal_real_ncpi_raw",
        "fx_reserves_usd_bn",
        "usd_lkr",
    ]:

        if (df[col].dropna() <= 0).any():
            raise ValueError(
                f"Non-positive index or observation: {col}"
            )

    return df.reset_index()


# ------------------------------------------------------------
# 2. CLASSIFY HISTORICAL CALENDAR PERIODS
# ------------------------------------------------------------

def period_label(date):

    year = date.year

    if year == 2020:
        return "2020 - Earlier conditions"

    if year == 2021:
        return "2021 - Pre-crisis period"

    if year == 2022:
        return "2022 - Crisis period"

    if year == 2023:
        return "2023 - Aftermath"

    return "Other"


# ------------------------------------------------------------
# 3. CALCULATE DESCRIPTIVE INDICATORS
# ------------------------------------------------------------

def compute_indicators(df):

    df = df.copy()

    # Moving average of official headline YoY inflation.
    df["inflation_3m_average_pct"] = (
        df["headline_yoy_pct"]
        .rolling(3, min_periods=3)
        .mean()
    )

    # Change between consecutive, non-overlapping
    # three-month averages, in percentage points.
    df["inflation_momentum_pp"] = (
        df["inflation_3m_average_pct"]
        - df["inflation_3m_average_pct"].shift(3)
    )

    # One-year change in official NCPI-adjusted
    # real wage-rate indices.
    for sector in ["public", "informal"]:

        name = f"{sector}_real_ncpi_raw"

        current = df[name]
        prior = current.shift(12)

        df[f"{sector}_real_wage_yoy_pct"] = (
            100 * (current / prior - 1)
        ).where(
            current.notna()
            & prior.notna()
            & (prior > 0)
        )

    # Reserves: end-of-month gross official reserves.
    reserves = df["fx_reserves_usd_bn"]

    df["reserves_3m_change_pct"] = (
        reserves.pct_change(
            periods=3,
            fill_method=None
        ) * 100
    )

    # Exchange rate: consistently defined monthly
    # average LKR per USD.
    exchange = df["usd_lkr"]

    df["usd_lkr_12m_change_pct"] = (
        exchange.pct_change(
            periods=12,
            fill_method=None
        ) * 100
    )

    # Observation-based descriptive flags.
    # Thresholds are illustrative, not crisis calibrated.
    df["high_inflation_flag"] = (
        df["inflation_3m_average_pct"] >= 10
    ).where(
        df["inflation_3m_average_pct"].notna()
    )

    df["public_real_wage_decline_flag"] = (
        df["public_real_wage_yoy_pct"] < 0
    ).where(
        df["public_real_wage_yoy_pct"].notna()
    )

    df["informal_real_wage_decline_flag"] = (
        df["informal_real_wage_yoy_pct"] < 0
    ).where(
        df["informal_real_wage_yoy_pct"].notna()
    )

    df["reserve_decline_flag"] = (
        df["reserves_3m_change_pct"] <= -10
    ).where(
        df["reserves_3m_change_pct"].notna()
    )

    df["currency_depreciation_flag"] = (
        df["usd_lkr_12m_change_pct"] >= 20
    ).where(
        df["usd_lkr_12m_change_pct"].notna()
    )

    df["historical_period"] = (
        df["date"].apply(period_label)
    )

    return df


# ------------------------------------------------------------
# 4. ANNUAL SUMMARY
# ------------------------------------------------------------

def annual_summary(df):

    historical = df[
        df["date"].dt.year.between(2020, 2023)
    ].copy()

    historical["year"] = historical["date"].dt.year

    # Means use available observations only.
    # The availability columns must be inspected.
    annual = historical.groupby(
        "year",
        as_index=False
    ).agg(
        months=("month", "count"),
        avg_headline_inflation_pct=(
            "headline_yoy_pct", "mean"
        ),
        avg_food_inflation_pct=(
            "food_yoy_pct", "mean"
        ),
        avg_public_real_wage_yoy_pct=(
            "public_real_wage_yoy_pct", "mean"
        ),
        avg_informal_real_wage_yoy_pct=(
            "informal_real_wage_yoy_pct", "mean"
        ),
        avg_reserves_usd_bn=(
            "fx_reserves_usd_bn", "mean"
        ),
        avg_usd_lkr=(
            "usd_lkr", "mean"
        ),
        reserves_months_available=(
            "fx_reserves_usd_bn", "count"
        ),
        exchange_months_available=(
            "usd_lkr", "count"
        ),
    )

    return historical, annual


# ------------------------------------------------------------
# 5. MONTHLY INFLATION GRAPH
# ------------------------------------------------------------

def plot_inflation(historical):

    fig, ax = plt.subplots(figsize=(12, 5.5))

    ax.plot(
        historical["date"],
        historical["headline_yoy_pct"],
        color=NAVY,
        linewidth=2.3,
        label="Headline inflation"
    )

    ax.plot(
        historical["date"],
        historical["food_yoy_pct"],
        color=AMBER,
        linewidth=1.7,
        label="Food inflation"
    )

    ax.axhline(
        0,
        color="gray",
        linestyle="--",
        linewidth=0.8
    )

    ax.set_title(
        "Sri Lanka: Inflation Before and During "
        "the 2022 Crisis",
        color=NAVY,
        fontweight="bold"
    )

    ax.set_ylabel("Year-on-year inflation (%)")
    ax.set_xlabel("")
    ax.legend(frameon=False)
    ax.grid(alpha=0.2)

    fig.tight_layout()

    fig.savefig(
        OUTPUT / "01_historical_inflation.png",
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(fig)


# ------------------------------------------------------------
# 6. REAL WAGE-RATE GRAPH
# ------------------------------------------------------------

def plot_real_wages(historical):

    fig, ax = plt.subplots(figsize=(12, 5.5))

    ax.plot(
        historical["date"],
        historical["public_real_ncpi_raw"],
        color=VIOLET,
        linewidth=2.1,
        label="Public sector"
    )

    ax.plot(
        historical["date"],
        historical["informal_real_ncpi_raw"],
        color=CORAL,
        linewidth=2.1,
        label="Informal private sector"
    )

    ax.set_title(
        "CBSL Official Real Wage-Rate Indices",
        color=NAVY,
        fontweight="bold"
    )

    ax.set_ylabel(
        "Published NCPI-adjusted wage-rate index"
    )

    ax.set_xlabel("")
    ax.legend(frameon=False)
    ax.grid(alpha=0.2)

    fig.tight_layout()

    fig.savefig(
        OUTPUT / "02_historical_real_wages.png",
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(fig)


# ------------------------------------------------------------
# 7. EXPORT HISTORICAL RESULTS
# ------------------------------------------------------------

def export_results(historical, annual):

    historical.to_csv(
        OUTPUT / "monthly_crisis_period_indicators.csv",
        index=False
    )

    annual.to_csv(
        OUTPUT / "annual_crisis_period_summary.csv",
        index=False
    )

    # Record observed flags without treating missing
    # measurements as a negative warning signal.
    flag_columns = [
        "month",
        "high_inflation_flag",
        "public_real_wage_decline_flag",
        "informal_real_wage_decline_flag",
        "reserve_decline_flag",
        "currency_depreciation_flag",
    ]

    historical[flag_columns].to_csv(
        OUTPUT / "historical_monitoring_flags.csv",
        index=False
    )


# ------------------------------------------------------------
# 8. MAIN PROGRAM
# ------------------------------------------------------------

def main():

    print("=" * 65)
    print("SL-EWRIS | STEP 16")
    print("HISTORICAL ECONOMIC STRESS: 2020-2023")
    print("=" * 65)

    df = load_data()

    print(f"Database months loaded: {len(df)}")

    df = compute_indicators(df)

    historical, annual = annual_summary(df)

    if len(historical) != 48:
        raise ValueError(
            "Expected 48 historical months for 2020-2023."
        )

    print("\nANNUAL ECONOMIC SUMMARY")
    print(
        annual.round(2).to_string(
            index=False,
            na_rep="Unavailable"
        )
    )

    print("\nEXTERNAL OBSERVATIONS AVAILABLE")

    print(
        "Reserve months:",
        historical["fx_reserves_usd_bn"].notna().sum()
    )

    print(
        "Exchange-rate months:",
        historical["usd_lkr"].notna().sum()
    )

    if historical[
        ["fx_reserves_usd_bn", "usd_lkr"]
    ].isna().any().any():

        print(
            "\n[NOTICE] External-sector data incomplete. "
            "No missing observations were estimated."
        )

    export_results(historical, annual)
    plot_inflation(historical)
    plot_real_wages(historical)

    print("\n[PASS] Historical analysis completed.")
    print("Outputs saved to:", OUTPUT)

    print(
        "\nIMPORTANT: This is retrospective descriptive "
        "analysis, not a validated pre-crisis forecast."
    )


if __name__ == "__main__":
    main()
