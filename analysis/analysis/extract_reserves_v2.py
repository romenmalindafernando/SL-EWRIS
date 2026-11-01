
from pathlib import Path
from datetime import datetime, date
import calendar
import math
import re

import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT / "data" / "cbsl_downloads"
    / "table2.15.2_20260930_e.xlsx"
)

OUT = ROOT / "outputs" / "cbsl_extraction"
OUT.mkdir(parents=True, exist_ok=True)

CANDIDATES = OUT / "reserve_candidates_v2.csv"
AUDIT = OUT / "reserve_audit_v2.csv"

SOURCE_URL = (
    "https://www.cbsl.gov.lk/sites/default/files/"
    "cbslweb_documents/statistics/sheets/"
    "table2.15.2_20260930_e.xlsx"
)

EXPECTED = set(
    pd.period_range(
        "2014-01", "2025-12", freq="M"
    ).astype(str)
)

MONTHS = {
    calendar.month_name[i].lower(): i
    for i in range(1, 13)
}
MONTHS.update({
    calendar.month_abbr[i].lower(): i
    for i in range(1, 13)
})


def sheet_month(name):
    match = re.fullmatch(
        r"([A-Za-z]+)-(\d{2}|\d{4})",
        name.strip()
    )
    if not match:
        return None

    month = MONTHS.get(match.group(1).lower())
    year_string = match.group(2)

    if month is None:
        return None

    year = int(year_string)
    if len(year_string) == 2:
        year += 2000

    result = f"{year:04d}-{month:02d}"
    return result if result in EXPECTED else None


def normalize(value):
    return re.sub(
        r"\s+", " ", str(value or "").lower()
    ).strip()


def parse_amount(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("Missing numeric amount")

    if isinstance(value, (int, float)):
        amount = float(value)
    else:
        text = str(value).strip()

        # Handles examples such as:
        # 6,838 (II) (III)
        match = re.fullmatch(
            r"(\d{1,3}(?:,\d{3})+|\d+)"
            r"(?:\.(\d+))?"
            r"\s*(?:\([IVXivx]+\)\s*)*",
            text
        )
        if not match:
            raise ValueError(
                f"Unexpected numeric format: {text}"
            )

        number = match.group(1).replace(",", "")
        if match.group(2):
            number += "." + match.group(2)

        amount = float(number)

    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("Invalid reserve amount")

    return amount


def reporting_date(value, expected_month):
    """
    Return the actual date shown in the workbook.

    A reporting date need not equal the last
    calendar day. It must belong to the expected
    month and be close to its end.
    """
    text = str(value or "").strip()

    match = re.search(
        r"(\d{1,2})/(\d{1,2})/(\d{4})",
        text
    )

    if match:
        day, month, year = map(int, match.groups())

        try:
            actual = date(year, month, day)
        except ValueError:
            return None

        last_day = calendar.monthrange(year, month)[1]

        if (
            actual.strftime("%Y-%m") == expected_month
            and last_day - day <= 4
        ):
            return actual.isoformat()

        return None

    match = re.search(
        r"\bEnd\s+([A-Za-z]+)\s+(\d{4})\b",
        text,
        flags=re.IGNORECASE
    )

    if match:
        month = MONTHS.get(match.group(1).lower())
        year = int(match.group(2))

        if month is not None:
            period = f"{year:04d}-{month:02d}"

            if period == expected_month:
                last_day = calendar.monthrange(
                    year, month
                )[1]
                return date(
                    year, month, last_day
                ).isoformat()

    return None


def inspect(ws, month):
    early = month <= "2015-05"

    if early:
        label_cell = "A6"
        unit_cell = "A5"
        value_cell = "F6"
        raw_date = ""
        actual_date = ""
        date_valid = True
    else:
        label_cell = "A7"
        unit_cell = "C6"
        value_cell = "C7"
        raw_date = str(ws["C5"].value or "")
        actual_date = reporting_date(
            ws["C5"].value, month
        )
        date_valid = actual_date is not None

    label = normalize(ws[label_cell].value)
    unit = normalize(ws[unit_cell].value)

    if early:
        label_valid = label.startswith(
            "official reserve assets"
        )
    else:
        # Accepts:
        # A. Official reserve assets
        # A. Official reserve assets(II)
        # A. Official reserve assetsII
        label_valid = re.match(
            r"^a\.\s*official reserve assets"
            r"(?:\b|ii\b)",
            label
        ) is not None

    unit_valid = (
        re.search(
            r"\busd\s*(mn|million|millions)\b",
            unit
        ) is not None
    )

    issues = []

    if not label_valid:
        issues.append("Reserve heading mismatch")

    if not unit_valid:
        issues.append("USD millions unit mismatch")

    if not date_valid:
        issues.append("Reporting date mismatch")

    raw_amount = ws[value_cell].value

    try:
        amount_mn = parse_amount(raw_amount)
    except ValueError as exc:
        amount_mn = None
        issues.append(str(exc))

    amount_bn = (
        amount_mn / 1000
        if amount_mn is not None
        else None
    )

    status = (
        "Candidate extracted"
        if not issues
        else "Needs review"
    )

    common = {
        "month": month,
        "source_sheet": ws.title,
        "source_cell": value_cell,
        "raw_reporting_date": raw_date,
        "observation_as_of_date": actual_date,
        "raw_reserve_value": str(raw_amount),
        "candidate_value_usd_mn": amount_mn,
        "candidate_value_usd_bn": amount_bn,
        "check_status": status,
        "issues": "; ".join(issues),
    }

    candidate = {
        "month": month,
        "indicator": "fx_reserves_usd_bn",
        "candidate_value": amount_bn,
        "unit": "USD billions",
        "observation_as_of_date": actual_date,
        "source_filename": SOURCE.name,
        "source_sheet": ws.title,
        "source_cell": value_cell,
        "official_source_url": SOURCE_URL,
        "publication_date": "",
        "verification_status": "Pending",
    }

    return common, candidate


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)

    if CANDIDATES.exists() or AUDIT.exists():
        raise FileExistsError(
            "V2 output already exists. "
            "Rename or archive it before rerunning."
        )

    wb = load_workbook(
        SOURCE, read_only=True, data_only=True
    )

    audits = []
    candidates = []
    seen = set()

    for name in wb.sheetnames:
        month = sheet_month(name)

        if month is None:
            continue

        if month in seen:
            raise ValueError(
                f"Duplicate month: {month}"
            )

        seen.add(month)
        audit, candidate = inspect(wb[name], month)
        audits.append(audit)

        if audit["check_status"] == "Candidate extracted":
            candidates.append(candidate)

    wb.close()

    missing = sorted(EXPECTED - seen)

    audit_df = pd.DataFrame(audits)
    audit_df.to_csv(
        AUDIT, index=False, encoding="utf-8-sig"
    )

    print("\n=== SL-EWRIS RESERVES V2 ===")
    print("Expected months:", len(EXPECTED))
    print("Recognized months:", len(seen))
    print("Accepted candidates:", len(candidates))
    print("Exceptions:", len(audits) - len(candidates))
    print("Missing months:", len(missing))

    failed = audit_df[
        audit_df["check_status"] == "Needs review"
    ]

    if not failed.empty:
        print("\nExceptions:")
        print(
            failed[
                ["month", "source_sheet", "issues"]
            ].to_string(index=False)
        )

    if len(candidates) == 144 and not missing:
        df = pd.DataFrame(candidates).sort_values("month")
        df.to_csv(
            CANDIDATES,
            index=False,
            encoding="utf-8-sig"
        )

        print("\n[PASS] 144 reserve candidates extracted")
        print("Saved:", CANDIDATES)

        print("\nSample observations:")
        print(
            df[
                [
                    "month",
                    "candidate_value",
                    "observation_as_of_date"
                ]
            ].iloc[
                [0, 17, 60, 95, 143]
            ].to_string(index=False)
        )
    else:
        print("\n[REVIEW] Full coverage not achieved")

    print("\nAudit:", AUDIT)
    print("PostgreSQL database unchanged.")
    print("All candidates remain Pending verification.")


if __name__ == "__main__":
    main()
