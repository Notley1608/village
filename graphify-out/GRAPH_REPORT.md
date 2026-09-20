# Graph Report - village  (2026-09-20)

## Corpus Check
- Corpus is ~19,248 words - fits in a single context window. You may not need a graph.

## Summary
- 408 nodes · 845 edges · 27 communities (17 shown, 10 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 15 edges (avg confidence: 0.85)
- Token cost: 176,789 input · 0 output

## Community Hubs (Navigation)
- Database & Draft Queue Core
- Scheduler & Dispatch
- FastAPI Dashboard Routes
- Email Digest & Mail
- Config Loading
- Content Residents & Monetization
- Governance Principles
- Ledger & DB (Tests)
- Ledger Spend Tracking
- Obsidian Vault Integration
- Site Build & Deploy
- Core Runtime Overview
- Dashboard Templates
- Queue State Machine Tests
- Markdown Rendering JS
- Web Dependencies
- Plumbing Module Overview
- Build Phases & Scaling Rule
- Email Polling (IMAP)
- Uvicorn Entrypoint
- Instagram Reels Channel
- TikTok Creator Channel
- Resident Registry Config
- SQLite Store File
- DB Init Command
- Login Template

## God Nodes (most connected - your core abstractions)
1. `connect()` - 28 edges
2. `_conn()` - 18 edges
3. `create_draft()` - 15 edges
4. `render()` - 15 edges
5. `daily_dispatch()` - 13 edges
6. `seed_residents()` - 13 edges
7. `Tooldeck index page (AI tools by use case)` - 13 edges
8. `load_config()` - 11 edges
9. `resident_by_name()` - 11 edges
10. `produce()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `TestDeck index page (draft directory scaffold)` --semantically_similar_to--> `Tooldeck index page (AI tools by use case)`  [INFERRED] [semantically similar]
  index.html → site/index.html
- `Resident: shorts_history (history/weird facts)` --semantically_similar_to--> `Resident: Shorts #1 (history/weird facts)`  [INFERRED] [semantically similar]
  config.yaml → PLAN.md
- `gemini-3.6-flash fallback LLM` --semantically_similar_to--> `Gemini Flash (free-tier LLM)`  [INFERRED] [semantically similar]
  config.yaml → PLAN.md
- `Tooldeck index page (AI tools by use case)` --semantically_similar_to--> `Resident: shorts_ai_tools (AI/automation tools, short-form)`  [INFERRED] [semantically similar]
  site/index.html → config.yaml
- `Village config v2 (content revenue ecosystem, replaced with short-form video + audience-growth model)` --references--> `Village (self-directed resident runtime)`  [AMBIGUOUS]
  config.yaml → PLAN.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Three PLAN.md residents scheduled by core/scheduler.py** — plan_resume_studio, plan_directory, plan_shorts, plan_core_scheduler [INFERRED 0.85]
- **Config v2 gray-zone residents (shorts_history, shorts_ai_tools, audience_growth)** — config_resident_shorts_history, config_resident_shorts_ai_tools, config_resident_audience_growth [INFERRED 0.85]
- **Tooldeck directory site (index + 8 category pages)** — site_index_tooldeck_page, site_pages_the_best_ai_tools_for_ai_code_review_page, site_pages_the_best_ai_tools_for_ai_customer_support_page, site_pages_the_best_ai_tools_for_ai_email_writing_page, site_pages_the_best_ai_tools_for_ai_image_generation_page, site_pages_the_best_ai_tools_for_ai_meeting_notes_page, site_pages_the_best_ai_tools_for_ai_resume_builder_page, site_pages_the_best_ai_tools_for_ai_spreadsheet_automation_page, site_pages_the_best_ai_tools_for_ai_video_editing_page [INFERRED 0.85]
- **Human-gated approval workflow across draft, queue, and escalation review** — web_templates_draft_draft, web_templates_queue_queue, web_templates_escalations_escalations, web_templates_escalation_detail_escalation_detail, web_templates_agents_agents, web_templates_queue_human_gated_approval [INFERRED 0.85]
- **Resident/agent dashboard card UI pattern (zone/status badges, chips, progress bar)** — web_templates_overview_overview, web_templates_agents_agents, web_templates_agent_agent [INFERRED 0.80]

## Communities (27 total, 10 thin omitted)

### Community 0 - "Database & Draft Queue Core"
Cohesion: 0.07
Nodes (38): connect(), _ensure_schema(), init_db(), _migrate(), Idempotent guard: if the DB file is empty or missing core tables, run the…, Migrate older DBs that predate the current schema. The test suite creates a DB…, create_draft(), log_event() (+30 more)

### Community 1 - "Scheduler & Dispatch"
Cohesion: 0.06
Nodes (43): daily_dispatch(), escalate(), pending_delegations(), proven_proposal(), Yield (job_id, spec) for every pending delegation Hermes has dropped here., Record an escalation that must reach the human., No autonomous produce() anymore. Residents are planned by the Hermes…, resident_dispatch() (+35 more)

### Community 2 - "FastAPI Dashboard Routes"
Cohesion: 0.13
Nodes (44): fastapi, fastapi_responses, fastapi_staticfiles, fastapi_templating, get, middleware, post, Request (+36 more)

### Community 3 - "Email Digest & Mail"
Cohesion: 0.09
Nodes (40): dotenv, email, email_message, html, imaplib, app_password(), apply_command(), _decode_bytes() (+32 more)

### Community 4 - "Config Loading"
Cohesion: 0.10
Nodes (26): Any, core, load_config(), resident_by_name(), residents(), workstream_for_kind(), workstreams_of(), resident_by_name() (+18 more)

### Community 5 - "Content Residents & Monetization"
Cohesion: 0.09
Nodes (36): gemini-3.6-flash fallback LLM, Resident: audience_growth (hook/format experiments), Resident: shorts_ai_tools (AI/automation tools, short-form), Resident: shorts_history (history/weird facts), youtube_partner revenue channel (AdSense/YPP), TestDeck index page (draft directory scaffold), Guardrails (no undisclosed AI, no fabricated claims), Launch Offer (25% off first 3 clients for testimonial) (+28 more)

### Community 6 - "Governance Principles"
Cohesion: 0.11
Nodes (20): Escalation routing (always requires human approval), Hermes Agent (content-orchestrator skill), Ledger settings ($50/mo cap, kill switch), proven_profitable_bar (breakeven clearance proposal), vault settings (nugget_graph, obsidian_vault_path, copyback), Village config v2 (content revenue ecosystem, replaced with short-form video + audience-growth model), Breakeven-Governed Principle, Compartmentalized Risk Principle (clean/gray zones never touch) (+12 more)

### Community 7 - "Ledger & DB (Tests)"
Cohesion: 0.17
Nodes (13): Connection, connect(), init_db(), _migrate(), cap_remaining(), monthly_spent(), Spend across all residents since the start of the current calendar month. Used…, Total spend this calendar month across all residents (for the $50/mo ceiling). (+5 more)

### Community 8 - "Ledger Spend Tracking"
Cohesion: 0.23
Nodes (15): add_outcome(), cap_remaining(), monthly_spent(), Spend across all residents since the start of the current calendar month. Used…, Total spend this calendar month across all residents (for the $50/mo ceiling)., record_spend(), spent_today(), total_spent() (+7 more)

### Community 9 - "Obsidian Vault Integration"
Cohesion: 0.23
Nodes (15): Path, cycle_note_path(), ensure_structure(), list_escalations(), Write cycle notes, lessons, and escalations into an Obsidian vault folder. This…, Append a specific lesson to Lessons/<title-slug>.md — short and specific, not…, Mirror an escalation into Ecosystem/Escalations/ so it is visible in Obsidian…, Dump raw pulled metrics from OPENCODE-ANALYST into Ecosystem/Analytics/. (+7 more)

### Community 10 - "Site Build & Deploy"
Cohesion: 0.19
Nodes (11): build_site(), deploy(), _embed_affiliate_links(), _inline(), main(), _markdown_to_html(), _shell(), _slug_draft() (+3 more)

### Community 11 - "Core Runtime Overview"
Cohesion: 0.18
Nodes (11): Queue states (pending/approved/published/rejected/rework/killed), core/ledger.py (spend, caps, launch-budget tracking), core/queue.py (review queue state machine), core/scheduler.py (systemd timers, daily jobs per resident), core/vault.py (nugget graph read/write, copyback), Email Digest Review Channel (approve/flag by reply), Telegram Channel (original pick, swapped for email), core/ runtime module (scheduler, queue, ledger, vault, db) (+3 more)

### Community 12 - "Dashboard Templates"
Cohesion: 0.49
Nodes (11): Agent Detail Template (agent.html), Agents List Template (agents.html), Base Layout Template (base.html), Draft Review Template (draft.html), Escalation Detail Template (escalation_detail.html), Escalations Queue Template (escalations.html), Ledger Template (ledger.html), Overview Dashboard Template (overview.html) (+3 more)

### Community 13 - "Queue State Machine Tests"
Cohesion: 0.47
Nodes (8): transition(), make_draft(), test_created_draft_is_pending(), test_events_logged(), test_full_lifecycle(), test_illegal_transition_raises(), test_missing_draft_raises(), test_reject_then_rework_then_kill()

### Community 14 - "Markdown Rendering JS"
Cohesion: 0.47
Nodes (3): esc(), inline(), renderMD()

### Community 15 - "Web Dependencies"
Cohesion: 0.40
Nodes (5): web/ FastAPI dashboard (polish editor, ledger, vault, review), web/ FastAPI review/polish dashboard, fastapi==0.111.0, jinja2==3.1.6, pydantic==2.8.2

### Community 16 - "Plumbing Module Overview"
Cohesion: 0.50
Nodes (4): plumbing/deploy.py (build + publish), plumbing/mail.py (email digest + reply-to-approve), plumbing/mining.py (competitor scraping + trend signals), plumbing/ module (email digest, mining, deploy)

## Ambiguous Edges - Review These
- `Village (self-directed resident runtime)` → `Village config v2 (content revenue ecosystem, replaced with short-form video + audience-growth model)`  [AMBIGUOUS]
  config.yaml · relation: references
- `Gray Zone (separate identity, burnable)` → `youtube_partner revenue channel (AdSense/YPP)`  [AMBIGUOUS]
  config.yaml · relation: conceptually_related_to

## Knowledge Gaps
- **39 isolated node(s):** `core/scheduler.py (systemd timers, daily jobs per resident)`, `core/ledger.py (spend, caps, launch-budget tracking)`, `core/vault.py (nugget graph read/write, copyback)`, `core/config.yaml (resident registry, described in PLAN.md)`, `core/store.sqlite` (+34 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 112 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Village (self-directed resident runtime)` and `Village config v2 (content revenue ecosystem, replaced with short-form video + audience-growth model)`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **What is the exact relationship between `Gray Zone (separate identity, burnable)` and `youtube_partner revenue channel (AdSense/YPP)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `connect()` connect `Database & Draft Queue Core` to `Scheduler & Dispatch`, `FastAPI Dashboard Routes`, `Email Digest & Mail`, `Config Loading`, `Ledger Spend Tracking`, `Site Build & Deploy`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Why does `seed_demo()` connect `Database & Draft Queue Core` to `Ledger Spend Tracking`, `Obsidian Vault Integration`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Why does `create_draft()` connect `Database & Draft Queue Core` to `Scheduler & Dispatch`, `Email Digest & Mail`, `Queue State Machine Tests`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **What connects `core/scheduler.py (systemd timers, daily jobs per resident)`, `core/ledger.py (spend, caps, launch-budget tracking)`, `core/vault.py (nugget graph read/write, copyback)` to the rest of the system?**
  _39 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Database & Draft Queue Core` be split into smaller, more focused modules?**
  _Cohesion score 0.07127882599580712 - nodes in this community are weakly interconnected._