# Task 058C — streamed run and provider-policy receipt

Date: 2026-09-18

Branch: `feat/058-mimi-dogfood-recovery`

Base implementation before this package: `746846a293c2f3ab01a75d31ccbfe52b5ada78a7`

## Outcome

058C is implemented and its automated local gates are green. This receipt is
not the 058D live-model/Owner dogfood acceptance.

Delivered behavior:

- authenticated POST + fetch/SSE observation without the generic 20-second CRUD timeout;
- process-owned background runs: closing/switching the presentation surface does not cancel work;
- durable sequenced application events, encrypted `assistant.delta` payloads at rest and no partial tool JSON exposure;
- elapsed time, truthful stages, 15-second ephemeral heartbeat and explicit cancel;
- retryable checkpoint Resume linked by parent run ID without duplicating the user message;
- unknown outcomes never auto-redispatch; explicit Reconcile consults generation metadata when an ID exists and otherwise remains fail-closed;
- 30-minute default lease, adjustable up to 120 minutes; exact deadline is shown by the UI;
- terminal union accepts ordinary assistant text or one independently validated `task.create.v1` proposal;
- exact lane pins model/provider/quantization with fallback off; adaptive lane stays inside provider/quantization allowlists with ZDR, data collection denied, parameter compatibility and max-price caps;
- the unsupported `parallel_tool_calls` parameter from Task 057 is omitted;
- actual provider/model/usage plus connect/TTFT/duration/throughput timing are retained;
- the three approved Mimi/Orbit/microSched concept boards are preserved under
  `docs/assets/brand-concepts/` with hashes and copy/production boundaries.

Brand boundary: the first code-native Mimi mark was an unapproved interpretation
of the concept board. The Owner rejected it and it was removed from this package.
The current functional icon is a neutral placeholder, not a claimed brand
implementation. Brand rollout waits for the separately approved identity asset
contract and must replace the placeholder as one coherent package.

## Verification

Observed PASS:

- Ruff on 058C backend/app/tests: PASS.
- Focused backend + PostgreSQL stream/lifecycle suite: `48 passed`.
- Backend non-PG suite: `504 passed, 1 skipped, 213 deselected`.
- Full throwaway PostgreSQL lane with CI-equivalent environment: `213 passed, 505 deselected`.
- Frontend ESLint + TypeScript: PASS.
- Frontend unit suite: `21 files, 148 tests passed`.
- Production frontend build, PWA surface and Apple icon guards: PASS.
- Focused Playwright Mimi matrix: `4 passed` across Chromium mobile 390x844 and desktop 1280x800.
- PostgreSQL integration specifically exercised: text streaming, ciphertext-at-rest, retryable → Resume, explicit cancel after provider dispatch, unknown-outcome retry refusal and generation reconciliation.
- Post-restart focused rerun: `18 passed`; its one unavailable PostgreSQL case
  reported local `ConnectionRefused` because Docker had stopped. After restarting
  the exact throwaway `microsched-058c-pg` container, that case passed separately
  (`1 passed`).

The first full PostgreSQL attempt was invalid evidence because it omitted the
CI `CI_*` variables and used the migration role where historical tests require
the bootstrap owner. It produced setup/privilege errors. The lane was rerun
with the exact CI-shaped synthetic environment and passed completely; no gate
or assertion was removed.

## Boundaries still open for 058D

- five consecutive valid live full-app model terminals;
- three full live journeys including ordinary text, clarification and Task preview/revision/confirm/reject;
- real transport-disconnect/reconnect observation in the full local shell;
- Owner manual dogfood approval;
- full Playwright suite and final diff/status review on the frozen package head.

No production enablement, Neon action, merge or deploy is implied by this receipt.
