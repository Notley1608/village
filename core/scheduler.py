import importlib
import json
import os
import sys
from datetime import datetime

from plumbing import mail
from plumbing import obsidian

from . import config as core_config
from . import db
from . import ledger

ENABLE_ENV = "VILLAGE_ENABLE_SCHEDULER"

# Orchestrator handoff directory: Hermes writes delegated task specs here as JSON files;
# the scheduler picks them up and executes them via the matching resident module.
def pending_delegations():
    """Yield (job_id, spec) for every pending delegation Hermes has dropped here."""
    deleg_dir = os.environ.get(
        "VILLAGE_HERMES_DELEGATIONS_DIR",
        os.path.join(os.path.dirname(__file__), "..", "hermes_delegations"),
    )
    if not os.path.isdir(deleg_dir):
        return
    for fname in sorted(os.listdir(deleg_dir)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(deleg_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                spec = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue
        # Mark as read by renaming to .done to avoid re-running.
        os.rename(path, path + ".done")
        yield fname[:-5], spec


def resident_by_name(name):
    cfg = core_config.load_config()
    for r in core_config.residents(cfg):
        if r["name"] == name:
            return r
    raise KeyError(name)


def escalate(conn, resident_id, kind, title, body, resident_name=None):
    """Record an escalation that must reach the human."""
    conn.execute(
        "INSERT INTO escalations (resident_id, kind, title, body) VALUES (?, ?, ?, ?)",
        (resident_id, kind, title, body),
    )
    conn.commit()
    obsidian.write_escalation(conn, resident_id, resident_name or "", kind, title, body)
    # Also try to email the escalation if mail is configured.
    try:
        mail.send_escalation(resident_name or "", kind, title, body)
    except Exception:
        pass


def proven_proposal(conn, resident_id, resident_name, views_total, revenue_total, cost_total, proposed_threshold):
    escalate(
        conn,
        resident_id,
        "proven_proposal",
        f"Proven-profitable proposal: {resident_name}",
        (
            f"Niche '{resident_name}' may be approaching proven-profitable status. "
            f"Views across test batch: {views_total:,}. Revenue to date: ${revenue_total:.2f}. "
            f"Cost this cycle: ${cost_total:.2f}. "
            f"Proposed view threshold from current platform benchmarks: {proposed_threshold:,}. "
            f"This is a PROPOSAL to relax volume/spend for this niche — it is NOT a self-executing unlock. "
            f"Approve or deny via the dashboard or email."
        ),
    )


def resident_dispatch(conn, resident, config_path=None):
    """No autonomous produce() anymore. Residents are planned by the Hermes orchestrator
    and executed here only when Hermes has dropped a delegation for them."""
    name = resident["name"]
    module_name = resident.get("module") or name
    for job_id, spec in pending_delegations():
        if spec.get("agent") != "OPENCODE-BUILDER":
            continue
        if spec.get("niche") != resident.get("niche"):
            continue
        try:
            mod = importlib.import_module(f"residents.{module_name}")
        except ImportError:
            continue
        if not hasattr(mod, "produce"):
            continue
        try:
            created = mod.produce(conn, spec=spec)
        except NotImplementedError:
            continue
        except Exception as exc:
            continue
    return f"{name}: dispatch checked (no new delegations or none matching)"


def daily_dispatch(config_path: str = None):
    if not os.environ.get(ENABLE_ENV):
        return "scheduler disabled (set VILLAGE_ENABLE_SCHEDULER=1)"
    cfg = core_config.load_config(config_path) if config_path else core_config.load_config()
    conn = db.connect()
    report = []
    try:
        # 1. Apply any human email replies first.
        try:
            handled = mail.poll_commands()
            report.append(f"poll: {len(handled)} reply(ies) applied")
        except Exception as exc:
            report.append(f"poll: ERROR {exc}")

        # 2. Run resident dispatch (only acts on Hermes delegations now).
        for resident in core_config.residents(cfg):
            try:
                report.append(resident_dispatch(conn, resident, config_path))
            except Exception as exc:
                report.append(f"{resident['name']}: ERROR {exc}")

        # 3. Monthly cap watch — hard ceiling $50/mo.
        monthly = ledger.monthly_spent(conn)
        cap = float(cfg.get("ledger", {}).get("monthly_cap_usd", 50.0) or 50.0)
        report.append(f"ledger: monthly spend ${monthly:.2f} / cap ${cap:.2f}")
        if monthly > cap:
            report.append("ledger: KILL SWITCH — monthly cap exceeded")

        # 4. Escalations waiting for human.
        pending_esc = conn.execute(
            "SELECT COUNT(*) AS n FROM escalations WHERE status = 'pending'"
        ).fetchone()["n"]
        report.append(f"escalations: {pending_esc} pending human decision(s)")

        # 5. Digest pending drafts (human-gated publish — same as before).
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