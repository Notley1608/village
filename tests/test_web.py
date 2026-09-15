import pytest
from fastapi.testclient import TestClient

from core import db, queue
from web import seed


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = str(tmp_path / "web.sqlite")
    db.init_db(path)
    monkeypatch.setattr(db, "DB_PATH", path)
    seed.seed_residents()
    web_app = __import__("web.app", fromlist=["app"]).app
    with TestClient(web_app, follow_redirects=False) as c:
        yield c


def test_overview_shows_all_residents(client):
    body = client.get("/").text
    assert "resume_studio" in body
    assert "directory" in body
    assert "shorts" in body


def test_queue_and_vault_and_ledger_render(client):
    assert client.get("/queue?status=pending").status_code == 200
    assert client.get("/vault").status_code == 200
    assert client.get("/ledger").status_code == 200


def test_draft_not_found(client):
    assert client.get("/draft/999").status_code == 404


def test_approve_from_dashboard(client):
    conn = db.connect()
    resident = conn.execute("SELECT id FROM residents WHERE name = 'resume_studio'").fetchone()
    draft_id = queue.create_draft(conn, resident["id"], "test_draft", "{}")
    conn.close()
    resp = client.post(f"/draft/{draft_id}/approve")
    assert resp.status_code == 303
    conn = db.connect()
    status = conn.execute("SELECT status FROM drafts WHERE id = ?", (draft_id,)).fetchone()["status"]
    conn.close()
    assert status == "approved"


def test_save_new_version(client):
    conn = db.connect()
    resident = conn.execute("SELECT id FROM residents WHERE name = 'resume_studio'").fetchone()
    draft_id = queue.create_draft(conn, resident["id"], "test_draft", "old")
    conn.close()
    resp = client.post(
        f"/draft/{draft_id}/save",
        data={"payload": "new text", "note": "tightened"},
    )
    assert resp.status_code == 303
    conn = db.connect()
    row = conn.execute("SELECT payload, version FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    conn.close()
    assert row["payload"] == "new text"
    assert row["version"] == 2


def test_jobs_pages_render(client):
    assert client.get("/jobs").status_code == 200
    assert client.get("/job/new").status_code == 200


def test_job_create_and_generate_offline(client):
    resp = client.post(
        "/job/new",
        data={
            "client_name": "Terra",
            "target_role": "SRE",
            "resume_text": "resume body text",
            "contact": "",
            "answers": "",
        },
    )
    assert resp.status_code == 303
    conn = db.connect()
    job_id = conn.execute("SELECT id FROM jobs WHERE client_name = 'Terra'").fetchone()["id"]
    conn.close()

    assert client.get(f"/job/{job_id}").status_code == 200
    assert "resume body text" in client.get(f"/job/{job_id}").text

    resp = client.post(f"/job/{job_id}/generate")
    assert resp.status_code == 303
    conn = db.connect()
    n = conn.execute("SELECT COUNT(*) AS n FROM drafts WHERE job_id = ?", (job_id,)).fetchone()["n"]
    status = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()["status"]
    conn.close()
    assert n == 3
    assert status == "drafted"


def test_job_not_found(client):
    assert client.get("/job/999").status_code == 404


def test_job_ship_and_income_shows(client):
    conn = db.connect()
    job_id = conn.execute(
        "INSERT INTO jobs (client_name, target_role, resume_text, status) "
        "VALUES ('PaidClient', 'PM', 'resume', 'drafted')"
    ).lastrowid
    conn.commit()
    conn.close()

    resp = client.post(f"/job/{job_id}/ship", data={"amount_usd": "75.00"})
    assert resp.status_code == 303

    conn = db.connect()
    status = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()["status"]
    income = conn.execute(
        "SELECT COALESCE(SUM(value), 0) AS s FROM outcomes WHERE metric = 'revenue_usd'"
    ).fetchone()["s"]
    conn.close()
    assert status == "shipped"
    assert income == 75.0

    body = client.get("/").text
    assert "75.00" in body