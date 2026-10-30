from pathlib import Path
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
import sqlite3

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]

LEDGER = (
    ROOT / "outputs/external_risk_analysis"
    / "historical_release_ledger_v1.csv"
)

st.set_page_config(
    page_title="SL-EWRIS | Point-in-Time Validation",
    page_icon="🕒",
    layout="wide"
)

st.title("Point-in-Time Economic Warning Validation")

st.warning(
    "Research prototype. This page uses records marked "
    "Verified in a manually maintained evidence ledger. "
    "It cannot independently authenticate source documents."
)

st.caption(
    "Historical decisions must exclude observations "
    "published after the selected decision date."
)

EXPECTED_UNITS = {
    "fx_reserves_usd_bn": "USD billions",
    "usd_lkr": "LKR per USD"
}

REQUIRED = {
    "month",
    "indicator",
    "published_value",
    "unit",
    "publication_date",
    "source_url",
    "verification_status"
}


def official_url(value):
    try:
        parsed = urlparse(str(value).strip())

        host = (parsed.hostname or "").lower()

        return (
            parsed.scheme == "https"
            and (
                host == "cbsl.gov.lk"
                or host.endswith(".cbsl.gov.lk")
                or host == "statistics.gov.lk"
                or host.endswith(".statistics.gov.lk")
            )
        )
    except ValueError:
        return False


def validate_row(row):
    """
    Basic eligibility check, NOT independent
    confirmation of document authenticity.
    """
    indicator = str(row["indicator"]).strip()

    if indicator not in EXPECTED_UNITS:
        return None, "Unknown indicator"

    if str(row["verification_status"]).strip() != "Verified":
        return None, "Not marked Verified"

    if str(row["unit"]).strip() != EXPECTED_UNITS[indicator]:
        return None, "Unit mismatch"

    if not official_url(row["source_url"]):
        return None, "Official URL format missing"

    try:
        period = pd.Period(
            str(row["month"]).strip(),
            freq="M"
        )

        published = date.fromisoformat(
            str(row["publication_date"]).strip()
        )

        value = Decimal(
            str(row["published_value"]).strip()
        )

    except (ValueError, TypeError, InvalidOperation):
        return None, "Invalid date or numeric value"

    if not value.is_finite() or value <= 0:
        return None, "Non-positive or invalid value"

    if published < period.start_time.date():
        return None, "Publication predates reporting month"

    return {
        "month": str(period),
        "indicator": indicator,
        "published_value": float(value),
        "publication_date": published,
        "source_url": str(row["source_url"]).strip(),
        "unit": str(row["unit"]).strip()
    }, "Eligible ledger record"


if not LEDGER.is_file():
    st.error(
        "Historical vintage ledger is missing. "
        "Run Step 37 --init first."
    )
    st.stop()

raw = pd.read_csv(
    LEDGER,
    dtype=str,
    keep_default_na=False
)

if not REQUIRED.issubset(raw.columns):
    st.error(
        "Ledger is missing these columns: "
        f"{sorted(REQUIRED - set(raw.columns))}"
    )
    st.stop()

st.subheader("1. Historical Evidence Readiness")

accepted = []
audit = []

for _, row in raw.iterrows():

    record, reason = validate_row(row)

    audit.append({
        "month": row["month"],
        "indicator": row["indicator"],
        "status": reason
    })

    if record is not None:
        accepted.append(record)

a, b, c = st.columns(3)

a.metric("Ledger Records", len(raw))
b.metric("Eligible Records", len(accepted))
c.metric("Pending / Rejected", len(raw) - len(accepted))

st.caption(
    "Eligible means that recorded evidence passes "
    "structural checks and is marked Verified. "
    "It does not establish independent authenticity."
)

with st.expander("View Evidence Audit"):
    st.dataframe(
        pd.DataFrame(audit),
        use_container_width=True,
        hide_index=True
    )

st.divider()

st.subheader("2. Select Historical Decision Date")

decision = st.date_input(
    "Decision Date",
    value=date(2022, 3, 31),
    min_value=date(2020, 1, 1),
    max_value=date(2025, 12, 31)
)

currency_threshold = st.slider(
    "Currency Pressure Threshold — 3 months (%)",
    min_value=1,
    max_value=30,
    value=10
)

reserve_threshold = st.slider(
    "Reserve Depletion Threshold — 3 months (%)",
    min_value=1,
    max_value=50,
    value=20
)

# Do not select any release that occurred
# AFTER the historical decision date.
eligible_at_date = [
    row for row in accepted
    if row["publication_date"] <= decision
    and pd.Period(row["month"], freq="M")
        <= pd.Period(decision, freq="M")
]

# For each reporting month and indicator, retain
# the most recent eligible published vintage.
vintage_map = {}

for row in sorted(
    eligible_at_date,
    key=lambda r: (
        r["publication_date"],
        r["month"]
    )
):
    key = (row["month"], row["indicator"])

    if (
        key in vintage_map
        and vintage_map[key]["publication_date"]
        == row["publication_date"]
        and vintage_map[key]["published_value"]
        != row["published_value"]
    ):
        st.error(
            "Conflicting releases for the same indicator, "
            "month and publication date. Resolve the "
            "ledger conflict before using this analysis."
        )
        st.stop()

    vintage_map[key] = row

st.subheader("3. Information Available on Decision Date")

latest_by_indicator = {}

for indicator in EXPECTED_UNITS:

    candidates = [
        row for row in vintage_map.values()
        if row["indicator"] == indicator
    ]

    if candidates:
        latest_by_indicator[indicator] = max(
            candidates,
            key=lambda r: (
                r["month"],
                r["publication_date"]
            )
        )

snapshot_rows = []

for indicator in EXPECTED_UNITS:

    record = latest_by_indicator.get(indicator)

    snapshot_rows.append({
        "Indicator": indicator,
        "Latest Available Month": (
            record["month"] if record else None
        ),
        "Published Value": (
            record["published_value"] if record else None
        ),
        "Publication Date": (
            str(record["publication_date"])
            if record else None
        ),
        "Status": (
            "Eligible recorded evidence"
            if record else "Unavailable"
        )
    })

st.dataframe(
    pd.DataFrame(snapshot_rows),
    use_container_width=True,
    hide_index=True
)

st.divider()
st.subheader("4. Point-in-Time Economic Stress Analysis")


def change_3m(indicator):
    current = latest_by_indicator.get(indicator)

    if current is None:
        return None, "No eligible current observation"

    current_period = pd.Period(
        current["month"], freq="M"
    )

    previous_period = str(current_period - 3)

    previous = vintage_map.get(
        (previous_period, indicator)
    )

    if previous is None:
        return (
            None,
            "No eligible observation exactly "
            "three months earlier"
        )

    old = previous["published_value"]
    new = current["published_value"]

    if old <= 0:
        return None, "Invalid comparison value"

    result = (new / old - 1) * 100

    return result, "Calculated using eligible vintages"


fx_change, fx_note = change_3m("usd_lkr")
reserve_change, reserve_note = change_3m(
    "fx_reserves_usd_bn"
)

a, b = st.columns(2)

a.metric(
    "Three-Month USD/LKR Change",
    (
        f"{fx_change:.2f}%"
        if fx_change is not None
        else "Unavailable"
    )
)

b.metric(
    "Three-Month Reserve Change",
    (
        f"{reserve_change:.2f}%"
        if reserve_change is not None
        else "Unavailable"
    )
)

st.caption(f"Currency: {fx_note}")
st.caption(f"Reserves: {reserve_note}")

currency_flag = (
    fx_change >= currency_threshold
    if fx_change is not None else None
)

reserve_flag = (
    reserve_change <= -reserve_threshold
    if reserve_change is not None else None
)

signal_rows = [
    {
        "Indicator": "Currency Pressure",
        "Threshold Exceeded": currency_flag
    },
    {
        "Indicator": "Reserve Pressure",
        "Threshold Exceeded": reserve_flag
    }
]

st.dataframe(
    pd.DataFrame(signal_rows),
    use_container_width=True,
    hide_index=True
)

available = sum(
    flag is not None
    for flag in (currency_flag, reserve_flag)
)

triggered = sum(
    flag is True
    for flag in (currency_flag, reserve_flag)
)

if available < 2:
    st.warning(
        "Insufficient verified historical coverage "
        "for a complete external-sector screening."
    )
else:
    st.metric(
        "Triggered External Stress Signals",
        f"{triggered} / 2"
    )

    if triggered:
        st.warning(
            "Historical stress threshold(s) exceeded."
        )
    else:
        st.info(
            "Neither selected threshold was exceeded "
            "by these two indicators."
        )

st.divider()
st.subheader("5. Research Interpretation")

st.write(
    "The dashboard selects only ledger records "
    "whose recorded publication dates are on or "
    "before the selected decision date."
)

st.write(
    "This page is limited to the two external-sector "
    "indicators. Inflation and wage series are "
    "not included in this historical vintage replay."
)

st.warning(
    "Even a complete score does not prove that a "
    "financial crisis was predicted. The evidence "
    "ledger must be independently audited, historical "
    "coverage expanded, and the methodology tested "
    "against predefined crisis events."
)

st.caption(
    "Read-only historical research dashboard. "
    "SQLite and source evidence files remain unchanged."
)
