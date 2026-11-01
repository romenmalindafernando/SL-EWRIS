
# ============================================================
# SL-EWRIS — STEP 28.14
# CBSL MONTHLY OFFICIAL RESERVE ASSETS EXTRACTOR
#
# Supports both confirmed CBSL workbook layouts:
#
# 2014-01 through 2015-05:
#   Heading: A5
#   Label:   A6
#   Value:   F6
#
# 2015-06 through 2025-12:
#   Date:    C5
#   Unit:    C6
#   Label:   A7
#   Value:   C7
#
# Source values are USD millions.
# Database candidates are USD billions.
#
# Original workbook and PostgreSQL remain unchanged.
# No publication dates or approvals are invented.
# ============================================================

from pathlib import Path
import calendar
import math
import re
import sys

import pandas as pd
from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT / "data" / "cbsl_downloads"
    / "table2.15.2_20260930_e.xlsx"
)

OUTPUT_DIR = ROOT / "outputs" / "cbsl_extraction"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CANDIDATE_FILE = (
    OUTPUT_DIR / "reserve_2014_2025_candidates_final.csv"
)

AUDIT_FILE = (
    OUTPUT_DIR / "reserve_extraction_audit_final.csv"
)

SOURCE_URL = (
    "https://www.cbsl.gov.lk/sites/default/files/"
    "cbslweb_documents/statistics/sheets/"
    "table2.15.2_20260930_e.xlsx"
)

EXPECTED_MONTHS = pd.period_range(
    "2014-01",
    "2025-12",
    freq="M"
).astype(str).tolist()

EXPECTED_SET = set(EXPECTED_MONTHS)

MONTH_LOOKUP = {}

for number in range(1, 13):
    MONTH_LOOKUP[calendar.month_name[number].lower()] = number
    MONTH_LOOKUP[calendar.month_abbr[number].lower()] = number


# ------------------------------------------------------------
# 1. IDENTIFY REPORTING MONTH
# ------------------------------------------------------------

def sheet_to_month(sheet_name):

    match = re.fullmatch(
        r"([A-Za-z]+)-(\d{2}|\d{4})",
        sheet_name.strip()
    )

    if not match:
        return None

    month_name = match.group(1).lower()
    year_text = match.group(2)

    month_number = MONTH_LOOKUP.get(month_name)

    if month_number is None:
        return None

    year = (
        2000 + int(year_text)
        if len(year_text) == 2
        else int(year_text)
    )

    month = f"{year:04d}-{month_number:02d}"

    return month if month in EXPECTED_SET else None


# ------------------------------------------------------------
# 2. CLEAN TEXT
# ------------------------------------------------------------

def normalize(value):

    return re.sub(
        r"\s+",
        " ",
        str(value or "").lower()
    ).strip()


# ------------------------------------------------------------
# 3. PARSE RESERVE VALUES WITH FOOTNOTES
# ------------------------------------------------------------

def parse_reserve_value(value):

    if value is None or isinstance(value, bool):
        raise ValueError("Reserve value missing or invalid")

    if isinstance(value, (int, float)):

        result = float(value)

    elif isinstance(value, str):

        text = value.strip()

        # Accept a leading numeric value with:
        # - commas as thousands separators
        # - optional decimals
        # - optional Roman-numeral footnotes
        #
        # Example:
        # "6,838 (II) (III)" -> 6838
        pattern = (
            r"^(\d{1,3}(?:,\d{3})+|\d+)"
            r"(?:\.(\d+))?"
            r"\s*(?:\([IVXivx]+\)\s*)*$"
        )

        match = re.fullmatch(pattern, text)

        if not match:
            raise ValueError(
                f"Unexpected reserve value format: {value!r}"
            )

        whole = match.group(1).replace(",", "")
        decimal = match.group(2)

        number_text = (
            whole + "." + decimal
            if decimal is not None
            else whole
        )

        result = float(number_text)

    else:

        raise ValueError(
            f"Unsupported value type: {type(value)}"
        )

    if not math.isfinite(result) or result <= 0:
        raise ValueError(
            "Reserve amount must be positive and finite"
        )

    return result


# ------------------------------------------------------------
# 4. VALIDATE REPORTING DATE IN LATER LAYOUT
# ------------------------------------------------------------

def check_later_reporting_date(value, expected_month):

    if value is None:
        return False

    text = str(value).strip()

    # Examples:
    # "as at 30/6/2015"
    # "as at 31/01/2019"
    # "End December 2025"

    numeric_match = re.search(
        r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)",
        text
    )

    if numeric_match:

        day, month, year = map(
            int,
            numeric_match.groups()
        )

        try:
            date_value = pd.Timestamp(
                year=year, month=month, day=day
            )
        except ValueError:
            return False

        period = pd.Period(date_value, freq="M")

        # Reserve stock must refer to month-end.
        return (
            str(period) == expected_month
            and day == date_value.days_in_month
        )

    written_match = re.search(
        r"\bend\s+([A-Za-z]+)\s+(\d{4})\b",
        text,
        flags=re.IGNORECASE
    )

    if written_match:

        month_number = MONTH_LOOKUP.get(
            written_match.group(1).lower()
        )

        year = int(written_match.group(2))

        return (
            month_number is not None
            and f"{year:04d}-{month_number:02d}"
            == expected_month
        )

    return False


# ------------------------------------------------------------
# 5. EXTRACT ONE WORKSHEET
# ------------------------------------------------------------

def inspect_sheet(ws, month):

    period = pd.Period(month, freq="M")

    if period <= pd.Period("2015-05", freq="M"):

        layout = "Earlier A5/A6/F6 layout"

        heading_cell = "A5"
        label_cell = "A6"
        value_cell = "F6"

        heading = normalize(
            ws[heading_cell].value
        )

        label = normalize(
            ws[label_cell].value
        )

        unit_ok = (
            "official reserve assets" in heading
            and re.search(
                r"usd\s*(mn|million|millions)\b",
                heading
            ) is not None
        )

        label_ok = label.startswith(
            "official reserve assets"
        )

        date_ok = True  # Month checked via sheet name.

    else:

        layout = "Later C5/C6/A7/C7 layout"

        heading_cell = "C6"
        label_cell = "A7"
        value_cell = "C7"

        heading = normalize(
            ws[heading_cell].value
        )

        label = normalize(
            ws[label_cell].value
        )

        unit_ok = re.search(
            r"usd\s*(mn|million|millions)\b",
            heading
        ) is not None

        # Require the main total heading.
        # Do not accept reserve components.
        label_ok = re.match(
            r"^a\.\s*official reserve assets\b",
            label
        ) is not None

        date_ok = check_later_reporting_date(
            ws["C5"].value,
            month
        )

    problems = []

    if not unit_ok:
        problems.append("Reserve unit/heading mismatch")

    if not label_ok:
        problems.append("Total reserve-assets label mismatch")

    if not date_ok:
        problems.append("Reporting date mismatch")

    raw_value = ws[value_cell].value

    value_mn = None

    try:
        value_mn = parse_reserve_value(raw_value)

    except ValueError as error:
        problems.append(str(error))

    candidate = {
        "month": month,
        "indicator": "fx_reserves_usd_bn",
        "candidate_value": (
            value_mn / 1000
            if value_mn is not None else None
        ),
        "unit": "USD billions",
        "source_filename": SOURCE.name,
        "source_sheet": ws.title,
        "source_column": value_cell,
        "source_row": ws[value_cell].row,
        "official_source_url": SOURCE_URL,
        "publication_date": "",
        "verification_status": "Pending",
    }

    audit = {
        "month": month,
        "sheet": ws.title,
        "layout": layout,
        "heading_cell": heading_cell,
        "label_cell": label_cell,
        "value_cell": value_cell,
        "raw_value": str(raw_value),
        "value_usd_mn": value_mn,
        "reporting_date_check": (
            "Passed" if date_ok else "Failed"
        ),
        "unit_check": (
            "Passed" if unit_ok else "Failed"
        ),
        "label_check": (
            "Passed" if label_ok else "Failed"
        ),
        "status": (
            "Candidate extracted"
            if not problems else "Needs review"
        ),
        "issues": "; ".join(problems),
    }

    return candidate, audit, not problems


# ------------------------------------------------------------
# 6. RUN EXTRACTION
# ------------------------------------------------------------

def main():

    if not SOURCE.is_file():
        raise FileNotFoundError(
            f"CBSL reserve workbook missing: {SOURCE}"
        )

    if CANDIDATE_FILE.exists() or AUDIT_FILE.exists():
        raise FileExistsError(
            "Final extraction files already exist. "
            "Archive them before rerunning."
        )

    print("=" * 65)
    print("SL-EWRIS | FINAL RESERVE EXTRACTION")
    print("=" * 65)

    wb = load_workbook(
        SOURCE,
        read_only=True,
        data_only=True
    )

    candidates = []
    audit_rows = []
    matched_months = set()

    for sheet_name in wb.sheetnames:

        month = sheet_to_month(sheet_name)

        if month is None:
            continue

        if month in matched_months:
            raise ValueError(
                f"Duplicate worksheet month: {month}"
            )

        matched_months.add(month)

        candidate, audit, valid = inspect_sheet(
            wb[sheet_name],
            month
        )

        audit_rows.append(audit)

        if valid:
            candidates.append(candidate)

    wb.close()

    missing_sheets = sorted(
        EXPECTED_SET - matched_months
    )

    audit_df = pd.DataFrame(audit_rows)

    candidate_df = pd.DataFrame(candidates)

    # Always save the audit so failed months are visible.
    audit_df.to_csv(
        AUDIT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print("\nExpected months:", len(EXPECTED_MONTHS))
    print("Monthly worksheets:", len(matched_months))
    print("Valid reserve candidates:", len(candidates))
    print(
        "Months needing review:",
        len(audit_rows) - len(candidates)
    )
    print("Missing worksheets:", len(missing_sheets))

    if missing_sheets:
        print(
            "Missing:",
            ", ".join(missing_sheets)
        )

    failed = audit_df[
        audit_df["status"] == "Needs review"
    ]

    if not failed.empty:
        print("\nLAYOUT OR VALUE EXCEPTIONS")
        print(
            failed[
                ["month", "sheet", "issues"]
            ].to_string(index=False)
        )

    if len(candidates) != 144 or missing_sheets:

        print(
            "\n[STOP] Complete candidate coverage "
            "not achieved. Review audit output."
        )

        print("Audit saved:", AUDIT_FILE)
        return

    candidate_df = candidate_df.sort_values(
        "month"
    ).reset_index(drop=True)

    candidate_df.to_csv(
        CANDIDATE_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n[PASS] 144 monthly reserve candidates extracted.")
    print("First:", candidate_df.iloc[0]["month"])
    print("Last:", candidate_df.iloc[-1]["month"])

    print("\nFIRST FIVE OBSERVATIONS")
    print(
        candidate_df[
            ["month", "candidate_value"]
        ].head().to_string(index=False)
    )

    print("\nLAST FIVE OBSERVATIONS")
    print(
        candidate_df[
            ["month", "candidate_value"]
        ].tail().to_string(index=False)
    )

    print("\nSaved:", CANDIDATE_FILE)
    print("Audit:", AUDIT_FILE)

    print(
        "\nAll candidates remain Pending source "
        "and historical-publication verification."
    )

    print("PostgreSQL database unchanged.")


if __name__ == "__main__":

    try:
        main()

    except (
        ValueError,
        FileNotFoundError,
        FileExistsError
    ) as error:

        print("[ERROR]", error)
        sys.exit(1)
