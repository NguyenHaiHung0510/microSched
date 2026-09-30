# B21 — Model funnel status and MIDEX-mini proposal

Status: **T1 PROPOSAL FOR OWNER REVIEW — NO THREE-MODEL EVAL RUN**

Checked: 2026-09-23. This note supplements the Owner-approved B19/D10 packet; it does not silently
replace that single-model GLM pilot or authorize additional provider inference.

## 1. What has actually passed

Task 056 defined and ran a public-catalog discovery pass: ZDR-filtered OpenRouter models were
screened for text output, context size, tools/tool choice and structured output. Its recorded
snapshot was 321 ZDR-listed models, 230 statically eligible, three free candidates. The result is
a candidate pool, not a Mimi quality ranking. No current repository receipt establishes that the
Task 056 S1 capability, S2 representative or S3 heavy comparative stages passed.

B19's Stage 0 endpoint inventory and its 42-run GLM D10 quality eval are also **NOT RUN**. Model
page capability and benchmark scores cannot prove a provider-specific ZDR route, high reasoning
effort, tool/schema fidelity, Vietnamese conversation quality, uptime under Mimi's workload, or
cost per correctly completed Mimi task. Those require exact route cards and version-bound runs.

The Mimi runtime presently has one configured model slug at a time (`MIMI_ROUTE_MODEL`), with
one exact provider/quantization or one adaptive provider allowlist. `.env.example` leaves the
model unset and the live gate disabled. Thus the approved/adopted P1C-A daily model count is
**zero**; GLM is the approved *first eval candidate*. The model currently present in any local or
production private environment is **UNVERIFIED** by this note. Historical dogfood attempts do
not establish current adoption.

## 2. Three current public model-page observations

These are displayed catalog prices per 1M tokens, checked 2026-09-23. They are not exact
ZDR-qualified endpoint prices or guaranteed renewal prices.

| Candidate | Input | Output | Cache read | Role in comparison |
|---|---:|---:|---:|---|
| `z-ai/glm-5.3-flash` | $0.075 | $0.25 | $0.015 | B19 candidate and low-price baseline; page labels its rate 50% off. |
| `openai/gpt-6-luna` | $0.10 | $0.50 | $0.01 | newly released challenger; possible better cost per correct task is a hypothesis. |
| `deepseek/deepseek-v4.1-flash` | $0.10 | $0.50 | $0.01 | independent model-family challenger; provider-level support and price vary. |

Primary catalog pages: <https://openrouter.ai/z-ai/glm-5.3-flash>,
<https://openrouter.ai/openai/gpt-6-luna>,
<https://openrouter.ai/deepseek/deepseek-v4.1-flash>.
Exact ZDR endpoint inventory must come from OpenRouter's authenticated endpoint API during an
approved preflight. Public benchmark scores are discovery signals only. GPT-6 Luna launched
2026-09-22, so long-window production reliability is not yet established.

## 3. Relation among D10, MIDEX-mini and MIDEX-v1

| Layer | Immediate question | Evidence/output | Decision it can support |
|---|---|---|---|
| D10 (B19) | Does one GLM route satisfy the first P1C-A STANDARD/Task contract? | controlled and daily-topology lanes; 9 scenarios/42 runs; hard gates plus semantic rubric | candidate live-dogfood admission for that version/route |
| MIDEX-mini (proposed) | Which of three candidates merits deeper Mimi testing? | paired hard cases on frozen P1C-A; route, cache, tokens, latency, correctness receipts | shortlist/challenger choice, **no champion claim** |
| MIDEX-v1 (Task 056) | Which exact routes best serve Mimi across scenario families? | S1/S2/S3, category champions and composite with uncertainty | Owner chooses daily and escalation routes; later sanitized publication gate |

MIDEX-mini should reuse MIDEX's exact-route identity and metric schema. It should not invent a
different score or publish a leaderboard. A first small comparison can record component metrics
without computing the final MIDEX index. The eventual index formula remains Owner-controlled.

## 4. Proposed MIDEX-mini admission and cost envelope

Run only after P1C-A deterministic gates and after a separate Owner-approved amendment freezes
the cases, exact route cards, effort equivalence, grading, monetary caps and retention. Proposed
first pass: the Task 056 S1 shape of **12 hard cases × 2 repetitions × 3 models = 72 scenario
runs**. Include ordinary/read-only/clarification, read-tool progress, draft/preview, injection,
partial coverage and reconnect. Pair each case across models, randomize order, and report
controlled exact-provider results and any production-style adaptive lane separately. No mutation
to Owner data. Stop a candidate at a hard privacy/authority/schema failure rather than spending
its remaining allowance.

Provisional cap: **0.5M provider tokens per model, 1.5M total**, counting cached input at full
volume, with separate input uncached/read/write, output/reasoning, calls/retries and buyer cost.
At a planning mix of 0.4M input + 0.1M output per model and the displayed catalog rates, the
three model totals are about **$0.055 GLM + $0.09 Luna + $0.09 DeepSeek = $0.235**, before
cache discounts, cache writes, fees and drift. An intentionally loose all-output bound at the
same displayed rates is **$0.625**. Neither is a spend receipt or a safe admission cap. The
execution amendment must use fresh endpoint price ceilings, per-run projected-cost admission
and an aggregate emergency cap; a preliminary cap of **$1.25** would cover 1.5M tokens at a
$0.60/M output ceiling plus headroom, but needs Owner approval and exact billing rules.

The mini pass is deliberately small: it can reject unsuitable routes and inform which models
deserve S2. It cannot establish stable P90 latency, uptime or statistically defensible
cost-per-correct-task for daily use. S2/S3 token envelopes are resized from observed S1 data,
not copied blindly from a 2026-09-15 forecast.

## 5. Sequence for the next credible live dogfood

1. Finish the P1C-A provider-neutral policy/context/read-loop/draft/preview/recovery contract.
2. Pass deterministic unit, fake-provider, disposable-Postgres, API/SSE and synthetic browser
   gates; independent ad-review reconciles the frozen implementation and QA spec.
3. Run the already approved GLM D10 preflight/eval only when B19's hashes, route criteria and
   `MIMI_DEMO_1` handling are satisfied. A route failure is a result, not permission to switch
   silently to Luna or DeepSeek.
4. If GLM passes, T1 prepares the local live app and Chrome QA; Owner then dogfoods the app.
   The model selector and context/effort inspector are shown according to P1C-A's two-surface
   contract, with unavailable routes clearly marked unavailable.
5. Execute MIDEX-mini in parallel with demo preparation only after its separate approval and
   without changing the demo route mid-acceptance. P1C-B bulk workflow and its eval amendment
   follow the first credible dogfood.

The nearest viable alternative is to run the three-model mini pass before D10. That could catch
a better candidate earlier, but it adds route qualification and comparison work to the shortest
path to a presentation-ready live demo. T1 recommends preserving D10 first and starting the
mini pass once the P1C-A fixture/harness is frozen.

## 6. Open Owner decision

Approve, amend or defer the **MIDEX-mini proposal** in §4. The B19 GLM D10 approval already
exists; this decision controls only the additional three-model comparison. No new model becomes
the Mimi default from this document alone.
