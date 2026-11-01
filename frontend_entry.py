"""Streamlit monthly-entry form shared by the custom cloud frontend."""

from __future__ import annotations

from datetime import date
import math
import re

import streamlit as st

from database import connect_database, create_tables
from monthly_entry import create_source_log, derived_updates, latest_ccpi_base


FIELDS = {
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


def _validate_month(value: str) -> None:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("Month must use YYYY-MM format.")
    year, month = map(int, value.split("-"))
    if year < 2014 or (year, month) >= (date.today().year, date.today().month):
        raise ValueError("Enter a completed month from January 2014 onward.")


def _months_between(start: str | None, end: str) -> list[str]:
    if not start or end <= start:
        return []
    year, month = map(int, start.split("-"))
    result: list[str] = []
    while True:
        month += 1
        if month == 13:
            year += 1
            month = 1
        candidate = f"{year:04d}-{month:02d}"
        if candidate >= end:
            return result
        result.append(candidate)


def save_observation(
    month: str,
    field: str,
    value: float,
    publication_date: date,
    source_name: str,
    source_url: str | None,
    base: str | None,
    allow_update: bool,
    allow_placeholders: bool,
) -> str:
    _validate_month(month)
    if not math.isfinite(value):
        raise ValueError("The value must be finite.")
    if publication_date < date.fromisoformat(month + "-01") or publication_date > date.today():
        raise ValueError("Publication date must not precede the observation month or be in the future.")
    if not source_name.strip():
        raise ValueError("Specify the official publication or source name.")
    if field.startswith("ccpi_") and base not in {"2013=100", "2021=100"}:
        raise ValueError("Select a known CCPI published base.")

    with connect_database() as conn:
        create_tables(conn)
        create_source_log(conn)
        current = conn.execute(
            f'SELECT "{field}", ccpi_published_base FROM economic_monthly WHERE month = ?',
            (month,),
        ).fetchone()
        last = conn.execute("SELECT MAX(month) FROM economic_monthly").fetchone()[0]
        if current is None and last and month < last:
            raise ValueError("An internal historical month is missing.")
        gaps = _months_between(last, month)
        if gaps and not allow_placeholders:
            raise ValueError("Authorize blank placeholders before adding a later month.")
        old_value = current[0] if current else None
        if old_value is not None and math.isclose(float(old_value), value, abs_tol=1e-10, rel_tol=0):
            return "No change: this value is already stored."
        if old_value is not None and not allow_update:
            raise ValueError("Existing value found. Authorize this source revision.")
        if field.startswith("ccpi_") and current and current[1] and current[1] != base:
            raise ValueError("CCPI base differs from the stored base.")

        for gap in gaps:
            conn.execute(
                """INSERT INTO economic_monthly(month, source, record_origin, notes)
                   VALUES (?, 'Awaiting official source data',
                           'missing_month_placeholder',
                           'Blank placeholder: no reported values')
                   ON CONFLICT(month) DO NOTHING""",
                (gap,),
            )
        conn.execute(
            """INSERT INTO economic_monthly(month, source, record_origin, notes)
               VALUES (?, 'Monthly manual entry; see indicator_source_log',
                       'manual_entry', 'Official source details in indicator_source_log')
               ON CONFLICT(month) DO NOTHING""",
            (month,),
        )
        changes = {field: value}
        if field.startswith("ccpi_"):
            changes["ccpi_published_base"] = base
        if month > "2025-12":
            changes.update(derived_updates(conn, month, field, value, base, False))
        assignments = ", ".join(f'"{column}" = ?' for column in changes)
        conn.execute(
            f'UPDATE economic_monthly SET {assignments}, updated_at = CURRENT_TIMESTAMP, '
            "record_origin = 'manual_entry' WHERE month = ?",
            [*changes.values(), month],
        )
        conn.execute(
            """INSERT INTO indicator_source_log
               (month, indicator, old_value, new_value, publication_date, source_name, source_url)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                month,
                field,
                str(old_value) if old_value is not None else None,
                str(value),
                publication_date.isoformat(),
                source_name.strip(),
                source_url.strip() if source_url else None,
            ),
        )
    return f"Saved {field} for {month}. Audit record created."


def render_monthly_entry() -> None:
    st.caption("Enter published observations only. Revisions require explicit confirmation and are audited.")
    with st.form("cloud_monthly_entry"):
        month = st.text_input("Observation month", placeholder="YYYY-MM")
        label = st.selectbox("Indicator", list(FIELDS))
        value = st.number_input("Published numeric value", value=0.0, format="%.6f")
        publication_date = st.date_input("Official publication date", value=date.today())
        source_name = st.text_input("Official source/document")
        source_url = st.text_input("Official source URL (optional)")
        base = st.selectbox("CCPI published base", ["Not applicable", "2013=100", "2021=100"])
        allow_update = st.checkbox("Authorize a source revision", value=False)
        allow_placeholders = st.checkbox("Authorize blank preceding-month placeholders", value=False)
        submitted = st.form_submit_button("Save audited observation", type="primary")
    if not submitted:
        return
    field, _positive = FIELDS[label]
    try:
        result = save_observation(
            month,
            field,
            value,
            publication_date,
            source_name,
            source_url or None,
            None if base == "Not applicable" else base,
            allow_update,
            allow_placeholders,
        )
    except (ValueError, TypeError) as error:
        st.error(str(error))
    else:
        st.success(result)
        st.cache_data.clear()
