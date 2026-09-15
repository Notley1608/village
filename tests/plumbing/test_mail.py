from core import queue
from plumbing import mail


def test_app_password_strips_spaces(monkeypatch):
    monkeypatch.setenv("MAIL_APP_PASSWORD", "fmfk nskn jnrs lsbb")
    assert mail.app_password() == "fmfknsknjnrslsbb"


def test_app_password_missing_is_empty(monkeypatch):
    monkeypatch.delenv("MAIL_APP_PASSWORD", raising=False)
    assert mail.app_password() == ""


def test_parse_approve():
    assert mail.parse_command("approve 3\n") == ("approve", 3, None)


def test_parse_flag_with_note():
    result = mail.parse_command("flag 12 the hook is weak")
    assert result == ("flag", 12, "the hook is weak")


def test_parse_case_insensitive_and_embedded():
    result = mail.parse_command("Hi all!\nApprove 7\nthanks")
    assert result == ("approve", 7, None)


def test_parse_ignores_unrelated_mail():
    assert mail.parse_command("No commands in here.") is None


def test_apply_approve_transitions(db_conn, resident):
    draft_id = queue.create_draft(db_conn, resident["id"], "test_draft", "{}")
    mail.apply_command(db_conn, "approve", draft_id)
    row = db_conn.execute("SELECT status FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    assert row["status"] == "approved"


def test_apply_flag_records_reject_and_note(db_conn, resident):
    draft_id = queue.create_draft(db_conn, resident["id"], "test_draft", "{}")
    mail.apply_command(db_conn, "flag", draft_id, note="weak angle")
    row = db_conn.execute("SELECT status FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    assert row["status"] == "rejected"
    event = db_conn.execute(
        "SELECT note FROM queue_events WHERE draft_id = ? AND event = 'rejected'",
        (draft_id,),
    ).fetchone()
    assert event["note"] == "weak angle"


def test_digest_body_lists_pending(db_conn, resident):
    queue.create_draft(db_conn, resident["id"], "money_page", "The ten best AI widgets for freelancers in 2026.")
    drafts = db_conn.execute(
        """
        SELECT d.*, r.name AS resident_name
        FROM drafts d JOIN residents r ON r.id = d.resident_id
        WHERE d.status = 'pending' ORDER BY d.created_at
        """
    ).fetchall()
    body = mail.digest_body(drafts)
    assert "1 draft(s) to review" in body
    assert "Money page" in body
    assert f"— test_resident (created " in body
    assert "approve 1" in body
    assert "flag 1 <note>" in body


def test_digest_body_empty():
    assert mail.digest_body([]) == "No drafts waiting for review."


def test_html_body_renders_cards_and_escapes(db_conn, resident):
    queue.create_draft(db_conn, resident["id"], "cover_letter", '<script>alert("x")</script> sample')
    drafts = db_conn.execute("SELECT * FROM drafts WHERE status = 'pending'").fetchall()
    html = mail.html_body(drafts)
    assert "Cover letter" in html
    assert "test_resident" in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "approve 1</code>" in html


def test_snippet_truncates():
    assert mail._snippet("a" * 500, length=200).endswith("…")
    assert len(mail._snippet("a" * 500, length=200)) == 200


def test_kind_label_fallback():
    assert mail._kind_label("resume_rewrite") == "Resume rewrite"
    assert mail._kind_label("unknown_thing") == "Unknown Thing"


def test_processed_marking_is_idempotent(db_conn):
    assert mail._is_processed(db_conn, 100) is False
    mail._mark_processed(db_conn, 100)
    mail._mark_processed(db_conn, 100)
    assert mail._is_processed(db_conn, 100) is True
    rows = db_conn.execute(
        "SELECT COUNT(*) AS n FROM processed_emails WHERE uid = 100"
    ).fetchone()
    assert rows["n"] == 1