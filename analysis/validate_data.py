
# ============================================================
# SL-EWRIS — SRI LANKA ECONOMIC RISK MONITORING SYSTEM
# STEP 5: HISTORICAL DATA IMPORT AND VALIDATION
#
# Historical period: January 2014 – December 2025
# Sources: DCS and CBSL
# ============================================================

from pathlib import Path

import pandas as pd


# ------------------------------------------------------------
# 1. Project paths
# ------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

DATA_FILE = ROOT / "data" / "historical_data.csv"

OUTPUT_DIR = ROOT / "outputs" / "validation"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# 2. Required dataset columns
# ------------------------------------------------------------

REQUIRED_COLUMNS = [
    "month",
    "publication_date",
    "headline_yoy_pct",
    "food_yoy_pct",
    "nonfood_yoy_pct",
    "ccpi_linked_jan2019_100",
    "public_nominal_jan2019_100",
    "informal_nominal_jan2019_100",
    "public_real_ncpi_raw",
    "informal_real_ncpi_raw",
    "average_monthly_salary_lkr",
    "fx_reserves_usd_bn",
    "usd_lkr",
    "source",
    "notes",
    "ccpi_published_base",
    "ccpi_headline_original",
    "ccpi_food_original",
    "ccpi_nonfood_original",
    "public_nominal_original",
    "informal_nominal_original",
    "inflation_rate_source",
]

NUMERIC_COLUMNS = [
    "headline_yoy_pct",
    "food_yoy_pct",
    "nonfood_yoy_pct",
    "ccpi_linked_jan2019_100",
    "public_nominal_jan2019_100",
    "informal_nominal_jan2019_100",
    "public_real_ncpi_raw",
    "informal_real_ncpi_raw",
    "average_monthly_salary_lkr",
    "fx_reserves_usd_bn",
    "usd_lkr",
    "ccpi_headline_original",
    "ccpi_food_original",
    "ccpi_nonfood_original",
    "public_nominal_original",
    "informal_nominal_original",
]

POSITIVE_COLUMNS = [
    "ccpi_linked_jan2019_100",
    "public_nominal_jan2019_100",
    "informal_nominal_jan2019_100",
    "public_real_ncpi_raw",
    "informal_real_ncpi_raw",
    "average_monthly_salary_lkr",
    "fx_reserves_usd_bn",
    "usd_lkr",
    "ccpi_headline_original",
    "ccpi_food_original",
    "ccpi_nonfood_original",
    "public_nominal_original",
    "informal_nominal_original",
]


# ------------------------------------------------------------
# 3. Load the original historical dataset
# ------------------------------------------------------------

print("\n" + "=" * 60)
print("SL-EWRIS — HISTORICAL DATA VALIDATION")
print("=" * 60)

if not DATA_FILE.is_file():
    raise FileNotFoundError(
        f"Historical dataset not found: {DATA_FILE}"
    )

df = pd.read_csv(DATA_FILE, dtype={"month": "string"})

print("\nDataset imported successfully.")
print(f"Original rows: {len(df)}")
print(f"Original columns: {len(df.columns)}")


# ------------------------------------------------------------
# 4. Validate dataset structure
# ------------------------------------------------------------

missing_columns = [
    column for column in REQUIRED_COLUMNS
    if column not in df.columns
]

if missing_columns:
    raise ValueError(
        f"Required columns are missing: {missing_columns}"
    )

if df.columns.duplicated().any():
    raise ValueError("Duplicate column names found.")

print("\n[PASS] Required columns are present.")


# ------------------------------------------------------------
# 5. Validate the monthly dates
# ------------------------------------------------------------

# Require exactly YYYY-MM, e.g. 2019-01
valid_month_format = df["month"].str.fullmatch(
    r"\d{4}-(0[1-9]|1[0-2])"
).fillna(False)

if not valid_month_format.all():
    raise ValueError("Invalid or missing YYYY-MM dates found.")

df["date"] = pd.to_datetime(
    df["month"],
    format="%Y-%m",
    errors="raise"
)

df = df.sort_values("date").reset_index(drop=True)

if df["date"].duplicated().any():
    duplicates = df.loc[
        df["date"].duplicated(keep=False), "month"
    ]
    raise ValueError(
        f"Duplicate observation months: {duplicates.tolist()}"
    )

expected_dates = pd.date_range(
    start="2014-01-01",
    end="2025-12-01",
    freq="MS"
)

if not pd.DatetimeIndex(df["date"]).equals(expected_dates):
    raise ValueError(
        "Monthly dates do not match the complete "
        "January 2014–December 2025 sequence."
    )

print("[PASS] All 144 monthly dates are present.")
print("[PASS] No duplicate months.")


# ------------------------------------------------------------
# 6. Convert numeric columns and detect invalid text
# ------------------------------------------------------------

for column in NUMERIC_COLUMNS:

    original = df[column]

    converted = pd.to_numeric(
        original,
        errors="coerce"
    )

    # Missing source data are allowed.
    # Non-missing text that cannot be converted is not allowed.
    invalid = original.notna() & converted.isna()

    if invalid.any():
        bad_months = df.loc[invalid, "month"].tolist()
        raise ValueError(
            f"Invalid numeric values in {column}: {bad_months}"
        )

    df[column] = converted


# ------------------------------------------------------------
# 7. Validate index values and percentage fields
# ------------------------------------------------------------

for column in POSITIVE_COLUMNS:

    invalid = df[column].notna() & (df[column] <= 0)

    if invalid.any():
        raise ValueError(
            f"Non-positive values found in {column}."
        )

# Inflation rates may legitimately be negative.
# Do not require YoY inflation to be positive.
print("[PASS] Numerical values validated.")


# ------------------------------------------------------------
# 8. Check source information and index-base metadata
# ------------------------------------------------------------

if df["source"].isna().any():
    raise ValueError("Missing source descriptions found.")

valid_bases = {"2013=100", "2021=100"}

if not df["ccpi_published_base"].isin(valid_bases).all():
    raise ValueError("Unexpected CCPI base labels found.")

print("[PASS] Source and CCPI-base metadata validated.")


# ------------------------------------------------------------
# 9. Summarize historical data availability
# ------------------------------------------------------------

coverage_rows = []

for column in NUMERIC_COLUMNS:

    available = df.loc[df[column].notna()]

    coverage_rows.append({
        "indicator": column,
        "available_months": len(available),
        "missing_months": int(df[column].isna().sum()),
        "first_available_month": (
            available["month"].iloc[0]
            if not available.empty else None
        ),
        "last_available_month": (
            available["month"].iloc[-1]
            if not available.empty else None
        ),
    })

coverage = pd.DataFrame(coverage_rows)

print("\n" + "=" * 60)
print("HISTORICAL DATA COVERAGE")
print("=" * 60)

print(coverage.to_string(index=False))


# ------------------------------------------------------------
# 10. Check important known coverage limits
# ------------------------------------------------------------

checks = {
    "CCPI observations": int(
        df["ccpi_headline_original"].notna().sum()
    ),
    "Headline YoY observations": int(
        df["headline_yoy_pct"].notna().sum()
    ),
    "Public nominal wage observations": int(
        df["public_nominal_original"].notna().sum()
    ),
    "Informal nominal wage observations": int(
        df["informal_nominal_original"].notna().sum()
    ),
}

print("\nKEY COVERAGE COUNTS")

for name, count in checks.items():
    print(f"{name}: {count}")

# These are expected for the historical source dataset.
# A mismatch stops the initial import for investigation.
expected_counts = {
    "CCPI observations": 144,
    "Headline YoY observations": 132,
    "Public nominal wage observations": 104,
    "Informal nominal wage observations": 84,
}

for name, expected in expected_counts.items():
    if checks[name] != expected:
        raise ValueError(
            f"{name}: expected {expected}, found {checks[name]}"
        )

print("\n[PASS] Historical source coverage matches expectations.")


# ------------------------------------------------------------
# 11. Preserve missing economic indicators
# ------------------------------------------------------------

optional_columns = [
    "publication_date",
    "average_monthly_salary_lkr",
    "fx_reserves_usd_bn",
    "usd_lkr",
]

print("\nOPTIONAL DATA AVAILABILITY")

for column in optional_columns:
    available_count = int(df[column].notna().sum())
    print(f"{column}: {available_count} populated records")

print(
    "\nNote: Missing reserves, exchange rates, salaries and "
    "publication dates are not estimated or replaced."
)


# ------------------------------------------------------------
# 12. Export validated datasets
# ------------------------------------------------------------

cleaned_file = OUTPUT_DIR / "validated_historical_data.csv"
coverage_file = OUTPUT_DIR / "data_coverage_summary.csv"

df.to_csv(cleaned_file, index=False)
coverage.to_csv(coverage_file, index=False)

print("\n" + "=" * 60)
print("DATA VALIDATION COMPLETED SUCCESSFULLY")
print("=" * 60)

print(f"Validated records: {len(df)}")
print(f"Historical period: {df['month'].iloc[0]} to "
      f"{df['month'].iloc[-1]}")

print(f"\nSaved validated data:\n{cleaned_file}")
print(f"\nSaved coverage summary:\n{coverage_file}")
