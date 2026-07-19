# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

**microSched** — a single-user personal task / note / calendar / tracker web app, **AI-first**, being built as a **clean rewrite** of an old desktop app (`VC_QuanLyThoiGian`). It is the "dự án trục" (spine project) of the owner's summer-2026 study plan; the parent planning/strategy workspace is at `../../hoc_he_2026` (read its `chien-luoc-he-2026.md` / `track_ai_eng_strategy.md` for the wider plan and the AI-engineering learning goals this project serves).

**Current state: design-complete, pre-code.** There is **no application code, package manifest, test suite, or git repo yet** — only decision records under `docs/` and one utility script. Do not fabricate build/lint/test commands; they don't exist until phase B scaffolds the app. Language, framework, architecture, and hosting are all decided (see `architecture-brief.md`); the **physical schema** (DDL, PK=UUIDv7, ORM=SQLModel, migrations, indexes, enum encoding, 3-tier AI logging) is decided too (see `schema-physical-brief.md`, 2026-07-19). The tracking-design session **closed 2026-07-19** (`tracking-brief.md`, all items final): A/B/C data split, VND-only money model, `tracker_group`, `subscription` entity, capture flow (one-tap + undo), dashboard behavior spec, medication reminder (discreet noti), and a full normalization review (§10, K1–K17) — **the schema is now fully locked across the project**. Remaining open decisions are the concrete frontend UI stack, auth implementation (now also owns the private-mode unlock mechanism), the Bước-1 AI choices, and a dedicated **encryption-review session** (whole-DB, scope in `tracking-brief.md` §6). A git repo now exists (docs committed); still no application code, package manifest, or test suite.

**Repo & workflow (see `devops-brief.md`):** GitHub repo is **public by deliberate choice**; work happens on `develop` → PR into `main` (ruleset `protect-main` blocks force-push/deletion and requires a PR; approvals are set to 0 on purpose — solo project). Convention: **one commit per decision session**, Vietnamese message explaining *why*. Delegated work goes in `agent-tasks/NNN-<slug>.md` as self-contained specs.

## Read the decision records before proposing anything

`docs/` holds **self-contained decision briefs** (written to be read with zero conversation context). They encode locked decisions *and their reasons* — read them rather than re-deriving:

- `docs/db-and-data-model-brief.md` — DB, hosting, backup decisions.
- `docs/schema-v1-brief.md` — the data model (entities + relationships), locked at concept level.
- `docs/schema-physical-brief.md` — the **physical** schema (column types, PK=UUIDv7, enum=TEXT+CHECK, indexes, ORM=SQLModel, Alembic+QA, 3-tier AI logging), locked 2026-07-19 except tracker specifics.
- `docs/tracking-brief.md` — tracking feature design, **locked 2026-07-19**: A/B/C data types, VND-only money model, `tracker_group`, `subscription`, capture flow + dashboard spec, normalization review (§10), medication reminder (§12), private-mode supersede (§5), encryption-review scope (§6).
- `docs/forward-spec.md` — feature backlog + the "viewability" and AI-first design principles.
- `docs/upgrade-notes-inbox.md` — verbatim raw capture of the owner's upgrade notes (provenance for `forward-spec.md`).
- `docs/architecture-brief.md` — language/framework (Python + FastAPI), modular-monolith architecture, hosting (Fly.io), auth approach (Google OAuth + allowlist, leaning), AI tool-layer/MCP sequencing, repo layout. **Read this before proposing any stack/infra change.**
- `docs/cost-brief.md` — running operating-cost tally across all chosen services; carries its own re-check date (~3 months), separate from architecture-brief so pricing drift doesn't invalidate decisions.
- `docs/devops-brief.md` — repo visibility + **the owner's threat model** (social engineering, not casual readers), git/PR workflow, secret-scanning layers, auto-PR-review options (deferred until there's code), agent-task convention. Read before touching repo settings or CI.
- `docs/migration-mapping-brief.md` — old data → new schema; where the real data lives.
- `docs/v1-reference.md` — old-app domain logic worth porting (code-level; not strategy).
- `docs/learnings-applied.md` — running log of concepts learned and applied.
- `scripts/inventory_old_stores.py` — read-only inventory of the OLD stores (needs the old app's venv python + `PGPW` env var). Reusable for cutover verification.

## Locked architecture (don't relitigate — see docs for the reasoning)

- **One data store only: PostgreSQL + `pgvector`, hosted on Neon.** No SQLite, no parallel stores. The old app ran SQLite *and* Postgres simultaneously and lost track of which held the truth — that split-brain is the anti-pattern this project exists to avoid.
- **Data model:** see `schema-v1-brief.md`. Core entities: `task`/`task_item`, `note`/`note_item`, `calendar_source`/`calendar_event`, `tracker`/`entry` (unified health + finance logging), `app_setting`, `audit_log`. Principle: **markdown for prose/body fields, structured columns for anything queryable**; timestamps on every entity; store full text, truncate only at display.
- **AI features are sequenced by blast radius:** Bước 0 (foundation) → 1 (read-only assistant, hybrid retrieval) → 2 (narrow write tools + confirm + audit) → 3 (finance). Auto-mode = **cascade self-verify**, not a learned router. Instrument/log from day one.
- **Backend: Python + FastAPI** (locked 2026-07-19). Python chosen for AI/RAG/eval ecosystem depth + AI-eng career alignment (re-examined against TS full-stack; hosting is cost-neutral between them so it wasn't a factor). FastAPI over Litestar for the biggest ecosystem / best AI-coding-assistant support (maximize time-on-AI, minimize framework plumbing) + Pydantic v2 being the de-facto tool-schema standard. **Do NOT justify this by "the owner already knows it from FANG" — familiarity was deliberately excluded as a weight (summer goal is renewal, not reuse).** ORM = **SQLModel**, Alembic with QA gates, PK = UUIDv7, enums = TEXT+CHECK, 3-tier AI logging — all locked 2026-07-19 in `schema-physical-brief.md`.
- **Architecture: modular monolith** (one process — web/domain/retrieval/agent/jobs as in-process modules, not services). No Celery/Redis; scheduled/background work (embeds, calendar import, backup, medication reminders) runs via external cron (GitHub Actions) hitting an endpoint. **Hosting: Fly.io**, 1× shared-cpu-1x Machine always-on (no scale-to-zero — cold start is a hard no for this user), region `sin`; start at 256MB (~$2/mo), scale to 512MB only if it OOMs. **Frontend = static SPA/PWA** (no SSR → one runtime; FastAPI serves the built static files on the same origin/Machine). DB stays Neon; no Fly volumes, no Fly Managed Postgres. See `architecture-brief.md` for full reasoning + rejected alternatives (Oracle Always-Free, VN shared hosting, Render free, Hetzner).
- **Frontend: PWA, offline-first for capture** (writes land in IndexedDB instantly, sync later) — decided in principle; concrete UI stack still OPEN, decide at frontend-scaffold time.
- **AI tool layer is Pydantic-typed and MCP-ready by construction**, but MCP protocol itself is deferred until there's a second consumer beyond the internal agent — don't wire an MCP server prematurely.

## Hard boundaries (do not cross)

- The old app at `C:\Users\os\Desktop\old_prj\VC_QuanLyThoiGian` is **reference only**. Its `main` branch (v1 desktop) and the real SQLite DB at `C:\Users\os\Desktop\Tools\VC_microSchedule_home\todo.db` are **do-not-touch** (they are the rollback path). Read old stores **read-only** only.
- **Migration source of truth = the local Postgres `microschedule_v2`** (live, edited daily). The old SQLite is dead — ignore it.
- The local `postgres` **superuser hosts many of the owner's other projects** — microSched must get its **own limited DB role**; never reuse that superuser for the app.
- Credentials live only in `.env`, never committed; the first commit's `.gitignore` must block `.env`.

## Working conventions

- Docs are **decision records**: self-contained, Vietnamese prose with English technical terms kept inline, status-flagged (`✅ CHỐT` / `⚠️ OPEN` / `DEFER`). When a decision changes, add a dated note — don't silently rewrite prior conclusions.
- **Role split:** the owner decides architecture/product and reviews; Claude executes. Present options at the **strategy/product level**, not as low-level backend claims — the owner does not retain backend detail of the old app.
- Where a decision in `docs/` conflicts with the parent strategy docs in `../../hoc_he_2026`, the newer decision here wins (those docs predate this project's design phase).
