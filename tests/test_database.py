import os
import uuid

import pytest

from database import DATA_COLUMNS, _row_factory, connect_database


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


requires_test_database = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to run Neon PostgreSQL integration tests",
)


def test_row_factory_defers_description_until_row_creation():
    class Column:
        def __init__(self, name):
            self.name = name

    class Cursor:
        description = None

    cursor = Cursor()
    make_row = _row_factory(cursor)
    cursor.description = [Column("name"), Column("value")]
    row = make_row(("Ada", 42))

    assert row["name"] == "Ada"
    assert row[0] == "Ada"
    assert row["value"] == 42
    assert row[1] == 42


def test_row_factory_handles_no_description():
    class Cursor:
        description = None

    assert dict(_row_factory(Cursor())(())) == {}


@pytest.fixture
def connection(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    conn = connect_database()
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@requires_test_database
def test_schema_integrity_and_expected_columns(connection):
    columns = {
        row[0]
        for row in connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'economic_monthly'
            """
        )
    }
    assert set(DATA_COLUMNS).issubset(columns)
    assert {"monthly_economic_drafts", "monthly_indicator_reviews"} <= {
        row[0]
        for row in connection.execute(
            "SELECT tablename FROM pg_catalog.pg_tables "
            "WHERE schemaname = current_schema()"
        )
    }


@requires_test_database
def test_write_row_count_and_persistence_after_restart(connection, monkeypatch):
    month = f"2099-{int(uuid.uuid4().hex[:2], 16) % 12 + 1:02d}"
    connection.execute(
        """
        INSERT INTO economic_monthly(month, source, record_origin, notes)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(month) DO NOTHING
        """,
        (month, "integration test", "test", "temporary"),
    )
    connection.commit()
    assert connection.execute(
        "SELECT COUNT(*) FROM economic_monthly WHERE month = ?", (month,)
    ).fetchone()[0] == 1
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    with connect_database() as restarted:
        assert restarted.execute(
            "SELECT source FROM economic_monthly WHERE month = ?", (month,)
        ).fetchone()[0] == "integration test"
        restarted.execute("DELETE FROM economic_monthly WHERE month = ?", (month,))
        restarted.commit()


@requires_test_database
def test_ddl_select_insert_and_transaction_rollback(connection):
    table = f"sl_ewris_test_{uuid.uuid4().hex}"
    connection.execute(
        f'CREATE TEMPORARY TABLE "{table}" (id INTEGER PRIMARY KEY, label TEXT)'
    )
    connection.execute(f'INSERT INTO "{table}" (id, label) VALUES (?, ?)', (1, "committed"))
    connection.commit()

    row = connection.execute(
        f'SELECT id, label FROM "{table}" WHERE id = ?', (1,)
    ).fetchone()
    assert row[0] == 1
    assert row["label"] == "committed"

    connection.execute(
        f'INSERT INTO "{table}" (id, label) VALUES (?, ?)',
        (2, "rolled back"),
    )
    connection.rollback()

    assert connection.execute(
        f'SELECT COUNT(*) FROM "{table}" WHERE id = ?', (2,)
    ).fetchone()[0] == 0
