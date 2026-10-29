
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

SOURCE = (
    ROOT / "data" / "cbsl_downloads"
    / "table2.15.2_20260930_e.xlsx"
)

OUTPUT = ROOT / "outputs" / "cbsl_extraction"
OUTPUT.mkdir(parents=True, exist_ok=True)

if not SOURCE.is_file():
    raise FileNotFoundError(
        f"Download the reserves workbook first: {SOURCE}"
    )

with pd.ExcelFile(SOURCE) as book:
    sheets = book.sheet_names

    print("Total worksheets:", len(sheets))
    print("\nFIRST 12 WORKSHEET NAMES:")
    print("\n".join(sheets[:12]))

    print("\nLAST 12 WORKSHEET NAMES:")
    print("\n".join(sheets[-12:]))

    # Examine representative months across the
    # research period to detect layout changes.
    targets = ["2014", "2019", "2021", "2022", "2025"]

    selected = []

    for year in targets:
        matches = [
            s for s in sheets if year in s
        ]
        if matches:
            selected.append(matches[0])

    # Fall back to sample worksheets if names
    # use unusual date formats.
    if not selected:
        selected = [
            sheets[0],
            sheets[len(sheets) // 2],
            sheets[-1]
        ]

    all_matches = []

    for sheet in dict.fromkeys(selected):
        print("\n" + "=" * 65)
        print("SHEET:", sheet)
        print("=" * 65)

        df = pd.read_excel(
            book,
            sheet_name=sheet,
            header=None,
            nrows=45,
            dtype=str
        )

        for index, row in df.iterrows():
            cells = [
                f"C{col + 1}: {str(value)[:90]}"
                for col, value in enumerate(row)
                if pd.notna(value)
            ]

            line = " | ".join(cells[:8])

            if line:
                print(f"Excel row {index + 1}: {line}")

            text = " ".join(
                str(value) for value in row
                if pd.notna(value)
            ).lower()

            if any(term in text for term in [
                "official reserve assets",
                "total official",
                "foreign currency reserves",
                "gross official reserves"
            ]):
                all_matches.append({
                    "sheet": sheet,
                    "excel_row": index + 1,
                    "row_text": text[:500]
                })

    pd.DataFrame(
        all_matches,
        columns=["sheet", "excel_row", "row_text"]
    ).to_csv(
        OUTPUT / "reserves_row_candidates.csv",
        index=False,
        encoding="utf-8-sig"
    )

print("\n[PASS] Reserves workbook inspected.")
print("No economic data were changed.")
