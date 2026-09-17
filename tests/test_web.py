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
    import web.app as web_app_mod
    monkeypatch.setattr(web_app_mod, "TOKEN", "")
    web_app = __import__("web.app", fromlist=["app"]).app
    with TestClient(web_app, follow_redirects=False) as c:
        yield c


def test_overview_shows_all_residents(client):
    body = client.get("/").text
    assert "shorts_history" in body
    assert "shorts_ai_tools" in body
    assert "audience_growth" in body
    # removed residents no longer on the dashboard
    assert "resume_studio" not in body
    assert "directory" not in body
    assert "matched_betting" not in body


def test_queue_and_vault_and_ledger_render(client):
    assert client.get("/queue?status=pending").status_code == 200
    assert client.get("/vault").status_code == 200
    assert client.get("/ledger").status_code == 200


def test_draft_not_found(client):
    assert client.get("/draft/999").status_code == 404


def test_approve_from_dashboard(client):
    conn = db.connect()
    resident = conn.execute("SELECT id FROM residents WHERE name = 'shorts_history'").fetchone()
    draft_id = queue.create_draft(conn, resident["id"], "short_script", "{}")
    conn.close()
    resp = client.post(f"/draft/{draft_id}/approve")
    assert resp.status_code == 303
    conn = db.connect()
    status = conn.execute("SELECT status FROM drafts WHERE id = ?", (draft_id,)).fetchone()["status"]
    conn.close()
    assert status == "approved"


def test_save_new_version(client):
    conn = db.connect()
    resident = conn.execute("SELECT id FROM residents WHERE name = 'shorts_history'").fetchone()
    draft_id = queue.create_draft(conn, resident["id"], "short_script", "old")
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


def test_jobs_pages_removed(client):
    # resume_studio is no longer a resident, so there are no jobs.
    assert client.get("/jobs").status_code == 404
    assert client.get("/job/new").status_code == 404
    assert client.get("/job/999").status_code == 404


def test_agents_pages_render(client):
    assert client.get("/agents").status_code == 200
    for name in ("shorts_history", "shorts_ai_tools", "audience_growth"):
        assert client.get(f"/agents/{name}").status_code == 200
        assert client.get(f"/agents/{name}/vault").status_code == 200
    assert client.get("/agents/nope").status_code == 404
    # removed residents 404
    assert client.get("/agents/resume_studio").status_code == 404
    assert client.get("/agents/directory").status_code == 404
    assert client.get("/agents/matched_betting").status_code == 404


def test_agent_queue_filters_by_workstream(client):
    conn = db.connect()
    rid = conn.execute("SELECT id FROM residents WHERE name = 'shorts_history'").fetchone()["id"]
    m1 = queue.create_draft(conn, rid, "short_script", "fact about rosetta stone")
    m2 = queue.create_draft(conn, rid, "storyboard", "storyboard one")
    conn.close()

    body = client.get("/agents/shorts_history/queue?status=pending").text
    assert "fact about rosetta stone" in body
    assert "storyboard one" in body

    # Both kinds are in the same workstream, so scoping to it shows both.
    scoped = client.get(
        "/agents/shorts_history/queue?status=pending&workstream=Short%20scripts%20%2B%20assembly"
    ).text
    assert "fact about rosetta stone" in scoped
    assert "storyboard one" in scoped


def test_agent_page_shows_workstream_sections(client):
    conn = db.connect()
    rid = conn.execute("SELECT id FROM residents WHERE name = 'shorts_history'").fetchone()["id"]
    queue.create_draft(conn, rid, "short_script", "keyword page two")
    queue.create_draft(conn, rid, "storyboard", "storyboard two")
    conn.close()
    body = client.get("/agents/shorts_history").text
    assert "Short scripts + assembly" in body
    assert "Needs review" in body or "needs review" in body.lower()


def test_escalations_page(client):
    assert client.get("/escalations").status_code == 200


def test_escalation_flow(client):
    # seed a fresh escalation
    conn = db.connect()
    rid = conn.execute("SELECT id FROM residents WHERE name = 'shorts_history'").fetchone()["id"]
    eid = conn.execute(
        "INSERT INTO escalations (resident_id, title, kind, status, body) "
        "VALUES (?, 'publish_request', 'publish_request', 'pending', 'test')",
        (rid,),
    ).lastrowid
    conn.commit()
    conn.close()

    assert client.get(f"/escalations/{eid}").status_code == 200

    resp = client.post(f"/escalations/{eid}/approve")
    assert resp.status_code == 303
    conn = db.connect()
    status = conn.execute("SELECT status FROM escalations WHERE id = ?", (eid,)).fetchone()["status"]
    conn.close()
    assert status == "approved"
