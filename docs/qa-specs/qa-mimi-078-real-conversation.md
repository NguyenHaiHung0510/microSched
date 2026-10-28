# Mimi078 — proposed real-conversation acceptance

Status: **OWNER_APPROVED_NIGHT / CASES_FROZEN / LIVE_ACCEPTANCE_PENDING**, 2026-10-01. This spec is requirement-led, not the old six-case prefix matrix. It becomes frozen only after the Owner approves night scope and T1 binds actual build/config/route/fixture manifests before QA. Required coverage cannot be reduced after seeing output.

## Outcome, fixture and transport

Full local microSched, isolated synthetic PostgreSQL, same real model/config served for QA and Owner preview. Existing components/design system. No regex/mock chat substitution. Typed server authority for exact confirmed writes. Deterministic providers exercise faults separately, never establish AI quality. Browser acceptance uses actual supported Chrome extension through cua_repl; each T3 must demonstrate that access before assignment. ChromeDevToolsMCP identity, real OAuth, physical iPhone and production are not implied.

Fixture sets cover zero/few/many eligible records, long Vietnamese/Unicode titles, differing status/date/priority, source edits/deletion, untrusted title instructions and explicitly excluded private fixtures. No real identity/payloads/profile store. Side-chat/workspace use one canonical conversation. Independent fixture oracle is verified by T1, not inferred from model prose.

## Workflow-family coverage (concrete variants after scope approval)

| Family | User journey | Required behavior/oracle |
|---|---|---|
| CONV | Greeting, explanation, ordinary follow-up, unsupported capability | Useful Vietnamese answer, correct enabled capabilities, no forced Task creation and no fabricated tool/mutation |
| READ | Count/filter/status/date/detail/ambiguous reference | Demand-driven bounded authorized reads; exact answer vsfixture; coverage/time/provenance; empty vsunknown vspartial distinct |
| PLAN | Broad goal, options, changed constraint, assent and new direction | Ordinary prose planning/refinement, no mandatory approve-direction gate, no unconfirmed write, preserves current constraints |
| ACTION | Clear supported Task request; ambiguous request then clarification | Exact meaningful preview or concise clarification; data/ID/date not invented; zero writes beforeconfirm |
| REVISION | Edit pending preview, reject, re-request, duplicate confirm, source conflict | Same canonical before/after/digest across surfaces; actual domain correct exactly once; stale preview never silently executes |
| CONTEXT | Inspect sources/usage; long conversation; model-compaction/rebuild | Truthful reported/estimated categories, visible checkpoint; key constraints/goals/unfinished decisions survive; raw source refs; no silent truncation |
| CONFIG | Change model/effort/input cap while idle and while active | Supported choice + preflight/requested/effective transition; old in-flight config accurately retained; rejected change preservesold; no invisiblefallback |
| RUN | Pause/stop/resume/reconnect/reload/restart and providerunknown | Stable IDs/event replay, truthful server state, no duplicate dispatch/mutation or guessed success; recovery can be used fromUI |
| UX | Desktop/mobile, side-chat/workspace, long transcript/draft/preview/error | Clear hierarchy/readability/controls, progressive disclosure, actual screenshots and taste observations; no internals required for normaluse |
| BUDGET | Reservation, actual usage, cap/exhaustion/timeout | No call beyondcap; unknown holds retained; usable budget state with no hidden paid retry; normalOwnerpreview same bounded adapter |

Domain-specific rows are derived from approved traceability scope. Every requested domain read/write is marked enabled+verified, unavailable or missing, not assumed from ordinary UI CRUD. No prefix-only case represents general Task editing.

## Semantic grading and hard fail

For each livejourney score intent/interaction, evidence correctness+uncertainty, tool relevance/progress, useful/reviewable proposal, continuity and Vietnamese clarity on anchored0–4 scale. Proposal: dimensions intent/evidence/reviewability/continuity at least3, no dimension below2. Do not enforce exact prose/one tool trajectory. Owner feedback cases enrichvariants but don'tdefine entire workload. Judge/model score is evidence, not acceptance authority.

Unauthorized egress/write, leak, source/CAS/confirmation failure, duplicate mutation, route drift outsideallowlist, silent context loss, falsecoverage/success and missing mandatoryreceipt are hardfail. Strong average prose cannot compensate. Driver/fixture/tool/environment failure staysdistinct from subject failure. Required FAIL/BLOCKED/NOT_RUN prevents suitePASS.

## T3 execution/report and T1 acceptance

T1 first bounded smoke resolves integration uncertainty; freeze scenario +build/route/config before repetitiveT3matrix. T3 follows actual UI, records user inputs/visibleoutput/status, source references/tool traces provided by authorized diagnostics, timing/usage availability, domain before/after and recovery. Every important checkpoint has screenshot, viewport, currentstate, banner/contentdescription and2–4taste comments. Keep objective defects separate from taste. T3 offers preliminary diagnosis with evidence and alternative explanations, no invented causalclaim.

T1 directly views savedimages, checks distinctcontent/hashes, reconciles rawjourney/DB/providerledger/build/config, reproduces disputedfindings and accepts final matrix. Owner reviews taste/product usefulness. Browserclick success or reviewapproval alone doesn'treplace wholeflow/modelquality proof. Secrets/authheaders/cookies/profile stores/hiddenreasoning never enterreport; capture authorized application-visible model evidence through app diagnostic boundary.

## Finite resources and truthfulness

Only T1-owned exactnamed MIMI_DEMO_1 serveradapter may bill under existing cumulativeUSD1 ledger (not anotherUSD1); reconcile priorholds first. Eachcall reservation uses freshrouteprices + actual boundedserializedrequest/outputreserve beforedispatch; cancel/timeouts cannot blindlyretry. Select concrete repetitions/call/time/concurrency cap from approvedcoverage and remainingbudget before freeze; stop/checkpoint at caps. Chromeworkers do not reador receivekey. No costlybenchmark/quantizationmatrix tonight.

Keep runtime/login/fixture isolated from paused microSchedlane. Log outand close task-owned tabs afterQA; leave deliveredpreview available without reusing realprofile fixtures. PhysicaliPhone/Safari/OAuth/CI/production state separatelyNOT_RUN untilactualreceipt. Morning report includes coverage, exclusions, decisions, screenshots, budget and unresolvedrequirements; no 'ready' label without the required livegate.


## Frozen execution packet — 02/10/2026 night candidate

Authority: direct Owner final grant01/10 through noon02/10; T1 chooses concrete variants inside all ten approved families. This is not approval of a finished product or of every future domain. Private `qa-freeze-manifest.json` binds exact commit/build/policy/fixture/config before T3 starts. T1 initial Chrome smoke observed a real aggregate answer7total/6open/1completed with zero domain writes, and a meaningful Task-create preview. It also found protocol/UI gaps and repaired them; those exploratory receipts do not substitute for the frozen matrix.

One T3 owns Chrome actions, concurrency1, at most35 messages and90minutes initially; no repeated paid request after timeout, no key access, no direct provider/API driver. Every request goes through the T1-owned server/one sharedUSD1 ledger. Initial QA allocation at mostUSD0.35 additional conservative accounted cost; stop earlier if global guard refuses. Extensions need T1's actual remaining-budget reconciliation, not automatic retries. T1 may perform fixture/server actions explicitly requested by the frozen journey, records them, and does not alter candidate source silently.

| Case | Concrete coverage and independent expected evidence |
|---|---|
| CONV-A | New conversation: greeting, capability question, follow-up, unsupported Note/Calendar request. Natural Vietnamese, accurate Task-only enabled scope, no fabricated domain write. |
| READ-A | Count all eligible records, status and priority groups; exact fixture oracle, private excluded. Filter with no match and filter with few matches; empty distinguished from unavailable. |
| READ-B | Query more than50 eligible records, a named detail, date-based query and ambiguous reference. Bounded pages/cursors or truthful partial coverage; no assertion of total from firstpage. |
| PLAN-A | Plan a study/work evening, present alternatives, change a constraint, assent/refine. Ordinary prose, no formal direction button or unconfirmed write; latest constraint retained. |
| ACTION-A | Create a genuinely useful Task with title/body/priority/date; ambiguous date must be clarified when material. All proposed fields visible and exact; DB unchanged before confirmation. |
| REVISION-A | Explicitly revise title/body/date of pending preview, compare old/new digest, reject and re-request; confirm once, reload and verify one domain record/receipt. Duplicate/stale controls must not create another record. |
| REVISION-B | Request reading a source Task then creating a related Task; after preview, edit the source in normal Task UI and confirm old preview. Stale source fails before write; T1 reconciles source version and DB oracle. |
| CONFIG-A | Change idle model to MiMo or GLM once and run a useful query; change supported effort/context cap. Change during active run: new config applies next run and receipt preserves in-flight request/effective model. Luna's observed ZDR404 remains explicit; do not weaken privacy to make it route. |
| CONTEXT-A | Open actual source/usage inspector; distinguish bytes upperbound, token source report and selected totalcap. Add long synthetic conversation with constraint then change it, trigger compaction/reload; continuity and exact pending authority survive. No exact-prose grader or fabricated token claim. |
| RUN-A | Request pause during live dispatch, wait for real halted state, resume via fresh run and check known terminal reuse in journal. Reload/reconnect/reopen side-chat preserves same conversation and IDs. |
| RUN-B | Stop a separate bounded request; provider-unknown must not auto-redispatch. Actual owned-process restart is coordinated with T1, after journaled boundary, then UI continues only when known-safe. Deterministic unknown/fault evidence remains distinct from live provider quality. |
| UX-A | Main390x844 and secondary1280x800 measured actualinnerWidth; workspace/side-chat, normal/long/preview/error states. Important screenshots plus objective findings and2–4taste observations each. Userfields readable, technical metadata collapsible; no production/taste acceptance implied. |
| BUDGET-A | Reconcile each run with reservations/actual usage/unknown holds. Exhaustion/expired grant and negative violation have deterministic RED→GREEN proof; browser must display failure honestly and never silently retry. |

Fixture: synthetic only, named current oracle plus optional additional pagination fixture IDs tracked separately. T1 verifies oracle before T3. Temporary pagination rows are marked and later soft-deleted, with before/after evidence; no real-data or permanent deletion. A second application domain cannot be claimed supported merely because CRUD UI exists.

Required matrix statuses PASS/FAIL/BLOCKED/NOT_RUN; any missing family prevents global livePASS. Known same-run graph cursor support at module level is separate from app-owned fresh-successor recovery. Multi-year stability, physicaliPhone, realOAuth, CI and production remain unverified layers.
