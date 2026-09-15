import importlib
import os
import sys

from plumbing import mail

from . import config as core_config
from . import db

ENABLE_ENV = "VILLAGE_ENABLE_SCHEDULER"


def _money_produced_this_week(conn, resident_id):
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM drafts "
        "WHERE resident_id = ? AND kind = 'money_page' "
        "AND created_at >= datetime('now', '-7 days')",
        (resident_id,),
    ).fetchone()
    return row["n"]


def resident_dispatch(conn, resident, config_path=None):
    name = resident["name"]
    if not resident.get("autonomous"):
        return f"{name}: not autonomous (skipped)"
    try:
        module = importlib.import_module(f"residents.{name}")
    except ImportError:
        return f"{name}: no module (skipped)"
    if not hasattr(module, "produce"):
        return f"{name}: no produce() (skipped)"
    cadence = int(resident.get("cadence_per_week", 0))
    if cadence <= 0:
        return f"{name}: cadence 0 (skipped)"
    row = conn.execute("SELECT id FROM residents WHERE name = ?", (name,)).fetchone()
    if row is None:
        return f"{name}: not seeded (skipped)"
    done = _money_produced_this_week(conn, row["id"])
    if done >= cadence:
        return f"{name}: {done}/{cadence} this week (skip)"
    limit = cadence - done
    created = module.produce(conn, run_llm=False, limit=limit)
    money = 0
    for draft_id in created:
        kind = conn.execute("SELECT kind FROM drafts WHERE id = ?", (draft_id,)).fetchone()["kind"]
        if kind == "money_page":
            money += 1
    return f"{name}: produced {money} money page(s) ({money}/{cadence} this week)"


def daily_dispatch(config_path: str = None):
    if not os.environ.get(ENABLE_ENV):
        return "scheduler disabled (set VILLAGE_ENABLE_SCHEDULER=1)"
    cfg = core_config.load_config(config_path) if config_path else core_config.load_config()
    conn = db.connect()
    report = []
    try:
        try:
            handled = mail.poll_commands()
            report.append(f"poll: {len(handled)} reply(ies) applied")
        except Exception as exc:
            report.append(f"poll: ERROR {exc}")
        for resident in core_config.residents(cfg):
            try:
                report.append(resident_dispatch(conn, resident, config_path))
            except Exception as exc:
                report.append(f"{resident['name']}: ERROR {exc}")
        pending = conn.execute(
            "SELECT COUNT(*) AS n FROM drafts WHERE status = 'pending'"
        ).fetchone()["n"]
        if pending:
            try:
                sent = mail.send_digest()
                report.append(f"digest: {sent} draft(s) emailed (from {pending} pending)")
            except Exception as exc:
                report.append(f"digest: ERROR {exc}")
        else:
            report.append("digest: nothing pending, not emailed")
    finally:
        conn.close()
    return "\n".join(report)


def run(config_path: str = None):
    print(daily_dispatch(config_path))


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else None)