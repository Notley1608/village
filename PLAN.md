# Village — Consolidated Architecture v1

## The idea in one sentence
A self-directed runtime where each AI agent ("resident") owns one revenue property; they share a research vault, a review queue, and a spend ledger; nothing ships without your thumbs-up; the village governs itself by breakeven rules.

## Operating principles
1. **Human-gated** — every draft hits your review before publish. One rough pass on Gemini Flash, your 10-20 min/night polish is the quality engine.
2. **Free-tier-first** — run on Gemini Flash free quota until a resident nears breakeven, then upgrade that resident only.
3. **Breakeven-governed** — each resident gets a launch budget to burn, then must trend toward covering its own AI spend or it pauses.
4. **Copyback learning** — your polish edits write highlights back into the vault, so the village learns your taste.
5. **Minimal touch** — Telegram pings only for items needing you + hard failures. Everything else is silent.
6. **Compartmentalized risk** — clean zone and gray zone never touch.

## Two risk zones
| | Clean zone | Gray zone |
|---|---|---|
| Residents | Resume/LinkedIn studio | Directory, Shorts |
| Identity | Your real name | Separate emails/domains/phones, zero links back |
| Payout | Personal PayPal | **Alias PayPal** (never the personal rail) |
| Playbook | Pristine — no automation on platforms, manual ship | Aggressive: mass content, undisclosed AI voice, engagement buys (deferred) |
| Survivability | Must outlive everything | Burnable; fresh accounts only |

## Money map (AU now -> UK later, individual, real name)
- **Service gigs** -> PayPal, works in both. First-dollar engine.
- **Directory** -> worldwide SaaS affiliate programs paying via PayPal (recurring 20-40% rev-share); Amazon Associates AU secondary (AU-only, reassess on move).
- **Shorts** -> AdSense/YPP (pays both), affiliate links in descriptions later.
- **Compliance** -> per-property books; treat the residency change as a tax milestone; gray payouts never touch personal PayPal.

## Runtime architecture (Python + cron + SQLite, one $5 VPS, systemd, no Docker)

```
village/
├── core/
│   ├── scheduler.py    # systemd timers: daily jobs per resident
│   ├── queue.py        # review queue: pending->approved->published | rejected->rework->killed
│   ├── ledger.py       # per-resident spend, daily caps, launch-budget tracking
│   ├── vault.py        # nugget graph: read/write, spawn refs, polish copyback
│   ├── config.yaml     # resident registry: niche, cap, budget, publish target, seeded sources
│   └── store.sqlite
├── residents/
│   ├── resume_studio/  # paste-or-PDF + 5-question intake -> parse -> drafts -> queue -> manual ship
│   ├── directory/      # vault topic -> money/hub pages -> Astro build -> free static deploy
│   └── shorts/         # topic -> script -> free TTS -> stock loops + captions -> preview -> YouTube (OAuth)
├── plumbing/
│   ├── telegram.py     # minimal pings + approve/flag/rework buttons
│   ├── mining.py       # competitor scraping + trend signals -> vault nuggets
│   └── deploy.py       # build + publish
└── web/                # FastAPI dashboard: versioned markdown polish editor, ledger, vault, monthly review
```

**Schema core tables:** `residents`, `nuggets` (+tags/sources/spawn-links), `drafts` (+version history), `queue_events`, `ledger_entries`, `outcomes` (views/hits/gigs), `polish_notes`.

**Telegram semantics:** *Approve* ships; *Flag* triggers one auto-rework with your note, then kill; failures ping, caps/digests/skips stay silent.

**Vault research:** you seed ~30 min/wk (5-8 links/angles per resident) -> mining agent expands via competitor scraping + free trend signals. Nugget graph means one fact feeds a money page, a short's script, and a service asset.

## The three residents
1. **Resume/LinkedIn studio** *(clean, first-dollar)* — intake -> analysis -> rewrite + LinkedIn summary + cover letter -> polish -> ship via warm network / Fiverr -> PayPal. Offer structure set after 1-2 warm sell-ins, price band $25-75.
2. **Directory** *(gray, compounding)* — "AI & automation tools by use case," US-English. Launch with **10 money pages + 5 hubs** on Astro, free static deploy, Search Console + interlinking. Affiliate approval via aged/ramped path.
3. **Shorts #1** *(gray, long ramp)* — history/weird facts. **Stock loops + animated captions + free local TTS**, faceless, undisclosed AI voice. Accounts opened early to age, 2-3 week cadence ramp. Budget: 120-day burn; engagement buy (~$50) only if organic stalls near the 10M-view bar.

## Budget (< $50/mo)
VPS ~$6 · domain ~$1 · AI ~$0 on free tier, projected $4-18/upgraded resident on demand · TTS/stock/video $0 · engagement $0 until decided. Buffer covers the rest.

## Build phases (evenings)
| Phase | Deliverable | Exit criteria |
|---|---|---|
| **0** | Scaffold: schema, scheduler, Telegram skeleton, config, fake draft through full queue | Draft -> review -> publish path works end-to-end |
| **1** | Resume studio live; warm sell-ins; offer set | **First dollar** |
| **2** | Directory: seed vault, 15 pages, deploy, Search Console, affiliate applications | 20+ indexed pages |
| **3** | Shorts: aged accounts, ramped cadence, ~50 videos/quarter, YPP tracked | 1k subs / 10M views traction |
| **4** | Village ops: monthly breakeven review, kill/pause/clone, copyback learning | >=1 resident self-funding |

**Clone rule (scale-the-whole-thing):** a resident covers its spend **and** shows 3+ weeks of upward slope -> clone pipeline into the next niche. No optimizer agent until volume outgrows your monthly 20-min review.

## Explicitly open slots (crunch when we hit them)
Resume offer/price · exact affiliate program shortlist (payout-country check done per program at Phase 2) · alias-PayPal mechanics (AU->UK) · directory use-case sub-angle (chosen from vault data at Phase 2) · shorts voice/style · engagement-buy timing.

## Deployment
- Runtime: single $5 VPS (Hetzner/DO), Python 3.9+, systemd timers, no Docker.
- Directory: Astro statically generated, deployed free (Netlify/GitHub Pages) from the VPS.
- Dev: macOS local, same codebase.