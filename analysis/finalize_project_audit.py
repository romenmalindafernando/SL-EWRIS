from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import datetime
from urllib.parse import urlparse
import csv
import psycopg
from database import connect_database
import py_compile
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs" / "external_risk_analysis"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = ROOT / "outputs" / "project_finalization" / STAMP

QUEUE = BASE / "cbsl_source_collection_queue_v1.csv"
PROGRESS = BASE / "cbsl_source_collection_progress.csv"
LEDGER = BASE / "historical_release_ledger_v1.csv"
REGISTER = BASE / "publication_evidence_register_2020_2022.csv"

OUT.mkdir(parents=True, exist_ok=False)


def load_csv(path):
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def official_url(value):
    try:
        parsed = urlparse(value.strip())
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and (
            host == "cbsl.gov.lk"
            or host.endswith(".cbsl.gov.lk")
            or host == "statistics.gov.lk"
            or host.endswith(".statistics.gov.lk")
        )
    except (ValueError, AttributeError):
        return False


queue = load_csv(QUEUE)
progress = load_csv(PROGRESS)
ledger = load_csv(LEDGER)
register = load_csv(REGISTER)

progress_lookup = {
    r["task_id"]: r
    for r in progress
    if r.get("task_id")
}

audit_rows = []

for task in queue:
    task_id = (
        task["reporting_month"]
        + "|"
        + task["indicator"]
    )
    record = progress_lookup.get(task_id, {})
    status = record.get("research_status", "Not started")

    missing = []

    if not official_url(
        record.get("exact_source_url", "")
    ):
        missing.append("Official URL")

    date_text = record.get("report_publication_date", "")
    try:
        published = datetime.strptime(
            date_text, "%Y-%m-%d"
        ).date()
        observed = datetime.strptime(
            task["reporting_month"] + "-01",
            "%Y-%m-%d"
        ).date()
        if published < observed:
            missing.append("Valid publication chronology")
    except ValueError:
        missing.append("Publication date")

    try:
        from decimal import Decimal
        value = Decimal(
            record.get("historically_published_value", "")
        )
        if not value.is_finite() or value <= 0:
            missing.append("Valid published value")
    except Exception:
        missing.append("Published value")

    expected_unit = {
        "usd_lkr": "LKR per USD",
        "fx_reserves_usd_bn": "USD billions"
    }.get(task["indicator"])

    if record.get("published_unit", "") != expected_unit:
        missing.append("Exact unit")

    if not record.get("source_page_or_table", "").strip():
        missing.append("Page or table reference")

    if record.get("definition_checked", "") != "Yes":
        missing.append("Definition check")

    if not record.get("review_notes", "").strip():
        missing.append("Research notes")

    ready = (
        status == "Ready for independent audit"
        and not missing
    )

    audit_rows.append({
        "task_id": task_id,
        "priority": task["priority"],
        "reporting_month": task["reporting_month"],
        "indicator": task["indicator"],
        "research_status": status,
        "audit_package_complete": "Yes" if ready else "No",
        "missing_requirements": "; ".join(missing),
        "source_url": record.get("exact_source_url", ""),
        "publication_date": date_text,
        "published_value": record.get(
            "historically_published_value", ""
        ),
        "published_unit": record.get("published_unit", ""),
        "source_page_or_table": record.get(
            "source_page_or_table", ""
        ),
        "review_notes": record.get("review_notes", ""),
        "independently_verified": "No"
    })


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(rows)


write_csv(
    OUT / "complete_source_audit.csv",
    audit_rows
)

ready_records = [
    r for r in audit_rows
    if r["audit_package_complete"] == "Yes"
]

write_csv(
    OUT / "ready_for_independent_audit.csv",
    ready_records
)

# Inspect existing PostgreSQL database without changing data.
db_status = "Missing"
draft_count = "Unknown"
review_count = "Unknown"

try:
    with connect_database() as con:
            tables = {
                r[0] for r in con.execute(
                    "SELECT tablename AS name FROM pg_catalog.pg_tables "
                    "WHERE schemaname = current_schema()"
                )
            }

            db_status = "Available"

            if "monthly_economic_drafts" in tables:
                draft_count = con.execute(
                    "SELECT COUNT(*) "
                    "FROM monthly_economic_drafts"
                ).fetchone()[0]

            if "monthly_indicator_reviews" in tables:
                review_count = con.execute(
                    "SELECT COUNT(*) "
                    "FROM monthly_indicator_reviews"
                ).fetchone()[0]

except psycopg.Error as exc:
    db_status = f"Read error: {exc}"

# Compile project code without generating __pycache__.
python_files = sorted(
    list((ROOT / "analysis").rglob("*.py"))
    + list((ROOT / "pages").rglob("*.py"))
    + [ROOT / "app.py"]
)

syntax_errors = []

for path in python_files:
    if not path.is_file():
        continue

    try:
        import ast
        ast.parse(
            path.read_text(encoding="utf-8-sig"),
            filename=str(path)
        )
    except (SyntaxError, UnicodeError) as exc:
        syntax_errors.append(f"{path.name}: {exc}")

# Execute existing risk-engine smoke tests.
engine = ROOT / "analysis" / "preliminary_risk_score.py"
test_result = "Not run"

if engine.exists():
    completed = subprocess.run(
        [sys.executable, str(engine)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=ROOT
    )

    test_result = (
        "Passed" if completed.returncode == 0
        else "Failed: "
        + (completed.stderr or completed.stdout)[-1200:]
    )

ledger_verified = sum(
    r.get("verification_status", "").strip() == "Verified"
    for r in ledger
)

report = f"""# SL-EWRIS — PROJECT FINALIZATION AUDIT

Generated: {datetime.now().isoformat(timespec="seconds")}

## 1. Software Readiness

Python files inspected: {len(python_files)}
Python syntax errors: {len(syntax_errors)}
Preliminary risk-engine smoke tests: {test_result}
Existing PostgreSQL database: {db_status}

Saved monthly drafts: {draft_count}
Manual review records: {review_count}

## 2. Historical Evidence Readiness

Evidence register rows: {len(register)}
Historical vintage ledger rows: {len(ledger)}
Ledger rows marked Verified: {ledger_verified}

Outstanding research queue tasks: {len(queue)}
Tasks with saved progress: {len(progress)}
Audit packages complete: {len(ready_records)}

IMPORTANT:
Audit package complete does not mean independently verified.
Ledger labels have not been independently authenticated by this script.

## 3. Current Scientific Limitations

- The retrospective stress screening is exploratory.
- Historical publication dates and data vintages are incomplete.
- We do not yet have defensible point-in-time predictive accuracy.
- No validated financial-crisis probability model exists.
- Risk thresholds and weights need independent validation.
- Saved user-entered drafts must not automatically become
  official historical observations.

## 4. Remaining Work Before Academic Submission

1. Verify source definitions, values, dates, and data vintages.
2. Establish crisis event labels and evaluation windows.
3. Perform time-aware out-of-sample validation.
4. Evaluate false alarms, missed events, and lead times.
5. Test Streamlit pages through actual user interactions.
6. Prepare methodology, results, limitations, and references.
7. Review files for secrets before GitHub push.

## 5. Audit Conclusion

Development prototype: assembled for further testing.
Research verification: incomplete.
Validated crisis predictor: not established.
"""

if syntax_errors:
    report += "\n## Python Syntax Errors\n\n"
    report += "\n".join(syntax_errors)

report_path = OUT / "PROJECT_READINESS_REPORT.md"

report_path.write_text(
    report,
    encoding="utf-8"
)

print("\n=== SL-EWRIS FINALIZATION AUDIT ===")
print("Python files inspected:", len(python_files))
print("Syntax errors:", len(syntax_errors))
print("Risk engine tests:", test_result)
print("Database:", db_status)
print("Evidence register records:", len(register))
print("Source collection tasks:", len(queue))
print("Audit packages complete:", len(ready_records))
print("Historical ledger marked Verified:", ledger_verified)
print("\nReports saved:", OUT)
print("PostgreSQL and original research files unchanged.")
print("No records automatically approved.")
