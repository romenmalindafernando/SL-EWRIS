from pathlib import Path
import ast
import sqlite3
import subprocess
import sys
import re
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "software_release_checks"
OUT.mkdir(parents=True, exist_ok=True)

results = []

def check(name, passed, details):
    results.append((name, passed, details))
    label = "PASS" if passed else "CHECK"
    print(f"[{label}] {name}: {details}")

print("\n=== SL-EWRIS SOFTWARE READINESS ===\n")

# 1. Main application
app = ROOT / "app.py"
check(
    "Main Streamlit Application",
    app.is_file(),
    "app.py found" if app.is_file() else "app.py missing"
)

# 2. Python syntax
files = sorted(
    set(
        [app]
        + list((ROOT / "analysis").rglob("*.py"))
        + list((ROOT / "pages").rglob("*.py"))
    )
)

syntax_errors = []

for path in files:
    if not path.is_file():
        continue
    try:
        ast.parse(
            path.read_text(encoding="utf-8-sig"),
            filename=str(path)
        )
    except (SyntaxError, UnicodeError) as exc:
        syntax_errors.append(f"{path.name}: {exc}")

check(
    "Python Syntax",
    len(syntax_errors) == 0,
    f"{len(files)} files inspected; "
    f"{len(syntax_errors)} errors"
)

# 3. Required pages
required_pages = [
    "39_Monthly_Economic_Monitoring.py",
    "40_Saved_Monthly_Economic_Data.py",
    "41_Data_Verification.py",
    "42_Data_Quality_Dashboard.py",
    "43_Unified_Economic_Intelligence.py",
    "44_Preliminary_Risk_Score.py",
    "45_Risk_Threshold_Sensitivity.py",
    "46_Historical_Lead_Time_Evaluation.py",
    "47_Point_In_Time_Validation.py",
    "48_Historical_Data_Freshness.py",
    "51_Historical_Evidence_Coverage.py",
    "53_CBSL_Source_Progress_Tracker.py"
]

missing_pages = [
    name for name in required_pages
    if not (ROOT / "pages" / name).is_file()
]

check(
    "Dashboard Page Files",
    len(missing_pages) == 0,
    f"{len(required_pages) - len(missing_pages)}"
    f"/{len(required_pages)} present"
)

# 4. SQLite integrity (read only)
db = ROOT / "database" / "economic_risk.db"

db_tables = []
db_integrity = "Not checked"

if db.is_file():
    try:
        with sqlite3.connect(
            f"{db.resolve().as_uri()}?mode=ro",
            uri=True
        ) as con:
            db_integrity = con.execute(
                "PRAGMA quick_check"
            ).fetchone()[0]

            db_tables = [
                row[0] for row in con.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table'"
                )
            ]
    except sqlite3.Error as exc:
        db_integrity = str(exc)

check(
    "SQLite Integrity",
    db_integrity == "ok",
    f"Integrity: {db_integrity}"
)

check(
    "Historical Data Table",
    "economic_monthly" in db_tables,
    "economic_monthly exists"
    if "economic_monthly" in db_tables
    else "Historical table unavailable"
)

check(
    "Monthly Draft Storage",
    "monthly_economic_drafts" in db_tables,
    "Draft table exists"
    if "monthly_economic_drafts" in db_tables
    else "Draft table unavailable"
)

# 5. Risk-scoring engine
engine = ROOT / "analysis" / "preliminary_risk_score.py"

engine_result = "File missing"
engine_passed = False

if engine.is_file():
    try:
        result = subprocess.run(
            [sys.executable, str(engine)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30
        )
        engine_passed = result.returncode == 0
        engine_result = (
            result.stdout.strip()
            if engine_passed
            else (result.stderr or result.stdout)[-600:]
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        engine_result = str(exc)

check("Risk Engine Tests", engine_passed, engine_result)

# 6. Historical research outputs
historical = (
    ROOT / "outputs" / "cbsl_preparation"
    / "combined_external_review_2014_2025.csv"
)

check(
    "Historical External Dataset",
    historical.is_file(),
    "Dataset present" if historical.is_file()
    else "Dataset unavailable"
)

# 7. Git repository
git = subprocess.run(
    ["git", "rev-parse", "--is-inside-work-tree"],
    cwd=ROOT,
    capture_output=True,
    text=True
)

check(
    "Git Repository",
    git.returncode == 0
    and git.stdout.strip() == "true",
    "Git initialized"
    if git.returncode == 0 else "Git not initialized"
)

# 8. Essential .gitignore patterns
gitignore = ROOT / ".gitignore"

patterns = (
    gitignore.read_text(
        encoding="utf-8-sig"
    ).splitlines()
    if gitignore.is_file() else []
)

active_patterns = {
    line.strip()
    for line in patterns
    if line.strip() and not line.lstrip().startswith("#")
}

required_ignore = [
    ".venv/",
    "__pycache__/",
    "outputs/",
    "*.db",
    ".env"
]

missing_ignore = [
    item for item in required_ignore
    if item not in active_patterns
]

check(
    "Git Ignore Review",
    not missing_ignore,
    "Essential patterns present"
    if not missing_ignore else
    "Review missing patterns: " + ", ".join(missing_ignore)
)

# 9. Write report
passed = sum(item[1] for item in results)
total = len(results)

report = [
    "# SL-EWRIS Software Readiness Report",
    "",
    f"Generated: {datetime.now().isoformat(timespec='seconds')}",
    "",
    f"Checks passed: {passed}/{total}",
    "",
    "## Results",
    ""
]

for name, success, detail in results:
    report.append(
        f"- {'PASS' if success else 'CHECK'}: "
        f"{name} — {detail}"
    )

report.extend([
    "",
    "## Research Status",
    "",
    "- Historical risk screening: exploratory",
    "- Manual entry workflow: requires UI testing",
    "- Publication-aware verification: incomplete",
    "- Crisis prediction accuracy: not validated",
    "- Future crisis probability: not established",
    "",
    "## Release Notes",
    "",
    "Passing syntax and smoke tests does not guarantee "
    "that every Streamlit page works correctly.",
    "Review secrets and staged files before GitHub push.",
])

if syntax_errors:
    report.extend([
        "",
        "## Syntax Errors",
        *syntax_errors
    ])

destination = OUT / (
    "readiness_" + datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    ) + ".md"
)

destination.write_text(
    "\n".join(report),
    encoding="utf-8"
)

print("\n================================")
print(f"CHECKS PASSED: {passed}/{total}")
print("================================")
print("Report saved:", destination)
print("\nNo SQLite records modified.")
print("No historical files modified.")
print("No Git commits or pushes performed.")
