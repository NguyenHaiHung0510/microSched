# B24 — P1C-A implementation and gate ledger

Status: **LOCAL OFFLINE SUITES GREEN; FINAL REVIEW RECONCILIATION/CI PENDING — NO PROVIDER EGRESS / NO PR**

Recorded 2026-09-23 by T1 in `feat/065-mimi-p1c-context-loop`, forked from
`develop` `0b5d75f`; the later fetched `origin/develop` is `5957c59`. This is a working-branch receipt, not a claim about the current
remote branch, CI, production or Owner dogfood. Parallel brand/058 worktrees were not edited.

## Implemented locally (uncommitted)

- Exact B18 `mimi-standard-v1` policy loader and SHA, typed authority/context/source/budget
  manifest, versioned read tools and server-only execution of STANDARD Task query, aggregate and
  bounded batch inspect. Model never receives SQL, shell or auto-write authority.
- Bounded read loop with explicit terminal union, byte/turn/tool/deadline and no-progress stops;
  each iterative read contributes a provenance source to the next manifest. Provider adapter
  preserves existing P1 default when `MIMI_CONTEXT_V1_ENABLED=false`.
- Non-executable draft direction and frozen preview/confirmation seam; encrypted canonical
  checkpoint event, source-hash checks and transcript suffix; approved/pending draft content is
  rehydrated from its encrypted message, not inferred from an extractive summary.
- Startup orphan classification uses a transaction-scoped per-run advisory guard only in the new
  live feature-gated lane. A guard held by an old Machine prevents takeover; after crash, an
  already dispatched provider call becomes `unknown` and is never automatically resent. A
  provider-success terminal interrupted before delivery becomes a truthful halted run with a
  user-visible failure message, not a guessed preview or implicit redispatch. Its encrypted
  terminal payload remains in the call ledger. This is a deliberate fail-safe bound: exact
  candidate-to-preview rematerialization after process death is **NOT IMPLEMENTED**. Local
  disposable Postgres proves the guard/restart classifications; Neon/PgBouncer under long runs
  remains **UNVERIFIED**.
- Side-chat shows concise draft action; workspace inspector shows source coverage/omission,
  requested/effective route, checkpoint and provider-reported usage, without inventing missing
  cache/cost. A read-only capabilities endpoint reports the configured single route; model
  switching is not enabled.
- In-process SDK spike: retain the one-dispatch `httpx` OpenRouter adapter for this dogfood lane.
  OpenRouter Python SDK's public chat method has not shown exact parity for Mimi's `store` and
  `usage` request fields and its default retry behavior is unsuitable for this ledger. LiteLLM
  adds a larger normalization/retry surface. Neither package was installed or sent credentials.

## Observed local verification

- Ruff check/format on changed Python: **PASS** after the final backend edits recorded here.
- Root pre-commit hooks eventually **PASS**. Their first run caught one high-entropy-looking
  synthetic `OAUTH_STATE_SECRET` fixture string in a new PG test; it was replaced with a low-entropy
  test-only expression, the exact four PG decision tests reran **4 PASS**, and all seven hooks,
  including gitleaks, then passed. No real credential was used or disclosed.
- Full backend non-PG suite: **545 PASS, 1 skip, 232 PG deselected** on an explicit worktree
  temporary directory. The earlier sandbox temp-access errors were environment-only and did not
  recur under the current full-access run. The one skip is recorded, not counted as PASS.
- Disposable Postgres `pgvector/pgvector:pg18` at local `127.0.0.1:55438`, synthetic roles only:
  schema upgraded to head and `migration_drift=empty`; current full PG suite **232 PASS, 546
  non-PG deselected**, 19 deprecation warnings. A worker verification pass failed after it
  changed the disposable container's `postgres` role password, invalidating the known CI
  bootstrap URL; it also exceeded its read-only handoff by re-preparing this disposable DB.
  T1 identified `InvalidPasswordError` in the first failing test, restored the local synthetic
  password to its prior CI value, confirmed the DB was still `microsched_p1ca` at migration
  `0015`, and reran the full PG suite. The latest 232-PASS run includes six later decision/source
  cases. No Neon connection was made.
- A later exact-worktree full PG rerun on a fresh `microsched_p1ca_pg_ci` database also produced
  **232 PASS, 546 deselected, 19 warnings** after reproducing CI's complete local role and
  environment topology. Two exploratory runs on different throwaway databases failed for QA
  setup reasons: a missing `CI_MIGRATOR_PASSWORD` and, after that was supplied, residual Mimi
  conversations from an aborted browser case blocked the historical downgrade as designed;
  then a fresh DB with only the limited migrator role lacked CI's bootstrap privilege, and the
  first full run with the proper temporary bootstrap privilege had **230 PASS, 2 FAIL** because
  `CI_APP_DATABASE_URL` was not set. The final 232-PASS run set the synthetic app URL, mirrored
  bootstrap privilege only inside this disposable container, and restored the migrator role's
  `rolsuper=false` afterward. None of those earlier failures is reported as PASS or a product
  regression; the final result is a separate clean run, not a relabeling.
- P1C-specific PG proofs: fake-model chat → direct answer; bounded aggregate read → answer;
  strategic draft/approval → zero domain writes; explicit create → frozen preview → zero writes;
  API/SSE preview → exact confirmation → one real synthetic Task and idempotent receipt.
  Crash tests cover live guard, pre-dispatch, dispatched/unknown, encrypted succeeded terminal,
  and simultaneous startup once-only classification. Removing the advisory guard intentionally
  produced RED (`expected recovered=0, observed=1`); restoring it produced GREEN (4 PG cases).
- After independent QA coverage review, four more disposable-PG cases were added and passed in a
  focused run: STANDARD/private/deleted Task read boundaries, 50/51 pagination/aggregate/batch
  inspect, cursor/validation limits, Owner-timezone due-day, and encrypted checkpoint rehydration
  across sessions with tampered-digest rejection. Independent diff review found an unsigned Task
  page cursor could skip rows while claiming complete coverage; the cursor now uses a
  domain-separated HMAC key. Disabling its signature guard produced RED (`DID NOT RAISE
  ValueError` at the forged-cursor assertion); restoring it produced GREEN (4/4 focused PG).
  The prior **222-PASS** and **226-PASS** full PG receipts predate the later decision/source
  cases; the latest full run is the **232-PASS** result above.
- Targeted guard probes now have explicit RED→GREEN receipts for C01 (replace approved policy
  digest: `mimi_policy_digest_mismatch` → 1 focused PASS after restore), C02 (disable Task cursor
  HMAC: forged-cursor assertion `DID NOT RAISE ValueError` → 4 focused PG PASS), C06 (disable
  repeated-read stop: `AssistantText` rather than expected `Blocked` → 1 focused PASS), C10
  (disable active-checkpoint digest verification: tampered checkpoint `DID NOT RAISE
  HTTPException` → 1 focused PG PASS), and C11 (remove startup advisory guard: recovered count
  1 instead of 0 → 4 focused PG PASS). C08 preview CAS RED was `DID NOT RAISE HTTPException`
  for a stale expected digest, then 4 focused PG PASS after restoration. C09 source-freshness RED
  was a stale confirmation accepted with one new synthetic Task in the test transaction; after
  restoring the guard, 4 focused PG PASS. Each temporary source mutation was restored before
  continuing.
- A later focused C04/C05/C06 contract matrix added 16 deterministic unit cases: full terminal
  union/strict rejection, 1–6 bounded reads with sequential query pages and independent batched
  reads inside the four-turn lease, provenance/remaining budgets, and model timeout classified as
  `unknown` with no hidden retry. Its own run was 16/16; T1 reran the complete non-PG suite to the
  **545-PASS** result above.
- Source-version binding now includes Task rows obtained by iterative reads outside the initial
  prefetch. Confirmation compares those rows under a transaction-held PostgreSQL read lock before
  creating a Task. A separate read-only Luna review identified two additional gaps: aggregates
  lack per-Task freshness bindings, and re-reading the same Task could replace an earlier source
  version. P1C-A now allows aggregate-backed answers/drafts but blocks an aggregate-backed
  preview; conflicting versions within one run halt before candidate materialization. Their two
  disposable-PG tests PASS. Temporarily removing each guard produced the intended RED state
  `waiting_confirmation` instead of `halted`, then 2/2 GREEN after restoration. A second
  read-only delta review found no actionable issue. This deliberately does **not** claim support
  for an aggregate-grounded preview in P1C-A.
- Frontend ESLint, `tsc -b`, Vite build and Vitest: **PASS** after replay reset (160 Vitest tests).
  Build warned about
  a large JS chunk and deprecated `inlineDynamicImports`; neither is a runtime acceptance claim.
- The full frontend Playwright suite reached **272 PASS, 34 skip** after stabilizing two
  preexisting Calendar test baselines: under six-worker load, initial bounded fetches could
  arrive after the test started counting interval or move-picker requests. Both tests now wait
  for initial network quiescence and preserve their exact request-count/probe assertions. Two
  prior full runs had one different Calendar failure each (271 PASS/34 skip/1 FAIL); both exact
  cases passed alone, then the full suite passed. A final full rerun after the later Alt+Enter
  UI fix also yielded **272 PASS, 34 skip**. The P1C-A route-mocked Mimi matrix remains 6 PASS across
  1280×800 and 390×844; it is not live-model proof.
- New A2 integrated browser lane: the built SPA and real FastAPI server ran at loopback on the
  fresh disposable `microsched_p1ca_accept` PostgreSQL database with a deterministic in-process provider;
  it stripped inherited buyer/provider key variables before app import. **2 PASS** (desktop
  1280×800, mobile 390×844) for real local auth, API/SSE, direct answer, clarification, draft
  approval without write, preview→confirm→one Task/receipt, matching side-chat/workspace digest,
  iterative Task read, active run continuing across dock close/Task-tab switch/reload without a
  duplicate dispatch, outcome-unknown→reconcile without retry, retryable→explicit Resume,
  checkpoint visible in workspace inspector, elapsed real 30-second deadline→unknown, and
  Owner cancellation of a waiting run. Each case deleted only its exact linked synthetic
  conversation/Task ID and logged out. Before the final run the database had 0 synthetic Tasks,
  change sets, receipts, provider-call rows and transport calls; after both cases those DB counts
  were again 0, transport calls 24, with no waiting fake-provider run. Schema migration to 0015
  and `migration_drift=empty` preceded the run. The first probe found Alt+Enter did not insert a
  line (RED); MimiScreen now handles it (GREEN). A separate false test assumption—mutating a
  deadline from another transaction would change an in-flight ORM object—was discarded; the
  accepted deadline proof uses the minimum real 30-second lease. Earlier exploratory failed runs
  left synthetic records in a different disposable DB; they are not evidence for this clean lane.
  This is not Neon or live-model proof. A headless multi-tab attempt did not change
  `document.hasFocus()` on the old tab, so browser tab-unfocus stays **NOT RUN** for the A4 Chrome
  lane. Process-death exact preview rematerialization is deliberately outside P1C-A; fail-safe
  halted/no-redispatch behavior is the accepted local boundary. An independent read-only delta
  review found no P0/P1 implementation defect but flagged QA launcher isolation and explicit
  fake-transport key assertion; T1 added loopback-only HTTP middleware and an assertion that the
  fake transport sees only `synthetic-never-sent`. The integrated 2-case matrix reran PASS after
  those changes, with the same zero DB after-counts. Frozen-commit review remains pending.
- Chrome MCP/live local acceptance: **NOT RUN**, gated after D10 by B23. Transaction-pooler
  behavior on Neon: **UNVERIFIED**; local Postgres is not a substitute for that runtime proof.
- `MIMI_DEMO_1`, OpenRouter Stage 0, D10, MIDEX-mini and live dogfood: **NOT RUN**.

## B23 case-coverage caution

The green suite counts above do **not** imply all C01–C12 acceptance cells and their mandated
RED/GREEN evidence are complete. Current case mapping is:

| B23 cell | Deterministic status | Evidence / remaining boundary |
|---|---|---|
| C01–C06 | PASS for declared offline cases | Policy/context, Task read boundaries, strict terminal union, 1–6 reads, no-progress, timeout/unknown; C01/C02/C06 RED→GREEN observed. |
| C07–C09 | PASS for declared offline cases | Draft reject, exact preview revision CAS, first write only on confirm, duplicate/stale source and iterative-read binding; C08/C09 RED→GREEN observed. Aggregate-grounded preview is explicitly blocked. |
| C10 | PASS for declared offline cases | Encrypted checkpoint rehydrate/tamper and suffix/frontier/hash checks; C10 RED→GREEN observed. |
| C11 | PARTIAL | Dispatched-unknown, startup guard, once-only reconciliation and timeout covered; integrated browser proves active fake-provider run survives dock close, Task-tab switch and reload, plus unknown/reconcile, retryable/Resume, real deadline and Owner cancel without duplicate dispatch. Browser unfocus remains A4. Encrypted provider-success terminal is retained after process loss, but exact candidate rematerialization is not implemented; halted/no-redispatch is the P1C-A fail-safe. C11 guard RED→GREEN observed. |
| C12 | PARTIAL | Missing usage/cache/cost and route fields have deterministic/UI tests, but effective provider fields and real cost require later Stage 0/D10. No live-route claim. |

B23 remains **INCOMPLETE** as a whole until frozen-commit independent
review/CI receipts are reconciled. Real tab unfocus is assigned to A4 Chrome acceptance and
is not inferred from headless Chromium. The backend full-suite
PASS is not an A2 or live-acceptance substitute.
Independent diff review also noted that model text is intentionally buffered until its terminal
outcome is known (to avoid narrating an eventual tool call as a final answer). Run-stage and tool
events stream, but token-by-token final answer text does not. The reattachment UI now clears the
  old partial buffer when canonical event replay starts; targeted frontend verification is PASS.

## Remaining gates before a demo or merge

1. Freeze the candidate commit, perform final independent delta/ad-review against exact files,
   reconcile findings, open a PR into `develop` and verify CI. The local deterministic cases and
   RED/GREEN ledger are present; final commit/CI equivalence is not yet proven. No merge/deploy
   before the remaining B23 and Owner gates.
2. Preserve the approved crash-recovery bound: current implementation fails safely and visibly
   after a provider-success/process-loss seam, but does not recover the exact candidate as a
   preview. Do not label that stronger behavior PASS. Exact rematerialization would require a
   separately tested implementation and new scope; it is not silently added to P1C-A.
3. Before any Stage 0 or D10 egress, present the updated exact route/resource/cost/runbook packet
   and obtain Owner's explicit permission and resources. B19's earlier approval is not sufficient
   to waive this newer Owner gate. No automatic key read or inference.
4. After full D10 PASS, perform B23 live Chrome MCP acceptance with isolated synthetic context,
   then T1 final acceptance and Owner local dogfood. D10, MIDEX-mini, live Chrome and dogfood
   remain **NOT RUN**.

No commit, PR, merge, deploy or credential use is implied by this ledger.
