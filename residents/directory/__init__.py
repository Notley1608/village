import json
import os
import re
import sys

import google.generativeai as genai
from dotenv import load_dotenv

from core import config as core_config
from core import db, ledger, queue, vault

load_dotenv()

RESIDENT_NAME = "directory"

RESEARCH_PROMPT = """
You are a market researcher for a niche SEO site about AI & automation tools.

Task: research the use case and return STRICT JSON only (no markdown fences, no prose), shaped:
{{
  "keywords": ["keyword phrase", ...],
  "tools": [
    {{"name": "Tool Name", "url": "https://tool.com", "pitch": "one-line pitch", "pricing": "Free / Paid from $X", "free_tier": true}}
  ]
}}

Rules:
- 6-8 keyword phrases real people search to solve this need.
- 10-15 REAL, existing tools. URLs must be official product pages. Never invent tools.
- "pricing" is one short string; free_tier=true when a usable free plan exists.
- Return ONLY the JSON object.

Use case: {use_case}
"""


def _dir_cfg(cfg):
    for r in cfg["residents"]:
        if r["name"] == RESIDENT_NAME:
            return r
    raise KeyError(RESIDENT_NAME)


def _resident_id(conn):
    row = conn.execute(
        "SELECT id FROM residents WHERE name = ?", (RESIDENT_NAME,)
    ).fetchone()
    if row is None:
        raise RuntimeError(f"resident '{RESIDENT_NAME}' not seeded; run `python -m web.seed`")
    return row["id"]


def _respond_json(prompt, model):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in .env")
    genai.configure(api_key=api_key)
    text = genai.GenerativeModel(model).generate_content(prompt).text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("model returned no JSON")
    return json.loads(match.group(0))


def seed_use_case(conn, tools=None, keywords=None):
    rid = _resident_id(conn)
    cfg = core_config.load_config()
    d = _dir_cfg(cfg)
    keywords = keywords or d["site"]["money_keywords"]
    tools = tools or [
        {"name": "Mira AI", "url": "https://mira-ai.example", "pitch": "Meeting notes from any call", "pricing": "Free / from $12", "free_tier": True},
        {"name": "TalentPath", "url": "https://talentpath.example", "pitch": "Resume builder with job-tailored tweaks", "pricing": "Free / from $9", "free_tier": True},
    ]
    created = []
    for keyword in keywords:
        created.append(vault.add_nugget(conn, f"keyword: {keyword}", keyword, tags=["keyword"], resident_id=rid))
    for tool in tools:
        body = f"{tool['name']}\n{tool['pitch']}\nPricing: {tool['pricing']}\nFree tier: {tool['free_tier']}\nURL: {tool['url']}"
        created.append(vault.add_nugget(conn, f"tool: {tool['name']}", body, tags=["tool"], source_url=tool["url"], resident_id=rid))
    return created


def research_use_case(conn, run_live=False):
    cfg = core_config.load_config()
    d = _dir_cfg(cfg)
    rid = _resident_id(conn)
    if not run_live:
        return seed_use_case(conn)
    prompt = RESEARCH_PROMPT.format(use_case=d["site"]["tagline"])
    data = _respond_json(prompt, cfg["village"]["model"])
    ledger.record_spend(conn, rid, 0.0, model=cfg["village"]["model"], kind="llm_token_cost")
    tools = [
        {
            "name": t.get("name", ""),
            "url": t.get("url", ""),
            "pitch": t.get("pitch", ""),
            "pricing": t.get("pricing", ""),
            "free_tier": bool(t.get("free_tier")),
        }
        for t in data.get("tools", [])
    ]
    keywords = data.get("keywords") or d["site"]["money_keywords"]
    return seed_use_case(conn, tools=tools, keywords=keywords)


def _tools_map(conn, rid):
    tools = []
    for n in vault.search(conn, tag="tool", resident_id=rid):
        lines = n["body"].splitlines()
        tools.append(
            {
                "name": n["title"].replace("tool: ", "", 1),
                "pitch": lines[1] if len(lines) > 1 else n["title"],
                "url": (n["source_url"] or "").strip(),
                "pricing": " / ".join(l.replace("Pricing: ", "") for l in lines if l.startswith("Pricing:")),
                "free_tier": any("Free tier: true" in l for l in lines),
            }
        )
    return tools


def _money_page(keyword, tools, site_url, affiliate_links=None):
    affiliate_links = affiliate_links or {}
    slug = keyword.lower().replace(" ", "-")
    out = [
        f"# The best AI tools for {keyword} (2026)",
        "",
        f"Need {keyword} done right? Here are the tools worth your time, what each really "
        "excels at, and who should upgrade to a paid plan.",
        "",
        "## What to look for",
        "",
        "Judge a tool on output quality, how much it removes from your workflow, and whether "
        "the free tier covers realistic use. We favour tools with genuinely usable free plans.",
        "",
        "## The tools",
        "",
    ]
    for t in tools:
        url = t["url"] or f"https://example.com/{t['name'].lower().replace(' ', '-')}"
        link = affiliate_links.get(t["name"]) or url
        line = f"- **{t['name']}** — {t['pitch']} — [{url}]({link})"
        if t["pricing"]:
            line += f" ({t['pricing']})"
        out.append(line)
    out += [
        "",
        "## Verdict",
        "",
        f"Start free and upgrade only when {keyword} becomes a daily workflow. Try two or "
        "three tools, then keep the one that sticks. All tools above are linked externally; "
        "links marked with our affiliate tag may earn us a commission at no extra cost to you.",
    ]
    return "\n".join(out)


def _hub_page(keywords):
    out = [
        "# AI & automation tools by use case",
        "",
        "I compare AI and automation tools, organised by use case so you can find the right "
        "one without the noise.",
        "",
        "## Browse by use case",
        "",
    ]
    for kw in keywords:
        slug = kw.lower().replace(" ", "-")
        out.append(f"- [{kw}](/pages/{slug}.html) — best tools ranked")
    out.append("")
    out.append("Every page is researched and checked by a human before publish.")
    return "\n".join(out)


def _drafted_keyword_slugs(conn, rid):
    rows = conn.execute(
        "SELECT payload FROM drafts WHERE resident_id = ? AND kind = 'money_page'",
        (rid,),
    ).fetchall()
    slugs = set()
    for row in rows:
        first = (row["payload"] or "").splitlines()[0].strip()
        match = re.match(r"^#\s+The best AI tools for (.+?) \(2026\)$", first)
        if match:
            slugs.add(match.group(1).strip().lower())
    return slugs


def produce(conn, run_llm=False, limit=None):
    cfg = core_config.load_config()
    d = _dir_cfg(cfg)
    rid = _resident_id(conn)
    keywords = [n["body"] for n in vault.search(conn, tag="keyword", resident_id=rid)]
    tools = _tools_map(conn, rid)
    if not keywords or not tools:
        raise RuntimeError("no research in vault; run `python -m residents.directory research` first")

    launch = d.get("launch_volume", {})
    money_target = limit if limit is not None else int(launch.get("money_pages", 10) or 10)
    money_target = int(money_target)
    affiliate_links = d["site"].get("affiliate_links", {}) or {}
    drafted = _drafted_keyword_slugs(conn, rid)

    created = []
    count = 0
    for kw in keywords:
        if kw.lower() in drafted:
            continue
        if count >= int(money_target):
            break
        payload = _money_page(kw, tools, d["site"].get("url", ""), affiliate_links)
        if run_llm:
            ledger.record_spend(conn, rid, 0.0, model=cfg["village"]["model"], kind="llm_token_cost")
        created.append(queue.create_draft(conn, rid, "money_page", payload))
        count += 1

    if launch.get("hub_pages", 0):
        existing_hub = conn.execute(
            "SELECT 1 FROM drafts WHERE resident_id = ? AND kind = 'hub_page'",
            (rid,),
        ).fetchone()
        if existing_hub is None:
            hub = _hub_page([k for k in keywords][: int(money_target)])
            if run_llm:
                ledger.record_spend(conn, rid, 0.0, model=cfg["village"]["model"], kind="llm_token_cost")
            created.append(queue.create_draft(conn, rid, "hub_page", hub))
    return created


def main():
    args = sys.argv[1:]
    command = args[0] if args else "help"
    conn = db.connect()
    try:
        if command == "research":
            created = research_use_case(conn, run_live="--llm" in args)
            print(f"seeded {len(created)} research nuggets")
        elif command == "draft":
            created = produce(conn, run_llm="--llm" in args)
            print(f"created drafts: {', '.join('#' + str(i) for i in created)}")
        else:
            print("usage: python -m residents.directory [research|draft] [--llm]")
    finally:
        conn.close()


if __name__ == "__main__":
    main()