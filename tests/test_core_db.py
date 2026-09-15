import sqlite3

import pytest

from core import db

TABLES = {
    "residents",
    "nuggets",
    "drafts",
    "queue_events",
    "ledger_entries",
    "outcomes",
    "polish_notes",
    "processed_emails",
    "jobs",
}


def table_names(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row["name"] for row in rows}


def test_init_creates_all_tables(db_conn):
    assert TABLES <= table_names(db_conn)


def test_init_is_idempotent(tmp_path):
    path = str(tmp_path / "twice.sqlite")
    db.init_db(path)
    db.init_db(path)
    conn = db.connect(path)
    assert TABLES <= table_names(conn)
    conn.close()


def test_foreign_keys_enforced(db_conn):
    with pytest.raises(Exception):
        db_conn.execute(
            "INSERT INTO drafts (resident_id, kind, payload) VALUES (999, 'x', '{}')"
        )


def test_wal_mode_enabled(db_conn):
    row = db_conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] in ("wal", "memory")


def test_migration_adds_job_id_to_existing_drafts(tmp_path):
    path = str(tmp_path / "old.sqlite")
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE residents (id INTEGER PRIMARY KEY, name TEXT); "
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY); "
        "CREATE TABLE nuggets (id INTEGER PRIMARY KEY, resident_id INTEGER); "
        "CREATE TABLE drafts (id INTEGER PRIMARY KEY, resident_id INTEGER, "
        "nugget_id INTEGER, kind TEXT, payload TEXT, version INTEGER, "
        "status TEXT, created_at TEXT, updated_at TEXT);"
    )
    conn.close()
    db.init_db(path)
    conn = db.connect(path)
    cols = [row["name"] for row in conn.execute("PRAGMA table_info(drafts)").fetchall()]
    assert "job_id" in cols
    conn.close()