
"""
SL-EWRIS Step 12: Safely import verified monthly CBSL external indicators.

Run from Python_Economic_Risk project root:
    python import_external_indicators.py --template
    python import_external_indicators.py --dry-run
    python import_external_indicators.py --apply

Do not populate figures from annual reports as though they were monthly values.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import re
import psycopg
from database import connect_database

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ============================================================
# 1. PROJECT CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent


INPUT = (
    ROOT
    / "data"
    / "cbsl_external_monthly_2014_2025.csv"
)

FIELDS = [
    "month",
    "fx_reserves_usd_bn",
    "fx_reserves_published_on",
    "fx_reserves_source_url",
    "usd_lkr",
    "usd_lkr_published_on",
    "usd_lkr_source_url",
]

INDICATORS = [
    (
        "fx_reserves_usd_bn",
        "fx_reserves_published_on",
        "fx_reserves_source_url",
    ),
    (
        "usd_lkr",
        "usd_lkr_published_on",
        "usd_lkr_source_url",
    ),
]


# ============================================================
# 2. GENERATE MONTHLY DATES FROM 2014 TO 2025
# ============================================================

def month_iter():

    for year in range(2014, 2026):

        for month in range(1, 13):

            yield f"{year:04d}-{month:02d}"


# ============================================================
# 3. CREATE HISTORICAL CSV TEMPLATE
# ============================================================

def make_template():

    INPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if INPUT.exists():

        print(
            "Template already exists, leaving unchanged:",
            INPUT
        )

        return

    with INPUT.open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=FIELDS
        )

        writer.writeheader()

        for month in month_iter():

            writer.writerow({
                "month": month
            })

    print(
        "Created 144-row BLANK template:",
        INPUT
    )


# ============================================================
# 4. VALIDATE CBSL MONTHLY DATA
# ============================================================

def validate():

    if not INPUT.exists():

        raise FileNotFoundError(
            f"{INPUT} does not exist. "
            "Run --template first."
        )

    with INPUT.open(
        newline="",
        encoding="utf-8-sig"
    ) as f:

        reader = csv.DictReader(f)

        if reader.fieldnames != FIELDS:

            raise ValueError(
                f"CSV columns must be: {FIELDS}"
            )

        rows = list(reader)

    if (
        len(rows) != 144
        or [row["month"] for row in rows]
        != list(month_iter())
    ):

        raise ValueError(
            "Template must have exactly 144 "
            "unique ordered months "
            "(2014-01 to 2025-12)."
        )

    updates = []

    for row in rows:

        observation_month = dt.date.fromisoformat(
            row["month"] + "-01"
        )

        for (
            name,
            date_field,
            url_field
        ) in INDICATORS:

            raw = row[name].strip()

            published = row[date_field].strip()

            url = row[url_field].strip()

            # ----------------------------------------
            # Preserve missing data
            # ----------------------------------------

            if not raw:

                if published or url:

                    raise ValueError(
                        f"{row['month']}: "
                        f"{name} source info exists "
                        "but value is blank"
                    )

                continue

            # ----------------------------------------
            # Validate numerical value
            # ----------------------------------------

            try:

                value = float(raw)

            except ValueError as ex:

                raise ValueError(
                    f"{row['month']}: "
                    f"nonnumeric {name}: {raw}"
                ) from ex

            if (
                not math.isfinite(value)
                or value <= 0
            ):

                raise ValueError(
                    f"{row['month']}: "
                    f"{name} must be a positive "
                    "finite number"
                )

            # ----------------------------------------
            # Validate units
            # ----------------------------------------

            if (
                name == "usd_lkr"
                and value > 10000
            ):

                raise ValueError(
                    f"{row['month']}: "
                    "implausibly large LKR per USD; "
                    "check units"
                )

            if (
                name == "fx_reserves_usd_bn"
                and value > 1000
            ):

                raise ValueError(
                    f"{row['month']}: "
                    "check USD billions vs millions"
                )

            # ----------------------------------------
            # Require source information
            # ----------------------------------------

            if not published or not url:

                raise ValueError(
                    f"{row['month']}: "
                    f"{name} requires publication "
                    "date AND official source URL"
                )

            # ----------------------------------------
            # Validate publication date
            # ----------------------------------------

            try:

                pub_date = dt.date.fromisoformat(
                    published
                )

            except ValueError as ex:

                raise ValueError(
                    f"{row['month']}: "
                    f"invalid publication date "
                    f"{published}; expected YYYY-MM-DD"
                ) from ex

            if pub_date < observation_month:

                raise ValueError(
                    f"{row['month']}: "
                    "publication date cannot precede "
                    "observation month"
                )

            if pub_date > dt.date.today():

                raise ValueError(
                    f"{row['month']}: "
                    "publication date is in the future"
                )

            # ----------------------------------------
            # Accept official CBSL URLs only
            # ----------------------------------------

            if not re.match(
                r"^https://(?:www\.)?"
                r"cbsl\.gov\.lk(?:/|$)",
                url,
                re.I
            ):

                raise ValueError(
                    f"{row['month']}: "
                    "only official "
                    "https://www.cbsl.gov.lk "
                    "source URLs are accepted"
                )

            updates.append(
                (
                    row["month"],
                    name,
                    value,
                    published,
                    url
                )
            )

    return updates


# ============================================================
# 5. CREATE SOURCE HISTORY TABLE
# ============================================================

def ensure_log_table(connection):

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS
        external_indicator_import_log (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            month TEXT NOT NULL,

            indicator TEXT NOT NULL,

            value REAL NOT NULL,

            publication_date TEXT NOT NULL,

            source_url TEXT NOT NULL,

            action TEXT NOT NULL,

            imported_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


# ============================================================
# 6. IMPORT AND VERIFY EXTERNAL INDICATORS
# ============================================================

def run(apply):

    updates = validate()

    print(
        "Verified-format populated input values:",
        len(updates)
    )

    with connect_database() as connection:
        # ----------------------------------------
        # Check existing database table
        # ----------------------------------------

        table = connection.execute(
            """
            SELECT name
            FROM pg_catalog.pg_tables
            WHERE schemaname = current_schema()
              AND name = 'economic_monthly'
            """
        ).fetchone()

        if not table:

            raise RuntimeError(
                "Database is missing "
                "economic_monthly table."
            )

        columns = {
            row["name"]
            for row in connection.execute(
                """
                SELECT column_name AS name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'economic_monthly'
                """
            )
        }

        for field, _, _ in INDICATORS:

            if field not in columns:

                raise RuntimeError(
                    f"Database missing expected "
                    f"column {field}"
                )

        changes = []

        unchanged = []

        conflicts = []

        absent = []

        # ----------------------------------------
        # Compare CSV values against database
        # ----------------------------------------

        for (
            month,
            field,
            value,
            published,
            url
        ) in updates:

            old = connection.execute(
                f"""
                SELECT "{field}" AS value
                FROM economic_monthly
                WHERE month = ?
                """,
                (month,)
            ).fetchone()

            if old is None:

                absent.append(
                    (month, field)
                )

                continue

            if old["value"] is None:

                changes.append(
                    (
                        month,
                        field,
                        value,
                        published,
                        url
                    )
                )

            elif math.isclose(
                float(old["value"]),
                value,
                rel_tol=1e-10,
                abs_tol=1e-10
            ):

                unchanged.append(
                    (month, field)
                )

            else:

                conflicts.append(
                    (
                        month,
                        field,
                        old["value"],
                        value
                    )
                )

        # ----------------------------------------
        # Report comparison
        # ----------------------------------------

        print(
            f"New values: {len(changes)} | "
            f"unchanged: {len(unchanged)} | "
            f"conflicting: {len(conflicts)} | "
            f"missing months: {len(absent)}"
        )

        if absent:

            print(
                "Missing database months:",
                absent[:8]
            )

        if conflicts:

            print(
                "CONFLICTS: existing values "
                "will not be overwritten:",
                conflicts[:8]
            )

        # ----------------------------------------
        # Dry-run mode
        # ----------------------------------------

        if not apply:

            print(
                "DRY RUN ONLY: database unchanged. "
                "Use --apply to save verified "
                "new values."
            )

            return

        # ----------------------------------------
        # Abort if conflicts are detected
        # ----------------------------------------

        if conflicts or absent:

            raise RuntimeError(
                "Aborting apply due to conflicting "
                "values or absent months; "
                "database unchanged."
            )

        # ----------------------------------------
        # Save verified values
        # ----------------------------------------

        with connection:

            ensure_log_table(connection)

            for (
                month,
                field,
                value,
                published,
                url
            ) in changes:

                connection.execute(
                    f"""
                    UPDATE economic_monthly

                    SET "{field}" = ?,
                        updated_at = CURRENT_TIMESTAMP

                    WHERE month = ?
                      AND "{field}" IS NULL
                    """,
                    (value, month)
                )

                connection.execute(
                    """
                    INSERT INTO
                    external_indicator_import_log
                    (
                        month,
                        indicator,
                        value,
                        publication_date,
                        source_url,
                        action
                    )

                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        month,
                        field,
                        value,
                        published,
                        url,
                        "initial import"
                    )
                )

        print(
            "Applied values:",
            len(changes)
        )

        print(
            "Unchanged:",
            len(unchanged)
        )

        print(
            "Source metadata recorded in "
            "external_indicator_import_log."
        )


# ============================================================
# 7. COMMAND-LINE EXECUTION
# ============================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    group = parser.add_mutually_exclusive_group(
        required=True
    )

    group.add_argument(
        "--template",
        action="store_true"
    )

    group.add_argument(
        "--dry-run",
        action="store_true"
    )

    group.add_argument(
        "--apply",
        action="store_true"
    )

    args = parser.parse_args()

    if args.template:

        make_template()

    else:

        run(args.apply)
