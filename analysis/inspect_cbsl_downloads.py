
# ============================================================
# SL-EWRIS — STEP 19
# INSPECT OFFICIAL CBSL DOWNLOADED DATASETS
#
# Supported:
#   Excel: .xlsx, .xlsm, .xls
#   Text:  .csv
#
# This program is READ-ONLY.
# It will NOT edit your original CBSL files,
# historical data, or SQLite database.
# ============================================================

from pathlib import Path
import pandas as pd


# ------------------------------------------------------------
# 1. PROJECT PATHS
# ------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

DOWNLOAD_DIR = ROOT / "data" / "cbsl_downloads"

OUTPUT_DIR = ROOT / "outputs" / "cbsl_inspection"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# 2. FILE TYPES
# ------------------------------------------------------------

SUPPORTED_EXTENSIONS = {
    ".xlsx",
    ".xlsm",
    ".xls",
    ".csv",
}


# ------------------------------------------------------------
# 3. MAKE TEXT SAFE FOR OUTPUT
# ------------------------------------------------------------

def format_value(value, limit=90):

    if pd.isna(value):
        return ""

    result = str(value).replace("\n", " ")

    if len(result) > limit:
        result = result[:limit] + "..."

    return result


# ------------------------------------------------------------
# 4. INSPECT EXCEL WORKBOOK
# ------------------------------------------------------------

def inspect_excel(file_path):

    results = []

    workbook = pd.ExcelFile(file_path)

    print(f"\nWORKBOOK: {file_path.name}")

    print("Worksheets:", workbook.sheet_names)

    for sheet_name in workbook.sheet_names:

        print("\n" + "-" * 60)

        print("SHEET:", sheet_name)

        # Read without assuming where headers start.
        # This matters because CBSL workbooks may have
        # several title and metadata rows.
        df = pd.read_excel(
            workbook,
            sheet_name=sheet_name,
            header=None,
            nrows=15
        )

        print("Preview rows:", len(df))
        print("Preview columns:", len(df.columns))

        print("\nFIRST 15 ROWS:")

        for row_number, row in df.iterrows():

            cells = []

            for col_number, value in row.items():

                if pd.notna(value):

                    cells.append(
                        f"C{col_number + 1}: "
                        f"{format_value(value)}"
                    )

            if cells:

                print(
                    f"Row {row_number + 1}: "
                    + " | ".join(cells[:12])
                )

        results.append({
            "filename": file_path.name,
            "sheet_name": sheet_name,
            "preview_rows": len(df),
            "preview_columns": len(df.columns),
            "status": "Inspected",
        })

    return results


# ------------------------------------------------------------
# 5. INSPECT CSV FILE
# ------------------------------------------------------------

def inspect_csv(file_path):

    results = []

    print(f"\nCSV FILE: {file_path.name}")

    # Try common encodings used by spreadsheets.
    df = None
    last_error = None

    for encoding in [
        "utf-8-sig",
        "utf-8",
        "cp1252",
    ]:

        try:

            df = pd.read_csv(
                file_path,
                header=None,
                nrows=15,
                encoding=encoding,
                dtype=str
            )

            break

        except UnicodeError as error:
            last_error = error

    if df is None:
        raise ValueError(
            "Could not decode CSV"
        ) from last_error

    print("Preview columns:", len(df.columns))

    print("\nFIRST 15 ROWS:")

    for row_number, row in df.iterrows():

        cells = []

        for col_number, value in row.items():

            if pd.notna(value):

                cells.append(
                    f"C{col_number + 1}: "
                    f"{format_value(value)}"
                )

        if cells:

            print(
                f"Row {row_number + 1}: "
                + " | ".join(cells[:12])
            )

    results.append({
        "filename": file_path.name,
        "sheet_name": "CSV",
        "preview_rows": len(df),
        "preview_columns": len(df.columns),
        "status": "Inspected",
    })

    return results


# ------------------------------------------------------------
# 6. SCAN DOWNLOAD FOLDER
# ------------------------------------------------------------

def main():

    print("=" * 65)

    print("SL-EWRIS | STEP 19")

    print("CBSL HISTORICAL DOWNLOAD INSPECTION")

    print("=" * 65)

    DOWNLOAD_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    files = sorted(
        file
        for file in DOWNLOAD_DIR.iterdir()
        if (
            file.is_file()
            and file.suffix.lower()
            in SUPPORTED_EXTENSIONS
            and not file.name.startswith("~$")
        )
    )

    if not files:

        print("\nNo CBSL spreadsheets found.")

        print(
            "\nDownload the official reserve and "
            "exchange-rate datasets into:"
        )

        print(DOWNLOAD_DIR)

        return

    print(f"\nSupported files found: {len(files)}")

    all_results = []

    for file_path in files:

        print("\n" + "=" * 65)

        try:

            if file_path.suffix.lower() == ".csv":

                results = inspect_csv(file_path)

            else:

                results = inspect_excel(file_path)

            all_results.extend(results)

        except Exception as error:

            print(
                f"[ERROR] Could not inspect "
                f"{file_path.name}: {error}"
            )

            all_results.append({
                "filename": file_path.name,
                "sheet_name": None,
                "preview_rows": 0,
                "preview_columns": 0,
                "status": str(error),
            })

    summary = pd.DataFrame(all_results)

    output_file = (
        OUTPUT_DIR / "cbsl_workbook_inspection.csv"
    )

    summary.to_csv(
        output_file,
        index=False
    )

    print("\n" + "=" * 65)

    print("INSPECTION FINISHED")

    print("=" * 65)

    print("\nRESULT SUMMARY:")

    print(summary.to_string(index=False))

    print("\nSaved summary to:", output_file)

    print(
        "\nOriginal CBSL downloads were not modified."
    )

    print(
        "No economic figures were imported "
        "into SQLite."
    )


if __name__ == "__main__":
    main()
