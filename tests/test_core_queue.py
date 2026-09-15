import pytest

from core import queue


def make_draft(db_conn, resident, kind="test_draft"):
    return queue.create_draft(db_conn, resident["id"], kind, '{"content": "x"}')


def test_created_draft_is_pending(db_conn, resident):
    draft_id = make_draft(db_conn, resident)
    row = db_conn.execute("SELECT status FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    assert row["status"] == "pending"


def test_pending_drafts_filtered_by_resident(db_conn, resident):
    other = db_conn.execute(
        "INSERT INTO residents (name, zone, niche, status, daily_cap_usd, launch_budget_days) "
        "VALUES ('other', 'gray', 'test', 'active', 0.0, 0)"
    ).lastrowid
    db_conn.commit()
    first = queue.create_draft(db_conn, resident["id"], "test_draft", "{}")
    queue.create_draft(db_conn, other, "test_draft", "{}")
    assert [d["id"] for d in queue.pending_drafts(db_conn, resident["id"])] == [first]


def test_full_lifecycle(db_conn, resident):
    draft_id = make_draft(db_conn, resident)
    queue.transition(db_conn, draft_id, "approved", actor="human")
    queue.transition(db_conn, draft_id, "published", actor="human")
    row = db_conn.execute("SELECT status FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    assert row["status"] == "published"


def test_reject_then_rework_then_kill(db_conn, resident):
    draft_id = make_draft(db_conn, resident)
    queue.transition(db_conn, draft_id, "rejected", actor="human", note="weak angle")
    queue.transition(db_conn, draft_id, "rework", actor="system")
    queue.transition(db_conn, draft_id, "rejected", actor="human", note="still weak")
    queue.transition(db_conn, draft_id, "killed", actor="system")
    row = db_conn.execute("SELECT status FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    assert row["status"] == "killed"


def test_illegal_transition_raises(db_conn, resident):
    draft_id = make_draft(db_conn, resident)
    with pytest.raises(ValueError):
        queue.transition(db_conn, draft_id, "published")


def test_events_logged(db_conn, resident):
    draft_id = make_draft(db_conn, resident)
    queue.transition(db_conn, draft_id, "rejected", actor="human", note="redo")
    events = db_conn.execute(
        "SELECT event, note, actor FROM queue_events WHERE draft_id = ? ORDER BY id",
        (draft_id,),
    ).fetchall()
    assert [(e["event"], e["actor"]) for e in events] == [
        ("created", "system"),
        ("rejected", "human"),
    ]
    assert events[1]["note"] == "redo"


def test_missing_draft_raises(db_conn):
    with pytest.raises(KeyError):
        queue.transition(db_conn, 404, "approved")