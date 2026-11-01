
# ============================================================
# SL-EWRIS — STEP 28.10
# DETECT CHANGING CBSL RESERVES WORKSHEET LAYOUTS
#
# Searches for official reserve asset headings throughout
# each monthly worksheet, not just A5/A6/F6.
#
# READ-ONLY:
# - Does not change the CBSL workbook
# - Does not change existing mapping files
# - Does not change the PostgreSQL database
# - Does not automatically approve observations
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

OUTPUT_DIR = (
    ROOT / "outputs" / "cbsl_extraction"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RESULT = OUTPUT_DIR / "reserve_layout_candidates_v2.csv"
SUMMARY = OUTPUT_DIR / "reserve_layout_summary_v2.csv"

EXPECTED = set(
    pd.period_range(
        "2014-01",
        "2025-12",
        freq="M"
    ).astype(str)
)

MONTH_NAMES = {}

for index in range(1, 13):
    MONTH_NAMES[calendar.month_name[index].lower()] = index
    MONTH_NAMES[calendar.month_abbr[index].lower()] = index


def identify_month(sheet_name):

    name = str(sheet_name).strip().lower()

    match = re.search(r"(20\d{2})", name)

    if not match:
        return None

    year = int(match.group(1))

    # Accept Jan-2015, April-2015, etc.
    for month_name, month_number in sorted(
        MONTH_NAMES.items(),
        key=lambda item: -len(item[0])
    ):

        if re.search(
            rf"(?<![a-z]){re.escape(month_name)}(?![a-z])",
            name
        ):
            result = f"{year:04d}-{month_number:02d}"

            if result in EXPECTED:
                return result

    return None


def normalize(value):

    if value is None:
        return ""

    text = str(value).lower()

    return re.sub(r"\s+", " ", text).strip()


def is_numeric(value):

    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def classify_label(text):

    # These are candidate labels only.
    # Final confirmation still requires checking
    # whether the value is TOTAL official reserves.
    if (
        "official reserve assets" in text
        or "gross official reserves" in text
    ):

        if "total" in text or text.strip().startswith(
            "official reserve assets"
        ):
            return "Possible total official reserves"

        return "Reserve heading or component"

    return None


def scan_sheet(ws, month):

    records = []

    max_row = min(ws.max_row, 120)
    max_col = min(ws.max_column, 30)

    for row in ws.iter_rows(
        min_row=1,
        max_row=max_row,
        min_col=1,
        max_col=max_col
    ):

        for cell in row:

            label = normalize(cell.value)
            classification = classify_label(label)

            if classification is None:
                continue

            # Avoid very long explanatory paragraphs.
            if len(label) > 170:
                continue

            # Examine the same row and next two rows.
            # Capture numeric candidates with their
            # actual Excel coordinates.
            nearby = []

            for row_number in range(
                cell.row,
                min(cell.row + 2, max_row) + 1
            ):

                for column_number in range(
                    cell.column + 1,
                    max_col + 1
                ):

                    other = ws.cell(
                        row_number,
                        column_number
                    )

                    if is_numeric(other.value):

                        nearby.append(
                            f"{other.coordinate}="
                            f"{other.value}"
                        )

            records.append({
                "month": month,
                "sheet": ws.title,
                "label_cell": cell.coordinate,
                "label_text": str(cell.value),
                "classification": classification,
                "nearby_numeric_cells": "; ".join(
                    nearby[:15]
                ),
                "numeric_candidate_count": len(nearby),
                "confirmed_value_cell": "",
                "confirmed_unit": "",
                "review_status": "Pending"
            })

    return records


def main():

    if not SOURCE.is_file():
        raise FileNotFoundError(
            f"CBSL workbook missing: {SOURCE}"
        )

    print("=" * 65)
    print("SL-EWRIS | RESERVES LAYOUT DETECTOR V2")
    print("=" * 65)

    wb = load_workbook(
        SOURCE,
        read_only=True,
        data_only=True
    )

    records = []
    matched_months = set()
    monthly_sheets = 0

    for sheet_name in wb.sheetnames:

        month = identify_month(sheet_name)

        if month is None:
            continue

        monthly_sheets += 1

        ws = wb[sheet_name]

        found = scan_sheet(ws, month)

        if found:
            matched_months.add(month)
            records.extend(found)
        else:
            print(
                f"[REVIEW] {month} | {sheet_name}: "
                "No recognizable reserve label"
            )

    wb.close()

    columns = [
        "month",
        "sheet",
        "label_cell",
        "label_text",
        "classification",
        "nearby_numeric_cells",
        "numeric_candidate_count",
        "confirmed_value_cell",
        "confirmed_unit",
        "review_status"
    ]

    result = pd.DataFrame(records, columns=columns)

    summary = pd.DataFrame([{
        "expected_months": len(EXPECTED),
        "monthly_worksheets_found": monthly_sheets,
        "months_with_reserve_labels": len(matched_months),
        "months_needing_review": len(
            EXPECTED - matched_months
        ),
        "candidate_label_rows": len(result),
    }])

    # Use distinct filenames so existing reviewed
    # files are never overwritten.
    if RESULT.exists() or SUMMARY.exists():
        raise FileExistsError(
            "V2 output already exists. Archive it "
            "before running the detector again."
        )

    result.to_csv(
        RESULT,
        index=False,
        encoding="utf-8-sig"
    )

    summary.to_csv(
        SUMMARY,
        index=False
    )

    print("\n=== RESULTS ===")

    print(summary.to_string(index=False))

    print("\n=== SAMPLE CANDIDATES ===")

    if not result.empty:

        print(
            result[
                [
                    "month",
                    "sheet",
                    "label_cell",
                    "nearby_numeric_cells"
                ]
            ].head(20).to_string(index=False)
        )

    print("\nSaved:", RESULT)
    print("Saved:", SUMMARY)

    print(
        "\n[PASS] Layout detection completed."
    )

    print(
        "All candidates are Pending verification."
    )

    print(
        "No original files or database values "
        "were modified."
    )


if __name__ == "__main__":
    main()
