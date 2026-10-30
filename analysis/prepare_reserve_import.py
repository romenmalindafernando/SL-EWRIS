
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT / "outputs/cbsl_extraction"
    / "reserve_candidates_v2.csv"
)

OUTPUT = (
    ROOT / "outputs/cbsl_extraction"
    / "reserves_import_staging.csv"
)

EXPECTED = list(
    pd.period_range(
        "2014-01", "2025-12", freq="M"
    ).astype(str)
)

def main():
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)

    if OUTPUT.exists():
        raise FileExistsError(
            f"Staging file already exists: {OUTPUT}"
        )

    df = pd.read_csv(
        SOURCE,
        dtype={"month": str}
    )

    required = [
        "month",
        "candidate_value",
        "verification_status",
        "official_source_url",
        "publication_date"
    ]

    missing_columns = [
        col for col in required
        if col not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing columns: {missing_columns}"
        )

    if len(df) != 144:
        raise ValueError(
            f"Expected 144 rows, found {len(df)}"
        )

    if df["month"].duplicated().any():
        raise ValueError("Duplicate months detected")

    if set(df["month"]) != set(EXPECTED):
        raise ValueError(
            "Incomplete or unexpected monthly coverage"
        )

    values = pd.to_numeric(
        df["candidate_value"],
        errors="coerce"
    )

    if values.isna().any() or (values <= 0).any():
        raise ValueError(
            "Missing or invalid reserve values"
        )

    if not (
        df["verification_status"]
        .fillna("")
        .eq("Pending")
        .all()
    ):
        raise ValueError(
            "Unexpected verification statuses"
        )

    # Publication dates must come from verified
    # release records, not observation dates.
    published = df["publication_date"].fillna("")
    if published.astype(str).str.strip().ne("").any():
        raise ValueError(
            "Unexpected publication dates: review first"
        )

    staging = pd.DataFrame({
        "month": df["month"],
        "fx_reserves_usd_bn": values,
        "fx_reserves_published_on": "",
        "fx_reserves_source_url":
            df["official_source_url"].fillna(""),
        "usd_lkr": "",
        "usd_lkr_published_on": "",
        "usd_lkr_source_url": ""
    })

    staging = staging.sort_values("month")
    staging.to_csv(
        OUTPUT,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n=== RESERVE DATA VALIDATION ===")
    print("Rows:", len(staging))
    print("First month:", staging.iloc[0]["month"])
    print("Last month:", staging.iloc[-1]["month"])
    print("Duplicate months: 0")
    print("Invalid reserve values: 0")

    print("\n=== SAMPLE OBSERVATIONS ===")
    sample = staging[
        staging["month"].isin([
            "2014-01",
            "2019-01",
            "2021-12",
            "2022-04",
            "2025-12"
        ])
    ]
    print(
        sample[
            ["month", "fx_reserves_usd_bn"]
        ].to_string(index=False)
    )

    print("\nSaved:", OUTPUT)
    print("Status: STAGING ONLY")
    print("No database changes made.")
    print(
        "Historical publication dates remain unknown."
    )

if __name__ == "__main__":
    main()
