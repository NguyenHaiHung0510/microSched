# 056 — Mimi P1 STANDARD Task walking skeleton

Status: **PACKAGE READY / AWAITING OWNER DECISIONS D1–D4 (2026-09-15)**

> Executor/integrator: T1 GPT-5.6 Sol/high · Profile: Balanced · Owner grant: current task, 2026-09-15, “tự lập detailed next package, triển khai, kiểm chứng và giao hoàn chỉnh” · Skill: `ui-ux-pro-max` within `docs/ui-brief.md` · Browser verification: isolated Playwright/local synthetic only · No Astra delegation.

## 1. Outcome and capability state

Deliver one real, bounded P1 vertical slice:

1. Owner starts a **STANDARD** Mimi conversation.
2. Mimi reads bounded Task state with stable IDs, source versions and provenance.
3. Owner can steer the conversation, inspect a typed create-Task preview, revise it, then confirm or reject the exact frozen digest.
4. Confirm executes atomically and idempotently through the existing Task domain behavior, writes an immutable receipt/audit record, and leaves a durable reminder-refresh marker that converges after a simulated crash.
5. Reload shows the durable conversation/run/preview/receipt. Halt, cancel, definitive retryable failure and unknown provider outcome have distinct states; no blind retry or replayed mutation.
6. Owner can save bounded feedback against the exact turn/run/operation and see its unresolved state after reload/restart.

Target delivery state is `LOCAL_VERIFIED` with deterministic and exact approved live-route synthetic evidence. `ENABLED` for real personal chat is a separate gate: it requires D2/D4 lifecycle truth, exact production config, CI/deploy receipts and Owner acceptance of remaining backup aging.

## 2. Authority and non-goals

Current grant includes detailed planning, implementation, proportional independent review, branch/PR work, exact-head gated merge and ordinary `develop` deployment. It does not grant:

- PRIVATE Mimi reads/writes, controlled release, private provider egress or soft-lock runtime work;
- Notes/Calendar/Tracker/Subscription tools, update/delete/restore/revert or cross-domain atomic sets;
- real-data migration/import, Neon branch create/delete/Restore/Sync, destructive production tests or automatic Alembic-on-deploy;
- R2 attachments, parsers, web search, memory/skills/Orbit, background model jobs or multi-route routing;
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

- Implement only the D1-approved Responses API adapter. No hosted web/file/computer/shell tools; only application-defined function tools and structured outputs. API key is supplied by the Owner through the existing secret/config mechanism, never chat/log/fixture.
- Run a small synthetic STANDARD route card: exact model/effort/endpoint, tool/structured-output/stream/usage behavior, latency and actual cost. Driver/provider/subject errors remain distinct.
- Run focused RED→GREEN guards, full backend non-PG, disposable PG migration/round-trip and Mimi integration, frontend lint/unit/build, repository hooks, local full-app Playwright, and required CI.
- Obtain risk-based independent delta review on a frozen application candidate before final publication/merge. Reconcile findings with evidence; no finding quota.
- Before merge: fresh PR OPEN/non-draft/head/base/diff/mergeability/checks, then CAS merge with exact head. Ordinary deploy proof requires exact `/api/readyz.commit` and `db=up`. No automatic migration or production data mutation.
- If real-chat enablement remains gated, deploy code/config default-off and report `LOCAL_VERIFIED`, not `ENABLED`.

## 5. Owner decisions required now

### D1 — Initial live route and spend

This decision has two independent parts: **which model family** and **which API procurement/transport route**. Passing model quality does not make an opaque or unauthorized route acceptable, and a compatible gateway does not prove model quality.

#### D1.a — Round-zero route/capability filter

A candidate is excluded before quality scoring if any of these cannot be proved with a synthetic route card:

1. exact model/version and actual upstream provider are observable; no alias, automatic model/provider fallback or hidden retry;
2. route use is authorized for application API traffic; subscription/OAuth/CLI/MITM access is not treated as an API entitlement;
3. streaming, cancellation, error/unknown-outcome mapping, usage accounting and application-executed function calls preserve stable IDs across the full round trip;
4. the Mimi structured-output subset is accepted and then independently validated by the application;
5. no silent context truncation/compression, prompt injection, server-side tool or request/response content logging;
6. STANDARD data policy is explicit; any future PRIVATE route additionally needs separately proved zero-retention eligibility;
7. hard request/token/cost caps and a request-level route receipt are available.

For direct OpenAI Responses calls, set `store=false` and `truncation=disabled`; provider `max_tool_calls` does not replace Mimi's application-level function-call ceiling. Gateway claims of OpenAI compatibility are not accepted as proof of Responses event/tool/recovery semantics.

#### D1.b — First quality round

**Recommended finalists:** run the same deterministic synthetic Task read → preview → confirm/create journey on:

| Candidate | Why it enters round 1 | Main trade-off |
|---|---|---|
| OpenAI `gpt-5.6-luna`, `medium` | Official Responses, streaming, function calling and structured-output support; USD 0.20/M input and USD 1.20/M output makes repeated harness tuning inexpensive. | Cheapest candidate may need more harness guidance or fail difficult planning/tool discipline; quality must be measured, not inferred from price. |
| Google `gemini-3.8-flash`, `medium` | Current GA Flash candidate with 1M context, function calling and structured output; gives a genuinely different model family. Paid promotional pricing through 2026-12-31 is USD 0.75/M input and USD 3.75/M output including thinking. | Native Interactions semantics differ from Responses; a gateway translation adds a fidelity seam. Free-tier content may be used to improve Google products. |

Score both on exact action correctness, unsupported-action refusal, no duplicate mutation, tool/argument validity, schema validity, recovery after injected transient/unknown outcomes, instruction/data separation, latency and observed cost. A hard safety/correctness failure is disqualifying; do not average it away with style scores.

If neither passes, add **OpenAI `gpt-5.6-terra`, `medium`** as the escalation finalist. It has the same needed API capabilities but currently costs USD 2/M input and USD 12/M output, so it is not the economical first probe. No Astra route.

#### D1.c — Procurement/transport cases

| Case | When it is eligible | Trade-off | Recommendation |
|---|---|---|---|
| Existing 9router connections | Only when each connection is an official provider API key/BYOK route and a probe shows exact upstream/model. Disable smart fallback, combinations, RTK/Headroom/Caveman/Ponytail transforms and content logging; localhost only. | No new credit purchase and one local endpoint, but 9router's translation layer must be tested. Its subscription/OAuth/MITM modes are not eligible for Mimi application traffic without separate terms/authority proof. | Use first if the Owner confirms both OpenAI and Google connections are BYOK/API-key routes. |
| OpenRouter prepaid credits | Pin the exact model and provider; `allow_fallbacks=false`, `require_parameters=true`, `data_collection=deny`; enable router metadata and reject any unexpected pipeline transform. | Easiest apples-to-apples purchase source and route receipt, but introduces a proxy and a 5.5% credit-purchase fee (USD 0.80 minimum). | Preferred neutral benchmark source if 9router route type/fidelity is uncertain. Buy only after checking existing balance; auto top-up stays off. |
| Direct OpenAI + Google API keys | Separate paid API projects/accounts are available. | Fewest translation layers and strongest native semantics, but two billing/config surfaces and potentially new purchases. | Preferred long-term production baseline after the benchmark, not required to start P1. |

**Recommended budget:** per run 30k input tokens, 4k output+reasoning budget, 6 provider calls, existing 24-tool ceiling and hard estimated-cost ceiling **USD 0.05**. Package-wide live synthetic acceptance spend ceiling **USD 2.00**, with no Batch, automatic fallback or auto top-up. If OpenRouter has no balance, authorize at most a **USD 5 credit purchase plus its disclosed purchase fee**; this purchase cap is separate from the USD 2 inference-spend ceiling.

Owner inputs needed for D1 (never paste a key into chat):

- for each 9router OpenAI/Google connection, identify `official API key/BYOK`, `subscription/OAuth/CLI bridge`, or `OpenRouter passthrough`;
- state whether Google free-tier synthetic prompts being used to improve Google products is acceptable; otherwise all tests use paid/no-training routes;
- state whether OpenRouter already has credit, and whether the capped USD 5 top-up is approved if needed.

Research checked 2026-09-15: [OpenAI GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna), [OpenAI model comparison](https://developers.openai.com/api/docs/models/compare), [OpenAI Responses create](https://developers.openai.com/api/reference/cli/resources/responses/methods/create), [Google latest model](https://ai.google.dev/gemini-api/docs/latest-model), [Google pricing](https://ai.google.dev/gemini-api/docs/pricing), [Google function calling](https://ai.google.dev/gemini-api/docs/function-calling), [9router documentation](https://docs.9router.com/), [9router repository](https://github.com/decolua/9router), [OpenRouter provider selection](https://openrouter.ai/docs/guides/routing/provider-selection), [OpenRouter router metadata](https://openrouter.ai/docs/guides/features/router-metadata), [OpenRouter privacy/ZDR](https://openrouter.ai/docs/guides/privacy/zdr) and [OpenRouter FAQ](https://openrouter.ai/docs/faq).

### D2 — Full diagnostic evidence lifecycle

The choice balances a reproducible debugging window against retaining sensitive conversation/tool payloads:

| Case | Trade-off | Recommendation |
|---|---|---|
| Synthetic/local evidence only | Lowest privacy and storage risk, but weak production diagnosis and slower dogfooding. | Acceptable while real chat remains default-off; insufficient by itself for later production enablement. |
| 7-day bounded full evidence | Covers the expected short review/debug cycle while bounding payload retention. | **Recommended P1:** 1 MiB per complete bundle (P0 ceiling), 4 MiB/run, 16 MiB/conversation, 64 MiB global; warn at 80% and 48 hours before expiry. |
| 14+ days or larger global cap | More time for intermittent defects, but meaningfully raises privacy, deletion and storage burden before value is measured. | Defer; expand only from observed missed-debug incidents. |

At cap, stop additional capture and mark `INCOMPLETE/CAP_REACHED`; never silent truncate/evict. Explicit Owner extension adds 7 days but cannot outlive conversation retention/deletion.

P1 export is a versioned JSON bundle plus SHA-256 manifest, explicitly downloaded by Owner; production export containing real content remains disabled until its encryption/destination flow is separately verified. Operational metadata trace remains the already-proposed 30 days and does not inherit this payload TTL.

### D3 — CSRF posture for Mimi writes

| Case | Trade-off | Recommendation |
|---|---|---|
| SameSite cookie only | Smallest change, but does not meet the approved auth brief and leaves browser edge cases without an explicit application check. | Reject. |
| Mimi-scoped provenance/header checks | Keeps session cookie `HttpOnly + Secure + SameSite=Lax`; additionally requires JSON, exact same-origin `Origin`, non-cross-site Fetch Metadata and a Mimi header for every unsafe `/api/mimi/*` request. | **Recommended P1:** explicit protection with bounded regression surface. Reject before body/model processing. |
| Session-bound synchronizer token for every app write | Strong and uniform across domains, but expands Task 056 into every protected client/test and raises unrelated regression risk. | Good follow-up platform hardening, not the P1 critical path. |

All mutations remain POST/PUT/PATCH/DELETE. Confirmation nonce/digest/idempotency are separate integrity guards, not CSRF substitutes.

### D4 — Key/deletion/production enablement truth

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

Stop affected work and ask Owner if D1–D4 are not decided, Docker is unavailable for required PG/full-app gates, a migration requires real Neon action, live route needs a secret/charge outside approved caps, the app cannot meet 512 MB bounds, or a finding requires changing PRIVATE/product/security authority. After roughly two unproductive attempts at the same blocker, preserve logs and re-plan.

## 8. Evidence and closeout paths

- Canonical task/package: this file.
- Raw concise command receipts: `agent-tasks/task-056/terminal-receipt.md`.
- UI screenshots/manifests: ignored local task evidence first; only sanitized reviewed artifacts may be published.
- Closeout must separate local/PG/browser/live-route/CI/deploy/device/production and exact enabled state. Physical iPhone/Safari, real OAuth and real-personal-data acceptance are never inferred from Chromium/synthetic gates.
