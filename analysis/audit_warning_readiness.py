from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT / "outputs/cbsl_preparation"
    / "combined_external_review_2014_2025.csv"
)

OUTPUT = (
    ROOT / "outputs/external_risk_analysis"
    / "point_in_time_readiness_audit.csv"
)

if not SOURCE.exists():
    raise FileNotFoundError(SOURCE)

df = pd.read_csv(
    SOURCE,
    dtype=str,
    keep_default_na=False
)

required = [
    "month",
    "fx_reserves_usd_bn",
    "usd_lkr",
    "reserves_as_of_date",
    "fx_reserves_published_on",
    "usd_lkr_published_on",
    "reserves_source_url",
    "usd_lkr_source_url"
]

missing = [c for c in required if c not in df.columns]
if missing:
    raise ValueError(f"Missing columns: {missing}")

if len(df) != 144 or df["month"].duplicated().any():
    raise ValueError("Expected 144 unique monthly records")

audit = df[required].copy()

audit["reserves_publication_known"] = (
    audit["fx_reserves_published_on"].str.strip().ne("")
)

audit["fx_publication_known"] = (
    audit["usd_lkr_published_on"].str.strip().ne("")
)

audit["both_release_dates_known"] = (
    audit["reserves_publication_known"]
    & audit["fx_publication_known"]
)

audit["reserves_source_url_present"] = (
    audit["reserves_source_url"].str.strip().ne("")
)

audit["fx_source_url_present"] = (
    audit["usd_lkr_source_url"].str.strip().ne("")
)

audit["point_in_time_status"] = audit[
    "both_release_dates_known"
].map({
    True: "Dates present; verification still needed",
    False: "Not ready: release dates missing"
})

if OUTPUT.exists():
    raise FileExistsError(
        f"Audit already exists: {OUTPUT}"
    )

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

audit.to_csv(
    OUTPUT,
    index=False,
    encoding="utf-8-sig"
)

print("\n=== SL-EWRIS POINT-IN-TIME READINESS ===")
print("Months audited:", len(audit))
print(
    "Reserve publication dates present:",
    audit["reserves_publication_known"].sum()
)
print(
    "USD/LKR publication dates present:",
    audit["fx_publication_known"].sum()
)
print(
    "Months with both dates present:",
    audit["both_release_dates_known"].sum()
)
print(
    "Reserve source URLs present:",
    audit["reserves_source_url_present"].sum()
)
print(
    "USD/LKR source URLs present:",
    audit["fx_source_url_present"].sum()
)

print("\nSaved:", OUTPUT)
print("No database changes made.")
print("Missing dates have not been invented.")
