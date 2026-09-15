import os
import sqlite3

DB_PATH = os.environ.get("VILLAGE_DB", os.path.join(os.path.dirname(__file__), "store.sqlite"))

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS residents (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL UNIQUE,
    zone              TEXT NOT NULL,
    niche             TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'idle',
    daily_cap_usd     REAL NOT NULL DEFAULT 0.0,
    launch_budget_days INTEGER NOT NULL DEFAULT 0,
    launch_start_date TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS nuggets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    resident_id INTEGER REFERENCES residents(id),
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    source_url  TEXT,
    tags        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS drafts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    resident_id       INTEGER NOT NULL REFERENCES residents(id),
    nugget_id         INTEGER REFERENCES nuggets(id),
    kind              TEXT NOT NULL,
    payload           TEXT NOT NULL,
    version           INTEGER NOT NULL DEFAULT 1,
    status            TEXT NOT NULL DEFAULT 'pending',
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS queue_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id   INTEGER NOT NULL REFERENCES drafts(id),
    event      TEXT NOT NULL,
    note       TEXT,
    actor      TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    resident_id INTEGER NOT NULL REFERENCES residents(id),
    kind       TEXT NOT NULL,
    amount_usd REAL NOT NULL DEFAULT 0.0,
    tokens_in  INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    model      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS outcomes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    resident_id INTEGER NOT NULL REFERENCES residents(id),
    asset_ref   TEXT,
    metric      TEXT NOT NULL,
    value       REAL NOT NULL,
    at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS polish_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id    INTEGER NOT NULL REFERENCES drafts(id),
    nugget_id   INTEGER NOT NULL REFERENCES nuggets(id),
    note        TEXT NOT NULL,
    copied_back INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS processed_emails (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    mailbox       TEXT NOT NULL,
    uid           INTEGER NOT NULL,
    processed_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (mailbox, uid)
);

CREATE INDEX IF NOT EXISTS idx_drafts_status   ON drafts(resident_id, status);
CREATE INDEX IF NOT EXISTS idx_nuggets_tags    ON nuggets(resident_id);
CREATE INDEX IF NOT EXISTS idx_ledger_resident ON ledger_entries(resident_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_metric ON outcomes(resident_id, metric);
"""


def connect(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(path: str = DB_PATH) -> None:
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("store.sqlite initialised")