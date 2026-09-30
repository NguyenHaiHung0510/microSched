# 068 — Mimi workflow lifecycle probe

Status: CONTRACT_READY; implementation NOT_RUN.
Authority: Owner approved second probe with “duyệt, tiếp tục” on 2026-09-30; subsequently authorized this same chat to continue overnight via scheduled wake-ups until completion. T1 owns integration and acceptance; architecture adoption remains an Owner decision.
Baseline: 066 closeout 378e77fa97eb707119b1676a7dfe138b438a3793; isolated branch feat/068-mimi-workflow-lifecycle-probe.

## Question and outcome

Does LangGraph materially improve development, diagnosis, recovery and user experience for Mimi's multi-step, multi-domain, long-lived workflows enough to justify its dependency and operational costs? First probe's small fake-provider latency measurement cannot answer this. Deliver a runnable local synthetic comparison, raw receipts, independent review and a Vietnamese recommendation with the strongest counterargument and nearest alternative.

## Frozen scope

- A B16-shaped workflow: query → frozen selection/source versions → grouping/strategy → conversational draft → Owner direction pause → server materialization → grouped frozen preview → exact confirmation pause → atomic execute/receipt/reconcile.
- Two synthetic domains (task-like records and note-like records) sharing typed workflow interfaces and stage contracts. The second domain is a fixture, not a production Notes rollout.
- Compare an explicit current-style state machine and actual LangGraph node scheduling using the same handlers, provider fake, authority rules and storage contracts. No wrapper around the old while-loop presented as graph execution.
- Real process termination and fresh-process continuation at direction/confirmation and selected persistence boundaries. Unknown dispatched provider calls halt for reconcile; saved terminals may be reused without redispatch. Node replay after an interrupt must not replay side effects.
- PostgreSQL remains the sole durable truth. Sensitive synthetic workflow content uses existing application crypto; checkpoints contain references/control metadata. No SQLite workflow store, copied real data or secrets.
- Retention/admission bounds, abandoned active runs and terminal pruning; one compatible persisted-state version upgrade and an incompatible-policy stop/re-preview. No silently migrated confirmations.
- Compare identical observable outcomes, call/write counts, timing distributions, checkpoint/storage growth, recovery UX and actual implementation/diagnosis effort. Report prototype-only inferences explicitly.

## Finite resources and safety

Local-only experimental entry point and dedicated database named microsched_p1ca_068* on loopback. Explicit setup only; no production Alembic migration, auto-DDL, Neon, live provider/key, deployment, adoption or merge.

Per run: at most 16 selected records, 8 fake model hops, 32 application events, 64 KiB serialized content frame and 120 seconds active execution excluding persisted Owner pauses. At most 8 retained active runs and 16 terminal runs per engine; an active quota overflow fails closed. Paused runs have an explicit 24-hour expiry and lose execution authority on expiry. Use an injected clock to exercise expiry without sleeping. Terminal cleanup removes exact probe-owned graph threads and subordinate data atomically where possible, with recoverable failure handling; never prune a still-authorized pending confirmation to satisfy a quota.

Measurement cohort: 40 completed runs per engine, alternating order and domains, plus at most 12 fault/restart/version cases. No recurring benchmark, production automation, parallel load or extrapolated years-of-operation guarantee. Report row/byte plateau separately: PostgreSQL allocation may retain a high-water mark after logical deletion.

Do not add a cron retention daemon. Bounded admission/completion cleanup or an explicit local command is sufficient for this probe. Document the remaining production scheduler/vacuum/upgrade obligations rather than implying automatic maintenance-free operation.

## Acceptance evidence

1. Both engines preserve exact confirmation, snapshot freshness, owner/generation binding and atomic receipts; no domain writes before exact confirmation.
2. Two domains run through the same orchestration without domain-specific runner branches.
3. Fresh process resumes a durably paused workflow and reuses saved fake-provider results; crash after dispatch before terminal save never blindly redispatches. Demonstrate actual process IDs/termination and record outcome.
4. New guards have fail-for-intended-violation then restored PASS evidence; retention preserves active fences and hard-bounds retained logical data under the finite cohort.
5. Compatible upgrade succeeds, incompatible policy/version or stale source invalidates execution authority and requires a new preview/confirmation.
6. Frozen diff receives proportional independent review. T1 reconciles all findings and inspects final Git status/diff; PASS is local probe acceptance, not architecture adoption.
7. Save runnable commands, limits, raw outputs, NOT_RUN boundaries and final advice. Full-app dogfood should reuse existing UI where integration is within scope; a CLI-only probe must be labeled as such and cannot claim browser UX acceptance.

## Work ownership and artifacts

T1 is the sole writer of this worktree. Separable evidence workers may write only their specifically granted private report files. Source contract/result remain in this branch; raw reports/receipts under C:/Users/os/.codex/visualizations/2026/09/30/01a0f1d8-b288-7012-8bb0-36417caed247/probe2/.

Before repeating an operation after timeout, inspect disk/process/database state. Preserve all other worktrees, the 066 preview and unrelated root files. Do not use a shared benchmark database concurrently with UI journeys. Authority-expanding blockers await Owner; continue unaffected work and save an explicit blocker rather than silently reducing acceptance.
