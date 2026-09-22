# B01 — Spec and package authority map

Status: **RESEARCH ONLY — no runtime change, API call, provider call, or eval**

Evidence date: 2026-09-22. Current source is `origin/develop=a4c7e81` in the
research worktree. Normative sources are under
`C:\Users\os\Desktop\cur_docs\PTHTTM\btl\`.

Labels: **FACT** = observed; **INFERENCE** = derived conclusion; **PROPOSAL** =
recommendation, not Owner decision; **OPEN** = unresolved/not evidenced.

## 1. Authority method

- **FACT** — consolidated spec 04 is current product/architecture authority;
  01/02 retain history/detail only where 04 incorporates them, and unresolved
  conflicts return to Owner (`04-spec-hop-nhat-mimi.md:1-16`).
- **FACT** — master plan 07 is Owner-approved dependency/packaging guidance and
  P0 is authorized, but planning does not grant coding, paid calls, migration or
  production enablement (`07-master-delivery-plan-mimi.md:1-19`).
- **FACT** — package 08 scopes P0 to local synthetic sandbox/contracts and no
  real DB/paid/provider/P1 auto-start; package 09 is the P1 engineering receipt
  and marks real chat disabled/live usefulness NOT_RUN
  (`08-package-p0-sandbox-and-contracts.md:1-21`; `09-package-p1-standard-task-walking-skeleton.md:1-30`).
- **FACT** — 05 is a dated 2026-09-10 snapshot, not current code authority;
  current source is rechecked separately here (`05-doi-chieu-implementation-mimi-2026-09-10.md:1-5,15-30`).

## 2. Normative package map

### P0 — sandbox and shared seams

- **FACT** — P0 must produce resettable full-local synthetic data, scenario IDs,
  fake clock/provider, contract map and evidence skeleton, not production Mimi or
  generic eval platform (`07-master-delivery-plan-mimi.md:63-71`; `08:6-10`).
- **FACT** — package work covers baseline/seams, sandbox entrypoint, J01–J06
  fixtures, P1 authority/API map, fake provider/barriers, feedback/evidence and
  handoff (`08:31-42`). Six pre-code seams include legacy/schema, central privacy
  coordinator, run lease, change-set adapter, durable handoff/attachments and
  reminder/cache hooks; API map must include auth/CSRF, DTO/errors, state,
  idempotency, source versions and bounds (`08:55-69`).
- **FACT** — full synthetic prompt/request/response/tool evidence must survive
  refresh/restart/reset/reseed, be separate from disposable fixtures, exclude
  secrets and truthfully mark incomplete/failed captures (`08:14-16`; `07:213-240`).
- **OPEN** — 08 receipt says P0.1–P0.6 had not run (`08:120-122`); this task did
  not execute them. OPEN-04 recovery/key/backup, L1 route/budget and L2 parser/
  resource packets are prepared, not self-closed (`08:71-79`).
- **INFERENCE** — context readiness at P0 means reproducible context/evidence
  envelope and seams, not final iterative agent behavior.

### P1 — STANDARD Task walking skeleton

- **FACT** — BTL core is bounded STANDARD Task read with stable ID/provenance and
  Task create via typed proposal → frozen preview → confirm/reject → atomic/
  idempotent execution + audit; fake + one exact live route suffice for BTL, while
  two live routes are needed for portability (`04:36-42`; `02:81-101`).
- **FACT** — 09 scopes delivered P1 to Task read/create STANDARD; no PRIVATE,
  Notes, Calendar, Tracker, Subscription, documents, memory, skills, Orbit or
  multi-model routing (`09:8-17`). Current source loads ten safe Tasks, one inline
  system prompt, bounded history and one turn/one tool lease
  (`backend/app/agent/service.py:404-446,581-607,695-799`; `contracts.py:37-59`).
- **FACT** — 09 reports local deterministic, throwaway PG, CI, default-off
  production code and focused UI at their stated layers, but production schema
  0014 is NOT_RUN, real chat DISABLED, live usefulness/BTL acceptance NOT_RUN,
  and physical device NOT_RUN (`09:19-30,116-146`).
- **FACT** — normative context still requires canonical transcript retention
  separated from active context, visible/mandatory compaction, B-first checkpoint,
  no silent truncation and bounded source-grounded retrieval (`04:27-30,250-257`).
- **INFERENCE** — P1 is a valid narrow engineering receipt, not the full context
  architecture. Current path has no context manifest/meter/frontier, tokenizer
  preflight, checkpoint/compaction, iterative reads or full encrypted prompt/
  payload evidence.

### P2 — bounded multi-domain slices

- **FACT** — P2 can deliver Tracker, Calendar+Task, Notes, Subscription, Task
  correction or analytics independently, reusing P1 executor/CAS; each operation
  still needs typed args, permission, bounded reads, receipt, inverse/unsupported
  state and domain hooks (`07:87-106`).
- **FACT** — the explicit Owner dogfood stop gate requires interaction/layout
  correction, full-app request/route diagnosis, prompt/run/route/error/latency/
  feedback evidence, and a repeated full local Owner journey before P2
  (`07:91-93`).
- **FACT** — current `task.create.v1` forces non-private Task and exposes no other
  domain operation (`backend/app/agent/openrouter.py:52-93`).
- **INFERENCE** — adding a domain tool or importing a Store cannot close P2 without
  the operation's sensitivity/permission, preview tier, expected-version/CAS,
  inverse, hooks, receipt and adversarial tests. Current P2 first slice is OPEN.

### P4 — documents and complex plans

- **FACT** — P4 depends on P1 context, L2 results and OPEN-05 artifact lifecycle;
  workflow writes require corresponding P2 operations (`07:116-124`). It needs
  upload/inventory/coverage → bounded reading → options/questions → preview/
  revise/execute, injection/coverage/parser/resource/privacy gates.
- **FACT** — current 04 replacement retains parsed material with chat, raw default
  seven days, and separates storage from active context/memory (`04:27-30,96-104`).
  OPEN-05 R2 protocol/versioning/encryption/lifecycle remains open
  (`04:295-305`).
- **INFERENCE** — P1 prompt assembly has no attachment/source-reader/coverage or
  modality envelope and cannot be treated as a P4 foundation by itself.

### P5 — memory and skills

- **FACT** — P5 depends on confirmed P1 writes/context and L3 retrieval research;
  static document skill may precede full memory (`07:126-132`). Approved STANDARD
  memory is queryable hybrid Neon memory after gates; PRIVATE memory remains
  ciphertext/bounded scan/no persistent FTS-vector and requires explicit Owner
  direction/approval plus provenance/source-delete policy (`04:31,70-80`; `01:100-111`).
- **FACT** — skills are static reviewed releases; draft/review is not installed,
  and Mimi cannot self-publish/hot-load or edit core policy (`04:31-33,190-199`).
- **INFERENCE** — current Task provenance is not a memory graph and Task context
  injection is not retrieval. No memory/skill claim follows from pgvector or the
  lease capability name.

### P6 — Orbit and jobs

- **FACT** — P6 requires durable jobs/recovery, snapshot/read-set freshness,
  revalidation, finding/chat dedup and APPLIED only from receipt; no provider Batch
  API is required (`07:134-140`; `04:201-220`).
- **FACT** — current reminder cron is not an `ai_job`/Orbit implementation;
  current source has no job/report/snapshot subsystem in the P1 request
  (`05:61-64`; source inspected at `backend/app/agent`).
- **INFERENCE** — do not put model waits into the reminder loop or treat provider
  batch existence as an app queue. P6 needs finite retry/admission/startup
  recovery and source revision revalidation. Private extraction/batch remains
  DEFER (`04:205-216`).

### P7 — routing and settings

- **FACT** — P7 adds benched routes, Auto allowlists, helper profiles and richer
  settings without a second orchestrator (`07:142-148`). Registry must record
  exact capabilities/limits/count method/privacy/pricing/probe/expiry; unverified
  routes cannot dispatch; Auto switch/cost/usage semantics are explicit
  (`04:201-211`).
- **FACT** — current settings/OpenRouter fields provide a route seam but 09 labels
  it “contract, not enabled”; no live route card/probe/usefulness/budget/Owner
  adoption receipt exists (`backend/app/core/settings.py:85-106,213-260`; `09:76-86`).
- **INFERENCE** — configured route values and no-network tests are not P7 or live
  adoption evidence. OPEN-01/02/03 remain gates (`04:295-305`).

## 3. Contradictions and reconciliation

### C1 — 07 P1 boundary versus 09/current narrow implementation

- **FACT** — 07 describes P1 with bounded context, B compaction/retry, minimal
  inbox/steering and exact live route (`07:73-85`), while 09 and current source
  deliver Task-only one-turn/one-tool P1 and explicitly omit broader capabilities
  (`09:8-17,158-168`; `service.py:709-720`).
- **INFERENCE** — reconcile as desired P1 contract versus implemented walking
  skeleton subset. Do not rewrite 09, but do not claim B compaction/inbox/steering
  or live usefulness from it.
- **PROPOSAL** — T1 should publish a correction/readiness matrix splitting
  engineering receipt from context/live-dogfood eligibility.

### C2 — “conversation thật” versus disabled/NOT_RUN

- **FACT** — 07 uses “real conversation” but expressly excludes a live personal
  chat claim; 09 marks default-off, schema NOT_RUN, real chat DISABLED and live
  usefulness NOT_RUN (`07:73-85`; `09:19-30`).
- **INFERENCE** — “real” means vertical-slice engineering behavior, not live
  Owner personal data. Live route/migration/evidence/product gates remain.

### C3 — package-complete language versus P2 stop gate

- **FACT** — 09 says implemented/merged/deployed-disabled yet records Owner product
  dogfood FAIL; 07 requires correction before P2 (`09:1-4,158-168`; `07:87-93`).
- **INFERENCE** — implementation completion is not product/P2 readiness; the failed
  full-app route must be diagnosed rather than hidden with deterministic route.

### C4 — 05 stale “no agent runtime” versus current P1

- **FACT** — 05 was an older snapshot and 07 marks it historical; current source
  has merged agent/service/OpenRouter/ledger implementation and 09 records it
  (`05:15-30`; `07:10-18`; `09:43-96`).
- **INFERENCE** — neither old “no runtime” nor current P1 receipt should be
  generalized into the full 04 architecture.

### C5 — old attachment/lock wording versus 04 replacement

- **FACT** — 04 replaces older ONE_SHOT/wipe-on-lock wording with parsed-retained,
  raw-seven-day, soft-lock bounded WIP in RAM; it says not to reuse old defaults
  (`04:18-30,82-104,250-265`).
- **INFERENCE** — future P3/P4 designs use 04's replacement, but replacement is
  normative only; it is not evidence those runtime capabilities are implemented.

### C6 — full diagnostic evidence versus P1 metadata

- **FACT** — 04/07 require encrypted full application-visible prompt/request/
  response/tool evidence, completeness state and persistence across reset/restart;
  09/current call rows retain hashes/route/usage, not an EvidenceBundle
  (`04:236-244`; `07:213-240`; `service.py:800-844,1011-1044`).
- **INFERENCE** — bounded metadata is a valid engineering receipt but not the
  approved diagnostic evidence required to debug live Owner dogfood.
- **OPEN** — exact production evidence TTL/cap/warning/export/key lifecycle.

### C7 — route fields versus P7 adoption

- **FACT** — adapter/settings already pin exact/adaptive providers, quantization,
  ZDR/data deny, price caps and tool choice, with no-network tests; 04/07 still
  require live discovery/exact probe/privacy/price/budget/Owner adoption and 09
  says route not enabled (`openrouter.py:96-179`; `04:201-211,295-305`; `09:76-86`).
- **INFERENCE** — route config is a safety seam, not a model selection or live
  route receipt.

## 4. Must close before Owner live dogfood

This is a **PROPOSAL/INFERENCE** gate list derived from 04/07/09, not a new Owner
decision. Close means dated evidence, not code presence:

1. **FACT/required:** synthetic P0 sandbox/contracts and evidence envelope with
   complete/incomplete/failed capture, secret exclusion, reset/restart survival
   (`08:31-42,55-69`; `07:213-240`).
2. **FACT/required:** diagnose full-app request stopping without preview and retain
   prompt/run/route/error/latency/feedback evidence (`07:91-93`).
3. **FACT/required:** correct side-panel chat/control-center interaction and run a
   repeated full local Owner journey; viewport screenshot/CI is not enough
   (`07:91-93`; `04:218-220`).
4. **OPEN/Owner:** exact route/model/effort/endpoint/privacy/cost cap/probe,
   migration and disable/rollback policy (`04:295-305`; `07:150-173`).
5. **OPEN/Owner:** evidence TTL/cap/warning/export/deletion/key policy and
   recovery/audit choices before real/personal data (`04:96-104,295-305`).
6. **INFERENCE/required for context claim:** request/context manifest, source
   frontier/omissions, token-count method/reserve, terminal state and evidence
   completeness; current fingerprint/byte guard is insufficient.
7. **INFERENCE/required:** exact enabled route run on full local app, measuring
   usefulness, latency, token/cost/provenance separately from deterministic safety.

### Explicit non-requirements for narrow STANDARD P1 dogfood

- **FACT** — P2's full domain set, P4 documents, P5 memory/skills, P6 Orbit jobs
  and P7 Auto/multi-route settings need not all be complete for a narrow Task
  slice; 04/07 use capability-scoped gates (`04:38-42`; `07:46-61,73-85`).
- **FACT** — PRIVATE, attachments, memory, skills, jobs and provider batch remain
  disabled/deferred until own receipts; Standard Task success cannot imply them.

## 5. Must close before opening P2

1. **FACT/required:** all Owner dogfood stop-gate items above: UI interaction,
   full-app request diagnosis, full evidence and repeated Owner journey.
2. **INFERENCE/required:** preserve P1 deterministic PASS while adding context /
   failure receipts (source versions, frontier/omission, token method/reserve,
   terminal state, completeness). Final prompt architecture remains Owner OPEN.
3. **OPEN/Owner:** exact route card/probe, budget, privacy, migration/config and
   disable/rollback receipt; default-off deploy is not this gate.
4. **FACT/required:** feedback is ACKed and survives refresh/restart/reset in the
   approved synthetic/evidence lifecycle and links to failed run/turn/route
   (`07:213-240`).
5. **OPEN:** Owner/T1 choose one bounded P2 slice and map typed reads, sensitivity,
   permission, preview tier, versions/CAS, inverse/unsupported, receipt and hooks.
6. **INFERENCE:** selected private/sensitive/bulk slice also requires relevant
   taint, route, source-deletion, lock/revoke and lifecycle receipts; otherwise it
   stays feature-off.
7. **INFERENCE:** use fake provider/clock/barriers, throwaway PG, CAS/idempotency,
   stale/current-version, reminder/cache hooks, trust/injection and RED→GREEN
   guard tests for that operation.

## 6. Dependency matrix

| Requirement | P0 | P1 | P2 | P4 | P5 | P6 | P7 |
|---|---|---|---|---|---|---|---|
| Sandbox/fixtures/clocks | Build | Reuse | Reuse | hostile docs | memory cases | job cases | route cases |
| Lease/privacy authority | Contract | STANDARD checks | per-domain | processor | private no-egress | job recheck | route matrix |
| Task read/create/CAS | Fake contract | narrow slice delivered | correction/new domains | plan writes | memory writes | report apply | reuse |
| Context/frontier/compact | Interface/gap | bounded projection/gap | iterative prerequisite | doc ranges | retrieval source | snapshot | handoff/caps |
| Full prompt evidence | Envelope | dogfood receipt needed | each slice | parser evidence | retrieval evidence | report evidence | route evidence |
| Attachments/R2 | decisions | disabled | if needed | primary | source lifecycle | job refs | registry |
| Memory/skills | contract | no tool | only if selected | static skill possible | primary | maintenance | helper route |
| Jobs/Orbit | contract | recovery substrate | not every slice | async if gated | maintenance | primary | batch adapter |
| Model/routing | L1 packet | adapter disabled | reuse approved | modality | embedding | background | primary |
| Owner UX | inspectable sandbox | dogfood failed | green before open | workflow | review | Orbit | settings |

**INFERENCE:** P0–P7 are capability labels, not eight mandatory sequential layers;
07 allows independent branches, but the explicit Owner P2 stop gate cannot be
parallelized away (`07:46-61,87-93`).

## 7. Questions for T1/Owner

1. Is the next dogfood current P1 Task-only after correction, or an approved
   iterative context manifest/loop first?
2. Which 07 P1 boundary (B compaction, inbox/steering, live route) is required
   next, and which named package defers each, without rewriting 09?
3. What exact route/model/effort/endpoint/privacy/spend/rollback is approved?
4. What full-payload evidence, encryption, TTL/cap/warning/export/deletion policy
   is approved before real/personal dogfood?
5. Which first P2 slice (Task correction, Notes, Tracker, Calendar, Subscription,
   analytics) is valuable enough for its own receipt?
6. Should first iterative reads be provider-visible typed tools or server preload?
7. Which OPEN-04/05/10 lifecycle decisions affect the selected P2 slice?
8. Must UI correction precede any live provider call, or is local full-app receipt
   sufficient for a bounded synthetic/exact smoke?

## 8. Evidence and limitations

- **FACT** — only read-only source/spec inspection was performed. No API, provider,
  browser, Docker, Neon/Fly/R2 operation, migration, test, benchmark or dogfood
  was run; existing test names/historical receipts are not new PASS evidence.
- **FACT** — 04 keeps its acceptance registry and marks those checks NOT_RUN in
  the consolidation (`04:246-293`). Current code/config can drift; re-query exact
  head, route/config, schema/migration and required gates immediately before any
  enablement decision.
- **OPEN** — this map does not choose final prompt, loop thresholds, model,
  retention/evidence numbers or first P2 slice.

## Short summary

**FACT:** 04 is normative; 07 is plan; 08 is synthetic P0; 09 proves a narrow
merged/deployed-disabled P1 Task skeleton, not live Mimi. Current source matches
that narrow P1 request, not the broad iterative context architecture.

**INFERENCE:** implementation completion is separate from product/live readiness.
The hard P2 stop is failed Owner dogfood: side-panel/control-center interaction,
full-app request diagnosis, full evidence and repeated journey. P2 then needs one
selected bounded slice with typed permission, preview, CAS, receipt, inverse/hooks
and tests.

**OPEN:** route/budget, context loop, evidence lifecycle, recovery decisions and
first P2 slice require T1 synthesis and Owner decisions. No live dogfood/P2
authorization is inferred.
