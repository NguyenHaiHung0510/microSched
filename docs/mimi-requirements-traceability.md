# Mimi requirements-to-acceptance map

Status: INITIAL BASELINE / PREPARED; no new implementation or QA PASS. 2026-10-01. Task078 waits final night approval. Source: cur_docs/PTHTTM/btl/04-spec-hop-nhat-mimi.md, Owner context decisions D1–D9, current Owner interrogation/reset overrides. This map locates evidence; it does not replace product decisions or invent authority.

Columns below will be expanded with exact source section, implementation files/lines, runtime/config hashes, case IDs, receipts and truthful state. One requirement can require multiple cases; one journey can cover multiple requirements. Existing pilot evidence is not general Mimi acceptance.

| ID | User outcome / acceptance invariant | Source baseline | Current gap / required proof |
|---|---|---|---|
| CONV-01 | Natural Vietnamese conversation, accurate explanation of enabled capabilities | Tier1 + D2 + current Owner | Deterministic preview chat is inadequate; live whole-app semantic cases |
| READ-01 | Grounded authorized reads/count/filter, truthful coverage/provenance | Tier3 + D1/B16 | Typed tools exist; prove live demand-driven retrieval, zero write, independent DB oracle |
| PLAN-01 | Ordinary prose consultation; refinement/assent in conversation, no mandatory direction gate | D2 draft definition + latest Owner | Structured draft button/gate currently imposed; reconcile to conversational continuation |
| WRITE-01 | Clear requests and agreed plans produce exact editable frozen previews | Tier3/D6/NORMAL | Single Task create exists; general Task operations and multi-record coverage remain gaps |
| WRITE-02 | Confirm/reject/revision enforce source freshness, atomicity/idempotency and receipts | Tier3 | Keep deterministic/race proof and live UI semantic proof separate |
| CTX-01 | Useful context, sources and truthful usage/estimation visible | Tier4/D4 | Inspector exists partially; completeness and explanatory UX acceptance missing |
| CTX-02 | Auto/manual model compaction/rebuild preserves goals/constraints/pending work with provenance | Tier4 B-first | Extractive checkpoint is not semantic quality proof; typed model summary validation and replay needed |
| CFG-01 | Change model/effort/input budget; requested/effective/preflight outcome survives restart | Tier4/Tier6 | Config defaults and disabled selection endpoint do not satisfy controls |
| RUN-01 | Stop/pause/resume/cancel/reconcile, reconnect and process restart preserve canonical truth | Tier3/Tier7 | Read-loop graph restart nonzero checkpoint currently requires reconciliation; prove new integration |
| DATA-01 | STANDARD/PRIVATE authority, lock/lifecycle and no unauthorized source or egress | Tier2 | STANDARD local candidate cannot claim completed PRIVATE workflows; required current guards stay active |
| DOMAIN-01 | Tasks/Calendar/Notes/Trackers/Subscriptions integrated as capability-specific slices | Tier1/master plan | Record each domain's read/write enabled/off and missing outcome; do not equate prefix pilot with multi-domain product |
| FILE-01 | Accepted attachments have bounded parsing, source readers and retention | Tier4 | Open storage/parser gates remain explicit; no completed capability claim |
| MEM-01 | Approved scoped memory and retrieval obey lifecycle/source rules | Tier5 | Future capability remains visible; no auto memory implementation/adoption from this map |
| SKILL-01 | Discover/review/release certified skills; no runtime self-publish | Tier5 | Future capability; tooling/receipt gates remain |
| JOB-01 | Orbit/jobs/routing settings expose freshness, bounds, cost and recovery | Tier6 | No new automatic jobs besides Owner-approved chat heartbeat |
| QA-01 | Real-model Chrome full-app journeys, preliminary T3 analysis, T1 direct evidence and taste review | Tier7/current Owner + qa-framework3.E/7/8 | Previous six cases prefix-only + Playwright CLI; new spec/Chrome execution pending |
| OPS-01 | Finite resources, restart/retention/version upgrade/rollback and feedback-to-regression | Tier7 | Local evidence not multi-year operational guarantee; record concrete tested limits |

Evidence states: MISSING, IMPLEMENTED_NOT_VERIFIED, OFFLINE_PASS, LOCAL_SYNTHETIC_PASS, LOCAL_LIVE_PASS, OWNER_ACCEPTED; deferred/disabled scope must remain explicit. CI/device/production are separate columns, not implied by other states. No global DONE without required coverage.

Use before design/delegation, during implementation, before QA/acceptance and on any prompt/model/SDK migration. Reverse-check implementation with no requirement and requirements with no code/case. Owner-approved scope changes are recorded, never silently translated into fewer cases.
