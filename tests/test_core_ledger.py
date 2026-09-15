import pytest

from core import ledger


def test_spend_accumulates_per_resident(db_conn, resident):
    ledger.record_spend(db_conn, resident["id"], 0.01, tokens_in=1000, tokens_out=500, model="gemini-2.0-flash")
    ledger.record_spend(db_conn, resident["id"], 0.005, tokens_in=400, tokens_out=200)
    assert ledger.spent_today(db_conn, resident["id"]) == pytest.approx(0.015, abs=1e-9)


def test_spend_per_resident_is_isolated(db_conn, resident):
    other = _other_resident(db_conn)
    ledger.record_spend(db_conn, resident["id"], 0.01)
    ledger.record_spend(db_conn, other, 0.99)
    assert ledger.spent_today(db_conn, resident["id"]) == pytest.approx(0.01, abs=1e-9)
    assert ledger.total_spent(db_conn, other) == pytest.approx(0.99, abs=1e-9)


def test_cap_remaining(db_conn, resident):
    ledger.record_spend(db_conn, resident["id"], 0.75)
    assert ledger.cap_remaining(db_conn, resident["id"], 1.0) == pytest.approx(0.25, abs=1e-9)
    assert ledger.cap_remaining(db_conn, resident["id"], 0.5) == pytest.approx(0.0, abs=1e-9)


def test_total_spent_all_residents(db_conn, resident):
    other = _other_resident(db_conn)
    ledger.record_spend(db_conn, resident["id"], 0.01)
    ledger.record_spend(db_conn, other, 0.02)
    assert ledger.total_spent(db_conn) == pytest.approx(0.03, abs=1e-9)


def test_add_outcome(db_conn, resident):
    ledger.add_outcome(db_conn, resident["id"], "views", 1200, asset_ref="vid_1")
    rows = db_conn.execute(
        "SELECT metric, value, asset_ref FROM outcomes WHERE resident_id = ?",
        (resident["id"],),
    ).fetchall()
    assert rows[0]["metric"] == "views"
    assert rows[0]["value"] == 1200
    assert rows[0]["asset_ref"] == "vid_1"


def _other_resident(db_conn):
    cur = db_conn.execute(
        "INSERT INTO residents (name, zone, niche, status, daily_cap_usd, launch_budget_days) "
        "VALUES ('other', 'gray', 'test', 'active', 0.0, 0)"
    )
    db_conn.commit()
    return cur.lastrowid