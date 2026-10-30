from pathlib import Path
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
import calendar
import csv
import re

ROOT = Path(__file__).resolve().parents[1]

LEDGER = (
    ROOT / "outputs/external_risk_analysis"
    / "historical_release_ledger_v1.csv"
)

OUTPUT = (
    ROOT / "outputs/external_risk_analysis"
    / "historical_freshness_audit_v1.csv"
)

INDICATORS = {
    "usd_lkr": "LKR per USD",
    "fx_reserves_usd_bn": "USD billions"
}

REQUIRED = {
    "month", "indicator", "published_value",
    "unit", "publication_date", "source_url",
    "verification_status"
}

DECISION_DATES = [
    "2021-03-31",
    "2021-06-30",
    "2021-09-30",
    "2021-12-31",
    "2022-03-31",
    "2022-06-30"
]


def official_url(url):
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()

        return (
            parsed.scheme == "https"
            and (
                host == "cbsl.gov.lk"
                or host.endswith(".cbsl.gov.lk")
                or host == "statistics.gov.lk"
                or host.endswith(".statistics.gov.lk")
            )
        )
    except ValueError:
        return False


def month_number(value):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("Invalid month")

    year, month = map(int, value.split("-"))
    return year * 12 + month


def read_ledger():
    if not LEDGER.exists():
        raise FileNotFoundError(
            "Historical release ledger missing. "
            "Complete Step 37 --init first."
        )

    with LEDGER.open(
        "r", encoding="utf-8-sig", newline=""
    ) as f:
        reader = csv.DictReader(f)

        if not REQUIRED.issubset(set(reader.fieldnames or [])):
            raise ValueError("Missing required ledger columns")

        rows = list(reader)

    valid = []
    rejected = []

    for index, row in enumerate(rows, start=2):
        try:
            indicator = row["indicator"].strip()
            month = row["month"].strip()
            month_number(month)

            published = date.fromisoformat(
                row["publication_date"].strip()
            )

            value = Decimal(
                row["published_value"].strip()
            )

            if row["verification_status"].strip() != "Verified":
                raise ValueError("Not marked Verified")

            if indicator not in INDICATORS:
                raise ValueError("Unknown indicator")

            if row["unit"].strip() != INDICATORS[indicator]:
                raise ValueError("Unit mismatch")

            if not value.is_finite() or value <= 0:
                raise ValueError("Invalid numeric value")

            if published < date.fromisoformat(month + "-01"):
                raise ValueError("Publication before observation month")

            if not official_url(row["source_url"]):
                raise ValueError("Invalid official URL format")

            valid.append({
                "month": month,
                "indicator": indicator,
                "value": float(value),
                "published": published,
                "source_url": row["source_url"].strip()
            })

        except (ValueError, InvalidOperation, TypeError) as exc:
            rejected.append({
                "csv_row": index,
                "reason": str(exc)
            })

    return rows, valid, rejected


def make_snapshot(decision_text, records, max_age=3):
    decision = date.fromisoformat(decision_text)
    decision_month = decision.strftime("%Y-%m")
    decision_n = month_number(decision_month)

    eligible = [
        r for r in records
        if r["published"] <= decision
        and month_number(r["month"]) <= decision_n
    ]

    # Detect conflicting values for the same dated release.
    groups = {}

    for r in eligible:
        key = (r["month"], r["indicator"], r["published"])
        groups.setdefault(key, set()).add(r["value"])

    conflicts = {
        key for key, values in groups.items()
        if len(values) > 1
    }

    if conflicts:
        return {
            "decision_date": decision_text,
            "usd_lkr_month": "",
            "reserves_month": "",
            "usd_lkr_age_months": "",
            "reserves_age_months": "",
            "same_reporting_month": False,
            "both_fresh": False,
            "usd_lkr_3m_ready": False,
            "reserves_3m_ready": False,
            "assessment_ready": False,
            "status": "Conflicting historical releases"
        }

    # Latest publication wins for each indicator-month.
    vintages = {}

    for r in sorted(
        eligible, key=lambda x: x["published"]
    ):
        vintages[(r["month"], r["indicator"])] = r

    latest = {}

    for indicator in INDICATORS:
        candidates = [
            r for r in vintages.values()
            if r["indicator"] == indicator
        ]

        latest[indicator] = (
            max(
                candidates,
                key=lambda x: (
                    month_number(x["month"]),
                    x["published"]
                )
            )
            if candidates else None
        )

    fx = latest["usd_lkr"]
    reserves = latest["fx_reserves_usd_bn"]

    fx_age = (
        decision_n - month_number(fx["month"])
        if fx else None
    )

    reserve_age = (
        decision_n - month_number(reserves["month"])
        if reserves else None
    )

    same_month = bool(
        fx and reserves
        and fx["month"] == reserves["month"]
    )

    both_fresh = bool(
        fx_age is not None
        and reserve_age is not None
        and fx_age <= max_age
        and reserve_age <= max_age
    )

    def has_three_month_baseline(record, indicator):
        if record is None:
            return False

        n = month_number(record["month"]) - 3
        year, zero_based_month = divmod(n - 1, 12)

        prior_month = (
            f"{year:04d}-{zero_based_month + 1:02d}"
        )

        return (prior_month, indicator) in vintages

    fx_baseline = has_three_month_baseline(
        fx, "usd_lkr"
    )

    reserve_baseline = has_three_month_baseline(
        reserves, "fx_reserves_usd_bn"
    )

    ready = bool(
        same_month
        and both_fresh
        and fx_baseline
        and reserve_baseline
    )

    if not fx or not reserves:
        status = "Missing eligible indicator"
    elif not same_month:
        status = "Reporting months differ"
    elif not both_fresh:
        status = "Stale observations"
    elif not (fx_baseline and reserve_baseline):
        status = "Missing three-month baseline"
    else:
        status = "Structurally ready; source audit still required"

    return {
        "decision_date": decision_text,
        "usd_lkr_month": fx["month"] if fx else "",
        "reserves_month": reserves["month"] if reserves else "",
        "usd_lkr_age_months": (
            fx_age if fx_age is not None else ""
        ),
        "reserves_age_months": (
            reserve_age if reserve_age is not None else ""
        ),
        "same_reporting_month": same_month,
        "both_fresh": both_fresh,
        "usd_lkr_3m_ready": fx_baseline,
        "reserves_3m_ready": reserve_baseline,
        "assessment_ready": ready,
        "status": status
    }


def create_audit(max_age=3):
    rows, valid, rejected = read_ledger()

    audit = [
        make_snapshot(day, valid, max_age)
        for day in DECISION_DATES
    ]

    return rows, valid, rejected, audit


if __name__ == "__main__":
    rows, valid, rejected, audit = create_audit()

    if OUTPUT.exists():
        raise FileExistsError(
            "Audit output already exists; preserving it."
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=list(audit[0].keys())
        )
        writer.writeheader()
        writer.writerows(audit)

    print("\n=== SL-EWRIS DATA FRESHNESS AUDIT ===")
    print("Ledger records:", len(rows))
    print("Structurally eligible records:", len(valid))
    print("Pending/rejected records:", len(rejected))
    print(
        "Structurally ready decision dates:",
        sum(r["assessment_ready"] for r in audit)
    )

    for row in audit:
        print(
            row["decision_date"],
            "|", row["status"]
        )

    print("\nSaved:", OUTPUT)
    print("SQLite and evidence ledger unchanged.")
    print(
        "Structural eligibility does not prove "
        "independent source verification."
    )
