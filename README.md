# Village

Self-directed AI agent runtime where each resident owns one revenue property.
Shared vault, review queue, and spend ledger. Human-gated publishing.

See `PLAN.md` for the full architecture spec.

## Layout

```
core/        runtime: scheduler, queue, ledger, vault, db
residents/   one subdir per revenue property
plumbing/    email digest (approval channel), topic mining, deploy
web/         FastAPI review/polish dashboard
```

## Setup (dev on macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m core.db          # initialise store.sqlite
```

## Review channel (email digest)

Drafts pile up in the review queue; you get a digest email and reply
`approve <id>` or `flag <id> <rework note>`.

One-time setup (Gmail):

1. Enable 2-Step Verification on your Google account.
2. Google Account > Security > App passwords > create one for "Mail".
3. Put `MAIL_USER` (your address), `MAIL_APP_PASSWORD` (the 16-char app
   password), and `MAIL_TO` in `.env`.

Usage:

```bash
.venv/bin/python -m plumbing.mail digest   # send today's review digest
.venv/bin/python -m plumbing.mail poll     # apply reply commands from inbox
```

The scheduler will run these automatically; IMAP `uid` tracking in SQLite
(`processed_emails`) makes polling idempotent.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

`tests/` covers the core runtime (db, queue, ledger, vault, config) plus a
per-resident contract suite in `tests/residents/` (`test_resume_studio.py`,
`test_directory.py`, `test_shorts.py`). The resident tests currently assert the
pipeline stubs; they get replaced with real unit tests as each agent is built in
Phases 1-3.

## Status

Phase 0 scaffold. Not production ready.

GitHub remote + history managed manually.