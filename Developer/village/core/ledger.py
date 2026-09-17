from .db import connect

def record_spend(conn, resident_id, amount_usd, tokens_in=0, tokens_out=0, model=None, kind="llm_token_cost", note=None):
    # Kill switch: if this spend would exceed the per-cycle cap, refuse and raise.
    # The cap is read from config; the human sets it when approving a cycle.
    # Before a niche is "proven", every spend requires human explicit approval
    # (enforced at the orchestrator layer, but we also hard-stop here as a backstop).
    from . import config as core_config
    cfg = core_config.load_config()
    per_cycle_cap = float(cfg.get("ledger", {}).get("per_cycle_cap_usd", 0.0) or 0.0)
    if per_cycle_cap > 0:
        spent = total_spent_this_cycle(conn)
        if spent + amount_usd > per_cycle_cap:
            raise RuntimeError(
                f"kill switch: spend ${amount_usd:.2f} would exceed per-cycle cap "
                f"${per_cycle_cap:.2f} (already spent ${spent:.2f} this cycle). "
                "No spend is made. Human reset required."
            )
    conn.execute(
        "INSERT INTO ledger_entries (resident_id, kind, amount_usd, tokens_in, tokens_out, model, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (resident_id, kind, amount_usd, tokens_in, tokens_out, model, note),
    )
    conn.commit()

def total_spent_this_cycle(conn):
    """Spend across all residents since the start of the current calendar month.
    Used by the kill switch and by the monthly-cap tracking."""
    import datetime
    now = datetime.datetime.now()
    start_of_month = datetime.datetime(now.year, now.month, 1).strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_usd), 0.0) AS total FROM ledger_entries WHERE created_at >= ?",
        (start_of_month,),
    ).fetchone()
    return float(row["total"])

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

def monthly_spent(conn):
    """Total spend this calendar month across all residents (for the $50/mo ceiling)."""
    return total_spent_this_cycle(conn)

def add_outcome(conn, resident_id, metric, value, asset_ref=None):
    conn.execute(
        "INSERT INTO outcomes (resident_id, metric, value, asset_ref) VALUES (?, ?, ?, ?)",
        (resident_id, metric, value, asset_ref),
    )
    conn.commit()
