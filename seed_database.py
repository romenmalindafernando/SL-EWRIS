
# ============================================================
# SL-EWRIS
# STEP 6 - IMPORT HISTORICAL DATA INTO SQLITE
# ============================================================

from pathlib import Path
from datetime import date
from math import isfinite

import pandas as pd

from database import (
    COLUMN_TYPES,
    DATA_COLUMNS,
    DATABASE_PATH,
    connect_database,
    create_tables,
    count_observations,
    show_database_info,
)


# ------------------------------------------------------------
# 1. File location
# ------------------------------------------------------------

ROOT = Path(__file__).resolve().parent

CSV_FILE = (
    ROOT
    / "outputs"
    / "validation"
    / "validated_historical_data.csv"
)


# ------------------------------------------------------------
# 2. Identify numeric columns
# ------------------------------------------------------------

NUMERIC_COLUMNS = [
    name
    for name, data_type in COLUMN_TYPES.items()
    if data_type == "REAL"
]


# ------------------------------------------------------------
# 3. Load and check validated data
# ------------------------------------------------------------

def load_historical_data():

    if not CSV_FILE.is_file():

        raise FileNotFoundError(
            "Validated historical CSV not found.\n"
            "Run Step 5 first:\n"
            "python analysis/validate_data.py"
        )

    df = pd.read_csv(
        CSV_FILE,
        dtype={"month": "string"}
    )

    missing_columns = [
        column
        for column in DATA_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing dataset columns: {missing_columns}"
        )

    # Only import the known database columns.
    # The extra 'date' column produced in Step 5
    # is not required in SQLite.
    df = df[DATA_COLUMNS].copy()

    if df["month"].isna().any():
        raise ValueError("Missing month values detected.")

    if df["month"].duplicated().any():
        raise ValueError("Duplicate months detected.")

    expected_months = pd.period_range(
        start="2014-01",
        end="2025-12",
        freq="M"
    ).astype(str).tolist()

    actual_months = sorted(df["month"].tolist())

    if actual_months != expected_months:
        raise ValueError(
            "Historical CSV must contain exactly "
            "January 2014 to December 2025."
        )

    # Validate numeric fields again before importing.
    for column in NUMERIC_COLUMNS:

        original = df[column]

        converted = pd.to_numeric(
            original,
            errors="coerce"
        )

        invalid_text = (
            original.notna()
            & converted.isna()
        )

        if invalid_text.any():
            raise ValueError(
                f"Invalid numeric data in {column}"
            )

        if not converted.dropna().map(isfinite).all():
            raise ValueError(
                f"Non-finite numeric data in {column}"
            )

        df[column] = converted

    if df["source"].isna().any():
        raise ValueError("Missing data sources detected.")

    # Validate publication dates if supplied.
    # Missing historical publication dates stay missing.
    for value in df["publication_date"].dropna():

        date.fromisoformat(str(value))

    return df.sort_values("month").reset_index(drop=True)


# ------------------------------------------------------------
# 4. Convert pandas missing values to SQLite NULL
# ------------------------------------------------------------

def prepare_records(df):

    records = []

    for record in df.to_dict(orient="records"):

        cleaned = []

        for column in DATA_COLUMNS:

            value = record[column]

            if pd.isna(value):
                cleaned.append(None)

            elif column in NUMERIC_COLUMNS:
                cleaned.append(float(value))

            else:
                cleaned.append(str(value))

        records.append(tuple(cleaned))

    return records


# ------------------------------------------------------------
# 5. Import data without overwriting existing months
# ------------------------------------------------------------

def import_historical_data():

    print("\n" + "=" * 60)
    print("SL-EWRIS - HISTORICAL DATABASE IMPORT")
    print("=" * 60)

    df = load_historical_data()

    records = prepare_records(df)

    print(f"\nValidated historical rows: {len(records)}")

    connection = connect_database()

    try:

        create_tables(connection)

        # Column names come from our fixed internal schema.
        column_names = ", ".join(
            f'"{column}"'
            for column in DATA_COLUMNS
        )

        placeholders = ", ".join(
            ["?"] * len(DATA_COLUMNS)
        )

        insert_sql = f"""
            INSERT INTO economic_monthly
                ({column_names})
            VALUES ({placeholders})
            ON CONFLICT(month) DO NOTHING
        """

        before = connection.total_changes

        # Transaction: either the entire insertion succeeds
        # or no new historical rows are committed.
        with connection:

            connection.executemany(
                insert_sql,
                records
            )

        inserted = connection.total_changes - before

        skipped = len(records) - inserted

        print(f"\nNewly inserted records: {inserted}")
        print(f"Existing records skipped: {skipped}")

        show_database_info(connection)

        print("\n[PASS] Historical import completed.")

        print(
            "\nMissing economic observations remain NULL."
        )

        print(
            "\nExisting monthly records were not overwritten."
        )

    finally:
        connection.close()


# ------------------------------------------------------------
# 6. Main program
# ------------------------------------------------------------

if __name__ == "__main__":

    import_historical_data()
