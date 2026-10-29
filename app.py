"""SL-EWRIS Step 9: Streamlit economic monitoring dashboard.

Run from Python_Economic_Risk project root:
    python -m streamlit run app.py

Shows observations and descriptive monitoring signals, not crisis probabilities.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import math
import re
import sqlite3

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "database" / "economic_risk.db"
NAVY, AMBER, TEAL, VIOLET, CORAL = "#142B49", "#E5A23A", "#0D9488", "#7C70D6", "#E26B69"

# Aligned to Step 8's whitelist. A value describes a single indicator,
# not a complete macroeconomic risk assessment.
ENTRY_FIELDS = {
    "Headline inflation YoY (%)": ("headline_yoy_pct", False),
    "Food inflation YoY (%)": ("food_yoy_pct", False),
    "Non-food inflation YoY (%)": ("nonfood_yoy_pct", False),
    "Headline CCPI (published base)": ("ccpi_headline_original", True),
    "Food CCPI (published base)": ("ccpi_food_original", True),
    "Non-food CCPI (published base)": ("ccpi_nonfood_original", True),
    "Public nominal wage index (published base)": ("public_nominal_original", True),
    "Informal nominal wage index (published base)": ("informal_nominal_original", True),
    "Public real wage index, NCPI-based": ("public_real_ncpi_raw", True),
    "Informal real wage index, NCPI-based": ("informal_real_ncpi_raw", True),
    "Foreign reserves (USD billions)": ("fx_reserves_usd_bn", True),
    "USD/LKR exchange rate": ("usd_lkr", True),
    "Published average monthly salary (LKR)": ("average_monthly_salary_lkr", True),
}

st.set_page_config(page_title="SL-EWRIS | Economic Monitor", page_icon="📊", layout="wide")
st.markdown("""<style>
.block-container {padding-top:1.6rem; max-width:1350px;}
h1,h2,h3 {color:#142B49;}
div[data-testid="stMetric"] {border:1px solid #e6ebf1; padding:12px 16px; border-radius:10px;}
</style>""", unsafe_allow_html=True)


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def load_data():
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"Database not found: {DB_PATH}. Run seed_database.py first.")
    with connect() as conn:
        data = pd.read_sql_query("SELECT * FROM economic_monthly ORDER BY month", conn)
    if data.empty:
        raise ValueError("The database contains no monthly observations.")
    needed = {
        "month", "headline_yoy_pct", "food_yoy_pct", "nonfood_yoy_pct",
        "ccpi_linked_jan2019_100", "public_nominal_jan2019_100",
        "informal_nominal_jan2019_100", "public_real_ncpi_raw",
        "informal_real_ncpi_raw", "fx_reserves_usd_bn", "usd_lkr",
    }
    missing = needed - set(data.columns)
    if missing:
        raise ValueError(f"Database has missing columns: {', '.join(sorted(missing))}")
    if data["month"].duplicated().any() or not data["month"].astype(str).str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])").all():
        raise ValueError("Duplicate or malformed month field in database.")
    data["date"] = pd.to_datetime(data["month"] + "-01", format="%Y-%m-%d")
    for c in needed - {"month"}:
        data[c] = pd.to_numeric(data[c], errors="coerce")
    return data.sort_values("date").reset_index(drop=True)


def nonmissing_latest(frame, column):
    rows = frame.loc[frame[column].notna(), ["month", column]]
    if rows.empty:
        return None, None
    row = rows.iloc[-1]
    return row["month"], float(row[column])


def series_chart(frame, choices, ylabel, reference=None):
    fig = go.Figure()
    for col, name, color in choices:
        if col in frame:
            fig.add_trace(go.Scatter(x=frame["date"], y=frame[col], name=name,
                                     mode="lines", line={"color": color, "width": 2.5}, connectgaps=False))
    if reference is not None:
        fig.add_hline(y=reference, line_dash="dash", line_color="#8D97A6")
    fig.update_layout(height=385, template="plotly_white", hovermode="x unified",
                      margin=dict(l=10, r=10, t=15, b=20), yaxis_title=ylabel,
                      legend=dict(orientation="h", y=1.13, x=0))
    return fig


def pressure_label(yoy):
    if yoy is None:
        return "Unavailable"
    if yoy < 0:
        return "Deflation"
    if yoy >= 20:
        return "Very high inflation"
    if yoy >= 10:
        return "High inflation"
    if yoy >= 5:
        return "Elevated inflation"
    return "Lower inflation"


def valid_completed_month(month):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise ValueError("Month must use YYYY-MM format.")
    yr, mn = map(int, month.split("-"))
    if yr < 2014 or (yr, mn) >= (date.today().year, date.today().month):
        raise ValueError("Enter a completed month from January 2014 onward.")


def months_between(start, end):
    if not start or end <= start:
        return []
    months = pd.period_range(start=start, end=end, freq="M").astype(str).tolist()
    return months[1:-1]


def save_observation(month, field, value, published, source, url, base, same_wage_base,
                     allow_update, allow_placeholders):
    """Atomic audited insert, using Step 8's source logging and linking helpers."""
    from monthly_entry import create_source_log, derived_updates, latest_ccpi_base
    from database import create_tables

    valid_completed_month(month)
    if not math.isfinite(value):
        raise ValueError("The value must be finite.")
    if published < date.fromisoformat(month + "-01") or published > date.today():
        raise ValueError("Publication date must not precede the observation month or be in the future.")
    if not source.strip():
        raise ValueError("Specify the official publication or source name.")
    if field.startswith("ccpi_") and base not in {"2013=100", "2021=100"}:
        raise ValueError("Select a known CCPI published base. New base revisions require separate review.")
    with connect() as conn:
        with conn:
            create_tables(conn)
            create_source_log(conn)
            existing = conn.execute(
                f'SELECT "{field}", ccpi_published_base FROM economic_monthly WHERE month=?', (month,)
            ).fetchone()
            last = conn.execute("SELECT MAX(month) FROM economic_monthly").fetchone()[0]
            if existing is None and last and month < last:
                raise ValueError("An internal historical month is missing. Review database gaps first.")
            gaps = months_between(last, month) if last and month > last else []
            if gaps and not allow_placeholders:
                raise ValueError(f"There are {len(gaps)} missing preceding months. Authorize blank placeholders.")
            old_value = existing[0] if existing else None
            if old_value is not None and math.isclose(float(old_value), value, abs_tol=1e-10, rel_tol=0):
                return "No change: this value is already stored."
            if old_value is not None and not allow_update:
                raise ValueError("Existing value found. Explicitly authorize a source revision.")
            if field.startswith("ccpi_"):
                stored_base = existing[1] if existing else None
                if stored_base and stored_base != base:
                    raise ValueError("CCPI base differs from the stored base for this month.")
                previous = latest_ccpi_base(conn, month)
                if previous and previous != base:
                    raise ValueError("CCPI base changed. Verify and document a new linking method before saving.")
            for gap in gaps:
                conn.execute("""INSERT INTO economic_monthly(month,source,record_origin,notes)
                                VALUES (?, 'Awaiting official source data', 'missing_month_placeholder',
                                'Blank placeholder: no reported values') ON CONFLICT(month) DO NOTHING""", (gap,))
            conn.execute("""INSERT INTO economic_monthly(month,source,record_origin,notes)
                            VALUES (?, 'Manual monthly entry; see source log', 'manual_entry',
                            'Source details in indicator_source_log') ON CONFLICT(month) DO NOTHING""", (month,))
            changes = {field: value}
            if field.startswith("ccpi_"):
                changes["ccpi_published_base"] = base
            if month > "2025-12":
                changes.update(derived_updates(conn, month, field, value, base, same_wage_base))
            assignments = ", ".join(f'"{col}" = ?' for col in changes)
            conn.execute(f'UPDATE economic_monthly SET {assignments}, updated_at=CURRENT_TIMESTAMP, '
                         "record_origin='manual_entry' WHERE month=?", [*changes.values(), month])
            conn.execute("""INSERT INTO indicator_source_log
                            (month,indicator,old_value,new_value,publication_date,source_name,source_url)
                            VALUES (?,?,?,?,?,?,?)""",
                         (month, field, str(old_value) if old_value is not None else None,
                          str(value), published.isoformat(), source.strip(), url.strip() or None))
    return f"Saved {field} for {month}. Audit record created."


st.title("Sri Lanka Economic Warning & Risk Intelligence System")
st.caption("CBSL / DCS historical monitoring · Descriptive indicators, not validated financial-crisis probabilities")
try:
    df = load_data()
except (FileNotFoundError, sqlite3.Error, ValueError) as error:
    st.error(str(error))
    st.code(r".\.venv\Scripts\python.exe .\seed_database.py", language="powershell")
    st.stop()

with st.sidebar:
    st.header("Explore the data")
    min_date, max_date = df["date"].min().date(), df["date"].max().date()
    start_date = st.date_input("Start month", value=min_date, min_value=min_date, max_value=max_date)
    end_date = st.date_input("End month", value=max_date, min_value=min_date, max_value=max_date)
    salary = st.number_input("Hypothetical fixed salary in Jan 2019 (LKR)", min_value=1000.0,
                             value=60000.0, step=1000.0)
    st.caption("Salary is a scenario, not a national observed salary series.")

if start_date > end_date:
    st.error("Start date must not be later than end date.")
    st.stop()

selected = df[(df["date"].dt.date >= start_date) & (df["date"].dt.date <= end_date)].copy()
if selected.empty:
    st.warning("No observations in this selected period.")
    st.stop()

last_month = df["month"].iloc[-1]
st.info(f"Database coverage: **{df['month'].iloc[0]} to {last_month}** · {len(df)} monthly rows. "
        "Different indicators have different coverage and reporting delays.")

overview, trends, wages, scenario, quality, entry = st.tabs([
    "Overview", "Inflation trends", "Wage-rate analysis", "Salary scenario", "Data availability", "Enter monthly data"
])

with overview:
    inflation_month, inflation = nonmissing_latest(df, "headline_yoy_pct")
    food_month, food = nonmissing_latest(df, "food_yoy_pct")
    reserve_month, reserves = nonmissing_latest(df, "fx_reserves_usd_bn")
    cols = st.columns(3)
    cols[0].metric("Latest headline YoY inflation", f"{inflation:.1f}%" if inflation is not None else "N/A",
                   help=f"Observation month: {inflation_month or 'unavailable'}")
    cols[1].metric("Latest food YoY inflation", f"{food:.1f}%" if food is not None else "N/A",
                   help=f"Observation month: {food_month or 'unavailable'}")
    cols[2].metric("Latest reserves (USD bn)", f"{reserves:.2f}" if reserves is not None else "N/A",
                   help=f"Observation month: {reserve_month or 'unavailable'}")
    st.write(f"**Illustrative inflation-pressure label:** {pressure_label(inflation)} "
             f"(based on {inflation_month or 'unavailable'} data).")
    st.warning("This is a descriptive inflation classification, **not** a probability or prediction of a financial crisis. "
               "Reserves, exchange rates, debt and other vulnerabilities must be sourced separately.")
    st.plotly_chart(series_chart(selected, [("headline_yoy_pct", "Headline", NAVY),
                                           ("food_yoy_pct", "Food", AMBER),
                                           ("nonfood_yoy_pct", "Non-food", TEAL)],
                                 "Year-on-year inflation (%)", reference=0), use_container_width=True, key="overview_inflation_chart")

with trends:
    st.subheader("Official-source year-on-year inflation")
    st.plotly_chart(series_chart(selected, [("headline_yoy_pct", "Headline", NAVY),
                                           ("food_yoy_pct", "Food", AMBER),
                                           ("nonfood_yoy_pct", "Non-food", TEAL)],
                                 "Year-on-year inflation (%)", reference=0), use_container_width=True, key="inflation_trends_chart")
    st.subheader("Inflation momentum")
    # Three-month rolling averages require all three monthly observations.
    tmp = df[["month", "date", "headline_yoy_pct"]].copy()
    tmp["three_month_mean"] = tmp["headline_yoy_pct"].rolling(3, min_periods=3).mean()
    tmp["momentum_pp"] = tmp["three_month_mean"] - tmp["three_month_mean"].shift(3)
    tmp = tmp[tmp["month"].isin(selected["month"])]
    st.plotly_chart(series_chart(tmp, [("momentum_pp", "3-month vs previous 3-month average", AMBER)],
                                 "Difference in percentage points", reference=0), use_container_width=True, key="inflation_momentum_chart")
    st.caption("Year-on-year inflation is taken from the source field. Momentum is a descriptive comparison, "
               "not a forward-looking forecast.")

with wages:
    st.subheader("CBSL wage-rate indices, January 2019 = 100")
    st.plotly_chart(series_chart(selected, [("public_nominal_jan2019_100", "Public nominal", VIOLET),
                                           ("informal_nominal_jan2019_100", "Informal nominal", CORAL)],
                                 "Nominal wage-rate index", reference=100), use_container_width=True, key="nominal_wage_chart")
    st.subheader("Researcher-calculated CCPI-adjusted wage-rate indices")
    tmp = selected.copy()
    price = tmp["ccpi_linked_jan2019_100"].where(tmp["ccpi_linked_jan2019_100"] > 0)
    for sector in ("public", "informal"):
        tmp[f"{sector}_real_ccpi"] = 100 * tmp[f"{sector}_nominal_jan2019_100"] / price
    st.plotly_chart(series_chart(tmp, [("public_real_ccpi", "Public (CCPI adjusted)", VIOLET),
                                      ("informal_real_ccpi", "Informal (CCPI adjusted)", CORAL)],
                                 "Researcher-calculated real wage-rate index", reference=100), use_container_width=True, key="real_wage_chart")
    st.caption("CBSL's published real wage indices are NCPI-adjusted. The CCPI-based indices shown here "
               "are researcher calculations using an approximately linked CCPI spanning a 2023 basket/base change. "
               "Wage-rate indices are not observed individual salaries.")

with scenario:
    st.subheader("Fixed-salary purchasing-power simulation")
    tmp = selected.copy()
    price = tmp["ccpi_linked_jan2019_100"].where(tmp["ccpi_linked_jan2019_100"] > 0)
    tmp["required_salary"] = salary * price / 100
    tmp["real_fixed_salary"] = salary * 100 / price
    st.plotly_chart(series_chart(tmp, [("required_salary", "Salary needed to match Jan 2019", AMBER),
                                      ("real_fixed_salary", "Real value of fixed salary", TEAL)],
                                 "Sri Lankan rupees (LKR)"), use_container_width=True, key="salary_scenario_chart")
    last = tmp.dropna(subset=["required_salary", "real_fixed_salary"])
    if not last.empty:
        row = last.iloc[-1]
        a, b = st.columns(2)
        a.metric("Required salary", f"LKR {row['required_salary']:,.0f}")
        b.metric("Fixed salary in Jan 2019 purchasing power", f"LKR {row['real_fixed_salary']:,.0f}")
        st.caption(f"Calculated for {row['month']}; January 2019 is the fixed reference period.")
    else:
        st.info("No compatible linked CCPI observations are available for this selection.")
    st.warning("Hypothetical fixed salary only. The linked price series is approximate and is not an official "
               "continuous DCS index across the 2023 revision.")

with quality:
    st.subheader("Coverage of available indicators")
    indicators = [
        ("Headline inflation", "headline_yoy_pct"),
        ("Food inflation", "food_yoy_pct"),
        ("Non-food inflation", "nonfood_yoy_pct"),
        ("Linked CCPI", "ccpi_linked_jan2019_100"),
        ("Public nominal wage rate", "public_nominal_jan2019_100"),
        ("Informal nominal wage rate", "informal_nominal_jan2019_100"),
        ("CBSL public real wage (NCPI)", "public_real_ncpi_raw"),
        ("CBSL informal real wage (NCPI)", "informal_real_ncpi_raw"),
        ("FX reserves", "fx_reserves_usd_bn"),
        ("USD/LKR", "usd_lkr"),
    ]
    rows = []
    for name, col in indicators:
        known = df.loc[df[col].notna(), "month"]
        rows.append({"Indicator": name, "Available months": len(known),
                     "First month": known.iloc[0] if len(known) else "—",
                     "Last month": known.iloc[-1] if len(known) else "—"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.write("#### Source-date audit")
    with connect() as conn:
        has_log = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='indicator_source_log'").fetchone()
        logs = pd.read_sql_query("SELECT month, indicator, new_value, publication_date, source_name, recorded_at "
                                 "FROM indicator_source_log ORDER BY id DESC LIMIT 100", conn) if has_log else pd.DataFrame()
    if logs.empty:
        st.info("No individually recorded monthly-entry source records yet. Historical CSV publication dates remain unknown.")
    else:
        st.dataframe(logs, hide_index=True, use_container_width=True)
    st.download_button("Download observations as CSV", data=df.to_csv(index=False).encode("utf-8"),
                       file_name="sl_ewris_economic_observations.csv", mime="text/csv")

with entry:
    st.subheader("Add one official monthly observation")
    st.caption("Enter only published values. Existing values require explicit revision confirmation, "
               "and every saved entry is audit-logged.")
    with st.form("monthly_entry_form", clear_on_submit=False):
        default_month = date.today().replace(day=1)
        if default_month.month == 1:
            default_month = date(default_month.year - 1, 12, 1)
        else:
            default_month = date(default_month.year, default_month.month - 1, 1)
        observation_date = st.date_input("Observation month", value=default_month,
                                         min_value=date(2014, 1, 1), max_value=default_month)
        month = observation_date.strftime("%Y-%m")
        label = st.selectbox("Economic indicator", list(ENTRY_FIELDS.keys()))
        field, positive = ENTRY_FIELDS[label]
        value_text = st.text_input("Published value", placeholder="For 2.1%, enter 2.1 (not 0.021)")
        publication = st.date_input("Official publication date", value=date.today())
        source = st.text_input("Official source / publication name", placeholder="e.g., DCS CCPI monthly release")
        url = st.text_input("Official source URL (optional)")
        ccpi_base = st.selectbox("Published CCPI base (for CCPI entries only)",
                                 ["2021=100", "2013=100"]) if field.startswith("ccpi_") else None
        same_wage_base = st.checkbox("Nominal wage index uses the same base as Jan 2019", value=False) if field in {
            "public_nominal_original", "informal_nominal_original"
        } else False
        allow_update = st.checkbox("I confirm replacement of an existing value (source revision)")
        allow_placeholders = st.checkbox("I authorize empty placeholders for intervening missing months")
        confirmed = st.checkbox("I verified this value and date against the stated official publication")
        submit = st.form_submit_button("Validate and save observation", type="primary")
    if submit:
        if not confirmed:
            st.error("Confirm the source verification before saving.")
        else:
            try:
                value = float(value_text.replace(",", ""))
                if not math.isfinite(value) or (positive and value <= 0) or (not positive and value < -100):
                    raise ValueError("Invalid value for the selected indicator or unit.")
                outcome = save_observation(month, field, value, publication, source, url,
                                           ccpi_base, same_wage_base, allow_update, allow_placeholders)
                st.success(outcome)
                st.info("Refresh the browser to see the new observation. Run Step 7 again to regenerate exported CSVs.")
            except (ValueError, sqlite3.Error, ImportError) as exc:
                st.error(f"Observation was not saved: {exc}")

st.divider()
st.caption("Research prototype · Not an investment advisory tool · Historical revisions and publication lags must be reviewed before forecasting.")

# ============================================================
# STEP 11 - ECONOMIC STRESS MONITOR
# ============================================================

from pathlib import Path

stress_file = (
    Path(__file__).resolve().parent
    / "outputs"
    / "economic_stress"
    / "monthly_economic_stress.csv"
)

st.divider()
st.subheader("Economic Stress Monitoring")

if stress_file.exists():

    stress_df = pd.read_csv(stress_file)

    latest_stress = stress_df.iloc[-1]

    st.caption(
        f"Latest assessed month: {latest_stress['month']}"
    )

    st.info(latest_stress["assessment_explanation"])

    st.warning(
        "Monitoring indicators are descriptive. "
        "They are not validated national financial "
        "crisis probabilities."
    )

    st.dataframe(
        stress_df.tail(12),
        use_container_width=True
    )

else:
    st.info(
        "Run analysis/economic_stress.py "
        "to generate monitoring indicators."
    )
    
    # ============================================================
# STEP 14 - EXTERNAL SECTOR MONITOR
# ============================================================

from analysis.external_dashboard import render_external_dashboard

render_external_dashboard()