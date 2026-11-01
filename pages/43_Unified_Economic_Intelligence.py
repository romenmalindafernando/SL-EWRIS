

import pandas as pd
import streamlit as st

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from database import connect_database
ROOT = Path(__file__).resolve().parents[1]

HISTORY = (
    ROOT / "outputs/cbsl_preparation"
    / "combined_external_review_2014_2025.csv"
)

RISK = (
    ROOT / "outputs/external_risk_analysis"
    / "external_risk_indicators_2014_2025.csv"
)

st.set_page_config(
    page_title="SL-EWRIS | Unified Intelligence",
    page_icon="🌍",
    layout="wide"
)

st.title("SL-EWRIS | Unified Economic Intelligence")
st.caption(
    "Sri Lanka Economic Warning & Risk Intelligence System"
)

st.warning(
    "Research prototype. Historical screening thresholds "
    "are illustrative, not calibrated crisis predictions. "
    "Monthly draft values are not independently verified."
)

INDICATORS = {
    "inflation_yoy_pct": "Inflation YoY",
    "nominal_wage_growth_yoy_pct": "Wage Growth YoY",
    "usd_lkr": "USD/LKR",
    "fx_reserves_usd_bn": "Foreign Reserves"
}


def read_csv(path):
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def read_database():
    with connect_database() as con:

        names = {
            row[0]
            for row in con.execute(
                "SELECT tablename AS name FROM pg_catalog.pg_tables "
                "WHERE schemaname = current_schema()"
            )
        }

        if "monthly_economic_drafts" in names:
            drafts = pd.read_sql_query(
                "SELECT * FROM monthly_economic_drafts "
                "ORDER BY month DESC",
                con
            )
        else:
            drafts = pd.DataFrame()

        if "monthly_indicator_reviews" in names:
            reviews = pd.read_sql_query(
                "SELECT * FROM monthly_indicator_reviews",
                con
            )
        else:
            reviews = pd.DataFrame()

    return drafts, reviews


def number(value, decimals=2, suffix=""):
    numeric = pd.to_numeric(value, errors="coerce")

    if pd.isna(numeric):
        return "Unavailable"

    return f"{float(numeric):,.{decimals}f}{suffix}"


historical = read_csv(HISTORY)
risk = read_csv(RISK)

try:
    drafts, reviews = read_database()
except psycopg.Error as exc:
    st.error(f"Database error: {exc}")
    st.stop()

st.subheader("1. System Overview")

historical_months = (
    historical["month"].nunique()
    if "month" in historical.columns else 0
)

draft_months = (
    drafts["month"].nunique()
    if "month" in drafts.columns else 0
)

review_count = len(reviews)

risk_months = (
    risk["month"].nunique()
    if "month" in risk.columns else 0
)

c1, c2, c3, c4 = st.columns(4)

c1.metric("Historical Months", historical_months)
c2.metric("Saved Draft Months", draft_months)
c3.metric("Manual Review Records", review_count)
c4.metric("Risk Screening Months", risk_months)

st.caption(
    "Manual review count does not represent independent "
    "verification or official approval."
)

st.divider()

tab1, tab2, tab3, tab4 = st.tabs([
    "Historical Trends",
    "Monthly Monitoring",
    "Data Quality",
    "Research Assessment"
])

# ------------------------------------------------
# TAB 1 — HISTORICAL TRENDS
# ------------------------------------------------

with tab1:

    st.subheader("Historical External Sector Trends")

    required = {
        "month", "fx_reserves_usd_bn", "usd_lkr"
    }

    if historical.empty or not required.issubset(
        historical.columns
    ):
        st.warning(
            "Historical data missing or columns unavailable."
        )

    else:
        hist = historical.copy()

        hist["month"] = hist["month"].astype(str)

        hist = hist.drop_duplicates(
            subset=["month"], keep="last"
        ).sort_values("month")

        for col in ["fx_reserves_usd_bn", "usd_lkr"]:
            hist[col] = pd.to_numeric(
                hist[col], errors="coerce"
            )

        selected_month = st.selectbox(
            "Select Historical Month",
            hist["month"].tolist(),
            index=len(hist) - 1
        )

        selected = hist[
            hist["month"] == selected_month
        ].iloc[0]

        a, b = st.columns(2)

        a.metric(
            "Official Reserve Assets",
            number(
                selected["fx_reserves_usd_bn"],
                3, " USD bn"
            )
        )

        b.metric(
            "Average USD/LKR",
            number(selected["usd_lkr"])
        )

        st.subheader("Foreign Reserves")

        st.line_chart(
            hist.set_index("month")[
                ["fx_reserves_usd_bn"]
            ]
        )

        st.subheader("USD/LKR Exchange Rate")

        st.line_chart(
            hist.set_index("month")[["usd_lkr"]]
        )

        st.caption(
            "Historical figures are retrospective compiled "
            "observations. Exact original release dates "
            "and historical data vintages remain incomplete."
        )

# ------------------------------------------------
# TAB 2 — MONTHLY MONITORING
# ------------------------------------------------

with tab2:

    st.subheader("Saved Monthly Economic Data")

    if drafts.empty:
        st.info(
            "No monthly drafts found. "
            "Enter data using Step 40."
        )

    else:
        month = st.selectbox(
            "Select Saved Month",
            drafts["month"].astype(str).tolist(),
            key="unified_month"
        )

        current = drafts[
            drafts["month"].astype(str) == month
        ].iloc[0]

        a, b, c, d = st.columns(4)

        a.metric(
            "Inflation YoY",
            number(
                current["inflation_yoy_pct"], 2, "%"
            )
        )

        b.metric(
            "Wage Growth YoY",
            number(
                current["nominal_wage_growth_yoy_pct"],
                2, "%"
            )
        )

        c.metric(
            "USD/LKR",
            number(current["usd_lkr"])
        )

        d.metric(
            "Foreign Reserves",
            number(
                current["fx_reserves_usd_bn"],
                3, " USD bn"
            )
        )

        inflation = pd.to_numeric(
            current["inflation_yoy_pct"],
            errors="coerce"
        )

        wages = pd.to_numeric(
            current["nominal_wage_growth_yoy_pct"],
            errors="coerce"
        )

        st.subheader("Purchasing Power Assessment")

        if (
            pd.notna(inflation)
            and pd.notna(wages)
            and inflation > -100
        ):

            real_wage = (
                (1 + wages / 100)
                / (1 + inflation / 100)
                - 1
            ) * 100

            st.metric(
                "Estimated Real Wage Growth",
                f"{real_wage:.2f}%"
            )

            if real_wage < 0:
                st.warning(
                    "Real wages are estimated to be falling."
                )
            else:
                st.info(
                    "Estimated real wage growth "
                    "is non-negative."
                )

            st.caption(
                "This calculation requires comparable "
                "wage and inflation populations and periods."
            )

        else:
            st.info(
                "Inflation and wage growth data are "
                "needed for purchasing power analysis."
            )

        st.warning(
            "These values are saved drafts. "
            "They are not automatically official data."
        )

        st.dataframe(
            drafts,
            use_container_width=True,
            hide_index=True
        )

# ------------------------------------------------
# TAB 3 — DATA QUALITY
# ------------------------------------------------

with tab3:

    st.subheader("Indicator Verification Overview")

    if drafts.empty:
        st.info("No draft records to audit.")

    else:
        review_lookup = {}

        if not reviews.empty:
            for _, r in reviews.iterrows():
                review_lookup[
                    (str(r["month"]), str(r["indicator"]))
                ] = r

        records = []

        for _, draft in drafts.iterrows():

            month = str(draft["month"])

            for column, label in INDICATORS.items():

                value = pd.to_numeric(
                    draft.get(column),
                    errors="coerce"
                )

                review = review_lookup.get(
                    (month, column)
                )

                if pd.isna(value):
                    status = "Missing data"

                elif review is None:
                    status = "Unverified"

                else:
                    reviewed = pd.to_numeric(
                        review["reviewed_value"],
                        errors="coerce"
                    )

                    same_value = (
                        pd.notna(reviewed)
                        and abs(float(value) - float(reviewed))
                        <= 0.000001
                    )

                    if not same_value:
                        status = "Review outdated"

                    elif (
                        str(review["review_status"])
                        == "Manually reviewed"
                    ):
                        status = "Manually reviewed"

                    else:
                        status = "Unverified"

                records.append({
                    "month": month,
                    "indicator": label,
                    "value": value,
                    "status": status
                })

        quality = pd.DataFrame(records)

        statuses = quality["status"].value_counts()

        a, b, c = st.columns(3)

        a.metric(
            "Manually Reviewed",
            int(statuses.get("Manually reviewed", 0))
        )

        b.metric(
            "Unverified",
            int(statuses.get("Unverified", 0))
        )

        c.metric(
            "Missing / Outdated",
            int(
                statuses.get("Missing data", 0)
                + statuses.get("Review outdated", 0)
            )
        )

        st.dataframe(
            quality,
            use_container_width=True,
            hide_index=True
        )

        st.caption(
            "A current manual review means its recorded "
            "numeric value matches the present draft. "
            "Source-note changes and independent source "
            "authenticity are not assessed here."
        )

# ------------------------------------------------
# TAB 4 — RESEARCH ASSESSMENT
# ------------------------------------------------

with tab4:

    st.subheader("Retrospective Risk Screening")

    required_risk = {
        "month",
        "screening_flags_count",
        "screening_status"
    }

    if risk.empty or not required_risk.issubset(
        risk.columns
    ):
        st.warning(
            "Retrospective risk screening output "
            "is unavailable or has different columns."
        )

    else:
        screen = risk.copy()

        screen["month"] = screen["month"].astype(str)
        screen["screening_flags_count"] = (
            pd.to_numeric(
                screen["screening_flags_count"],
                errors="coerce"
            )
        )

        screen = screen.sort_values("month")

        screen_month = st.selectbox(
            "Historical Screening Month",
            screen["month"].tolist(),
            index=len(screen) - 1
        )

        r = screen[
            screen["month"] == screen_month
        ].iloc[0]

        st.metric(
            "Illustrative Stress Flags",
            number(
                r["screening_flags_count"], 0
            )
        )

        st.write(
            "**Historical Screening Status:**",
            r["screening_status"]
        )

        chart = screen[
            ["month", "screening_flags_count"]
        ].dropna()

        st.bar_chart(
            chart.set_index("month")
        )

        st.dataframe(
            screen,
            use_container_width=True,
            hide_index=True
        )

    st.divider()

    st.subheader("Research Interpretation")

    st.write(
        "Retrospective screening can describe periods "
        "of currency pressure and reserve depletion. "
        "However, retrospective signals do not establish "
        "that a crisis could have been predicted "
        "using information available at that time."
    )

    st.write(
        "The historical publication-aware replay "
        "remains a separate evidence-controlled process. "
        "This dashboard does not use unverified new "
        "draft observations as training data."
    )

    st.warning(
        "No validated crisis probability, "
        "forecast accuracy or false-alarm rate "
        "is established by this dashboard."
    )

st.divider()

st.caption(
    "SL-EWRIS Capstone | Unified monitoring prototype | "
    "Historical research data remain unchanged."
)
