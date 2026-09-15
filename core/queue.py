from .db import connect

VALID_TRANSITIONS = {
    "pending": {"approved", "rejected", "killed"},
    "approved": {"published", "killed"},
    "rejected": {"rework", "killed"},
    "rework": {"approved", "rejected", "killed"},
    "published": set(),
    "killed": set(),
}


def create_draft(conn, resident_id, kind, payload, nugget_id=None):
    cur = conn.execute(
        "INSERT INTO drafts (resident_id, nugget_id, kind, payload, status) "
        "VALUES (?, ?, ?, ?, 'pending')",
        (resident_id, nugget_id, kind, payload),
    )
    draft_id = cur.lastrowid
    log_event(conn, draft_id, "created")
    conn.commit()
    return draft_id


def transition(conn, draft_id, event, actor="system", note=None):
    row = conn.execute("SELECT status FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if row is None:
        raise KeyError(draft_id)
    current = row["status"]
    if event not in VALID_TRANSITIONS[current]:
        raise ValueError(f"{event} not allowed from {current}")
    conn.execute("UPDATE drafts SET status = ?, updated_at = datetime('now') WHERE id = ?", (event, draft_id))
    log_event(conn, draft_id, event, actor=actor, note=note)
    conn.commit()


def log_event(conn, draft_id, event, actor="system", note=None):
    conn.execute(
        "INSERT INTO queue_events (draft_id, event, actor, note) VALUES (?, ?, ?, ?)",
        (draft_id, event, actor, note),
    )


def pending_drafts(conn, resident_id=None):
    if resident_id is None:
        return conn.execute(
            "SELECT * FROM drafts WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
    return conn.execute(
        "SELECT * FROM drafts WHERE resident_id = ? AND status = 'pending' ORDER BY created_at",
        (resident_id,),
    ).fetchall()