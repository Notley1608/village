import json
import sys
from pathlib import Path

from core import config as core_config
from core import db, ledger, queue, vault
from plumbing import obsidian


def seed_residents(config_path=None, conn=None):
    cfg = core_config.load_config(config_path) if config_path else core_config.load_config()
    owns = conn is None
    conn = conn or db.connect()
    try:
        for resident in core_config.residents(cfg):
            fmt = resident.get("format")
            if fmt and isinstance(fmt, list):
                fmt = json.dumps(fmt)
            elif fmt:
                pass
            else:
                fmt = "[]"
            conn.execute(
                """INSERT OR IGNORE INTO residents
                   (name, zone, niche, status, daily_cap_usd, launch_budget_days, format)
                   VALUES (?, ?, ?, 'idle', ?, ?, ?)""",
                (
                    resident["name"],
                    resident.get("zone", "gray"),
                    resident.get("niche", ""),
                    resident.get("daily_cap_usd", 0.0),
                    resident.get("launch_budget_days", 0),
                    fmt,
                ),
            )
        conn.commit()
    finally:
        if owns:
            conn.close()
    return "seeded residents from config"


def seed_demo(config_path=None):
    conn = db.connect()
    try:
        resident = conn.execute(
            "SELECT id FROM residents WHERE name = 'shorts_history'"
        ).fetchone()
        if resident is None:
            seed_residents(config_path)
            resident = conn.execute(
                "SELECT id FROM residents WHERE name = 'shorts_history'"
            ).fetchone()
            if resident is None:
                conn.close()
                return "no shorts_history resident seeded; update config.yaml and re-run seed"
        rid = resident["id"]
        obsidian.ensure_structure()
        nuggets = []
        for index, title in enumerate(["Gemini free tier limits", "YPP Shorts threshold"]):
            nuggets.append(
                vault.add_nugget(
                    conn,
                    title,
                    f"Demo research nugget {index + 1}. Replace with real mined research.",
                    tags=["demo"],
                    resident_id=rid,
                )
            )
        queue.create_draft(
            conn,
            rid,
            "short_script",
            "The ten best AI widgets for freelancers in 2026. [Demo draft - replace with real agent output.]",
            nugget_id=nuggets[0],
        )
        queue.create_draft(
            conn,
            rid,
            "storyboard",
            "Storyboard placeholder for a history short. [Demo draft.]",
            nugget_id=nuggets[1],
        )
        ledger.record_spend(conn, rid, 0.01, tokens_in=1200, tokens_out=340, model="gemini-2.0-flash", note="demo seed spend")
        # Seed a pending escalation in the DB so the escalations page is not empty.
        conn.execute(
            "INSERT INTO escalations (resident_id, kind, title, body) VALUES (?, 'publish_request', ?, ?)",
            (rid, "Test escalation: review the dashboard escalation flow",
             "This is a demo escalation to confirm the escalations page and email mirror work. "
             "Approve or deny from the dashboard — the real orchestrator will create these from its operating loop."),
        )
        conn.commit()
        # Mirror the same escalation into the Obsidian vault folder.
        obsidian.write_escalation(
            conn, rid, "shorts_history", "publish_request",
            "Test escalation: review the dashboard escalation flow",
            "This is a demo escalation to confirm the escalations page and email mirror work. "
            "Approve or deny from the dashboard — the real orchestrator will create these from its operating loop.",
        )
    finally:
        conn.close()
    return "demo rows added"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "residents"
    if mode == "demo":
        print(seed_demo())
    else:
        print(seed_residents())


if __name__ == "__main__":
    main()
