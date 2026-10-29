"""SL-EWRIS Step 11: transparent monthly economic-stress monitoring.

Descriptive rules only; no trained crisis classifier or crisis probabilities.
Run: python analysis/economic_stress.py
"""
from pathlib import Path
import sqlite3
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'database' / 'economic_risk.db'
OUT = ROOT / 'outputs' / 'economic_stress'
OUT.mkdir(parents=True, exist_ok=True)

REQUIRED = [
    'month', 'headline_yoy_pct', 'food_yoy_pct', 'nonfood_yoy_pct',
    'ccpi_linked_jan2019_100', 'public_real_ncpi_raw',
    'informal_real_ncpi_raw', 'fx_reserves_usd_bn', 'usd_lkr',
]
NUMERIC = [c for c in REQUIRED if c != 'month']


def load_history():
    if not DB.is_file():
        raise FileNotFoundError(f'Database not found: {DB}. Run seed_database.py first.')
    with sqlite3.connect(DB) as con:
        df = pd.read_sql_query('SELECT * FROM economic_monthly ORDER BY month', con)
    if df.empty:
        raise ValueError('economic_monthly has no rows.')
    missing = sorted(set(REQUIRED) - set(df.columns))
    if missing:
        raise ValueError(f'Missing SQLite columns: {missing}')
    if df['month'].isna().any() or not df['month'].astype(str).str.fullmatch(r'\d{4}-(0[1-9]|1[0-2])').all():
        raise ValueError('Expected complete YYYY-MM dates.')
    df['date'] = pd.to_datetime(df['month'] + '-01', format='%Y-%m-%d')
    if df['date'].duplicated().any():
        raise ValueError('Duplicate months present.')
    df = df.sort_values('date').reset_index(drop=True)
    expected = pd.date_range(df.date.iloc[0], df.date.iloc[-1], freq='MS')
    if not pd.DatetimeIndex(df.date).equals(expected):
        raise ValueError('Month gaps found; fill missing months with NULL observations first.')
    for col in NUMERIC:
        df[col] = pd.to_numeric(df[col], errors='raise')
        if not np.isfinite(df[col].dropna().to_numpy(dtype=float)).all():
            raise ValueError(f'Non-finite values in {col}')
    for col in ['ccpi_linked_jan2019_100', 'public_real_ncpi_raw', 'informal_real_ncpi_raw', 'fx_reserves_usd_bn', 'usd_lkr']:
        if (df[col].dropna() <= 0).any():
            raise ValueError(f'Nonpositive index/level in {col}')
    return df


def yoy(series):
    previous = series.shift(12)
    return ((series / previous) - 1) * 100


def inflation_status(value):
    if pd.isna(value):
        return 'Unavailable'
    if value >= 20:
        return 'Very high inflation'
    if value >= 10:
        return 'High inflation'
    if value >= 5:
        return 'Elevated inflation'
    if value < 0:
        return 'Deflation (prices falling YoY)'
    return 'Lower positive inflation'


def trend_status(value):
    if pd.isna(value):
        return 'Unavailable'
    if value > 1:
        return 'Accelerating YoY inflation'
    if value < -1:
        return 'Decelerating YoY inflation'
    return 'Relatively stable YoY inflation'


def real_wage_status(value):
    if pd.isna(value):
        return 'Unavailable'
    if value < 0:
        return 'Real wage-rate decline YoY'
    return 'No real wage-rate decline YoY'


def calculate(df):
    df = df.copy()
    df['headline_3m_avg_pct'] = df['headline_yoy_pct'].rolling(3, min_periods=3).mean()
    df['prior_3m_avg_pct'] = df['headline_3m_avg_pct'].shift(3)
    df['inflation_momentum_pp'] = df['headline_3m_avg_pct'] - df['prior_3m_avg_pct']
    df['public_real_wage_yoy_pct'] = yoy(df['public_real_ncpi_raw'])
    df['informal_real_wage_yoy_pct'] = yoy(df['informal_real_ncpi_raw'])

    # Fixed nominal salary purchasing-power scenario relative to Jan 2019.
    # Historical months before Jan 2019 intentionally left unavailable.
    jan19 = df.loc[df.month == '2019-01', 'ccpi_linked_jan2019_100']
    if len(jan19) != 1 or pd.isna(jan19.iloc[0]) or jan19.iloc[0] <= 0:
        raise ValueError('Missing valid January 2019 researcher-linked CCPI reference')
    price_ratio = df['ccpi_linked_jan2019_100'] / jan19.iloc[0]
    after_jan19 = df.date >= pd.Timestamp('2019-01-01')
    df['fixed_salary_real_value_index'] = np.where(after_jan19, 100 / price_ratio, np.nan)
    df['fixed_salary_pp_change_since_2019_pct'] = df['fixed_salary_real_value_index'] - 100
    df['inflation_level_status'] = df['headline_3m_avg_pct'].apply(inflation_status)
    df['inflation_trend_status'] = df['inflation_momentum_pp'].apply(trend_status)
    df['public_real_wage_status'] = df['public_real_wage_yoy_pct'].apply(real_wage_status)
    df['informal_real_wage_status'] = df['informal_real_wage_yoy_pct'].apply(real_wage_status)
    # No reserves/exchange-rate risk model yet: presence alone cannot establish external risk.
    df['external_vulnerability_status'] = 'Not assessed — requires a validated external-risk model'
    return df


def narrative(row):
    parts = []
    if pd.notna(row['headline_3m_avg_pct']):
        parts.append(f"3-month average headline inflation: {row['headline_3m_avg_pct']:.2f}% ({row['inflation_level_status']}).")
    else:
        parts.append('Insufficient published inflation observations for a 3-month average.')
    if pd.notna(row['inflation_momentum_pp']):
        parts.append(f"Inflation momentum: {row['inflation_momentum_pp']:+.2f} percentage points compared with the previous three months.")
    else:
        parts.append('Inflation momentum unavailable.')
    for sector, label in [('public', 'Public'), ('informal', 'Informal private')]:
        v = row[f'{sector}_real_wage_yoy_pct']
        parts.append(f'{label} annual real wage-rate change (official NCPI-adjusted index): {v:+.2f}%.' if pd.notna(v) else f'{label} annual real wage-rate change unavailable.')
    pp = row['fixed_salary_pp_change_since_2019_pct']
    parts.append(f'Hypothetical fixed-salary purchasing power since Jan 2019: {pp:+.2f}%.' if pd.notna(pp) else 'Fixed-salary Jan 2019 scenario unavailable for this month.')
    parts.append('National crisis probability NOT estimated; reserves, debt, credit and exchange-rate pressures require separate analysis.')
    return ' '.join(parts)


def main():
    df = calculate(load_history())
    df['assessment_explanation'] = df.apply(narrative, axis=1)
    wanted = [
        'month', 'headline_yoy_pct', 'food_yoy_pct', 'nonfood_yoy_pct',
        'headline_3m_avg_pct', 'inflation_momentum_pp', 'inflation_level_status',
        'inflation_trend_status', 'public_real_wage_yoy_pct',
        'public_real_wage_status', 'informal_real_wage_yoy_pct',
        'informal_real_wage_status', 'fixed_salary_real_value_index',
        'fixed_salary_pp_change_since_2019_pct', 'external_vulnerability_status',
        'fx_reserves_usd_bn', 'usd_lkr', 'assessment_explanation',
    ]
    df[wanted].to_csv(OUT / 'monthly_economic_stress.csv', index=False)
    latest = df.iloc[-1]
    df[wanted].tail(1).to_csv(OUT / 'latest_economic_stress.csv', index=False)
    metadata = {
        'latest_month': latest['month'],
        'records': len(df),
        'interpretation': 'Descriptive monitoring only; not a validated financial crisis probability.',
        'inflation_rules': 'Three-month mean YoY headline inflation: <0 deflation, 0–<5 lower, 5–<10 elevated, 10–<20 high, >=20 very high; thresholds illustrative.',
        'momentum_rules': 'Current 3-month average minus previous nonoverlapping 3-month average; >+1 rising, <-1 falling; illustrative.',
        'wage_method': 'Official CBSL NCPI-adjusted real wage-rate index YoY change, where available.',
        'salary_method': 'Fixed nominal salary purchasing power from Jan 2019, using researcher-linked CCPI; 2023 base revision caveat.',
        'limitation': 'Single national crisis 2022 event, incomplete publication dates, external risk model unavailable, historical CPI series researcher-linked.',
    }
    (OUT / 'methodology.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print('\nSL-EWRIS | STEP 11 — ECONOMIC STRESS MONITORING')
    print('Data window:', df.month.iloc[0], 'to', df.month.iloc[-1], '| Months:', len(df))
    print('\nLATEST MONITORING MONTH:', latest['month'])
    print(latest['assessment_explanation'])
    print('\nFiles:')
    for p in sorted(OUT.iterdir()):
        print('  ', p.relative_to(ROOT))
    print('\n[PASS] Descriptive monitoring computed. No crisis probabilities estimated.')


if __name__ == '__main__':
    main()
