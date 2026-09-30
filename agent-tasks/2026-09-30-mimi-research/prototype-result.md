# Mimi local prototype result — 2026-09-30

Status: **LOCAL EXPERIMENT RECORDED; SCRIPTED INTEGRATION PASS; ADOPTION NOT_READY.** T1 accepts the recorded local evidence and repaired feedback behavior within its tested scope. Overall 066 acceptance is not PASS: checkpoint retention remains NOT_MET and full restart continuation is not implemented. This is an experimental result, not approval to ship the runner.

Frozen code: `945b324159579b30470793d37b0aa6216349c437`, baseline `b5246bbd39f997e46e6e53368802491937429e3f`. Subsequent closeout commit changes documentation only. Worktrees 065/066/067 and unique work are retained; no merge, deployment, live model inference or Neon operation in this experiment.

## Recommendation

Continue investing in LangGraph as a roadmap candidate for multi-domain, B16-shaped workflows. Keep the current runner as the operating control until the candidate proves safe continuation, finite storage and reusable workflow development. Do not reject the framework based on the first small fake-provider latency comparison. See [lifecycle assessment](lifecycle-assessment.md) for the corrected reasoning, strongest counterargument and nearest alternative.

The useful delivered preparation is separate: answer/run/call/receipt feedback, server-side target membership, encryption/idempotency, truthful cancellation handling, and a bounded manual synthetic replay/DecisionFacade contract. No real Jev quality claim or automatic new model hop is introduced. Provider transport remains httpx; an SDK migration was not mixed into the runner experiment.

## Verified layers

| Layer | Observed result | Limit |
|---|---|---|
| Backend without PostgreSQL | 576 passed, 1 skipped, 233 deselected | PG is a separate lane; not a whole-suite PASS |
| Focused Mimi PostgreSQL | 16 passed; separate graph persistence test 1 passed | Disposable PG18.6, schema0015; not the entire repository PG suite |
| Final frontend tests | 23 files / 168 passed | Final code target; no physical device claim |
| Build / lint / hooks | Frontend build, Apple/PWA guards, targeted ESLint, backend Ruff and commit hooks passed | Local checks; no final-candidate GitHub CI or production claim |
| Feedback API with real PostgreSQL | 10 owning targets accepted, 10 cross-conversation404, malformed/absent404; same client gives one identity, changed content409; 10 ciphertext rows/plaintext absent | Deterministic synthetic ASGI cohort, five target kinds; exact generated rows cleaned |
| Fresh-process graph fencing | First PID dispatched once and ended unknown; second PID refused continuation with zero dispatch; reference-only checkpoint and exact thread cleanup | Safe refusal, not full continuation or full service-kill recovery |
| Current runner fallback | Actual API current-v1, one fake dispatch, zero domain/checkpoint delta, logout204 | New-run fallback; no conversion of old graph runs |
| Final full app browser | Desktop1280×800 and mobile390×844: 2 passed, one worker, zero retries; exact fixture cleanup200 and logout204 on both | Actual API/SSE/PG with fake provider; emulated Chromium, no semantic quality/device proof |
| Independent review | Luna/high and exact Gemini3.8Flash/high on the first frozen code; both independently reviewed the two-file final label delta | Review evidence is reconciled by T1; retention blocker remains open |

Final browser journey preserved readonly → clarify/draft/direction → preview/confirm/receipt → authorized read → side-chat/reload slow run → unknown/reconcile → retryable/resume → deadline/cancel. Additions verified answer feedback without a receipt, run/call feedback on cancelled+unknown, duplicate/conflict behavior, persisted target consistency across surfaces, absence of a stale cancel action/pending panel, and continued Reconcile affordance. Unsaved drafts are instance-local, not synchronized across surfaces.

Screenshots are supporting scroll-position captures. They do not establish comprehensive visual acceptance of every nested-scroll state or feedback control. Feedback failure/retry rendering lacks a frozen browser error-injection seam and remains NOT_RUN; focused binding/presentation tests are separate evidence. Per-run journal/checkpoint metadata for every browser-created run was not separately archived before exact fixture cleanup; graph route was verified in T1's first actual API smoke and dedicated PG tests. Do not expand that evidence into an all-run forensic claim.

## Failures and reconciliation

All earlier failures and raw receipts were retained privately; none was converted into PASS by changing a product guard.

- Initial private API duplicate test omitted Origin/fetch metadata: actual403 `mimi_cross_site_forbidden`, while browser feedback save201. Correcting only the private request gave retry201 and conflict409.
- Actual UI defect: two per-run attempt1 calls had identical unknown labels. The repair adds run generation and conversation call ordinal while preserving target IDs. New regression failed for uniqueness before the repair and passed afterward; both independent delta reviews found no new finding.
- Interrupted matrix left one exact receipt-linked synthetic Task. T1 verified its provenance and removed only that Task/conversation through the existing guarded helper. The private script also compared one conversation's receipts against the global DB count; correction asserts zero receipts for the fresh conversation while retaining the separate global no-write check. The final unchanged product candidate passed both viewports.
- Windows Uvicorn loop-factory and optional Linux libpq packaging problems were repaired with focused evidence. Permission-review timeouts and sandbox process-launch failures were execution constraints; bounded successful retries are retained separately.

Luna L1 / Gemini F01 (retention) remain **OPEN / NOT_MET**. Full reconstruction/continuation remains an explicit implementation limit; neither framework capability nor the current checkpoint cursor proves it. Integrated feedback evidence gaps raised in the first reviews were closed by actual PG/browser receipts. Reviewer suggestions do not add an unapproved cron, privacy policy, storage authority or product domain.

## Footprint interpretation

Earlier graph-only Linux snapshot: 20 synthetic conversations and25 dispatches in each cell, no OOM at512MiB/1CPU. Mean turn53.054ms control versus97.572ms graph; warm mean50.86 versus73.09ms. End RSS126.7 versus164.7MiB. Graph produced70 checkpoints/340 writes. These measurements precede final feedback integration; they are discovery samples, not final-build capacity, live latency or maintenance statistics. Similar cgroup peaks do not establish process-RAM parity.

No measured framework-specific UX/recovery/maintenance gain yet offsets that overhead. This is a missing benefit demonstration, not evidence that a standard framework cannot help the broader roadmap.

## Next decision

The next meaningful probe should cover one B16-shaped multi-step workflow, an alternate synthetic domain sharing interfaces, real restart continuation across saved provider results and confirmation pauses, finite retention/storage plateau, and one checkpoint/policy upgrade. Compare the actual changes needed in the current runner and graph, progress responsiveness and time to a correct result. Freeze finite synthetic work and resource caps before implementation; no new production domain or live inference is implied by this proposal.

Raw research, worker reports, commands/exits, scheduler dispatch/terminal receipts, failure traces and final screenshots remain in the private task artifact archive. The repository retains this curated result, source ledger, lifecycle assessment and task contracts. D10, MIDEX-mini, later MIDEX, live Jev, physical iPhone, production and multi-month operation remain separate NOT_RUN gates. No champion model or architecture adoption is declared.
