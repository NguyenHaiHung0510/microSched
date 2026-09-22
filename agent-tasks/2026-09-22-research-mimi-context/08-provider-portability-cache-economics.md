# B07 — Provider portability, cache, and economics

**Status:** EVIDENCE COLLECTED — T1/Owner review pending
**Actual writer:** T3 GPT-5.6 Luna, high effort
**Date:** 2026-09-22
**Boundary:** research only. No provider call, no `MIMI_DEMO_1`, no runtime change, no model selection, no live evaluation, and no Owner-approved policy is created by this report.

## 1. Question and scope

This batch investigates how Mimi can remain portable across models and provider endpoints while preserving privacy, cache correctness, route reproducibility, uptime expectations, and a useful cost view. It covers model identity versus the infrastructure provider that actually serves a request; provider selection, ordering, fallback, capability/parameter filters, and health signals; implicit and explicit prompt/context caching, response caching, sticky sessions, and retention implications; ZDR, data-collection controls, BYOK/source provenance, `store` and truncation differences; the difference between listed price, effective billed price, cache-adjusted cost, and estimated cost; and the measurements Mimi would need before it can make a route or cost claim.

It does **not** choose a final model/provider, choose a cache-hit target, assume a 93% hit rate, or decide whether Mimi should use OpenRouter, a first-party API, or 9router in production.

## 2. Method and exact sources

Research used primary provider/router documentation and API references only. Pages were checked on 2026-09-22; provider behavior and prices remain versioned, time-dependent evidence rather than permanent facts.

### OpenRouter

1. [Prompt Caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching) — sticky provider routing, cache-read/write fields, provider-specific cache semantics, and `cache_discount`.
2. [Response Caching](https://openrouter.ai/docs/guides/features/response-caching) — beta response cache behavior, zero billing on hits, cache key/TTL constraints, and incompatibility with account-level ZDR.
3. [Uptime Optimization](https://openrouter.ai/docs/guides/best-practices/uptime-optimization) — provider health/availability tracking, response-time/error-rate signals, and fallback behavior.
4. [Get request and usage metadata for a generation](https://openrouter.ai/docs/api/api-reference/generations/get-generation) — generation-level provider/model, timing, prompt/completion/cached token, upstream cost, `total_cost`, router, fallback/session and streamed/cancelled metadata.
5. [Create a response](https://openrouter.ai/docs/api/api-reference/responses/create-responses) — response-level `session_id` sticky routing, provider metadata opt-in, and top-level prompt-cache control for supported Anthropic routes.
6. [Guardrails](https://openrouter.ai/docs/guides/features/guardrails/overview) — model/provider allowlists, ZDR, data controls, budget limits, and restrictive guardrail composition.
7. [Sovereign AI / in-region routing](https://openrouter.ai/docs/guides/get-started/sovereign-ai) — per-request `provider.zdr` and `provider.data_collection` controls.
8. [Workspaces](https://openrouter.ai/docs/guides/features/workspaces/overview) — workspace-scoped API keys, BYOK, routing defaults, guardrails, and observability boundaries.
9. [OpenRouter Privacy Policy](https://openrouter.ai/privacy/) — provider-side data practices vary; the policy was last updated 2026-08-31 and distinguishes OpenRouter handling from the selected model provider's handling.
10. [How OpenRouter model routing works](https://openrouter.ai/blog/insights/model-routing/) — official explanation of model routing versus provider routing and the provider object controls (`order`, `only`, `ignore`, `sort`, fallbacks, parameter and price/performance preferences).

### First-party provider documentation

11. [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) — cached prefix behavior, cache-related usage and diagnostics.
12. [OpenAI data controls by endpoint](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint) — Responses storage defaults, ZDR treatment of `store`, background-mode retention, and the fact that extended prompt caching is not ZDR eligible.
13. [Google Gemini context caching](https://ai.google.dev/gemini-api/docs/generate-content/caching) — implicit versus explicit caching, minimums, TTL, storage cost, and usage metadata.
14. [Google Gemini caching API reference](https://ai.google.dev/api/caching) — cached content is model-bound and can include system instructions, tools, tool configuration, and expiry metadata.
15. [Google Gemini ZDR](https://ai.google.dev/gemini-api/docs/zdr) — explicit cached context is stored until its TTL/expiry; an absolute zero-data footprint must not use `cached_content`; implicit in-memory caching is a different mechanism.
16. [Google Gemini token counting](https://ai.google.dev/gemini-api/docs/generate-content/tokens) — preflight `count_tokens` and post-call prompt/output/thought/cached/total usage fields.
17. [Google Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) — pricing is model, tier, mode, cache, and date dependent; it also shows that promotional and future renewal prices can differ.
18. [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — explicit breakpoints, minimum cacheable blocks, TTL and cache read/write accounting.

## 3. Observed facts

### 3.1 Route identity is at least two-dimensional

**FACT:** OpenRouter separates the selected **model** from the provider endpoint that serves that model. Its provider controls include explicit order/allow/ignore choices, sorting goals, fallbacks, parameter compatibility, and pricing/performance preferences. A model name alone is therefore not a complete reproducibility key. The generation metadata can expose the actual provider, model, router, upstream ID, session, timings and usage.

**FACT:** OpenRouter tracks provider response time, error rate and availability and uses this data in smart routing. Automatic fallback can change the serving provider and adds latency. “The selected model is X” must not be reported as “provider Y served the call” without receipt evidence.

**FACT:** A request may use a fixed provider order, adaptive sorting, or model fallbacks. These have different reproducibility and availability properties; routing configuration must be recorded with the run, not inferred later from a model slug.

### 3.2 Cache is not one portable feature

**FACT:** OpenRouter documents both prompt/context caching and response caching. They are materially different: prompt caching reuses a prefix or provider cache and still runs model inference; response caching can return an identical cached response without reaching a provider and reports zero billable usage; response caching is unavailable when account-level ZDR is enforced because it temporarily stores response data.

**FACT:** Prompt cache semantics differ by provider and model. OpenRouter documents automatic caching for several providers and explicit `cache_control` requirements for others. Cache write and read prices can differ, some writes cost more than ordinary input, and TTLs differ. The existence of a `cached_tokens` field is not a universal guarantee that the same discount or retention behavior applies on another route.

**FACT:** OpenRouter uses provider sticky routing to increase cache hits. Its documented default conversation identity is derived from opening messages, while an explicit `session_id` provides a more direct sticky-session key. Manual provider order takes precedence over sticky routing. A model route that is allowed to spray across providers can therefore have a different cache profile from a route pinned to one provider.

**FACT:** Cache measurements are exposed at different levels. OpenRouter exposes generation metadata such as cached/native prompt tokens, `cache_discount`, `upstream_inference_cost`, `total_cost`, and provider identity. Gemini exposes `usage_metadata` fields including cached content tokens; OpenAI and Anthropic expose provider-specific cache usage. Mimi must preserve the native receipt and avoid pretending that all providers have the same counter semantics.

### 3.3 Privacy and caching can conflict

**FACT:** OpenRouter's `zdr=true` and `data_collection="deny"` are routing controls, not the same thing as application-side storage. Account or guardrail settings can enforce stricter policies, and the request-level controls cannot loosen them. OpenRouter's privacy policy states that model providers have different retention/training practices; routing through OpenRouter does not erase the provider-side policy question.

**FACT:** First-party retention semantics differ too. OpenAI documents that Responses storage is enabled by default for a retention period and that ZDR forces `store=false`; extended prompt caching requires application state and is not ZDR eligible. Gemini says explicit `cached_content` is stored until expiry even when request logs follow ZDR dropping rules, so it is not suitable for an absolute zero-data footprint. This means “ZDR route” and “no persistent cache/context” are separate invariants.

**FACT:** OpenRouter response caching is disabled by account-level ZDR, but ordinary prompt caching may still be available depending on the actual provider and route. Mimi must not infer “all caching off” from `zdr=true`; it needs a route-specific cache policy and receipt.

### 3.4 Listed price is not the billed/effective cost

**FACT:** Listed input/output prices are a tariff snapshot, not a run's bill. Effective cost can change with cache reads/writes, reasoning tokens, provider endpoint, fallback, request mode, promo or renewal period, and rate-limit/billing rules.

**FACT:** OpenRouter generation metadata can contain token counts and `total_cost` plus `upstream_inference_cost` and `cache_discount`. When available, this is stronger evidence than reconstructing cost from a model page's list price. When it is unavailable, Mimi must label a derived number `ESTIMATED` and retain the price snapshot and formula version.

**FACT:** Gemini's official pricing page demonstrates time-varying and tier-varying prices, including dated promotional versus future prices. A cost dashboard therefore needs an `effective_at`/source version and cannot safely freeze today's displayed price for a one-year projection.

**FACT:** Cache hit rate alone is not cost. A high hit rate can coexist with expensive output or reasoning tokens, cache-write/storage charges, fallback calls, or a route whose cached price is not the cheapest route. Conversely, a low hit rate may still be acceptable when prompts are short.

## 4. Competing policies and trade-offs

These are candidate policies for T1/Owner consideration, not decisions.

### Policy A — Adaptive provider routing inside a privacy/capability envelope

Use an exact model family but let OpenRouter choose among an allowlist, with `zdr=true` and `data_collection="deny"` where required, `require_parameters=true`, max-price and latency/throughput preferences, and controlled fallbacks.

- **Strengths:** availability, less single-provider fragility, can exploit price/throughput/health changes, easy provider rotation.
- **Costs:** cache locality and response quality can vary; exact reproduction is weaker; a fallback may alter price, latency, language behavior, or tool support.
- **Required evidence:** actual provider per call, route policy hash, fallback count, usage/cost, cache counters, and provider capability snapshot.

### Policy B — Fixed provider pin for a route or conversation

Use `provider.only`/explicit `order` and disable fallback outside the approved endpoint set. Use an explicit session identity to preserve cache locality.

- **Strengths:** strongest reproducibility, easier debugging and cache attribution, easier comparison between prompt revisions.
- **Costs:** single-provider outage/429s become visible failures; stale cache or provider degradation can dominate cost and latency; it may discard a cheaper healthy endpoint.
- **Use case:** route-card tests, controlled prompt experiments, and privacy-sensitive conversations where the allowlist is small.

### Policy C — Hybrid by workload/privacy state

Use fixed, eligibility-checked routes for private or evaluation runs; use adaptive routing for ordinary standard work within the same privacy and capability envelope. The UI shows the route mode and actual provider after completion.

- **Strengths:** preserves reproducible evidence where it matters while allowing daily resilience and lower cost elsewhere.
- **Costs:** two route behaviors complicate support and cost comparisons; standard and private metrics are not directly interchangeable.
- **Key hazard:** a fallback must not escape the private route's privacy/capability envelope.

### Policy D — Cost-first adaptive routing

Sort by price and accept provider movement, while using a minimum capability/uptime gate.

- **Strengths:** low nominal cost and easy scale.
- **Costs:** listed price can be a false economy when cache is cold, output/reasoning grows, or a provider's error/latency creates retries. It risks selecting a provider whose tool/structured-output support does not satisfy Mimi's contract.
- **Minimum guardrail:** price is a tie-breaker after privacy and capability eligibility, not the first unrestricted decision.

## 5. Proposed provider-neutral contract

The following is a **PROPOSAL** for later T1 synthesis; it is not an Owner-approved runtime policy.

### 5.1 Route identity and admission

Represent each provider call with an immutable route card containing:

```text
model_id
provider_endpoint_id (if known)
router/source (OpenRouter, first-party, 9router abstraction, ...)
provider_policy_version
provider_allowlist/order/fallback mode
privacy mode (STANDARD or PRIVATE)
zdr and data_collection requirement
store/truncation/cache policy
reasoning/effort and tool-choice mode
parameter/capability requirements
price snapshot ID and currency
context/output/deadline and retry caps
```

Admission should evaluate in this order:

1. data/privacy eligibility and source boundary;
2. required model parameters/tools/structured output;
3. context/output/deadline and budget bounds;
4. provider health/availability floor and fallback envelope;
5. latency/throughput/cost/cache preference.

This ordering prevents a low nominal price from overriding privacy or contract capability.

### 5.2 Cache policy

Keep three explicit switches, rather than one `cache=true` flag:

1. `prompt_cache`: provider-native prefix/context caching allowed, forbidden, or unspecified;
2. `response_cache`: identical-response cache allowed only for non-sensitive, explicitly eligible standard requests; disabled for Private and account-level ZDR;
3. `application_state`: provider `store`, background state, files, and conversation persistence.

The context builder must keep the stable system/tool/policy prefix byte-stable where practical and place volatile user/task state after it. It must not add timestamps, unordered maps, changing IDs, or route noise to the stable prefix without recording the reason. This is a cache optimization, not a license to omit provenance or truncate safety policy.

### 5.3 Privacy policy

For a future PRIVATE route, a conservative **PROPOSAL** is: enforce account/guardrail privacy settings and request-level `zdr=true`/`data_collection=deny` where supported; disable response caching and provider-side persistent conversation state unless separately approved; avoid explicit provider caches whose documented TTL stores content when the product promise is zero-persistence; keep the fallback set inside the same privacy/capability envelope; and record provider policy/version and actual endpoint in a scrubbed receipt.

For STANDARD, adaptive prompt caching may be allowed if the route card records its semantics and the UI does not present cache hits as proof of privacy or quality.

### 5.4 Portability seam

Do not expose OpenRouter-only fields as Mimi's domain truth. Use a normalized envelope with optional native fields:

```text
normalized: input_tokens, output_tokens, reasoning_tokens?, cached_tokens?, total_cost?, provider_id?, model_id, latency, ttft?, finish/outcome
native:     provider-specific usage, cache write/read fields, generation ID, pricing components
provenance: source, checked_at, route-card hash, price snapshot, normalization version
```

Missing native data remains `UNKNOWN`/`UNAVAILABLE`; it must not become zero. “No provider API available” means Mimi may show an estimate, not fabricate a billed cost.

## 6. Hybrid estimated + measured cost accounting

The recommended approach is **hybrid measurement**, not a single fixed estimate.

### Measured lane

For every eligible provider call, retain (scrubbed) actual input/output/reasoning/cache token fields, actual provider/model, generation/request ID, `total_cost` or purchasing-provider usage, latency, fallback/attempt count, and price/policy snapshot IDs. Prefer direct purchasing-provider billing APIs when Owner enables them; otherwise use the router generation endpoint. This lane reports observed cost, not a forecast.

### Estimated lane

Before dispatch, calculate a range from versioned assumptions:

```text
estimated_cost_low  = low input/output volume × eligible low effective rates
estimated_cost_mid  = expected volume × current effective-rate snapshot
estimated_cost_high = high volume/reasoning/fallback case × eligible high rates
```

For repeated Mimi use, model at least these variables separately: input tokens by context segment (stable prefix, history, dynamic domain context, user turn, tool-return payload); output and reasoning tokens; prompt cache read/write tokens and response-cache hit count; calls per user request, tool-loop turns, retries, fallbacks and unknown reconciliations; model/provider price snapshot, mode/tier, currency and promotional expiry; and observed cache-hit distribution and TTL/window, not a fixed target.

Use a rolling measured distribution (for example P50/P90 and an observation count) only after enough real receipts exist. Recompute when model, provider, prompt assembly hash, tool schema, route policy, pricing source, or cache behavior changes. Projections for month/quarter/year should show a range and assumptions, not silently extrapolate one day's hit rate.

### Cost formula boundary

When `total_cost` is supplied by the purchasing layer, it is the canonical billed observation. A derived formula may explain it but must not replace it. When only token counts and rates exist, the result is `ESTIMATED`; if cached-token pricing, reasoning pricing, provider surcharge, or fallback cost is missing, widen the range and mark the missing component. A cache-hit rate without a price snapshot is not enough to produce a dollar figure.

## 7. Measurements needed for Mimi/OpenRouter

The following measurement card is a **PROPOSAL** for a later Owner-approved eval/dogfood spec.

### Per-call

- route-card hash/version and requested model;
- actual provider endpoint, model, router, `session_id` class, upstream/generation ID;
- requested privacy/data policy, provider policy result, and actual data-policy metadata if supplied;
- input/output/reasoning/cached/cache-write token counts, total tokens and native usage payload;
- measured `total_cost`, `upstream_inference_cost`, `cache_discount`, or explicit unavailable status;
- request accepted time, TTFT, completion time, throughput, timeout/cancel/retry/fallback;
- tool/structured-output capability result and terminal outcome;
- context assembly hash, stable-prefix hash, tool schema hash, prompt policy hash;
- `ESTIMATED` versus `OBSERVED` label and price-source `checked_at`.

### Aggregates

- cache-read and cache-write ratio by model/provider/route policy;
- cost per request and cost per successful semantic task, separately for standard/private;
- P50/P90 TTFT, end-to-end latency, throughput, retry/fallback rate, unknown reconciliation rate;
- provider availability/error-rate window and sample size;
- output/reasoning volume distribution;
- effective cost range at daily/weekly/monthly/quarterly/yearly calendar boundaries;
- count of calls for which cost/provider/cache evidence was unavailable.

### Confounders to record

- changed prompt/system/tool prefix or serialization order;
- changed model snapshot, provider, quantization, effort or parameter support;
- cache TTL expiry, new conversation/session, provider failover, account balance/credit checks;
- price/promotion/tier date; response cache versus prompt cache;
- standard/private policy and whether a BYOK or router key was used.

## 8. Open questions for Owner/T1

1. Should the daily Mimi route be Policy A (adaptive), Policy B (pinned), or Policy C (hybrid)?
2. For STANDARD, is response caching acceptable at all, or should Mimi use prompt caching only?
3. For PRIVATE, is the desired promise “provider ZDR/no training” or the stricter “no provider-side persistent cache/state,” with the cost/latency trade-off accepted?
4. Which OpenRouter provider allowlist and fallback scope is acceptable, and what evidence should qualify an endpoint as healthy (uptime window, error rate, throughput, cache economics)? No numeric threshold is assumed here.
5. Should Mimi consume OpenRouter generation metadata only, or may it use direct purchasing-provider management/billing APIs for the dashboard? If the latter, which key scope and retention boundary?
6. Is explicit provider pinning allowed for reproducible research runs while daily production remains adaptive?
7. Which cost horizon and calendar grain should be shown, and how should missing historical source data be labeled/snapshotted?
8. Which normalized fields are mandatory for a route to be `ROUTE_CARD_PASS`, and which may remain `UNKNOWN` without blocking standard text-only chat?

## 9. Evidence version and limitations

- Evidence date: 2026-09-22 (Asia/Saigon); links were accessed/crawled on or before this date.
- Provider docs are authoritative for their own API semantics, but OpenRouter's normalized surface cannot guarantee every upstream provider reports identical counters or retention behavior.
- Dashboard/provider health and cache ratios are time-window observations, not perpetual guarantees.
- Search/browser research did not call an API, inspect an account, read a key, or validate Mimi's current production route. No model/provider is selected by this file.
- OpenRouter, OpenAI, Google, and Anthropic may change prices, model aliases, cache TTLs, ZDR rules, and usage fields; a later eval must snapshot URLs/versions and recheck before egress.
- `MIMI_DEMO_1` was not read, printed, or used.

## 10. Research receipt

```text
scope: B07 provider portability/cache/economics
actor: T3 GPT-5.6 Luna, high effort
worktree: C:\Users\os\.codex\worktrees\mimi-context-research-2026-09-22\microsched
runtime/API/key/eval: NOT RUN by design
file changed: agent-tasks/2026-09-22-research-mimi-context/08-provider-portability-cache-economics.md
git diff --check: PASS (worker and T1 integration checks)
commit: none
```
