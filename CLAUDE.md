# Project Instructions

## Project

Village is a self-directed AI agent runtime where each "resident" owns one revenue-generating
property (e.g. shorts, resume studio, directory). A shared core (scheduler, review queue, spend
ledger, vault, SQLite store) coordinates residents; drafts route through a human-gated review
channel (email digest) before publishing. A FastAPI + Jinja2 dashboard exposes residents, queue,
vault, and ledger for review and polish editing.

## Core rules

- Read relevant code before making changes.
- Prefer existing patterns over introducing new abstractions.
- Make the smallest change that solves the problem.
- Run relevant tests after modifications.
- Never modify tests merely to make them pass.
- Do not introduce dependencies without justification.
- Preserve existing public APIs unless explicitly instructed otherwise.

## Architecture

- `core/` — runtime: scheduler, queue, ledger, vault, db
- `residents/` — one subdirectory per revenue property (e.g. `shorts/`)
- `plumbing/` — email digest (approval channel), topic mining, deploy
- `web/` — FastAPI review/polish dashboard
- `tests/` — core runtime tests plus per-resident contract suites (`tests/residents/`)

See `PLAN.md` for the full architecture spec.

## Workflow

For substantial tasks:

1. Inspect relevant code.
2. Inspect `PLAN.md` for architectural context.
3. Create/modify tests.
4. Implement.
5. Verify (`.venv/bin/python -m pytest`).
6. Update `PLAN.md` or `README.md` if the change affects the architecture or setup.

## Git

- Never force push.
- Never discard unrelated user changes.
- Keep commits focused.
