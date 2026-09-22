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
- **D5 was reopened after correction, then approved below:** Owner rejects a blanket ban on provider
  conversation/response cache and expects production acceptance eval to reflect
  the actual daily STANDARD routing/cache/fallback topology. T1 must present a
  layered cache policy and production-faithful plus controlled-diagnostic eval
  lanes; the resulting policy is approved in the follow-up section below.
- **Two-surface preview direction approved:** side-chat is a quick, compact chat
  surface balancing power and space; Mimi workspace is the detailed inspection
  surface. Both must project the same canonical run/preview state. Workspace uses
  progressive disclosure rather than either hiding material change details or
  showing an unnecessarily complex technical dashboard by default.
- **Additional research approved:** tool granularity/bulk operations and the Mimi
  loop-engine/harness. Research must address large reads/writes (for example 100
  Tasks), explicit bulk preview, reasoning-versus-server authority, recovery and
  QA before T1 presents the final recommendation.

## Owner follow-up decisions and research constraints — 2026-09-22

- **D5 approved by “còn lại đồng ý”:** use layered cache policy and two evidence
  lanes. Daily STANDARD acceptance must reproduce the approved daily adaptive
  topology; controlled exact-pin/no-fallback/cache-declared lanes diagnose and
  compare rather than replace production-faithful acceptance. Exact providers,
  privacy promise and route allowlist remain a later route-card decision.
- **D6 base direction approved; revised generalization needs review:** query,
  selection snapshot, server materialization, whole/group atomic execution and no
  silent partial commit are accepted as the base. Owner requested deeper research
  before freezing the abstraction beyond the “100 Task rename” example.
- **D7 approved:** use the durable bounded state machine/worker in the current
  monolith, no external workflow engine now; side-chat and workspace project one
  canonical run/preview with different disclosure; expose application events and
  receipts, not raw hidden reasoning. The new storage-tier question refines where
  state/cache lives and is tracked separately as D9.
- **Execution-mode research added:** assess a NORMAL mode where every write preview
  is confirmed and an AUTO mode with bounded automatic writes. Do not assume a
  binary global toggle or treat provider automatic tool choice as authority.
- **Hard-case generalization rule:** a difficult example is a probe into the real
  product need, not permission to optimize only that example. Research must derive
  the broader workflow, present the strongest counterargument and nearest simpler
  alternative, then let Owner choose. For the “rename 100 Tasks” probe, include
  filter/facet/cluster/rank/classify, strategy per group, explicit coverage and
  grouped preview/execution.
- **Storage-tier research added:** inventory current Mimi use of RAM, Fly rootfs,
  browser storage and Neon; verify Fly lifecycle/capacity instead of assuming “8GB
  Docker”; recommend how to use RAM → disposable local storage → durable DB without
  turning ephemeral bytes into canonical state.
- Side-chat remains the compact projection; workspace remains the detailed,
  progressively disclosed review surface for these workflows.
- **Revised D6 approved:** use the explicit-operation fast path plus generalized
  query/aggregate → selection → plan candidate/draft → approved direction → server-
  materialized frozen preview path. Typed transform/mapping are bounded leaves;
  whole-batch/group atomicity is explicit and no silent per-item partial execution.
- **D8 approved:** NORMAL is the only write mode in the next package. A future
  AUTO-write is a scoped, expiring and revocable per-operation grant and cannot be
  piloted before the approved CAS/idempotency/receipt/reconcile/inverse gates.
- **D9 approved:** Neon remains canonical; RAM/rootfs/provider caches are
  discardable; add no Fly Volume/generic disk cache before measurement; use future
  encrypted object storage only for large durable artifacts; cold-start recovery
  and Neon idle/wake are acceptance evidence.
- **Owner-provided production observation at 09:58 2026-09-22:** `df -h` inside the
  current `microsched` Fly Machine showed `/` and `/.fly-upper-layer` at `7.8G`
  total, `37M` used and `7.4G` available. `/proc/meminfo` showed `MemTotal=469892
  kB`, `MemAvailable=259624 kB`, `SwapTotal=524284 kB`, `SwapFree=524284 kB`.
  This confirms current capacity at that instant; it does not change Fly rootfs
  restart/deploy durability semantics.

## Explicitly not yet approved

- No final system prompt. D1–D9 and the two-surface direction are approved; exact
  schemas, prompt text, route cards and measured limits remain package/eval work.
- No exact “small versus large” threshold.
- No live eval matrix, token budget, model list, repetitions, judge, or scoring formula.
- No runtime implementation, route adoption, deployment, or production enablement.
