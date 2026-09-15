# Task 056 — Mimi model-selection research

Status: **ROUTE/BENCH OWNER-APPROVED / MIDEX-v1 FORMULA PENDING**
Checked: 2026-09-15
Scope: model discovery, OpenRouter route policy, cache-aware forecasting and resumable Mimi-specific evaluation. This artifact contains no credential, account identifier or raw screenshot.

## 1. Corrections to the prior proposal

The earlier five-model funnel was not a complete independent market scan. It validated Owner-nominated DeepSeek/GLM/Muse candidates and added OpenAI/Google references. Treating that list as the five best current Mimi candidates was unsupported. This revision replaces it with a reproducible discovery policy and a current public-catalog scan.

The earlier single-price monthly estimate also omitted prompt-cache reads/writes, endpoint price variation and time drift. The USD 2 label was an ambiguous proposed inference allowance and is removed. Local/heavy bench is governed by cases, tokens, retries and wall time; money remains an observed output.

## 2. Independent discovery method and receipt

Public source: `GET https://openrouter.ai/api/v1/models?zdr=true`.

Static eligibility filter:

1. at least one endpoint is represented in the public ZDR-filtered model catalog;
2. output modality includes text;
3. context length is at least 131,072 tokens;
4. supported parameters include `tools` and `tool_choice`;
5. supported parameters include `structured_outputs` or `response_format`.

Observed snapshot:

```text
zdr_models=321
statically_eligible=230
free_statically_eligible=3
```

This is only a discovery filter. The model-level catalog aggregates endpoint capabilities and lowest pricing; exact provider/quantization, ZDR policy, parameters, context, availability and price must be refreshed and frozen in each route card.

### Free capability-smoke queue

| Model | Context | Public benchmark discovery signal | Use |
|---|---:|---|---|
| `google/gemma-4-31b-it:free` | 262K | agentic 6.7; coding 43.4 | First free smoke candidate. |
| `nvidia/nemotron-3-super-120b-a12b:free` | 262K | agentic 4.1; coding 37.7 | Independent architecture/provider comparison. |
| `google/gemma-4-26b-a4b-it:free` | 262K | coding 39.3; no agentic index in snapshot | Optional third smoke candidate. |

Free variants are useful for capability falsification, not assumed production defaults. OpenRouter documents 50 free-model requests/day without the qualifying credit threshold and 1,000/day after at least USD 10 purchased credits; availability differs from paid routes.

Owner reports the account has already purchased USD 10 and spent more than USD 9, so it previously met the documented purchase condition. Treat current 1,000/day eligibility as `OWNER_OBSERVED / LIVE_CHECK_REQUIRED`: immediately before free smoke, ask the Owner to confirm the dashboard still grants the higher quota. Remaining balance alone is not inferred to change the purchase-history condition.

### Ultra-cheap paid/ZDR discovery queue

Prices are the current model-catalog lowest structures, not guaranteed exact endpoint prices.

| Model | Input / cache read / output USD per 1M | Context | Agentic / coding discovery signal | Origin of nomination |
|---|---:|---:|---:|---|
| `z-ai/glm-5.3-flash` | 0.15 / 0.03 / 0.50 | 1.31M | 51.2 / 71.5 | Owner + scan validation |
| `deepseek/deepseek-v4-flash-0731` | 0.05 / 0.01 / 0.10 | 1.31M | 41.7 / 69.1 | Independent scan; Owner has prior usage |
| `deepseek/deepseek-v4.1-flash` | 0.30 / 0.006 / 1.20 | 1.05M | unavailable in snapshot | Owner nomination + scan validation |
| `inclusionai/ling-3.0-flash-vl` | 0.06 / 0.012 / 0.18 | 131K | 30.0 / 57.0 | Independent scan |
| `xiaomi/mimo-v2.5` | 0.14 / 0.0028 / 0.28 | 1.05M | 17.4 / 56.8 | Independent scan; Owner has prior usage |

DeepSeek V4.1 Flash's public model page says `response_format` is not enforced while the Models API lists `response_format` and `structured_outputs`. This inconsistency is a reason to test exact endpoints, not to exclude or accept the model from documentation alone.

### Quality-reference queue

| Model | Input / cache read / output USD per 1M | Context | Agentic / coding discovery signal | Note |
|---|---:|---:|---:|---|
| `z-ai/glm-5.3` | 1.40 / 0.26 / 4.40 | 1.31M | 53.4 / 74.8 | High-quality same-family reference. |
| `qwen/qwen3.8-27b` | 0.214 / 0.15 / 2.55 | 1.00M | 46.5 / 68.1 | Independent non-Western reference. |
| `openai/gpt-5.6-luna` | 0.20 / 0.02 / 1.20 | 1.05M | 42.7 / 71.4 | Low-cost OpenAI reference. Cache writes currently 0.25/M. |
| `google/gemini-3.8-flash` | 0.75 / 0.075 / 3.75 | 1.05M | 41.1 / 76.3 | Strong coding reference. Catalog exposes cache-write pricing. |
| `meta/muse-spark-1.3` | 1.25 / 0.15 / 4.25 | 1.05M | Design Arena signals only | STANDARD-only in this snapshot; absent from `models?zdr=true`. |

Benchmark indices are third-party discovery signals surfaced by OpenRouter. They do not establish Mimi safety, function-call correctness, Vietnamese interaction quality or cost per completed Task.

Batch variants are excluded from the interactive-route competition. They can answer a separate offline-throughput question but do not share the latency, interruption or request semantics of live Mimi chat.

## 3. Selection governance

Candidate discovery is collaborative but validation is evidence-driven:

1. Owner nominates models from benchmarks, experience or price discoveries.
2. T1 independently refreshes the eligible catalog and may add candidates.
3. Static filters remove obvious incompatibilities without spending tokens.
4. S1 falsifies hard capabilities cheaply. Failing tool/schema/state/privacy behavior stops the candidate.
5. S2 estimates task-family quality, token behavior, cacheability and latency.
6. Owner approves S3 finalists and token/wall-time envelope.
7. S3 selects a daily cost-first champion and an explicit higher-quality challenger/escalation route. No silent cross-model routing.

This agrees with current OpenRouter guidance: benchmarks create a shortlist, product-specific prompts select the winner, and cost per completed task matters more than token price alone.

## 4. Centralized OpenRouter route contract

### Privacy, state and context

- OpenRouter prompt/completion logging and data-sharing stay off.
- STANDARD and PRIVATE use separate API keys and guardrails.
- All requests set `data_collection="deny"`; PRIVATE additionally enforces ZDR at key/account scope and sends `provider.zdr=true`.
- ZDR solves endpoint retention selection; it does not solve input overflow. microSched owns canonical conversation state, assembles the bounded context and refuses unexpected router/provider compression or truncation.
- Exact model/provider, parameter support, attempts and pipeline transformations are preserved from router metadata.
- Provider-side response IDs are evidence/reconciliation handles, never the only recoverable state.

### Routing and price

- exact canonical model slug; no model aliases or automatic model fallback;
- exact eligible provider allowlist, `allow_fallbacks=false`, `require_parameters=true`;
- `max_price` sets input/output/request ceilings; current eligible minimum and ceiling are recorded in the route card;
- route card freezes model, provider, quantization, context, supported parameters, reasoning effort, prompt/tool/schema versions and catalog timestamp.

### Caching

Provider **prompt caching** is permitted and measured. Stable instructions/tool schemas go first, dynamic Task/conversation state goes last; a stable non-identifying session/cache key may improve sticky routing. Record `cached_tokens`, `cache_write_tokens`, cache discount and provider.

OpenRouter **response caching** is disabled for action-bearing Mimi requests. It stores and replays an entire previous response, including tool calls, and account-level ZDR disables it. It must not be confused with provider prompt-prefix caching.

OpenRouter considers in-memory prompt caching compatible with its ZDR policy. The route receipt must still establish the effective endpoint and cache fields.

### 9router local benchmark abstraction

The Owner guarantees the upstream legitimacy. T1 treats 9router only as a local technical abstraction and does not inspect or evaluate its source. Required observable contract: exact requested model/config, no unwanted transformation, complete token/cache/error receipt where available, bounded concurrency, rate-limit behavior and resumable atomic cases. It never becomes the production dependency.

## 5. Cache- and price-aware cost bands

Use disjoint usage counters:

- `U`: uncached, non-write input tokens;
- `C`: cached input-read tokens;
- `W`: cache-write tokens;
- `O`: visible output plus billed reasoning tokens;
- `S`: separately priced server-tool calls.

`cost = U×P_input + C×P_cache_read + W×P_cache_write + O×P_output + S×P_tool`

For each route, refresh:

- `P_low(t)`: cheapest endpoint at time `t` that passes every Mimi route constraint;
- `P_cap`: explicit OpenRouter `max_price`; this is the enforceable price ceiling;
- `H`: `C / (U + C + W)` for prompt input, reported with cache writes separately.

Publish three scenarios:

1. **Cold ceiling:** `H=0%`, use `P_cap` and the higher of input/cache-write rate for potentially written tokens.
2. **Warm planning:** initially `H=70%`; later replace with the rolling P10 cache-hit rate of comparable Mimi runs.
3. **Ideal operating:** `H=93%`, slightly below the Owner's observed 95.2% harness snapshot; use current eligible `P_low`.

Example only: 300 runs/month, each aggregating 30K prompt tokens plus 4K output/reasoning, current catalog prices, no search/tool charges. Values are USD/month:

| Model | Cold 0% | Warm 70% | Ideal 93% |
|---|---:|---:|---:|
| GLM 5.3 Flash | 1.95 | 1.19 | 0.95 |
| DeepSeek V4 Flash 0731 | 0.57 | 0.32 | 0.24 |
| DeepSeek V4.1 Flash | 4.14 | 2.29 | 1.68 |
| GPT-5.6 Luna | 3.69 | 2.24 | 1.76 |
| Gemini 3.8 Flash | 11.25 | 7.00 | 5.60 |
| Qwen3.8 27B | 4.99 | 4.58 | 4.45 |
| MiMo V2.5 | 1.60 | 0.73 | 0.45 |

The interval matters more than the point estimate. Output-heavy models benefit less from prompt cache. Prices, eligible endpoints and promotions can change; the route card timestamp and `max_price` turn that drift into an observable failure instead of a silent bill increase.

### Sanitized Owner baseline from supplied screenshots

```text
total_tokens=340M
requests=3K
average_tokens_per_request≈113K
total_spend=USD 9.46
average_spend_per_request≈USD 0.00315
blended_cost≈USD 0.0278/M tokens
reported_cache_hit=95.2%
```

The screenshots do not identify whether the 95.2% metric is provider prompt caching or a broader dashboard aggregation, nor the cached-token mix per model. Therefore 93% is an ideal scenario prior, not an acceptance claim for Mimi.

## 6. Hybrid measurement and drift control

Estimation and measurement answer different questions:

- estimation bounds future spend before equivalent observations exist;
- measurement tells the truth for one frozen workload/model/route/time window;
- hybrid control uses estimates as guardrails and repeated measurements to update them.

A measurement is comparable only when its receipt binds fixture/case hash, prompt/tool/schema versions, exact model/provider/quantization, reasoning effort, routing policy, cache mode, repetition and time window. Terminal OpenRouter usage is billing truth; local tokenization is a preflight sanity estimate.

Report by scenario family rather than one global average:

- task success and hard-safety failure count;
- tool/schema validity and duplicate-action count;
- input uncached/cached/write, visible output and reasoning tokens;
- cost per attempted run and per correctly completed Task;
- time to first token, end-to-end latency and retry/unknown-outcome rates;
- P50/P90/P95 plus cold/warm splits.

Refresh or invalidate the forecast when model/provider/price changes, prompt/tool/schema changes, cache-hit rolling P10 drops materially, workload mix shifts, or observed token/cost P90 exceeds its prior band. Early measurements calibrate the next estimate; they do not permanently replace the cold ceiling.

## 7. Token-governed resumable evaluation

### Stages

| Stage | Dataset | Repetition | Provisional per-model cap | Promotion rule |
|---|---:|---:|---:|---|
| S1 capability | 12 hard cases | 2 | 0.5M total provider tokens | Every hard contract passes twice. |
| S2 representative | 60 stratified cases | 2 | 5M | No hard failure; quality/cost/latency frontier remains competitive. |
| S3 heavy | 240 cases + long-horizon/recovery slice | 3 | 35M | Paired outcome, tail reliability and cost/task support champion/challenger decision. |

The S3 design is roughly 24.5M tokens for 240×3 runs at the provisional 30K input + 4K output shape, leaving about 10.5M for long-horizon cases, cache warm-up, controlled retries and tokenizer variance. The actual deterministic harness receipts from S1/S2 resize this envelope before S3.

Token caps count cached tokens at full volume and preserve separate counters for uncached input, cached input, cache writes, visible output, reasoning output, searches, calls and retries. Comparable models receive the same cases, repetitions and output limits; price does not buy extra quality attempts.

If S3 remains inconclusive, request equal 25M-token expansion tranches for the affected paired finalists. A proposed 100M or 200M allocation is therefore possible, but only after observed uncertainty or tail coverage justifies it; it is not the initial default.

### Checkpoint and resume

The atomic identity is `(bench_id, case_id, repetition, model_config_hash)`. Persist:

1. reserved input/output/total token allowance and wall-time deadline;
2. dispatch intent and attempt number before the network call;
3. route/generation ID when accepted;
4. terminal usage/cache/cost metadata and output hash;
5. grader results and promotion/stop reason.

Completed atomic units are immutable and skipped on resume. A retryable rate-limit/network failure retries only that unit within its allowance. An unknown outcome remains distinct and consumes its reserved budget until reconciled; restarting never reruns the entire model bench. Checkpoint after every unit, cap concurrency, and support clean stop at token, wall-clock, error-rate or Owner halt boundaries.

Recommended initial S3 wall-clock ceiling is 24 hours/model, resumable. The Owner can stop between units without corrupting receipts.

## 8. MIDEX-v1 proposal

### Unit and outputs

MIDEX ranks an exact route configuration:

`model + provider + quantization + reasoning effort + route-policy version`

Publish separate `MIDEX-S` and `MIDEX-P`; a route without current ZDR eligibility has no PRIVATE score. Always publish the component scores and these category champions alongside the composite:

- `M-Cost`: lowest cost per correctly completed Task;
- `M-Intel`: best performance on difficult planning/reasoning scenarios;
- `M-Accuracy`: highest exact expected-state correctness;
- `M-Truth`: strongest groundedness, abstention and confidence calibration;
- `M-Agent`: best tool/schema/recovery/action reliability;
- `M-Speed`: best P90 end-to-end latency per correct Task;
- `M-Uptime`: strongest qualifying endpoint and observed reliability.

MIDEX is decision support, not an automatic Owner decision.

### Hard gates

A route is unranked if it fails privacy/retention/context policy, leaks PRIVATE data, silently truncates/compresses, performs an unauthorized or duplicate mutation, or cannot satisfy required tool/schema semantics. These failures cannot be compensated by price or intelligence.

Uptime policy:

- `<90%`: excluded/quarantined;
- `90%–<95%`: benchmark/degraded lane only;
- `≥95%`: production-eligible;
- use `U = min(current OpenRouter endpoint availability, Mimi terminal-success rate)`;
- missing or insufficient current uptime evidence is benchmark-only, not production PASS.

Use p90/p99 latency rather than only averages and bind provider/quantization because identical model slugs can behave differently across serving endpoints.

### Component weights

| Component | Weight | Primary measurement |
|---|---:|---|
| Cost efficiency | 25% | Observed cost per correctly completed Task, including retries, reasoning, cache writes/reads and server tools. |
| Exact correctness | 20% | Expected final response/state/receipt match on the stratified Mimi set. |
| Truthfulness/calibration | 15% | Unsupported-claim rate, citation entailment where applicable, correct abstention and confidence calibration. |
| Agentic reliability | 15% | Tool/argument/schema validity, recovery, stop discipline and non-duplicate action behavior beyond hard gates. |
| Task intelligence | 10% | Difficult planning, instruction/data separation and multi-step solution quality. |
| Speed | 10% | P90 end-to-end latency per correctly completed Task; TTFT and throughput remain visible submetrics. |
| Uptime | 5% | Qualified route availability and Mimi terminal-success observations. |

Cost is the largest single weight because it is the Owner's main daily-use constraint. Correctness, truthfulness and agentic reliability together retain 50%, so cheap hallucination cannot win.

### Normalization and composite

All components are normalized to `[0,100]` using anchors frozen before S3. Quality axes use the same stratified cases and rubrics for every route. Speed and cost use log scaling because their practical ranges are multiplicative.

For cost per correct Task `C`, with pre-approved ideal `C_good` and unacceptable `C_bad`:

`S_cost = clamp(10 + 90 × ln(C_bad / C) / ln(C_bad / C_good), 10, 100)`

This gives the cost dimension a floor of 10 rather than zero: a route around 20× more expensive is heavily penalized if `C_bad/C_good=20`, but exceptional quality can still partially compensate. The same anchored log pattern applies to P90 latency.

For qualifying uptime, use piecewise anchors: 90%=0, 95%=80, 99.9%=100; interpolate between anchors. Routes below 95% remain non-production regardless of their composite.

Recommended composite:

`MIDEX = 100 × product((S_i / 100) ^ w_i)`

The weighted geometric mean penalizes an imbalanced route more than a weighted arithmetic mean. Category champions remain visible, so MIDEX never hides why one route ranks above another.

### Uncertainty, ties and versioning

- Compute a stratified bootstrap 95% interval by resampling benchmark cases, not merely repetitions of the same case.
- Report routes as tied when intervals overlap or point estimates differ by less than 3 MIDEX points.
- Freeze weights, anchors, hard gates and dataset manifest before S3 results are visible.
- Formula changes create a new version such as `MIDEX-v1.1` and rescore all frozen receipts; never tune weights to promote a preferred model after seeing results.
- Owner makes the final champion/challenger choice and may override MIDEX with a recorded rationale.

This follows holistic evaluation principles: broad scenario coverage, multiple explicit metrics and standardized comparison. Artificial Analysis likewise constructs domain indices from separately run component benchmarks and role-specific task weights, while noting that any index has limits for a specific use case.

## 9. Sources checked

- [OpenRouter public model catalog](https://openrouter.ai/api/v1/models?zdr=true)
- [OpenRouter model API/filter documentation](https://openrouter.ai/docs/api/api-reference/models/get-models)
- [OpenRouter model-selection framework](https://openrouter.ai/blog/tutorials/choose-best-ai-model/)
- [OpenRouter prompt caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching)
- [OpenRouter usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
- [OpenRouter response caching](https://openrouter.ai/docs/guides/features/response-caching)
- [OpenRouter ZDR](https://openrouter.ai/docs/guides/features/zdr)
- [OpenRouter provider routing and `max_price`](https://openrouter.ai/docs/guides/routing/provider-selection)
- [OpenRouter free-model limits](https://openrouter.ai/docs/faq)
- [Official OpenAI Responses reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
- [Official OpenAI prompt-caching/model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [Official OpenAI GPT-5.6 Luna pricing](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
- [Stanford HELM holistic evaluation](https://crfm.stanford.edu/2022/11/17/helm.html)
- [Artificial Analysis capability-index methodology](https://artificialanalysis.ai/methodology/capability-indices)
- [OpenRouter provider performance methodology](https://openrouter.ai/blog/insights/evaluate-llm-provider-performance/)
- [NIST statistical models for AI evaluation](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.800-3.pdf)
