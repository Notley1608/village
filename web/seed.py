import sys

from core import config as core_config
from core import db, ledger, queue, vault


def seed_residents(config_path=None, conn=None):
    cfg = core_config.load_config(config_path) if config_path else core_config.load_config()
    owns = conn is None
    conn = conn or db.connect()
    try:
        for resident in core_config.residents(cfg):
            conn.execute(
                "INSERT OR IGNORE INTO residents "
                "(name, zone, niche, status, daily_cap_usd, launch_budget_days) "
                "VALUES (?, ?, ?, 'idle', ?, ?)",
                (
                    resident["name"],
                    resident["zone"],
                    resident["niche"],
                    resident.get("daily_cap_usd", 0.0),
                    resident.get("launch_budget_days", 0),
                ),
            )
        conn.commit()
    finally:
        if owns:
            conn.close()
    return f"seeded residents from config"


def seed_demo(config_path=None):
    conn = db.connect()
    try:
        resident = conn.execute(
            "SELECT id FROM residents WHERE name = 'resume_studio'"
        ).fetchone()
        if resident is None:
            seed_residents(config_path)
            resident = conn.execute(
                "SELECT id FROM residents WHERE name = 'resume_studio'"
            ).fetchone()
        rid = resident["id"]
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
            "money_page",
            "The ten best AI widgets for freelancers in 2026. [Demo draft - replace with real agent output.]",
            nugget_id=nuggets[0],
        )
        queue.create_draft(
            conn,
            rid,
            "resume_rewrite",
            "Professional summary rewrite for a backend engineer targeting a senior role. [Demo draft.]",
            nugget_id=nuggets[1],
        )
        ledger.record_spend(conn, rid, 0.01, tokens_in=1200, tokens_out=340, model="gemini-2.0-flash")
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