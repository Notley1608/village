"""Canonical short-form video resident — the execution layer Hermes delegates to.

This module is what OPENCODE-BUILDER produces and maintains. Hermes drops a
job spec JSON into hermes_delegations/; the scheduler picks it up and calls
produce(conn, spec=...) here.

Scope for v1: draft generation only. Assembly, TTS, publishing are downstream
jobs the orchestrator will delegate separately once the script module is proven.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, date
from pathlib import Path

from core import config as core_config
from core import db, ledger, queue, vault

RESIDENT_NAME = "shorts_history"
OUTPUT_KINDS = ["short_script", "storyboard", "asset_manifest", "marketing_copy"]


def resident_id(conn) -> int:
    row = conn.execute(
        "SELECT id FROM residents WHERE name = ?", (RESIDENT_NAME,)
    ).fetchone()
    if row is None:
        raise RuntimeError(
            f"resident '{RESIDENT_NAME}' not seeded; run `python -m web.seed`"
        )
    return row["id"]


def _default_script_payload(niche: str, fmt: str) -> str:
    """Offline placeholder draft the orchestrator can review before spending tokens."""
    return (
        f"# OFFLINE DRAFT — {fmt}\n"
        f"**Niche:** {niche}\n"
        f"**Format:** {fmt}\n"
        f"**Generated:** {datetime.now().isoformat()}\n\n"
        f"(placeholder — run with an LLM-backed delegation to produce a real script)\n"
    )


def _default_marketing_payload(niche: str, fmt: str) -> str:
    """Growth Hacker's offline placeholder: title/description/hashtags for the
    same delegation, reviewed alongside the script before any distribution."""
    return (
        f"# OFFLINE MARKETING COPY — {fmt}\n"
        f"**Niche:** {niche}\n"
        f"**Title:** (placeholder — hook for {niche})\n"
        f"**Description:** (placeholder — run with an LLM-backed delegation for real copy)\n"
        f"**Hashtags:** #shorts #{niche.replace('_', '')}\n"
        f"**Generated:** {datetime.now().isoformat()}\n"
    )


def seed_use_case(conn, count=3):
    """Seed a small number of research nuggets for the history niche so the
    resident can produce drafts in tests without hitting an LLM."""
    rid = resident_id(conn)
    created = []
    topics = ["Rosetta Stone", "Library of Alexandria", "Antikythera mechanism"]
    for i in range(min(count, len(topics))):
        title = f"fact: {topics[i]}"
        body = f"A short factoid about {topics[i]}. Replace with researched history content."
        created.append(vault.add_nugget(conn, title, body, tags=["fact"], resident_id=rid))
    return created


def produce(conn, spec: dict | None = None, run_llm: bool = False, limit: int | None = None):
    """Produce drafts for this resident.

    Parameters
    ----------
    conn : sqlite3.Connection
    spec : dict
        The job spec Hermes dropped (Section 2 of the orchestrator skill). If None,
        produce offline placeholders only.
    run_llm : bool
        Whether to actually call an LLM (requires API key in .env). In v1 this is
        delegated to the script-generator Node module; this flag is retained for
        the offline/online split the existing dashboard supports.
    limit : int
        Max drafts to produce thiscall.
    """
    cfg = core_config.load_config()
    rid = resident_id(conn)

    if spec is None:
        # No delegation — produce offline placeholders so the dashboard has something
        # to show while the orchestrator is being wired.
        niche = _resident_niche(cfg)
        created = []
        for kind in OUTPUT_KINDS:
            if limit is not None and len(created) >= limit:
                break
            payload = (
                _default_marketing_payload(niche, kind)
                if kind == "marketing_copy"
                else _default_script_payload(niche, kind)
            )
            created.append(queue.create_draft(conn, rid, kind, payload))
        return created

    # We have a delegation from Hermes.
    job_id = spec.get("job_id", f"delegation-{uuid.uuid4().hex[:8]}")
    niche = spec.get("niche", _resident_niche(cfg))
    fmt = spec.get("format", "faceless_narrated")
    budget = float(spec.get("constraints", {}).get("budget", 0.0))

    # Enforce the budget field from the job spec (never exceed it).
    # In v1 we record LLM spend as $0 until we hook up real billing; the guardrail
    # is structural — the orchestrator sets the budget, we never exceed it.
    created = []
    model = cfg.get("village", {}).get("model", "")

    # Engineer: builds the script/asset. Growth Hacker: builds the marketing
    # copy for the same delegation, in parallel. Each invoices the Treasurer
    # under its own ledger kind so spend is attributable per role.
    script_payload = _default_script_payload(niche, fmt)
    created.append(queue.create_draft(conn, rid, "short_script", script_payload))
    marketing_payload = _default_marketing_payload(niche, fmt)
    created.append(queue.create_draft(conn, rid, "marketing_copy", marketing_payload))

    if run_llm:
        # In v1, LLM-backed generation is done by the Node script-generator module.
        # This path is a stub that records the intent; the real implementation is
        # what OPENCODE-BUILDER delivers. Spend is $0 until real billing is wired —
        # the guardrail is structural, not a live budget check.
        ledger.record_spend(conn, rid, 0.0, model=model, kind="engineer_build", note=f"delegation {job_id}")
        ledger.record_spend(conn, rid, 0.0, model=model, kind="growth_distribution", note=f"delegation {job_id}")

    # Attach the delegation job id to each draft's payload for traceability.
    # The payload is markdown, not JSON, so append it as a text footnote rather
    # than using json_insert (which would reject non-JSON text).
    for draft_id in created:
        conn.execute(
            "UPDATE drafts SET payload = payload || char(10) || '-- delegation_job_id: ' || ? || char(10) WHERE id = ?",
            (job_id, draft_id),
        )
    conn.commit()
    return created


def _resident_niche(cfg) -> str:
    for r in core_config.residents(cfg):
        if r["name"] == RESIDENT_NAME:
            return r.get("niche", "history_and_weird_facts")
    return "history_and_weird_facts"


def main():
    import sys
    args = sys.argv[1:]
    command = args[0] if args else "help"
    conn = db.connect()
    try:
        if command in ("draft", "produce"):
            created = produce(conn, run_llm="--llm" in args)
            print(f"created drafts: {', '.join('#' + str(i) for i in created)}")
        else:
            print("usage: python -m residents.shorts [draft|produce] [--llm]")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
