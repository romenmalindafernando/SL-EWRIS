from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT / "outputs/external_risk_analysis"
    / "external_risk_indicators_2014_2025.csv"
)

OUT = ROOT / "outputs/external_risk_analysis"
REPORT = OUT / "pre_crisis_warning_report.csv"
SUMMARY = OUT / "pre_crisis_warning_summary.txt"

if not SOURCE.exists():
    raise FileNotFoundError(
        "Step 30 output missing. Run external_risk_screening.py first."
    )

if REPORT.exists() or SUMMARY.exists():
    raise FileExistsError(
        "Step 31 outputs already exist. Review or archive them before rerunning."
    )

df = pd.read_csv(SOURCE)

df["month"] = df["month"].astype(str)
df = df.sort_values("month").reset_index(drop=True)

required = [
    "month",
    "usd_lkr",
    "fx_reserves_usd_bn",
    "fx_change_3m_pct",
    "reserves_change_3m_pct",
    "reserves_change_12m_pct",
    "screening_status"
]

missing = [c for c in required if c not in df.columns]

if missing:
    raise ValueError(f"Missing columns: {missing}")

period = df[
    (df["month"] >= "2020-01")
    & (df["month"] <= "2022-12")
].copy()

# These are illustrative retrospective flags,
# not validated financial crisis probabilities.
period["reserve_depletion_signal"] = (
    period["reserves_change_12m_pct"] <= -30
)

period["rapid_reserve_loss_signal"] = (
    period["reserves_change_3m_pct"] <= -20
)

period["currency_depreciation_signal"] = (
    period["fx_change_3m_pct"] >= 10
)

signal_columns = [
    "reserve_depletion_signal",
    "rapid_reserve_loss_signal",
    "currency_depreciation_signal"
]

period["number_of_signals"] = (
    period[signal_columns].sum(axis=1)
)

period["multiple_signals"] = (
    period["number_of_signals"] >= 2
)

# Retain actual observations and calculated indicators.
# No invented publication dates.
report_columns = [
    "month",
    "fx_reserves_usd_bn",
    "usd_lkr",
    "reserves_change_3m_pct",
    "reserves_change_12m_pct",
    "fx_change_3m_pct",
    *signal_columns,
    "number_of_signals",
    "multiple_signals"
]

period[report_columns].to_csv(
    REPORT,
    index=False,
    encoding="utf-8-sig"
)

before_2022 = period[
    period["month"] < "2022-01"
]

early = before_2022[
    before_2022["multiple_signals"]
]

single = before_2022[
    before_2022["number_of_signals"] >= 1
]

first_multiple = (
    early.iloc[0]["month"]
    if len(early) else "None detected"
)

first_any = (
    single.iloc[0]["month"]
    if len(single) else "None detected"
)

lines = [
    "SL-EWRIS RETROSPECTIVE EARLY-WARNING ANALYSIS",
    "=" * 55,
    "Analysis window: January 2020 - December 2022",
    "Historical comparison cutoff: January 2022",
    "",
    f"Months analyzed: {len(period)}",
    f"Pre-2022 months with any signal: {len(single)}",
    f"Pre-2022 months with multiple signals: {len(early)}",
    f"First pre-2022 month with any signal: {first_any}",
    f"First pre-2022 month with multiple signals: {first_multiple}",
    "",
    "Interpretation:",
    "These flags describe historical economic stress.",
    "Thresholds are illustrative, not statistically calibrated.",
    "Official historical release dates have not been verified.",
    "A retrospective flag is not proof of advance prediction.",
    "Gross reserves are not necessarily fully usable reserves.",
    "No model sensitivity, specificity or predictive probability",
    "has been validated.",
]

SUMMARY.write_text(
    "\n".join(lines),
    encoding="utf-8"
)

print("\n" + "\n".join(lines))

print("\n=== 2021 WARNING SIGNALS ===")

print(
    period[
        (period["month"] >= "2021-01")
        & (period["month"] <= "2021-12")
    ][
        [
            "month",
            "reserves_change_12m_pct",
            "fx_change_3m_pct",
            "number_of_signals"
        ]
    ].round(2).to_string(index=False)
)

print("\n[PASS] Historical screening report generated.")
print("CSV:", REPORT)
print("Summary:", SUMMARY)
print("SQLite database unchanged.")

