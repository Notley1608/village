# Village

Self-directed AI agent runtime where each resident owns one revenue property.
Shared vault, review queue, and spend ledger. Human-gated publishing.

See `PLAN.md` for the full architecture spec.

## Layout

```
core/        runtime: scheduler, queue, ledger, vault, db
residents/   one subdir per revenue property
plumbing/    telegram bot, topic mining, deploy
web/         FastAPI review/polish dashboard
```

## Setup (dev on macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m core.db          # initialise store.sqlite
```

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