
# ============================================================
# SL-EWRIS - STEP 28.12
# CORRECTED CBSL FOREIGN RESERVE MAPPING
#
# Recognizes:
#   Jan-2014
#   April-2014
#   May-15
#   Dec-25
#
# Checks A5, A6, and F6 for each monthly worksheet.
#
# Creates a NEW proposed mapping.
# Does not approve values or modify PostgreSQL.
# ============================================================

from pathlib import Path
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

OUTPUT_DIR = ROOT / "outputs" / "cbsl_extraction"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PROPOSED = (
    OUTPUT_DIR / "proposed_reserve_mapping_v3.csv"
)

AUDIT = (
    OUTPUT_DIR / "reserve_mapping_audit_v3.csv"
)

EXPECTED = set(
    pd.period_range(
        "2014-01", "2025-12", freq="M"
    ).astype(str)
)

MONTH_LOOKUP = {}

for i in range(1, 13):
    MONTH_LOOKUP[calendar.month_name[i].lower()] = i
    MONTH_LOOKUP[calendar.month_abbr[i].lower()] = i


def identify_month(name):
    """
    Recognize both four-digit and two-digit
    years in CBSL worksheet names.
    """

    name = name.strip()

    match = re.fullmatch(
        r"([A-Za-z]+)[- ](\d{2}|\d{4})",
        name
    )

    if match is None:
        return None

    month_name = match.group(1).lower()
    year_string = match.group(2)

    month_number = MONTH_LOOKUP.get(month_name)

    if month_number is None:
        return None

    if len(year_string) == 2:
        year = 2000 + int(year_string)
    else:
        year = int(year_string)

    result = f"{year:04d}-{month_number:02d}"

    return result if result in EXPECTED else None


def normalize(value):

    return re.sub(
        r"\s+", " ", str(value or "").lower()
    ).strip()


def check_sheet(ws, month):

    heading = normalize(ws["A5"].value)
    label = normalize(ws["A6"].value)
    raw_value = ws["F6"].value

    # Confirm the published reserve-assets heading
    # and USD million unit.
    heading_ok = (
        "official reserve assets" in heading
        and re.search(
            r"\busd\s*(mn|million|millions)\b",
            heading
        ) is not None
    )

    # Accept the observed total-series label, but
    # exclude obvious subcomponents.
    label_ok = (
        label.startswith("official reserve assets")
        and not any(
            word in label
            for word in [
                "gold",
                "foreign currency",
                "sdr holdings",
                "reserve position",
                "other reserve assets"
            ]
        )
    )

    value_ok = (
        isinstance(raw_value, (int, float))
        and not isinstance(raw_value, bool)
        and math.isfinite(raw_value)
        and raw_value > 0
    )

    valid = bool(
        heading_ok and label_ok and value_ok
    )

    reasons = []

    if not heading_ok:
        reasons.append("A5 heading/unit mismatch")

    if not label_ok:
        reasons.append("A6 reserve label mismatch")

    if not value_ok:
        reasons.append("F6 missing/invalid numeric value")

    return {
        "month": month,
        "sheet": ws.title,
        "label_cell": "A6",
        "label_text": str(ws["A6"].value or ""),
        "heading_text": str(ws["A5"].value or ""),
        "confirmed_month": month if valid else "",
        "confirmed_value_cell": "F6" if valid else "",
        "confirmed_unit": "USD millions" if valid else "",
        "candidate_value_usd_mn": (
            raw_value if value_ok else None
        ),
        "candidate_value_usd_bn": (
            raw_value / 1000 if value_ok else None
        ),
        "pattern_status": (
            "Pattern matched"
            if valid else "Needs manual inspection"
        ),
        "issue": "; ".join(reasons),
        "review_status": "Pending"
    }


def main():

    if not SOURCE.is_file():
        raise FileNotFoundError(
            f"CBSL workbook missing: {SOURCE}"
        )

    if PROPOSED.exists() or AUDIT.exists():
        raise FileExistsError(
            "V3 outputs already exist. "
            "Archive them before running again."
        )

    print("=" * 65)
    print("SL-EWRIS | RESERVE MAPPING V3")
    print("=" * 65)

    book = load_workbook(
        SOURCE,
        read_only=True,
        data_only=True
    )

    records = []

    for sheet in book.sheetnames:

        month = identify_month(sheet)

        if month is None:
            continue

        records.append(
            check_sheet(book[sheet], month)
        )

    book.close()

    if not records:
        raise ValueError(
            "No monthly reserve worksheets recognized."
        )

    df = pd.DataFrame(records)

    if df["month"].duplicated().any():
        raise ValueError(
            "Multiple worksheets map to the same month."
        )

    df = df.sort_values("month")

    matched = df[
        df["pattern_status"] == "Pattern matched"
    ].copy()

    missing_months = sorted(
        EXPECTED - set(df["month"])
    )

    df.to_csv(
        AUDIT,
        index=False,
        encoding="utf-8-sig"
    )

    # This file is compatible with the earlier
    # mapping structure, but remains Pending.
    proposal = matched[
        [
            "month",
            "sheet",
            "label_cell",
            "label_text",
            "confirmed_month",
            "confirmed_value_cell",
            "confirmed_unit",
            "review_status"
        ]
    ].copy()

    proposal = proposal.rename(
        columns={"month": "suggested_month"}
    )

    proposal.to_csv(
        PROPOSED,
        index=False,
        encoding="utf-8-sig"
    )

    print("\nExpected months:", len(EXPECTED))
    print("Recognized monthly sheets:", len(df))
    print("Matched A5/A6/F6 patterns:", len(matched))
    print(
        "Layouts needing review:",
        len(df) - len(matched)
    )
    print("Missing worksheet months:", len(missing_months))

    if missing_months:
        print(
            "\nMissing months:",
            ", ".join(missing_months)
        )

    failed = df[
        df["pattern_status"] == "Needs manual inspection"
    ]

    if not failed.empty:
        print("\nLAYOUT EXCEPTIONS")
        print(
            failed[
                ["month", "sheet", "issue"]
            ].to_string(index=False)
        )

    print("\nSaved audit:", AUDIT)
    print("Saved proposal:", PROPOSED)

    print(
        "\nAll proposed mappings remain Pending."
    )

    print(
        "The source workbook, existing mapping "
        "file and PostgreSQL database are unchanged."
    )


if __name__ == "__main__":
    main()
