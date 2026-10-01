# 078 — Mimi requirements-led local release candidate

Status: **PREPARED / WAITING_FINAL_OWNER_APPROVAL**. Date 2026-10-01 Asia/Saigon. Base c21b1893df50c8693f376b222f1d4ab81aea51b6. Branch feat/078-mimi-real-conversation. This file is a concrete proposed night contract, not permission to begin night implementation.

## Authority and current hold

Owner asked to record accepted decisions/lessons in memory and project documents, requested one GPT-6 Luna retrieval research, permitted coordination with thread 01a0f2c9-bf7c-7d90-8e78-43313b7cc4b8, and requested autonomous overnight implementation/QA with morning decision report. Latest direct message requires T1 to present the completed plan for FINAL approval before beginning the night shift. That latest instruction controls: prepare documents/research only; no implementation writer, paid dispatch or ACTIVE night automation until approval. One Luna/high research worker 01a0f808-c91d-78d1-ab7b-8b7aeb783eb3 is finishing existing read-only scope. Runtime metadata requested Luna/high; upstream provider attestation not claimed.

Other chat reports its own lane remains PAUSED_BY_OWNER, no resume grant from this message. Its reserved worktrees/runtimes/data are preserved. Coordination messages only for conflicts or material changes.

## Accepted Owner product/process clarifications

- Requirements-first traceability links outcomes, source decisions, design, implementation, runtime configuration, QA and receipts. General workflow families, not hardcoded Owner sentences, define coverage.
- Owner-facing dogfood is one complete full local microSched + Mimi experience using a real model and synthetic data. Deterministic fixtures remain a separate development lane, never a substitute for conversation-quality acceptance.
- Natural conversation and planning are model-led. Code keeps auth/privacy/schema/source/CAS/confirmation/budget/transaction authority. Regex greeting/intent fallback is not the product conversational path.
- T1 owns quality before dogfood. T3 follows the QA spec through actual browser interactions, captures meaningful screenshots and application-visible evidence, performs preliminary analysis; T1 directly examines images and deeper evidence, reconciles findings and reports limitations. Taste evidence is separate from Owner taste acceptance.
- No silent substitution of Chrome browser acceptance by Playwright-only or mock-only QA. Current tool is cua_repl Chrome extension, not attested legacy Chrome DevTools MCP. Verify each worker can use the supported browser surface before assigning journeys.
- Owner rejects continuing the fixed [planned] pilot as product direction. Preserve code/receipts; hide/disable pilot in new candidate rather than delete history.
- Exact prompt, effort, context/output/time bounds must not be promoted from code defaults to approved product choices. Model/effort/context inspection and changes, pause/resume and recovery remain real requirements.
- Owner says uncriticized recommendations are accepted. Annotated decisions still requiring deliberation (hard draft-direction gate, compaction design, precision costs, LangGraph adoption, SDK) are resolved only through the final plan/decision packet and subsequent scoped evidence.

## Proposed night outcome and work order

Deliver a normal full local app with dedicated synthetic PostgreSQL and real Mimi conversation: conversational answers, truthful supported-capability explanation, grounded reads/count/filter/analysis, ordinary prose planning and multi-turn corrections, frozen preview/confirm/reject/revise for supported Task actions, honest run/error/recovery controls and context/config visibility. Domain breadth must be reflected in the traceability matrix and capability UI; unsupported domain writes remain unavailable. Do not silently claim seven-tier product completion or manufacture a prefix-only acceptance.

1. Reconcile full requirements baseline from cur_docs/PTHTTM/btl/04-spec-hop-nhat-mimi.md and newer Owner overrides. Populate docs/mimi-requirements-traceability.md; identify scope and gaps before code. Keep all deferred requirements visible.
2. Freeze interaction and representative QA coverage. Ordinary prose plan/draft is conversational content; no mandatory approve-direction button for ordinary planning. Only exact executable preview confirmation is a hard write boundary. A structured planning workspace is optional future UX, not imposed on every turn.
3. Select one candidate route profile and SDK from current evidence. Owner leans OpenRouter Python SDK. Verify async/stream/tools/schema/provider/privacy/usage/cancel/retry parity first; do not silently substitute on failure. OpenAI SDK is Apache-2.0 and supports OpenRouter, but is an alternative rather than an automatic adoption. Do not attempt to remove HTTPX needed by Authlib.
4. Use LangGraph for orchestration in the local release candidate, if final plan approved. Preserve app-owned durable result ledger, domain transactions/receipts, source validation and no blind redispatch. Prototype runner cannot resume nonzero checkpoint safely yet; repair/prove continuation rather than claiming framework feature equals working integration. Keep previous Git source as rollback; no engine switch in owner-facing candidate.
5. Implement backend/integration in 078, UI in 079 with one writer each. Finish interfaces before delegation. Do not assign same checkout to multiple writers or launch repetitive QA before stable behavior/spec.
6. Run relevant deterministic/Postgres/safety checks. Then bounded live-model first smoke through full app; freeze target; delegate Chrome journeys with screenshots/semantic rubric. T1 diagnose/repair/reconcile, inspect actual screenshots and before/after DB outcomes.
7. Record decisions, exceptions, source/config/route manifests, PASS/FAIL/NOT_RUN and morning report. Keep detailed evidence local; curated decisions/traceability/spec in Git worktree, publication through later approved PR flow.

## Proposed model/config packet (not adopted yet)

MiMo v2.6 Pro via OpenRouter DeepInfra FP8 is the initial local candidate because it has an existing bounded Vietnamese whole-flow receipt and advertises all required tool-choice modes. This is not a model champion. GLM5.3Flash/GPT6Luna/DeepSeekV4.1Flash/MiMo remain the Owner shortlist; do not launch a new benchmark tonight. Refresh exact endpoint/privacy/price/capability before dispatch. Effort medium is a candidate only if exact route supports it; otherwise expose real supported behavior and stop/re-plan, not silently translate unknown support. Requested input starts at the documented 100k preset; output/reasoning reserve proposed 8192 and route-normalized fit must be verified. Bounds are a measured local profile, not general production constants. Preview TTL follows existing 10-minute product contract; separate per-call timeouts from total run deadline. T1 may tune bounded local profile after evidence and record the change for morning; hard budget/permissions do not expand.

## Resources and boundaries

- Proposed cadence: one heartbeat in THIS chat every hour after final approval, reuse mimi-068-ti-p-t-c-qua-m; no second wake/job. Proposal horizon 12:00 02/10 Asia/Saigon, checkpoint-only from 11:45; pause on completion, Owner dependency or horizon. Verify persisted next_run_at UTC/local before claiming ACTIVE schedule.
- Current other-account usage is not the whole Owner pool. Do not change login/accounts or consume reset credits. Each wake checks actual allowed usage and existing worker state, then checkpoint/return if unavailable; no retry loops.
- API8018, PG55478 proposed reservations, verify before use. Keep 073/8014 and other chat's 8003/4174/4178/55470/55471 intact. Do not share browser fixture/session between lanes. Docker: verify daemon; if unavailable require Owner to start per project rule rather than guessing.
- Paid budget remains the previous cumulative USD1.00 MIMI_DEMO_1 grant, not a fresh dollar. Prior conservative accounted USD0.07095643565 per 073 report requires fresh ledger reconciliation; do not release unknown holds. Only T1 reads exact named key in process. Workers never receive/read the key. Bounded server-side QA requests may use the T1-owned paid adapter after explicit route/budget reservation guard is verified. No secrets in prompt/log/commit/report. Account usage and ledger must reconcile, no blind timeout retry, preserve USD0.50 key buffer.
- No production deploy/merge, Neon create/delete/sync/restore/migration, real-data access/deletion, privacy/credential changes, unbounded jobs, Astra, external commitments or harness authority changes. LangGraph/SDK choices in local candidate do not auto-authorize production architecture adoption.
- Harness maintenance tonight: targeted read-only failure-chain diagnosis and small proposed checklist, not broad instruction rewrites/installations/cleanup. Product lane comes first.

## Acceptance and handoff

All designated release journeys must be covered in the frozen spec; no dropped failing cases or changing expected behavior after output. Verify same build/route/config actually served to Owner. Record meaningful model quality separately from provider transport and offline tests. Runtime controls shown in UI must work; missing capabilities cannot be labelled enabled. Morning report is brief plus links: decisions made under grant, implementation, QA scope/results, live URL, effective model/route, budget, unresolved decisions and production/device NOT_RUN.

If final gates are incomplete, leave a truthful candidate/checkpoint and report the missing gate; never hand over a deterministic stub as live Mimi. Documentation/prompt approval is distinct from working quality. Night delivery is an objective, not a guarantee obtained by weakening scope or acceptance.
