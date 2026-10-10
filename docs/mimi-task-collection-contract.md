# Mimi Task Collection contract v1 — A1 freeze

Scope is approved Full A STANDARD nonprivate Task only. Latest Owner keeps
DeepSeek V4.1 Flash only and grants autonomous workspace correction. S1 means
whole Task depth before other domains; Batch B remains separate. Existing auth,
CSRF, ownership, PIN/private and same-origin gates are reused without weakening.

## Commands, versions and transaction boundary

`task.collection_candidate.v1` is an untrusted proposal, never execution.
Server produces one `ChangeOperation(tool="task.collection.v1")` containing
`schema_version=mimi.task-collection.v1`, a frozen selection ref, 1..200 unique
Task entries, named action, canonical fields/children/reminder effects and
before/after snapshots. Empty, duplicate or oversized requests fail before write;
maximum canonical command1MiB. Each existing target binds UUID, collection_version,
updated_at, full child identities/versions and exact active reminder ID/revision/
status (including explicit absence). New Task/child IDs are server-issued UUIDv7.
Each target has one coherent entry; multiple edits to it are combined before freeze.

Actions: create, edit, soft_delete, restore and compensating undo. Patch fields:
`title`, `body_md`, `status`, `priority`, canonical complete due triad
`due_precision/due_on/due_at`, `pinned`. Omitted means preserve, explicit nullable
null means clear. Non-null fields reject null/blank; dates are civil Vietnam dates,
instants require timezone. ID/timestamps/completed_at are server-owned; completion
derives completed_at. Privacy transitions, hard delete and recurrence are rejected.
Body is preserved verbatim up to the command bound, never display-truncated storage.

Checklist operations: append, patch content/completion/position, full active-ID
reorder, soft_remove and restore exact tombstone. Child must belong to the target;
no reparenting. Restore requires live nonprivate parent; no duplicate/missing IDs
or accidental undelete from normal reads. Positions are nonnegative integers;
reorder contains exactly the active IDs, no hidden dropped child. Changes to any
child advance aggregate Task collection_version even through old/raw DB writers.
New app normal lists/counts/content filter child tombstones. Task delete preserves
children; Task restore preserves individual child tombstones.

Freeze validates all entries and computes visible old→new fields, checklist and
reminder effects from current locked state. Confirm reuses the encrypted frozen
operation; it NEVER reruns a query or calls the model. Existing change-set ID,
digest, nonce, expiry, owner, run generation/frontier and lease bind the request.
Lock order: global idempotency advisory lock, conversation/run/change-set, all
Task parents in UUID order, their children, then reminders in deterministic order.
Validate every target before applying any. A stale member, privacy drift, missing
child, changed reminder or invalid inverse gives zero domain writes.

Same transaction contains all domain changes, one existing execution receipt,
encrypted before/after/recovery material, refresh marker and durable notification
intent. Exceptions rollback all of these. No store helper commits. HTTP success
follows commit; disconnect/timeout is ambiguous until receipt lookup converges.
Same key+same digest/change-set/nonce returns the original receipt; any differing
binding fails closed. Lookup remains owner-bound; global unique key collisions
must return a conflict, never another owner's receipt. No blind unknown replay.
Existing v1 create receipts stay readable; v2 result has ordered Task IDs/counts
and historical first-task anchor, plus encrypted recovery content.

Undo is a NEW preview and compensating confirmation, bound to original receipt
and exact post-write Task/child/reminder versions. It restores only the fields
changed by that operation; unrelated content survives. Concurrent changes conflict.
Create undo soft-deletes new rows; delete undo restores those rows; checklist
removal undo restores exact child identity/order. No sent Push retraction or
historical reminder rearm. Receipts/recovery survive reload without a toast.

## Selection, aliases and content paging

`mimi.selection.v1` records scope/intent, considered alias/typo variants, each
query's filter/sort/page cursor obligation and completion, deduplicated exact IDs,
collection versions/as-of, included/excluded/uncertain with reasons, and omissions.
Server derives seen IDs/versions from actual tool receipts, not model assertions.
Selection checkpoints use encrypted existing MimiEvent payloads, with sequence/ref
and hash; continuation/compaction carries obligations and ref, not just prose.
Changing classification creates a new snapshot. Client/UI search/page filters
do not change the frozen confirmation set. A missing next page or variant is an
open obligation; query-complete never implies semantic-complete. Confirm-all
requires explicit resolved scope and exact targets. An explicitly named subset
can be confirmed with honest remaining omissions; never label it all.

Training fixture49 has48 actual sessions (aliases and typos included) and one
incidental mention, separately excluded with reason. Due date never substitutes
for occurred/completed date semantics. Generic alias families are demonstrated;
no regex hardcoding of one Owner sentence, no promise of perfect semantic recall.
Tool pages50, UI pages20 and inspect batches50 are independent of full set200.
Content pages preserve full body/checklist values, exact parent version and child
IDs; continuation must expose remaining body/item text offsets without silent
500-character truncation. Current stale page stops/rebuilds; keyset traversal over
changed data is not a repeatable snapshot. Writes freeze current exact versions.

## Reminders

Read configuration/status/history under STANDARD source gates. Configure absolute
future instant or relative offset with explicit date anchor time where needed;
cancel requires expected active ID/revision/status and source version. Active
sending or ambiguous dispatched work blocks mutating reminder effects until
reconciliation. No silent replacement or rearm. Existing one-shot helpers/triggers
are reused with a prevalidated collection contract.

Complete/delete cancel eligible pending/needs_reschedule reminders atomically.
Due change recalculates relative reminders from the new anchor; absolute due
stays fixed unless explicitly replaced. Missing/past new anchor becomes
needs_reschedule, no new past delivery. Restore never autorearms sent/past/
cancelled/superseded occurrence; explicit future configure creates a new one.
Preview shows these effects and the exact reminder CAS. Dispatcher reload follows
commit via durable refresh marker; device receipt is separate from domain commit.

## Agent bounds and graceful finalization

At most8 validated READ requests per model response, sequential execution under
remaining64-read budget, deadline, payload and no-progress checks. Validate entire
batch/schema/allowlist before first read. Execute fitting requests, mark remaining
not_run with reason; do not silently discard or relabel cap as provider failure.
32 main turns retain ONE no-tools final slot inside32. Final wire request omits
tool schemas and sets tool_choice=none, with completed/not-run reads, selection
obligations and provenance. Exhausted deadline/context or unknown provider yields
honest deterministic partial/reconcile state, no extra paid call. Legacy loop and
LangGraph must have equivalent safety outcomes and encrypted restored reads.
No new polling/retry market job or money manager; existing process admission and
unknown-outcome journal remain authoritative. Bare greeting is natural Vietnamese,
no unnecessary tool. Proposed, confirmed and committed remain distinct.

## Model/effort and eligible provider pool

Only `deepseek/deepseek-v4.1-flash` is admitted this shift. Existing MiMo v2.6 Pro
and GLM5.3 Flash stay unqualified for tool/compaction continuity; Luna retains prior
ZDR404 evidence. These are next candidate cards after a separate scoped grant,
not current availability claims. Prototype Flash/Sol/Luna/Opus labels are synthetic.
Provider fallback keeps EXACT selected model and supported Owner-selected effort.
Requested/default/mapped/effective effort and actual endpoint are recorded separately.
Unsupported effort fails explicitly; no silent lowering or cross-model substitution.

Adaptive native routing is fenced by a local timestamped eligible endpoint pool:
ZDR=true, data_collection=deny, required tool/effort parameters, qualified precision,
exact routing-tag coverage, and input/output price ceilings. Unknown mandatory
metadata or variant coverage fails closed. Strict uptime>95% over1d by default;
user may configure finite threshold0<=x<100 and window1d/30m. No fallback to a
lower privacy or relaxed criterion. Eligible session affinity is soft; no default
hard provider.order or permanent DeepInfra pin masquerading as adaptation.
Catalog refresh on demand, TTL5min, timeout10s, max2MiB, single flight, one fetch
per new run and manual cooldown30s; no automatic retries/background polling.
Pool/config/source/time/hash frozen per run. Native filters do not prove local
uptime; exact endpoint matching must be supported, not inferred from base slug.

## Encrypted causal feedback

Reuse existing MimiEvidence and MimiFeedback tables. Server derives the target's
conversation/run/request→answer causal range, canonical messages/calls/tool/source
versions/config/selection/operation/receipt references. Owner/client bundle IDs
are checked for same owner/conversation/run/causal scope; no cross-run attachment.
Add nullable encrypted content field with resource-bound AAD; existing legacy rows
remain valid. Metadata is IDs/hashes/counts/completeness, no prose or secrets.
Max1MiB per bundle, finite causal range; omitted/truncated parts make INCOMPLETE,
never fabricated COMPLETE. Logical expiry90days, no automatic physical purge.
Receipt recovery ciphertext is durable separately. No hidden reasoning, auth
headers or key values; no transcript promotion into memory/global harness.

## N2 completion and device opt-in

Durable in-app unread attention plus separate per-device Mimi opt-in/default off.
Reuse existing PushSubscription transport but never claim legacy subscriptions
for Mimi automatically: explicit authenticated device proof/registration binds
opaque existing owner identity and subscription. No account-wide/presence tracking.
Three additive records: device preference, completion intent, per-device delivery.
One intent per canonical completion event/kind. Completion/valid approval-ready
state and intent commit together; dispatcher wakes post-commit and scans durable
pending work at startup, not cron/reminder per run. Read-only answer can notify.
Canonical STANDARD title max80chars and visible snippet max240chars, markup
stripped without a new model call. Approval-ready says not yet applied; expired,
superseded/stale preview suppressed. Private provenance is excluded entirely.

Dispatcher rechecks owner, consent, STANDARD and preview before send. Bounded
existing20s send timeout, four attempts/backoff30/120/600 for PROVEN safe retries,
45min attention TTL bounded by preview expiry; up to100 opted-in devices and
1000 pending items per snapshot, bounded owned worker capacity. Send failure never
rolls back committed domain. HTTP accepted is not displayed/read. Timeout or crash
after dispatch is UNKNOWN; startup never resets sending/unknown to retryable.
Tracked late result may reconcile with exact delivery identity; otherwise hold.
No automatic retry after an ambiguous send. Preference-off/expiry suppress work.
Opaque deep-link locator contains no identity/prose/auth/nonce; resolve requires
normal authentication+ownership, known same-origin Mimi route, no GET/click write.
Click restores canonical conversation/run/current state; no confirm or new model.
Physical iPhone/OS delivery is NOT_RUN until separately granted/observed.

## A4 UI and dependencies

Compact approved sidechat, small model+effort/progress cell, response-bound icon
feedback, collapsed source/run detail, concise paged collection table50/100/200.
A drawer remains default; inspector on demand. Full Mimi WORKSPACE has left rail,
broad central MAIN CONVERSATION, right rail. BOTH rails independently collapse
AND resize (pointer and keyboard); clamp widths to preserve central dominance,
use reachable overlays at narrow widths rather than squeezed center/overflow.
Remember only local presentation widths; no private content in local storage.
Composer/latest messages and focus remain reachable, no hover-only actions.
Use current shadcn/tokens/Nunito/light/12px minimum, UI brief touch/font rules.

Original Q-P0 NOT_CLOSED. Same T1 may amend only owned prototype sources after
terminal reviewers, freeze new hashes and preserve dirty app WIP. Retest affected
PQA08/10/13/14/15 plus left/right resize PQA16/17 and justified CSS regressions with
Luna/xhigh execution + Gemini/high artifact challenge. Q-P0 pass2/3 retains initial
lineage. No A4 adoption before prototype closure and A3 backend-ready. A2 core may
proceed after A1 publication and fresh baseline/provenance verification.

## Acceptance and fallback

Immutable A2 target requires independent Q-A0 Luna/max and G-A0 Gemini3.8Flash/high,
then T1 consolidated technical disposition. A4 freeze requires real Chrome MCP
Luna/xhigh Q-A1 with capabilities/data/oracles bound; mocks prove lifecycle only.
Initial+MAX2 grouped fix/retests per logical gate, no reset by hashes/workers/splits;
same root cause after two failed fixes STOP_REPLAN. Whole batches finish before
routine fixes. Only rare non-safety P2/P3 may defer with impact/evidence/next action;
privacy/CAS/atomicity/unknown or required assertions are never waived.
Disable new capabilities/dispatcher while keeping additive schema and receipts;
old app is read-only rollback once child tombstones/collection recovery are active.
No live downgrade. Live Neon exact DDL/backup/rollforward activation, new A merge/
deploy and device permission remain Owner-only; no local work is blocked by them.

## Bound collection preview revision

An explicit `revise_pending_preview` request remains bound to the current pending
change-set ID and digest. Its leased model loop may perform authorized STANDARD
reads and freeze a fresh selection from current-run versioned read receipts before
returning `task.collection_candidate.v1`. The included selection must equal the
collection targets exactly. These intermediate tools do not write Task data.
Only a validated typed collection terminal can supersede the old preview; text,
clarification, failure, incomplete reads or a single-create terminal retain its
operation, digest, nonce and persisted expiry. Retention does not rebase an old
preview's generation authority: existing frontier/CAS, source-version, PRIVATE,
lease, expiry and atomic confirmation gates still apply. A valid replacement gets
its own preview clock; a retained preview's existing expiry is never extended.

Collection conversation GET includes server-owned `confirmation_preflight`
(`eligible`/`blocked`, reason). It reports the current pending/expiry/feature,
STANDARD/frontier and execution-lease checks without mutating the preview or
revalidating the full source CAS. `eligible` is a read-time snapshot, not permission
to skip POST. The review disables Confirm for a blocked or absent preflight and
explains a retained stale preview; its frozen payload and persisted expiry stay
unchanged. A later race still yields authoritative POST refusal. The client only
clears a known frontier-refusal intent after a matching ID/digest/nonce terminal
server snapshot; receipt absence or a transport error remains UNKNOWN/no replay.
