import json
import os
import sys

import google.generativeai as genai
from dotenv import load_dotenv

from core import config as core_config
from core import db, ledger, queue
from .prompts import (
    build_cover_letter,
    build_linkedin_summary,
    build_resume_rewrite,
)

load_dotenv()

OUTPUT_KINDS = [
    ("resume_rewrite", build_resume_rewrite),
    ("linkedin_summary", build_linkedin_summary),
    ("cover_letter", build_cover_letter),
]

RESIDENT_NAME = "resume_studio"


def add_job(conn, client_name, target_role, resume_text, contact=None, answers=None):
    answers_json = None
    if answers:
        answers_json = json.dumps(answers) if isinstance(answers, dict) else str(answers)
    cur = conn.execute(
        "INSERT INTO jobs (client_name, contact, target_role, resume_text, answers, status) "
        "VALUES (?, ?, ?, ?, ?, 'new')",
        (client_name, contact, target_role, resume_text, answers_json),
    )
    conn.commit()
    return cur.lastrowid


def list_jobs(conn):
    return conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()


def job_drafts(conn, job_id):
    return conn.execute(
        """
        SELECT d.*, r.name AS resident_name
        FROM drafts d JOIN residents r ON r.id = d.resident_id
        WHERE d.job_id = ?
        ORDER BY d.id
        """,
        (job_id,),
    ).fetchall()


def _template(kind, job):
    resume_snip = (job["resume_text"] or "")[:800].replace("\n", " ")
    return (
        f"OFFLINE DRAFT ({kind}) - run `python -m residents.resume_studio draft "
        f"{job['id']} --llm` to generate with Gemini.\n\n"
        f"Client: {job['client_name']}\n"
        f"Target role: {job['target_role']}\n\n"
        f"---\n\n"
        f"[Placeholder {kind} for review. Source excerpt: {resume_snip}]"
    )


def _respond(prompt, model):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in .env")
    genai.configure(api_key=api_key)
    response = genai.GenerativeModel(model).generate_content(prompt)
    return response.text


def _resident_id(conn):
    row = conn.execute(
        "SELECT id FROM residents WHERE name = ?", (RESIDENT_NAME,)
    ).fetchone()
    if row is None:
        raise RuntimeError(f"resident '{RESIDENT_NAME}' not seeded; run `python -m web.seed`")
    return row["id"]


def ship_job(conn, job_id, amount_usd):
    row = conn.execute("SELECT id, status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(job_id)
    if row["status"] == "shipped":
        raise ValueError("job already shipped")
    conn.execute("UPDATE jobs SET status = 'shipped' WHERE id = ?", (job_id,))
    ledger.add_outcome(
        conn,
        _resident_id(conn),
        "revenue_usd",
        float(amount_usd),
        asset_ref=f"job:{job_id}",
    )
    conn.commit()
    return job_id


def mark_lost(conn, job_id, reason=None):
    row = conn.execute("SELECT id, status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(job_id)
    if row["status"] in ("shipped", "lost"):
        raise ValueError("job already closed")
    conn.execute("UPDATE jobs SET status = 'lost' WHERE id = ?", (job_id,))
    conn.commit()
    return job_id


def produce(conn, job_id, run_llm=False):
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        raise KeyError(job_id)
    rid = _resident_id(conn)
    model = core_config.load_config()["village"]["model"]
    created = []
    for kind, builder in OUTPUT_KINDS:
        if run_llm:
            payload = _respond(builder(job), model)
            ledger.record_spend(conn, rid, 0.0, model=model, kind="llm_token_cost")
        else:
            payload = _template(kind, job)
        draft_id = queue.create_draft(conn, rid, kind, payload)
        conn.execute(
            "UPDATE drafts SET job_id = ? WHERE id = ?", (job_id, draft_id)
        )
        created.append(draft_id)
    conn.execute("UPDATE jobs SET status = 'drafted' WHERE id = ?", (job_id,))
    conn.commit()
    return created


def _parse_flags(args):
    opts = {"--answer": [], "--resume": None, "--resume-file": None}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--answer":
            if i + 1 < len(args):
                opts["--answer"].append(args[i + 1])
                i += 2
                continue
        elif a.startswith("--") and i + 1 < len(args):
            opts[a] = args[i + 1]
            i += 2
            continue
        i += 1
    return opts


def _parse_kv_pairs(items):
    answers = {}
    for item in items:
        for sep in ("=", ":"):
            if sep in item:
                key, _, value = item.partition(sep)
                answers[key.strip()] = value.strip()
                break
    return answers


def _usage():
    return (
        "usage: python -m residents.resume_studio <command> [args]\n"
        "  jobs\n"
        "  add-job --name NAME --target 'ROLE' --resume 'TEXT' [--resume-file PATH]\n"
        "          [--contact EMAIL] [--answer 'key=value']...\n"
        "  draft <job_id> [--llm]\n"
        "  help"
    )


def main():
    args = sys.argv[1:]
    command = args[0] if args else "help"
    if command == "help":
        print(_usage())
        return
    conn = db.connect()
    try:
        if command == "jobs":
            for job in list_jobs(conn):
                print(f"{job['id']}: {job['client_name']} -> {job['target_role']} [{job['status']}]")
        elif command == "add-job":
            opts = _parse_flags(args[1:])
            resume_file = opts.get("--resume-file")
            resume_text = open(resume_file).read() if resume_file else opts.get("--resume", "")
            if not opts.get("--name") or not opts.get("--target") or not resume_text:
                print(_usage())
                raise SystemExit("add-job requires --name, --target, and --resume or --resume-file")
            job_id = add_job(
                conn,
                opts.get("--name"),
                opts.get("--target"),
                resume_text,
                contact=opts.get("--contact"),
                answers=_parse_kv_pairs(opts.get("--answer", [])),
            )
            print(f"job {job_id} created")
        elif command == "draft":
            if len(args) < 2:
                print(_usage())
                raise SystemExit("draft requires <job_id>")
            job_id = int(args[1])
            created = produce(conn, job_id, run_llm="--llm" in args)
            print(f"created drafts: {', '.join('#' + str(i) for i in created)}")
        else:
            print(_usage())
    finally:
        conn.close()


if __name__ == "__main__":
    main()