"""SL-EWRIS Step 18: release-aware monthly monitoring simulation.

Run from project root:
    python analysis/monthly_point_in_time_simulation.py

Evidence comes ONLY from manually source-checked historical_release_ledger.csv.
No model is trained, and indicators are not crisis probabilities.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "economic_risk.db"
LEDGER = ROOT / "data" / "historical_release_ledger.csv"
OUT = ROOT / "outputs" / "point_in_time_simulation"

INDICATORS = [
    "headline_yoy_pct", "public_real_ncpi_raw", "informal_real_ncpi_raw",
    "fx_reserves_usd_bn", "usd_lkr",
]
LEDGER_COLS = ["month", "indicator", "published_value", "publication_date", "source_url"]
SIGNALS = [
    "high_inflation", "inflation_acceleration", "public_real_wage_decline",
    "informal_real_wage_decline", "reserve_depletion", "currency_depreciation",
]


def load_evidence():
    if not DB.is_file():
        raise FileNotFoundError(f"SQLite database missing: {DB}")
    with sqlite3.connect(f"{DB.resolve().as_uri()}?mode=ro", uri=True) as conn:
        months = {row[0] for row in conn.execute("SELECT month FROM economic_monthly")}
    if not LEDGER.exists():
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=LEDGER_COLS).to_csv(LEDGER, index=False)
        print(f"Created blank source ledger: {LEDGER}")
    evidence = pd.read_csv(LEDGER, dtype="string")
    if not set(LEDGER_COLS).issubset(evidence.columns):
        raise ValueError(f"Ledger must contain columns: {LEDGER_COLS}")
    evidence = evidence[LEDGER_COLS].copy()
    if evidence.empty:
        return evidence.assign(obs_date=pd.Series(dtype="datetime64[ns]"),
                               release_date=pd.Series(dtype="datetime64[ns]"))
    if evidence.isna().any().any() or (evidence.astype(str).apply(lambda c: c.str.strip() == "")).any().any():
        raise ValueError("Ledger has blank cells; complete or remove incomplete rows")
    if not evidence["indicator"].isin(INDICATORS).all():
        raise ValueError("Ledger includes unknown indicators for Step 18")
    if not evidence["month"].str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])").all():
        raise ValueError("Invalid YYYY-MM observation months")
    if not set(evidence["month"]).issubset(months):
        raise ValueError("Ledger includes observation months missing from database")
    evidence["obs_date"] = pd.to_datetime(evidence["month"] + "-01", format="%Y-%m-%d")
    evidence["release_date"] = pd.to_datetime(evidence["publication_date"], format="%Y-%m-%d", errors="raise")
    if (evidence["release_date"] < evidence["obs_date"]).any():
        raise ValueError("Publication cannot precede observation month")
    if not evidence["source_url"].str.startswith("https://").all():
        raise ValueError("Source URLs must use https://")
    evidence["published_value"] = pd.to_numeric(evidence["published_value"], errors="raise")
    if not np.isfinite(evidence["published_value"].to_numpy(dtype=float)).all():
        raise ValueError("Non-finite historical values")
    positive = evidence["indicator"].ne("headline_yoy_pct")
    if (evidence.loc[positive, "published_value"] <= 0).any():
        raise ValueError("Reserve, wage index and exchange rate levels must be positive")
    if evidence.duplicated(["month", "indicator", "publication_date"]).any():
        raise ValueError("Multiple releases for same indicator, month and date; resolve vintages")
    return evidence


def available_vintage(evidence: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Most recently released vintage per indicator-month, as of cutoff."""
    if evidence.empty:
        return evidence.copy()
    eligible = evidence[(evidence["release_date"] <= cutoff) & (evidence["obs_date"] <= cutoff)]
    return (eligible.sort_values(["release_date", "month"])
            .drop_duplicates(["indicator", "month"], keep="last"))


def level_series(vintages, indicator):
    rows = vintages[vintages["indicator"] == indicator]
    if rows.empty:
        return pd.Series(dtype=float)
    return pd.Series(rows["published_value"].astype(float).to_numpy(),
                     index=pd.PeriodIndex(rows["month"], freq="M"), dtype=float).sort_index()


def latest_fresh_period(series, cutoff, max_age_months=3):
    """Select latest observed period if no more than 3 calendar months old."""
    if series.empty:
        return None
    last = series.index.max()