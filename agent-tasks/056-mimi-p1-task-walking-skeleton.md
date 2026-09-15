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
- R2 attachments, parsers, web search unless D1.f is approved, memory/skills/Orbit, background model jobs or automatic multi-model routing;
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

- Implement only the D1-approved OpenRouter-compatible adapter and exact model routes. Application-defined function tools and independently validated structured outputs are the core; no hosted file/computer/shell tools. D1.f controls the optional web-search lane. API keys are supplied by the Owner through the existing secret/config mechanism, never chat/log/fixture.
- Run a small synthetic STANDARD route card: exact model/effort/endpoint, tool/structured-output/stream/usage behavior, latency and actual cost. Driver/provider/subject errors remain distinct.
- Run focused RED→GREEN guards, full backend non-PG, disposable PG migration/round-trip and Mimi integration, frontend lint/unit/build, repository hooks, local full-app Playwright, and required CI.
- Obtain risk-based independent delta review on a frozen application candidate before final publication/merge. Reconcile findings with evidence; no finding quota.
- Before merge: fresh PR OPEN/non-draft/head/base/diff/mergeability/checks, then CAS merge with exact head. Ordinary deploy proof requires exact `/api/readyz.commit` and `db=up`. No automatic migration or production data mutation.
- If real-chat enablement remains gated, deploy code/config default-off and report `LOCAL_VERIFIED`, not `ENABLED`.

## 5. Owner decisions

### D1 — Initial live route and spend

This decision has three independent parts: **candidate funnel**, **API procurement/transport route**, and **whether bounded web search joins this slice**. Passing model quality does not make an opaque or unauthorized route acceptable, and a compatible gateway does not prove model quality.

#### D1.a — Round-zero route/capability filter

A candidate is excluded before quality scoring if any of these cannot be proved with a synthetic route card:

1. exact model/version and actual upstream provider are observable; no alias, automatic model/provider fallback or hidden retry;
2. route use is authorized for application API traffic; subscription/OAuth/CLI/MITM access is not treated as an API entitlement;
3. streaming, cancellation, error/unknown-outcome mapping, usage accounting and application-executed function calls preserve stable IDs across the full round trip;
4. the Mimi structured-output subset is accepted and then independently validated by the application;
5. no silent context truncation/compression, unapproved prompt/plugin transformation, unapproved server-side tool or request/response content logging;
6. STANDARD data policy is explicit; any future PRIVATE route additionally needs separately proved zero-retention eligibility;
7. hard request/token/cost caps and a request-level route receipt are available.

`NO_PROVIDER_STATE` and `NO_SILENT_TRUNCATION` are provider-neutral adapter invariants, not OpenAI-only parameter names:

- microSched is the canonical conversation/run store. Mimi never depends on a provider conversation object or provider response retrieval for recovery;
- send the strongest explicit no-store option where a route exposes one. Otherwise require an endpoint policy such as OpenRouter ZDR for PRIVATE and fail closed if eligibility cannot be proved;
- assemble and preflight the bounded context in microSched. Configure explicit overflow failure where supported and reject any receipt showing gateway/provider context compression or dropped messages;
- OpenAI Responses specifically requires `store=false`; `truncation=disabled` makes overflow fail rather than drop oldest items. Provider `max_tool_calls` does not replace Mimi's application-level function-call ceiling;
- gateway claims of compatibility are not accepted as proof of event, function-call, structured-output or recovery semantics.

#### D1.b — Broad candidate funnel, not geography-based selection

Public benchmark position is only a discovery signal. The first Mimi-specific smoke round runs the same synthetic Task read → preview → confirm/create journey on a broad cost/quality pool; only smoke survivors enter the heavier fault/recovery matrix:

| Candidate | Current OpenRouter list price used for conservative estimation | Why it belongs | Known gate/risk |
|---|---:|---|---|
| Z.ai `z-ai/glm-5.3-flash` | USD 0.15/M input, 0.50/M output; a current provider promotion is lower | Extremely low-cost, 1M+ context, reasoning, tools and structured outputs; designed for efficient coding/long-horizon agents. | Reasoning is mandatory; actual output-token multiplier and route-level schema/tool reliability must be measured. |
| DeepSeek `deepseek/deepseek-v4.1-flash` | USD 0.30/M input, 1.20/M output; current time/provider discounts can halve this | Cost-efficient agent/coding model with 1M context and tools. | OpenRouter's model page and Models API currently disagree about enforced `response_format`; exact ZDR endpoint must pass strict-schema tests. |
| OpenAI `openai/gpt-5.6-luna`, `medium` | USD 0.20/M input, 1.20/M output | Low-cost native Responses reference with tools and structured outputs. | Quality versus the two cheaper Asian candidates must be earned in Mimi tests, not assumed. |
| Google `google/gemini-3.8-flash`, `medium` | USD 0.75/M input, 3.75/M output through 2026-12-31 promotion | Cross-family quality reference with 1M context, tools and structured outputs. | Higher daily cost; native Interactions semantics differ from the OpenRouter compatibility layer. |
| Meta `meta/muse-spark-1.3`, `medium` | USD 1.25/M input, 4.25/M output | Strong long-running agent/coding reference with tools and structured outputs. | The public `zdr=true` catalog snapshot did not include it on 2026-09-15, so it is STANDARD-only unless eligibility changes. |

The current public `models?zdr=true` snapshot includes GLM 5.3 Flash, DeepSeek V4.1 Flash, Gemini 3.8 Flash and GPT-5.6 Luna. This is refreshed during route selection and before enablement because endpoint policies can change.

Score survivors on exact action correctness, unsupported-action refusal, no duplicate mutation, tool/argument validity, schema validity, recovery after injected transient/unknown outcomes, instruction/data separation, total billed input/output including reasoning, latency and observed cost. A hard safety/correctness failure is disqualifying; do not average it away with style or generic benchmark scores.

**Recommended funnel:** smoke all five cheaply; run the complete Mimi matrix first on GLM 5.3 Flash, DeepSeek V4.1 Flash and the best quality-reference survivor. Select a cost-first daily STANDARD default plus a stronger explicit escalation model; do not silently route between them. No Astra route.

#### D1.c — Procurement/transport cases

| Case | When it is eligible | Trade-off | Recommendation |
|---|---|---|---|
| 9router local gateway | Local synthetic and heavy comparative benchmarks only. Disable smart fallback, combinations, RTK/Headroom/Caveman/Ponytail transforms and content logging. | Useful for large local experiments, but local process/config availability and subscription/OAuth translation are unsuitable production dependencies. | **Approved direction from Owner:** never use as Mimi production route. |
| OpenRouter credits and/or BYOK | Add existing official OpenAI and Google AI Studio credentials to OpenRouter as prioritized BYOK keys; filter them to Mimi's OpenRouter API keys and prevent shared-capacity fallback when exact BYOK use is required. Other models use OpenRouter credits. | One production interface, unified policy/usage evidence and broad model access; adds a gateway and credit-purchase/BYOK policy surface. | **Recommended production interface.** Start with minimum controls below and harden before PRIVATE enablement. |
| Direct OpenAI + Google APIs | Retain as rollback/diagnostic comparison where native semantics must be isolated. | Fewest translation layers, but duplicates adapters, billing and policy configuration. | Not the primary P1 interface if OpenRouter route fidelity passes. |

#### D1.d — OpenRouter configuration, minimum to hardened

**Minimum for any Mimi synthetic/production request:**

- exact canonical model slug; no `latest`, `auto`, `:free`, `:online`, `:nitro`, `:floor` or `:exacto` variants;
- `allow_fallbacks=false`, `require_parameters=true`, `data_collection="deny"`, exact resolved provider allowlist, and request `max_price` ceilings;
- prompt/completion logging and the 1% data-sharing discount remain off; no plugins, response healing or context compression;
- `X-OpenRouter-Metadata: enabled`; reject/flag a response whose requested/served model, provider, attempts or pipeline differs from the approved route;
- application caps provider calls, function calls, input/output tokens and deadlines; the model/provider cannot extend them.

**STANDARD key:** separate OpenRouter API key with a model allowlist, daily/monthly budget and a guardrail denying data collection. It may use approved non-ZDR endpoints, but exact provider and no-retention setting remain observable.

**PRIVATE key:** distinct OpenRouter API key and guardrail enforcing ZDR for OpenAI, Google and non-frontier groups, plus the same model/provider allowlists and tighter budget. Mimi additionally sends `provider.zdr=true` and `data_collection="deny"` per request. Because OpenRouter combines these controls using stricter OR/intersection rules, request code cannot loosen the key/account policy. Refresh the ZDR endpoint eligibility immediately before every model approval; fail closed if none remains.

#### D1.e — Cost-estimation frame and separate budgets

Mimi cost is driven by aggregate billed tokens across every provider call, not the length of the Owner's first message:

`monthly model cost = runs/month × ((billed input/run × input price) + (billed output+reasoning/run × output price)) / 1,000,000`

The initial planning profiles below exclude web search, purchase fee, taxes and temporary provider discounts:

| Usage profile | Runs/month | Aggregate billed tokens per run | GLM 5.3 Flash | DeepSeek V4.1 Flash | GPT-5.6 Luna | Gemini 3.8 Flash | Muse Spark 1.3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Light | 100 | 10k input + 1.5k output | USD 0.23 | USD 0.48 | USD 0.38 | USD 1.31 | USD 1.89 |
| Regular daily | 300 | 30k input + 4k output | USD 1.95 | USD 4.14 | USD 3.24 | USD 11.25 | USD 16.35 |
| Heavy daily | 600 | 80k input + 10k output | USD 10.20 | USD 21.60 | USD 16.80 | USD 58.50 | USD 85.50 |

After local deterministic runs, record actual total tokens/calls for each journey and replace these guesses with P50/P90 daily projections. Keep three independent controls:

1. **Codex development usage:** unrelated to Mimi and never charged to a Mimi/OpenRouter API key.
2. **One-time Mimi model-selection benchmark allowance:** proposed maximum USD 2 inference spend across all candidates; no purchase implied by this cap.
3. **Mimi production runtime budget:** selected only after measured P50/P90 usage; enforce on the dedicated STANDARD/PRIVATE keys. OpenRouter credit purchases add the current 5.5% fee (USD 0.80 minimum) separately.

#### D1.f — Optional web-search server tool

Web search is useful for current-information questions, but it changes Mimi's data flow, cost, determinism and prompt-injection surface. OpenRouter's `openrouter:web_search` tool is currently beta and is executed by OpenRouter/search engines rather than microSched.

**Recommended bounded extension:** keep the Task walking skeleton independent of search, then add a STANDARD-only, explicit Owner-enabled `Research mode` in this same task after the core route is GREEN. Pin one search engine rather than `auto`; allow at most 2 searches/run, 5 results/search and 10 total results; require source URLs/citations; treat every result as untrusted data; include query/count/cost/completeness in the evidence bundle. A typical Exa/Parallel/Perplexity search costs USD 0.005 plus LLM tokens for the returned content.

PRIVATE web search remains disabled until the selected search engine's own retention/data-use path is proved; a ZDR model endpoint alone does not establish that the separate search processor is ZDR.

Owner inputs still needed for D1 (never paste a key into chat):

- approve or narrow the five-model smoke funnel and three-model full-matrix rule;
- confirm OpenRouter as the production interface with separate STANDARD and PRIVATE API keys/guardrails;
- approve or defer the bounded STANDARD-only Research mode;
- state whether OpenRouter already has usable credits; if not, choose the maximum top-up separately from the USD 2 benchmark inference allowance.

Research checked 2026-09-15: [OpenAI GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna), [OpenAI model comparison](https://developers.openai.com/api/docs/models/compare), [OpenAI Responses create](https://developers.openai.com/api/reference/cli/resources/responses/methods/create), [Google latest model](https://ai.google.dev/gemini-api/docs/latest-model), [Google pricing](https://ai.google.dev/gemini-api/docs/pricing), [Google function calling](https://ai.google.dev/gemini-api/docs/function-calling), [9router documentation](https://docs.9router.com/), [9router repository](https://github.com/decolua/9router), [OpenRouter model catalog API](https://openrouter.ai/api/v1/models), [OpenRouter BYOK](https://openrouter.ai/docs/guides/overview/auth/byok), [OpenRouter provider selection](https://openrouter.ai/docs/guides/routing/provider-selection), [OpenRouter router metadata](https://openrouter.ai/docs/guides/features/router-metadata), [OpenRouter ZDR](https://openrouter.ai/docs/guides/features/zdr), [OpenRouter guardrails](https://openrouter.ai/docs/guides/features/guardrails/overview), [OpenRouter web-search server tool](https://openrouter.ai/docs/guides/features/server-tools/web-search) and [OpenRouter FAQ](https://openrouter.ai/docs/faq).

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
