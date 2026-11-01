"""SL-EWRIS Step 10: one-month-ahead headline inflation forecasting.

Inputs: Neon PostgreSQL table economic_monthly, field headline_yoy_pct.
Outputs: outputs/machine_learning/*.csv and *.png.

Methodology:
- Target: official-source headline year-on-year CCPI inflation, in percentage points.
- Predict month t using only observed inflation values through t-1.
- Expanding-window one-step-ahead evaluation: validate in 2024, test in 2025.
- Choose model solely on 2024 RMSE; never tune on 2025.
- 2025 remains an evaluation set, not an untouched first-ever holdout because
  the wider R capstone has previously inspected that period.
- A simple last-month and same-month-last-year baseline are included.
- This does not estimate the probability of a national financial crisis.
"""

from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from database import connect_database

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error

try:
    from xgboost import XGBRegressor
    HAVE_XGBOOST = True
except ImportError:
    HAVE_XGBOOST = False

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "machine_learning"
OUT.mkdir(parents=True, exist_ok=True)

NAVY = "#142B49"
AMBER = "#E5A23A"
TEAL = "#0D9488"
VIOLET = "#7C70D6"
CORAL = "#E26B69"
FEATURES = ["lag_1", "lag_2", "lag_3", "lag_6", "lag_12", "mean_prev_3", "mean_prev_6"]


def load_data() -> pd.DataFrame:
    with connect_database() as con:
        df = pd.read_sql_query(
            "SELECT month, headline_yoy_pct FROM economic_monthly ORDER BY month", con
        )
    if df.empty or df["month"].duplicated().any():
        raise ValueError("Database empty or duplicate months found.")
    if not df["month"].astype(str).str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])").all():
        raise ValueError("Month must use YYYY-MM format.")
    df["date"] = pd.to_datetime(df["month"], format="%Y-%m")
    expected = pd.date_range(df["date"].min(), df["date"].max(), freq="MS")
    if not pd.DatetimeIndex(df["date"]).equals(expected):
        raise ValueError("Months must be consecutive. Check database gaps.")
    df["headline_yoy_pct"] = pd.to_numeric(df["headline_yoy_pct"], errors="raise")
    if not np.isfinite(df["headline_yoy_pct"].dropna()).all():
        raise ValueError("Non-finite inflation found.")
    if df["date"].min() > pd.Timestamp("2014-01-01") or df["date"].max() < pd.Timestamp("2025-12-01"):
        raise ValueError("Historical coverage must include 2014-01 through 2025-12.")
    # Expected 2014 headline YoY values are missing, because 2013 data were not supplied.
    if df.loc[df["date"].between("2014-01-01", "2014-12-01"), "headline_yoy_pct"].notna().any():
        print("Note: 2014 headline YoY observations exist; verify their provenance.")
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Strict lagged predictors: no t-month contemporaneous data as features."""
    x = df[["month", "date", "headline_yoy_pct"]].copy()
    y = x["headline_yoy_pct"]
    for lag in [1, 2, 3, 6, 12]:
        x[f"lag_{lag}"] = y.shift(lag)
    x["mean_prev_3"] = y.shift(1).rolling(3, min_periods=3).mean()
    x["mean_prev_6"] = y.shift(1).rolling(6, min_periods=6).mean()
    return x


def make_model(name: str):
    if name == "Ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=10.0))
    if name == "Random Forest":
        return RandomForestRegressor(
            n_estimators=200, max_depth=4, min_samples_leaf=3,
            random_state=42, n_jobs=-1
        )
    if name == "XGBoost" and HAVE_XGBOOST:
        return XGBRegressor(
            objective="reg:squarederror", n_estimators=140, max_depth=2,
            learning_rate=0.05, subsample=1.0, colsample_bytree=1.0,
            reg_lambda=5, random_state=42, n_jobs=2
        )
    raise ValueError(f"Unknown or unavailable model: {name}")


def evaluate_window(x: pd.DataFrame, start: str, end: str, model_names: list[str]) -> pd.DataFrame:
    """Expanding origin. Prediction for t uses actual data known through t-1."""
    candidates = x.loc[x["month"].between(start, end)].copy()
    rows: list[dict] = []
    for _, item in candidates.iterrows():
        if pd.isna(item["headline_yoy_pct"]):
            continue
        if item[FEATURES].isna().any():
            continue
        train = x.loc[(x["date"] < item["date"])].dropna(subset=FEATURES + ["headline_yoy_pct"])
        if len(train) < 36:
            raise ValueError(f"Insufficient training history at {item['month']}: {len(train)}")
        xtrain = train[FEATURES]
        ytrain = train["headline_yoy_pct"]
        xtest = item[FEATURES].to_frame().T.astype(float)
        actual = float(item["headline_yoy_pct"])
        row_base = {"month": item["month"], "actual": actual, "train_n": len(train)}
        rows.append({**row_base, "model": "Naive last month", "prediction": float(item["lag_1"])})
        rows.append({**row_base, "model": "Seasonal naive 12m", "prediction": float(item["lag_12"])})
        for name in model_names:
            model = make_model(name)
            model.fit(xtrain, ytrain)
            prediction = float(model.predict(xtest)[0])
            rows.append({**row_base, "model": name, "prediction": prediction})
    return pd.DataFrame(rows)


def accuracy_table(pred: pd.DataFrame) -> pd.DataFrame:
    result = []
    for model, group in pred.groupby("model", sort=True):
        actual = group["actual"].to_numpy()
        forecast = group["prediction"].to_numpy()
        result.append({
            "model": model,
            "observations": len(group),
            "MAE_pp": mean_absolute_error(actual, forecast),
            "RMSE_pp": float(np.sqrt(mean_squared_error(actual, forecast))),
            "Bias_pp": float(np.mean(forecast - actual)),
        })
    return pd.DataFrame(result).sort_values(["RMSE_pp", "MAE_pp", "model"]).reset_index(drop=True)


def save_plot(test: pd.DataFrame, chosen: str) -> None:
    actual = test[test["model"] == chosen].sort_values("month")
    baseline = test[test["model"] == "Naive last month"].sort_values("month")
    dates = pd.to_datetime(actual["month"], format="%Y-%m")
    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.plot(dates, actual["actual"], color=NAVY, lw=2.6, marker="o", label="Observed inflation")
    ax.plot(dates, actual["prediction"], color=TEAL, lw=2.0, marker="s", label=f"{chosen} forecast")
    ax.plot(dates, baseline["prediction"], color=AMBER, lw=1.6, ls="--", label="Last-month baseline")
    ax.axhline(0, color="gray", lw=0.8)
    ax.set(title="One-month-ahead headline inflation forecasts — 2025", ylabel="YoY inflation (%)", xlabel="")
    ax.legend(frameon=False)
    ax.grid(alpha=0.18)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(OUT / "01_2025_inflation_ml_backtest.png", dpi=250)
    plt.close(fig)


def forecast_next_month(x: pd.DataFrame, chosen: str) -> dict | None:
    """Only one-step-ahead, only when latest actual inflation is available."""
    if x.empty or pd.isna(x.iloc[-1]["headline_yoy_pct"]):
        return None
    last_month = pd.Period(str(x.iloc[-1]["month"]), freq="M")
    # Existing feature frame for next month, using only observed previous months.
    y = x["headline_yoy_pct"]
    if len(y) < 13 or y.tail(12).isna().any():
        return None
    next_features = {
        "lag_1": float(y.iloc[-1]),
        "lag_2": float(y.iloc[-2]),
        "lag_3": float(y.iloc[-3]),
        "lag_6": float(y.iloc[-6]),
        "lag_12": float(y.iloc[-12]),
        "mean_prev_3": float(y.tail(3).mean()),
        "mean_prev_6": float(y.tail(6).mean()),
    }
    if chosen == "Naive last month":
        prediction = next_features["lag_1"]
    elif chosen == "Seasonal naive 12m":
        prediction = next_features["lag_12"]
    else:
        train = x.dropna(subset=FEATURES + ["headline_yoy_pct"])
        model = make_model(chosen)
        model.fit(train[FEATURES], train["headline_yoy_pct"])
        prediction = float(model.predict(pd.DataFrame([next_features], columns=FEATURES))[0])
    return {
        "forecast_month": str(last_month + 1),
        "latest_observation_month": str(last_month),
        "selected_model": chosen,
        "forecast_headline_yoy_pct": prediction,
        "forecast_horizon": "one month ahead",
        "warning": "Forecast is exploratory, not a financial-crisis probability."
    }


def main() -> None:
    print("\n" + "=" * 65)
    print("SL-EWRIS | STEP 10: INFLATION ML BACKTEST")
    print("=" * 65)
    raw = load_data()
    x = build_features(raw)
    models = ["Ridge", "Random Forest"]
    if HAVE_XGBOOST:
        models.append("XGBoost")
    else:
        print("Optional XGBoost not installed; skipping it.")
    print(f"Historical months: {len(raw)} ({raw.month.iloc[0]} to {raw.month.iloc[-1]})")
    print(f"Evaluated models: {', '.join(models)} plus two naive baselines")

    validation = evaluate_window(x, "2024-01", "2024-12", models)
    if validation.empty or validation["month"].nunique() != 12:
        raise ValueError("2024 validation must have 12 months of actuals and lagged features.")
    val_scores = accuracy_table(validation)
    selected = str(val_scores.iloc[0]["model"])
    print("\n2024 VALIDATION RESULTS (percentage points):")
    print(val_scores.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"\nSelected model from 2024 validation only: {selected}")

    # Run 2025 evaluation after selection, using a one-month rolling origin.
    test = evaluate_window(x, "2025-01", "2025-12", models)
    if test.empty or test["month"].nunique() != 12:
        raise ValueError("2025 test must have 12 months of actuals and lagged features.")
    test_scores = accuracy_table(test)
    selected_result = test_scores.loc[test_scores["model"] == selected].iloc[0]
    print("\n2025 TEST RESULTS (percentage points):")
    print(test_scores.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"\nSelected model {selected} | Test RMSE {selected_result['RMSE_pp']:.3f} pp | Test MAE {selected_result['MAE_pp']:.3f} pp")

    validation.to_csv(OUT / "2024_validation_predictions.csv", index=False)
    val_scores.to_csv(OUT / "2024_validation_accuracy.csv", index=False)
    test.to_csv(OUT / "2025_test_predictions.csv", index=False)
    test_scores.to_csv(OUT / "2025_test_accuracy.csv", index=False)
    pd.DataFrame([{"selected_model": selected, "selection_period": "2024", "selection_metric": "RMSE_pp"}]).to_csv(OUT / "selected_model.csv", index=False)
    save_plot(test, selected)

    next_forecast = forecast_next_month(x, selected)
    if next_forecast is not None:
        pd.DataFrame([next_forecast]).to_csv(OUT / "next_month_forecast.csv", index=False)
        print(f"\nExploratory {next_forecast['forecast_month']} forecast: {next_forecast['forecast_headline_yoy_pct']:.2f}%")
    else:
        print("\nNext-month forecast unavailable: latest 12 observed inflation values are incomplete.")
    print(f"\n[PASS] Results saved to {OUT}")
    print("IMPORTANT: No future-data leakage in features. This is not a crisis prediction.")
    print("2025 was already examined in the wider R project, so this is not a fully untouched test.")


if __name__ == "__main__":
    main()
