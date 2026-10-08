# Mimi research decisions — 2026-09-30

Status: Owner-approved **local prototype/preparation scope**, not framework adoption or live inference approval.

## Direction

Try full LangGraph orchestration/checkpoint experiment with existing httpx provider adapter as control. Do not require OpenAI SDK migration first: it mixes the independent transport question with runner/recovery. PydanticAI full runner is nearest alternative for typed tools/messages/output; retaining current runner is valid if integration overhead exceeds observed gain. [066 prototype contract](../066-mimi-langgraph-prototype.md).

Owner clarified the decision horizon includes multiple domains/workflow shapes and months or years of operation with light maintenance. [Lifecycle assessment](lifecycle-assessment.md) separates this strategic choice from the first prototype's readiness: the small fake-provider latency comparison does not justify rejecting LangGraph. Current continuation/retention gaps remain explicit; reusable workflow, recovery, upgrade and UX gains require representative evidence.

LangGraph nodes/edges/state replace operational progression; server owns canonical transcript, privacy, source freshness, frozen preview/confirm and receipt. Framework replay is not exactly-once provider execution: consult call journal and stable keys before replay. No second execution truth or raw plaintext checkpoint. Measure 512MB full-app/PG overhead, net glue and recovery; no performance claim before receipts.

Provider client candidates remain httpx incumbent, OpenAI Python SDK through OpenRouter, official OpenRouter SDK and LiteLLM. SDK convenience is source-supported but full Mimi wire/stream/error/retry/usage/route/privacy parity is not measured. Pin actual package version and prove compatibility; mutable source constraints are not installed solver failures. No SDK adoption here.

## Decision models and feedback

Jev-family is an optional semantic harness component, not main conversational model. Published examples support triage->code lookup->LLM prose, policy verification and moderation patterns; these are vendor tutorials/evals, not independent customer outcomes. Prioritize feedback/log/dogfood to discover actual Mimi failure classes, then freeze sanitized replay cases and compare rules, same-turn structured decision and Jev if a measured need exists.

Prepare offline synthetic replay/fake facade only in [067](../067-mimi-feedback-replay.md). Intent/draft/create/clarify shadow is first hypothesis; semantic critique/context relevance are later hypotheses. No confirmation/permissions/budget/date truth delegated to probabilities. No automatic Jev call every turn. External semantic evaluation remains separately approved inference even with synthetic data.

## Model-selection pipeline

Primary shortlist: GLM5.3Flash, GPT6Luna, DeepSeekV4.1Flash, Xiaomi MiMoV2.6Pro. Gemini/Qwen omitted from this round by Owner choice, not a universal model-quality verdict. GLM is B19 D10 candidate; effective current app model was not inspected. D10 qualifies route+Mimi version; MIDEX-mini compares shortlist on common Mimi tasks; later MIDEX broadens scope. No parallel redundant inference track or silent B19 substitution.

OpenRouter weekly rank measures platform token usage; AA Intelligence/cost/task concerns its benchmark/effort/price basis. Use those for discovery, then paired Vietnamese tasks and complete failed+successful run receipts for Mimi cost-per-correct-task. Exact provider/API/effort/tool/schema/cache/privacy/price card is the comparison unit. No champion established by this research.

## Research retention

This curated decision file, source ledger and task contracts are the repository payload. Raw reports/source fetch ledgers and local machine/tool receipts are retained in the task's private artifact archive; they are supporting research, not canonical domain policy. Older `2026-09-26-mimi-reuse-research` files retain dated research meaning. Update canonical briefs only after adoption/product decisions, not merely from a worker recommendation.

Dates/pricing/availability in source reports are 30/09 snapshots and require refresh at a future route gate. No key/provider call/production operation authorized here.
