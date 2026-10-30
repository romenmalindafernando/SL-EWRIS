from pathlib import Path
import sqlite3
import math

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "economic_risk.db"

st.set_page_config(
    page_title="SL-EWRIS | Data Quality",
    page_icon="🔍",
    layout="wide"
)

st.title("Data Quality & Verification Dashboard")
st.caption("SL-EWRIS | Monthly Data Quality Monitoring")

st.info(
    "This dashboard checks draft completeness and manual "
    "review consistency. It does not independently verify "
    "official publications or predict financial crises."
)

INDICATORS = {
    "inflation_yoy_pct": "Inflation YoY",
    "nominal_wage_growth_yoy_pct": "Wage Growth YoY",
    "usd_lkr": "USD/LKR",
    "fx_reserves_usd_bn": "Foreign Reserves"
}

if not DB.is_file():
    st.error("Existing economic_risk.db database is missing.")
    st.stop()


def load_data():

    with sqlite3.connect(DB, timeout=15) as con:

        tables = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table'"
            )
        }

        if "monthly_economic_drafts" not in tables:
            return None, None

        drafts = pd.read_sql_query(
            "SELECT * FROM monthly_economic_drafts "
            "ORDER BY month DESC",
            con
        )

        if "monthly_indicator_reviews" in tables:
            reviews = pd.read_sql_query(
                "SELECT * FROM monthly_indicator_reviews",
                con
            )
        else:
            reviews = pd.DataFrame(columns=[
                "month", "indicator", "reviewed_value",
                "unit", "publication_date", "source_url",
                "review_status", "reviewed_at"
            ])

    return drafts, reviews


try:
    drafts, reviews = load_data()
except (sqlite3.Error, KeyError) as exc:
    st.error(f"Unable to load database records: {exc}")
    st.stop()

if drafts is None:
    st.warning("Run Step 40 to initialize draft storage.")
    st.stop()

if drafts.empty:
    st.warning("No monthly data saved yet.")
    st.stop()


def is_present(value):
    if pd.isna(value):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


review_lookup = {}

for _, review in reviews.iterrows():
    key = (
        str(review["month"]),
        str(review["indicator"])
    )
    review_lookup[key] = review


records = []

for _, draft in drafts.iterrows():

    month = str(draft["month"])

    for column, label in INDICATORS.items():

        value = draft[column]
        available = is_present(value)

        review = review_lookup.get((month, column))

        publication_date = ""
        source_url = ""
        reviewed_at = ""

        if not available:
            status = "Missing data"

        elif review is None:
            status = "Unverified"

        else:
            publication_date = str(
                review.get("publication_date", "")
            )
            source_url = str(
                review.get("source_url", "")
            )
            reviewed_at = str(
                review.get("reviewed_at", "")
            )

            reviewed_value = review.get("reviewed_value")

            matches = (
                is_present(reviewed_value)
                and math.isclose(
                    float(value),
                    float(reviewed_value),
                    rel_tol=0,
                    abs_tol=0.000001
                )
            )

            if not matches:
                status = "Review outdated"
            elif (
                str(review.get("review_status", ""))
                != "Manually reviewed"
            ):
                status = "Unverified"
            else:
                status = "Manually reviewed"

        records.append({
            "month": month,
            "indicator": label,
            "draft_value": (
                float(value) if available else None
            ),
            "status": status,
            "publication_date": publication_date,
            "source_url": source_url,
            "reviewed_at": reviewed_at
        })


quality = pd.DataFrame(records)

st.subheader("1. Data Quality Overview")

total_months = quality["month"].nunique()

available_count = int(
    (quality["status"] != "Missing data").sum()
)

reviewed_count = int(
    (quality["status"] == "Manually reviewed").sum()
)

outdated_count = int(
    (quality["status"] == "Review outdated").sum()
)

c1, c2, c3, c4 = st.columns(4)

c1.metric("Months Saved", total_months)
c2.metric("Available Indicator Values", available_count)
c3.metric("Current Manual Reviews", reviewed_count)
c4.metric("Outdated Reviews", outdated_count)

total_cells = len(quality)

coverage = (
    100 * available_count / total_cells
    if total_cells else 0
)

st.write(f"**Draft Data Coverage: {coverage:.1f}%**")
st.progress(min(coverage / 100, 1.0))

st.caption(
    "Coverage is the proportion of the four tracked "
    "indicators with a numeric value across saved months. "
    "It is not a measure of statistical reliability."
)

st.divider()

st.subheader("2. Select Reporting Month")

selected_month = st.selectbox(
    "Reporting Month",
    sorted(quality["month"].unique(), reverse=True)
)

selected = quality[
    quality["month"] == selected_month
].copy()

st.dataframe(
    selected[
        [
            "indicator",
            "draft_value",
            "status",
            "publication_date",
            "reviewed_at"
        ]
    ],
    use_container_width=True,
    hide_index=True
)

missing = selected[
    selected["status"] == "Missing data"
]

unverified = selected[
    selected["status"] == "Unverified"
]

outdated = selected[
    selected["status"] == "Review outdated"
]

st.subheader("3. Monthly Data Readiness")

if not missing.empty:
    st.warning(
        f"{len(missing)} indicator(s) are missing."
    )

if not unverified.empty:
    st.warning(
        f"{len(unverified)} indicator(s) have no "
        "current manual review."
    )

if not outdated.empty:
    st.error(
        f"{len(outdated)} indicator(s) have reviews "
        "that no longer match the saved draft value."
    )

if (
    missing.empty
    and unverified.empty
    and outdated.empty
):
    st.success(
        "All four indicators have current matching "
        "manual reviews. Independent source "
        "verification is still required."
    )

st.divider()

st.subheader("4. Indicator Status Across Months")

status_table = quality.pivot(
    index="month",
    columns="indicator",
    values="status"
).sort_index(ascending=False)

st.dataframe(
    status_table,
    use_container_width=True
)

st.subheader("5. Review Summary")

summary = (
    quality.groupby(
        ["indicator", "status"]
    )
    .size()
    .reset_index(name="records")
)

st.dataframe(
    summary,
    use_container_width=True,
    hide_index=True
)

st.divider()

st.subheader("6. Export Quality Audit")

csv_data = quality.to_csv(
    index=False
).encode("utf-8-sig")

st.download_button(
    "Download Data Quality Audit CSV",
    data=csv_data,
    file_name="sl_ewris_data_quality_audit.csv",
    mime="text/csv"
)

st.caption(
    "Read-only dashboard. No SQLite records are "
    "modified, deleted or automatically approved."
)
