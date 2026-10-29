
# ============================================================
# SL-EWRIS — STEP 15
# EXTERNAL-SECTOR DATA COVERAGE AND SOURCE AUDIT
#
# Period: January 2014 – December 2025
# Database: SQLite
#
# This script is READ-ONLY.
# It does not change any economic observations.
# ============================================================

from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ------------------------------------------------------------
# 1. PROJECT PATHS
# ------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

DB_PATH = ROOT / "database" / "economic_risk.db"

OUTPUT_DIR = ROOT / "outputs" / "external_data_audit"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

NAVY = "#142B49"
TEAL = "#0D9488"
AMBER = "#E5A23A"


# ------------------------------------------------------------
# 2. EXPECTED MONTHS AND INDICATORS
# ------------------------------------------------------------

EXPECTED_MONTHS = pd.period_range(
    "2014-01",
    "2025-12",
    freq="M"
).astype(str)

INDICATORS = {
    "fx_reserves_usd_bn": {
        "label": "Gross official reserves",
        "unit": "USD billions",
        "definition": "End-of-month",
    },
    "usd_lkr": {
        "label": "USD/LKR exchange rate",
        "unit": "LKR per USD",
        "definition": "Monthly average",
    },
}

CBSL_SOURCE = (
    "https://www.cbsl.gov.lk/statistics/"
    "economic-indicators/monthly-indicators"
)


# ------------------------------------------------------------
# 3. LOAD THE DATABASE
# ------------------------------------------------------------

def load_database():

    if not DB_PATH.is_file():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}"
        )

    # Open SQLite in read-only mode.
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"

    with sqlite3.connect(uri, uri=True) as conn:

        existing_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table'"
            )
        }

        if "economic_monthly" not in existing_tables:
            raise RuntimeError(
                "economic_monthly table does not exist."
            )

        monthly = pd.read_sql_query(
            """
            SELECT
                month,
                fx_reserves_usd_bn,
                usd_lkr
            FROM economic_monthly
            WHERE month >= '2014-01'
              AND month <= '2025-12'
            ORDER BY month
            """,
            conn
        )

        # Step 12 source metadata is optional.
        if "external_indicator_import_log" in existing_tables:

            source_log = pd.read_sql_query(
                """
                SELECT
                    month,
                    indicator,
                    value,
                    publication_date,
                    source_url,
                    imported_at
                FROM external_indicator_import_log
                """,
                conn
            )

        else:
            source_log = pd.DataFrame(
                columns=[
                    "month",
                    "indicator",
                    "value",
                    "publication_date",
                    "source_url",
                    "imported_at",
                ]
            )

    if monthly["month"].duplicated().any():
        raise ValueError(
            "Duplicate month records found in SQLite."
        )

    # Check that the dates use the correct format.
    for value in monthly["month"]:
        try:
            pd.Period(value, freq="M")
        except (ValueError, TypeError) as error:
            raise ValueError(
                f"Invalid database month: {value}"
            ) from error

    # Reindex instead of silently dropping absent months.
    monthly = (
        monthly
        .set_index("month")
        .reindex(EXPECTED_MONTHS)
    )

    monthly.index.name = "month"

    monthly = monthly.reset_index()

    for column in INDICATORS:

        monthly[column] = pd.to_numeric(
            monthly[column],
            errors="raise"
        )

        present = monthly[column].dropna()

        if (
            not np.isfinite(present).all()
            or (present <= 0).any()
        ):
            raise ValueError(
                f"Invalid values in {column}."
            )

    return monthly, source_log


# ------------------------------------------------------------
# 4. CHECK HISTORICAL SOURCE DOCUMENTATION
# ------------------------------------------------------------

def build_source_lookup(source_log):

    source_lookup = {}

    if source_log.empty:
        return source_lookup

    for row in source_log.itertuples(index=False):

        key = (row.month, row.indicator)

        if row.indicator not in INDICATORS:
            continue

        # Do not blindly assume the most recently
        # logged figure matches the current DB value.
        source_lookup.setdefault(key, []).append({
            "value": row.value,
            "publication_date": row.publication_date,
            "source_url": row.source_url,
        })

    return source_lookup


def source_status(month, indicator, value, lookup):

    if pd.isna(value):
        return "No observation"

    records = lookup.get((month, indicator), [])

    if not records:
        return "Source metadata not in Step 12 log"

    matching = []

    for record in records:

        try:
            recorded_value = float(record["value"])
        except (ValueError, TypeError):
            continue

        if np.isclose(
            float(value),
            recorded_value,
            rtol=1e-10,
            atol=1e-10
        ):
            matching.append(record)

    if not matching:
        return "Logged value differs from database"

    complete = any(
        str(r["publication_date"]).strip()
        and str(r["source_url"]).strip()
        for r in matching
    )

    return (
        "Source metadata recorded"
        if complete
        else "Source metadata incomplete"
    )


# ------------------------------------------------------------
# 5. GENERATE THE COVERAGE WORKSHEET
# ------------------------------------------------------------

def build_coverage(monthly, source_log):

    lookup = build_source_lookup(source_log)

    rows = []

    for record in monthly.itertuples(index=False):

        for indicator, info in INDICATORS.items():

            value = getattr(record, indicator)

            available = pd.notna(value)

            rows.append({
                "month": record.month,
                "year": int(record.month[:4]),
                "indicator": indicator,
                "description": info["label"],
                "required_definition": info["definition"],
                "required_unit": info["unit"],
                "stored_value": (
                    float(value)
                    if available else np.nan
                ),
                "availability": (
                    "Available"
                    if available else "Missing"
                ),
                "source_audit": source_status(
                    record.month,
                    indicator,
                    value,
                    lookup
                ),
                "source_search_page": CBSL_SOURCE,
                "action_required": (
                    "Find and verify official monthly value"
                    if not available
                    else "Review source documentation"
                    if source_status(
                        record.month,
                        indicator,
                        value,
                        lookup
                    ) != "Source metadata recorded"
                    else "None"
                ),
            })

    return pd.DataFrame(rows)


# ------------------------------------------------------------
# 6. SUMMARY TABLES
# ------------------------------------------------------------

def summarize_coverage(coverage):

    summary = (
        coverage
        .groupby("indicator", as_index=False)
        .agg(
            expected_months=("month", "count"),
            available_months=(
                "availability",
                lambda s: int((s == "Available").sum())
            ),
            missing_months=(
                "availability",
                lambda s: int((s == "Missing").sum())
            ),
        )
    )

    summary["coverage_pct"] = (
        100
        * summary["available_months"]
        / summary["expected_months"]
    )

    yearly = (
        coverage
        .assign(
            available=(
                coverage["availability"] == "Available"
            ).astype(int)
        )
        .pivot_table(
            index="year",
            columns="indicator",
            values="available",
            aggfunc="sum",
            fill_value=0
        )
        .reset_index()
    )

    return summary, yearly


# ------------------------------------------------------------
# 7. COVERAGE VISUALIZATION
# ------------------------------------------------------------

def plot_coverage(yearly):

    years = yearly["year"].to_numpy()

    reserves = yearly[
        "fx_reserves_usd_bn"
    ].to_numpy()

    exchange = yearly[
        "usd_lkr"
    ].to_numpy()

    width = 0.36

    fig, ax = plt.subplots(figsize=(12, 5.5))

    ax.bar(
        years - width / 2,
        reserves,
        width=width,
        color=NAVY,
        label="Foreign reserves"
    )

    ax.bar(
        years + width / 2,
        exchange,
        width=width,
        color=TEAL,
        label="USD/LKR"
    )

    ax.set_title(
        "Sri Lanka — External Data Availability",
        fontsize=15,
        fontweight="bold",
        color=NAVY
    )

    ax.set_ylabel("Available monthly observations")

    ax.set_xlabel("Year")

    ax.set_xticks(years)

    ax.set_ylim(0, 12.8)

    ax.set_yticks(range(0, 13, 2))

    ax.grid(axis="y", alpha=0.2)

    ax.legend(frameon=False)

    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIR / "01_external_data_coverage.png",
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(fig)


# ------------------------------------------------------------
# 8. EXPORT AUDIT RESULTS
# ------------------------------------------------------------

def export_audit(coverage, summary, yearly):

    coverage.to_csv(
        OUTPUT_DIR / "monthly_source_audit.csv",
        index=False
    )

    missing = coverage[
        coverage["availability"] == "Missing"
    ]

    missing.to_csv(
        OUTPUT_DIR / "missing_external_observations.csv",
        index=False
    )

    summary.to_csv(
        OUTPUT_DIR / "indicator_coverage_summary.csv",
        index=False
    )

    yearly.to_csv(
        OUTPUT_DIR / "annual_data_coverage.csv",
        index=False
    )

    plot_coverage(yearly)


# ------------------------------------------------------------
# 9. RUN THE AUDIT
# ------------------------------------------------------------

def main():

    print("=" * 60)
    print("SL-EWRIS | STEP 15: EXTERNAL DATA AUDIT")
    print("=" * 60)

    monthly, source_log = load_database()

    coverage = build_coverage(monthly, source_log)

    summary, yearly = summarize_coverage(coverage)

    export_audit(coverage, summary, yearly)

    print("\nHistorical period: 2014-01 to 2025-12")

    print("Expected months per indicator: 144")

    print("\nCOVERAGE SUMMARY")

    print(
        summary.to_string(index=False)
    )

    missing = int(
        (coverage["availability"] == "Missing").sum()
    )

    print(f"\nMissing indicator-month entries: {missing}")

    undocumented = int(
        (
            (coverage["availability"] == "Available")
            & (
                coverage["source_audit"]
                != "Source metadata recorded"
            )
        ).sum()
    )

    print(
        "Available values needing source-log review:",
        undocumented
    )

    print("\nOutputs saved to:", OUTPUT_DIR)

    print("\n[PASS] Read-only audit completed.")

    print(
        "No database observations were modified."
    )


if __name__ == "__main__":
    main()
