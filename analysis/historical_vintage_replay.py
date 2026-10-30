from pathlib import Path
from datetime import date
from decimal import Decimal, InvalidOperation
import csv
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "external_risk_analysis"
OUT.mkdir(parents=True, exist_ok=True)

SOURCE = OUT / "historical_reserve_publications_v1.csv"
LEDGER = OUT / "historical_release_ledger_v1.csv"
REPLAY = OUT / "historical_vintage_snapshots_v1.csv"

FIELDS = [
    "month", "indicator", "published_value", "unit",
    "publication_date", "source_url", "precision",
    "verification_status", "revision_note"
]

DECISIONS = [
    "2021-03-31", "2021-06-30", "2021-09-30",
    "2021-12-31", "2022-03-31", "2022-06-30"
]

INDICATORS = ["fx_reserves_usd_bn", "usd_lkr"]


def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, columns):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def initialize():
    if LEDGER.exists():
        print("[STOP] Ledger already exists:", LEDGER)
        print("Existing reviews have been preserved.")
        return

    rows = []

    if SOURCE.exists():
        for source_row in read_csv(SOURCE):
            rows.append({
                "month": source_row["month"],
                "indicator": source_row["indicator"],
                "published_value": source_row["published_value"],
                "unit": source_row["unit"],
                "publication_date": source_row["publication_date"],
                "source_url": source_row["source_url"],
                "precision": source_row.get("precision", ""),
                # Source identified does not mean value verified.
                "verification_status": "Pending",
                "revision_note": (
                    "Check original dated publication, value, "
                    "unit and release date"
                )
            })

    write_csv(LEDGER, rows, FIELDS)

    print("\n=== HISTORICAL VINTAGE LEDGER ===")
    print("Records:", len(rows))
    print("Verified:", 0)
    print("Saved:", LEDGER)
    print("No records automatically approved.")


def validate_record(row):
    if row["indicator"] not in INDICATORS:
        return None

    if row["verification_status"].strip() != "Verified":
        return None

    if not row["source_url"].startswith("https://"):
        return None

    try:
        observation = date.fromisoformat(row["month"] + "-01")
        published = date.fromisoformat(row["publication_date"])
        amount = Decimal(row["published_value"])
    except (ValueError, InvalidOperation):
        return None

    if not amount.is_finite() or amount <= 0:
        return None

    if published < observation:
        return None

    expected_unit = {
        "fx_reserves_usd_bn": "USD billions",
        "usd_lkr": "LKR per USD"
    }

    if row["unit"] != expected_unit[row["indicator"]]:
        return None

    return {
        **row,
        "published_date_object": published,
        "value_decimal": amount
    }


def replay():
    if not LEDGER.exists():
        raise FileNotFoundError(
            "Run --init first to create the release ledger."
        )

    ledger = read_csv(LEDGER)
    accepted = []

    for row in ledger:
        valid = validate_record(row)
        if valid:
            accepted.append(valid)

    snapshots = []

    for decision_text in DECISIONS:
        decision = date.fromisoformat(decision_text)

        for indicator in INDICATORS:
            eligible = [
                r for r in accepted
                if r["indicator"] == indicator
                and r["published_date_object"] <= decision
                and r["month"] <= decision_text[:7]
            ]

            # Latest observation month first. If that month
            # has multiple releases, use the latest release
            # available by this decision date.
            eligible.sort(
                key=lambda r: (
                    r["month"], r["published_date_object"]
                )
            )

            if eligible:
                selected = eligible[-1]

                snapshots.append({
                    "decision_date": decision_text,
                    "indicator": indicator,
                    "available_month": selected["month"],
                    "available_value": selected["published_value"],
                    "released_on": selected["publication_date"],
                    "source_url": selected["source_url"],
                    "status": "Verified source record available"
                })
            else:
                snapshots.append({
                    "decision_date": decision_text,
                    "indicator": indicator,
                    "available_month": "",
                    "available_value": "",
                    "released_on": "",
                    "source_url": "",
                    "status": "No verified historical value"
                })

    columns = [
        "decision_date", "indicator", "available_month",
        "available_value", "released_on", "source_url",
        "status"
    ]

    if REPLAY.exists():
        raise FileExistsError(
            "Replay output exists. Archive it before rerunning."
        )

    write_csv(REPLAY, snapshots, columns)

    print("\n=== SL-EWRIS HISTORICAL VINTAGE REPLAY ===")
    print("Ledger records:", len(ledger))
    print("Records passing basic eligibility checks:", len(accepted))
    print("Decision dates:", len(DECISIONS))

    for row in snapshots:
        print(
            row["decision_date"],
            row["indicator"],
            row["available_month"] or "Unavailable",
            row["available_value"]
        )

    print("\nSaved:", REPLAY)
    print("SQLite unchanged.")
    print("No unverified values used.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python historical_vintage_replay.py --init | --replay")
        sys.exit(1)

    if sys.argv[1] == "--init":
        initialize()
    elif sys.argv[1] == "--replay":
        replay()
    else:
        raise ValueError("Use --init or --replay")
