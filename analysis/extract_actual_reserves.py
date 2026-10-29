
from pathlib import Path
import argparse
import re
import sys

import pandas as pd
from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT / "data" / "cbsl_downloads"
    / "table2.15.2_20260930_e.xlsx"
)

OUTPUT = ROOT / "outputs" / "cbsl_extraction"
OUTPUT.mkdir(parents=True, exist_ok=True)

CANDIDATES = OUTPUT / "reserve_cell_candidates.csv"
MAPPING = OUTPUT / "verified_reserve_cell_mapping.csv"
EXTRACTED = OUTPUT / "reserve_2014_2025_candidates.csv"

SOURCE_URL = (
    "https://www.cbsl.gov.lk/sites/default/files/"
    "cbslweb_documents/statistics/sheets/"
    "table2.15.2_20260930_e.xlsx"
)

MONTHS = pd.period_range(
    "2014-01", "2025-12", freq="M"
).astype(str).tolist()

MONTH_LOOKUP = {
    "jan": 1, "feb": 2, "mar": 3,
    "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9,
    "oct": 10, "nov": 11, "dec": 12
}


def identify_month(sheet_name):
    """
    Suggest a month from the worksheet name.

    This is only a candidate. The month must
    be checked against the source worksheet.
    """
    text = str(sheet_name).lower()

    year_match = re.search(
        r"(?<!\d)(20\d{2})(?!\d)", text
    )

    if not year_match:
        return ""

    year = int(year_match.group(1))

    for name, month in MONTH_LOOKUP.items():
        if re.search(name, text):
            candidate = f"{year}-{month:02d}"
            return candidate if candidate in MONTHS else ""

    return ""


def clean(value):
    return re.sub(
        r"\s+", " ", str(value or "")
    ).strip()


def inspect():
    if not SOURCE.is_file():
        raise FileNotFoundError(
            f"Download CBSL reserves workbook: {SOURCE}"
        )

    book = load_workbook(
        SOURCE,
        read_only=True,
        data_only=True
    )

    rows = []

    print("Worksheets found:", len(book.sheetnames))

    for sheet_name in book.sheetnames:
        ws = book[sheet_name]
        suggested_month = identify_month(sheet_name)

        for values in ws.iter_rows(
            min_row=1,
            max_row=min(ws.max_row, 80),
            max_col=min(ws.max_column, 20)
        ):
            for cell in values:
                text = clean(cell.value)
                lower = text.lower()

                # Find the total reserve-assets row.
                # These are candidates, not confirmations.
                possible = (
                    "official reserve assets" in lower
                    or "gross official reserves" in lower
                )

                if not possible:
                    continue

                # Ignore obvious narrative paragraphs
                # and very long explanatory notes.
                if len(text) > 160:
                    continue

                numeric_cells = []

                for value_cell in values:
                    value = value_cell.value

                    if isinstance(value, (int, float)) \
                            and not isinstance(value, bool) \
                            and pd.notna(value):
                        numeric_cells.append(
                            f"{value_cell.coordinate}={value}"
                        )

                rows.append({
                    "suggested_month": suggested_month,
                    "sheet": sheet_name,
                    "label_cell": cell.coordinate,
                    "label_text": text,
                    "numeric_cells_on_row": "; ".join(
                        numeric_cells
                    ),
                    "confirmed_month": "",
                    "confirmed_value_cell": "",
                    "confirmed_unit": "",
                    "review_status": "Pending"
                })

    book.close()

    if not rows:
        print(
            "No matching reserve headings found. "
            "Inspect the source layout manually."
        )
        return

    result = pd.DataFrame(rows)

    result.to_csv(
        CANDIDATES,
        index=False,
        encoding="utf-8-sig"
    )

    if not MAPPING.exists():
        result.to_csv(
            MAPPING,
            index=False,
            encoding="utf-8-sig"
        )

    print("\nCandidate rows:", len(result))
    print("Saved:", CANDIDATES)
    print("Review mapping:", MAPPING)

    print(
        "\nIMPORTANT: Confirm the month, "
        "total official reserve assets value cell "
        "and unit before extraction."
    )


def extract():
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)

    if not MAPPING.is_file():
        raise FileNotFoundError(
            "Run inspection first to create "
            "verified_reserve_cell_mapping.csv."
        )

    mapping = pd.read_csv(
        MAPPING,
        dtype=str,
        keep_default_na=False
    )

    required = {
        "sheet",
        "confirmed_month",
        "confirmed_value_cell",
        "confirmed_unit",
        "review_status"
    }

    if not required.issubset(mapping.columns):
        raise ValueError(
            "Mapping file lacks required columns."
        )

    verified = mapping[
        mapping["review_status"]
        .str.strip().str.casefold() == "verified"
    ].copy()

    if verified.empty:
        raise ValueError(
            "No verified reserve cell mappings yet."
        )

    if verified["confirmed_month"].duplicated().any():
        raise ValueError(
            "More than one verified mapping "
            "exists for the same month."
        )

    book = load_workbook(
        SOURCE,
        read_only=True,
        data_only=True
    )

    output_rows = []

    for row in verified.itertuples(index=False):
        month = row.confirmed_month.strip()

        if month not in MONTHS:
            raise ValueError(
                f"Unexpected month: {month}"
            )

        if row.sheet not in book.sheetnames:
            raise ValueError(
                f"Missing worksheet: {row.sheet}"
            )

        unit = row.confirmed_unit.strip()

        if unit not in {"USD millions", "USD billions"}:
            raise ValueError(
                f"{month}: Unit must be USD millions "
                "or USD billions."
            )

        cell_address = row.confirmed_value_cell.strip()

        if not re.fullmatch(
            r"[A-Za-z]{1,3}[1-9]\d*",
            cell_address
        ):
            raise ValueError(
                f"{month}: Invalid Excel cell address."
            )

        value = book[row.sheet][cell_address].value

        if isinstance(value, bool):
            raise ValueError(
                f"{month}: Boolean value is invalid."
            )

        try:
            value = float(value)
        except (ValueError, TypeError) as error:
            raise ValueError(
                f"{month}: Non-numeric reserve value "
                f"in {cell_address}."
            ) from error

        if not (0 < value < float("inf")):
            raise ValueError(
                f"{month}: Invalid reserve value."
            )

        if unit == "USD millions":
            value /= 1000

        output_rows.append({
            "month": month,
            "indicator": "fx_reserves_usd_bn",
            "candidate_value": value,
            "unit": "USD billions",
            "source_filename": SOURCE.name,
            "source_sheet": row.sheet,
            "source_column": cell_address,
            "official_source_url": SOURCE_URL,
            "publication_date": "",
            "verification_status": "Pending"
        })

    book.close()

    result = pd.DataFrame(output_rows)

    result = result.sort_values(
        "month"
    ).reset_index(drop=True)

    missing = sorted(
        set(MONTHS) - set(result["month"])
    )

    if missing:
        print(
            "\n[NOTICE] Missing months:",
            len(missing)
        )
        print(", ".join(missing[:24]))

    if EXTRACTED.exists():
        raise FileExistsError(
            "Previous reserves extraction exists. "
            "Archive it before rerunning."
        )

    result.to_csv(
        EXTRACTED,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n[PASS] Candidate values extracted.")
    print("Observations:", len(result))
    print("Saved:", EXTRACTED)
    print("All values remain Pending verification.")
    print("SQLite database unchanged.")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--extract",
        action="store_true"
    )

    args = parser.parse_args()

    if args.extract:
        extract()
    else:
        inspect()


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        FileNotFoundError,
        FileExistsError
    ) as error:
        print("[ERROR]", error)
        sys.exit(1)
