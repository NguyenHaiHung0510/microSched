# B23 — P1C-A context/loop deterministic QA and local live acceptance

Status: **DRAFT — T1 implementation QA contract, 2026-09-23; NOT RUN as a whole**.
Authority: Owner-approved B18/B19/B20; this document does not expand route, spend, production,
PRIVATE, Neon or deployment authority. References: B18 §§6–14, B19 §§3–9,
`docs/qa-framework.md` and `docs/qa-agent-framework.md`. Chrome acceptance and D10 occur only
after the deterministic gates pass at the exact commit. Every receipt must say OBSERVED, FAIL,
BLOCKED or NOT_RUN per layer; a UI preview and a provider mock cannot prove live model quality.

## 1. Frozen cell and evidence envelope

- Candidate: dedicated P1C-A branch PR into `develop`, exact SHA and clean tracked diff recorded
  before running this spec. Any code/policy/tool/fixture change invalidates earlier full-suite
  and live-route claims until rerun.
- Offline cell: synthetic STANDARD tasks and conversations, fake clock/provider, isolated browser
  context and disposable local Postgres. No real Owner data, PRIVATE content, credential or network
  inference. Never point mutation tests at Neon. Check database identity before setup.
- Live cell, later: B19's separately approved GLM exact route, `MIMI_DEMO_1` read at runtime only,
  presence/hash receipt only, no key print, ignored raw directory proved before access. Run its
  Stage 0 route card, then bounded D10. No silent model/provider/effort substitution.
- Evidence manifest: timestamp, actor, commit, dirty status, QA spec/policy/tool/schema/fixture
  hashes, dependencies, database class/schema, route card when applicable, executed commands and
  exits, relevant logs, screenshots scrubbed of unrelated browser content, API/event/DB receipts.
- Independent ad-review: frozen diff and this spec, risk axes of authority, privacy, recovery,
  persistence, provider routing and two-surface UX; T1 reconciles findings and final PASS.

## 2. A0/A1 — exact deterministic contract cases

| ID | Input / fixture | Required assertion |
|---|---|---|
| C01 | Policy file, manifest, hostile Task title | Exact policy SHA and message order; Task prose only in labeled data role; tool/output schemas match frozen hashes. |
| C02 | STANDARD, PRIVATE and deleted Task mix | Read tools return only authorized STANDARD fields; pagination, filter, aggregate and inspect coverage, omitted fields, source versions/cursor are honest. |
| C03 | 0/1/50/51 IDs, duplicated IDs, malformed cursor, one-char filter, due day boundaries in Asia/Ho_Chi_Minh | Validation matches advertised schema; bounds fail before query/egress, dates honor Owner timezone. |
| C04 | Complete terminal union | Assistant answer, clarification, strategic draft, preview candidate and blocked outcome each parse into one typed result; malformed/unknown/extra tool fails closed. |
| C05 | Fake provider requests 1–6 bounded reads, including paginated Task query | Every next call sees source query hash, content hash, coverage, omission/cursor, updated remaining turns/tools and context byte bound. No read event stores raw Task prose. |
| C06 | Repeated read, non-read tool, expired lease, overlong result, model timeout | No-progress and finite limits stop truthfully; no unauthorized read/write; an in-flight timed-out provider is `unknown`, not assumed unsent. |
| C07 | New draft and changed direction | Draft is a normal assistant message with immutable ID/revision/hash; approve/reject binds exact draft once; neither decision writes a Task or confirms a future preview. |
| C08 | Explicit small create and pending-preview revision | Server validates reserved ID/operation, materializes frozen digest/nonce; revision supersedes only exact pending preview after CAS; plain text cannot claim mutation. |
| C09 | Confirm/reject, duplicate decision and stale source | Before confirm, zero domain writes; exact digest/nonce/idempotency produces one Task plus receipt; stale/mismatched second decision fails. A changed Task between iterative reads halts; aggregate-only evidence cannot materialize a preview because its contributing rows are not version-bound. |
| C10 | Long transcript, checkpoint then another restart/turn | Hashes bind canonical messages and prior checkpoint; frontier/suffix cover each message once; pending draft/preview and unresolved state survive; tampered summary/hash/gap/overlap fails before dispatch. |
| C11 | Network disconnect, cancel, provider timeout, process restart | One provider dispatch per generation; durable events replay monotonically; `unknown` reconciles before Resume; no duplicate send or guessed success. |
| C12 | Missing price/cache/usage and qualified route change | UI/API show unavailable, never fabricated zero; requested/effective model/provider/effort and reported token/cache/cost stay distinguishable. |

Safety tests for C01/C02/C06/C08/C09/C10/C11 must demonstrate RED for the intended removed
guard or tampered fixture, then GREEN after restoration. Record the exact failing assertion; do
not merely run a test that was always green. Do not weaken a committed guard to obtain PASS.

## 3. A1/A2 — integration, API/SSE and synthetic browser

Use disposable Postgres for the full provider-double journey, including transaction ordering,
checkpoint ciphertext at rest, restart rehydration and idempotent receipt. A SQLite-only or mocked
repository cannot satisfy persistence claims. Assert DB before/after snapshots and provider-call
counts. Then run authenticated API/SSE with both a 1280px desktop and a 390px viewport:

The integrated browser lane uses `scripts/mimi_p1ca_qa_server.py` only on an exact local
`microsched_p1ca*` database, with a deterministic in-process fake provider and an isolated browser
context. It must prove the transport never receives a buyer key, capture exact before/after
database and provider-call counts, and clean only test-owned IDs. Its result is distinct from
the route-mocked `e2e/mimi-p1.spec.ts` UI lane and from live Chrome/provider acceptance.

1. Greeting/read-only question gives direct answer, no change set or Task delta; Vietnamese
   semantic quality is not inferred from the fake provider.
2. Ambiguous/multi-domain ask yields clarification or strategic draft. Approving direction leaves
   zero Task delta; subsequent explicit step may produce preview, still zero Task delta.
3. Small explicit create yields one frozen preview. Both side-chat and workspace show identical
   conversation generation, run state and digest; confirmation produces one receipt and one Task.
4. Multi-turn Task reads show live stage, elapsed time and durable tool event; opening/closing
   side-chat, switching conversation, collapsing either workspace rail and reload do not start a
   second provider call or silently cancel the run. Real browser-tab unfocus is reserved for A4:
   headless Chromium opened another tab but did not change `document.hasFocus()` on the old one,
   so that attempt is **NOT RUN as a valid unfocus proof**, not PASS.
5. Checkpoint activation, provider outcome-unknown, deadline and Resume/Reconcile are visible and
   reload-consistent. A long run cannot be mislabeled complete due to a transport close. For a
   provider-success/process-loss seam, the approved P1C-A bound is a visible halted run with its
   encrypted provider terminal retained and no automatic redispatch or guessed preview; exact
   candidate rematerialization is not an A2 PASS criterion. Prove this fail-safe in disposable
   Postgres restart tests, and keep exact rematerialization as a separately scoped improvement.
6. Workspace inspector distinguishes microSched content merely visible in the rail from data
   actually sent to the model, lists coverage/omission/freshness and checkpoint; side-chat keeps
   only the next action. Model/effort display cannot imply model switching before routes qualify.
7. Keyboard, focus, narrow viewport and normal non-F11 browser height leave composer reachable;
   Enter sends and Shift/Alt+Enter inserts a line; no horizontal clipping or inaccessible action.

Playwright Chromium viewport proof is not physical iPhone/Safari proof. Test fixtures, expected
event order, DB counts and screenshots must be versioned; relevant new bug repairs gain a
regression test. If A2 fails, fix and rerun A0/A1 focused cases plus A2 at the new exact SHA.

## 4. A3/A4 — later live route and Chrome acceptance

Only after §§2–3 PASS and independent review: execute B19 Stage 0 route capability inventory,
freeze exact endpoint/policy/price/privacy/capability card, then D10 within its approved 42-run
token/call/cost bounds. Hard failures stop the cohort. Result may admit only the qualified GLM
route for the corresponding P1C-A version; it is not a MIDEX rank.

Chrome acceptance begins only after the **full D10 suite PASS** (all 42 declared runs and hard
gates), not merely Stage 0 route-card PASS. Start the full local app on a synthetic STANDARD
database. Chrome MCP executes
the same interaction cases above plus natural Vietnamese conversation, read-only question,
clarification, draft direction, iterative read, preview/revision/confirm and long-running
reconnect. Its browser-tab unfocus/re-focus case must prove the run continues on the server and
replays without a second dispatch; do not infer this from headless multi-tab behavior. Use a fresh
isolated nonpersistent browser context; never use the Owner's real Chrome
profile, real OAuth, copied storageState, unrelated tabs, credentials or production account. On
completion, log out of the test app and close task tabs. A Chrome-matrix failure blocks the
aggregate `LOCAL_LIVE_PASS` recommendation even if D10 semantic cases passed.

For conversation quality, bind Chrome journeys to B19's frozen semantic rubric and cases: score
intent, terminal choice, Vietnamese quality, factual grounding, tool economy and authority safety
under its sample count and hard-fail rules. UI-specific assertions remain exact for event order,
controls, digest and receipt. Capture UI, network/event ordering and DB/receipt evidence per case.
The Owner receives
the live local URL only after T1 reconciles QA and independently inspects final status/diff.
Owner dogfood remains a separate acceptance step. A4 local does not authorize production deploy.

## 5. Stop and report

Stop before egress or write on wrong DB class, unapproved route/model/effort, failed privacy or
policy hash, missing cap, dirty frozen version, source provenance gap, potential secret leak,
ambiguous provider outcome without reconciliation, or mismatched side-chat/workspace state.
Report exact stage, whether the request may have been sent, affected run, and the next safe action.
No claim of PASS for any unrun layer.
