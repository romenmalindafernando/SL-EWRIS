
# ============================================================
# SL-EWRIS — STEP 22
# EXTRACT CBSL MONTHLY USD/LKR EXCHANGE RATES
#
# Confirmed workbook:
# IF_Monthly_Average_Exchange_Rates_September 2026.xlsx
#
# Worksheet: Avg ExRate
# Column B: Year
# Column C: Month
# Column E: USD/LKR
#
# Period: 2014-01 to 2025-12
#
# IMPORTANT:
# - Original Excel workbook is never modified.
# - PostgreSQL database is never modified.
# - Historical publication dates are NOT invented.
# - All extracted data remain pending verification.
# ============================================================

from pathlib import Path
import calendar
import re
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT
    / "data"
    / "cbsl_downloads"
    / "IF_Monthly_Average_Exchange_Rates_September 2026.xlsx"
)

OUTPUT_DIR = ROOT / "outputs" / "cbsl_extraction"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "usd_lkr_2014_2025_candidates.csv"

REVIEW_FILE = (
    ROOT
    / "outputs"
    / "cbsl_preparation"
    / "source_review_2014_2025.csv"
)

SHEET = "Avg ExRate"

MONTH_NAMES = {
    name.lower(): index
    for index, name in enumerate(calendar.month_name)
    if index > 0
}

EXPECTED_MONTHS = pd.period_range(
    "2014-01", "2025-12", freq="M"
).astype(str).tolist()


def parse_year(value):

    if pd.isna(value):
        return None

    text = str(value).strip()

    if not re.fullmatch(r"\d{4}(\.0)?", text):
        return None

    year = int(float(text))

    if not 1900 <= year <= 2100:
        return None

    return year


def parse_month(value):

    if pd.isna(value):
        return None

    name = str(value).strip().lower()

    return MONTH_NAMES.get(name)


def load_monthly_rates():

    if not SOURCE.exists():
        raise FileNotFoundError(
            f"CBSL workbook not found: {SOURCE}"
        )

    df = pd.read_excel(
        SOURCE,
        sheet_name=SHEET,
        header=None
    )

    # Check the exact header discovered in Step 22.
    header = df.iloc[5]

    if (
        str(header.iloc[1]).strip() != "Year"
        or str(header.iloc[2]).strip() != "Month"
        or str(header.iloc[4]).strip() != "USD"
    ):
        raise ValueError(
            "Workbook column structure does not match "
            "the inspected CBSL layout."
        )

    rows = []

    current_year = None

    # Python row index 8 = Excel row 9.
    for index in range(8, len(df)):

        row = df.iloc[index]

        year_value = row.iloc[1]
        month_value = row.iloc[2]
        usd_value = row.iloc[4]

        parsed_year = parse_year(year_value)

        if parsed_year is not None:
            current_year = parsed_year

        month_number = parse_month(month_value)

        # Skip annual average rows, blank separators,
        # headings and other non-monthly entries.
        if month_number is None:
            continue

        if current_year is None:
            raise ValueError(
                f"Excel row {index + 1}: "
                "Month found before a valid year."
            )

        month = (
            f"{current_year:04d}-{month_number:02d}"
        )

        if month not in EXPECTED_MONTHS:
            continue

        if pd.isna(usd_value):
            raise ValueError(
                f"Missing USD/LKR rate for {month}"
            )

        try:
            value = float(
                str(usd_value).replace(",", "").strip()
            )
        except ValueError as error:
            raise ValueError(
                f"Invalid USD/LKR value at {month}: "
                f"{usd_value!r}"
            ) from error

        if not (0 < value < float("inf")):
            raise ValueError(
                f"Non-positive or non-finite USD/LKR: "
                f"{month}"
            )

        rows.append({
            "month": month,
            "indicator": "usd_lkr",
            "candidate_value": value,
            "unit": "LKR per USD",
            "source_filename": SOURCE.name,
            "source_sheet": SHEET,
            "source_column": "E (USD)",
            "source_row": index + 1,
            "publication_date": "",
            "official_source_url": "",
            "verification_status": "Pending",
        })

    result = pd.DataFrame(rows)

    if result.empty:
        raise ValueError(
            "No observations extracted for 2014-2025."
        )

    duplicates = result[
        result.duplicated("month", keep=False)
    ]

    if not duplicates.empty:
        raise ValueError(
            "Duplicate monthly observations detected: "
            + ", ".join(duplicates["month"])
        )

    actual_months = set(result["month"])

    missing = [
        month for month in EXPECTED_MONTHS
        if month not in actual_months
    ]

    if missing:
        raise ValueError(
            f"Only {len(result)} of 144 months found. "
            f"Missing months: {missing}"
        )

    result = result.sort_values(
        "month"
    ).reset_index(drop=True)

    return result


def main():

    print("=" * 65)
    print("SL-EWRIS | USD/LKR EXCHANGE-RATE EXTRACTION")
    print("=" * 65)

    result = load_monthly_rates()

    # Do not overwrite existing extracted work.
    if OUTPUT_FILE.exists():
        raise FileExistsError(
            f"Output already exists: {OUTPUT_FILE}. "
            "Archive or rename it before rerunning."
        )

    result.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n[PASS] Extraction successful.")
    print("Observations:", len(result))
    print("First month:", result.iloc[0]["month"])
    print("Last month:", result.iloc[-1]["month"])

    print("\nFIRST FIVE OBSERVATIONS")
    print(
        result[
            ["month", "candidate_value"]
        ].head().to_string(index=False)
    )

    print("\nLAST FIVE OBSERVATIONS")
    print(
        result[
            ["month", "candidate_value"]
        ].tail().to_string(index=False)
    )

    print("\nSaved:", OUTPUT_FILE)

    print(
        "\n[NOTICE] Extracted observations are "
        "not automatically verified."
    )

    print(
        "Publication dates and the official "
        "source URL must still be documented."
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
        print(f"\n[ERROR] {error}")
        sys.exit(1)
