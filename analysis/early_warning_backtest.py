
# ============================================================
# SL-EWRIS — STEP 17
# HISTORICAL EARLY-WARNING READINESS AUDIT
#
# Point-in-time checks for Sri Lanka's 2022 crisis
#
# IMPORTANT:
# - Never use observations published after a cutoff.
# - Never assume a missing publication date.
# - Never assume today's revised database value
#   was the same value published historically.
# - This is NOT yet a validated crisis backtest.
# ============================================================

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from database import connect_database

import numpy as np
import pandas as pd


# ------------------------------------------------------------
# 1. PROJECT PATHS
# ------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]


OUTPUT = ROOT / "outputs" / "early_warning_backtest"

OUTPUT.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# 2. HISTORICAL DECISION CHECKPOINTS
# ------------------------------------------------------------

CHECKPOINTS = [
    "2020-12-31",
    "2021-06-30",
    "2021-12-31",
    "2022-03-31",
]


# ------------------------------------------------------------
# 3. ECONOMIC INDICATORS
# ------------------------------------------------------------

INDICATORS = {
    "headline_yoy_pct": "Headline inflation (%)",
    "food_yoy_pct": "Food inflation (%)",
    "nonfood_yoy_pct": "Non-food inflation (%)",
    "public_real_ncpi_raw": "Public real wage index",
    "informal_real_ncpi_raw": "Informal real wage index",
    "fx_reserves_usd_bn": "Gross official reserves",
    "usd_lkr": "USD/LKR exchange rate",
}


# ------------------------------------------------------------
# 4. READ DATABASE IN READ-ONLY MODE
# ------------------------------------------------------------

def load_database():

    with connect_database() as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT tablename AS name FROM pg_catalog.pg_tables "
                "WHERE schemaname = current_schema()"
            )
        }

        if "economic_monthly" not in tables:
            raise RuntimeError(
                "economic_monthly table is missing."
            )

        columns = ", ".join(
            f'"{name}"'
            for name in INDICATORS
        )

        monthly = pd.read_sql_query(
            f"""
            SELECT month, publication_date, {columns}
            FROM economic_monthly
            ORDER BY month
            """,
            conn
        )

        # Step 12 source records, if they exist.
        if "external_indicator_import_log" in tables:

            external_log = pd.read_sql_query(
                """
                SELECT
                    month,
                    indicator,
                    value,
                    publication_date,
                    source_url
                FROM external_indicator_import_log
                """,
                conn
            )

        else:

            external_log = pd.DataFrame(
                columns=[
                    "month",
                    "indicator",
                    "value",
                    "publication_date",
                    "source_url",
                ]
            )

    if monthly.empty:
        raise ValueError("Historical database is empty.")

    if monthly["month"].duplicated().any():
        raise ValueError("Duplicate observation months.")

    monthly["observation_date"] = pd.to_datetime(
        monthly["month"] + "-01",
        format="%Y-%m-%d",
        errors="raise"
    )

    for indicator in INDICATORS:

        monthly[indicator] = pd.to_numeric(
            monthly[indicator],
            errors="raise"
        )

        present = monthly[indicator].dropna()

        if not np.isfinite(present).all():
            raise ValueError(
                f"Non-finite observations in {indicator}"
            )

    return monthly, external_log


# ------------------------------------------------------------
# 5. OPTIONAL VERIFIED HISTORICAL RELEASE LEDGER
# ------------------------------------------------------------

LEDGER_PATH = (
    ROOT / "data" / "historical_release_ledger.csv"
)

LEDGER_COLUMNS = [
    "month",
    "indicator",
    "published_value",
    "publication_date",
    "source_url",
]


def load_release_ledger():

    # The template is created only if absent.
    # We never overwrite a manually completed ledger.
    if not LEDGER_PATH.exists():

        pd.DataFrame(
            columns=LEDGER_COLUMNS
        ).to_csv(
            LEDGER_PATH,
            index=False
        )

        print(
            "[INFO] Created blank historical "
            "release ledger."
        )

    ledger = pd.read_csv(
        LEDGER_PATH,
        dtype="string"
    )

    missing = [
        col for col in LEDGER_COLUMNS
        if col not in ledger.columns
    ]

    if missing:
        raise ValueError(
            f"Ledger is missing columns: {missing}"
        )

    if ledger.empty:
        return ledger

    ledger = ledger[LEDGER_COLUMNS].copy()

    if ledger.isna().any().any():
        raise ValueError(
            "Incomplete ledger rows found. "
            "Remove empty rows or complete every field."
        )

    if not ledger["indicator"].isin(INDICATORS).all():
        raise ValueError(
            "Unknown indicator name in ledger."
        )

    if not ledger["month"].str.fullmatch(
        r"\d{4}-(0[1-9]|1[0-2])"
    ).all():
        raise ValueError(
            "Invalid month format in ledger."
        )

    ledger["published_value"] = pd.to_numeric(
        ledger["published_value"],
        errors="raise"
    )

    if not np.isfinite(
        ledger["published_value"]
    ).all():
        raise ValueError(
            "Non-finite published value."
        )

    ledger["publication_date"] = pd.to_datetime(
        ledger["publication_date"],
        format="%Y-%m-%d",
        errors="raise"
    )

    observation_month = pd.to_datetime(
        ledger["month"] + "-01",
        format="%Y-%m-%d"
    )

    if (
        ledger["publication_date"] < observation_month
    ).any():
        raise ValueError(
            "Publication date precedes observation month."
        )

    if not ledger["source_url"].str.startswith(
        "https://"
    ).all():
        raise ValueError(
            "Ledger source URLs must use HTTPS."
        )

    return ledger


# ------------------------------------------------------------
# 6. COMBINE SOURCE RELEASE EVIDENCE
# ------------------------------------------------------------

def build_evidence(ledger, external_log):

    evidence = []

    # Manual ledger contains independently checked
    # historical published values and dates.
    if not ledger.empty:

        for row in ledger.itertuples(index=False):

            evidence.append({
                "month": row.month,
                "indicator": row.indicator,
                "published_value": float(
                    row.published_value
                ),
                "publication_date": row.publication_date,
                "source_url": row.source_url,
                "evidence_origin": "manual_release_ledger",
            })

    # Existing external import log is useful
    # as provisional source metadata. An import
    # timestamp is NOT a historical publication date.
    if not external_log.empty:

        for row in external_log.itertuples(
            index=False
        ):

            if row.indicator not in INDICATORS:
                continue

            if (
                pd.isna(row.publication_date)
                or pd.isna(row.source_url)
            ):
                continue

            try:
                published_date = pd.to_datetime(
                    row.publication_date,
                    format="%Y-%m-%d",
                    errors="raise"
                )

                published_value = float(row.value)

                if not np.isfinite(published_value):
                    continue

            except (ValueError, TypeError):
                continue

            evidence.append({
                "month": row.month,
                "indicator": row.indicator,
                "published_value": published_value,
                "publication_date": published_date,
                "source_url": row.source_url,
                "evidence_origin": "external_import_log",
            })

    if not evidence:

        return pd.DataFrame(
            columns=[
                "month",
                "indicator",
                "published_value",
                "publication_date",
                "source_url",
                "evidence_origin",
            ]
        )

    return pd.DataFrame(evidence)


# ------------------------------------------------------------
# 7. ASSESS A SINGLE HISTORICAL CHECKPOINT
# ------------------------------------------------------------

def assess_checkpoint(monthly, evidence, cutoff):

    cutoff_date = pd.Timestamp(cutoff)

    # Only observation months up to the cutoff.
    eligible = monthly[
        monthly["observation_date"]
        <= cutoff_date
    ].copy()

    snapshot_rows = []

    for indicator, label in INDICATORS.items():

        observations = eligible[
            eligible[indicator].notna()
        ].copy()

        if observations.empty:

            snapshot_rows.append({
                "checkpoint": cutoff,
                "indicator": indicator,
                "description": label,
                "observation_month": None,
                "value": np.nan,
                "publication_date": None,
                "source_url": None,
                "status": "No historical observation",
            })

            continue

        indicator_evidence = evidence[
            evidence["indicator"] == indicator
        ].copy()

        # Require explicitly documented publication
        # on or before the historical cutoff.
        eligible_evidence = indicator_evidence[
            indicator_evidence["publication_date"]
            <= cutoff_date
        ].copy()

        eligible_evidence = eligible_evidence.sort_values(
            "publication_date"
        )

        candidates = []

        # Historical evidence may contain original
        # vintages that differ from the revised DB.
        for source in eligible_evidence.itertuples(
            index=False
        ):

            matching_month = observations[
                observations["month"] == source.month
            ]

            if matching_month.empty:
                continue

            candidates.append({
                "month": source.month,
                "published_value": (
                    source.published_value
                ),
                "publication_date": (
                    source.publication_date
                ),
                "source_url": source.source_url,
                "evidence_origin": (
                    source.evidence_origin
                ),
            })

        if candidates:

            candidates.sort(
                key=lambda x: (
                    x["month"],
                    x["publication_date"]
                )
            )

            chosen = candidates[-1]

            # Use the documented historical published
            # value rather than today's potentially
            # revised database value.
            snapshot_rows.append({
                "checkpoint": cutoff,
                "indicator": indicator,
                "description": label,
                "observation_month": chosen["month"],
                "value": chosen["published_value"],
                "publication_date": (
                    chosen["publication_date"]
                    .strftime("%Y-%m-%d")
                ),
                "source_url": chosen["source_url"],
                "status": (
                    "Candidate historical vintage - "
                    "manual source verification needed"
                    if chosen["evidence_origin"]
                    == "external_import_log"
                    else "Documented historical vintage"
                ),
            })

        else:

            latest = observations.iloc[-1]

            snapshot_rows.append({
                "checkpoint": cutoff,
                "indicator": indicator,
                "description": label,
                "observation_month": latest["month"],
                "value": np.nan,
                "publication_date": None,
                "source_url": None,
                "status": (
                    "Observation exists, but "
                    "historical publication not verified"
                ),
            })

    return snapshot_rows


# ------------------------------------------------------------
# 8. BUILD ALL CHECKPOINT SNAPSHOTS
# ------------------------------------------------------------

def build_snapshots(monthly, evidence):

    snapshots = []

    for cutoff in CHECKPOINTS:

        snapshots.extend(
            assess_checkpoint(
                monthly,
                evidence,
                cutoff
            )
        )

    return pd.DataFrame(snapshots)


# ------------------------------------------------------------
# 9. COVERAGE AND READINESS RESULTS
# ------------------------------------------------------------

def summarize_readiness(snapshots):

    summary_rows = []

    for cutoff, group in snapshots.groupby(
        "checkpoint",
        sort=True
    ):

        documented = int(
            (
                group["status"]
                == "Documented historical vintage"
            ).sum()
        )

        provisional = int(
            group["status"].str.startswith(
                "Candidate historical vintage"
            ).sum()
        )

        unavailable = int(
            group["value"].isna().sum()
        )

        summary_rows.append({
            "checkpoint": cutoff,
            "indicators_expected": len(INDICATORS),
            "documented_vintages": documented,
            "provisional_vintages": provisional,
            "unavailable_for_backtest": unavailable,
            "readiness": (
                "Fully documented for this indicator set"
                if documented == len(INDICATORS)
                else "Incomplete - do not claim "
                     "validated crisis backtest"
            ),
        })

    return pd.DataFrame(summary_rows)


# ------------------------------------------------------------
# 10. EXPORT OUTPUTS
# ------------------------------------------------------------

def main():

    print("=" * 65)
    print("SL-EWRIS | STEP 17")
    print("HISTORICAL EARLY-WARNING READINESS AUDIT")
    print("=" * 65)

    monthly, external_log = load_database()

    ledger = load_release_ledger()

    evidence = build_evidence(
        ledger,
        external_log
    )

    snapshots = build_snapshots(
        monthly,
        evidence
    )

    readiness = summarize_readiness(
        snapshots
    )

    snapshots.to_csv(
        OUTPUT / "historical_checkpoint_snapshots.csv",
        index=False
    )

    readiness.to_csv(
        OUTPUT / "backtest_readiness_summary.csv",
        index=False
    )

    missing = snapshots[
        snapshots["status"]
        != "Documented historical vintage"
    ]

    missing.to_csv(
        OUTPUT / "source_verification_needed.csv",
        index=False
    )

    print("\nBACKTEST READINESS SUMMARY")

    print(
        readiness.to_string(
            index=False
        )
    )

    print("\nOutput folder:", OUTPUT)

    print(
        "\n[PASS] Point-in-time evidence audit completed."
    )

    print(
        "No crisis model was trained, "
        "and no historical predictions were invented."
    )

    print(
        "A documented publication date is necessary, "
        "but its underlying source must also be checked "
        "for historical revisions."
    )


if __name__ == "__main__":
    main()
