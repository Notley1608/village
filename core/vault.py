from .db import connect


def add_nugget(conn, title, body, tags=None, source_url=None, resident_id=None):
    cur = conn.execute(
        "INSERT INTO nuggets (resident_id, title, body, tags, source_url) VALUES (?, ?, ?, ?, ?)",
        (resident_id, title, body, ",".join(tags or []), source_url),
    )
    conn.commit()
    return cur.lastrowid


def search(conn, term=None, tag=None, resident_id=None):
    sql = "SELECT * FROM nuggets WHERE 1=1"
    params = []
    to_add = []
    if term:
        sql += " AND (title LIKE ? OR body LIKE ?)"
        to_add += [f"%{term}%", f"%{term}%"]
    if tag:
        sql += " AND tags LIKE ?"
        to_add.append(f"%{tag}%")
    if resident_id is not None:
        sql += " AND resident_id = ?"
        to_add.append(resident_id)
    sql += " ORDER BY created_at DESC"
    params = to_add
    return conn.execute(sql, params).fetchall()


def add_polish_note(conn, draft_id, nugget_id, note, copied_back=0):
    cur = conn.execute(
        "INSERT INTO polish_notes (draft_id, nugget_id, note, copied_back) VALUES (?, ?, ?, ?)",
        (draft_id, nugget_id, note, copied_back),
    )
    conn.commit()
    return cur.lastrowid