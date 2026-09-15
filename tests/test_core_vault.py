from core import vault


def test_add_and_find_by_term(db_conn, resident):
    vault.add_nugget(
        db_conn,
        "Gemini Flash free tier",
        "Runs free up to a generous quota.",
        tags=["ai", "cost"],
        source_url="https://aistudio.google.com",
        resident_id=resident["id"],
    )
    hits = vault.search(db_conn, term="quota")
    assert len(hits) == 1
    assert hits[0]["title"] == "Gemini Flash free tier"


def test_find_by_tag(db_conn, resident):
    vault.add_nugget(db_conn, "YPP threshold", "10M views in 90 days.", tags=["youtube", "money"])
    vault.add_nugget(db_conn, "AdSense RPM", "US-first English wins.", tags=["adsense", "money"])
    hits = vault.search(db_conn, tag="money")
    assert len(hits) == 2


def test_filter_by_resident(db_conn, resident):
    other = _other_resident(db_conn)
    a = vault.add_nugget(db_conn, "A", "body a", resident_id=resident["id"])
    vault.add_nugget(db_conn, "B", "body b", resident_id=other)
    hits = vault.search(db_conn, resident_id=resident["id"])
    assert [n["id"] for n in hits] == [a]


def test_source_url_persisted(db_conn, resident):
    vault.add_nugget(
        db_conn,
        "N",
        "body",
        source_url="https://example.com/source",
        resident_id=resident["id"],
    )
    row = db_conn.execute("SELECT source_url FROM nuggets WHERE title = 'N'").fetchone()
    assert row["source_url"] == "https://example.com/source"


def test_polish_note_copyback(db_conn, resident):
    from core import queue

    nugget_id = vault.add_nugget(db_conn, "T", "b", resident_id=resident["id"])
    draft_id = queue.create_draft(db_conn, resident["id"], "test_draft", "{}", nugget_id=nugget_id)
    vault.add_polish_note(db_conn, draft_id, nugget_id, "lead with the number", copied_back=0)
    rows = db_conn.execute(
        "SELECT note, copied_back FROM polish_notes WHERE draft_id = ?",
        (draft_id,),
    ).fetchall()
    assert rows[0]["note"] == "lead with the number"
    assert rows[0]["copied_back"] == 0


def _other_resident(db_conn):
    cur = db_conn.execute(
        "INSERT INTO residents (name, zone, niche, status, daily_cap_usd, launch_budget_days) "
        "VALUES ('other', 'gray', 'test', 'active', 0.0, 0)"
    )
    db_conn.commit()
    return cur.lastrowid