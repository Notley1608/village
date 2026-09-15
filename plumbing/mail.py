import imaplib
import os
import re
import smtplib
import sys
from email import message_from_bytes
from email.message import EmailMessage

from dotenv import load_dotenv

from core import db, queue

load_dotenv()

MAIL_USER = os.environ.get("MAIL_USER", "")
MAIL_APP_PASSWORD = os.environ.get("MAIL_APP_PASSWORD", "")
MAIL_TO = os.environ.get("MAIL_TO", MAIL_USER)
MAIL_FROM = os.environ.get("MAIL_FROM", MAIL_USER)
IMAP_SERVER = os.environ.get("MAIL_IMAP_SERVER", "imap.gmail.com")
SMTP_SERVER = os.environ.get("MAIL_SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("MAIL_SMTP_PORT", "587"))

MAILBOX = "INBOX"

COMMAND_RE = re.compile(r"(?im)^\s*(approve|flag)\s+(\d+)(.*)$")


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


def digest_body(drafts):
    if not drafts:
        return "No drafts waiting for review."
    parts = ["Village review digest", ""]
    for draft in drafts:
        snippet = (draft["payload"] or "")[:300].replace("\n", " ")
        parts.append(f"[DRAFT {draft['id']}] {draft['kind']} | resident {draft['resident_id']}")
        parts.append(snippet)
        parts.append(f"Reply: approve {draft['id']} | flag {draft['id']} <rework note>")
        parts.append("")
    parts.append("Reply 'approve <id>' or 'flag <id> <rework note>'.")
    return "\n".join(parts)


def send(subject, body, to=None):
    if not MAIL_USER or not MAIL_APP_PASSWORD:
        raise RuntimeError("Set MAIL_USER and MAIL_APP_PASSWORD in .env")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = MAIL_FROM
    message["To"] = to or MAIL_TO
    message.set_content(body)
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(MAIL_USER, MAIL_APP_PASSWORD)
        server.send_message(message)


def _pending_drafts(conn):
    return conn.execute(
        "SELECT * FROM drafts WHERE status = 'pending' ORDER BY created_at"
    ).fetchall()


def send_digest():
    conn = db.connect()
    drafts = _pending_drafts(conn)
    conn.close()
    if not drafts:
        return 0
    send(f"Village digest: {len(drafts)} draft(s) awaiting review", digest_body(drafts))
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
    if not MAIL_USER or not MAIL_APP_PASSWORD:
        raise RuntimeError("Set MAIL_USER and MAIL_APP_PASSWORD in .env")
    handled = []
    with imaplib.IMAP4_SSL(IMAP_SERVER) as server:
        server.login(MAIL_USER, MAIL_APP_PASSWORD)
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