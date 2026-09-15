import os

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core import db, queue, vault
from residents import resume_studio
from web import seed

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Village")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

TOKEN = os.environ.get("DASHBOARD_TOKEN", "")

KNOWN_STATUSES = ["pending", "approved", "rejected", "rework", "published", "killed"]


def _conn():
    return db.connect()


def _active_from_path(path):
    if path.startswith("/queue") or path.startswith("/draft"):
        return "queue"
    if path.startswith("/job"):
        return "jobs"
    if path.startswith("/vault"):
        return "vault"
    if path.startswith("/ledger"):
        return "ledger"
    return "overview"


def _base_ctx(request):
    conn = db.connect()
    try:
        pending_count = conn.execute(
            "SELECT COUNT(*) AS n FROM drafts WHERE status = 'pending'"
        ).fetchone()["n"]
        income_total = conn.execute(
            "SELECT COALESCE(SUM(value), 0) AS s FROM outcomes WHERE metric = 'revenue_usd'"
        ).fetchone()["s"]
    finally:
        conn.close()
    return {
        "request": request,
        "active": _active_from_path(request.url.path),
        "auth_on": bool(TOKEN),
        "pending_count": pending_count,
        "income_total": income_total,
        "msg": request.query_params.get("msg"),
        "msg_class": request.query_params.get("msg_class", "ok"),
    }


def render(request, template_name, **ctx):
    data = _base_ctx(request)
    data.update(ctx)
    return templates.TemplateResponse(template_name, data)


def _auth_ok(request):
    if not TOKEN:
        return True
    return request.cookies.get("village_key") == TOKEN or request.query_params.get("key") == TOKEN


@app.middleware("http")
async def auth_middleware(request, call_next):
    path = request.url.path
    public = (
        path.startswith("/static")
        or path == "/login"
        or path == "/logout"
        or path == "/favicon.ico"
    )
    if TOKEN and not _auth_ok(request) and not public:
        return RedirectResponse(f"/login?next={path}", status_code=302)
    return await call_next(request)


@app.on_event("startup")
def _startup():
    seed.seed_residents()


@app.get("/login")
def login_page(request: Request, next: str = "/"):
    return render(request, "login.html", error=False, next=next)


@app.post("/login")
def login(request: Request, key: str = Form(...), next: str = Form("/")):
    if key == TOKEN:
        response = RedirectResponse(next or "/", status_code=303)
        response.set_cookie("village_key", TOKEN, httponly=True, samesite="lax")
        return response
    return render(request, "login.html", error=True, next=next)


@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("village_key")
    return response


def _residents_with_counts(conn):
    return conn.execute(
        """
        SELECT r.*,
          (SELECT COUNT(*) FROM drafts d WHERE d.resident_id = r.id AND d.status = 'pending')   AS pending,
          (SELECT COUNT(*) FROM drafts d WHERE d.resident_id = r.id AND d.status = 'approved')  AS approved,
          (SELECT COUNT(*) FROM drafts d WHERE d.resident_id = r.id AND d.status = 'published') AS published,
          (SELECT COUNT(*) FROM drafts d WHERE d.resident_id = r.id AND d.status = 'rejected')  AS rejected,
          (SELECT COALESCE(SUM(le.amount_usd), 0) FROM ledger_entries le
             WHERE le.resident_id = r.id AND date(le.created_at) = date('now'))                 AS spend_today,
          (SELECT COALESCE(SUM(le.amount_usd), 0) FROM ledger_entries le
             WHERE le.resident_id = r.id)                                                       AS spend_total,
          CAST(julianday('now') - julianday(r.launch_start_date) AS INTEGER)                    AS launch_days_used
        FROM residents r
        ORDER BY r.id
        """
    ).fetchall()


@app.get("/")
def overview(request: Request):
    conn = _conn()
    residents = _residents_with_counts(conn)
    totals_pending = conn.execute(
        "SELECT COUNT(*) AS n FROM drafts WHERE status = 'pending'"
    ).fetchone()["n"]
    spend_today = conn.execute(
        "SELECT COALESCE(SUM(amount_usd), 0) AS s FROM ledger_entries "
        "WHERE date(created_at) = date('now')"
    ).fetchone()["s"]
    spend_total = conn.execute(
        "SELECT COALESCE(SUM(amount_usd), 0) AS s FROM ledger_entries"
    ).fetchone()["s"]
    income_total = conn.execute(
        "SELECT COALESCE(SUM(value), 0) AS s FROM outcomes WHERE metric = 'revenue_usd'"
    ).fetchone()["s"]
    events = conn.execute(
        """
        SELECT e.*, d.kind AS draft_kind, r.name AS resident_name
        FROM queue_events e
        JOIN drafts d ON d.id = e.draft_id
        JOIN residents r ON r.id = d.resident_id
        ORDER BY e.id DESC
        LIMIT 20
        """
    ).fetchall()
    conn.close()
    return render(
        request,
        "overview.html",
        title="Overview",
        breadcrumb="<b>Overview</b>",
        residents=residents,
        totals_pending=totals_pending,
        spend_today=spend_today,
        spend_total=spend_total,
        income_total=income_total,
        events=events,
    )


@app.get("/queue")
def queue_page(request: Request, status: str = "pending", q: str = ""):
    conn = _conn()
    params = [status]
    like = None
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            """
            SELECT d.*, r.name AS resident_name
            FROM drafts d JOIN residents r ON r.id = d.resident_id
            WHERE d.status = ? AND (d.payload LIKE ? OR CAST(d.id AS TEXT) = ?)
            ORDER BY d.id DESC
            """,
            (status, like, q.strip()),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT d.*, r.name AS resident_name
            FROM drafts d JOIN residents r ON r.id = d.resident_id
            WHERE d.status = ?
            ORDER BY d.id DESC
            """,
            (status,),
        ).fetchall()
    present = [
        r["status"]
        for r in conn.execute("SELECT DISTINCT status FROM drafts ORDER BY status").fetchall()
    ]
    counts = {}
    for r in conn.execute("SELECT status, COUNT(*) AS n FROM drafts GROUP BY status").fetchall():
        counts[r["status"]] = r["n"]
    conn.close()
    statuses = present or KNOWN_STATUSES
    if status not in statuses:
        statuses.append(status)
    if status not in counts:
        counts[status] = 0
    return render(
        request,
        "queue.html",
        title="Queue",
        breadcrumb="<b>Queue</b>",
        rows=rows,
        status=status,
        statuses=statuses,
        counts=counts,
        q=q,
    )


@app.get("/draft/{draft_id}")
def draft_page(request: Request, draft_id: int):
    conn = _conn()
    row = conn.execute(
        """
        SELECT d.*, r.name AS resident_name, r.zone, r.niche
        FROM drafts d JOIN residents r ON r.id = d.resident_id
        WHERE d.id = ?
        """,
        (draft_id,),
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="draft not found")
    events = conn.execute(
        "SELECT * FROM queue_events WHERE draft_id = ? ORDER BY id", (draft_id,)
    ).fetchall()
    conn.close()
    return render(
        request,
        "draft.html",
        title=f"Draft {draft_id}",
        breadcrumb=f'<a href="/queue">Queue</a> <span style="opacity:.5" >/</span> <b>Draft #{draft_id}</b>',
        draft=row,
        events=events,
    )


def _back(request):
    return request.headers.get("referer") or "/queue?status=pending"


def _transition(request, draft_id, event, note=None, msg=None):
    conn = _conn()
    try:
        queue.transition(conn, draft_id, event, actor="human", note=note)
    except (ValueError, KeyError) as exc:
        conn.close()
        raise HTTPException(status_code=400, detail=str(exc))
    conn.close()
    back = _back(request)
    sep = "&" if "?" in back else "?"
    return RedirectResponse(
        f"{back}{sep}msg={msg or event}&msg_class=ok", status_code=303
    )


@app.post("/draft/{draft_id}/approve")
def approve(request: Request, draft_id: int):
    return _transition(request, draft_id, "approved", msg="Approved")


@app.post("/draft/{draft_id}/flag")
def flag(request: Request, draft_id: int, note: str = Form("")):
    return _transition(request, draft_id, "rejected", note=note or None, msg="Flagged for rework")


@app.post("/draft/{draft_id}/publish")
def publish(request: Request, draft_id: int):
    return _transition(request, draft_id, "published", msg="Published")


@app.post("/draft/{draft_id}/save")
def save(request: Request, draft_id: int, payload: str = Form(...), note: str = Form("")):
    conn = _conn()
    row = conn.execute(
        "SELECT id, nugget_id, status, version FROM drafts WHERE id = ?", (draft_id,)
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="draft not found")
    new_version = row["version"] + 1
    conn.execute(
        "UPDATE drafts SET payload = ?, version = ?, updated_at = datetime('now') WHERE id = ?",
        (payload, new_version, draft_id),
    )
    queue.log_event(conn, draft_id, "edit", actor="human", note=note or "polished")
    conn.commit()
    conn.close()
    return RedirectResponse(f"/draft/{draft_id}?msg=Version %d saved&msg_class=ok" % new_version, status_code=303)


@app.post("/draft/{draft_id}/copyback")
def toggle_copyback(request: Request, draft_id: int, note: str = Form("")):
    conn = _conn()
    row = conn.execute(
        "SELECT id, nugget_id, status FROM drafts WHERE id = ?", (draft_id,)
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="draft not found")
    if row["nugget_id"]:
        vault.add_polish_note(
            conn, draft_id, row["nugget_id"], note or "editor highlight", copied_back=1
        )
    conn.close()
    return RedirectResponse(f"/draft/{draft_id}", status_code=303)


@app.get("/jobs")
def jobs_page(request: Request):
    conn = _conn()
    jobs = resume_studio.list_jobs(conn)
    rows = []
    for job in jobs:
        drafts = conn.execute(
            "SELECT COUNT(*) AS n, SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending "
            "FROM drafts WHERE job_id = ?",
            (job["id"],),
        ).fetchone()
        rows.append((job, drafts["n"], drafts["pending"] or 0))
    conn.close()
    return render(
        request, "jobs.html", title="Jobs", breadcrumb="<b>Jobs</b>", rows=rows
    )


@app.get("/job/new")
def job_new_page(request: Request):
    return render(
        request, "job_new.html", title="New job", breadcrumb='<a href="/jobs">Jobs</a> / <b>New job</b>'
    )


@app.post("/job/new")
def job_create(
    request: Request,
    client_name: str = Form(...),
    target_role: str = Form(...),
    resume_text: str = Form(...),
    contact: str = Form(""),
    answers: str = Form(""),
):
    conn = _conn()
    answers_dict = None
    lines = [line.strip() for line in answers.splitlines() if line.strip()]
    if lines:
        answers_dict = {}
        for line in lines:
            if ":" in line:
                key, _, value = line.partition(":")
                answers_dict[key.strip()] = value.strip()
    job_id = resume_studio.add_job(
        conn, client_name, target_role, resume_text, contact=contact or None,
        answers=answers_dict or None,
    )
    conn.close()
    return RedirectResponse(f"/job/{job_id}", status_code=303)


@app.get("/job/{job_id}")
def job_page(request: Request, job_id: int):
    conn = _conn()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        conn.close()
        raise HTTPException(status_code=404, detail="job not found")
    drafts = resume_studio.job_drafts(conn, job_id)
    conn.close()
    return render(
        request,
        "job.html",
        title=f"Job {job_id}",
        breadcrumb=f'<a href="/jobs">Jobs</a> / <b>{job["client_name"]}</b>',
        job=job,
        drafts=drafts,
    )


@app.post("/job/{job_id}/generate")
def job_generate(request: Request, job_id: int):
    conn = _conn()
    try:
        resume_studio.produce(conn, job_id, run_llm=False)
    except KeyError:
        conn.close()
        raise HTTPException(status_code=404, detail="job not found")
    conn.close()
    return RedirectResponse(f"/job/{job_id}?msg=Drafts generated&msg_class=ok", status_code=303)


@app.post("/job/{job_id}/ship")
def job_ship(request: Request, job_id: int, amount_usd: float = Form(...)):
    conn = _conn()
    try:
        resume_studio.ship_job(conn, job_id, amount_usd)
    except KeyError:
        conn.close()
        raise HTTPException(status_code=404, detail="job not found")
    except ValueError as exc:
        conn.close()
        raise HTTPException(status_code=400, detail=str(exc))
    conn.close()
    return RedirectResponse(
        f"/job/{job_id}?msg=Shipped — income recorded&msg_class=ok", status_code=303
    )


@app.post("/job/{job_id}/lost")
def job_lost(request: Request, job_id: int):
    conn = _conn()
    try:
        resume_studio.mark_lost(conn, job_id)
    except KeyError:
        conn.close()
        raise HTTPException(status_code=404, detail="job not found")
    except ValueError as exc:
        conn.close()
        raise HTTPException(status_code=400, detail=str(exc))
    conn.close()
    return RedirectResponse(
        f"/job/{job_id}?msg=Marked as lost&msg_class=warn", status_code=303
    )


@app.get("/vault")
def vault_page(request: Request, q: str = "", tag: str = ""):
    conn = _conn()
    rows = vault.search(conn, term=q or None, tag=tag or None)
    conn.close()
    return render(
        request, "vault.html", title="Vault", breadcrumb="<b>Vault</b>", rows=rows, q=q, tag=tag
    )


@app.get("/ledger")
def ledger_page(request: Request):
    conn = _conn()
    rows = conn.execute(
        """
        SELECT r.name AS resident, date(le.created_at) AS day, SUM(le.amount_usd) AS spend
        FROM ledger_entries le JOIN residents r ON r.id = le.resident_id
        WHERE le.created_at >= datetime('now', '-14 days')
        GROUP BY r.id, day
        ORDER BY day DESC, r.id
        """
    ).fetchall()
    per_resident = conn.execute(
        """
        SELECT r.name, COALESCE(SUM(le.amount_usd), 0) AS total
        FROM residents r LEFT JOIN ledger_entries le ON le.resident_id = r.id
        GROUP BY r.id ORDER BY r.id
        """
    ).fetchall()
    income_total = conn.execute(
        "SELECT COALESCE(SUM(value), 0) AS s FROM outcomes WHERE metric = 'revenue_usd'"
    ).fetchone()["s"]
    outcomes = conn.execute(
        """
        SELECT o.*, r.name AS resident
        FROM outcomes o JOIN residents r ON r.id = o.resident_id
        ORDER BY o.id DESC LIMIT 20
        """
    ).fetchall()
    conn.close()
    return render(
        request,
        "ledger.html",
        title="Ledger",
        breadcrumb="<b>Ledger</b>",
        rows=rows,
        per_resident=per_resident,
        income_total=income_total,
        outcomes=outcomes,
    )