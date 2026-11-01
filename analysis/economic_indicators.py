
# ============================================================
# SL-EWRIS — SRI LANKA ECONOMIC RISK MONITORING SYSTEM
#
# STEP 7: ECONOMIC INDICATOR ANALYSIS
#
# Data: CBSL / DCS historical observations
# Period: January 2014 onward
#
# Important:
# These are descriptive economic indicators.
# They are NOT validated financial crisis probabilities.
# ============================================================

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from database import connect_database

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ------------------------------------------------------------
# 1. PROJECT PATHS
# ------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]


OUTPUT_DIR = ROOT / "outputs" / "indicators"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# 2. PROFESSIONAL CHART COLOURS
# ------------------------------------------------------------

NAVY = "#142B49"
AMBER = "#E5A23A"
TEAL = "#0D9488"
VIOLET = "#7C70D6"
CORAL = "#E26B69"


# ------------------------------------------------------------
# 3. READ HISTORICAL DATA FROM SQLITE
# ------------------------------------------------------------

def load_data():

    with connect_database() as connection:

        df = pd.read_sql_query(
            """
            SELECT *
            FROM economic_monthly
            ORDER BY month
            """,
            connection
        )

    if df.empty:
        raise ValueError("Economic database is empty.")

    if not df["month"].astype(str).str.fullmatch(
        r"\d{4}-(0[1-9]|1[0-2])"
    ).all():
        raise ValueError("Invalid month format in database.")

    df["date"] = pd.to_datetime(
        df["month"] + "-01",
        format="%Y-%m-%d"
    )

    df = df.sort_values("date").reset_index(drop=True)

    if df["date"].duplicated().any():
        raise ValueError("Duplicate observation months found.")

    # Time-series lags require consecutive calendar months.
    # Do not silently treat a gap as one month.
    expected = pd.date_range(
        df["date"].min(),
        df["date"].max(),
        freq="MS"
    )

    if not pd.DatetimeIndex(df["date"]).equals(expected):
        raise ValueError(
            "Missing calendar months detected. "
            "Insert the missing monthly records before analysis."
        )

    numeric_columns = [
        "headline_yoy_pct",
        "food_yoy_pct",
        "nonfood_yoy_pct",
        "ccpi_linked_jan2019_100",
        "public_nominal_jan2019_100",
        "informal_nominal_jan2019_100",
        "public_real_ncpi_raw",
        "informal_real_ncpi_raw",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="raise"
        )

    for column in [
        "ccpi_linked_jan2019_100",
        "public_nominal_jan2019_100",
        "informal_nominal_jan2019_100",
        "public_real_ncpi_raw",
        "informal_real_ncpi_raw",
    ]:
        if (df[column].dropna() <= 0).any():
            raise ValueError(
                f"Invalid non-positive index in {column}"
            )

    return df


# ------------------------------------------------------------
# 4. YEAR-ON-YEAR PERCENTAGE CHANGE
# ------------------------------------------------------------

def year_on_year_change(series):
    """
    Compares the current month with the same month
    one year earlier.

    Missing observations remain missing.
    """

    previous_year = series.shift(12)

    return np.where(
        series.notna()
        & previous_year.notna()
        & (previous_year > 0),
        100 * (series / previous_year - 1),
        np.nan
    )


# ------------------------------------------------------------
# 5. INFLATION ANALYSIS
# ------------------------------------------------------------

def calculate_inflation_indicators(df):

    df = df.copy()

    # Use source-provided annual inflation rates.
    df["headline_inflation"] = df["headline_yoy_pct"]
    df["food_inflation"] = df["food_yoy_pct"]
    df["nonfood_inflation"] = df["nonfood_yoy_pct"]

    # Average headline inflation for the latest 3 months.
    df["inflation_3m_average"] = (
        df["headline_inflation"]
        .rolling(window=3, min_periods=3)
        .mean()
    )

    # Compare the current 3-month average
    # with the preceding non-overlapping 3 months.
    df["previous_3m_average"] = (
        df["inflation_3m_average"].shift(3)
    )

    # Difference measured in percentage points.
    df["inflation_momentum_pp"] = (
        df["inflation_3m_average"]
        - df["previous_3m_average"]
    )

    # Difference between food and headline inflation.
    df["food_inflation_gap_pp"] = (
        df["food_inflation"]
        - df["headline_inflation"]
    )

    return df


# ------------------------------------------------------------
# 6. WAGE-RATE ANALYSIS
# ------------------------------------------------------------

def calculate_wage_indicators(df):

    df = df.copy()

    sectors = ["public", "informal"]

    for sector in sectors:

        nominal_column = (
            f"{sector}_nominal_jan2019_100"
        )

        official_real_column = (
            f"{sector}_real_ncpi_raw"
        )

        # Annual nominal wage-rate index growth.
        df[f"{sector}_nominal_yoy_pct"] = (
            year_on_year_change(
                df[nominal_column]
            )
        )

        # Annual real wage-rate index growth,
        # calculated from official NCPI-adjusted
        # CBSL wage-rate indices.
        df[f"{sector}_real_ncpi_yoy_pct"] = (
            year_on_year_change(
                df[official_real_column]
            )
        )

        # Researcher-calculated CCPI-adjusted index.
        # Both nominal wages and CCPI are rebased
        # to January 2019 = 100.
        df[f"{sector}_real_ccpi_jan2019_100"] = (
            100
            * df[nominal_column]
            / df["ccpi_linked_jan2019_100"]
        )

        # Growth from the CCPI-adjusted measure.
        # Interpret cautiously across the 2023
        # CCPI basket/base revision.
        df[f"{sector}_real_ccpi_yoy_pct"] = (
            year_on_year_change(
                df[f"{sector}_real_ccpi_jan2019_100"]
            )
        )

        # Change in purchasing power relative
        # to January 2019.
        df[f"{sector}_purchasing_power_change_pct"] = (
            df[f"{sector}_real_ccpi_jan2019_100"]
            - 100
        )

    return df


# ------------------------------------------------------------
# 7. FIXED-SALARY PURCHASING-POWER SCENARIO
# ------------------------------------------------------------

def calculate_salary_scenario(df, salary=60000):

    df = df.copy()

    if salary <= 0:
        raise ValueError("Salary must be positive.")

    # Hypothetical nominal monthly salary
    # that remains unchanged since January 2019.
    df["fixed_salary_lkr"] = salary

    # Required salary to purchase a comparable
    # basket of goods and services.
    df["required_salary_lkr"] = (
        salary
        * df["ccpi_linked_jan2019_100"]
        / 100
    )

    # Inflation-adjusted value in January 2019 LKR.
    df["fixed_salary_real_lkr"] = (
        salary
        * 100
        / df["ccpi_linked_jan2019_100"]
    )

    # Percentage change in purchasing power.
    df["fixed_salary_purchasing_power_change_pct"] = (
        100 * (
            df["fixed_salary_real_lkr"] / salary - 1
        )
    )

    return df


# ------------------------------------------------------------
# 8. TRANSPARENT INFLATION MONITORING SIGNALS
# ------------------------------------------------------------

def classify_inflation_pressure(value):
    """
    Illustrative descriptive thresholds only.

    These are NOT official CBSL/IMF thresholds,
    learned ML predictions, or crisis probabilities.
    """

    if pd.isna(value):
        return "Unavailable"

    if value < 0:
        return "Deflation"

    if value >= 20:
        return "Very high inflation"

    if value >= 10:
        return "High inflation"

    if value >= 5:
        return "Elevated inflation"

    return "Lower inflation"


def classify_inflation_momentum(value):
    """
    Positive difference: recent YoY inflation
    is rising relative to the preceding period.

    The +/- 1 percentage point threshold is
    illustrative, not statistically calibrated.
    """

    if pd.isna(value):
        return "Unavailable"

    if value > 1:
        return "Rising"

    if value < -1:
        return "Falling"

    return "Relatively stable"


def add_monitoring_signals(df):

    df = df.copy()

    df["inflation_pressure_signal"] = (
        df["inflation_3m_average"]
        .apply(classify_inflation_pressure)
    )

    df["inflation_momentum_signal"] = (
        df["inflation_momentum_pp"]
        .apply(classify_inflation_momentum)
    )

    for sector in ["public", "informal"]:

        column = f"{sector}_real_ncpi_yoy_pct"

        df[f"{sector}_real_wage_signal"] = np.where(
            df[column].isna(),
            "Unavailable",
            np.where(
                df[column] < 0,
                "Real wage-rate decline",
                "No annual real wage-rate decline"
            )
        )

    return df


# ------------------------------------------------------------
# 9. INFLATION TREND VISUALIZATION
# ------------------------------------------------------------

def plot_inflation(df):

    fig, ax = plt.subplots(figsize=(12, 5.5))

    ax.plot(
        df["date"],
        df["headline_inflation"],
        color=NAVY,
        linewidth=2.3,
        label="Headline inflation"
    )

    ax.plot(
        df["date"],
        df["inflation_3m_average"],
        color=AMBER,
        linewidth=2,
        linestyle="--",
        label="3-month average"
    )

    ax.axhline(
        0,
        color="gray",
        linewidth=0.9,
        alpha=0.7
    )

    ax.set_title(
        "Sri Lanka — Headline Inflation Trends",
        fontsize=15,
        fontweight="bold",
        color=NAVY
    )

    ax.set_ylabel("Year-on-year inflation (%)")
    ax.set_xlabel("")

    ax.grid(alpha=0.2)
    ax.legend(frameon=False)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIR / "01_inflation_trends.png",
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(fig)


# ------------------------------------------------------------
# 10. REAL WAGE-RATE VISUALIZATION
# ------------------------------------------------------------

def plot_real_wages(df):

    fig, ax = plt.subplots(figsize=(12, 5.5))

    ax.plot(
        df["date"],
        df["public_real_ccpi_jan2019_100"],
        color=VIOLET,
        linewidth=2.2,
        label="Public sector"
    )

    ax.plot(
        df["date"],
        df["informal_real_ccpi_jan2019_100"],
        color=CORAL,
        linewidth=2.2,
        label="Informal private sector"
    )

    ax.axhline(
        100,
        color="gray",
        linestyle="--",
        linewidth=1
    )

    ax.set_title(
        "CCPI-Adjusted Real Wage-Rate Indices",
        fontsize=15,
        fontweight="bold",
        color=NAVY
    )

    ax.set_ylabel("Index (January 2019 = 100)")
    ax.set_xlabel("")
    ax.set_xlim(
        pd.Timestamp("2019-01-01"),
        df["date"].max()
    )

    ax.grid(alpha=0.2)
    ax.legend(frameon=False)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIR / "02_real_wage_trends.png",
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(fig)


# ------------------------------------------------------------
# 11. EXPORT RESULTS AND LATEST MONTH SUMMARY
# ------------------------------------------------------------

def export_results(df):

    output_file = (
        OUTPUT_DIR / "economic_indicators_all_months.csv"
    )

    df.to_csv(output_file, index=False)

    latest = df.iloc[-1]

    summary = pd.DataFrame([{
        "month": latest["month"],
        "headline_inflation_pct": (
            latest["headline_inflation"]
        ),
        "food_inflation_pct": latest["food_inflation"],
        "inflation_3m_average_pct": (
            latest["inflation_3m_average"]
        ),
        "inflation_momentum_pp": (
            latest["inflation_momentum_pp"]
        ),
        "inflation_pressure_signal": (
            latest["inflation_pressure_signal"]
        ),
        "inflation_momentum_signal": (
            latest["inflation_momentum_signal"]
        ),
        "public_real_ccpi_index": (
            latest["public_real_ccpi_jan2019_100"]
        ),
        "informal_real_ccpi_index": (
            latest["informal_real_ccpi_jan2019_100"]
        ),
        "public_real_wage_signal": (
            latest["public_real_wage_signal"]
        ),
        "informal_real_wage_signal": (
            latest["informal_real_wage_signal"]
        ),
        "required_salary_lkr": (
            latest["required_salary_lkr"]
        ),
        "fixed_salary_real_lkr": (
            latest["fixed_salary_real_lkr"]
        ),
    }])

    summary.to_csv(
        OUTPUT_DIR / "latest_monitoring_summary.csv",
        index=False
    )

    print("\nLATEST OBSERVATION")

    for column, value in summary.iloc[0].items():
        print(f"{column}: {value}")

    print(f"\nSaved: {output_file}")
    print("Saved: latest_monitoring_summary.csv")


# ------------------------------------------------------------
# 12. MAIN EXECUTION
# ------------------------------------------------------------

def main():

    print("\n" + "=" * 60)
    print("SL-EWRIS — ECONOMIC INDICATOR ANALYSIS")
    print("=" * 60)

    df = load_data()

    print(f"Loaded observations: {len(df)}")
    print(
        f"Period: {df['month'].iloc[0]}"
        f" to {df['month'].iloc[-1]}"
    )

    df = calculate_inflation_indicators(df)

    df = calculate_wage_indicators(df)

    df = calculate_salary_scenario(
        df,
        salary=60000
    )

    df = add_monitoring_signals(df)

    plot_inflation(df)

    plot_real_wages(df)

    export_results(df)

    print("\n[PASS] Economic indicator analysis completed.")
    print(f"Output folder: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
