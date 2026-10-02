# Mimi requirements-to-acceptance map

Status: OWNER_APPROVED_NIGHT / IMPLEMENTATION_CANDIDATE / FINAL_LIVE_QA_PENDING. 2026-10-02. Owner final grant expires noon02/10; no production delivery authorized. Source: cur_docs/PTHTTM/btl/04-spec-hop-nhat-mimi.md, Owner context decisions D1–D9, current Owner interrogation/reset overrides. This map locates evidence; it does not replace product decisions or invent authority.

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


## Candidate implementation and proof pointers — 078

These pointers describe the final local candidate at QA freeze, not acceptance of the entire seven-tier vision.

| Requirement | Implementation | Verification / remaining gate |
|---|---|---|
| CONV/PLAN | agent/policy/mimi-standard-v2.md; context_builder.py; openrouter.py native text plus typed function tools; MimiScreen.tsx/MimiMessageText.tsx | Offline context/wire tests; real Chrome count/preview initialsmoke; CONV-A/PLAN-A final live pending |
| READ | tools/registry.py/task_reads.py; loop.py/langgraph_runner.py; service.py encrypted read receipts and source rebind | Task-read/source-CAS PG tests; READ-A/B exact oracle + pagination live pending |
| WRITE | service.py frozen Task-create candidate/revision/confirmation; ChangeSetPreview in MimiScreen | PG source/stale/digest/atomicity/idempotency tests; ACTION-A/REVISION-A/B actual UI+DB pending. Edit/delete/bulk/otherdomain writes MISSING |
| CONFIG | route_config.py; models.py+0016; GET/PUT configuration; MimiConfiguration | Pure immutable binding + PG CAS/active receipt independence PASS; CONFIG-A live pending |
| CONTEXT | compaction.py; own versioned compaction prompt; service.py journalled encrypted checkpoint activation; actual manifest inspector | Shape/source/prior/activation-conflict RED→GREEN and PG restore; CONTEXT-A semantic faithfulness/longhistory pending |
| RUN/OPS | runtime pause signal; service.py new-run/freshlease reuse of known encrypted terminal/read receipt; graph_support/langgraph_runner appdurability callback | Pause/resume PG, graph reopen/unknown-no-redispatch PG PASS; RUN-A/B real browser/restart pending. Abandoned graph retention and version upgrade need explicit evidence, not framework assumptions |
| QA/UI | qa-mimi-078-real-conversation.md frozen families; Markdown+existing tokens/shadcn; real Chrome extension T3 preflight | Frontend182PASS/build/lint/audit0; T3 screenshots, semantic/taste rubric and T1 reconciliation pending |
| MEM/SKILL/JOB | Existing approved lifecycle remains; no new implicit memory/skills/jobs | Deferred/MISSING as stated in baseline. This night does not claim all7tiers implemented |

Private raw receipts and Owner grant remain local. Curated project map/spec locate actual proof; CI/device/production and Owner final usefulness/taste acceptance are separate and NOT_RUN here.


## Dated evidence update — 02/10 09:10

| Outcome | Source/runtime | Actual evidence | State / remaining proof |
|---|---|---|---|
| READ-B authorized pagination | native loop/graph wire; integration078c08f9a58 | Chrome phase2 synthesized53/48open/5completed; independent fixture oracle matches | LOCAL_LIVE_PASS for that fixture; arbitrary strict-prefix semantics not supported by contains filter |
| Task-create revision/rejection/confirmation | service frozen operation/source/digest/receipt; phase2 assetStqfP4lS | one meaningful Task after revised preview→reject→re-request→confirm; DB exact title/body/date/P2/3items+one receipt | LOCAL_LIVE evidence pending complete screenshot/taste and source-conflict gate; no edit/delete/bulk domain claim |
| Completed run/receipt restart | app journal and owned local API6440, readinessc08f9a58 | DB before/after one Task/receipt and61eligible; zero active runs at restart | LOCAL_SYNTHETIC completed-state proof; active live pause/recovery still pending |
| Compaction request/validation/orphan classification | versioned summary prompt; source8fca0e5 integratedc08f9a58 | independent finding closure; source-bound duplicate/supersession + helperintent/dispatched RED→GREEN21focusedPASS | OFFLINE/LOCAL_SYNTHETIC_PASS; actual model semantic continuity remains pending |
| UX and evidence capture | current full app desktop/mobile | actual T1 images show clipping; several saved JPEG thumbnails mislabeled PNG | FAIL/pending measurable repair and full-quality recapture; Owner taste acceptance absent |
| Budget | named-key T1-only adapter and cumulative ledger | finite guard RED→GREEN;09:03 conservative0.14714049465, unknown holds retained; key delta residual0.0003543540 | bounded accounting evidence; no exact reconciliation or exhaustion browserPASS claim |

These are additive dated checkpoints, not approval changes. The families still awaiting evidence remain required. Full seven-tier vision, physical device, CI and production are not accepted by these receipts.
