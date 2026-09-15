import os

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core import db, queue, vault
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
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": False, "next": next}
    )


@app.post("/login")
def login(request: Request, key: str = Form(...), next: str = Form("/")):
    if key == TOKEN:
        response = RedirectResponse(next or "/", status_code=303)
        response.set_cookie("village_key", TOKEN, httponly=True, samesite="lax")
        return response
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": True, "next": next}
    )


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
    return templates.TemplateResponse(
        "overview.html",
        {
            "request": request,
            "title": "Overview",
            "residents": residents,
            "totals_pending": totals_pending,
            "spend_today": spend_today,
            "spend_total": spend_total,
            "events": events,
        },
    )


@app.get("/queue")
def queue_page(request: Request, status: str = "pending"):
    conn = _conn()
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
    conn.close()
    statuses = present or KNOWN_STATUSES
    if status not in statuses:
        statuses.append(status)
    return templates.TemplateResponse(
        "queue.html",
        {
            "request": request,
            "title": "Queue",
            "rows": rows,
            "status": status,
            "statuses": statuses,
        },
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
    return templates.TemplateResponse(
        "draft.html",
        {
            "request": request,
            "title": f"Draft {draft_id}",
            "draft": row,
            "events": events,
        },
    )


def _back(request):
    return request.headers.get("referer") or "/queue?status=pending"


def _transition(request, draft_id, event, note=None):
    conn = _conn()
    try:
        queue.transition(conn, draft_id, event, actor="human", note=note)
    except (ValueError, KeyError) as exc:
        conn.close()
        raise HTTPException(status_code=400, detail=str(exc))
    conn.close()
    return RedirectResponse(_back(request), status_code=303)


@app.post("/draft/{draft_id}/approve")
def approve(request: Request, draft_id: int):
    return _transition(request, draft_id, "approved")


@app.post("/draft/{draft_id}/flag")
def flag(request: Request, draft_id: int, note: str = Form("")):
    return _transition(request, draft_id, "rejected", note=note or None)


@app.post("/draft/{draft_id}/publish")
def publish(request: Request, draft_id: int):
    return _transition(request, draft_id, "published")


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
    return RedirectResponse(f"/draft/{draft_id}", status_code=303)


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


@app.get("/vault")
def vault_page(request: Request, q: str = "", tag: str = ""):
    conn = _conn()
    rows = vault.search(conn, term=q or None, tag=tag or None)
    conn.close()
    return templates.TemplateResponse(
        "vault.html",
        {"request": request, "title": "Vault", "rows": rows, "q": q, "tag": tag},
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
    outcomes = conn.execute(
        """
        SELECT o.*, r.name AS resident
        FROM outcomes o JOIN residents r ON r.id = o.resident_id
        ORDER BY o.id DESC LIMIT 20
        """
    ).fetchall()
    conn.close()
    return templates.TemplateResponse(
        "ledger.html",
        {
            "request": request,
            "title": "Ledger",
            "rows": rows,
            "per_resident": per_resident,
            "outcomes": outcomes,
        },
    )