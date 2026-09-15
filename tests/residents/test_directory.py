import pytest

from core import db, queue
from residents import directory
from web.seed import seed_residents


@pytest.fixture
def conn(tmp_path):
    path = str(tmp_path / "store.sqlite")
    db.init_db(path)
    c = db.connect(path)
    seed_residents(conn=c)
    return c


def test_module_exposes_produce():
    assert callable(directory.produce)


def test_launch_budget_geometry(cfg):
    d = [r for r in cfg["residents"] if r["name"] == "directory"][0]
    assert d["launch_volume"]["money_pages"] == 10
    assert d["launch_volume"]["hub_pages"] == 5


def test_seed_use_case_populates_vault(conn):
    created = directory.seed_use_case(conn, keywords=["AI code review"], tools=[{"name": "ReviewBot", "url": "https://reviewbot.example", "pitch": "Static analysis", "pricing": "Free", "free_tier": True}])
    assert len(created) == 2
    tools = directory._tools_map(conn, directory._resident_id(conn))
    assert ["ReviewBot"] == [t["name"] for t in tools]
    assert tools[0]["url"] == "https://reviewbot.example"


def test_research_offline_seeds_default_keywords(conn):
    directory.research_use_case(conn, run_live=False)
    rid = directory._resident_id(conn)
    keywords = directory.vault.search(conn, tag="keyword", resident_id=rid)
    assert len(keywords) == 8
    assert any(k["body"] == "AI meeting notes" for k in keywords)


def test_produce_creates_money_and_hub(conn):
    directory.seed_use_case(conn)
    created = directory.produce(conn)
    kinds = [
        conn.execute("SELECT kind FROM drafts WHERE id = ?", (i,)).fetchone()["kind"]
        for i in created
    ]
    assert kinds[0] == "money_page"
    assert kinds[-1] == "hub_page"
    total = conn.execute("SELECT COUNT(*) AS n FROM drafts").fetchone()["n"]
    assert total == len(created) == 8 + 1
    payload = conn.execute(
        "SELECT payload FROM drafts WHERE id = ?", (created[0],)
    ).fetchone()["payload"]
    assert "AI meeting notes" in payload
    assert "Verdict" in payload


def test_produce_rejects_without_research(conn):
    with pytest.raises(RuntimeError):
        directory.produce(conn)


def test_produce_respects_limit(conn):
    directory.seed_use_case(conn)
    created = directory.produce(conn, limit=3)
    assert len(created) == 4  # 3 money + 1 hub


def test_published_drafts_feed_build(conn):
    directory.seed_use_case(conn)
    created = directory.produce(conn, limit=1)
    rid = directory._resident_id(conn)
    for draft_id in created:
        queue.transition(conn, draft_id, "approved", actor="human")
        queue.transition(conn, draft_id, "published", actor="human")

    from plumbing import deploy

    pages = deploy.build_site(conn, str(tmp_pages(conn)), site_name="TestDeck", site_url="https://test.example")
    assert len(pages) >= 2


def tmp_pages(conn):
    import tempfile
    return tempfile.mkdtemp()


def test_money_page_injects_affiliate_links():
    tools = [{"name": "Songbird", "pitch": "pings", "url": "https://songbird.example", "pricing": "Free", "free_tier": True}]
    affiliate = {"Songbird": "https://songbird.example?ref=xyz"}
    body = directory._money_page("AI meeting notes", tools, "https://s.example", affiliate)
    assert "songbird.example?ref=xyz" in body
    assert "affiliate tag may earn us a commission" in body


def test_money_page_falls_back_without_affiliate():
    tools = [{"name": "Songbird", "pitch": "pings", "url": "https://songbird.example", "pricing": "", "free_tier": True}]
    body = directory._money_page("AI meeting notes", tools, "https://s.example", {})
    assert "[https://songbird.example](https://songbird.example)" in body
    assert "ref=" not in body


def test_produce_is_idempotent(conn):
    directory.seed_use_case(conn)
    first = directory.produce(conn)
    second = directory.produce(conn)
    assert len(first) == 8 + 1
    assert second == []


def test_produce_hub_created_only_once(conn):
    directory.seed_use_case(conn)
    rid = directory._resident_id(conn)
    directory.produce(conn, limit=1)
    directory.produce(conn, limit=1)
    hubs = conn.execute(
        "SELECT COUNT(*) AS n FROM drafts WHERE resident_id = ? AND kind = 'hub_page'",
        (rid,),
    ).fetchone()["n"]
    assert hubs == 1