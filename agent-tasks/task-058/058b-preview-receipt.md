# Task 058B conversation foundation preview receipt

Date: 2026-09-17 21:17 +07:00

Branch: `feat/058-mimi-dogfood-recovery`

Result: **READY FOR OWNER UI PREVIEW — not 058C/runtime/live-provider acceptance**

## Observed implementation

- Conversation title metadata is encrypted with the existing per-conversation
  DEK and conversation-bound AAD. Auto-title is bounded to 80 visible Unicode
  characters; an Owner rename locks it against subsequent auto-title changes.
- Active/archived lists have deterministic `updated_at DESC, id DESC` ordering,
  bounded cursor pagination, latest-run state, and no permanent delete action.
- Create accepts a client idempotency key. Rename/archive/restore use a separate
  metadata version and row lock, so transcript generation does not become a
  presentation-state concurrency token.
- Archive is reversible and archived conversations are excluded from
  `current`; restore returns them to the active list.
- The Control Center Conversations module now has a management rail, the shared
  Mimi transcript, and a right workspace rail at wide desktop breakpoints.
  Smaller layouts open the rail in a dialog.
- The right rail exposes compact read-only Task, Calendar, Notes and Tracker
  views, plus Preview and Run. It is an Owner viewport: rail visibility does
  not grant the model access to that content.
- Usage period controls now distinguish rolling today/7/30 days from fixed
  calendar week/month/quarter/year. Compact provider snapshots are the approved
  future fallback for source APIs with short history; 058B does not fabricate
  or integrate provider billing data.

## Observed verification

| Check | Result |
|---|---|
| Ruff for changed backend/tests/migration | PASS |
| Focused backend guards/contracts | PASS, 31 tests |
| PostgreSQL `0001 → 0015` migration | PASS on dedicated throwaway PostgreSQL 18 + pgvector |
| Alembic current | PASS, `0015 (head)` |
| Migration drift | PASS, `migration_drift=empty` |
| PostgreSQL Mimi API scenario | PASS, including create retry, cursor list, rename lock, archive retry, restore and ciphertext-at-rest proof |
| Frontend lint/typecheck | PASS |
| Frontend unit suite | PASS, 21 files / 148 tests |
| Frontend production build | PASS, including icon/PWA guards |
| Focused Playwright acceptance | PASS, 4/4 at Chromium desktop 1280 and mobile 390 |
| Headed local browser review | PASS at 1440×900: three-column workspace visible, no document horizontal overflow, Context/Preview/Run switch correctly |

The first PostgreSQL migration run correctly failed because revision `0015`
sent three statements in one asyncpg prepared statement. The migration was
split into atomic statements; a clean rerun reached `0015 (head)` and drift was
empty.

Two focused Playwright iterations exposed test-fixture problems: an ambiguous
accessible label and a mock message response that discarded a renamed title.
Both were corrected; the final run passed 4/4. The application implementation
was not weakened to make the tests pass.

The canonical backend suite without PostgreSQL CI variables produced 508 pass,
201 skip and one configuration failure because a historical role-split test
accesses `CI_APP_DATABASE_URL` without skipping when it is absent. Running that
exact remaining test with the dedicated throwaway application-role URL passed
1/1. An earlier all-suite invocation carrying only `NEON_MIGRATOR_URL` was an
invalid mixed-lane invocation and is not claimed as product evidence.

## Preview endpoints

- UI with hot reload: `http://127.0.0.1:5158/`
- Synthetic API: `http://127.0.0.1:8058/`
- Dedicated migration/API database: loopback PostgreSQL on port `55458`.

All preview data is synthetic. No real provider key, production account or
personal payload is used.

After the Owner restarted the machine, the loopback synthetic API and Vite
preview were restarted on 2026-09-18 07:30 +07:00; both endpoints returned HTTP
200. The throwaway PostgreSQL lane was not needlessly recreated for UI review.

## Evidence boundaries

- 058B conversation schema/API/UI and focused local acceptance: **PASS**.
- Owner approval of the current 058B workspace UX: **PENDING**.
- Streaming, server-owned background runs, lease/cancel/resume/reconcile,
  OpenRouter analytics/provider policy, live-model path and 058C: **NOT RUN / not implemented**.
- CI, physical device, production migration/deploy and Owner live dogfood:
  **NOT RUN**.
