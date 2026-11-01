from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT / "outputs/cbsl_preparation"
    / "combined_external_review_2014_2025.csv"
)

OUT = ROOT / "outputs/external_risk_analysis"
OUT.mkdir(parents=True, exist_ok=True)

DEST = OUT / "external_risk_indicators_2014_2025.csv"
SUMMARY = OUT / "historical_risk_screening.csv"

if DEST.exists() or SUMMARY.exists():
    raise FileExistsError(
        "Output files already exist. Archive the old "
        "outputs before rerunning."
    )

df = pd.read_csv(SOURCE)

df["month"] = df["month"].astype(str)

df = df.sort_values("month").reset_index(drop=True)

expected = pd.period_range(
    "2014-01", "2025-12", freq="M"
).astype(str)

if (
    len(df) != 144
    or df["month"].duplicated().any()
    or df["month"].tolist() != list(expected)
):
    raise ValueError("Invalid monthly coverage")

if not df["verification_status"].eq("Pending").all():
    raise ValueError("Unexpected verification status")

for col in ["fx_reserves_usd_bn", "usd_lkr"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

    if not np.isfinite(df[col]).all():
        raise ValueError(f"Non-finite values: {col}")

    if (df[col] <= 0).any():
        raise ValueError(f"Non-positive values: {col}")

df["fx_change_1m_pct"] = (
    df["usd_lkr"].pct_change(fill_method=None) * 100
)

df["fx_change_3m_pct"] = (
    df["usd_lkr"].pct_change(
        periods=3, fill_method=None
    ) * 100
)

df["reserves_change_3m_pct"] = (
    df["fx_reserves_usd_bn"].pct_change(
        periods=3, fill_method=None
    ) * 100
)

df["reserves_change_12m_pct"] = (
    df["fx_reserves_usd_bn"].pct_change(
        periods=12, fill_method=None
    ) * 100
)

# Illustrative screening thresholds.
# These are NOT validated crisis-risk cutoffs.

df["currency_pressure_flag"] = (
    df["fx_change_3m_pct"] >= 10
)

df["reserve_pressure_flag"] = (
    df["reserves_change_3m_pct"] <= -20
)

df["long_term_reserve_flag"] = (
    df["reserves_change_12m_pct"] <= -30
)

df["screening_flags_count"] = (
    df[
        [
            "currency_pressure_flag",
            "reserve_pressure_flag",
            "long_term_reserve_flag"
        ]
    ].sum(axis=1)
)

# Never label the first 12 months as fully
# assessed: 12-month change is unavailable.
df["screening_status"] = np.where(
    df["reserves_change_12m_pct"].isna(),
    "Insufficient history",
    np.where(
        df["screening_flags_count"] >= 2,
        "Multiple stress signals",
        np.where(
            df["screening_flags_count"] == 1,
            "One stress signal",
            "No threshold exceeded"
        )
    )
)

df["analysis_type"] = "Retrospective screening"
df["publication_date_verified"] = False

df.to_csv(
    DEST, index=False, encoding="utf-8-sig"
)

selected = df[
    (df["month"] >= "2020-01")
    & (df["month"] <= "2022-12")
][
    [
        "month",
        "fx_reserves_usd_bn",
        "usd_lkr",
        "fx_change_3m_pct",
        "reserves_change_3m_pct",
        "reserves_change_12m_pct",
        "screening_status"
    ]
]

selected.to_csv(
    SUMMARY, index=False, encoding="utf-8-sig"
)

print("\n=== SL-EWRIS EXTERNAL RISK ANALYSIS ===")
print("Months analyzed:", len(df))

print("\n=== STRESS SCREENING COUNTS ===")
print(df["screening_status"].value_counts())

print("\n=== 2021-2022 CRISIS PERIOD ===")
print(
    df[
        (df["month"] >= "2021-07")
        & (df["month"] <= "2022-06")
    ][
        [
            "month",
            "fx_change_3m_pct",
            "reserves_change_12m_pct",
            "screening_status"
        ]
    ].round(2).to_string(index=False)
)

print("\nSaved:", DEST)
print("Saved:", SUMMARY)

print("\nIMPORTANT:")
print("Retrospective screening only.")
print("Thresholds are illustrative and unvalidated.")
print("No crisis predictions have been generated.")
print("PostgreSQL database unchanged.")
