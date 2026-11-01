from pathlib import Path
import sys
import csv

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))

from analysis.build_evidence_coverage import build_coverage

OUT = ROOT / "outputs" / "external_risk_analysis"
QUEUE = OUT / "cbsl_source_collection_queue_v1.csv"

ARCHIVES = {
    "fx_reserves_usd_bn":
        "https://www.cbsl.gov.lk/en/press/"
        "press-releases/external-sector-performance",
    "usd_lkr":
        "https://www.cbsl.gov.lk/statistics/"
        "economic-indicators/monthly-indicators"
}

LABELS = {
    "fx_reserves_usd_bn":
        "Gross Official Reserve Assets - USD billions",
    "usd_lkr":
        "Monthly Average USD/LKR - LKR per USD"
}


def priority(month):

    if "2021-01" <= month <= "2022-03":
        return 1, "P1 - Pre-crisis evidence"

    if "2020-10" <= month <= "2020-12":
        return 2, "P2 - Three-month baselines"

    return 3, "P3 - Supporting historical coverage"


def main():

    if QUEUE.exists():
        raise FileExistsError(
            "Collection queue already exists. "
            "Existing work has been preserved."
        )

    matrix, details = build_coverage()

    tasks = []

    for record in details:

        if record["evidence_count"] > 0:
            continue

        month = record["month"]
        indicator = record["indicator"]

        rank, priority_name = priority(month)

        tasks.append({
            "priority_rank": rank,
            "priority": priority_name,
            "reporting_month": month,
            "indicator": indicator,
            "required_definition": LABELS[indicator],
            "research_start_url": ARCHIVES[indicator],
            "exact_source_url": "",
            "report_publication_date": "",
            "historically_published_value": "",
            "published_unit": "",
            "source_page_or_table": "",
            "definition_checked": "No",
            "publication_date_checked": "No",
            "retrospective_value_checked": "No",
            "first_release_checked": "No",
            "research_status": "Not started",
            "review_notes": ""
        })

    tasks.sort(
        key=lambda r: (
            r["priority_rank"],
            r["reporting_month"],
            r["indicator"]
        )
    )

    OUT.mkdir(parents=True, exist_ok=True)

    columns = [
        "priority_rank",
        "priority",
        "reporting_month",
        "indicator",
        "required_definition",
        "research_start_url",
        "exact_source_url",
        "report_publication_date",
        "historically_published_value",
        "published_unit",
        "source_page_or_table",
        "definition_checked",
        "publication_date_checked",
        "retrospective_value_checked",
        "first_release_checked",
        "research_status",
        "review_notes"
    ]

    with QUEUE.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file, fieldnames=columns
        )

        writer.writeheader()
        writer.writerows(tasks)

    print("\n=== SL-EWRIS SOURCE COLLECTION PLAN ===")
    print("Historical months:", len(matrix))
    print("Total indicator-month records:", len(details))
    print("Remaining source research tasks:", len(tasks))

    for rank in (1, 2, 3):
        count = sum(
            t["priority_rank"] == rank
            for t in tasks
        )
        print(f"Priority P{rank} tasks:", count)

    print("\n=== FIRST 12 TASKS ===")

    for task in tasks[:12]:
        print(
            task["priority"],
            "|", task["reporting_month"],
            "|", task["indicator"]
        )

    print("\nSaved:", QUEUE)
    print("No publication dates or values invented.")
    print("Original evidence files unchanged.")
    print("PostgreSQL database unchanged.")


if __name__ == "__main__":
    main()
