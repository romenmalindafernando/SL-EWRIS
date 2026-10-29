
# ============================================================
# SL-EWRIS — STEP 20
# PREPARE CBSL MONTHLY DATA FOR REVIEW
#
# Reads original downloaded CBSL spreadsheets.
# Identifies candidate reserve/exchange-rate tables.
#
# READ-ONLY for original source files and SQLite.
# Does NOT invent, interpolate or import economic data.
# ============================================================

from pathlib import Path
import re
import pandas as pd


# ------------------------------------------------------------
# 1. PROJECT PATHS
# ------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

DOWNLOADS = ROOT / "data" / "cbsl_downloads"

OUTPUT = ROOT / "outputs" / "cbsl_preparation"

OUTPUT.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# 2. SUPPORTED FILES
# ------------------------------------------------------------

SUPPORTED = {".xlsx", ".xlsm", ".xls", ".csv"}

RESERVE_TERMS = [
    "gross official reserves",
    "official reserve assets",
    "international reserves",
    "foreign reserves",
    "gross reserves",
    "reserve assets",
]

EXCHANGE_TERMS = [
    "monthly average spot",
    "monthly average exchange",
    "usd/lkr",
    "lkr/usd",
    "us dollar",
    "us dollars",
    "exchange rate",
    "exchange rates",
]

DATE_TERMS = [
    "month",
    "year",
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
]

MAX_PREVIEW_ROWS = 35
MAX_PREVIEW_COLUMNS = 18


# ------------------------------------------------------------
# 3. NORMALIZE TEXT
# ------------------------------------------------------------

def normalize(value):

    if pd.isna(value):
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value).lower().strip()
    )


# ------------------------------------------------------------
# 4. READ WORKSHEETS
# ------------------------------------------------------------

def read_sheets(path):

    if path.suffix.lower() == ".csv":

        last_error = None

        for encoding in [
            "utf-8-sig",
            "utf-8",
            "cp1252",
        ]:

            try:

                df = pd.read_csv(
                    path,
                    header=None,
                    nrows=MAX_PREVIEW_ROWS,
                    dtype=str,
                    encoding=encoding,
                    on_bad_lines="error"
                )

                yield "CSV", df
                return

            except UnicodeError as error:
                last_error = error

        raise ValueError(
            f"Could not decode {path.name}"
        ) from last_error

    else:

        with pd.ExcelFile(path) as workbook:

            for sheet in workbook.sheet_names:

                df = pd.read_excel(
                    workbook,
                    sheet_name=sheet,
                    header=None,
                    nrows=MAX_PREVIEW_ROWS,
                    dtype=str
                )

                yield sheet, df


# ------------------------------------------------------------
# 5. IDENTIFY CANDIDATE CONTENT
# ------------------------------------------------------------

def evaluate_sheet(filename, sheet_name, df):

    # Include sheet names because some official
    # workbooks have short column headings.
    text_parts = [
        normalize(filename),
        normalize(sheet_name)
    ]

    for row in df.itertuples(index=False, name=None):

        for value in row:

            text_parts.append(normalize(value))

    searchable = " | ".join(text_parts)

    reserve_matches = [
        term for term in RESERVE_TERMS
        if term in searchable
    ]

    exchange_matches = [
        term for term in EXCHANGE_TERMS
        if term in searchable
    ]

    date_matches = [
        term for term in DATE_TERMS
        if term in searchable
    ]

    if reserve_matches and exchange_matches:
        category = "Mixed external-sector candidate"

    elif reserve_matches:
        category = "Reserve candidate"

    elif exchange_matches:
        category = "Exchange-rate candidate"

    else:
        category = "No clear indicator match"

    # These scores help prioritize inspection.
    # They are not evidence that a particular
    # column contains the correct statistical series.
    score = (
        4 * len(reserve_matches)
        + 4 * len(exchange_matches)
        + min(len(date_matches), 3)
    )

    return {
        "filename": filename,
        "sheet": sheet_name,
        "category": category,
        "review_score": score,
        "reserve_keywords": ", ".join(
            reserve_matches
        ),
        "exchange_keywords": ", ".join(
            exchange_matches
        ),
        "date_keywords": ", ".join(
            date_matches
        ),
        "preview_rows": len(df),
        "preview_columns": len(df.columns),
    }


# ------------------------------------------------------------
# 6. EXPORT SOURCE TABLE PREVIEW
# ------------------------------------------------------------

def prepare_preview(df, filename, sheet):

    # Show original Excel-style row and column
    # positions to make manual verification easier.

    preview = df.iloc[
        :MAX_PREVIEW_ROWS,
        :MAX_PREVIEW_COLUMNS
    ].copy()

    preview.columns = [
        f"Column_{i + 1}"
        for i in range(len(preview.columns))
    ]

    preview.insert(
        0,
        "Excel_Row_Number",
        range(1, len(preview) + 1)
    )

    return preview


# ------------------------------------------------------------
# 7. CREATE BLANK MONTHLY REVIEW WORKSHEET
# ------------------------------------------------------------

def create_review_worksheet():

    rows = []

    for period in pd.period_range(
        "2014-01",
        "2025-12",
        freq="M"
    ):

        month = str(period)

        for indicator, definition, unit in [
            (
                "fx_reserves_usd_bn",
                "End-of-month gross official reserves",
                "USD billions"
            ),
            (
                "usd_lkr",
                "Monthly-average USD/LKR exchange rate",
                "LKR per USD"
            ),
        ]:

            rows.append({
                "month": month,
                "indicator": indicator,
                "required_definition": definition,
                "unit": unit,
                "verified_value": None,
                "source_filename": None,
                "source_sheet": None,
                "source_column": None,
                "publication_date": None,
                "official_source_url": None,
                "verification_status": "Pending",
            })

    result = OUTPUT / "source_review_2014_2025.csv"

    # Never overwrite work the user has completed.
    if not result.exists():

        pd.DataFrame(rows).to_csv(
            result,
            index=False
        )

        print("Created review worksheet:", result)

    else:

        print(
            "Existing review worksheet preserved:",
            result
        )


# ------------------------------------------------------------
# 8. MAIN PROGRAM
# ------------------------------------------------------------

def main():

    print("=" * 65)
    print("SL-EWRIS | STEP 20")
    print("CBSL MONTHLY DATA PREPARATION")
    print("=" * 65)

    DOWNLOADS.mkdir(
        parents=True,
        exist_ok=True
    )

    files = sorted(
        p for p in DOWNLOADS.iterdir()
        if (
            p.is_file()
            and p.suffix.lower() in SUPPORTED
            and not p.name.startswith("~$")
        )
    )

    create_review_worksheet()

    if not files:

        print("\nNo CBSL downloads found in:")
        print(DOWNLOADS)
        print(
            "\nDownload official source files "
            "before proceeding with extraction."
        )
        return

    print(f"\nFiles discovered: {len(files)}")

    all_results = []

    preview_count = 0

    for file_number, path in enumerate(
        files,
        start=1
    ):

        print(f"\nInspecting: {path.name}")

        try:

            for sheet_number, (sheet, df) in enumerate(
                read_sheets(path),
                start=1
            ):

                result = evaluate_sheet(
                    path.name,
                    sheet,
                    df
                )

                all_results.append(result)

                print(
                    f"  Sheet: {sheet} | "
                    f"{result['category']} | "
                    f"Score: {result['review_score']}"
                )

                if result["review_score"] > 0:

                    preview = prepare_preview(
                        df,
                        path.name,
                        sheet
                    )

                    preview_path = (
                        OUTPUT
                        / f"preview_{file_number:03d}_"
                          f"{sheet_number:03d}.csv"
                    )

                    preview.to_csv(
                        preview_path,
                        index=False
                    )

                    preview_count += 1

        except Exception as error:

            print(
                f"[ERROR] Failed to read "
                f"{path.name}: {error}"
            )

            all_results.append({
                "filename": path.name,
                "sheet": "READ ERROR",
                "category": str(error),
                "review_score": -1,
                "reserve_keywords": "",
                "exchange_keywords": "",
                "date_keywords": "",
                "preview_rows": 0,
                "preview_columns": 0,
            })

    summary = pd.DataFrame(all_results)

    summary = summary.sort_values(
        "review_score",
        ascending=False
    )

    summary_file = (
        OUTPUT / "cbsl_candidate_tables.csv"
    )

    summary.to_csv(
        summary_file,
        index=False
    )

    print("\n" + "=" * 65)
    print("CANDIDATE TABLE SUMMARY")
    print("=" * 65)

    print(
        summary[
            [
                "filename",
                "sheet",
                "category",
                "review_score"
            ]
        ].to_string(index=False)
    )

    print("\nSource files inspected:", len(files))
    print("Candidate previews generated:", preview_count)

    print("\nSaved:", summary_file)
    print("Saved all outputs to:", OUTPUT)

    print(
        "\n[PASS] Source inspection completed."
    )

    print(
        "\nNo observations were imported or "
        "modified in SQLite."
    )

    print(
        "Candidate tables require verification "
        "before automatic extraction."
    )


if __name__ == "__main__":
    main()
