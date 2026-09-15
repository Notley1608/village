import json

import pytest

from core import db
from residents import resume_studio
from web.seed import seed_residents


@pytest.fixture
def conn(tmp_path):
    path = str(tmp_path / "store.sqlite")
    db.init_db(path)
    c = db.connect(path)
    seed_residents(conn=c)
    return c


SAMPLE_RESUME = (
    "Jane Doe\nSoftware Engineer, Acme Corp 2019-present\n"
    "Built API microservices in Python. Led a 4-person team. "
    "Cut p95 latency 40%.\nYears of experience: 6"
)


def jane(conn, **overrides):
    args = dict(
        client_name="Jane Doe",
        target_role="Senior Data Engineer",
        resume_text=SAMPLE_RESUME,
        contact="jane@example.com",
        answers={"Years": "6"},
    )
    args.update(overrides)
    return resume_studio.add_job(conn, **args)


def test_add_and_list_jobs(conn):
    a = jane(conn)
    b = jane(conn, client_name="Bob")
    jobs = resume_studio.list_jobs(conn)
    ids = [j["id"] for j in jobs]
    assert ids == [b, a]
    first = jobs[1]
    assert first["client_name"] == "Jane Doe"
    assert first["status"] == "new"
    assert json.loads(first["answers"]) == {"Years": "6"}


def test_produce_offline_creates_three_drafts_linked_to_job(conn):
    job_id = jane(conn)
    created = resume_studio.produce(conn, job_id, run_llm=False)
    assert len(created) == 3

    kinds = [d["kind"] for d in resume_studio.job_drafts(conn, job_id)]
    assert kinds == ["resume_rewrite", "linkedin_summary", "cover_letter"]

    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    assert row["status"] == "drafted"

    for draft_id in created:
        d = conn.execute(
            "SELECT * FROM drafts WHERE id = ? AND job_id = ?", (draft_id, job_id)
        ).fetchone()
        assert d is not None
        assert d["status"] == "pending"
        assert d["version"] == 1


def test_produce_offline_payload_is_offline_placeholder(conn):
    job_id = jane(conn)
    created = resume_studio.produce(conn, job_id)
    payload = conn.execute(
        "SELECT payload FROM drafts WHERE id = ?", (created[0],)
    ).fetchone()["payload"]
    assert "OFFLINE DRAFT" in payload
    assert "Jane Doe" in payload


def test_produce_missing_job_raises(conn):
    with pytest.raises(KeyError):
        resume_studio.produce(conn, 999)


def test_produce_requires_seeded_resident(tmp_path):
    c = db.connect(tmp_path / "store.sqlite")
    db.init_db(tmp_path / "store.sqlite")
    job_id = resume_studio.add_job(c, "X", "Role", "resume")
    with pytest.raises(RuntimeError):
        resume_studio.produce(c, job_id)


def test_prompts_include_client_context(conn):
    job = conn.execute(
        "SELECT * FROM jobs WHERE id = ?", (jane(conn),)
    ).fetchone()
    for builder in (
        resume_studio.prompts.build_resume_rewrite,
        resume_studio.prompts.build_linkedin_summary,
        resume_studio.prompts.build_cover_letter,
    ):
        prompt = builder(job)
        assert "Senior Data Engineer" in prompt
        assert "Jane Doe" in prompt
        assert "Acme" in prompt


def test_add_job_answers_serialized(conn):
    job_id = jane(conn, answers={"Salary": "130k", "Remote": "yes"})
    answers = json.loads(
        conn.execute("SELECT answers FROM jobs WHERE id = ?", (job_id,)).fetchone()[0]
    )
    assert answers == {"Salary": "130k", "Remote": "yes"}


def test_ship_job_records_revenue_outcome(conn):
    job_id = jane(conn)
    resume_studio.ship_job(conn, job_id, 60.0)
    row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    assert row["status"] == "shipped"
    rid = conn.execute(
        "SELECT id FROM residents WHERE name = 'resume_studio'"
    ).fetchone()["id"]
    outcome = conn.execute(
        "SELECT * FROM outcomes WHERE resident_id = ? AND metric = 'revenue_usd'",
        (rid,),
    ).fetchone()
    assert outcome is not None
    assert outcome["value"] == 60.0
    assert outcome["asset_ref"] == f"job:{job_id}"


def test_ship_job_idempotency_guard(conn):
    job_id = jane(conn)
    resume_studio.ship_job(conn, job_id, 60.0)
    with pytest.raises(ValueError):
        resume_studio.ship_job(conn, job_id, 60.0)


def test_ship_missing_job_raises(conn):
    with pytest.raises(KeyError):
        resume_studio.ship_job(conn, 999, 60.0)


def test_mark_lost(conn):
    job_id = jane(conn)
    resume_studio.mark_lost(conn, job_id)
    assert conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()["status"] == "lost"
    with pytest.raises(ValueError):
        resume_studio.mark_lost(conn, job_id)