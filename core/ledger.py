from .db import connect


def record_spend(conn, resident_id, amount_usd, tokens_in=0, tokens_out=0, model=None, kind="llm_token_cost"):
    conn.execute(
        "INSERT INTO ledger_entries (resident_id, kind, amount_usd, tokens_in, tokens_out, model) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (resident_id, kind, amount_usd, tokens_in, tokens_out, model),
    )
    conn.commit()


def spent_today(conn, resident_id):
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_usd), 0) AS total "
        "FROM ledger_entries "
        "WHERE resident_id = ? AND date(created_at) = date('now')",
        (resident_id,),
    ).fetchone()
    return row["total"]


def cap_remaining(conn, resident_id, daily_cap_usd):
    return max(0.0, daily_cap_usd - spent_today(conn, resident_id))


def total_spent(conn, resident_id=None):
    if resident_id is None:
        return conn.execute("SELECT COALESCE(SUM(amount_usd), 0) AS total FROM ledger_entries").fetchone()["total"]
    return conn.execute(
        "SELECT COALESCE(SUM(amount_usd), 0) AS total FROM ledger_entries WHERE resident_id = ?",
        (resident_id,),
    ).fetchone()["total"]


def add_outcome(conn, resident_id, metric, value, asset_ref=None):
    conn.execute(
        "INSERT INTO outcomes (resident_id, metric, value, asset_ref) VALUES (?, ?, ?, ?)",
        (resident_id, metric, value, asset_ref),
    )
    conn.commit()