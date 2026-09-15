import pytest

from core import config, db


@pytest.fixture
def db_conn(tmp_path):
    path = str(tmp_path / "test.sqlite")
    db.init_db(path)
    conn = db.connect(path)
    yield conn
    conn.close()


@pytest.fixture
def cfg():
    return config.load_config()


@pytest.fixture
def resident(db_conn):
    cur = db_conn.execute(
        "INSERT INTO residents (name, zone, niche, status, daily_cap_usd, launch_budget_days) "
        "VALUES ('test_resident', 'clean', 'test', 'active', 0.0, 0)"
    )
    db_conn.commit()
    return {"id": cur.lastrowid, "name": "test_resident"}