# 056 — Mimi P1 STANDARD Task walking skeleton

Status: **PACKAGE READY / D2–D4 OWNER-APPROVED; D1 MODEL/WEB-SEARCH CHOICE PENDING (2026-09-15)**

> Executor/integrator: T1 GPT-5.6 Sol/high · Profile: Balanced · Owner grant: current task, 2026-09-15, “tự lập detailed next package, triển khai, kiểm chứng và giao hoàn chỉnh” · Skill: `ui-ux-pro-max` within `docs/ui-brief.md` · Browser verification: isolated Playwright/local synthetic only · No Astra delegation.

## 1. Outcome and capability state

Deliver one real, bounded P1 vertical slice:

1. Owner starts a **STANDARD** Mimi conversation.
2. Mimi reads bounded Task state with stable IDs, source versions and provenance.
3. Owner can steer the conversation, inspect a typed create-Task preview, revise it, then confirm or reject the exact frozen digest.
4. Confirm executes atomically and idempotently through the existing Task domain behavior, writes an immutable receipt/audit record, and leaves a durable reminder-refresh marker that converges after a simulated crash.
5. Reload shows the durable conversation/run/preview/receipt. Halt, cancel, definitive retryable failure and unknown provider outcome have distinct states; no blind retry or replayed mutation.
6. Owner can save bounded feedback against the exact turn/run/operation and see its unresolved state after reload/restart.

Target delivery state is `LOCAL_VERIFIED` with deterministic and exact approved live-route synthetic evidence. `ENABLED` for real personal chat is a separate gate: it requires the approved D2/D4 lifecycle controls, exact production config, CI/deploy receipts and Owner acceptance of remaining backup aging.

## 2. Authority and non-goals

Current grant includes detailed planning, implementation, proportional independent review, branch/PR work, exact-head gated merge and ordinary `develop` deployment. It does not grant:

- PRIVATE Mimi reads/writes, controlled release, private provider egress or soft-lock runtime work;
- Notes/Calendar/Tracker/Subscription tools, update/delete/restore/revert or cross-domain atomic sets;
- real-data migration/import, Neon branch create/delete/Restore/Sync, destructive production tests or automatic Alembic-on-deploy;
- R2 attachments, parsers, web search unless D1.e is approved, memory/skills/Orbit, background model jobs or automatic multi-model routing;
- paid calls before D1, unbounded benchmark spend, new infrastructure, recurring automation or branch/worktree/volume cleanup.

STANDARD source boundary remains active: the run must reject private Task rows before decrypt/return/provider dispatch. Disabling PRIVATE tools is not permission to skip sensitivity checks.

## 3. Current baseline and reused seams

- Branch/worktree: `feat/056-mimi-p1-task-walking-skeleton` at `C:/Users/os/Desktop/ai_eng_path/microsched/worktrees/056-mimi-p1-task-walking-skeleton`.
- Base: `origin/develop@2f06ddca28ea5570f5d1bad018ce574b9f782881`, the merged P0 delivery from PR #222.
- P0 reuse: `backend/app/agent/contracts.py`, deterministic provider/clock/barrier helpers, synthetic J01–J06 manifest, guarded full-app runner and evidence/feedback contract tests.
- Domain reuse: protected router/session dependency, Task DTO/Store/read gates, request transaction boundary, reminder reload seam, AES-GCM primitive, UUIDv7, SQLModel/Alembic and current React/shadcn/TanStack Query shell.
- Existing `Message`/`AuditLog` are legacy seams, not a sufficient conversation/run ledger. Migration design must preserve them and must not silently reinterpret legacy rows as completed P1 runs.
- Root checkout contains pre-existing dirty/untracked Owner files; it is not the writer. This isolated worktree is the single writer for Task 056.

## 4. Delivery decomposition

The outcome may use sequential reviewable PRs, but the task closes only when the end-to-end capability reaches its declared state. Each merge remains default-disabled until its enablement gate.

### 056A — Persistence, authority and protected API foundation

- Add an additive migration after `0013` for the smallest durable set needed by this slice: conversation, ordered message, run, event/frontier, provider call/result intent, frozen change set, execution receipt, refresh-needed marker, feedback and evidence metadata/content reference.
- Use explicit TEXT+CHECK states, UUIDv7 IDs, timestamptz, owner/conversation generations, monotonic sequence uniqueness and bounded JSON/text columns. No generic workflow engine and no future-domain tables.
- Issue execution context server-side. Client/model cannot provide owner ID, `allow_private`, capability lists, budget extensions, policy versions or session/private timestamps.
- Protected endpoints have exact request/response/error/auth/idempotency/page bounds. All Mimi mutation requests use D3 CSRF posture; no state-changing GET.
- Feature flags default off for live route and real-personal-chat enablement. Deterministic adapter remains available only in local/test environments.

### 056B — Deterministic run loop and Task adapter

- Implement bounded run states and provider-call outcome separately: accepted/building/running/waiting-confirmation/executing/completed; halt/cancel; retryable; outcome-unknown; terminal deadline/budget states.
- Bounded Task read accepts allowlisted filters/ranges/cursor/page size and returns provenance + entity version. Private rows are filtered before DTO assembly and provider dispatch.
- Provider handoff persists intent/fingerprint before dispatch and durable result before canonical materialization. Unknown outcome disables automatic retry; an Owner retry creates a distinct attempt and fences a late old result.
- Build one typed operation: `task.create.v1`, maximum five operations but P1 UI proposes one by default. IDs are preallocated. Canonical digest binds schema/tool/policy versions, ordered args, destination, expected source versions, expiry and nonce.
- Confirmation accepts only change-set ID, digest, decision and nonce. Same key/same digest returns the original receipt; same key/different digest is 409; stale source/frontier/version and expired preview fail closed.
- Execute one related set in one transaction with immutable receipt/audit and durable refresh marker. Required fault: Task commit succeeds, process stops before fast signal, recovery converges reminder state without duplicate Task.

### 056C — Context, UI, feedback and local acceptance

- P1 context is bounded raw suffix plus a structured B checkpoint. Compaction is visible, automatic at the configured hard boundary, manual-rebuild capable and never summary-of-summary at an unchanged frontier. Oversized input fails explicitly; no silent truncation.
- Minimal inbox/steer persists stable client ID, ordered sequence and expected run generation. Harmless supplement may retain preview; material change revises it and requires fresh confirmation; uncertain impact asks narrowly.
- Add a `Mimi` top-level tab without replacing normal domain UI. P1 exposes only the conversation/Overview surface; future Orbit/Memory/Skills/Settings are not fake tabs.
- Reuse warm-rose tokens, Nunito, light-only shadcn components and existing shell. Reject the skill search's teal/Quicksand/new design-system output because it conflicts with `ui-brief`; retain only applicable guidance on explicit labels, visible state, feedback and cancellable transitions.
- Mobile 390×844 and desktop 1280×800: no horizontal overflow; input text at least 16px; primary touch target at least 44px; other targets at least 24px with spacing; keyboard/focus/ARIA live regions; no hover-only information; reduced motion respected.
- UI states: empty, loading, load error, sending, send error with retained draft, offline, running, waiting confirmation, stale/expired, retryable, outcome unknown, halted, cancelled, completed, feedback saving/saved/failed, long content and 30+ events/messages.
- Preview shows exact operation, destination STANDARD, Task fields, provenance/source version, expiry/digest summary and why confirmation is required. Success is brief and links to Task/receipt; error is outside any closing dialog.
- Feedback uses stable client ID and server ACK. Unknown/failed save stays visibly unsaved and retryable; no plaintext persistent browser queue.

### 056D — Exact live route, release and evidence closure

- Implement only the D1-approved OpenRouter-compatible adapter and exact model routes. Application-defined function tools and independently validated structured outputs are the core; no hosted file/computer/shell tools. D1.e controls the optional web-search lane. API keys are supplied by the Owner through the existing secret/config mechanism, never chat/log/fixture.
- Run a small synthetic STANDARD route card: exact model/effort/endpoint, tool/structured-output/stream/usage behavior, latency and actual cost. Driver/provider/subject errors remain distinct.
- Run focused RED→GREEN guards, full backend non-PG, disposable PG migration/round-trip and Mimi integration, frontend lint/unit/build, repository hooks, local full-app Playwright, and required CI.
- Obtain risk-based independent delta review on a frozen application candidate before final publication/merge. Reconcile findings with evidence; no finding quota.
- Before merge: fresh PR OPEN/non-draft/head/base/diff/mergeability/checks, then CAS merge with exact head. Ordinary deploy proof requires exact `/api/readyz.commit` and `db=up`. No automatic migration or production data mutation.
- If real-chat enablement remains gated, deploy code/config default-off and report `LOCAL_VERIFIED`, not `ENABLED`.

## 5. Owner decisions

### D1 — Model/route selection and benchmark — **RESEARCH REVISED; OWNER CONFIRMATION PENDING**

The earlier five-model list validated Owner nominations plus two incumbent references; it was not a complete independent market scan and is superseded. Canonical research, formulas, current catalog receipts and the resumable benchmark design now live in [Task 056 model-selection research](task-056/model-selection-research.md).

#### D1.a — Centralized OpenRouter route contract

OpenRouter is the production abstraction. Keep retention, canonical state, context overflow, caching, provider selection and receipts in one route contract:

- separate STANDARD and PRIVATE API keys/guardrails; prompt/completion logging and data-sharing remain off;
- PRIVATE enforces account/key guardrail ZDR plus request `provider.zdr=true`; every request uses `data_collection="deny"`;
- microSched remains the canonical conversation/run store and never requires provider response retrieval to recover;
- microSched assembles and preflights context; unexpected router/provider context compression or message dropping fails the route card;
- use exact model/provider, `allow_fallbacks=false`, `require_parameters=true`, request `max_price`, bounded output/tool calls and router metadata;
- provider prompt caching is allowed and measured under the approved retention posture; OpenRouter full-response caching is disabled for Mimi action-bearing traffic because replayed tool outputs are unsafe and account-level ZDR disables that cache anyway.

ZDR centralizes the no-retention route policy, but it does **not** prevent truncation. Overflow safety still requires application preflight plus route-specific fail-not-truncate behavior. For OpenAI Responses that means `store=false` and `truncation=disabled`; other routes must prove equivalent behavior.

9router is an Owner-guaranteed local benchmark abstraction. T1 does not inspect or judge its upstream source; only observable technical behavior matters: exact requested model/config, token accounting, quota/rate-limit errors, interruption and resume. It is not a production dependency.

#### D1.b — Candidate governance and independent discovery

Use three equal nomination channels: Owner-observed candidates, T1 independent catalog scan, and incumbent/reference models. A nomination is not a finalist. T1 applies static eligibility and cheap capability smoke; the Owner approves the token envelope for heavy Mimi-specific bench; only heavy-bench survivors can become daily default or explicit escalation routes.

The 2026-09-15 independent scan queried the public OpenRouter catalog with `zdr=true`, then required text output, context ≥128K, `tools`, `tool_choice`, and `structured_outputs` or `response_format`. It observed 321 ZDR-listed models, 230 statically eligible models, and 3 free eligible variants. New candidates found independently include DeepSeek V4 Flash 0731, InclusionAI Ling 3.0 Flash VL, Xiaomi MiMo V2.5, Qwen3.8 27B and GLM 5.3 non-Flash.

Recommended funnel:

1. free capability smoke: Gemma 4 31B IT free and Nemotron 3 Super 120B free;
2. ultra-cheap screen: GLM 5.3 Flash, DeepSeek V4 Flash 0731, DeepSeek V4.1 Flash, Ling 3.0 Flash VL and MiMo V2.5;
3. quality references: Qwen3.8 27B, GLM 5.3, GPT-5.6 Luna and Gemini 3.8 Flash; Muse Spark 1.3 remains STANDARD-only while absent from the ZDR catalog;
4. batch variants do not compete for the interactive route because their latency/execution semantics differ.

Generic benchmark indices and popularity only form the discovery queue. Exact Task read/preview/confirm correctness, tool/schema validity, duplicate-mutation protection, recovery, latency, total token use and cost per completed Task select the winner.

#### D1.c — Hybrid forecast and measurement

Use an interval, not one price. For each eligible endpoint refresh `P_low` and enforce `P_cap` with OpenRouter `max_price`. Compute three cache scenarios: cold `H=0%`, provisional warm `H=70%`, and ideal `H=93%`. The 93% scenario is grounded by the Owner's sanitized OpenRouter snapshot (95.2% cache hit) but is not called a Mimi guarantee.

Separate uncached input, cached input, cache writes and output/reasoning:

`cost = U×P_input + C×P_cache_read + W×P_cache_write + O×P_output + tool charges`

The Owner snapshot observed 340M tokens / 3K requests / USD 9.46 / 95.2% cache hit / about USD 0.03 blended per 1M. This is a useful prior for an agentic harness, not a Mimi forecast: workload/model mix, prefix stability, cache TTL and response length differ.

Use hybrid control:

- estimate before execution for route and token-envelope planning;
- measure exact terminal usage/cost/cache/reasoning/provider metadata per generation;
- report cold/warm P50/P90/P95 by scenario family, model/config hash and time window;
- refresh catalog prices/eligible endpoints at bench start and production review; invalidate comparisons when fixture, prompt, tools, model/provider, reasoning effort or routing changes;
- use rolling measurements to recalibrate the interval, never replace the cold-cache safety ceiling with one early average.

#### D1.d — Token-governed, resumable benchmark

Money is observed, not the primary local-bench stop control. The proposed initial envelope is:

| Stage | Purpose | Provisional per-model ceiling |
|---|---|---:|
| S1 | 12 hard capability cases × 2 repetitions | 0.5M total provider tokens |
| S2 | 60 representative cases × 2 repetitions | 5M total provider tokens |
| S3 | 240 stratified cases × 3 repetitions plus long-horizon/recovery slice | 35M total provider tokens |

Count cached input at its full token count. Also track separate uncached input, cached input, cache-write, visible output, reasoning output, calls and retries. Run the same cases/settings across models; do not grant a weaker model more cases merely because it is cheaper. Expand S3 only in equal 25M-token tranches when paired results remain inconclusive or tail/recovery coverage is insufficient, with Owner approval.

Every `(bench_id, case_id, repetition, model_config_hash)` is a durable checkpoint. Reserve tokens before dispatch; persist dispatch intent, generation/route ID, terminal usage and result hash; resume by skipping completed units. Rate limit/network errors pause or retry the atomic unit within its retry allowance. Unknown outcomes remain counted/resolved separately; a restart never reruns the whole bench. Record wall time and use a hard wall-clock deadline in addition to token ceilings.

#### D1.e — Optional web-search server tool

Keep the Task walking skeleton independent of search, then add a STANDARD-only, explicit Owner-enabled `Research mode` after the core route is GREEN: one pinned engine, at most 2 searches/run, 5 results/search and 10 total results, citations required, untrusted-result boundary and exact usage receipt. PRIVATE web search remains disabled until the search processor's own retention path is proved.

Owner confirmations still needed:

- approve this discovery → smoke → heavy-bench governance and the S1/S2/S3 token envelopes;
- approve OpenRouter as production abstraction with separate STANDARD/PRIVATE keys and the centralized route contract;
- approve or defer bounded STANDARD-only Research mode;
- choose a wall-clock ceiling for S3 (recommended 24 hours/model, resumable).

### D2 — Full diagnostic evidence lifecycle — **OWNER APPROVED 2026-09-15**

The choice balances a reproducible debugging window against retaining sensitive conversation/tool payloads:

| Case | Trade-off | Recommendation |
|---|---|---|
| Synthetic/local evidence only | Lowest privacy and storage risk, but weak production diagnosis and slower dogfooding. | Acceptable while real chat remains default-off; insufficient by itself for later production enablement. |
| 7-day bounded full evidence | Covers the expected short review/debug cycle while bounding payload retention. | **Recommended P1:** 1 MiB per complete bundle (P0 ceiling), 4 MiB/run, 16 MiB/conversation, 64 MiB global; warn at 80% and 48 hours before expiry. |
| 14+ days or larger global cap | More time for intermittent defects, but meaningfully raises privacy, deletion and storage burden before value is measured. | Defer; expand only from observed missed-debug incidents. |

At cap, stop additional capture and mark `INCOMPLETE/CAP_REACHED`; never silent truncate/evict. Explicit Owner extension adds 7 days but cannot outlive conversation retention/deletion.

P1 export is a versioned JSON bundle plus SHA-256 manifest, explicitly downloaded by Owner; production export containing real content remains disabled until its encryption/destination flow is separately verified. Operational metadata trace remains the already-proposed 30 days and does not inherit this payload TTL.

### D3 — CSRF posture for Mimi writes — **OWNER APPROVED 2026-09-15**

| Case | Trade-off | Recommendation |
|---|---|---|
| SameSite cookie only | Smallest change, but does not meet the approved auth brief and leaves browser edge cases without an explicit application check. | Reject. |
| Mimi-scoped provenance/header checks | Keeps session cookie `HttpOnly + Secure + SameSite=Lax`; additionally requires JSON, exact same-origin `Origin`, non-cross-site Fetch Metadata and a Mimi header for every unsafe `/api/mimi/*` request. | **Recommended P1:** explicit protection with bounded regression surface. Reject before body/model processing. |
| Session-bound synchronizer token for every app write | Strong and uniform across domains, but expands Task 056 into every protected client/test and raises unrelated regression risk. | Good follow-up platform hardening, not the P1 critical path. |

All mutations remain POST/PUT/PATCH/DELETE. Confirmation nonce/digest/idempotency are separate integrity guards, not CSRF substitutes.

### D4 — Key/deletion/production enablement truth — **OWNER APPROVED 2026-09-15**

| Case | Trade-off | Recommendation |
|---|---|---|
| One shared content key | Simpler schema/operations, but weak per-conversation isolation and deletion semantics; deleting a row cannot make one conversation's ciphertext uniquely inaccessible. | Reject for persisted Mimi content. |
| Per-conversation DEK, real chat default-off | Each conversation has a random DEK wrapped by the existing application master key; content-bearing feedback/evidence uses that DEK. Live deletion removes live rows and its wrapped DEK. | **Recommended P1:** implement and fully test synthetic/local/live-route behavior, then deploy capability default-off. |
| Per-conversation DEK and enable real chat immediately | Fastest dogfooding, but backup retention may still preserve recoverable historical ciphertext/key material; an instant crypto-shred claim would be false. | Reject until retention truth and restore/deletion rehearsal are observed. |

UI/receipt must state that old backups may retain a recoverable historical copy until the actual retention window expires. Do not claim instant backup purge or crypto-shred. Enable real personal chat only after a disposable deletion/restore rehearsal and Owner confirmation of the actual Neon/manual-backup aging window. Synthetic local/CI and synthetic live-route acceptance may proceed before that confirmation.

## 6. Acceptance matrix

| Case | Expected proof |
|---|---|
| A-TOOL-01 | Bounded STANDARD Task read returns stable IDs/provenance; private source never enters assembled DTO/provider evidence. |
| A-WRITE-01 | Preview v1 → revise v2; only v2 digest/nonce can execute. Reject/expiry/stale/different-content idempotency return exact errors. |
| A-WRITE-02/03 | Related create transaction is all-or-nothing; receipt/audit/refresh marker share commit; crash-before-signal recovery converges without duplicate. |
| A-RUN-01/02 | Halt/cancel/steer/frontier/retry/unknown/result fence survive restart and do not replay committed mutation. |
| A-CTX-01..06 scoped | Hard input boundary, visible B checkpoint, raw suffix, no unchanged-frontier recompact, no silent truncation and truthful usage categories. |
| A-OBS-01 | Full application-visible synthetic evidence with completeness manifest; secrets/hidden reasoning rejected; ACK feedback survives reload/restart. |
| A-GUARD-01 | Each new safety guard is deliberately violated for intended RED, restored, then GREEN. |
| A-UX-01 scoped | Screen×state matrix at 390×844 and 1280×800, stable test IDs, keyboard/focus/touch/long-content checks; physical iPhone remains separate. |
| A-MODEL-01 scoped | Exact approved live route completes representative synthetic Task read/create journey within hard budget; no portability claim from one route. |
| A-DEPLOY-01 | Required CI on exact head; if merged, ordinary deployment and exact readyz SHA/db proof. Capability flag state reported separately. |

## 7. Stop and re-plan conditions

Stop only the affected live-route/web-search work while D1 remains undecided. Stop and ask Owner if Docker is unavailable for required PG/full-app gates, a migration requires real Neon action, live route needs a secret/charge outside approved caps, the app cannot meet 512 MB bounds, or a finding requires changing PRIVATE/product/security authority. After roughly two unproductive attempts at the same blocker, preserve logs and re-plan.

## 8. Evidence and closeout paths

- Canonical task/package: this file.
- Raw concise command receipts: `agent-tasks/task-056/terminal-receipt.md`.
- UI screenshots/manifests: ignored local task evidence first; only sanitized reviewed artifacts may be published.
- Closeout must separate local/PG/browser/live-route/CI/deploy/device/production and exact enabled state. Physical iPhone/Safari, real OAuth and real-personal-data acceptance are never inferred from Chromium/synthetic gates.
