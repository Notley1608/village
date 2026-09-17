import pytest
from residents import shorts


def test_module_exposes_produce():
    assert callable(shorts.produce)


def test_production_config(cfg):
    r = [r for r in cfg["residents"] if r["name"] == "shorts_history"][0]
    assert r["production"]["style"] == "stock_loops_captions"
    assert r["production"]["tts"] == "free_local"
    assert "case_by_case" in (r["production"].get("disclosure") or "")


def test_pipeline_accepts_spec():
    """With a Hermes delegation spec, produce() should create a draft (not raise)."""
    from core import db, vault, queue
    from web.seed import seed_residents
    c = db.connect()
    try:
        seed_residents(conn=c)
        spec = {
            "job_id": "test-spec",
            "agent": "OPENCODE-BUILDER",
            "niche": "history_and_weird_facts",
            "format": "faceless_narrated",
            "constraints": {"budget": 0.0, "deadline": "2026-12-31T00:00:00Z", "platform_rules": []},
            "success_criteria": [],
            "output_contract": "short_script",
            "vault_log_path": "Ecosystem/Cycles/2026-09-15-test.md",
        }
        created = shorts.produce(c, spec=spec)
        assert created
        row = c.execute("SELECT kind, payload FROM drafts WHERE id = ?", (created[0],)).fetchone()
        assert row["kind"] == "short_script"
        assert "OFFLINE DRAFT" in row["payload"]
    finally:
        c.close()


def test_offline_placeholder_format():
    """Offline placeholder drafts should follow the expected template shape."""
    from core import db
    from web.seed import seed_residents
    c = db.connect()
    try:
        seed_residents(conn=c)
        created = shorts.produce(c)
        row = c.execute("SELECT payload FROM drafts WHERE id = ?", (created[0],)).fetchone()
        lines = row["payload"].splitlines()
        assert lines[0].startswith("# OFFLINE DRAFT")
        assert any("Niche:" in l for l in lines)
        assert any("Format:" in l for l in lines)
    finally:
        c.close()
