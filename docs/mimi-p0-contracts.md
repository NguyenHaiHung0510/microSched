# Mimi P0 contracts and seam map

Status: P0 local synthetic substrate. This is not a Mimi runtime, a production schema, or permission to start P1.

## Baseline and ownership

- Task: `055-mimi-p0-sandbox`; branch `feat/055-mimi-p0-sandbox`; base `origin/develop@7806f4e9f75ef66110ae3d485cffd036d42d94c1`.
- Existing microSched foundation is reused: FastAPI modular monolith, SQLModel/Alembic, Task/Note/Calendar/Tracker/Subscription, `app.core.crypto`, local dev-session, React/Vite, and Postgres QA bootstrap.
- P0 does not register an Agent API/router, provider, background job, migration, live capture, or new production config.

## P1 interface and authority map

These are the minimum endpoint purposes, not final URL names. Every protected endpoint remains under the existing authenticated router, uses the existing same-origin session/CSRF posture, and must not accept `allow_private`, UI-grant timestamps, arbitrary Store calls, SQL, URLs, shell, secrets, or policy overrides from model output.

| Purpose | Request | Success | Errors/state | Authority and bounds |
|---|---|---|---|---|
| Start STANDARD run | client idempotency key, message, sensitivity, source-version refs | run ID, accepted state, execution-lease summary | 401; 409 idempotency/content conflict; 422 invalid bounds; 429 lane/budget | Server issues owner/run identity and capability snapshot; P1 only Task bounded read + propose-create. |
| Read run/events | run ID, cursor, bounded page size | neutral state plus permitted page | 401/404; 403 private locked; 409 stale cursor | PRIVATE reveals no title/snippet/counters/tool detail while locked. Cursor and response have explicit bounds. |
| Submit/revise preview | run ID, expected frontier, change-set version | frozen typed operations, digest, expiry | 409 stale run/source/frontier; 422 unsupported tool/tier | Proposal only. Preallocated IDs, canonical args, expected entity versions, no mutation. |
| Confirm/reject preview | change-set ID, digest, decision, nonce | atomic receipt or rejected state | 403 grant/lease; 409 stale/digest/nonce/idempotency; 410 expired | Backend reads frozen payload, re-checks lease/source/current entity, executes one related transaction, writes receipt and refresh marker together. |
| Save feedback | stable client ID, target ID/type, encrypted comment/expected, bounded evidence refs | server ACK and feedback ID | 403 locked PRIVATE; 409 client-ID conflict; 413 cap; 422 secret-bearing/invalid bundle | No plaintext persistent retry queue. `ACKNOWLEDGED` remains unresolved until explicit triage/terminal decision. |
| Review feedback | state/filter/cursor/page size | bounded encrypted records/references | 403 private locked; 422 invalid transition | NEW → ACKNOWLEDGED → TRIAGED → LINKED_TO_FIX/CASE → VERIFIED or DISMISSED. Model never self-closes. |

### Canonical P0 envelopes

- `mimi.execution-lease.v1`: server issuer, owner/run identity, sensitivity, capabilities, source versions, deadline, turn/tool/cost ceilings and revocation.
- `mimi.change-set.v1`: ordered typed operations, expected versions, digest, single-use nonce, expiry and server-scoped idempotency key.
- `mimi.evidence-bundle.v1`: environment/fixture/source snapshot plus application-visible assembled prompt, request, response, tool args/results, route/config/usage and truthful completeness manifest.
- `mimi.feedback.v1`: stable client ID, target/comment/expected, evidence refs, sensitivity, state and unresolved flag.

## Required state/fault matrix for P1

| Boundary | Required case | Expected behavior |
|---|---|---|
| Provider | definitive retryable failure | `WAITING_RETRY`; bounded retry may issue a new call but never replay a committed domain mutation. |
| Provider | timeout/stream closes with uncertain outcome | call `OUTCOME_UNKNOWN`; capture `INCOMPLETE`/`FAILED` with missing parts; auto-retry false until reconciliation. |
| Steer | new Owner input while building/running | persist input, explicitly rebase/cancel/continue according to frontier; never silently omit. |
| Source | source version changes after preview | `STALE`; require fresh preview; no retry on latest state. |
| Confirmation | same nonce/digest repeats | return prior receipt exactly; different content under same idempotency key is 409. |
| Commit | domain commit succeeds, process fails before reminder signal | durable refresh-needed marker survives; recovery converges without duplicate mutation. P1 implementation test remains required. |
| Privacy | STANDARD run touches PRIVATE source | deny before decrypt/return/egress; neutral reason; no implicit promotion. |
| Lock/revoke | UI soft-lock | hide/purge reads and callbacks, preserve bounded WIP only in volatile store; run continues only inside valid lease. |
| Lock/revoke | logout/session invalid/revoke | hard-wipe volatile WIP and stop later steps; no rollback of committed work. |
| Feedback | refresh/restart/reseed/reset | server-ACK acknowledged/unresolved item and full encrypted bundle remain available with original environment/fixture/source snapshot. |

## Six pre-code seams and current integration points

| Seam | Reused source / P0 lock | P1 or later work still disabled |
|---|---|---|
| Legacy schema | `app.domain.models.Message` and `AuditLog` show encrypted message/trace seams; P0 fixture cases require distinct snapshot versions and truthful partial state. | Migration/backfill and zero/mixed/interrupted rehearsal require a separately approved schema decision. |
| Central privacy coordinator | `app.domain.models.Gate`, `app.domain.private_gate`, protected API mount; lease contract forbids model-created bypass. | Cross-surface coordinator/runtime registration and soft-lock DOM/cache behavior are P3; STANDARD source boundary is P1. |
| Private note index | Existing `Note.embedding` is nullable; contract retains no-index/no-late-worker requirement. | DB constraint/trigger/worker fence and any live backfill remain disabled. |
| Run lease/authority | `ExecutionLease` fixes issuer, owner/run, capability/source snapshots, deadline/revocation and budgets. | Admission/re-check at every dispatch/tool/commit boundary is P1; private lease/UI coordination later. |
| Change-set adapter | `FrozenChangeSet` fixes args, versions, digest, nonce and idempotency. Existing Task domain/store is the first target adapter. | P1 implements Task create transaction/CAS/receipt/refresh marker; other operations and undo wait. |
| Durable handoff/attachments | evidence completeness distinguishes full/partial/failed; source snapshots prevent reused fixture IDs from impersonating old evidence. | Provider call result fence/recovery is P1. R2 protocol/upload/parser and accepted attachments remain OPEN-05/P4. |

Reminder/cache hook: existing domain mutation/reload code is an integration reference only; P1 must add the durable same-transaction marker and commit→crash→recover test before claiming this seam complete.

## Review/evidence lifecycle

P0 review state lives under ignored `.local/mimi-p0/review`, while disposable domain fixtures are rows with exact manifest-owned IDs. Ordinary `reset` deletes only those IDs and cannot address the review directory. The local store encrypts every bundle, feedback row, and idempotency binding through `app.core.crypto`; filenames contain only UUIDs or SHA-256 of client IDs. It stores no API keys, Authorization/proxy headers, cookies, refresh/access tokens, auth headers, or provider hidden reasoning.

The P0 store enforces a 1 MiB plaintext cap per evidence bundle, 64 KiB per feedback record and 8 KiB per client binding. These are local substrate safety ceilings, not approved production retention policy. Same-process writers share a per-root lock, and an encrypted pending intent completes an interrupted entity/binding write when the store reopens. Multi-process/distributed concurrency, exact production caps and quota UX remain P1/pre-live gates.

This local filesystem implementation is synthetic substrate only. Before real capture the Owner must approve a finite packet containing:

1. exact full-evidence TTL and per-run/per-chat/global byte caps;
2. warning thresholds and UI behavior before expiry/cap;
3. verified export destination/format/integrity and extension flow;
4. deletion/source/privacy mapping, object encryption/key isolation, backup-aging truth;
5. explicit teardown behavior that refuses deletion until required export/preservation verifies.

No live capture, silent truncation/eviction, real/private export, or 30-day full-payload default is enabled by P0. The separate proposed 30-day operational trace does not set the full-evidence, execution, recovery, or audit lifecycle.

## Local commands and stop behavior

From `backend`:

```powershell
uv run --frozen python -m scripts.mimi_sandbox start --install
uv run --frozen python -m scripts.mimi_sandbox status
uv run --frozen python -m scripts.mimi_sandbox verify
uv run --frozen python -m scripts.mimi_sandbox reset
uv run --frozen python -m scripts.mimi_sandbox stop
```

`start` owns one exact labeled container (`microsched-mimi-p0-055`), local volume and loopback database/ports. `reset` never truncates and never removes the encrypted review store. `stop` stops only exact recorded processes/container and deletes nothing. There is intentionally no broad cleanup command or production-like target override.

The runner starts children from an allowlisted process environment, disables dotenv loading for those children, and injects only synthetic database/auth/encryption values. Existing containers must match the exact task label, image, `127.0.0.1:55455` binding and named volume mount. A manifest reset refuses rather than deletes any unowned Entry/Subscription rows that depend on the synthetic trackers. On Windows, recorded application PIDs must still own the expected loopback listeners before stop; a stop timeout still reaches the exact-container stop path.

When feedback capture becomes usable in P1, remind the Owner to schedule the microSched feedback review every three days and choose time/destination then; P0 creates no automation. When L2 begins, remind the Owner to retrieve the actual Codex planning chat from about one month earlier; never import it into these synthetic fixtures automatically.
