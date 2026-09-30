# 066 — Mimi isolated LangGraph prototype

Status: **OWNER-APPROVED 2026-09-30 — IMPLEMENTATION / NO PROVIDER EGRESS**.

Closeout 2026-09-30: [local experiment result](2026-09-30-mimi-research/prototype-result.md). Frozen code945b324: final synthetic browser2/2PASS, separate backend/PG/frontend receipts and independent Luna+Gemini reviews retained. Overall adoption readiness NOT_PASS: retention NOT_MET and full reconstruction absent. Current runner stays the control; long-term LangGraph candidacy remains open. No merge/deploy/live inference in this grant.

Owner approved T1's steps 1–5 in the current chat: freeze baseline and curate research; isolated full LangGraph runner using current provider transport control; no-key contract/disposable-PG/full-app QA and measured comparison/rollback; narrow feedback and offline DecisionFacade/replay preparation; final independent Luna/high plus Gemini 3.8 Flash/high reviews. This authorizes an experiment, not adoption, live provider/key use, production migration or deployment. T1 owns integration and acceptance.

## Target and controls

Baseline: P1C-A head `1a10eb4` plus recovery commit `b5246bb` (metadata TransportError -> unknown; focused 38 PASS). PR239 is a baseline delivery candidate, not proof the prototype or live gates passed. Current runner and httpx adapter are control A. Cell B replaces operational orchestration with actual LangGraph nodes/edges/checkpoints while retaining provider wire, policy, context builder, tool schema, synthetic fixtures, UI and domain authority. No wrapper that simply calls the full old loop inside a graph node.

Canonical transcript/privacy/source freshness/frozen preview/nonce/CAS/atomic receipt stay server-owned. One operational cursor; projections don't independently schedule. New config is local-only/default current. No model/provider product-route change, no hosted tracing/platform, Redis, worker service or cron. Dependency versions, graph pools and checkpoint retention must be bounded. Any requirement conflict is reported, not weakened.

## Acceptance and evidence

- Typed terminal union and all loop budgets/no-progress/read tools/context binding preserve B18/B23 meaning. Before confirmation zero domain writes; confirmation exactly one mutation/receipt.
- Every provider dispatch is journaled; unknown never auto-redispatched. Stable run/generation/step keys fence node replay. Terminal already saved is reused only after hash/decrypt/source validation. Exact rematerialization gain must be measured; baseline safe halt must not be relabeled as recovery.
- Durable graph checkpoint is encrypted/ref-only in disposable PostgreSQL; reject corrupt/foreign/version-mismatched state. No plaintext transcript/tool results in checkpoint metadata. Explicit local setup only; no production/startup schema creation or live downgrade.
- Control-vs-graph negative/fault cases: read/clarify/draft/preview/revision/confirm, stale source, repetition, deadline/cap, partial stream, unknown, cancel, process interruption, reload/event cursor and rollback. New safety guards require intended RED -> restored GREEN receipts.
- Full local app uses existing components and synthetic STANDARD fixture with real API/SSE/PG plus fake provider injected into actual graph seam. Prove no buyer key or provider egress. Desktop1280x800 and mobile390x844 are distinct from physical device/live quality.
- Measure full-app startup/RSS/cgroup peak/OOM/headroom under Linux Python3.14 and 512MB, DB writes/pools, operational glue removed/added, stable-state recovery timing and equivalent scenario outcomes. Finite discovery samples (3 cold starts/20 conversations maximum initially) are leak/footprint checks, not production statistics.
- Rollback for new runs uses current runner; existing experimental runs retain runner version or halt safely. No speculative state conversion or replay. No worktree/unique-work cleanup implied.

Required closeout: exact SHA/diff/status; dependency/fixture/policy hashes; raw dated commands/exits; PASS/FAIL/NOT_RUN per layer; consolidated findings from two independent final-target reviews (Luna/high then Gemini3.8Flash/high), T1 reconciliation; recommendation retain/reject/adopt for Owner. Reviews do not substitute tests or Owner's reserved architecture adoption decision. No merge/deploy in this experiment grant.

## Parallel slice and next gate

[067](067-mimi-feedback-replay.md) owns feedback/replay preparation separately; integrate after both writers finish. [Research decisions](2026-09-30-mimi-research/decisions.md) record the accepted shortlist and hypotheses. D10 route qualification, MIDEX-mini comparison and future MIDEX remain distinct. GLM B19 pin stays unchanged; next live resource/spend plan requires Owner approval before any provider request/key.

See B18/B23/B24 under `2026-09-22-research-mimi-context`, `docs/qa-agent-framework.md`, `docs/qa-framework.md`, `docs/ui-brief.md`. Dated old receipts are historical evidence, not current runtime.
