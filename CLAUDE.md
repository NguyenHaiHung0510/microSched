# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

**microSched** — a single-user personal task / note / calendar / tracker web app, **AI-first**, being built as a **clean rewrite** of an old desktop app (`VC_QuanLyThoiGian`). It is the "dự án trục" (spine project) of the owner's summer-2026 study plan; the parent planning/strategy workspace is at `../../hoc_he_2026` (read its `chien-luoc-he-2026.md` / `track_ai_eng_strategy.md` for the wider plan and the AI-engineering learning goals this project serves).

**Current state: design-complete, pre-code.** There is **no application code, package manifest, test suite, or git repo yet** — only decision records under `docs/` and one utility script. Do not fabricate build/lint/test commands; they don't exist until phase B scaffolds the app. The next phase (B) is choosing the backend framework + inter-service architecture, then scaffolding.

## Read the decision records before proposing anything

`docs/` holds **self-contained decision briefs** (written to be read with zero conversation context). They encode locked decisions *and their reasons* — read them rather than re-deriving:

- `docs/db-and-data-model-brief.md` — DB, hosting, backup decisions.
- `docs/schema-v1-brief.md` — the data model (entities + relationships), locked at concept level.
- `docs/forward-spec.md` — feature backlog + the "viewability" and AI-first design principles.
- `docs/migration-mapping-brief.md` — old data → new schema; where the real data lives.
- `docs/v1-reference.md` — old-app domain logic worth porting (code-level; not strategy).
- `docs/learnings-applied.md` — running log of concepts learned and applied.
- `scripts/inventory_old_stores.py` — read-only inventory of the OLD stores (needs the old app's venv python + `PGPW` env var). Reusable for cutover verification.

## Locked architecture (don't relitigate — see docs for the reasoning)

- **One data store only: PostgreSQL + `pgvector`, hosted on Neon.** No SQLite, no parallel stores. The old app ran SQLite *and* Postgres simultaneously and lost track of which held the truth — that split-brain is the anti-pattern this project exists to avoid.
- **Data model:** see `schema-v1-brief.md`. Core entities: `task`/`task_item`, `note`/`note_item`, `calendar_source`/`calendar_event`, `tracker`/`entry` (unified health + finance logging), `app_setting`, `audit_log`. Principle: **markdown for prose/body fields, structured columns for anything queryable**; timestamps on every entity; store full text, truncate only at display.
- **AI features are sequenced by blast radius:** Bước 0 (foundation) → 1 (read-only assistant, hybrid retrieval) → 2 (narrow write tools + confirm + audit) → 3 (finance). Auto-mode = **cascade self-verify**, not a learned router. Instrument/log from day one.
- **Backend framework (FastAPI) + frontend (PWA) are still OPEN** — to be decided when scaffolding starts, then written down as a brief.

## Hard boundaries (do not cross)

- The old app at `C:\Users\os\Desktop\old_prj\VC_QuanLyThoiGian` is **reference only**. Its `main` branch (v1 desktop) and the real SQLite DB at `C:\Users\os\Desktop\Tools\VC_microSchedule_home\todo.db` are **do-not-touch** (they are the rollback path). Read old stores **read-only** only.
- **Migration source of truth = the local Postgres `microschedule_v2`** (live, edited daily). The old SQLite is dead — ignore it.
- The local `postgres` **superuser hosts many of the owner's other projects** — microSched must get its **own limited DB role**; never reuse that superuser for the app.
- Credentials live only in `.env`, never committed; the first commit's `.gitignore` must block `.env`.

## Working conventions

- Docs are **decision records**: self-contained, Vietnamese prose with English technical terms kept inline, status-flagged (`✅ CHỐT` / `⚠️ OPEN` / `DEFER`). When a decision changes, add a dated note — don't silently rewrite prior conclusions.
- **Role split:** the owner decides architecture/product and reviews; Claude executes. Present options at the **strategy/product level**, not as low-level backend claims — the owner does not retain backend detail of the old app.
- Where a decision in `docs/` conflicts with the parent strategy docs in `../../hoc_he_2026`, the newer decision here wins (those docs predate this project's design phase).
