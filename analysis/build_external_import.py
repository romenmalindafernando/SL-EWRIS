
# ============================================================
# SL-EWRIS — STEP 21
# BUILD VERIFIED CBSL EXTERNAL-SECTOR IMPORT FILE
#
# Input:
# outputs/cbsl_preparation/source_review_2014_2025.csv
#
# Output:
# outputs/cbsl_preparation/verified_external_import.csv
#
# Does not modify original source files or SQLite.
# ============================================================

from pathlib import Path
from datetime import date
from urllib.parse import urlparse
import math
import re
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

REVIEW_FILE = (
    ROOT / "outputs" / "cbsl_preparation"
    / "source_review_2014_2025.csv"
)

OUTPUT_FILE = (
    ROOT / "outputs" / "cbsl_preparation"
    / "verified_external_import.csv"
)

COLUMNS = [
    "month",
    "fx_reserves_usd_bn",
    "fx_reserves_published_on",
    "fx_reserves_source_url",
    "usd_lkr",
    "usd_lkr_published_on",
    "usd_lkr_source_url",
]

REVIEW_COLUMNS = [
    "month",
    "indicator",
    "required_definition",
    "unit",
    "verified_value",
    "source_filename",
    "source_sheet",
    "source_column",
    "publication_date",
    "official_source_url",
    "verification_status",
]

EXPECTED_MONTHS = pd.period_range(
    "2014-01", "2025-12", freq="M"
).astype(str).tolist()

INDICATOR_MAP = {
    "fx_reserves_usd_bn": (
        "fx_reserves_usd_bn",
        "fx_reserves_published_on",
        "fx_reserves_source_url",
        "USD billions",
        "End-of-month gross official reserves"
    ),
    "usd_lkr": (
        "usd_lkr",
        "usd_lkr_published_on",
        "usd_lkr_source_url",
        "LKR per USD",
        "Monthly-average USD/LKR exchange rate"
    ),
}


def valid_cbsl_url(raw):
    parsed = urlparse(raw)
    return (
        parsed.scheme == "https"
        and parsed.hostname in {
            "cbsl.gov.lk",
            "www.cbsl.gov.lk"
        }
        and not parsed.username
        and not parsed.password
    )


def required_text(value, label):
    if pd.isna(value) or not str(value).strip():
        raise ValueError(f"Missing {label}")
    return str(value).strip()


def load_review():

    if not REVIEW_FILE.exists():
        raise FileNotFoundError(
            "Source review worksheet missing. "
            "Run Step 20 first."
        )

    review = pd.read_csv(
        REVIEW_FILE,
        dtype=str,
        keep_default_na=False
    )

    missing = set(REVIEW_COLUMNS) - set(review.columns)
    if missing:
        raise ValueError(
            f"Missing review columns: {sorted(missing)}"
        )

    if review.duplicated(
        subset=["month", "indicator"]
    ).any():
        raise ValueError(
            "Duplicate month/indicator review rows found."
        )

    expected_pairs = {
        (month, indicator)
        for month in EXPECTED_MONTHS
        for indicator in INDICATOR_MAP
    }

    actual_pairs = set(
        zip(review["month"], review["indicator"])
    )

    if actual_pairs != expected_pairs:
        missing_pairs = expected_pairs - actual_pairs
        extra_pairs = actual_pairs - expected_pairs

        raise ValueError(
            "Review worksheet does not contain exactly "
            "the required 288 month-indicator pairs. "
            f"Missing: {list(missing_pairs)[:5]}; "
            f"Unexpected: {list(extra_pairs)[:5]}"
        )

    return review


def validate_verified_row(row):

    month = row["month"]
    indicator = row["indicator"]

    (
        value_column,
        published_column,
        url_column,
        required_unit,
        required_definition,
    ) = INDICATOR_MAP[indicator]

    value_text = required_text(
        row["verified_value"],
        f"{month} {indicator} value"
    )

    try:
        value = float(value_text)
    except ValueError as error:
        raise ValueError(
            f"{month}: Invalid numeric value {value_text}"
        ) from error

    if not math.isfinite(value) or value <= 0:
        raise ValueError(
            f"{month}: {indicator} must be positive "
            "and finite."
        )

    if row["unit"].strip() != required_unit:
        raise ValueError(
            f"{month}: Wrong unit for {indicator}. "
            f"Expected: {required_unit}"
        )

    if (
        row["required_definition"].strip()
        != required_definition
    ):
        raise ValueError(
            f"{month}: Indicator definition mismatch."
        )

    published_text = required_text(
        row["publication_date"],
        "publication date"
    )

    try:
        published = date.fromisoformat(published_text)
    except ValueError as error:
        raise ValueError(
            f"{month}: Publication date must be YYYY-MM-DD"
        ) from error

    observation_month = date.fromisoformat(month + "-01")

    if published < observation_month:
        raise ValueError(
            f"{month}: Publication date precedes "
            "the observation month."
        )

    if published > date.today():
        raise ValueError(
            f"{month}: Future publication date."
        )

    url = required_text(
        row["official_source_url"],
        "official source URL"
    )

    if not valid_cbsl_url(url):
        raise ValueError(
            f"{month}: Source must be an official "
            "HTTPS cbsl.gov.lk URL."
        )

    for field in [
        "source_filename",
        "source_sheet",
        "source_column"
    ]:
        required_text(row[field], field)

    return (
        value_column,
        published_column,
        url_column,
        value,
        published_text,
        url
    )


def main():

    print("=" * 65)
    print("SL-EWRIS | STEP 21")
    print("BUILD VERIFIED EXTERNAL-SECTOR IMPORT")
    print("=" * 65)

    review = load_review()

    verified = review[
        review["verification_status"]
        .str.strip().str.casefold() == "verified"
    ].copy()

    unverified_count = len(review) - len(verified)

    print(f"Expected review entries: {len(review)}")
    print(f"Marked Verified: {len(verified)}")
    print(f"Pending or unverified: {unverified_count}")

    result = pd.DataFrame(
        {"month": EXPECTED_MONTHS}
    )

    for column in COLUMNS[1:]:
        result[column] = ""

    result = result.set_index("month")

    for _, row in verified.iterrows():

        (
            value_column,
            published_column,
            url_column,
            value,
            publication_date,
            source_url
        ) = validate_verified_row(row)

        month = row["month"]

        result.loc[month, value_column] = value

        result.loc[month, published_column] = (
            publication_date
        )

        result.loc[month, url_column] = source_url

    result = result.reset_index()
    result = result[COLUMNS]

    # Prevent overwriting a previously reviewed export.
    if OUTPUT_FILE.exists():
        raise FileExistsError(
            f"{OUTPUT_FILE} already exists. "
            "Review or rename the previous export "
            "before generating a replacement."
        )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    result.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8"
    )

    print("\n[PASS] Import-ready CSV created.")
    print("File:", OUTPUT_FILE)

    print(
        "Verified reserves:",
        result["fx_reserves_usd_bn"].ne("").sum()
    )

    print(
        "Verified exchange rates:",
        result["usd_lkr"].ne("").sum()
    )

    if verified.empty:
        print(
            "\n[NOTICE] No observations were marked "
            "Verified. The output contains empty values."
        )

    print(
        "\nSQLite database unchanged. "
        "Run the importer's dry-run before applying."
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError,
            FileExistsError) as error:
        print(f"\n[ERROR] {error}")
        sys.exit(1)
