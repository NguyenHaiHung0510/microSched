# Owner decisions and research constraints

Date: 2026-09-22

## Approved

- Research the complete model-call context for Mimi, including system policy, dynamic context,
  tools, deterministic checks, provider behavior, and user-facing context controls.
- Use T3 researchers to gather independent evidence; T1 synthesizes only after presenting the
  evidence and working with Owner to elicit desired Mimi behavior.
- Use a dated, structured research folder. Agents save their batch results into assigned files.
- `MIMI_DEMO_1` is the approved external-model API key alias for later authorized experiments.
- After context work: T3 builds local dogfood; T1 writes/finalizes QA spec; Gemini 3.8 Flash
  executes multilayer QA including Chrome MCP; T1 audits; Owner dogfoods before acceptance.

## Owner product preference to research

- Owner currently leans toward an iterative agent loop.
- Mimi should be able to use bounded read tools to understand current microSched state.
- Draft and preview are distinct:
  - draft: conversational understanding/options/plan, not executable;
  - preview: frozen typed mutation set awaiting confirmation.
- Small, clear, explicit “do it now” requests may go directly to preview.
- Large, ambiguous, multi-record, or explicitly requested draft work should normally present a
  draft before preview.
- The final policy and thresholds must be research-based and Owner-approved.

## Owner workshop decisions — 2026-09-22

- **D1 approved:** mandatory server envelope plus bounded iterative read-tool loop;
  retain fixed server prefetch/one-call as a fast path and controlled baseline.
- **D2 approved:** adaptive interaction. Ordinary/read-only requests answer directly;
  missing material facts trigger clarification; broad, ambiguous, multi-domain or
  explicitly planning work produces a draft; a narrow, clear “do it now” request
  may proceed directly to preview. No fixed entity-count threshold is approved.
- **Draft meaning clarified:** a draft is an ordinary conversational reply that
  presents the agent's strategic understanding, options and proposed direction for
  Owner approval, analogous to T1 presenting a plan. It is not an executable or
  partially executable object. After the direction is approved, Mimi may construct
  an implementation-detailed frozen preview for separate confirmation.
- **D3 approved:** microSched owns the canonical transcript/context and can
  rehydrate it; provider state and cache are optional optimizations, never the sole
  source of truth. This decision does not prohibit privacy-compatible caching.
- **D4 approved:** progressive-disclosure context UX, receipt-backed model/effort
  and context status, advanced inspector, and visible recoverable compaction
  checkpoints. Exact thresholds remain measured/route-specific.
- **D5 remains open after correction:** Owner rejects a blanket ban on provider
  conversation/response cache and expects production acceptance eval to reflect
  the actual daily STANDARD routing/cache/fallback topology. T1 must present a
  layered cache policy and production-faithful plus controlled-diagnostic eval
  lanes for approval.
- **Two-surface preview direction approved:** side-chat is a quick, compact chat
  surface balancing power and space; Mimi workspace is the detailed inspection
  surface. Both must project the same canonical run/preview state. Workspace uses
  progressive disclosure rather than either hiding material change details or
  showing an unnecessarily complex technical dashboard by default.
- **Additional research approved:** tool granularity/bulk operations and the Mimi
  loop-engine/harness. Research must address large reads/writes (for example 100
  Tasks), explicit bulk preview, reasoning-versus-server authority, recovery and
  QA before T1 presents the final recommendation.

## Explicitly not yet approved

- No final system prompt. Context architecture D1–D4 is approved at direction
  level and the two-surface constraint is approved, but implementation detail and
  D5–D7 routing/cache/tool/loop policy remain open.
- No exact “small versus large” threshold.
- No live eval matrix, token budget, model list, repetitions, judge, or scoring formula.
- No runtime implementation, route adoption, deployment, or production enablement.
