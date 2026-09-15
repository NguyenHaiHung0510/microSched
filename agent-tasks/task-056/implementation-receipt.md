# Task 056 implementation receipt

Date: 2026-09-15 · Candidate branch: `feat/056-mimi-p1-task-walking-skeleton`

## Delivered in the candidate

- additive Alembic `0014` ledger for conversation, ordered encrypted messages,
  bounded run/event/provider state, encrypted frozen change set, immutable
  execution receipt, durable refresh marker, feedback and evidence metadata;
- per-conversation AES-256-GCM DEK wrapped by the existing app master key;
- authenticated STANDARD-only API with exact-origin JSON/custom-header/
  Fetch-Metadata CSRF checks on every mutation;
- server-derived opaque owner ID, server-issued execution lease and source versions;
- bounded public Task read, deterministic local `task.create.v1` preview, digest +
  nonce confirmation, TaskStore reuse and atomic Task/receipt/marker/audit write;
- startup/reload reconciliation hook for crash-after-commit/before-fast-signal;
- default-off production enablement and exact no-fallback OpenRouter route contract;
- responsive Mimi tab with durable reload, preview/confirm/reject, receipt, feedback,
  offline/error/draft-retention and bounded event UI.

## Observed checks

| Check | Result |
|---|---|
| Backend Ruff | PASS — `All checks passed!` |
| Focused Mimi/backend | PASS — 48 passed, 4 PG deselected |
| Full backend non-PG | PASS — 495 passed, 1 skipped, 212 PG deselected |
| Frontend ESLint | PASS |
| Frontend unit | PASS — 21 files, 148 tests |
| Frontend production build/PWA guards | PASS |
| Playwright Mimi mobile 390×844 + desktop 1280×800 | PASS — 2 tests |
| Alembic graph | PASS — single head `0014` |
| Migration drop guard | PASS — `migration_drop_guard=ok` |
| PostgreSQL clean upgrade + drift | PASS — `base -> 0014`; `migration_drift=empty` |
| PostgreSQL full round-trip + drift | PASS — `0014 -> base -> 0014`; `migration_drift=empty` |
| Focused Mimi PostgreSQL API | PASS — 1 passed |
| Full PostgreSQL lane | PASS — 212 passed, 496 deselected |
| Live provider route card | NOT_RUN — no approved exact route pin/secret supplied; production gate remains off |

The failed initial non-PG regression after adding scheduler reconciliation was not
accepted as green: the hook had altered test/runtime seams. The implementation now
injects the hook only into the enabled app timer; focused CronTimer/lifespan
regression then passed 62 tests and the full backend suite passed as recorded above.

Frozen-candidate self-review also closed three fail-closed gaps before publication:
same client IDs with changed message/feedback content now return 409; confirmation
retries bind the original nonce as well as digest; and any distinct new user turn
marks an earlier pending preview stale because P1 cannot safely prove a supplement
is harmless. Change-set operations are encrypted at rest, not retained as JSONB.

The real PostgreSQL lane found two issues hidden by the fast tests. Alembic's asyncpg
driver rejects multi-statement prepared commands, so `0014` now executes each DDL
statement separately and the schema/model registry explicitly includes every Mimi
table, constraint and partial index. PostgreSQL also ordered scalar-FK child inserts
before `mimi_run`; the service now flushes the parent run before writing its events,
message and provider-call intent. Both fixes are covered by the clean migration
round-trip, empty-drift checks and focused API test above.

Two exploratory full-PG invocations were red and were not accepted: the first omitted
the CI role variables; the second used non-canonical local role passwords. After the
throwaway database was reset to `base` and configured exactly like the Migration QA
workflow, the canonical full lane passed 212 tests. No Neon or real user data was used.

## Remaining closure gate

Freeze and commit the PostgreSQL fixes, rerun proportional regression and repository
hooks, then publish the candidate as a PR and require its exact-head CI gates before
merge. Production real chat remains separately disabled until MIDEX selects an exact
route and its route card passes.
