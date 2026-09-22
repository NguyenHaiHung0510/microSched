# B10 — T1 synthesis and Owner workshop packet

Status: **D1–D4 OWNER-APPROVED — D5–D7 READY FOR OWNER — EVAL NOT AUTHORIZED**

Date: 2026-09-22. Evidence base: B00–B09, independent critique B11, and
tool/bulk/loop research B12–B14.
Current code snapshot: `a4c7e8152bc83a07451eedbf8c1ec8f9de0b3ddf`.

This packet does not select a final prompt, route, model, threshold or eval budget.
It separates facts from proposals so T1 and Owner can close product behavior before
implementation.

## 1. What the research establishes

### Current implementation facts

- Current P1 is a narrow Task walking skeleton: an inline Vietnamese policy, up to
  ten STANDARD Tasks, at most 24 history messages/65,536 stored bytes, one
  `task.create.v1` schema, and one model turn/one tool call.
- Server-side gates already own the real authority: authentication, privacy,
  source versions, reserved ID, preview digest/nonce/expiry, idempotency, CAS,
  transaction and receipt. Model output is never write authority.
- Current code has no approved final `MIMI.md`, provider-neutral context manifest,
  token-accurate admission, iterative read loop, checkpoint/compaction or complete
  encrypted model payload evidence.

### Spec/package interpretation

- The merged spec already places stable policy, context construction and bounded
  context behavior in the P1 foundation. It does not defer a usable system policy
  to documents, memory or Orbit.
- Package 09 delivered a smaller engineering skeleton and explicitly recorded
  live usefulness and product acceptance as not achieved. Therefore the missing
  prompt/context design is a P1 correction/readiness gap, not a future P4/P5
  feature.
- The next implementation package must close this correction before claiming live
  P1 dogfood readiness or opening P2. Its final name/scope follows this workshop.

### Stable engineering conclusions

1. microSched owns the canonical transcript/run ledger; provider-side state is an
   optional optimization, not truth.
2. The request should be assembled from typed/versioned layers with a manifest:
   policy, run authority, tools, dynamic domain sources, conversation/checkpoint,
   pending preview, current user turn and output contract.
3. System/developer text helps the model choose behavior. Tool schemas describe
   callable shapes. Deterministic server code enforces permission, privacy,
   freshness, confirmation and mutation.
4. Draft and preview are distinct. A draft is an ordinary reply that presents
   Mimi's strategic understanding, options and proposed direction for Owner
   approval, analogous to T1 presenting a plan. It is not a weaker preview and has
   no executable identity/digest. After that direction is approved, Mimi may build
   an implementation-detailed frozen preview. “Do it now” can skip draft, never
   Owner confirmation of a preview.
5. Tool/domain content is data, not instruction. Every included item needs source,
   version/range, sensitivity and availability; prompt-injection resistance cannot
   depend on prose alone.
6. Token, cache, route and cost fields must say `REPORTED`, `ESTIMATED` or
   `UNAVAILABLE`. Missing data is not zero. ZDR, `store`, provider state, prompt
   cache and response cache are separate controls.

## 2. What the research does not establish

The following raw-report values are not accepted facts or defaults: provider/model
capability inferred from display names; 450–1,400 ms latency; near-100% schema
success; three read calls/eight seconds; two-versus-three entity boundaries;
32k context examples; 65/80% compaction thresholds; 93% cache hit; mobile-use
percentages; universal effort enums; N=3/N=5 repetitions; 25 judge samples;
Kappa 0.85; fixed call/USD/token budgets; or raw-evidence retention periods.

They may become measured options in a later approval packet. B11 is the controlling
critique for these dispositions.

## 3. Decision D1 — runtime reasoning shape

### A. One terminal call with fixed server prefetch

The server predicts all required data, makes one model call and receives text,
clarification or one proposal.

- Best for small known Task actions: cheap, reproducible and easy to debug.
- Weak for “inspect my calendar and 20 Tasks, then propose a workable exam plan”:
  it either overfetches or misses a needed source and cannot recover by reading.

### B. Mandatory server envelope + bounded iterative reads — T1 recommendation

The server always supplies identity/safety/current versions and a scoped tool
registry. The model may call authorized C0 read tools repeatedly within a lease,
then finish with text, clarification, draft or preview.

- Matches Owner's desired flexible workflow and avoids stuffing all microSched data
  into every request.
- Costs more round trips and expands injection/race surface; each read and the final
  preview require provenance, budgets and revalidation.

### C. Provider-native state/agent loop as truth

Let the provider own continuation/context and loop state.

- Potentially simple and cache-friendly.
- Rejected as canonical architecture candidate: retention, replay, truncation and
  tool semantics differ; recovery/provider switching become unsafe. It may only be
  an optional optimization behind B.

**OWNER-APPROVED 2026-09-22:** B is the design direction; A remains the fast path
and controlled baseline for narrow requests.

## 4. Decision D2 — draft, clarification and preview policy

### Immediate-preview policy

All write-shaped requests attempt preview immediately. Lowest friction, but bad for
broad planning and likely to produce a large wrong change set.

### Always-draft policy

Every write gets a draft first. Easy to explain and safest conversationally, but
annoying for “create Task X tomorrow at 21:00”.

### Adaptive policy — T1 recommendation

- **Direct answer:** ordinary chat or read-only question; no preview.
- **Clarification:** a required fact/scope is missing and reading cannot resolve it.
- **Draft first:** explicit “draft/plan/options”; broad or multi-domain work;
  multiple plausible strategies; incomplete/contradictory coverage; or a change
  set whose consequences are not easy to review as one bounded unit. The draft is
  simply a well-structured reply containing the strategic proposal and questions;
  it does not need a special executable artifact type.
- **Direct preview:** Owner explicitly asks to perform a narrow, fully specified,
  authorized action and required reads reveal no unresolved conflict.
- **Draft approved → preview:** approval of the strategic direction authorizes
  Mimi to prepare the detailed implementation preview; it does not confirm or
  execute the resulting mutations.
- **Execute:** only after Owner confirms the frozen preview.

This is a semantic policy, not a fixed “2 records good, 3 records bad” rule. A later
eval must test classification errors and review burden before numeric caps exist.

**OWNER-APPROVED 2026-09-22:** use this qualitative matrix for the first prompt
candidate; refine examples before implementation and do not invent a numeric
entity threshold.

## 5. Decision D3 — canonical context and provider state

### Stateless canonical replay

Reassemble all active context from microSched each turn; fail closed on overflow.
Strongest reproducibility/privacy, potentially more input tokens.

### Canonical replay + optional compatible provider state — T1 recommendation

microSched remains truth; route cards may enable provider continuation or prompt
cache only when storage/ZDR/replay behavior is compatible. A state ID is a hint and
must have a stateless rehydrate path.

**OWNER-APPROVED 2026-09-22:** microSched canonical replay plus optional compatible
provider state/cache and a stateless rehydrate path. Cache eligibility, especially
for PRIVATE, is decided separately in D5; D3 is not a blanket cache prohibition.

## 6. Decision D4 — context and compaction UX

T1 recommends progressive disclosure, not an IDE dashboard in every chat:

- composer/header shows requested/effective model and effort only when receipt-
  backed, plus a compact context status (`reported` or `estimated`);
- an inspector shows included source groups, omissions/partial/stale status,
  context frontier/checkpoints, pending preview, route/privacy/cache state and
  token/cost provenance; it never exposes secrets or hidden chain-of-thought;
- manual compact is available at a safe/quiescent boundary;
- automatic compaction may exist only with a visible immutable checkpoint,
  source/range provenance, pending-intent preservation and recovery receipt;
- provider-native silent truncation is not an acceptable Mimi UX.

All thresholds and exact controls remain route/measured. Model/effort options come
from the active route-card capability matrix, not a universal enum.

**OWNER-APPROVED 2026-09-22:** use this progressive-disclosure shape; expose
receipt-backed model/effort selection in the composer and keep advanced provider,
cache and privacy detail in inspector/settings.

## 7. Decision D5 — routing, cache and measurement (revised proposal)

### 7.1 Cache is layered, not globally on/off

1. **Canonical application state:** microSched always retains the authoritative
   transcript/run/context ledger under its own lifecycle. This is not a provider
   cache and cannot be replaced by one.
2. **Provider prompt/context cache — recommend eligible by default:** allow implicit
   or explicit prefix caching when the exact route's privacy/retention contract is
   compatible. Keep stable policy/tool prefixes byte-stable where practical and
   record cache reads/writes, TTL/type and actual provider. PRIVATE may use a
   documented ZDR-compatible in-memory prompt cache; explicit persistent cache
   objects require separate approval.
3. **Provider conversation state — optional:** STANDARD may use it when `store`,
   retention, deletion and recovery are known, but canonical replay remains
   available. PRIVATE persistent conversation state starts disabled unless a route
   card proves it satisfies the selected privacy promise.
4. **Router response cache — selective, not banned:** it can save an identical
   successful response and is valuable for idempotent retry/recovery or truly
   immutable read-only requests. Initially keep it disabled for independent
   semantic eval repetitions and mutation/preview-producing turns, because a
   verbatim cached tool proposal can mask model variance or replay stale authority.
   Enable other classes only when the cache key is bound to the complete request,
   context/source versions and route policy, with TTL/clear behavior and a visible
   cache-hit receipt. Account-level ZDR incompatibility remains a hard route fact.

This preserves cache economics without treating cache as authority. Cache hit rate
alone does not prove lower total cost because output/reasoning, cache-write/storage,
retry and fallback costs can dominate.

### 7.2 Eval must include two different evidence lanes

**Lane P — production-faithful acceptance (primary):** run the exact proposed daily
STANDARD topology: same model selection, adaptive provider allowlist/order, sticky
session, prompt/response-cache eligibility, fallback policy, parameters and context
builder. Record the actual provider/model, cache kind/hit, fallback, latency,
tokens/cost and terminal result for every call. This lane decides whether daily
Mimi is acceptable; provider mixing is part of the product behavior, not noise to
hide.

**Lane C — controlled diagnostic/comparison (supporting):** pin exact model,
provider, effort and parameters; prohibit silent fallback; disable response cache;
run declared cold/warm prompt-cache cohorts when the provider supports them. This
lane isolates whether a failure comes from prompt/model/provider/cache/routing and
supports fair MIDEX comparisons. It must not substitute for Lane P.

Production topology changes invalidate or version Lane P results. Provider-pin or
cache-policy changes version Lane C cohorts. A finalist needs both: controlled
capability evidence and representative daily-route evidence.

### 7.3 Remaining Owner decisions

- **D5-A:** daily STANDARD route: one pinned provider, or an adaptive allowlist with
  sticky session and bounded fallback? T1 recommends adaptive allowlist only after
  each endpoint independently passes privacy, tool/parameter and uptime gates.
- **D5-B:** approve the layered cache defaults above: prompt cache eligible;
  provider state optional; response cache selective and initially off for semantic
  repetitions plus preview/mutation turns?
- **D5-C:** PRIVATE promise: ordinary provider ZDR/no training, or stricter no
  persistent provider conversation/explicit cache state? Both can still permit a
  documented in-memory ZDR-compatible prompt cache.

## 8. Decision D6 — tool granularity and bulk operations

### 8.1 Current gap

Current provider-visible Mimi exposes only `task.create.v1`. The lease name
`task.read.standard.v1` is server prefetch of at most ten Tasks, not a callable
model tool. Current HTTP API can list a page of Tasks, but rename/update remains one
`PATCH` per Task. Therefore current Mimi cannot truthfully inspect or reformat 100
Tasks in one run; a row-level tool design would multiply latency, context and race
surface.

### 8.2 T1 recommendation — query, snapshot, transform, preview

Use a small set of workflow-shaped tools rather than mirroring every CRUD endpoint:

1. **Bounded query/list:** typed filter/range/sort/projection/detail + opaque cursor;
   return high-signal rows, aggregates, source versions, completeness/omission and
   `data_as_of`. No raw SQL, arbitrary predicate or model-controlled privacy flag.
2. **Selection snapshot:** when work targets many rows, server freezes an opaque,
   scoped, expiring selection handle with exact visible IDs/source versions,
   query/projection hash, frontier, sensitivity and completeness. The handle is
   provenance, not write authority.
3. **Typed transform or bounded mapping:** for deterministic changes such as
   prefix/suffix/whitespace/template normalization, model proposes an allowlisted
   declarative rule. For heterogeneous semantic renames, it can propose per-ID
   mappings in bounded pages/checkpoints. No executable Python/JS/SQL/regex.
4. **Server materialization:** server evaluates the proposal against the snapshot,
   validates every result and builds exact before→after operations with expected
   versions, conflicts, no-ops, omissions, groups, inverse metadata and digests.
5. **Frozen preview:** Owner reviews the materialized result; confirmation binds the
   exact top-level/group digest. Model text or selection handle cannot execute it.

This reduces model/tool round trips without pretending the underlying 100 row
checks disappeared. Batch transport, batch authority and batch atomicity remain
separate concepts.

### 8.3 Execution policy recommendation

- Prefer **whole-batch atomic** execution when the set fits measured transaction,
  preview and review budgets: any stale/invalid member produces zero writes.
- For larger/independent sets, allow only **explicit deterministic groups**, each
  with its own digest, confirmation scope and atomic receipt.
- Keep silent per-row partial commit disabled in the first bulk design. If later
  enabled, it needs explicit Owner choice and per-row durable outcomes.
- Never silently downgrade whole-batch to grouped/partial after timeout. Unknown
  outcome must reconcile by change-set/group/idempotency identity before retry.

### 8.4 Remaining D6 decisions

- **D6-A:** approve query → selection snapshot → typed transform/mapping → server-
  materialized frozen preview as the default bulk architecture?
- **D6-B:** approve whole-batch atomic when measured-safe, deterministic group
  atomic otherwise, and no silent per-row partial execution initially?
- **D6-C:** first allowlisted transforms: T1 recommends title prefix/suffix,
  whitespace/case normalization and approved templates; schedule/status or private
  bulk changes remain separate capability packages.

## 9. Decision D7 — loop engine, preview and two surfaces

### 9.1 T1 recommendation — durable bounded loop in the monolith

Implement a DB-backed run state machine and small server worker inside the existing
FastAPI/Postgres modular monolith. Do not add Temporal, Celery, Redis or a provider-
native agent framework as a new source of authority without measured need.

The state machine durably separates:

```text
accept/preflight → model turn → tool intent/gate/run/result → model turn
→ owner input/draft approval → preview ready → confirm/execute/reconcile → terminal
```

Every loop has server-issued limits for model turns, tool calls/pages/bytes,
deadline, cost, concurrency and no-progress detection. Fixed-prefetch/one-call stays
the fast path. Provider continuation/cache is attachable and discardable; restart
rehydrates from canonical microSched state.

Model responsibility: interpret intent, choose an allowed read tool, decide whether
more evidence is useful, summarize uncertainty and propose draft/typed candidate.
Server responsibility: auth/privacy/capabilities, budgets, schema, source freshness,
CAS/idempotency, preview/confirmation, commit, cancellation fences, event order and
unknown-result reconciliation.

### 9.2 Bulk preview presentation — one state, two projections

The server stores one frozen preview ID/digest and paged row/group projection.
Side-chat and workspace never build separate selections or confirmation state.

**Side-chat (quick):** current phase, elapsed time, compact changed/no-op/conflict/
omitted counts, blocking attention, expiry and one next action. A large preview gets
an `Open workspace to review` CTA; it may show a small labelled sample but never
imply the sample is the whole set. Small previews may be confirmed there only when
every material before→after fits without hidden rows/conflicts.

**Mimi workspace (inspection):** frozen summary and completeness; grouping,
filter/search/sort over the frozen projection; paged before→after rows; exceptions,
source versions and per-row expansion; confirm-all/confirm-group scope; after-run
receipt/reconcile state. Advanced hashes, tool events, route/cache/token/cost and
policy versions stay collapsed on demand. Full transparency means visible data,
actions, omissions and authority—not raw hidden chain-of-thought.

### 9.3 Recovery and progress

Both surfaces subscribe to the same `run_id` and monotonic durable event sequence.
Disconnect closes only observation; cancel is a request until durable evidence says
the work stopped. Crash after commit recovers from receipt; unknown provider result
reconciles before retry; interrupted compaction preserves the previous active
checkpoint. UI shows truthful phases and elapsed time, never invented percentages.

### 9.4 Remaining D7 decisions

- **D7-A:** approve the DB-backed bounded run state machine in the current monolith,
  with no external workflow engine for this package?
- **D7-B:** approve the side-chat compact/workspace detailed projection contract;
  bulk previews require workspace review whenever material rows/conflicts are
  collapsed in side-chat?
- **D7-C:** approve application events/progress without raw hidden reasoning, with
  detailed context/tool/receipt information progressively disclosed in workspace?

## 10. Decision D8 — first eval approval packet, not execution

After D1–D7, T1 will submit a separate versioned approval packet containing:

- exact Git SHA; policy/context-builder/tool-schema/fixture/harness hashes;
- exact model + effort + endpoint/provider route card and parameters;
- synthetic tuning/held-out cases for ordinary chat, read-only, clarification,
  bounded reads, draft/direct-preview classification, revision/CAS, injection and
  compaction/recovery only when implemented;
- deterministic hard gates versus semantic rubric and Owner calibration cases;
- repetitions/order/cache cohorts justified by a pilot, not guessed now;
- token envelope including cached tokens, estimated cost range, wall-time,
  concurrency, checkpoint/resume/cancel and stop conditions;
- normalized raw receipts with `REPORTED/ESTIMATED/UNAVAILABLE`, sanitizer
  RED/GREEN proof and retention proposal;
- explicit actor/evidence/approval checklist before `MIMI_DEMO_1` is accessed.

The first approved run should be a small synthetic route-capability/behavior pilot.
Heavy MIDEX/model comparison, judge calibration and long-context stress are later
lanes, not prerequisites forced into the first experiment.

## 11. Decisions deliberately deferred

- exact system-prompt wording and final policy hash;
- exact context/reserve/tool/latency thresholds;
- first exact model/provider/effort and fallback allowlist;
- web-search/outbound tool enablement and SSRF/data/source policy;
- provider-published reasoning display (optional UX only; no raw hidden CoT);
- evidence TTL/cap/export/destruction policy;
- eval model list, repetitions, judge, token cap and scoring formula;
- first P2 domain slice.

## 12. Workshop completion rule

B10 becomes `OWNER WORKSHOP COMPLETE` after Owner decisions on D5–D7 and any
concrete example corrections. D1–D4 and the two-surface direction are already
approved. T1 may then draft the final context/
system-policy package and the separate eval approval packet. No runtime edit,
live route, key use, dogfood, deployment or P2 work is authorized by this packet.
