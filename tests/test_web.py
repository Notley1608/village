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