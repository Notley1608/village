"""Scout + Actuary: rank caller-supplied signals into vault nuggets.

No network calls live here — real source fetching (GitHub/Reddit/YouTube
trends) is wired up later. `mine_topics` takes plain signal dicts so it can
be tested and reasoned about without hitting live services.
"""
from core import vault

RISK_KEYWORDS = {"copyrighted", "trademarked", "scrape_tos_violation", "counterfeit"}


def score_signal(signal: dict) -> dict:
    """Actuary: cheap profitability/risk scorecard for one signal.

    profitability_score is est. MRR per dollar of cost, clamped to 0-10.
    verdict is "fail" if any risk flag fires or the score is too low to bother.
    """
    cost = float(signal.get("estimated_cost_usd", 0.0))
    mrr = float(signal.get("est_mrr_usd", 0.0))
    score = max(0.0, min(10.0, mrr / (cost + 1.0)))

    risk_flags = sorted(RISK_KEYWORDS.intersection(signal.get("risk_keywords", [])))

    return {
        "profitability_score": round(score, 2),
        "risk_flags": risk_flags,
        "verdict": "fail" if risk_flags or score < 1.0 else "pass",
    }


def audit_signals(signals) -> list:
    """The Auditor: score every signal and return (signal, scorecard) pairs,
    best-first, so a Go/No-Go decision is visible for each one — not just
    the survivors."""
    scored = [(s, score_signal(s)) for s in signals]
    return sorted(scored, key=lambda pair: pair[1]["profitability_score"], reverse=True)


def mine_topics(conn, signals, resident_id=None) -> list:
    """Score `signals`, keep the ones that pass, write them to the vault as
    nuggets ranked best-first. Returns the created nugget ids in rank order."""
    passing = [pair for pair in audit_signals(signals) if pair[1]["verdict"] == "pass"]

    nugget_ids = []
    for signal, scorecard in passing:
        risk = ", ".join(scorecard["risk_flags"]) or "none"
        body = (
            f"{signal.get('summary', '')}\n\n"
            f"Score: {scorecard['profitability_score']}/10. Risk: {risk}."
        ).strip()
        nugget_ids.append(
            vault.add_nugget(
                conn,
                signal["title"],
                body,
                tags=signal.get("tags"),
                source_url=signal.get("url"),
                resident_id=resident_id,
            )
        )
    return nugget_ids
