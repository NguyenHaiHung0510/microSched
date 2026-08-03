# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Bảo trì file này (đọc trước khi sửa):** file này bị giới hạn ~40k ký tự vì nó nạp vào context của MỌI phiên. Nó chỉ chứa **luật/trạng thái hiện hành**, sửa tại chỗ (không thêm dated note tích luỹ). Lịch sử từng phiên, lý do đằng sau các quyết định, và các bài học chi tiết nằm ở [`docs/session-log.md`](docs/session-log.md) (nhật ký theo phiên) và [`docs/learnings-applied.md`](docs/learnings-applied.md) — trỏ tới đó thay vì dán lại nội dung. Nếu một mục ở đây cần ghi "vì sao đổi", viết 1 dòng trỏ `docs/session-log.md#<ngày>` chứ đừng chép nguyên đoạn.

## What this repository is

**microSched** — a single-user personal task / note / calendar / tracker web app, **AI-first**, being built as a **clean rewrite** of an old desktop app (`VC_QuanLyThoiGian`). It is the "dự án trục" (spine project) of the owner's summer-2026 study plan; the parent planning/strategy workspace is at `../../hoc_he_2026` (read its `chien-luoc-he-2026.md` / `track_ai_eng_strategy.md` for the wider plan and the AI-engineering learning goals this project serves).

**Current state (2026-08-02): real app in production.** `backend/` (FastAPI + SQLModel + Alembic, Python ≥3.14 via `uv`, ruff + pytest), `frontend/` (React 19 + TypeScript + Vite + Tailwind v4/shadcn-ui + TanStack Query v5, Playwright e2e in `frontend/e2e/`), one root `Dockerfile`, live at `microsched.fly.dev` on Neon PG18; Fly runs one `shared-cpu-1x` 256MB Machine continuously in `sin`. Production cron remains on Google Cloud Scheduler (not GitHub Actions — see `devops-brief.md` §10). **Build/lint/test commands are real — read them from `backend/pyproject.toml`, `frontend/package.json` and `.github/workflows/` instead of assuming or inventing them; migration count, table count, and test count all change often enough that this file does not track them — check `backend/alembic/versions/` and run the test suite instead of trusting a number written here.**

**Design phase: fully closed.** All architecture/schema/frontend/auth/UI/QA-framework decisions are locked — see the doc list below. The only thing left to design is the **Bước-1 AI choices** (embedding provider, vector dimension, default LLM, hybrid retrieval details) — everything else in `docs/` is final, read it rather than re-deriving.

**Slice progress:** `003`?`007` (walking skeleton), `008` + all sub-tasks (`a/b/d/e/f/i/k/m/n/g`), `013` (DevSecOps), `014` (cron RSS watch), `015` (gitleaks history scan), `016` (private unlock), `018` (QA framework + Playwright harness), `009` (note slice), `010a` (calendar import/CRUD) ? **all done and live**. Open, not blocking: `008c` (cost-tracking feature, scope in `cost-brief.md` ?7.4, do when free). Deferred to after `012` + a dedicated branding session with the owner + a copy rewrite (drop first-person voice): `008h` (landing page).

**?? Vi?c k? ti?p th?t s?:** thi c?ng `010b` (calendar ph?n nh?n) ? **`010a` ?? merge & QA closeout t?i PR #86/#87**. H?ng ??i: `010b ? 011a ? 011c ? 011b ? 020 ? 012 ? 008h`. T?nh tr?ng spec (vi?t tr??c 2026-08-01 ?? h?ng ??i ch?y ???c c? khi T1 v?ng): `010b` ?? duy?t ? `011a`/`011b`/`011c` DRAFT ch? ch? duy?t ? `020` (3 c?t gi? d? li?u app c?) v? `012` (cutover) **?? c? spec DRAFT**, ?? qua m?t v?ng ph?n bi?n T2+T3 2026-08-02, **ch?a qua v?ng v? + ch? duy?t b?n chi ti?t**. `020` l? ph? thu?c c?ng c?a `012` (ph?i merge tr??c, xem `020` ?1). **??ng ??o th? t? trong h? `011`:** `011b` nh?c c? thu?c l?n sub n?n ph?i sau `011c`. B?ng chi ti?t t?ng l?: `agent-tasks/README.md`. Chi ti?t l?ch s? v? sao th? t? n?y ??i nhi?u l?n (018/016/015 chen tr??c 009): `docs/session-log.md`.

## Read the decision records before proposing anything

`docs/` holds **self-contained decision briefs** (written to be read with zero conversation context). They encode locked decisions *and their reasons* — read them rather than re-deriving:

- `docs/db-and-data-model-brief.md` — DB, hosting, backup decisions.
- `docs/schema-v1-brief.md` — the data model (entities + relationships), locked at concept level.
- `docs/schema-physical-brief.md` — the **physical** schema (column types, PK=UUIDv7, enum=TEXT+CHECK, indexes, ORM=SQLModel, Alembic+QA, 3-tier AI logging), locked 2026-07-19 except tracker specifics.
- `docs/tracking-brief.md` — tracking feature design, **locked 2026-07-19**: A/B/C data types, VND-only money model, `tracker_group`, `subscription`, capture flow + dashboard spec, normalization review (§10), medication reminder (§12), private-mode supersede (§5), encryption-review **closed 2026-07-20** (§6 — column-level verdict, mechanism, pgvector/FTS exclusion).
- `docs/forward-spec.md` — feature backlog + the "viewability" and AI-first design principles.
- `docs/upgrade-notes-inbox.md` — verbatim raw capture of the owner's upgrade notes (provenance for `forward-spec.md`).
- `docs/architecture-brief.md` — language/framework (Python + FastAPI), modular-monolith architecture, hosting (Fly.io), AI tool-layer/MCP sequencing, repo layout. **Read this before proposing any stack/infra change.**
- `docs/frontend-brief.md` — frontend UI stack, **locked 2026-07-20**: React 19 + TypeScript + Vite + Tailwind v4/shadcn-ui + TanStack Query v5 + Dexie/hand-rolled outbox (no sync-engine; TanStack DB noted as a two-way upgrade door); runtime model (Node exists only at build time — production runs one Python process, multi-stage Docker); owner-device (iPhone) PWA consequences; shadcn + npm supply-chain conventions.
- `docs/ui-brief.md` — hệ thiết kế UI, **locked 2026-07-25**: hướng "B · hồng ấm" `#E8698C`, font Nunito Variable tự host, light-only, thang màu/token ở `index.css`, §6 = luật UI cứng (không thẻ thô, không hardcode màu, không chiều cao cứng, chữ ≥12px, không tương tác chỉ-hover), §8 = bộ component + 4 cái bẫy của `shadcn add`. **Đụng UI thì đọc trước khi viết dòng đầu tiên.**
- `docs/qa-framework.md` — khung QA dùng chung, **✅ CHỐT 2026-07-29**: bốn trục (Nielsen · chạm/mobile-HIG · WCAG đo được gồm non-text contrast · microcopy), ma trận màn × trạng thái, bộ dữ liệu test bắt buộc, quy ước `data-testid` → Playwright. Áp cho mọi slice từ 009.
- `docs/auth-brief.md` — auth, **locked 2026-07-20**: Google OAuth + env allowlist (Authlib, login-only OIDC), server-side `session` table, private unlock (PIN 6 chữ số — đảo từ passphrase, xem `auth-brief.md` §3 dated note — TTL 36', throttle leo thang 10/20/36'), **AI × private ruleset R1–R7**, cron-endpoint bearer auth.
- `docs/cost-brief.md` — running operating-cost tally across all chosen services; carries its own re-check date, separate from architecture-brief so pricing drift doesn't invalidate decisions.
- `docs/devops-brief.md` — repo visibility + **the owner's threat model** (social engineering, not casual readers), git/PR workflow, secret-scanning layers, harness-eng operating model (T1/T2/T3 topology, full-access rules), agent-task convention. Read before touching repo settings or CI.
- `docs/migration-mapping-brief.md` — old data → new schema; where the real data lives.
- `docs/v1-reference.md` — old-app domain logic worth porting (code-level; not strategy).
- `docs/learnings-applied.md` — running log of concepts learned and applied.
- `docs/session-log.md` — **archive lịch sử đến 2026-08-01 và nhật ký các phiên sau đó.** Đọc nó cho *why* và biên lai lịch sử; đừng đọc nó cho current state.
- `scripts/inventory_old_stores.py` — read-only inventory of the OLD stores (needs the old app's venv python + `PGPW` env var). Reusable for cutover verification.

## Locked architecture (don't relitigate — see docs for the reasoning)

- **One data store only: PostgreSQL + `pgvector`, hosted on Neon.** No SQLite, no parallel stores. The old app ran SQLite *and* Postgres simultaneously and lost track of which held the truth — that split-brain is the anti-pattern this project exists to avoid.
- **Data model:** see `schema-v1-brief.md`. Core entities: `task`/`task_item`, `note`/`note_item`, `calendar_source`/`calendar_event`, `tracker`/`entry` (unified health + finance logging), `app_setting`, `audit_log`. Principle: **markdown for prose/body fields, structured columns for anything queryable**; timestamps on every entity; store full text, truncate only at display.
- **AI features are sequenced by blast radius:** Bước 0 (foundation) → 1 (read-only assistant, hybrid retrieval) → 2 (narrow write tools + confirm + audit) → 3 (finance). Auto-mode = **cascade self-verify**, not a learned router. Instrument/log from day one.
- **Backend: Python + FastAPI** (locked 2026-07-19). Python chosen for AI/RAG/eval ecosystem depth + AI-eng career alignment. FastAPI over Litestar for ecosystem/AI-coding-assistant support + Pydantic v2 as the de-facto tool-schema standard. **Do NOT justify this by "the owner already knows it" — familiarity was deliberately excluded as a weight.** ORM = **SQLModel**, Alembic with QA gates, PK = UUIDv7, enums = TEXT+CHECK, 3-tier AI logging — all locked 2026-07-19 in `schema-physical-brief.md`.
- **Architecture: modular monolith** (one process — web/domain/retrieval/agent/jobs as in-process modules, not services). No Celery/Redis; scheduled/background work runs via external cron (Google Cloud Scheduler) hitting an endpoint. **Hosting: Fly.io**, exactly one `shared-cpu-1x` 256MB Machine kept running continuously (`auto_stop_machines = false`, `min_machines_running = 1`), region `sin`; the 2026-08-02 reversal and conditional under-$5 invoice waiver are recorded in `architecture-brief.md` §5 and `cost-brief.md` §7.6. **Frontend = static SPA/PWA** (no SSR → one runtime; FastAPI serves the built static files on the same origin/Machine). DB stays Neon; no Fly volumes, no Fly Managed Postgres. See `architecture-brief.md` for full reasoning + rejected alternatives.
- **Frontend: PWA, offline-first for capture** — stack locked 2026-07-20 (`frontend-brief.md`): React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui + TanStack Query v5 + Dexie with a hand-rolled outbox — **no sync-engine** (single-user has no multi-client conflict problem). Node exists only at build time; production runs a single Python process. Two offline-write seams (idempotent client-generated UUIDv7 id, `008m`) are open; full outbox queue is deferred to `015`-family work — see `docs/session-log.md` 2026-07-28 for the exact scope split.
- **Auth (locked 2026-07-20, `auth-brief.md`):** Google OAuth + env allowlist via Authlib (login-only OIDC); server-side `session` table (opaque token cookie, hash stored); private unlock = separate PIN opening the session for a TTL (a *display* gate — the encryption master key stays app-held; live and QA-verified as of `016`, 2026-07-31). **AI follows the session's private gate (R1–R7):** locked ⇒ agent tools filter `is_private`; unlocked ⇒ full read (write comes with Bước 2); encrypted columns still never enter pgvector/FTS; private-in-context ⇒ force zdr/no-train for the whole cascade; background/cron AI is public-only.
- **AI tool layer is Pydantic-typed and MCP-ready by construction**, but MCP protocol itself is deferred until there's a second consumer beyond the internal agent — don't wire an MCP server prematurely.

## Hard boundaries (do not cross)

- The old app at `C:\Users\os\Desktop\old_prj\VC_QuanLyThoiGian` is **reference only**. Its `main` branch (v1 desktop) and the real SQLite DB at `C:\Users\os\Desktop\Tools\VC_microSchedule_home\todo.db` are **do-not-touch** (they are the rollback path). Read old stores **read-only** only.
- **Migration source of truth = the local Postgres `microschedule_v2`** (live, edited daily). The old SQLite is dead — ignore it.
- The local `postgres` **superuser hosts many of the owner's other projects** — microSched must get its **own limited DB role**; never reuse that superuser for the app.
- Credentials live only in `.env`, never committed; `.gitignore` blocks `.env`.
- **Migrations are never auto-applied on deploy.** No `release_command` in `fly.toml`, no alembic step in `deploy.yml`. Apply by hand: `cd backend && uv run alembic upgrade head` (uses `NEON_MIGRATOR_URL`). *"Merge ≠ migration applied"* — verify with a real query against Neon (e.g. `information_schema.columns` / `pg_constraint`), never stop at `alembic current`.

## Repo & workflow (see `devops-brief.md`)

GitHub repo is **public by deliberate choice**; work happens on `develop` → PR into `main`. **Merging into `develop` deploys to production** (`devops-brief.md` §2.1). `develop` = what is running on Fly and where the owner/T3 verify. **`main` never deploys** — it is a deliberately-lagging **release label**, tagged `v0.x` when a slice is worth a rollback point. Rollback = **roll-forward** (`git revert` on `develop`).

**Everything GitHub reads from the default branch only reads from `main`** — workflow `schedule:`, `dependabot.yml` (both read *and* `target-branch` write), `CODEOWNERS`, community health files. Since `main` is intentionally stale, anything of this kind merged only into `develop` is silently inert — check this every time you touch `.github/`. Full incident history: `docs/session-log.md`.

**`develop` requires a PR for everything, including docs** — `protect-develop` has required status checks (incl. `Secret scan`), so a bare push without a passing check is rejected (`GH013`). One commit per decision session, Vietnamese message explaining *why*. Delegated work goes in `agent-tasks/NNN-<slug>.md` as self-contained specs; code tasks run on a `feat/NNN-<slug>` branch with a PR into `develop`.

**Merge gate by criticality** (`pr-merge-gate-by-criticality` memory): non-critical PRs need one adversarial-review pass (T2 or T3) + green CI, then merge (owner has pre-authorized this, no need to ask). Critical/ops-irreversible work still gets the full T1 receipt trail (PR# + `gh pr checks` green + diff read + live SHA).

Data boundary for third-party tools (`devops-brief.md` §7): public code/docs = any tier may touch; real secrets and personal data never enter agent sessions.

## Working conventions

- Docs are **decision records**: self-contained, Vietnamese prose with English technical terms kept inline, status-flagged (`✅ CHỐT` / `⚠️ OPEN` / `DEFER`). When a decision **changes**, add a dated note in the *relevant brief* (e.g. `auth-brief.md` §3) — don't silently rewrite prior conclusions. When something is merely **current state** (a fact that just became outdated, not a decision reversal), fix it in place — don't let a stale fact and its correction coexist in the same paragraph (see `docs/session-log.md` 2026-07-23 "mâu thuẫn D1" for why this distinction matters).
- **Role split:** the owner decides architecture/product and reviews; Claude executes. Present options at the **strategy/product level**, not as low-level backend claims.
- Where a decision in `docs/` conflicts with the parent strategy docs in `../../hoc_he_2026`, the newer decision here wins.
- **pre-commit + gitleaks are active** (`.pre-commit-config.yaml`): every `git commit` runs a basic hygiene hook + gitleaks. Hook doesn't survive `git clone` — run `pip install pre-commit && pre-commit install` on a new machine.
- **CLAUDE.md itself:** current-state facts get fixed in place; session-close notes go to `docs/session-log.md`, not appended here (see the maintenance note at the top of this file, and `feedback_session_close_checklist` in memory).

## Delegation qua sub-agent (Codex + OpenCodex) — ✅ Cập nhật 2026-08-03

Từ 2026-08-03, dự án chuyển sang **Codex Desktop App** làm harness chính (thay thế Claude Code). Việc điều phối sub-agents (T2 thi công, T3 phản biện/test) sử dụng cơ chế `spawn_agent` tích hợp sẵn trong Codex Desktop, kết hợp **OpenCodex** (gọi các model qua Antigravity và OpenRouter).

**Ma trận phân vai & Định tuyến Model:**
- **T1 (Óc — Main thread Codex Desktop):** Lập kế hoạch, spec, ADR, review diff cuối. Model: `gpt-5.6-sol` (effort: `xhigh`/`high`) khi có quota; PAYG/cạn quota: `google-antigravity/claude-opus-4-6-thinking` hoặc `google-antigravity/gemini-3.6-flash`.
- **T2 (Tay thi công — `spawn_agent` sub-agent):** Thi công code trên branch `feat/NNN-<slug>`. Model: `gpt-5.6-sol` (high) cho việc khó/Auth/DDL/Crypto; `gpt-5.6-terra` (medium) cho CRUD/UI; `gpt-5.6-luna` (low/medium) cho sửa vặt/lint/test-loop; PAYG: `google-antigravity/gemini-3.6-flash` hoặc `openrouter/~deepseek-deepseek-v4-flash-latest`.
- **T3 (Máy chạy test & Phản biện 6 trục — `spawn_agent` sub-agent):** Phản biện 6 trục (Rubric §7.3i), e2e Playwright, regression. Model: `google-antigravity/gemini-3.6-flash` (tốc độ/AI Pro quota); `google-antigravity/gemini-3.1-pro-high` (soát lỗi chuyên sâu); PAYG OpenRouter: `openrouter/~deepseek-deepseek-v4-flash-latest` hoặc `openrouter/deepseek/deepseek-v4-pro`.
