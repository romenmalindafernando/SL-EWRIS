from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "outputs" / "cbsl_extraction"
OUTPUT = ROOT / "outputs" / "cbsl_preparation"
OUTPUT.mkdir(parents=True, exist_ok=True)

RESERVES = INPUT / "reserve_candidates_v2.csv"
FX = INPUT / "usd_lkr_2014_2025_candidates.csv"

DESTINATION = OUTPUT / "combined_external_review_2014_2025.csv"

EXPECTED = pd.period_range("2014-01", "2025-12", freq="M").astype(str)

def validate(df, label, indicator, unit):
    required = {
        "month", "indicator", "candidate_value",
        "unit", "verification_status", "publication_date"
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label}: missing columns {missing}")

    if len(df) != 144:
        raise ValueError(f"{label}: expected 144 rows, got {len(df)}")

    if df["month"].duplicated().any():
        raise ValueError(f"{label}: duplicate months")

    if set(df["month"]) != set(EXPECTED):
        raise ValueError(f"{label}: month coverage mismatch")

    if not df["indicator"].eq(indicator).all():
        raise ValueError(f"{label}: indicator mismatch")

    if not df["unit"].eq(unit).all():
        raise ValueError(f"{label}: unit mismatch")

    if not df["verification_status"].eq("Pending").all():
        raise ValueError(f"{label}: unexpected verification status")

    if df["publication_date"].fillna("").astype(str).str.strip().ne("").any():
        raise ValueError(f"{label}: publication dates need review")

    df["candidate_value"] = pd.to_numeric(
        df["candidate_value"], errors="coerce"
    )

    if not np.isfinite(df["candidate_value"]).all():
        raise ValueError(f"{label}: non-finite values")

    if (df["candidate_value"] <= 0).any():
        raise ValueError(f"{label}: invalid values")

    return df

def main():
    if DESTINATION.exists():
        raise FileExistsError(
            f"Output already exists: {DESTINATION}. "
            "Keep the previous file and choose a new version name."
        )

    reserves = pd.read_csv(RESERVES, dtype=str, keep_default_na=False)
    fx = pd.read_csv(FX, dtype=str, keep_default_na=False)

    reserves = validate(
        reserves, "Reserves", "fx_reserves_usd_bn", "USD billions"
    )
    fx = validate(
        fx, "Exchange rate", "usd_lkr", "LKR per USD"
    )

    reserves = reserves.rename(columns={
        "candidate_value": "fx_reserves_usd_bn",
        "source_sheet": "reserves_source_sheet",
        "source_cell": "reserves_source_cell",
        "observation_as_of_date": "reserves_as_of_date",
        "official_source_url": "reserves_source_url"
    })

    fx = fx.rename(columns={
        "candidate_value": "usd_lkr",
        "source_sheet": "usd_lkr_source_sheet",
        "source_row": "usd_lkr_source_row",
        "official_source_url": "usd_lkr_source_url"
    })

    reserve_cols = [
        "month", "fx_reserves_usd_bn", "reserves_as_of_date",
        "reserves_source_sheet", "reserves_source_cell",
        "reserves_source_url"
    ]

    fx_cols = [
        "month", "usd_lkr", "usd_lkr_source_sheet",
        "usd_lkr_source_row", "usd_lkr_source_url"
    ]

    combined = reserves[reserve_cols].merge(
        fx[fx_cols], on="month", how="outer",
        validate="one_to_one", indicator=True
    )

    if not combined["_merge"].eq("both").all():
        raise ValueError("Unmatched months between datasets")

    combined = combined.drop(columns="_merge")
    combined = combined.sort_values("month").reset_index(drop=True)

    combined["usd_lkr_change_pct"] = (
        combined["usd_lkr"].pct_change(fill_method=None) * 100
    )

    combined["reserves_monthly_change_pct"] = (
        combined["fx_reserves_usd_bn"].pct_change(fill_method=None) * 100
    )

    combined["reserves_yoy_change_pct"] = (
        combined["fx_reserves_usd_bn"]
        .pct_change(periods=12, fill_method=None) * 100
    )

    # A retrospective workbook does not establish when each
    # historical observation first became publicly available.
    combined["fx_reserves_published_on"] = ""
    combined["usd_lkr_published_on"] = ""
    combined["verification_status"] = "Pending"

    combined.to_csv(
        DESTINATION, index=False, encoding="utf-8-sig"
    )

    print("\n=== SL-EWRIS EXTERNAL DATA MERGE ===")
    print("Combined months:", len(combined))
    print("First month:", combined.iloc[0]["month"])
    print("Last month:", combined.iloc[-1]["month"])
    print("Reserve observations:", combined["fx_reserves_usd_bn"].notna().sum())
    print("Exchange-rate observations:", combined["usd_lkr"].notna().sum())

    print("\n=== SELECTED HISTORICAL MONTHS ===")
    selected = combined[
        combined["month"].isin([
            "2014-01", "2019-01", "2021-12",
            "2022-04", "2025-12"
        ])
    ]

    print(selected[[
        "month", "fx_reserves_usd_bn", "usd_lkr",
        "reserves_yoy_change_pct"
    ]].to_string(index=False))

    print("\nSaved:", DESTINATION)
    print("All observations remain Pending.")
    print("SQLite database unchanged.")

if __name__ == "__main__":
    main()
