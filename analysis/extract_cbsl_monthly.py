
# ============================================================
# SL-EWRIS - STEP 22 (REVISED FOR YOUR ACTUAL FILES)
#
# Actual folder:
# data/cbsl_downloads/
#   IF_Monthly_Average_Exchange_Rates_Se...
#   table2.04_20260930_e.xlsx
#   cbsl_external_monthly_2014_2025.csv
#
# Modes:
#   python analysis/extract_cbsl_monthly.py
#   python analysis/extract_cbsl_monthly.py --extract
#
# SAFE:
# - Does not modify original Excel files.
# - Does not modify the PostgreSQL database.
# - Does not invent publication dates.
# - Does not auto-approve extracted observations.
# ============================================================

from pathlib import Path
import argparse
import json
import math
import re

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

DOWNLOAD_DIR = ROOT / "data" / "cbsl_downloads"
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "outputs" / "cbsl_extraction"

CONFIG_FILE = CONFIG_DIR / "cbsl_actual_sources.json"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# 1. MATCH THE FILES SHOWN IN YOUR SCREENSHOT
# ------------------------------------------------------------

SOURCE_PATTERNS = {
    "exchange_workbook": "IF_Monthly_Average_Exchange_Rates_Se*",
    "second_workbook": "table2.04_20260930_e.xlsx",
}

EXCEL_EXTENSIONS = {".xlsx", ".xls", ".xlsm"}

EXPECTED_MONTHS = set(
    pd.period_range(
        "2014-01", "2025-12", freq="M"
    ).astype(str)
)

KEYWORDS = [
    "gross official reserves",
    "official reserve",
    "foreign reserve",
    "reserve assets",
    "monthly average",
    "usd/lkr",
    "us dollar",
    "exchange rate",
    "lkr per usd",
]


def find_workbooks():

    if not DOWNLOAD_DIR.exists():
        raise FileNotFoundError(
            f"Folder not found: {DOWNLOAD_DIR}"
        )

    found = {}

    for label, pattern in SOURCE_PATTERNS.items():

        matches = [
            p for p in DOWNLOAD_DIR.glob(pattern)
            if (
                p.is_file()
                and p.suffix.lower() in EXCEL_EXTENSIONS
                and not p.name.startswith("~$")
            )
        ]

        if not matches:
            print(f"[MISSING] {label}: {pattern}")
            continue

        if len(matches) > 1:
            raise ValueError(
                f"Multiple files match {pattern}: "
                f"{[p.name for p in matches]}"
            )

        found[label] = matches[0]

    return found


# ------------------------------------------------------------
# 2. INSPECT WORKBOOK STRUCTURE
# ------------------------------------------------------------

def clean_text(value):

    if pd.isna(value):
        return ""

    return re.sub(
        r"\s+", " ", str(value)
    ).strip()


def inspect_workbook(label, path, file_number):

    print("\n" + "=" * 65)
    print(f"WORKBOOK: {path.name}")
    print("=" * 65)

    summary = []

    with pd.ExcelFile(path) as workbook:

        print("Worksheets:", workbook.sheet_names)

        for sheet_number, sheet in enumerate(
            workbook.sheet_names,
            start=1
        ):

            df = pd.read_excel(
                workbook,
                sheet_name=sheet,
                header=None,
                nrows=60,
                dtype=str
            )

            print(f"\nSHEET: {sheet}")
            print(f"Preview dimensions: {df.shape}")

            preview = df.iloc[:, :30].copy()

            preview.columns = [
                f"Column_{i+1}"
                for i in range(len(preview.columns))
            ]

            preview.insert(
                0,
                "Excel_Row",
                range(1, len(preview) + 1)
            )

            preview_file = OUTPUT_DIR / (
                f"preview_{file_number:02d}_"
                f"{sheet_number:02d}.csv"
            )

            preview.to_csv(
                preview_file,
                index=False,
                encoding="utf-8-sig"
            )

            matches = []

            for row_index, row in df.iterrows():

                content = " | ".join(
                    clean_text(value)
                    for value in row
                    if pd.notna(value)
                )

                matched = [
                    word for word in KEYWORDS
                    if word in content.lower()
                ]

                if matched:
                    matches.append(
                        f"Row {row_index+1}: "
                        f"{content[:180]}"
                    )

            for match in matches[:10]:
                print("  ", match)

            if not matches:
                print(
                    "  No identifying keywords in "
                    "the first 60 rows."
                )

            print("  Preview:", preview_file.name)

            summary.append({
                "workbook_type": label,
                "filename": path.name,
                "worksheet": sheet,
                "preview_rows": len(df),
                "preview_columns": len(df.columns),
                "keyword_matches": len(matches),
                "preview_file": preview_file.name,
            })

    return summary


# ------------------------------------------------------------
# 3. CREATE CONFIGURATION FOR THE ACTUAL FILES
# ------------------------------------------------------------

def create_config(found):

    if CONFIG_FILE.exists():
        print(
            "\nExisting extraction configuration "
            "preserved:",
            CONFIG_FILE
        )
        return

    config = {
        "sources": []
    }

    if "exchange_workbook" in found:

        config["sources"].append({
            "indicator": "usd_lkr",
            "filename": found[
                "exchange_workbook"
            ].name,
            "sheet": "",
            "header_row": None,
            "month_column": "",
            "value_column": "",
            "date_format": "",
            "source_unit": "LKR per USD",
            "source_url": ""
        })

    # Do not assume table2.04 is a reserves file.
    if "second_workbook" in found:

        config["sources"].append({
            "indicator": "UNCONFIRMED",
            "filename": found[
                "second_workbook"
            ].name,
            "sheet": "",
            "header_row": None,
            "month_column": "",
            "value_column": "",
            "date_format": "",
            "source_unit": "",
            "source_url": ""
        })

    CONFIG_FILE.write_text(
        json.dumps(
            config,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print("\nCreated configuration:", CONFIG_FILE)


# ------------------------------------------------------------
# 4. VALIDATE EXTRACTION CONFIGURATION
# ------------------------------------------------------------

def load_config():

    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            "Run the inspection mode first."
        )

    config = json.loads(
        CONFIG_FILE.read_text(encoding="utf-8")
    )

    sources = config.get("sources", [])

    if not sources:
        raise ValueError("No sources configured.")

    required = [
        "indicator",
        "filename",
        "sheet",
        "header_row",
        "month_column",
        "value_column",
        "date_format",
        "source_unit",
        "source_url"
    ]

    for source in sources:

        for field in required:

            if source.get(field) in ("", None):
                raise ValueError(
                    f"{source.get('filename')}: "
                    f"Set '{field}' after inspecting "
                    "the worksheet preview."
                )

        if source["indicator"] not in {
            "fx_reserves_usd_bn", "usd_lkr"
        }:
            raise ValueError(
                f"Unconfirmed indicator for "
                f"{source['filename']}. "
                "Inspect the workbook before "
                "assigning its economic meaning."
            )

        if (
            not isinstance(source["header_row"], int)
            or source["header_row"] < 1
        ):
            raise ValueError(
                "header_row must be a positive integer."
            )

        if not source["source_url"].startswith(
            "https://www.cbsl.gov.lk/"
        ):
            raise ValueError(
                "Provide the official CBSL "
                "source publication URL."
            )

        if source["indicator"] == "usd_lkr":
            if source["source_unit"] != "LKR per USD":
                raise ValueError(
                    "USD/LKR unit must be LKR per USD."
                )
        else:
            if source["source_unit"] not in {
                "USD millions",
                "USD billions"
            }:
                raise ValueError(
                    "Reserve units must be "
                    "USD millions or USD billions."
                )

    return sources


# ------------------------------------------------------------
# 5. EXTRACT VERIFIED-COLUMN CANDIDATES
# ------------------------------------------------------------

def extract_source(source, found_paths):

    filename = source["filename"]

    allowed_paths = {
        p.name: p
        for p in found_paths.values()
    }

    if filename not in allowed_paths:
        raise ValueError(
            f"Unrecognized source filename: {filename}"
        )

    path = allowed_paths[filename]

    frame = pd.read_excel(
        path,
        sheet_name=source["sheet"],
        header=source["header_row"] - 1
    )

    month_col = source["month_column"]
    value_col = source["value_column"]

    if month_col not in frame.columns:
        raise ValueError(
            f"Month column not found: {month_col}. "
            f"Actual columns: {list(frame.columns)}"
        )

    if value_col not in frame.columns:
        raise ValueError(
            f"Value column not found: {value_col}. "
            f"Actual columns: {list(frame.columns)}"
        )

    rows = []

    for index, row in frame.iterrows():

        raw_month = row[month_col]
        raw_value = row[value_col]

        if pd.isna(raw_month):
            if pd.notna(raw_value):
                raise ValueError(
                    f"{filename}: value without month "
                    f"at source row {index + source['header_row'] + 1}"
                )
            continue

        try:
            parsed_month = pd.to_datetime(
                raw_month,
                format=source["date_format"],
                errors="raise"
            )
        except (ValueError, TypeError):
            if pd.isna(raw_value):
                continue
            raise ValueError(
                f"{filename}: invalid month "
                f"at data row {index + 1}: {raw_month!r}"
            )

        month = parsed_month.strftime("%Y-%m")

        if month not in EXPECTED_MONTHS:
            continue

        if pd.isna(raw_value):
            continue

        number = str(raw_value).strip().replace(
            ",", ""
        )

        try:
            value = float(number)
        except ValueError as error:
            raise ValueError(
                f"{filename}, {month}: "
                f"Invalid numeric value {raw_value!r}"
            ) from error

        if not math.isfinite(value) or value <= 0:
            raise ValueError(
                f"{filename}, {month}: "
                "Value must be positive and finite."
            )

        if source["indicator"] == "fx_reserves_usd_bn":
            if source["source_unit"] == "USD millions":
                value /= 1000.0

        rows.append({
            "month": month,
            "indicator": source["indicator"],
            "candidate_value": value,
            "source_filename": filename,
            "source_sheet": source["sheet"],
            "source_column": value_col,
            "source_row": (
                index + source["header_row"] + 1
            ),
            "official_source_url": source["source_url"],
            "publication_date": "",
            "verification_status": "Pending"
        })

    return rows


# ------------------------------------------------------------
# 6. MAIN
# ------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--extract",
        action="store_true",
        help="Extract after completing source configuration."
    )

    args = parser.parse_args()

    found = find_workbooks()

    if not found:
        raise FileNotFoundError(
            "Neither of the expected CBSL "
            "workbooks could be located."
        )

    if not args.extract:

        all_summary = []

        for number, (label, path) in enumerate(
            found.items(),
            start=1
        ):
            all_summary.extend(
                inspect_workbook(label, path, number)
            )

        summary = pd.DataFrame(all_summary)

        summary_file = (
            OUTPUT_DIR / "actual_workbook_inspection.csv"
        )

        summary.to_csv(
            summary_file,
            index=False,
            encoding="utf-8-sig"
        )

        create_config(found)

        print("\n[PASS] Workbook inspection completed.")
        print("Summary:", summary_file)

        print(
            "\nReview the preview CSV files before "
            "editing cbsl_actual_sources.json."
        )

        return

    sources = load_config()

    collected = []

    for source in sources:
        extracted = extract_source(source, found)
        collected.extend(extracted)

        print(
            f"{source['indicator']}: "
            f"{len(extracted)} candidate observations"
        )

    if not collected:
        print("No observations extracted.")
        return

    result = pd.DataFrame(collected)

    duplicates = result.duplicated(
        subset=["month", "indicator"],
        keep=False
    )

    if duplicates.any():
        print(
            result.loc[
                duplicates,
                ["month", "indicator", "source_filename"]
            ].to_string(index=False)
        )

        raise ValueError(
            "Duplicate indicator-month observations."
        )

    result = result.sort_values(
        ["month", "indicator"]
    )

    output_file = (
        OUTPUT_DIR / "extracted_candidates.csv"
    )

    if output_file.exists():
        raise FileExistsError(
            "Previous extracted_candidates.csv exists. "
            "Archive it before another extraction."
        )

    result.to_csv(
        output_file,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n[PASS] Candidate extraction completed.")
    print("Saved:", output_file)

    print(
        "\nAll extracted values are Pending "
        "source verification."
    )
    print("PostgreSQL database unchanged.")


if __name__ == "__main__":
    main()
