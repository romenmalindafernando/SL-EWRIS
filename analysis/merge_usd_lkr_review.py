
# ============================================================
# SL-EWRIS — STEP 23
# MERGE EXTRACTED USD/LKR CANDIDATES INTO REVIEW WORKSHEET
#
# Does not overwrite original review or SQLite data.
# Does not automatically mark observations Verified.
# ============================================================

from pathlib import Path
import math
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

CANDIDATES = (
    ROOT / "outputs" / "cbsl_extraction"
    / "usd_lkr_2014_2025_candidates.csv"
)

REVIEW = (
    ROOT / "outputs" / "cbsl_preparation"
    / "source_review_2014_2025.csv"
)

OUTPUT = (
    ROOT / "outputs" / "cbsl_preparation"
    / "source_review_with_usd_lkr.csv"
)

EXPECTED_MONTHS = pd.period_range(
    "2014-01", "2025-12", freq="M"
).astype(str).tolist()


def load_files():

    if not CANDIDATES.is_file():
        raise FileNotFoundError(
            "USD/LKR candidate file missing. "
            "Run extract_actual_usd_lkr.py first."
        )

    if not REVIEW.is_file():
        raise FileNotFoundError(
            "Source review worksheet missing. "
            "Run Step 20 first."
        )

    candidates = pd.read_csv(
        CANDIDATES,
        dtype=str,
        keep_default_na=False
    )

    review = pd.read_csv(
        REVIEW,
        dtype=str,
        keep_default_na=False
    )

    required_candidate_columns = {
        "month",
        "indicator",
        "candidate_value",
        "unit",
        "source_filename",
        "source_sheet",
        "source_column",
        "verification_status"
    }

    required_review_columns = {
        "month",
        "indicator",
        "verified_value",
        "unit",
        "required_definition",
        "source_filename",
        "source_sheet",
        "source_column",
        "publication_date",
        "official_source_url",
        "verification_status"
    }

    if not required_candidate_columns.issubset(
        candidates.columns
    ):
        raise ValueError(
            "Candidate CSV has missing columns."
        )

    if not required_review_columns.issubset(
        review.columns
    ):
        raise ValueError(
            "Review worksheet has missing columns."
        )

    return candidates, review


def validate_candidates(candidates):

    if len(candidates) != 144:
        raise ValueError(
            "Expected exactly 144 monthly exchange "
            f"rates; found {len(candidates)}."
        )

    if candidates["month"].duplicated().any():
        raise ValueError(
            "Duplicate months in candidate file."
        )

    if set(candidates["month"]) != set(EXPECTED_MONTHS):
        raise ValueError(
            "Exchange-rate month coverage is incomplete."
        )

    if not candidates["indicator"].eq("usd_lkr").all():
        raise ValueError(
            "Candidate file contains another indicator."
        )

    if not candidates["unit"].eq("LKR per USD").all():
        raise ValueError(
            "Unexpected exchange-rate unit."
        )

    if not candidates[
        "verification_status"
    ].eq("Pending").all():
        raise ValueError(
            "Candidate verification statuses changed."
        )

    for row in candidates.itertuples(index=False):

        value = float(
            str(row.candidate_value).replace(",", "")
        )

        if not math.isfinite(value) or value <= 0:
            raise ValueError(
                f"Invalid USD/LKR value for {row.month}"
            )


def merge_review(candidates, review):

    output = review.copy()

    if output.duplicated(
        ["month", "indicator"]
    ).any():
        raise ValueError(
            "Duplicate month/indicator rows "
            "in review worksheet."
        )

    candidate_lookup = (
        candidates.set_index("month").to_dict("index")
    )

    updated = 0
    preserved = 0

    for index, row in output.iterrows():

        if row["indicator"] != "usd_lkr":
            continue

        month = row["month"]

        if month not in candidate_lookup:
            raise ValueError(
                f"Missing candidate for {month}"
            )

        candidate = candidate_lookup[month]

        new_value = str(
            candidate["candidate_value"]
        ).strip()

        old_value = str(
            row["verified_value"]
        ).strip()

        # Never overwrite an observation that someone
        # has already entered into the review sheet.
        if old_value:

            if not math.isclose(
                float(old_value),
                float(new_value),
                rel_tol=1e-9,
                abs_tol=1e-9
            ):
                raise ValueError(
                    f"Conflict for {month}: "
                    f"review={old_value}, "
                    f"candidate={new_value}"
                )

            preserved += 1
            continue

        # Transfer candidate without verifying it.
        output.at[index, "verified_value"] = new_value
        output.at[index, "source_filename"] = (
            candidate["source_filename"]
        )
        output.at[index, "source_sheet"] = (
            candidate["source_sheet"]
        )
        output.at[index, "source_column"] = (
            candidate["source_column"]
        )
        output.at[index, "verification_status"] = (
            "Pending"
        )

        # Publication date and official source URL
        # stay empty until independently documented.
        updated += 1

    return output, updated, preserved


def main():

    print("=" * 60)
    print("SL-EWRIS | STEP 23")
    print("MERGE CBSL USD/LKR CANDIDATES")
    print("=" * 60)

    candidates, review = load_files()

    validate_candidates(candidates)

    merged, updated, preserved = merge_review(
        candidates, review
    )

    if OUTPUT.exists():
        raise FileExistsError(
            f"Previous output exists: {OUTPUT}. "
            "Rename or archive it before rerunning."
        )

    merged.to_csv(
        OUTPUT,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n[PASS] Review merge completed.")
    print("New candidate values transferred:", updated)
    print("Existing review values preserved:", preserved)
    print("Output:", OUTPUT)

    print(
        "\nAll new values are still Pending "
        "source verification."
    )

    print("Original review file unchanged.")
    print("SQLite database unchanged.")


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
