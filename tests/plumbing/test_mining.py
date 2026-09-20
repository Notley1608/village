from core import vault
from plumbing import mining


def _signal(**overrides):
    signal = {
        "title": "AI resume tailoring niche",
        "summary": "Underserved, low competition.",
        "url": "https://example.com/signal",
        "tags": ["hustle"],
        "estimated_cost_usd": 5.0,
        "est_mrr_usd": 50.0,
    }
    signal.update(overrides)
    return signal


def test_score_signal_profitable_passes():
    scorecard = mining.score_signal(_signal())
    assert scorecard["verdict"] == "pass"
    assert scorecard["profitability_score"] > 1.0
    assert scorecard["risk_flags"] == []


def test_score_signal_low_profitability_fails():
    scorecard = mining.score_signal(_signal(estimated_cost_usd=100.0, est_mrr_usd=10.0))
    assert scorecard["verdict"] == "fail"


def test_score_signal_risk_keyword_fails_even_if_profitable():
    scorecard = mining.score_signal(_signal(risk_keywords=["copyrighted"]))
    assert scorecard["verdict"] == "fail"
    assert scorecard["risk_flags"] == ["copyrighted"]


def test_mine_topics_writes_only_passing_signals(db_conn, resident):
    good = _signal(title="Good idea")
    bad = _signal(title="Bad idea", risk_keywords=["trademarked"])

    ids = mining.mine_topics(db_conn, [good, bad], resident_id=resident["id"])

    assert len(ids) == 1
    hits = vault.search(db_conn, resident_id=resident["id"])
    assert len(hits) == 1
    assert hits[0]["title"] == "Good idea"


def test_mine_topics_ranks_best_score_first(db_conn, resident):
    low = _signal(title="Low", est_mrr_usd=10.0, estimated_cost_usd=5.0)
    high = _signal(title="High", est_mrr_usd=100.0, estimated_cost_usd=1.0)

    ids = mining.mine_topics(db_conn, [low, high], resident_id=resident["id"])

    titles = [
        db_conn.execute("SELECT title FROM nuggets WHERE id = ?", (nid,)).fetchone()["title"]
        for nid in ids
    ]
    assert titles == ["High", "Low"]


def test_mine_topics_no_signals_writes_nothing(db_conn, resident):
    assert mining.mine_topics(db_conn, [], resident_id=resident["id"]) == []
