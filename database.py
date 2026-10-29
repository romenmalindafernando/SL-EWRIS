
# ============================================================
# SL-EWRIS
# STEP 6 - SQLITE ECONOMIC DATABASE
# ============================================================

from pathlib import Path
import sqlite3


# ------------------------------------------------------------
# 1. Database location
# ------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

DATABASE_DIR = BASE_DIR / "database"

DATABASE_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DATABASE_DIR / "economic_risk.db"


# ------------------------------------------------------------
# 2. Historical economic dataset schema
# ------------------------------------------------------------

# These columns correspond to our existing historical_data.csv.
# Each month is unique.
#
# The original and researcher-constructed price indices
# are kept separately.

COLUMN_TYPES = {
    "month": "TEXT PRIMARY KEY NOT NULL",
    "publication_date": "TEXT",

    "headline_yoy_pct": "REAL",
    "food_yoy_pct": "REAL",
    "nonfood_yoy_pct": "REAL",

    "ccpi_linked_jan2019_100": "REAL",

    "public_nominal_jan2019_100": "REAL",
    "informal_nominal_jan2019_100": "REAL",

    "public_real_ncpi_raw": "REAL",
    "informal_real_ncpi_raw": "REAL",

    "average_monthly_salary_lkr": "REAL",

    "fx_reserves_usd_bn": "REAL",
    "usd_lkr": "REAL",

    "source": "TEXT NOT NULL",
    "notes": "TEXT",

    "ccpi_published_base": "TEXT",

    "ccpi_headline_original": "REAL",
    "ccpi_food_original": "REAL",
    "ccpi_nonfood_original": "REAL",

    "public_nominal_original": "REAL",
    "informal_nominal_original": "REAL",

    "inflation_rate_source": "TEXT",
}


DATA_COLUMNS = list(COLUMN_TYPES.keys())


# ------------------------------------------------------------
# 3. Database connection
# ------------------------------------------------------------

def connect_database():
    """
    Open a connection to our SQLite database.
    """

    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")

    return connection


# ------------------------------------------------------------
# 4. Create the economic observations table
# ------------------------------------------------------------

def create_tables(connection):
    """
    Create the database table if it does not already exist.

    Existing observations are not deleted.
    """

    column_definitions = ",\n".join(
        f'"{name}" {data_type}'
        for name, data_type in COLUMN_TYPES.items()
    )

    sql = f"""
        CREATE TABLE IF NOT EXISTS economic_monthly (
            {column_definitions},

            record_origin TEXT NOT NULL
                DEFAULT 'historical_import',

            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            updated_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP
        )
    """

    connection.execute(sql)


# ------------------------------------------------------------
# 5. Count monthly observations
# ------------------------------------------------------------

def count_observations(connection):

    result = connection.execute(
        "SELECT COUNT(*) FROM economic_monthly"
    ).fetchone()

    return result[0]


# ------------------------------------------------------------
# 6. Retrieve the historical date range
# ------------------------------------------------------------

def get_date_range(connection):

    return connection.execute(
        """
        SELECT
            MIN(month) AS first_month,
            MAX(month) AS last_month
        FROM economic_monthly
        """
    ).fetchone()


# ------------------------------------------------------------
# 7. Retrieve monthly economic observations
# ------------------------------------------------------------

def get_monthly_data(connection, start=None, end=None):
    """
    Retrieve stored observations in chronological order.

    start and end use YYYY-MM format.

    NULL values remain NULL.
    """

    query = "SELECT * FROM economic_monthly WHERE 1 = 1"

    parameters = []

    if start is not None:
        query += " AND month >= ?"
        parameters.append(start)

    if end is not None:
        query += " AND month <= ?"
        parameters.append(end)

    query += " ORDER BY month"

    rows = connection.execute(
        query,
        parameters
    ).fetchall()

    return [dict(row) for row in rows]


# ------------------------------------------------------------
# 8. Database information
# ------------------------------------------------------------

def show_database_info(connection):

    total = count_observations(connection)

    date_range = get_date_range(connection)

    print("\n" + "=" * 60)
    print("SL-EWRIS - SQLITE DATABASE")
    print("=" * 60)

    print(f"Database: {DATABASE_PATH}")

    print(f"Total observations: {total}")

    print(f"First month: {date_range['first_month']}")

    print(f"Last month: {date_range['last_month']}")

    print("=" * 60)


# ------------------------------------------------------------
# 9. Allow independent testing
# ------------------------------------------------------------

if __name__ == "__main__":

    connection = connect_database()

    try:
        create_tables(connection)
        connection.commit()

        show_database_info(connection)

    finally:
        connection.close()
