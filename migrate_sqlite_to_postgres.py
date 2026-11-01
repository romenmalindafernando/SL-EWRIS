"""One-time, additive migration from a local SQLite backup to Neon PostgreSQL.

The source is opened read-only. A timestamped copy is created before any
destination writes. Existing PostgreSQL rows are never updated or deleted.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import DATA_COLUMNS, connect_database, create_tables

TABLE_COLUMNS = {
    "economic_monthly": DATA_COLUMNS + ["record_origin", "created_at", "updated_at"],
    "indicator_source_log": [
        "id", "month", "indicator", "old_value", "new_value",
        "publication_date", "source_name", "source_url", "recorded_at",
    ],
    "external_indicator_import_log": [
        "id", "month", "indicator", "value", "publication_date",
        "source_url", "action", "imported_at",
    ],
    "monthly_economic_drafts": [
        "month", "inflation_yoy_pct", "nominal_wage_growth_yoy_pct",
        "usd_lkr", "fx_reserves_usd_bn", "source_note",
        "verification_status", "created_at", "updated_at",
    ],
    "monthly_indicator_reviews": [
        "month", "indicator", "reviewed_value", "unit", "publication_date",
        "source_url", "review_status", "review_note", "reviewed_at",
    ],
}


def _backup_path(source: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return source.with_name(f"{source.name}.{stamp}.bak")


def _source_rows(source: sqlite3.Connection, table: str, columns: list[str]):
    available = {
        row[1] for row in source.execute(f'PRAGMA table_info("{table}")')
    }
    selected = [column for column in columns if column in available]
    if not selected:
        return [], []
    quoted = ", ".join(f'"{column}"' for column in selected)
    rows = source.execute(f'SELECT {quoted} FROM "{table}"').fetchall()
    return selected, rows


def migrate(source_path: Path, dry_run: bool = False) -> dict[str, int]:
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite backup not found: {source_path}")

    with sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True) as source:
        source.row_factory = sqlite3.Row
        present = {
            row[0] for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        payload = {
            table: _source_rows(source, table, columns)
            for table, columns in TABLE_COLUMNS.items()
            if table in present
        }

    counts = {table: len(rows) for table, (_, rows) in payload.items()}
    if dry_run:
        return counts

    backup = _backup_path(source_path)
    shutil.copy2(source_path, backup)
    with connect_database() as destination:
        create_tables(destination)
        for table, (columns, rows) in payload.items():
            if not rows:
                continue
            quoted_columns = ", ".join(f'"{column}"' for column in columns)
            placeholders = ", ".join("?" for _ in columns)
            destination.executemany(
                f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders}) '
                "ON CONFLICT DO NOTHING",
                [tuple(row[column] for column in columns) for row in rows],
            )
    print(f"SQLite source backup retained at: {backup}")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sqlite_path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(migrate(args.sqlite_path, dry_run=args.dry_run))
