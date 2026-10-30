from pathlib import Path
from datetime import date
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT / "outputs/external_risk_analysis"
    / "publication_evidence_register_2020_2022.csv"
)

OUT = ROOT / "outputs/external_risk_analysis"
REVIEW = OUT / "publication_evidence_validation.csv"
REPLAY = OUT / "historical_information_snapshots.csv"

DECISION_DATES = [
    "2021-03-31",
    "2021-06-30",
    "2021-09-30",
    "2021-12-31",
    "2022-03-31",
    "2022-06-30"
]

REQUIRED = [
    "month",
    "indicator",
    "retrospective_value",
    "historical_publication_date",
    "historical_publication_url",
    "historically_published_value",
    "same_definition_and_precision",
    "verification_status"
]

INDICATORS = {"fx_reserves_usd_bn", "usd_lkr"}


def text(value):
    return str(value or "").strip()


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def main():

    if not SOURCE.exists():
        raise FileNotFoundError(
            "Step 33 publication evidence register missing."
        )

    if REVIEW.exists() or REPLAY.exists():
        raise FileExistsError(
            "Replay outputs already exist. "
            "Preserve or archive them before rerunning."
        )

    df = pd.read_csv(
        SOURCE,
        dtype=str,
        keep_default_na=False
    )

    missing = set(REQUIRED) - set(df.columns)
    if missing:
        raise ValueError(
            f"Missing evidence columns: {sorted(missing)}"
        )

    if df[["month", "indicator"]].duplicated().any():
        raise ValueError(
            "Duplicate month-indicator records. "
            "A historical vintage ledger is needed "
            "for multiple releases of the same indicator."
        )

    if not df["indicator"].isin(INDICATORS).all():
        raise ValueError("Unexpected indicator found")

    if not df["month"].str.fullmatch(
        r"20\d{2}-(0[1-9]|1[0-2])"
    ).all():
        raise ValueError("Invalid reporting month")

    results = []

    for _, row in df.iterrows():

        month = text(row["month"])
        published = text(
            row["historical_publication_date"]
        )
        url = text(row["historical_publication_url"])

        historical = pd.to_numeric(
            row["historically_published_value"],
            errors="coerce"
        )

        retrospective = pd.to_numeric(
            row["retrospective_value"],
            errors="coerce"
        )

        verified = (
            text(row["verification_status"]).lower()
            == "verified"
        )

        same_definition = (
            text(row["same_definition_and_precision"])
            .lower() == "yes"
        )

        release_date = parse_date(published)

        value_match = (
            np.isfinite(historical)
            and np.isfinite(retrospective)
            and np.isclose(
                historical,
                retrospective,
                rtol=0,
                atol=0.000001
            )
        )

        valid = (
            verified
            and same_definition
            and release_date is not None
            and bool(url)
            and url.startswith(("https://", "http://"))
            and bool(value_match)
            and release_date >= date.fromisoformat(
                month + "-01"
            )
        )

        results.append({
            "month": month,
            "indicator": row["indicator"],
            "value": retrospective,
            "historical_publication_date": published,
            "historical_publication_url": url,
            "evidence_accepted": bool(valid),
            "review_result": (
                "Accepted"
                if valid
                else "Pending or insufficient evidence"
            )
        })

    checked = pd.DataFrame(results)

    checked.to_csv(
        REVIEW,
        index=False,
        encoding="utf-8-sig"
    )

    snapshots = []

    for decision_text in DECISION_DATES:

        decision = date.fromisoformat(decision_text)

        for indicator in sorted(INDICATORS):

            eligible = checked[
                (checked["indicator"] == indicator)
                & checked["evidence_accepted"]
            ].copy()

            eligible["publication_dt"] = pd.to_datetime(
                eligible["historical_publication_date"],
                errors="coerce"
            )

            eligible = eligible[
                eligible["publication_dt"].dt.date
                <= decision
            ].sort_values(
                ["month", "publication_dt"]
            )

            if eligible.empty:

                snapshots.append({
                    "decision_date": decision_text,
                    "indicator": indicator,
                    "latest_available_month": "",
                    "latest_available_value": "",
                    "published_on": "",
                    "availability_status":
                        "No verified observation available"
                })

            else:

                selected = eligible.iloc[-1]

                snapshots.append({
                    "decision_date": decision_text,
                    "indicator": indicator,
                    "latest_available_month":
                        selected["month"],
                    "latest_available_value":
                        selected["value"],
                    "published_on":
                        selected["historical_publication_date"],
                    "availability_status":
                        "Verified observation available"
                })

    snapshot_df = pd.DataFrame(snapshots)

    snapshot_df.to_csv(
        REPLAY,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n=== SL-EWRIS PUBLICATION-AWARE REPLAY ===")
    print("Evidence records:", len(checked))
    print(
        "Accepted evidence records:",
        int(checked["evidence_accepted"].sum())
    )

    print("\n=== HISTORICAL INFORMATION SNAPSHOTS ===")
    print(snapshot_df.to_string(index=False))

    print("\nSaved:", REVIEW)
    print("Saved:", REPLAY)
    print("\nNo dates or observations were invented.")
    print("SQLite database unchanged.")
    print("This is availability checking, not crisis prediction.")


if __name__ == "__main__":
    main()
