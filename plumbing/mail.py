import imaplib
import os
import re
import smtplib
import sys
from datetime import datetime
from email import message_from_bytes
from email.message import EmailMessage
from html import escape

from dotenv import load_dotenv

from core import db, queue

load_dotenv()

MAIL_USER = os.environ.get("MAIL_USER", "")
MAIL_TO = os.environ.get("MAIL_TO", MAIL_USER)
MAIL_FROM = os.environ.get("MAIL_FROM", MAIL_USER)
IMAP_SERVER = os.environ.get("MAIL_IMAP_SERVER", "imap.gmail.com")
SMTP_SERVER = os.environ.get("MAIL_SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("MAIL_SMTP_PORT", "587"))

MAILBOX = "INBOX"

COMMAND_RE = re.compile(r"(?im)^\s*(approve|flag)\s+(\d+)(.*)$")

KIND_LABELS = {
    "resume_rewrite": "Resume rewrite",
    "linkedin_summary": "LinkedIn summary",
    "cover_letter": "Cover letter",
    "money_page": "Money page",
}


def app_password():
    return os.environ.get("MAIL_APP_PASSWORD", "").replace(" ", "")


def parse_command(body):
    match = COMMAND_RE.search(body)
    if not match:
        return None
    action = match.group(1).lower()
    draft_id = int(match.group(2))
    note = match.group(3).strip() if action == "flag" else None
    return action, draft_id, note


def apply_command(conn, action, draft_id, note=None):
    if action == "approve":
        event = "approved"
    elif action == "flag":
        event = "rejected"
    else:
        raise ValueError(action)
    queue.transition(conn, draft_id, event, actor="human", note=note)


def _kind_label(kind):
    return KIND_LABELS.get(kind, kind.replace("_", " ").title())


def _resident_name(draft):
    if "resident_name" in draft.keys():
        return draft["resident_name"]
    return f"resident {draft['resident_id']}"


def _snippet(payload, length=200):
    text = " ".join((payload or "").split())
    if len(text) <= length:
        return text
    return text[: length - 1].rstrip() + "…"


def _format_time(created_at):
    try:
        parsed = datetime.fromisoformat(created_at.replace(" ", "T"))
        return parsed.strftime("%b %d, %Y %H:%M")
    except (ValueError, AttributeError):
        return str(created_at or "")


def digest_body(drafts):
    if not drafts:
        return "No drafts waiting for review."
    parts = [f"Village review digest — {len(drafts)} draft(s) to review", ""]
    for index, draft in enumerate(drafts, 1):
        label = _kind_label(draft["kind"])
        created = _format_time(draft["created_at"])
        parts.append(
            f"{index}. #{draft['id']} {label} — {_resident_name(draft)} (created {created})"
        )
        parts.append("")
        snippet = _snippet(draft["payload"] or "")
        parts.append(snippet if snippet else "(empty draft)")
        parts.append("")
        parts.append(f"   Approve: approve {draft['id']}   |   Flag: flag {draft['id']} <note>")
        parts.append("")
    parts.append("Nothing ships without your call.")
    return "\n".join(parts)


def html_body(drafts):
    if not drafts:
        return "<p>No drafts waiting for review.</p>"
    cards = []
    for draft in drafts:
        label = escape(_kind_label(draft["kind"]))
        snippet = escape(_snippet(draft["payload"] or ""))
        created = _format_time(draft["created_at"])
        name = escape(_resident_name(draft))
        cards.append(
            f'<div style="border:1px solid #e3e6ea;border-left:4px solid #d9772f;'
            f'border-radius:10px;padding:12px 14px;margin:0 0 12px;">'
            f'<div style="font-weight:700;font-size:14px;">#{draft["id"]} {label} '
            f'<span style="color:#7a8494;font-weight:400;">— {name} · {created}</span></div>'
            f'<div style="margin:8px 0;color:#38414f;font-size:13px;line-height:1.5;">'
            f'{snippet or "(empty draft)"}</div>'
            f'<div style="font-size:12px;color:#57616f;">'
            f'<b style="color:#1e7a44;">Approve:</b> <code>approve {draft["id"]}</code>'
            f' &nbsp; <b style="color:#b91c1c;">Flag:</b> <code>flag {draft["id"]} &lt;note&gt;</code>'
            f"</div></div>"
        )
    heading = f"Village review digest — {len(drafts)} draft(s) to review"
    footer = (
        '<p style="color:#57616f;font-size:12px;">Nothing ships without your call. '
        'Reply <code>approve &lt;id&gt;</code> or <code>flag &lt;id&gt; &lt;note&gt;</code> '
        "to review by email.</p>"
    )
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'max-width:640px;margin:0 auto;padding:16px;">'
        f'<h2 style="font-size:16px;color:#1c2430;">{heading}</h2>'
        + "".join(cards)
        + footer
        + "</div>"
    )


def send(subject, body, to=None, html=None):
    if not MAIL_USER or not app_password():
        raise RuntimeError("Set MAIL_USER and MAIL_APP_PASSWORD in .env")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = MAIL_FROM
    message["To"] = to or MAIL_TO
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(MAIL_USER, app_password())
        server.send_message(message)


def _pending_drafts(conn):
    return conn.execute(
        """
        SELECT d.*, r.name AS resident_name
        FROM drafts d JOIN residents r ON r.id = d.resident_id
        WHERE d.status = 'pending'
        ORDER BY d.created_at
        """
    ).fetchall()


def send_digest():
    conn = db.connect()
    drafts = _pending_drafts(conn)
    conn.close()
    if not drafts:
        return 0
    send(
        f"Village digest: {len(drafts)} draft(s) awaiting review",
        digest_body(drafts),
        html=html_body(drafts),
    )
    return len(drafts)


def _is_processed(conn, uid, mailbox=MAILBOX):
    row = conn.execute(
        "SELECT 1 FROM processed_emails WHERE mailbox = ? AND uid = ?", (mailbox, uid)
    ).fetchone()
    return row is not None


def _mark_processed(conn, uid, mailbox=MAILBOX):
    conn.execute(
        "INSERT OR IGNORE INTO processed_emails (mailbox, uid) VALUES (?, ?)",
        (mailbox, uid),
    )
    conn.commit()


def _decode_bytes(raw):
    message = message_from_bytes(raw)
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
                return ""
    payload = message.get_payload(decode=True)
    return payload.decode("utf-8", errors="replace") if payload else ""


def poll_commands(limit=20):
    if not MAIL_USER or not app_password():
        raise RuntimeError("Set MAIL_USER and MAIL_APP_PASSWORD in .env")
    handled = []
    with imaplib.IMAP4_SSL(IMAP_SERVER) as server:
        server.login(MAIL_USER, app_password())
        server.select(MAILBOX)
        typ, data = server.search(None, "ALL")
        if typ != "OK":
            return handled
        uids = data[0].split()
        if not uids:
            return handled
        conn = db.connect()
        try:
            for raw in uids[-limit:]:
                uid = int(raw)
                if _is_processed(conn, uid):
                    continue
                typ, msg = server.fetch(str(uid), "(BODY.PEEK[])")
                if typ == "OK" and msg and msg[0][1]:
                    body = _decode_bytes(msg[0][1])
                    command = parse_command(body)
                    if command:
                        action, draft_id, note = command
                        apply_command(conn, action, draft_id, note)
                        handled.append((uid, action, draft_id))
                _mark_processed(conn, uid)
        finally:
            conn.close()
            server.close()
    return handled


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "digest"
    try:
        if mode == "digest":
            print(f"digest sent, drafts: {send_digest()}")
        elif mode == "poll":
            print(f"processed {len(poll_commands())} command(s)")
        else:
            print(f"usage: python -m plumbing.mail [digest|poll]", file=sys.stderr)
            sys.exit(2)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()