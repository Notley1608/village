import pytest
from core import db, scheduler
from plumbing import deploy
from residents import shorts
from web.seed import seed_residents


@pytest.fixture
def conn(tmp_path, monkeypatch):
    path = str(tmp_path / "store.sqlite")
    db.init_db(path)
    monkeypatch.setattr(db, "DB_PATH", path)
    c = db.connect()
    seed_residents(conn=c)
    return c


@pytest.fixture
def tmpvault(conn):
    shorts.seed_use_case(conn)
    return conn


@pytest.fixture
def no_mail(tmpvault, monkeypatch):
    monkeypatch.setattr("plumbing.mail.poll_commands", lambda limit=20: [])
    monkeypatch.setattr("plumbing.mail.send_digest", lambda: 0)
    return tmpvault


def test_verification_file(tmp_path):
    path = deploy.write_verification_file(str(tmp_path), "ABC123")
    assert path.endswith("googleABC123.html")
    with open(path) as f:
        text = f.read()
    assert "googleABC123.html" in text


def test_verification_cli_generates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["deploy", "verify", "TOKEN9"])
    deploy.main()
    assert (tmp_path / "site" / "googleTOKEN9.html").exists()


def test_scheduler_disabled_by_default(monkeypatch):
    monkeypatch.delenv("VILLAGE_ENABLE_SCHEDULER", raising=False)
    assert "disabled" in scheduler.daily_dispatch()


def test_scheduler_skips_without_delegations(no_mail, monkeypatch):
    monkeypatch.setenv("VILLAGE_ENABLE_SCHEDULER", "1")
    report = scheduler.daily_dispatch()
    assert "shorts_history: dispatch checked (no new delegations or none matching)" in report
    assert "shorts_ai_tools: dispatch checked (no new delegations or none matching)" in report
    assert "audience_growth: dispatch checked (no new delegations or none matching)" in report


def test_scheduler_runs_on_delegation(no_mail, monkeypatch, tmp_path):
    monkeypatch.setenv("VILLAGE_ENABLE_SCHEDULER", "1")
    import json
    from pathlib import Path
    deleg_dir = Path(str(tmp_path)) / "hermes_delegations"
    deleg_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "job_id": "job-1",
        "agent": "OPENCODE-BUILDER",
        "niche": "history_and_weird_facts",
        "format": "faceless_narrated",
        "constraints": {"budget": 0.0, "deadline": "2026-12-31T00:00:00Z", "platform_rules": []},
        "success_criteria": [],
        "output_contract": "short_script",
        "vault_log_path": "Ecosystem/Cycles/2026-09-15-job-1.md",
    }
    (deleg_dir / "job-1.json").write_text(json.dumps(spec))
    monkeypatch.setenv("VILLAGE_HERMES_DELEGATIONS_DIR", str(deleg_dir))
    report = scheduler.daily_dispatch()
    assert "shorts_history: dispatch checked" in report
    c = db.connect()
    n = c.execute("SELECT COUNT(*) AS n FROM drafts WHERE status='pending'").fetchone()["n"]
    assert n >= 1
    c.close()


def test_scheduler_second_run_is_idempotent(no_mail, monkeypatch):
    monkeypatch.setenv("VILLAGE_ENABLE_SCHEDULER", "1")
    scheduler.daily_dispatch()
    before = db.connect().execute(
        "SELECT COUNT(*) AS n FROM drafts WHERE kind = 'short_script'"
    ).fetchone()["n"]
    report = scheduler.daily_dispatch()
    after = db.connect().execute(
        "SELECT COUNT(*) AS n FROM drafts WHERE kind = 'short_script'"
    ).fetchone()["n"]
    assert after == before
    assert "shorts_history: dispatch checked (no new delegations or none matching)" in report
