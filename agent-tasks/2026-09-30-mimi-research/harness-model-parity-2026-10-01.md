# Mimi: model language quality depends on the request contract

Date: 2026-10-01. Status: observed local synthetic evidence and T1 advice, not model ranking, default migration or architecture adoption. Private raw research and provider receipts remain saved locally; this edited note is the repository record.

## Conclusion and recommendation

The poor GLM draft observed in this pilot does not establish that GLM generally handles Vietnamese poorly. Mimi's harness had concrete defects: a draft prompt hardcoded two groups while the actual grouping could contain one, and the grouping schema accepted arbitrary strings instead of only selected Task IDs. These are application defects to fix before interpreting a model comparison. The separate MiMo natural-language draft candidate produced clear Vietnamese; it still needs task-specific scoring beyond this narrow pilot.

Keep HTTPX for the provider transport and LangGraph only in the approved local B16 pilot. Use structured output for decisions consumed by code, with enums for authorized IDs and server validation of the complete partition. Generate advisory Vietnamese prose with explicit domain context and bounded output. The server continues to own immutable preview, source freshness, permissions, confirmation and atomic writes. A model's prose never authorizes execution.

Nearest alternative: keep JSON-wrapped prose if an endpoint performs well with it, using a prompt and output budget verified on the same tasks. JSON itself is not inherently bad for Vietnamese. Current evidence does not prove that an SDK switch, LangGraph, or prose format alone caused the improvement.

## Observed evidence

| Observation | Interpretation and limits |
|---|---|
| GLM5.3Flash through OpenInference/fp4, low effort: a completed draft mixed Vietnamese and irrelevant English/foreign phrases. | REJECT for that task/route/request. It is not a verdict on the entire model family. |
| A matched GLM schema versus JSON-object pair completed only the schema arm; the second arm failed its usage preflight before paid dispatch. | INCOMPLETE; no causal format comparison. Do not rank or retry an ambiguous provider operation. |
| MiMo through DeepInfra/fp8: the earlier strict-schema draft reached exactly 1,600 characters and ended mid-clause; another draft repeated its ideas. | Language/UX REJECT. A schema ceiling may be a confound, not a proven cause. |
| A natural-language MiMo candidate returned three complete sentences, 241 characters, with the planned prefix and confirmation boundary. | Narrow language PASS. Prompt, format and token cap changed together, so this is candidate selection, not an isolated experiment. |
| During a real workflow, the old prompt requested two groups although the provider returned one. | Observed harness inconsistency. Bind the next prompt to the actual validated groups. |
| Another grouping response inserted `group_name_1` and `group_name_2` alongside IDs. | Server validation blocked execution. The request schema now enumerates the exact permitted IDs; server partition validation remains necessary. |
| A repaired request returned one group containing the two selected IDs and a complete, coherent Vietnamese draft. The run survived a stopped server and later completed exact confirmation with one receipt for two actual synthetic Tasks. | Narrow live workflow/restart continuation evidence. No general model champion, production reliability or autonomous operation acceptance. |

The pure request builder and regression tests live in `backend/app/agent/workflow_pilot_requests.py` and `backend/tests/test_mimi_workflow_pilot_requests.py`. They have no key, model selection or network dispatch. The paid local QA transport remains a private, finite helper. This change does not enable paid inference in the default application.

## What mature harnesses teach us

OpenCode documents provider-specific integrations, OpenRouter setup and custom OpenAI-compatible endpoints. A familiar model name does not guarantee identical provider, quantization, parameters or context. [Official provider documentation](https://opencode.ai/docs/providers/).

OpenRouter documents schema support at the endpoint level and warns that strict enforcement differs among providers. Use supported parameters and validate the result in the application rather than assuming strict JSON establishes semantic correctness. [Official structured-output documentation](https://openrouter.ai/docs/guides/features/structured-outputs).

The archived research also consulted official Hermes provider-routing and integration sources. They support inspecting serving and parameter differences, not a reproduced head-to-head quality advantage over Mimi. No external Codex plugin request path or real user session was inspected.

For a useful future comparison, hold model alias, upstream, quantization, prompt, reasoning effort, token allowance and history constant; compare serialized request manifests first. If parity is unavailable, label the comparison confounded. D10 and MIDEX-mini should judge the complete Mimi task, including tools, authority, failure recovery, total cost and latency.

## Boundaries and next decision

Real browser profiles, credentials and personal records were excluded. Paid QA was synthetic, T1-only, with a cumulative USD1 owner ceiling, reservations and unresolved holds. The two older uncertain calls remain held; they are not silently retried or released. Exact costs and raw returned text stay in private receipts.

Remaining before dogfood: finish the frozen browser error/recovery matrix, bind final source/build evidence, reconcile all review findings and present the retained local preview. Physical iPhone, CI and production are separate evidence layers; this note does not mark them PASS. Selecting the default model or adopting LangGraph broadly remains the Owner's decision.
