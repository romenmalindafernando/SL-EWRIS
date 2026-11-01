from pathlib import Path
import csv
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "outputs" / "external_risk_analysis"

REGISTER = FOLDER / "publication_evidence_register_2020_2022.csv"
LEDGER = FOLDER / "historical_release_ledger_v1.csv"

EVIDENCE_FILES = [
    (
        FOLDER / "cbsl_documented_evidence_v1.csv",
        "historically_published_value",
        "report_date",
        "official_source_url"
    ),
    (
        FOLDER / "cbsl_additional_evidence_v2.csv",
        "published_value",
        "report_date",
        "source_url"
    )
]

MATRIX = FOLDER / "historical_evidence_coverage_matrix_v1.csv"
DETAIL = FOLDER / "historical_evidence_coverage_details_v1.csv"

INDICATORS = [
    "fx_reserves_usd_bn",
    "usd_lkr"
]


def read_csv(path):
    if not path.exists():
        return []

    with path.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        return list(csv.DictReader(file))


def month_list():
    months = []

    for year in (2020, 2021, 2022):
        for month in range(1, 13):
            months.append(f"{year}-{month:02d}")

    return months


def compare_rounded(retrospective, published):
    try:
        original = Decimal(str(retrospective))
        reported = Decimal(str(published))

        if not original.is_finite() or not reported.is_finite():
            return "Cannot compare"

        # Use the decimal precision of the published value.
        rounded = original.quantize(
            reported.as_tuple().exponent
            and Decimal(1).scaleb(reported.as_tuple().exponent)
            or Decimal("1"),
            rounding=ROUND_HALF_UP
        )

        return (
            "Consistent at reported precision"
            if rounded == reported
            else "Mismatch - investigate"
        )

    except (InvalidOperation, ValueError, TypeError):
        return "Cannot compare"


def build_coverage():

    if not REGISTER.exists():
        raise FileNotFoundError(
            "Step 33 publication evidence register missing."
        )

    reference_rows = read_csv(REGISTER)

    reference = {}

    for row in reference_rows:
        key = (row["month"], row["indicator"])

        if key in reference:
            raise ValueError(
                f"Duplicate historical reference: {key}"
            )

        reference[key] = row

    expected = {
        (month, indicator)
        for month in month_list()
        for indicator in INDICATORS
    }

    if set(reference.keys()) != expected:
        missing = expected - set(reference.keys())
        extra = set(reference.keys()) - expected

        raise ValueError(
            f"Unexpected register coverage. "
            f"Missing: {sorted(missing)}; "
            f"Extra: {sorted(extra)}"
        )

    evidence = {}

    for path, value_col, date_col, url_col in EVIDENCE_FILES:

        for row in read_csv(path):
            key = (row["month"], row["indicator"])

            if key not in expected:
                raise ValueError(
                    f"Unexpected evidence record: {key}"
                )

            evidence.setdefault(key, []).append({
                "published_value": row[value_col],
                "report_date": row[date_col],
                "source_url": row[url_col],
                "source_file": path.name
            })

    ledger_rows = read_csv(LEDGER)
    ledger = {}

    for row in ledger_rows:
        key = (row["month"], row["indicator"])
        ledger.setdefault(key, []).append(row)

    details = []

    for month in month_list():

        for indicator in INDICATORS:

            key = (month, indicator)

            original = reference[key]
            evidence_items = evidence.get(key, [])
            ledger_items = ledger.get(key, [])

            # Report evidence may have several publication
            # versions. Never silently choose one.
            if not evidence_items:
                evidence_status = "No report evidence identified"
                rounded_status = "Not assessed"
            elif len(evidence_items) > 1:
                evidence_status = "Multiple reports - review"
                rounded_status = "Multiple evidence versions"
            else:
                evidence_status = "Report evidence identified"

                rounded_status = compare_rounded(
                    original["retrospective_value"],
                    evidence_items[0]["published_value"]
                )

            verified_count = sum(
                r.get("verification_status", "").strip()
                == "Verified"
                for r in ledger_items
            )

            ledger_status = (
                "Marked Verified - independent audit required"
                if verified_count > 0
                else "Not marked Verified"
            )

            if evidence_status == "No report evidence identified":
                next_action = "Find official dated publication"

            elif rounded_status == "Mismatch - investigate":
                next_action = "Investigate numeric mismatch"

            elif evidence_status == "Multiple reports - review":
                next_action = "Review historical publication versions"

            elif verified_count == 0:
                next_action = "Check source and document review"

            else:
                next_action = "Audit source before research use"

            first_evidence = (
                evidence_items[0] if evidence_items else {}
            )

            details.append({
                "month": month,
                "indicator": indicator,
                "retrospective_value":
                    original["retrospective_value"],
                "evidence_status": evidence_status,
                "historical_published_value":
                    first_evidence.get("published_value", ""),
                "report_date":
                    first_evidence.get("report_date", ""),
                "source_url":
                    first_evidence.get("source_url", ""),
                "evidence_count": len(evidence_items),
                "rounded_comparison": rounded_status,
                "ledger_status": ledger_status,
                "next_action": next_action
            })

    detail_lookup = {
        (r["month"], r["indicator"]): r
        for r in details
    }

    matrix = []

    for month in month_list():

        reserves = detail_lookup[
            (month, "fx_reserves_usd_bn")
        ]

        fx = detail_lookup[
            (month, "usd_lkr")
        ]

        evidence_count = sum(
            r["evidence_count"] > 0
            for r in (reserves, fx)
        )

        matrix.append({
            "month": month,
            "foreign_reserves":
                reserves["evidence_status"],
            "usd_lkr":
                fx["evidence_status"],
            "indicators_with_report_evidence":
                evidence_count,
            "report_evidence_coverage_pct":
                round(100 * evidence_count / 2, 1),
            "both_have_report_evidence":
                "Yes" if evidence_count == 2 else "No",
            "point_in_time_readiness":
                "Not established"
        })

    return matrix, details


def write_csv(path, records):
    if path.exists():
        raise FileExistsError(
            f"Output exists; preserving existing file: {path}"
        )

    with path.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=list(records[0].keys())
        )
        writer.writeheader()
        writer.writerows(records)


if __name__ == "__main__":

    matrix, details = build_coverage()

    if MATRIX.exists() or DETAIL.exists():
        raise FileExistsError(
            "An output already exists. "
            "Previous reports have been preserved."
        )

    FOLDER.mkdir(parents=True, exist_ok=True)

    write_csv(MATRIX, matrix)
    write_csv(DETAIL, details)

    identified = sum(
        r["evidence_count"] > 0
        for r in details
    )

    matched = sum(
        r["rounded_comparison"]
        == "Consistent at reported precision"
        for r in details
    )

    print("\n=== SL-EWRIS HISTORICAL COVERAGE ===")
    print("Reporting months:", len(matrix))
    print("Indicator-month records:", len(details))
    print("Records with report evidence:", identified)
    print("Rounded comparisons consistent:", matched)

    print("Months with both reports:", sum(
        r["both_have_report_evidence"] == "Yes"
        for r in matrix
    ))

    print("\nSaved:", MATRIX)
    print("Saved:", DETAIL)
    print("\nOriginal evidence records unchanged.")
    print("PostgreSQL database unchanged.")
    print("No records automatically verified.")
