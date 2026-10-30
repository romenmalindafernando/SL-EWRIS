from pathlib import Path
from datetime import date
from urllib.parse import urlparse
import sqlite3
import math

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "economic_risk.db"

st.set_page_config(
    page_title="SL-EWRIS | Data Verification",
    page_icon="✅",
    layout="wide"
)

st.title("Economic Data Verification")
st.caption("SL-EWRIS | Official Source Evidence Review")

st.warning(
    "This page records a human review of source evidence. "
    "It does not independently authenticate CBSL/DCS data "
    "and does not modify historical research observations."
)

if not DB.exists():
    st.error("Existing SQLite database was not found.")
    st.stop()

INDICATORS = {
    "Inflation YoY (%)": (
        "inflation_yoy_pct", "%"
    ),
    "Nominal Wage Growth YoY (%)": (
        "nominal_wage_growth_yoy_pct", "%"
    ),
    "Monthly Average USD/LKR": (
        "usd_lkr", "LKR per USD"
    ),
    "Gross Official Reserves": (
        "fx_reserves_usd_bn", "USD billions"
    ),
}


def connect():
    con = sqlite3.connect(DB, timeout=15)
    con.row_factory = sqlite3.Row
    return con


def initialize():
    with connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS
            monthly_indicator_reviews (
                month TEXT NOT NULL,
                indicator TEXT NOT NULL,
                reviewed_value REAL NOT NULL,
                unit TEXT NOT NULL,
                publication_date TEXT NOT NULL,
                source_url TEXT NOT NULL,
                review_status TEXT NOT NULL,
                review_note TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (month, indicator)
            )
        """)


def load_drafts():
    with connect() as con:
        return pd.read_sql_query("""
            SELECT *
            FROM monthly_economic_drafts
            ORDER BY month DESC
        """, con)


def load_reviews():
    with connect() as con:
        return pd.read_sql_query("""
            SELECT *
            FROM monthly_indicator_reviews
            ORDER BY month DESC, indicator
        """, con)


def valid_official_url(url):
    try:
        parsed = urlparse(url.strip())

        if parsed.scheme != "https":
            return False

        host = (parsed.hostname or "").lower()

        return (
            host == "cbsl.gov.lk"
            or host.endswith(".cbsl.gov.lk")
            or host == "statistics.gov.lk"
            or host.endswith(".statistics.gov.lk")
        )
    except ValueError:
        return False


initialize()

st.subheader("1. Select Monthly Draft")

try:
    drafts = load_drafts()
except sqlite3.Error as exc:
    st.error(f"Cannot read drafts: {exc}")
    st.stop()

if drafts.empty:
    st.info(
        "No monthly drafts found. "
        "Use Step 40 to save a draft first."
    )
    st.stop()

month = st.selectbox(
    "Reporting Month",
    drafts["month"].tolist()
)

indicator_name = st.selectbox(
    "Economic Indicator",
    list(INDICATORS.keys())
)

column, unit = INDICATORS[indicator_name]

draft = drafts.loc[
    drafts["month"] == month
].iloc[0]

draft_value = draft[column]

if pd.isna(draft_value):
    st.error(
        "This indicator has no value in the selected draft."
    )
    st.stop()

draft_value = float(draft_value)

st.metric(
    "Draft Value",
    f"{draft_value:,.6f} {unit}"
)

st.write(
    "**Current Draft Source Notes:**",
    draft["source_note"] or "Not provided"
)

st.divider()
st.subheader("2. Enter Official Source Evidence")

with st.form("indicator_review_form"):

    source_url = st.text_input(
        "Official Publication URL",
        placeholder="https://www.cbsl.gov.lk/..."
    )

    published_on = st.date_input(
        "Official Publication Date",
        value=date.today(),
        max_value=date.today()
    )

    official_value = st.number_input(
        "Value Reported by Official Source",
        value=draft_value,
        format="%.6f"
    )

    st.caption(
        f"Enter the published value using {unit}. "
        "Do not mix USD millions and USD billions, "
        "or monthly and annual growth rates."
    )

    review_note = st.text_area(
        "Evidence / Definition Notes",
        placeholder=(
            "Table number, page, units, "
            "reporting month, definition..."
        )
    )

    checked = st.checkbox(
        "I manually checked the official source, "
        "reporting month, indicator definition, "
        "units and published value."
    )

    submitted = st.form_submit_button(
        "Record Manual Review",
        type="primary"
    )

if submitted:

    errors = []

    if not valid_official_url(source_url):
        errors.append(
            "A valid HTTPS CBSL/DCS source URL is required."
        )

    if published_on < date.fromisoformat(month + "-01"):
        errors.append(
            "Publication date cannot precede reporting month."
        )

    if not math.isfinite(official_value):
        errors.append("Published value must be finite.")

    if not math.isclose(
        official_value,
        draft_value,
        rel_tol=0,
        abs_tol=0.000001
    ):
        errors.append(
            "Draft and published values do not match "
            "at the required precision. Review the "
            "difference before recording this evidence."
        )

    if not review_note.strip():
        errors.append(
            "Provide a source table/page or definition note."
        )

    if not checked:
        errors.append(
            "Manual source-review confirmation is required."
        )

    if errors:
        for error in errors:
            st.error(error)
    else:
        try:
            with connect() as con:

                # Read current draft inside transaction.
                # Do not approve an outdated edited value.
                current = con.execute(
                    f"""
                    SELECT {column}
                    FROM monthly_economic_drafts
                    WHERE month = ?
                    """,
                    (month,)
                ).fetchone()

                if (
                    current is None
                    or current[column] is None
                    or not math.isclose(
                        float(current[column]),
                        draft_value,
                        rel_tol=0,
                        abs_tol=0.000001
                    )
                ):
                    raise ValueError(
                        "Draft changed. Refresh before reviewing."
                    )

                con.execute("""
                    INSERT INTO monthly_indicator_reviews (
                        month, indicator, reviewed_value,
                        unit, publication_date, source_url,
                        review_status, review_note
                    )
                    VALUES (?, ?, ?, ?, ?, ?,
                            'Manually reviewed', ?)

                    ON CONFLICT(month, indicator)
                    DO UPDATE SET
                        reviewed_value = excluded.reviewed_value,
                        unit = excluded.unit,
                        publication_date =
                            excluded.publication_date,
                        source_url = excluded.source_url,
                        review_status = 'Manually reviewed',
                        review_note = excluded.review_note,
                        reviewed_at = CURRENT_TIMESTAMP
                """, (
                    month,
                    column,
                    draft_value,
                    unit,
                    published_on.isoformat(),
                    source_url.strip(),
                    review_note.strip()
                ))

            st.success(
                "Manual review recorded successfully. "
                "Independent verification is still required "
                "before research or model use."
            )

        except (sqlite3.Error, ValueError) as exc:
            st.error(str(exc))

st.divider()
st.subheader("3. Recorded Manual Reviews")

reviews = load_reviews()

if reviews.empty:
    st.info("No manual reviews recorded yet.")
else:
    # Re-check current draft values so edited drafts
    # are not mistaken for still-reviewed observations.
    current_values = drafts.melt(
        id_vars=["month"],
        value_vars=[
            "inflation_yoy_pct",
            "nominal_wage_growth_yoy_pct",
            "usd_lkr",
            "fx_reserves_usd_bn"
        ],
        var_name="indicator",
        value_name="current_draft_value"
    )

    display = reviews.merge(
        current_values,
        on=["month", "indicator"],
        how="left",
        validate="one_to_one"
    )

    matches = (
        display["current_draft_value"].notna()
        & (
            (display["reviewed_value"]
             - display["current_draft_value"]).abs()
            <= 0.000001
        )
    )

    display["review_valid_for_current_draft"] = matches

    st.metric(
        "Reviews Matching Current Drafts",
        int(matches.sum())
    )

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True
    )

st.caption(
    "Manual review records are stored separately. "
    "They are not automatically imported into "
    "economic_monthly or the historical replay ledger."
)
