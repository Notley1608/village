import pytest

from core import db, scheduler
from plumbing import deploy
from residents import directory
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
    directory.seed_use_case(conn)
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


def test_scheduler_skips_non_autonomous(no_mail, monkeypatch):
    monkeypatch.setenv("VILLAGE_ENABLE_SCHEDULER", "1")
    report = scheduler.daily_dispatch()
    assert "resume_studio: not autonomous (skipped)" in report
    assert "shorts: not autonomous (skipped)" in report


def test_scheduler_drafts_directory_within_cadence(no_mail, monkeypatch):
    monkeypatch.setenv("VILLAGE_ENABLE_SCHEDULER", "1")
    before = db.connect().execute(
        "SELECT COUNT(*) AS n FROM drafts WHERE kind = 'money_page'"
    ).fetchone()["n"]
    report = scheduler.daily_dispatch()
    after = db.connect().execute(
        "SELECT COUNT(*) AS n FROM drafts WHERE kind = 'money_page'"
    ).fetchone()["n"]
    assert after - before == 3  # directory cadence_per_week
    assert "directory: produced 3 money page(s)" in report
    assert "pending" in report


def test_scheduler_second_run_is_idempotent(no_mail, monkeypatch):
    monkeypatch.setenv("VILLAGE_ENABLE_SCHEDULER", "1")
    scheduler.daily_dispatch()
    before = db.connect().execute(
        "SELECT COUNT(*) AS n FROM drafts WHERE kind = 'money_page'"
    ).fetchone()["n"]
    report = scheduler.daily_dispatch()
    after = db.connect().execute(
        "SELECT COUNT(*) AS n FROM drafts WHERE kind = 'money_page'"
    ).fetchone()["n"]
    assert after == before
    assert "directory: 3/3 this week (skip)" in report