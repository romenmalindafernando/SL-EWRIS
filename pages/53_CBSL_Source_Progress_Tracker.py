from pathlib import Path
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
import os
import shutil
import tempfile

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]

FOLDER = ROOT / "outputs" / "external_risk_analysis"

QUEUE = FOLDER / "cbsl_source_collection_queue_v1.csv"
PROGRESS = FOLDER / "cbsl_source_collection_progress.csv"
BACKUPS = FOLDER / "progress_backups"

STAGES = [
    "Not started",
    "Source found",
    "Value checked",
    "Definition checked",
    "Ready for independent audit"
]

FIELDS = [
    "task_id",
    "research_status",
    "exact_source_url",
    "report_publication_date",
    "historically_published_value",
    "published_unit",
    "source_page_or_table",
    "definition_checked",
    "review_notes",
    "updated_at"
]

st.set_page_config(
    page_title="SL-EWRIS | CBSL Research Tracker",
    page_icon="📚",
    layout="wide"
)

st.title("CBSL Historical Source Collection Tracker")

st.caption(
    "SL-EWRIS | Historical Evidence Research Management"
)

st.warning(
    "Research tracking only. Progress status does not "
    "constitute independent source verification. "
    "The historical release ledger and SQLite database "
    "are not modified."
)


def valid_cbsl_url(value):
    try:
        parsed = urlparse(str(value).strip())
        host = (parsed.hostname or "").lower()

        return (
            parsed.scheme == "https"
            and (
                host == "cbsl.gov.lk"
                or host.endswith(".cbsl.gov.lk")
            )
        )
    except ValueError:
        return False


def task_identifier(month, indicator):
    return f"{month}|{indicator}"


def load_queue():
    if not QUEUE.is_file():
        raise FileNotFoundError(
            "Step 52 source collection queue not found."
        )

    data = pd.read_csv(
        QUEUE,
        dtype=str,
        keep_default_na=False
    )

    required = {
        "priority_rank",
        "priority",
        "reporting_month",
        "indicator",
        "research_start_url"
    }

    missing = required - set(data.columns)

    if missing:
        raise ValueError(
            f"Missing queue columns: {sorted(missing)}"
        )

    data["task_id"] = data.apply(
        lambda r: task_identifier(
            r["reporting_month"],
            r["indicator"]
        ),
        axis=1
    )

    if data["task_id"].duplicated().any():
        raise ValueError(
            "Duplicate source collection tasks detected."
        )

    return data


def load_progress():

    if not PROGRESS.exists():
        return pd.DataFrame(columns=FIELDS)

    data = pd.read_csv(
        PROGRESS,
        dtype=str,
        keep_default_na=False
    )

    missing = set(FIELDS) - set(data.columns)

    if missing:
        raise ValueError(
            f"Progress file missing columns: {sorted(missing)}"
        )

    if data["task_id"].duplicated().any():
        raise ValueError("Duplicate progress records found.")

    return data[FIELDS].copy()


def save_progress(data):
    """
    Create a backup, then atomically replace the
    progress CSV. Original collection queue unchanged.
    """

    FOLDER.mkdir(parents=True, exist_ok=True)

    if PROGRESS.exists():
        BACKUPS.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now(
            timezone.utc
        ).strftime("%Y%m%dT%H%M%S%fZ")

        backup = BACKUPS / f"progress_{stamp}.csv"
        shutil.copy2(PROGRESS, backup)

    fd, temporary = tempfile.mkstemp(
        prefix="progress_",
        suffix=".tmp",
        dir=FOLDER
    )

    try:
        with os.fdopen(
            fd, "w", encoding="utf-8-sig",
            newline=""
        ) as file:
            data[FIELDS].to_csv(
                file, index=False
            )

        os.replace(temporary, PROGRESS)

    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


try:
    queue = load_queue()
    saved = load_progress()

except (FileNotFoundError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

unknown_ids = (
    set(saved["task_id"]) - set(queue["task_id"])
)

if unknown_ids:
    st.error(
        "Progress file contains tasks not present "
        "in the original queue. Reconcile the files "
        "before updating."
    )
    st.stop()

progress_lookup = {
    r["task_id"]: r.to_dict()
    for _, r in saved.iterrows()
}

records = []

for _, task in queue.iterrows():

    task_id = task["task_id"]
    existing = progress_lookup.get(task_id, {})

    records.append({
        **task.to_dict(),
        **{
            field: existing.get(field, "")
            for field in FIELDS
            if field != "task_id"
        },
        "research_status": existing.get(
            "research_status", "Not started"
        ) or "Not started"
    })

tracker = pd.DataFrame(records)

if not tracker["research_status"].isin(STAGES).all():
    st.error(
        "Unknown research status found in progress file."
    )
    st.stop()

st.subheader("1. Overall Research Progress")

total = len(tracker)

started = int(
    (tracker["research_status"] != "Not started").sum()
)

ready = int(
    (
        tracker["research_status"]
        == "Ready for independent audit"
    ).sum()
)

not_started = total - started

a, b, c, d = st.columns(4)

a.metric("Total Research Tasks", total)
b.metric("Tasks Started", started)
c.metric("Not Started", not_started)
d.metric("Ready for Audit", ready)

progress_ratio = started / total if total else 0

st.progress(progress_ratio)

st.caption(
    f"Research activity started for "
    f"{progress_ratio * 100:.1f}% of queued tasks. "
    "This is not verified evidence coverage."
)

st.divider()

st.subheader("2. Source Collection Queue")

priority_filter = st.selectbox(
    "Priority",
    ["All", "P1", "P2", "P3"]
)

status_filter = st.selectbox(
    "Research Status",
    ["All"] + STAGES
)

filtered = tracker.copy()

if priority_filter != "All":
    filtered = filtered[
        filtered["priority"].str.startswith(
            priority_filter
        )
    ]

if status_filter != "All":
    filtered = filtered[
        filtered["research_status"] == status_filter
    ]

st.dataframe(
    filtered[
        [
            "priority",
            "reporting_month",
            "indicator",
            "research_status",
            "exact_source_url",
            "updated_at"
        ]
    ],
    use_container_width=True,
    hide_index=True
)

st.divider()

st.subheader("3. Update a Research Task")

if filtered.empty:
    st.info("No tasks match the selected filters.")
    st.stop()

options = filtered["task_id"].tolist()

selected_id = st.selectbox(
    "Choose Reporting Month and Indicator",
    options
)

task = tracker.loc[
    tracker["task_id"] == selected_id
].iloc[0]

st.write("**Priority:**", task["priority"])
st.write("**Reporting Month:**", task["reporting_month"])
st.write("**Indicator:**", task["indicator"])

st.markdown(
    f"[Open CBSL Research Archive]"
    f"({task['research_start_url']})"
)

current_status = task["research_status"]

with st.form(f"research_form_{selected_id}"):

    status = st.selectbox(
        "Research Progress Status",
        STAGES,
        index=STAGES.index(current_status)
    )

    source_url = st.text_input(
        "Exact Official CBSL Source URL",
        value=task["exact_source_url"],
        placeholder="https://www.cbsl.gov.lk/..."
    )

    publication_date = st.text_input(
        "Report Publication Date (YYYY-MM-DD)",
        value=task["report_publication_date"],
        placeholder="2021-05-18"
    )

    published_value = st.text_input(
        "Historically Published Value",
        value=task["historically_published_value"],
        placeholder="Enter exact reported number"
    )

    unit = st.text_input(
        "Published Unit",
        value=task["published_unit"],
        placeholder="USD billions / LKR per USD"
    )

    page = st.text_input(
        "Report Page / Table / Section",
        value=task["source_page_or_table"]
    )

    definition = st.checkbox(
        "Indicator definition and unit manually checked",
        value=(
            task["definition_checked"] == "Yes"
        )
    )

    notes = st.text_area(
        "Research Notes",
        value=task["review_notes"],
        placeholder=(
            "Record source details, revisions, "
            "precision and unresolved questions."
        )
    )

    submitted = st.form_submit_button(
        "Save Research Progress",
        type="primary"
    )

if submitted:

    errors = []

    if status != "Not started":
        if not valid_cbsl_url(source_url):
            errors.append(
                "A valid official CBSL HTTPS "
                "source URL is required."
            )

    if publication_date.strip():
        try:
            release_date = date.fromisoformat(
                publication_date.strip()
            )

            observation_start = date.fromisoformat(
                task["reporting_month"] + "-01"
            )

            if release_date < observation_start:
                errors.append(
                    "Report date cannot be before "
                    "the observation month."
                )

            if release_date > date.today():
                errors.append(
                    "A future publication date "
                    "cannot be used as existing evidence."
                )

        except ValueError:
            errors.append(
                "Publication date must use YYYY-MM-DD."
            )

    if status in STAGES[2:]:

        if not published_value.strip():
            errors.append(
                "The published value is required."
            )

        else:
            try:
                value = Decimal(
                    published_value.strip()
                )

                if not value.is_finite() or value <= 0:
                    errors.append(
                        "Published value must be positive "
                        "and finite for these indicators."
                    )

            except InvalidOperation:
                errors.append(
                    "Published value must be numeric."
                )

    if status in STAGES[3:]:

        if not unit.strip():
            errors.append(
                "Published unit is required."
            )

        if not definition:
            errors.append(
                "Indicator definition must be checked."
            )

    if status == "Ready for independent audit":

        if not publication_date.strip():
            errors.append(
                "Publication date is required."
            )

        if not page.strip():
            errors.append(
                "Source page/table is required."
            )

        if not notes.strip():
            errors.append(
                "Research notes are required."
            )

    if errors:
        for error in errors:
            st.error(error)

    else:
        record = {
            "task_id": selected_id,
            "research_status": status,
            "exact_source_url": source_url.strip(),
            "report_publication_date":
                publication_date.strip(),
            "historically_published_value":
                published_value.strip(),
            "published_unit": unit.strip(),
            "source_page_or_table": page.strip(),
            "definition_checked":
                "Yes" if definition else "No",
            "review_notes": notes.strip(),
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(timespec="seconds")
        }

        updated = saved.copy()

        if selected_id in set(updated["task_id"]):
            mask = updated["task_id"] == selected_id

            for field, value in record.items():
                updated.loc[mask, field] = value

        else:
            updated = pd.concat(
                [
                    updated,
                    pd.DataFrame([record])
                ],
                ignore_index=True
            )

        try:
            save_progress(updated)

            st.success(
                "Research progress saved. "
                "Original source queue unchanged."
            )

            st.rerun()

        except OSError as exc:
            st.error(f"Unable to save progress: {exc}")

st.divider()

st.subheader("4. Download Research Progress")

export = tracker.to_csv(
    index=False
).encode("utf-8-sig")

st.download_button(
    "Download Source Collection Progress CSV",
    data=export,
    file_name="sl_ewris_source_collection_progress.csv",
    mime="text/csv"
)

st.caption(
    "Single-user research prototype. Do not edit "
    "the same progress CSV concurrently from multiple "
    "sessions. This page does not automatically "
    "approve historical observations."
)
