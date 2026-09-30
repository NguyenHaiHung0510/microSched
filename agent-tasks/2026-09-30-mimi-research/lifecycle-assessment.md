# Mimi runner: lifecycle assessment after the first prototype

Date: 2026-09-30. Status: T1 recommendation; framework adoption remains Owner-reserved.
Authority: approved 066/067 local no-key experiment. This assessment changes the interpretation of its evidence, not product scope or production architecture.

## Corrected recommendation

Continue considering LangGraph as the leading orchestration candidate for Mimi's growing workflow needs. The first prototype is not ready for adoption, but its small fake-provider benchmark does not justify rejecting the framework or selecting the current loop for Mimi's whole roadmap. Keep the current runner as the working control while completing the approved experiment. Do not equate temporary deployment choice with long-term architecture selection.

The Owner's clarification explicitly includes many domains, workflow shapes, reasoning rounds, long-lived operation and continued development. B16 already describes a generalized query → evidence snapshot → grouping/strategy → direction → materialization → frozen preview → confirmation → atomic execution/reconciliation path. Its dated implementation inventory is historical; its approved workflow direction is relevant. A simple read/create loop is a useful parity probe but underrepresents this direction.

## What the measurement establishes

OBSERVED: 20 finite synthetic conversations per cell, 25 dispatches per cell, same canned provider responses. Mean complete turn: control 53.054 ms, graph 97.572 ms; warm mean excluding the first sample: 50.86 ms and 73.09 ms. Absolute mean delta about 44.5 ms; relative delta about 84% of this tiny fake-provider baseline. These are non-interleaved discovery samples, not a reliable production latency estimate or tail distribution. They do not isolate per-node cost or establish user-perceived responsiveness.

OBSERVED: end RSS about 126.7 versus 164.7 MiB; both finite workloads avoided OOM under the tested 512 MiB container limit. Graph produced 70 checkpoints and 340 checkpoint writes over 20 threads. The prototype added orchestration code while retaining the current loop for rollback. These facts establish current overhead and duplication; line count alone does not establish future development or maintenance cost.

INFERRED, conditional illustration only: if an otherwise equivalent real turn took 3 seconds and the extra cost stayed 44.5 ms, its relative increase would be about 1.5%. Neither premise has been measured with a live provider. Do not extrapolate linear graph cost across more nodes, reads, checkpoints or concurrent runs.

UI acceptance should separate initial acknowledgement, first useful progress/text, time waiting for a confirmation, cancellation acknowledgement and settlement, resume/reconcile truthfulness, and total time to a correct result. A slower total run can be preferable when it exposes useful progress, recovers reliably or prevents repeating work. This prototype has not demonstrated those framework-specific benefits; the cancellation UI repair belongs to the feedback/lifecycle slice and must not automatically be credited to LangGraph.

## Why a standard framework may pay off

Primary documentation describes reusable subgraphs with explicit input/output schemas, separate development of graph parts, persistent execution state and human interruptions. Those mechanisms plausibly suit reusable domain workflows and pause/review/continue paths. This is a transfer hypothesis, not evidence of lower Mimi maintenance cost. See [subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs), [persistence](https://docs.langchain.com/oss/python/langgraph/persistence), and [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), fetched 2026-09-30.

Standardization needs to cover Mimi's typed state, tool/domain interfaces, event meanings, checkpoint schema/version, ownership and confirmation contracts regardless of runner. LangGraph is a candidate implementation of orchestration; it does not supply Mimi's permission decisions, source freshness, canonical encrypted records, atomic mutations or exactly-once external effects. Keep those in the existing server/journal boundaries and avoid a second operational truth.

The strongest counterargument is integration complexity: two persistence representations, app-owned journal and privacy constraints, version compatibility, additional dependencies and checkpoint growth may cost more than a small explicit state machine. A framework can reduce orchestration machinery while still requiring substantial product-specific glue. The present ref-only graph does not reconstruct its in-memory execution frame after restart, so its checkpoints currently support safe refusal rather than improved continuation.

Nearest viable alternative: retain the current runner behind the same typed domain/event contracts and modularize workflows incrementally. PydanticAI remains a separate runner candidate if typed model/tool contracts become the dominant problem; changing provider SDK at the same time would obscure attribution.

## Evidence needed for a long-term decision

| Axis | Meaningful probe | Current evidence |
|---|---|---|
| Workflow growth | Add a representative B16 workflow and a second synthetic domain using shared interfaces; compare modifications to existing modules and tests | NOT_RUN; no product domain added in this experiment |
| Recovery | Kill/restart between journal intent, dispatch, saved terminal and materialization; continue safely without duplicate dispatch or lost confirmation | Ref-only validation and unknown no-redispatch observed; full reconstruction/continuation NOT_MET |
| Human pause and UX | Pause at direction/confirmation, reconnect after a long absence, expose truthful progress/cancel/resume states | Existing app confirmation semantics exercised separately; graph-specific benefit UNVERIFIED |
| Longevity | Bound retained checkpoint rows/bytes, concurrency and connections; test a storage plateau with synthetic accelerated work | Finite footprint observed; retention requirement NOT_MET |
| Change and upgrades | Resume or safely halt a pending run across checkpoint/policy/runner version change; exercise fallback for new and old runs | Version/hash rejection covered; upgrade continuity NOT_RUN |
| Maintenance | Compare one concrete workflow change, fault diagnosis and dependency upgrade on both candidates | NOT_RUN; source line counts are insufficient |

Months or years with little maintenance should mean bounded storage, observable failures, recoverable state and controlled upgrades. Neither custom code nor a framework establishes those outcomes merely through its name. The framework docs themselves call out checkpoint growth and the need for retention.

## Next work and decision boundary

Finish the already approved integrated 066/067 QA, rollback evidence and exact Luna/high plus Gemini 3.8 Flash/high independent reviews. Present current implementation readiness separately from roadmap suitability. Preserve all receipts, including unmet retention/continuation requirements; no blanket PASS or automatic adoption.

Then propose a bounded second probe centered on one B16-shaped workflow, one synthetic alternate domain, real restart continuation, bounded retention and one schema/policy upgrade. Do not implement a speculative universal workflow platform or new production domains under the first probe. Adoption is justified if reusable workflow/recovery/maintenance gains outweigh measured integration and resource costs while authority/privacy remain correct. Reject or revise the integration if those gains do not materialize; a few dozen milliseconds alone is not a rejection criterion.
