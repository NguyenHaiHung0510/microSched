# B02 — Cross-provider prompt and context research

Status: COMPLETE — research only; no runtime change, key access, live call, or eval

Actual writer: T3 GPT-5.6 Luna, high effort
Research date: 2026-09-22 (Asia/Saigon)

## 1. Question and scope

This batch asks how Mimi should assemble model context and policy across OpenAI,
Google Gemini, OpenRouter, and provider-neutral adapters. It specifically covers:

- instruction hierarchy and where system/developer/user/tool-result content belongs;
- structured tool calls and the distinction between proposing a call and executing it;
- multi-turn state, replay, storage, truncation, and retention;
- prompt/context caching and provider stickiness;
- portability hazards when one logical Mimi run moves between APIs/providers;
- a research-grounded *shape* for a future Mimi system policy, without writing or
  approving the final prompt.

Out of scope: selecting the production model/provider, pricing approval, exact
small/large thresholds, a final system prompt, implementation, live experiments,
or an Owner acceptance decision.

## 2. Method and exact primary sources

Method: read current official documentation pages from the provider/API owners;
compare semantics rather than copying one provider's request format; record
access date and avoid treating a search result or a model's claimed behavior as
evidence. No API key was read and no provider request was made.

Sources (accessed 2026-09-22):

1. OpenAI, Chat Completions API reference, message roles and developer/system
   messages: https://platform.openai.com/docs/api-reference/chat/object
2. OpenAI, Responses streaming/API reference, previous response state, tools,
   `truncation`, usage and cached tokens:
   https://platform.openai.com/docs/api-reference/responses
3. OpenAI, data controls, application-state retention and ZDR behavior:
   https://platform.openai.com/docs/models/default-usage-policies-by-endpoint
4. Google AI for Developers, function calling (declaration, client execution,
   function response, modes): https://ai.google.dev/gemini-api/docs/function-calling
5. Google AI for Developers, tools and function-calling lifecycle:
   https://ai.google.dev/gemini-api/docs/tools
6. Google AI for Developers, Interactions API state, per-interaction parameters,
   storage and retention: https://ai.google.dev/gemini-api/docs/interactions-overview
7. Google AI for Developers, context caching:
   https://ai.google.dev/gemini-api/docs/caching
8. OpenRouter, prompt caching and provider sticky routing:
   https://openrouter.ai/docs/guides/best-practices/prompt-caching
9. OpenRouter, response caching and its ZDR limitation:
   https://openrouter.ai/docs/guides/features/response-caching
10. OpenRouter, ZDR/data-collection/provider controls:
    https://openrouter.ai/docs/guides/get-started/sovereign-ai
11. OpenRouter, guardrail hierarchy and provider/model allowlists:
    https://openrouter.ai/docs/guides/features/guardrails/overview

These are versioned web documents whose availability, model support, limits and
retention terms can change. The URLs and access date are the reproducibility
receipt; a future implementation must re-check them before pinning behavior.

## 3. Observed facts

### 3.1 Instruction hierarchy is not one portable wire contract

**FACT — OpenAI.** The Chat Completions reference distinguishes `developer` and
`system` messages from `user` and `assistant`. It says developer/system
instructions take precedence over user instructions; for newer reasoning models,
developer messages replace the older system-message usage. The Responses input
also treats a text input as equivalent to a developer-role instruction in the
documented input model. This is an API-specific representation, not a guarantee
that every provider accepts the same role set.

**FACT — Google.** Gemini exposes `system_instruction`/system instructions and
function declarations, but its contents/parts model and function-response
turns differ from OpenAI messages. The documented Interactions API lets a later
call reference `previous_interaction_id`; system instructions, tools and
generation configuration are interaction-scoped and must be re-specified on each
new interaction if they should continue to apply.

**FACT — OpenRouter.** OpenRouter provides a common API surface, routing and
provider controls, but its own documentation describes transformations and
provider-specific caching/routing behavior. A common endpoint does not make
provider semantics identical.

**INFERENCE.** Mimi needs a canonical internal message/policy IR. It must not
build its safety model by concatenating text into a provider-specific `system`
field and hoping the adapter preserves it.

### 3.2 Tool calls are proposals; the application executes them

**FACT — Google.** Function calling is explicitly a loop: declare a function,
send it to the model, extract the model's function call, execute the function in
the application, return the function response, and ask the model for a final or
next call. Google documents `AUTO` (model may call or answer), `ANY` (must call),
`NONE` (cannot call), and `VALIDATED` (schema-constrained call/answer behavior,
with restrictions depending on tool-combination mode).

**FACT — OpenAI.** Function tools have a JSON Schema and a `strict` option; the
API reference describes a tool as something the model may generate arguments for.
It does not turn generated arguments into authorization to mutate application
state.

**FACT — provider-neutral engineering boundary.** A model-generated call is
untrusted data. The deterministic server must validate the name, schema, scope,
entity versions, privacy boundary, lease and confirmation state before any write.
This is also the boundary required by the repository's QA-agent framework.

**INFERENCE.** Mimi's tool protocol should expose read tools and write-proposal
tools as separate capability classes. A typed `preview_change_set` proposal can
be returned to the UI without being executable; a separate server-side confirm
operation performs the write. Text such as “done” is never evidence of a write.

### 3.3 Multi-turn state has materially different storage semantics

**FACT — OpenAI.** Responses supports a `previous_response_id`/conversation
style of continuation. The reference documents `store`, `truncation` and usage
including cached tokens. With `truncation=auto`, the service may drop items from
the beginning when the input exceeds the context window; with disabled
truncation, the request fails instead. OpenAI's data-controls page says Responses
application state is retained by default for at least 30 days when stored, while
ZDR changes `store` to false; background mode is not ZDR-compatible because it
stores state for polling.

**FACT — Google.** Interactions can continue with `previous_interaction_id`,
but by default stores Interaction objects. The official page says paid-tier
interactions are retained for 55 days and free-tier interactions for 1 day, and
`store=false` opts into stateless behavior. In a stateless function-calling flow,
the client must resend the full history including model-generated tool steps
exactly as returned. System instructions/tools/generation config are not carried
forward merely by the previous interaction ID.

**FACT — OpenRouter.** OpenRouter's response cache is a separate request-level
cache. Its documentation says account-level ZDR disables response caching; a
per-request ZDR flag does not by itself determine response-cache eligibility.
Prompt caching at supported upstream providers is a distinct mechanism. This is
important: “provider ZDR” and “router does not retain a response” are not the
same claim.

**INFERENCE.** Mimi should own the canonical durable conversation/run ledger and
reconstruct provider input per turn. Provider-side state may be an optimization,
never the sole source of truth for conversation, preview, receipt or safety
state. Every adapter needs an explicit state mode (`stateless`, `provider_state`
with retention policy, or `router_state`) and a receipt of what was actually used.

### 3.4 Truncation must be explicit and safety-aware

**FACT.** OpenAI exposes an `auto` truncation behavior that can drop the oldest
items; the documented behavior is not an application-specific relevance policy.
Gemini's stateless mode places the responsibility for sending history on the
client; server-side Interactions state hides some history assembly but does not
carry all per-call policy. Provider-specific adapters may also apply their own
context limits.

**PROPOSAL (not approved).** Mimi should assemble a bounded context manifest before
egress with immutable safety/policy blocks first, then current user turn, then
selected conversation summaries and domain snapshots. If the budget cannot fit,
Mimi should surface `CONTEXT_LIMIT`/ask to compact or reduce scope, not silently
drop system/tool policy, pending confirmation, source-version data or the latest
user request. A provider may use its own truncation only when the manifest and
receipt make the behavior observable and the mandatory blocks are protected.

### 3.5 Caching is useful but changes portability and privacy assumptions

**FACT — OpenAI.** Responses usage can report input, output, reasoning and
cached-token details. OpenAI documents that truncation can reduce later cache
reuse. Data-controls documentation distinguishes application state from abuse
monitoring and states that extended prompt caching requires stored application
state, making it ineligible for ZDR.

**FACT — Google.** Gemini documents implicit context caching for current models,
with minimum token thresholds varying by model, and exposes cached-token usage.
Explicit caching is a separate Generate Content capability; the Interactions API
does not support manually-created explicit cache objects. Common prefixes and
short intervals improve implicit-cache chances.

**FACT — OpenRouter.** OpenRouter prompt caching may use provider sticky routing;
an explicit `session_id` can keep a multi-turn workflow on the same provider.
Its response cache is exact-request based, key-scoped, and disabled by account
level ZDR. A manual provider order takes precedence over sticky routing, and an
unavailable sticky provider may fall back.

**INFERENCE.** Cache hit rate cannot be treated as a correctness, privacy or cost
guarantee. Mimi must report cache source/type (`provider_prompt`, `router_response`,
or `none`), hit/miss and policy eligibility separately from token and billed-cost
data. A cache key must never include secret or private content merely to make a
hit likely.

## 4. Competing context architectures

### A — Provider-native state first

Pass a stable system policy once and use `previous_response_id`,
`previous_interaction_id`, or an OpenRouter session for later turns.

**Benefits:** less request assembly, potential cache gains, lower latency.

**Costs:** state/retention differs by provider; policy and tools may not carry
forward (Google); state may be stored against privacy requirements; switching
providers or recovering a failed call becomes difficult; hidden truncation may
remove safety-relevant history. Not suitable as Mimi's canonical ledger.

### B — Stateless canonical replay (provider-neutral baseline)

Mimi stores the conversation/run ledger and sends an explicitly assembled,
versioned context manifest on every turn; provider adapters translate the IR.

**Benefits:** reproducible, portable, clear privacy/retention boundary, easier
replay/reconcile and exact QA receipts.

**Costs:** repeated input tokens and possible cache misses; context builder and
budgeting are application responsibilities; adapters must preserve ordering and
tool-result pairing.

### C — Hybrid canonical replay + optional provider state (proposal)

Use B as source of truth; optionally use provider state only when the route's
retention, ZDR and replay contract are compatible. Keep a canonical manifest hash,
provider state ID, policy/tool hashes and explicit fallback to stateless replay.

**Benefits:** safety/portability of B with selective cache/latency benefits.

**Costs:** more adapter complexity and two state representations to reconcile;
must detect provider-state drift and rehydrate from canonical state.

**PROPOSAL.** C is the strongest candidate for Mimi, but it is not Owner-approved
and must be tested against the eventual route and privacy policy.

## 5. Proposed provider-neutral context layers (not a final prompt)

The future context builder should emit a manifest with ordered, typed blocks:

1. `policy.core`: identity, language, response behavior, uncertainty, no-claim
   rules, user-visible progress and draft/preview/confirm semantics.
2. `policy.security`: instruction hierarchy, prompt-injection handling, privacy
   class, tool authorization, no-secret/no-raw-credentials boundary.
3. `policy.interaction`: direct answer vs bounded read-only tools vs draft vs
   frozen preview; explicit rules for ambiguous or multi-record requests.
4. `tool.registry`: only tools granted for this run, each with JSON Schema,
   capability class, read/write flag and server validation contract.
5. `domain.snapshot`: deterministic, source-labelled microSched facts selected by
   the server (not arbitrary UI text; not a license to infer missing data).
6. `conversation.state`: bounded recent turns plus durable summaries/checkpoints,
   pending preview and unresolved clarification, with source/version IDs.
7. `user.turn`: the exact current request and attachments permitted by the lane.
8. `output.contract`: permitted terminal forms: text, clarification, or one typed
   proposal; no claim of mutation until a receipt exists.

This is a design vocabulary, not an approved system prompt. System/developer
messages should carry stable policy; tool schemas should carry callable contracts;
server code should enforce authority, filtering, version checks and mutation;
user messages should carry intent; tool results should be clearly typed,
source-labelled and treated as data rather than instructions.

## 6. Portability hazards and adapter requirements

| Hazard | Why it breaks portability | Adapter requirement |
|---|---|---|
| `system` vs `developer` | Role precedence and support vary | Canonical policy IR + capability map; fail closed if hierarchy cannot be preserved |
| Tool-choice modes | `AUTO/ANY/NONE/VALIDATED` and strict schemas differ | Normalize intent (`may_call`, `must_call`, `must_not_call`); validate server-side |
| Tool-result shape | OpenAI tool messages, Gemini function-response parts, other formats differ | Preserve call ID, name, args digest, result digest and order |
| Provider state IDs | IDs have provider-specific retention and replay semantics | Store IDs as hints; retain canonical ledger and rehydrate path |
| Hidden reasoning/thought steps | Some APIs return signatures/steps; others expose none | Never require raw chain-of-thought; preserve only provider-required opaque metadata |
| Truncation | Server may drop oldest context or simply reject | Preflight token budget; protect mandatory blocks; record actual behavior |
| Cache semantics | Prompt cache, response cache and router stickiness are different | Record cache kind, policy, hit/miss, TTL and source separately |
| Retention/ZDR | ZDR and router caching can conflict; defaults differ | Per-route privacy contract; reject incompatible state/cache mode before egress |
| Streaming/event shape | Delta events and terminal records differ | Normalize to Mimi event schema with monotonic sequence and durable replay |
| Model-specific parameters | `reasoning`, temperature, max output, schema support vary | Capability probe/card; don't silently drop a required parameter |
| Language behavior | Provider/model may default differently | Request Vietnamese in policy, but semantic QA must verify; language is not a hard safety gate alone |

## 7. What belongs where

**System/developer policy (stable, versioned):** role and scope, language default,
interaction modes, tool-use rules, draft/preview/confirmation semantics,
uncertainty/no-fabrication rules, formatting and user-facing progress. It should
not be the only enforcement point.

**Tool schema/description (typed capability):** name, arguments, required fields,
read/write classification, expected result shape, units and error semantics.
Descriptions should help selection but cannot grant authorization.

**Deterministic server gate:** allowlist and lease, auth/privacy, input bounds,
source/entity versions, preview digest/nonce/expiry, idempotency, transaction,
receipt, reconnect/reconcile and budget admission. This is authoritative.

**Dynamic context:** only server-selected, source-labelled domain data and
conversation state needed for the current turn. UI right-rail content should not
automatically enter context; the user/model must have an explicit scope.

**User turn:** exact user intent, with attachments/metadata only when the lane
allows them. Treat quoted documents, web pages and tool results as untrusted data;
they cannot override higher-level policy.

## 8. Recommendations (PROPOSAL, not approval)

1. Adopt a canonical, versioned context manifest and provider adapter IR before
   tuning a final system prompt.
2. Use the hybrid architecture C: canonical replay is mandatory; provider state and
   caching are optional optimizations behind a route privacy/capability contract.
3. Separate `answer`, `clarify`, `draft`, `preview`, `confirm` and `execute` as
   server-visible states. Keep draft conversational and preview frozen/typed.
4. Permit iterative tool loops, but cap turns/tool calls/deadline/budget in a
   server-issued lease. Read tools can be repeated; write operations stop at
   frozen preview until Owner confirmation.
5. Make “do it now” an input signal, not an authority bypass. The server still
   decides whether the request is small/clear enough for preview; broad or
   ambiguous work can return a draft/clarification first.
6. Require every request to carry policy/tool/context hashes and an admission
   decision; expose a sanitized context summary to the UI so Owner can inspect
   model input without exposing secrets.
7. Treat Vietnamese output, naturalness and model reasoning visibility as
   probabilistic QA criteria; do not claim provider parity from schema compliance.

## 9. Open questions for Owner/T1

- Which exact context blocks may be sent in STANDARD versus PRIVATE, and what is
  the Owner-approved ZDR/cache policy per route?
- Should Mimi always use canonical stateless replay initially, or enable hybrid
  provider state for an explicitly approved route?
- What thresholds make a request “small/clear,” “broad,” or “ambiguous”? What is
  the safe maximum read-tool loop/deadline for each mode?
- Which terminal forms are allowed for each user-facing interaction: direct text,
  clarification, draft, preview, or exactly one proposal?
- Is raw provider-published reasoning a display preference only, and which opaque
  signatures/metadata must be retained without exposing hidden chain-of-thought?
- What context-budget policy should warn, compact, ask the Owner, or fail closed?
- Which provider capabilities are mandatory for the first route card: streaming,
  strict tool schema, cached-token telemetry, provider ID, ZDR, and reconciliation?
- Which public metrics are allowed in future MIDEX output, given that route/provider
  and cost provenance may be private or estimated?

## 10. Evidence version and limits

Evidence is current as read on 2026-09-22, but provider documentation, API versions,
model support, retention defaults, cache pricing and ZDR eligibility can change.
Official documentation describes API contracts, not Mimi's semantic quality or
the actual behavior of a specific route under load. No live route was called, no
model was benchmarked, and no claim here establishes that any candidate model can
follow Mimi's Vietnamese, tool, privacy or preview rubric. B02 therefore supports
T1 synthesis and an Owner workshop; it does not authorize prompt deployment or
dogfood.

## 11. Receipt

- Files read: `AGENTS.md`, `agent-tasks/2026-09-22-research-mimi-context/README.md`,
  `00-owner-decisions.md`, `docs/qa-agent-framework.md`,
  `docs/project-guide.md`, `docs/harness-policy.md`.
- Network: official OpenAI, Google AI for Developers, Anthropic, and OpenRouter
  documentation only; no authenticated API call.
- Secret handling: `.env` and `MIMI_DEMO_1` value not read or printed.
- Runtime/eval: `NOT_RUN` by authorization; no code/runtime files changed.
- Verification: `git diff --check` and scope check are recorded by the parent
  coordinator after this write; this worker did not commit.
