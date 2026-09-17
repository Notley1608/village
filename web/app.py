import os

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core import config as core_config
from core import db, queue, vault
from core import ledger
from residents import shorts
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
    if path.startswith("/agents"):
        return "agents"
    if path.startswith("/queue") or path.startswith("/draft"):
        return "queue"
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
          CAST(julianday('now') - julianday(r.launch_start_date) AS INTEGER)                    AS launch_days_used,
          COALESCE(r.proven, 0)                                                                AS proven,
          COALESCE(r.format, '[]')                                                             AS format
        FROM residents r
        ORDER BY r.id
        """
    ).fetchall()


def _scope_kinds(cfg, name, workstream):
    if not workstream:
        return None
    for ws in core_config.workstreams_of(cfg, name):
        if ws["name"] == workstream:
            return ws["kinds"]
    return []


def _queue_rows(conn, status, resident_id=None, kinds=None, q=""):
    sql = (
        "SELECT d.*, r.name AS resident_name "
        "FROM drafts d JOIN residents r ON r.id = d.resident_id WHERE d.status = ?"
    )
    params = [status]
    if resident_id is not None:
        sql += " AND d.resident_id = ?"
        params.append(resident_id)
    if kinds is not None:
        sql += f" AND d.kind IN ({','.join('?' * len(kinds))})"
        params += list(kinds)
    if q:
        sql += " AND (d.payload LIKE ? OR CAST(d.id AS TEXT) = ?)"
        params += [f"%{q}%", q.strip()]
    sql += " ORDER BY d.id DESC"
    return conn.execute(sql, params).fetchall()


def _draft_counts_by_status(conn, resident_id=None, kinds=None):
    sql = "SELECT status, COUNT(*) AS n FROM drafts WHERE 1=1"
    params = []
    if resident_id is not None:
        sql += " AND resident_id = ?"
        params.append(resident_id)
    if kinds is not None:
        sql += f" AND kind IN ({','.join('?' * len(kinds))})"
        params += list(kinds)
    sql += " GROUP BY status"
    return {r["status"]: r["n"] for r in conn.execute(sql, params).fetchall()}


def _workstream_summary(conn, cfg, name, rid):
    ws_list = core_config.workstreams_of(cfg, name)
    covered = set()
    out = []
    for ws in ws_list:
        counts = _draft_counts_by_status(conn, rid, ws["kinds"])
        out.append((ws, counts))
        covered.update(ws["kinds"])
    kinds_in_db = [
        r["kind"]
        for r in conn.execute(
            "SELECT DISTINCT kind FROM drafts WHERE resident_id = ?", (rid,)
        ).fetchall()
    ]
    other = [k for k in kinds_in_db if k not in covered]
    if other:
        out.append(({"name": "Other", "kinds": other}, _draft_counts_by_status(conn, rid, other)))
    return out


def _agent_income(conn, rid):
    return conn.execute(
        "SELECT COALESCE(SUM(value), 0) AS s FROM outcomes "
        "WHERE resident_id = ? AND metric IN ('revenue_usd', 'profit_usd')",
        (rid,),
    ).fetchone()["s"]


@app.get("/agents")
def agents_page(request: Request):
    conn = _conn()
    residents = _residents_with_counts(conn)
    conn.close()
    return render(
        request,
        "agents.html",
        title="Agents",
        breadcrumb="<b>Agents</b>",
        residents=residents,
    )


@app.get("/agents/{name}")
def agent_page(request: Request, name: str):
    cfg = core_config.load_config()
    conn = _conn()
    try:
        r_cfg = core_config.resident_by_name(cfg, name)
    except KeyError:
        conn.close()
        raise HTTPException(status_code=404, detail="agent not found")
    resident = conn.execute(
        "SELECT * FROM residents WHERE name = ?", (name,)
    ).fetchone()
    if resident is None:
        conn.close()
        raise HTTPException(status_code=404, detail="agent not seeded")
    rid = resident["id"]
    counts = _draft_counts_by_status(conn, rid)
    ws_summary = _workstream_summary(conn, cfg, name, rid)
    recent = _queue_rows(conn, "pending", rid, None)
    recent += _queue_rows(conn, "approved", rid, None)
    recent = sorted(recent, key=lambda d: d["id"], reverse=True)[:8]
    vault_rows = conn.execute(
        "SELECT * FROM nuggets WHERE resident_id = ? ORDER BY id DESC", (rid,)
    ).fetchall()
    vault_tags = sorted({
        t.strip()
        for n in vault_rows
        for t in (n["tags"] or "").split(",")
        if t.strip()
    })
    spend_today = conn.execute(
        "SELECT COALESCE(SUM(amount_usd), 0) AS s FROM ledger_entries "
        "WHERE resident_id = ? AND date(created_at) = date('now')",
        (rid,),
    ).fetchone()["s"]
    # `/jobs` and `/job/*` routes removed — resume_studio is no longer a resident,
    # so there is no jobs concept. See `residents/` for the active video-niche residents.
    events = conn.execute(
        """
        SELECT e.*, d.kind AS draft_kind, r.name AS resident_name
        FROM queue_events e
        JOIN drafts d ON d.id = e.draft_id
        JOIN residents r ON r.id = d.resident_id
        WHERE d.resident_id = ?
        ORDER BY e.id DESC LIMIT 12
        """,
        (rid,),
    ).fetchall()
    agent_income = _agent_income(conn, rid)
    conn.close()
    return render(
        request,
        "agent.html",
        title=name,
        breadcrumb=f'<a href="/agents">Agents</a> / <b>{name}</b>',
        agent_cfg=r_cfg,
        resident=resident,
        counts=counts,
        workstreams=ws_summary,
        recent=recent,
        vault_rows=vault_rows,
        vault_tags=vault_tags,
        spend_today=spend_today,
        agent_income=agent_income,
        events=events,
    )


@app.get("/agents/{name}/queue")
def agent_queue(request: Request, name: str, status: str = "pending", workstream: str = "", q: str = ""):
    cfg = core_config.load_config()
    conn = _conn()
    try:
        core_config.resident_by_name(cfg, name)
        resident = conn.execute("SELECT * FROM residents WHERE name = ?", (name,)).fetchone()
    except KeyError:
        conn.close()
        raise HTTPException(status_code=404, detail="agent not found")
    if resident is None:
        conn.close()
        raise HTTPException(status_code=404, detail="agent not seeded")
    kinds = _scope_kinds(cfg, name, workstream)
    rows = _queue_rows(conn, status, resident["id"], kinds, q)
    counts = _draft_counts_by_status(conn, resident["id"], kinds)
    present = [
        r["status"]
        for r in conn.execute("SELECT DISTINCT status FROM drafts ORDER BY status").fetchall()
    ]
    conn.close()
    statuses = present or KNOWN_STATUSES
    if status not in statuses:
        statuses.append(status)
    if status not in counts:
        counts[status] = 0
    return render(
        request,
        "queue.html",
        title=f"{name} queue",
        breadcrumb=f'<a href="/agents">Agents</a> / <a href="/agents/{name}">{name}</a> / <b>Queue</b>',
        agent=name,
        rows=rows,
        status=status,
        statuses=statuses,
        counts=counts,
        q=q,
        workstream=workstream,
        workstreams=core_config.workstreams_of(cfg, name),
        scoped_base=f"/agents/{name}/queue",
    )


@app.get("/agents/{name}/vault")
def agent_vault(request: Request, name: str, q: str = "", tag: str = ""):
    conn = _conn()
    resident = conn.execute("SELECT id FROM residents WHERE name = ?", (name,)).fetchone()
    if resident is None:
        conn.close()
        raise HTTPException(status_code=404, detail="agent not seeded")
    rows = vault.search(conn, term=q or None, tag=tag or None, resident_id=resident["id"])
    conn.close()
    return render(
        request,
        "vault.html",
        title=f"{name} vault",
        breadcrumb=f'<a href="/agents">Agents</a> / <a href="/agents/{name}">{name}</a> / <b>Vault</b>',
        rows=rows,
        q=q,
        tag=tag,
        scoped_base=f"/agents/{name}/vault",
    )


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


def _escalation_list():
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT e.*, r.name AS resident_name FROM escalations e LEFT JOIN residents r ON r.id = e.resident_id ORDER BY e.id DESC"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "kind": r["kind"],
                "status": r["status"],
                "created_at": r["created_at"],
                "resident_name": r["resident_name"] or "",
                "source": "dashboard",
            }
            for r in rows
        ]
    finally:
        conn.close()


@app.get("/escalations")
def escalations_page(request: Request):
    return render(
        request,
        "escalations.html",
        title="Escalations",
        breadcrumb="<b>Escalations</b>",
        escalations=_escalation_list(),
    )


@app.post("/escalations/{esc_id}/approve")
def approve_escalation(request: Request, esc_id: int):
    conn = _conn()
    try:
        row = conn.execute("SELECT status FROM escalations WHERE id = ?", (esc_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="escalation not found")
        if row["status"] != "pending":
            raise HTTPException(status_code=400, detail="escalation not pending")
        conn.execute("UPDATE escalations SET status = 'approved', resolved_at = datetime('now') WHERE id = ?", (esc_id,))
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse("/escalations?msg=approved&msg_class=ok", status_code=303)


@app.post("/escalations/{esc_id}/deny")
def deny_escalation(request: Request, esc_id: int):
    conn = _conn()
    try:
        row = conn.execute("SELECT status FROM escalations WHERE id = ?", (esc_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="escalation not found")
        if row["status"] != "pending":
            raise HTTPException(status_code=400, detail="escalation not pending")
        conn.execute("UPDATE escalations SET status = 'denied', resolved_at = datetime('now') WHERE id = ?", (esc_id,))
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse("/escalations?msg=denied&msg_class=warn", status_code=303)


@app.get("/escalations/{esc_id}")
def escalation_detail(request: Request, esc_id: int):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT e.*, r.name AS resident_name FROM escalations e LEFT JOIN residents r ON r.id = e.resident_id WHERE e.id = ?",
            (esc_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="escalation not found")
        return render(
            request,
            "escalation_detail.html",
            title=f"Escalation #{esc_id}",
            breadcrumb="<a href='/escalations'>Escalations</a> / <b>#%d</b>" % esc_id,
            esc=dict(row),
        )
    finally:
        conn.close()