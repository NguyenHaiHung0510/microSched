# 055 — Mimi P0 synthetic sandbox and contracts

Status: **P0 DELIVERED / MERGED / PRODUCTION VERIFIED (2026-09-14)**

> Executor/writer: T1 GPT-5.6 Sol/high, Economy · Owner grant: 2026-09-14 “còn lại đồng ý, thực thi” · Automation `mimi-p0-sol-handoff-once` · source task `01a05311-c272-7633-9ac0-5abdcf44c22e` · P0 merged/deployed; no real data/paid provider/P1 start.

## Delivery-closure startup — 2026-09-14

- Owner grant source: `dispatch-p0/p0-remediation-handoff.md`; executor may reconcile the eight P0 allegations, apply bounded corrections, verify, obtain independent delta review, and deliver through PR/exact-head CI/CAS merge. Grant ends at P0 delivery or an Owner-reserved blocker.
- Startup observed: clean `feat/055-mimi-p0-sandbox@b772e1c2a6e513527df7835e2a7c778e841730b5`; local `develop@6507a54d3149bab77e4e4381ee87f26a41969afd`; no known open PR. GitHub refresh initially blocked by sandbox proxy and the local `gh` keyring reporting an invalid token, so remote/PR facts remain UNVERIFIED until retried through an authorized network path.
- Writer check: Git status/worktree inventory showed this exact worktree clean and uniquely bound to the branch. System-wide command-line inventory was denied by Windows access control; no concurrent Git mutations were observed. Recheck status before edits/commit/publication.
- Topology: tightly coupled remediation stays with the single T1 writer. A fresh read-only T3 review will run only after the final candidate is frozen. No T2 contributor handoff is needed; no Astra route is invoked.
- Preliminary disposition: Docker-context exclusion, dotenv/host-environment isolation, exact container/port/volume identity, nested secret/hidden-reasoning rejection, bounded atomic review records, PID ownership, and final-candidate provenance are P0 closure work. Dynamic P1 rows are not silently deleted during P0 reset; an unowned-dependent preflight must fail closed. P1 runtime/provider/device/real-data gates remain NOT_RUN.

## Identity, grant and baseline

- Branch/worktree: `feat/055-mimi-p0-sandbox` at `C:/Users/os/Desktop/ai_eng_path/microsched/worktrees/055-mimi-p0-sandbox`.
- Refreshed base: `origin/develop@7806f4e9f75ef66110ae3d485cffd036d42d94c1`, fetched 2026-09-14; upstream commit timestamp 2026-09-09T18:10:24+07:00.
- Duplicate-writer inventory: no Mimi P0 task/branch/worktree/open PR existed before creation. Existing dirty root (`.gitignore`, Task031/doc drafts/backup script) and all unrelated worktrees were preserved.
- Canonical task/progress path: this file. Evidence directory: `agent-tasks/task-055/`. Contract/seam map: `docs/mimi-p0-contracts.md`.
- Frozen application/test candidate: `1c7af66582d574f43ab34493d4e3d8af856dbb23`; this supersedes remediation candidate `572209231f833a0a5c6d9e4066e6ad2204aace85` after independent review found a serialized-secret blocker. Any later commit is receipt-only unless this line is explicitly revised with new verification.
- Source authority read: dispatcher `dispatch-p0/launch.md`, package08, scoped current04 §1–4/§7A–9, 06/07, repo AGENTS/harness-policy/project-guide and relevant architecture/schema/auth/QA briefs. Current grant superseded historical proposed/no-grant lines.

## Delivered P0 artifacts

1. Guarded runner `backend/scripts/mimi_sandbox.py`: exact labeled local pgvector/Postgres container, local-only URLs, migration/start/status/seed/reset/verify/stop; no broad cleanup, remote override or secret output.
2. Versioned fixture `mimi-p0.v1`: J01–J06 source/case manifest; Task/Note/Calendar/Tracker/Subscription synthetic rows, stable clock/timezone, intentional overlap, stale version, missing/partial capture, expired/revoked lease and injection-shaped document data.
3. P1 contracts: bounded server-issued execution lease, frozen change-set, evidence completeness/full application-visible payload, stable-client feedback envelope and lifecycle states.
4. Durable encrypted local review store separate from disposable fixture rows. Retry is idempotent; conflict is explicit; acknowledged unresolved feedback and full bundle survive store reopen and fixture reseed/reset. No auth header/cookie/token/provider hidden reasoning field is accepted.
5. Fake clock/provider/barrier with deterministic failure and in-flight delay smoke.
6. Detailed P1 endpoint-purpose/authority/error/state/fault map, six seam owners/test points, and pre-live retention/cap/warning/export decision packet in `docs/mimi-p0-contracts.md`.

## Observed receipts

Raw concise receipts: `agent-tasks/task-055/terminal-receipt.md`.

- Docker Desktop 29.7.2 observed after Owner started it.
- Fresh local container/migration ran `0001 → 0013`; seed verified exact counts: Task 3, Note 2, Calendar source/event 1/1, private day annotation 1, Tracker group/tracker 2/3, Subscription 1, Entry 5.
- Repeat start was idempotent. Before reset and after explicit reset/reseed, `counts_match=true`, fixture SHA-256 `39661bc7b78d88b310257077e75834613ffc7e968062524022c0691b2f5003cc`, `review_store_preserved=true`.
- Real durable check before/after reset and again after a full stop/start: `review_bundle_roundtrip=true`, `feedback_acknowledged=true`, `feedback_unresolved=true`.
- Full local app: backend `/api/readyz` returned `db=up` and exact baseline commit `7806f4e9f75ef66110ae3d485cffd036d42d94c1`; frontend ready on `127.0.0.1:5173`.
- Isolated Playwright CLI dev-session displayed seeded STANDARD Note “Kế hoạch tuần synthetic”, Tracker “Chi phí AI synthetic” / “Đọc sách synthetic”, group/subscription counts, and Calendar UI. PRIVATE fixtures stayed hidden while locked. Logged out and browser session closed. The one console 401 occurred after explicit logout when the public page checked `/api/me`; not a seeded-app failure.
- Focused tests: 19 passed. Ruff lint and formatter were run; final receipt below supersedes the earlier formatter-not-yet-applied result.
- Full backend non-PG regression: 459 passed, 211 deselected, one existing Starlette/httpx deprecation warning. Final runner start → stop → start → verify → stop passed; app and container are stopped, while local volume/evidence are retained.
- Resolved verification finding: the first Windows stop attempt tracked transient venv/npm launcher PIDs; their child listeners briefly survived and restart correctly refused unrecorded ports. Runner now resolves/stores exact listener PIDs and uses a bounded graceful-then-force stop. Final two-cycle receipt is green.

## Status boundaries and next safe action

- P0 is merged and ordinarily deployed. It adds no runtime Agent router/provider/orchestrator, production schema, real capture, migration beyond existing migrations, Neon/R2 operation, paid model call, recurring automation or P1 implementation.
- Production, CI, production-image, real OAuth/profile, physical iPhone/Safari, live-provider portability, combined 512 MB resource tests, and all Mimi P1+ acceptance IDs: **NOT_RUN**.
- Existing `npm ci` audit reported 6 dependency vulnerabilities (3 moderate, 3 high); no dependency changes were authorized or made. This is not a P0 acceptance claim.
- Before any live/full evidence capture, Owner decision is still required for exact TTL, per-run/per-chat/global caps, warning threshold/UX, verified export/extension, deletion mapping, key isolation and backup-aging truth. P0 enabled none of these.
- Safe next action: Owner reviews the decision packet and proposed detailed P1 Task STANDARD read/create slice from observed seams. Do not auto-start P1.
- Feedback review is not usable product functionality yet, so do **not** schedule the three-day review now. When P1 first makes capture/review usable, remind Owner to choose the CRON time/destination. At L2 remind Owner to retrieve the real planning Codex chat from about one month earlier.

## Independent-finding dispositions — delivery closure

| Finding | Disposition | Evidence / boundary |
|---|---|---|
| `.local` absent from Docker ignore | **CONFIRMED / FIXED P0** | Narrow `.local` exclusion added. Docker canary build transferred a `2B` context and failed with `CopyIgnoredFile` / canary not found. |
| Host environment + backend dotenv can activate external config | **CONFIRMED / FIXED P0** | Sandbox children now receive an allowlisted OS environment plus exact synthetic settings; `MIMI_P0_DISABLE_DOTENV=1` makes `get_settings()` ignore dotenv only for this runner. Regression proves host Google/Neon variables are absent without reading their values. |
| Reset/container/volume identity incomplete | **CONFIRMED / FIXED P0** | Container inspect now binds label, exact image, one loopback port mapping and one named volume mount. Reset preflights all current FK/semantic dependents and refuses unowned rows. Exact synthetic integration inserted an unowned Entry, observed refusal `entry=1`, removed only that row, then reset/reseed/verify passed. |
| Arbitrary nested evidence may contain secrets/hidden reasoning | **CONFIRMED / FIXED P0 CONTRACT** | Evidence payload forbids unknown top-level provider fields and recursively rejects nested credential aliases, serialized auth/cookie material and provider-internal reasoning keys across prompt/request/response/tools/route/config/usage. Application-visible `reasoning_summary` remains allowed; raw provider ingestion/runtime remains P1 NOT_RUN. |
| Entity + client binding durability/concurrency; missing caps | **CONFIRMED / BOUNDED P0 FIX** | Per-root same-process lock, encrypted pending intent recovery and rollback-on-error cover the local single-process substrate; exact per-record P0 ceilings are 1 MiB bundle / 64 KiB feedback / 8 KiB binding. Multi-process/distributed concurrency and production quota/TTL UX remain explicit P1/pre-live gates. |
| Stored PID may be reused; stop can strand Postgres | **CONFIRMED / FIXED P0** | On Windows a live recorded PID must still own the exact listener before start/stop. Occupied unrecorded ports refuse. Container stop executes in `finally` even if app shutdown times out. |
| Runtime receipt predates candidate SHA | **CONFIRMED EVIDENCE GAP** | Prior receipt is retained as working-tree evidence, not mislabeled absent. Closure requires a fresh sequence after the remediation commit, with `/api/readyz.commit` equal to that final candidate. |
| Raw receipt provenance/internal metadata | **CONFIRMED EVIDENCE/PUBLICATION WORK** | This task is canonical; final candidate SHA, commands/exits, review, CI, PR, merge and deploy receipts will be appended here/terminal receipt. Private dispatch/thread metadata is not needed in PR copy. |

Rejected as a P0 behavior change: silently deleting dynamic P1 rows during reset. That would violate manifest ownership. The accepted behavior is fail-closed with an exact blocker count; P1 test orchestration may explicitly own/delete its own dynamic rows later.

First independent delta review (`T3 Luna/high`, fresh context, read-only) blocked publication of `5722092`: serialized JSON containing `password`, `token`, `private_key`, `reasoning_content`, `reasoning_details`, or `reasoning` remained accepted. This was adjudicated **VALID P0 blocker**, fixed at `1c7af66`, and covered by explicit regressions. Only application-visible `reasoning_summary` content and non-content `reasoning_effort` config are allowed; semantic secret detection in arbitrary prose and live-provider DTO construction remain P1/NOT_RUN. Bounded re-review of `5722092..1c7af66` directly probed every listed alias, ran the focused contract suite (`25 passed`), found no new delta regression, and **closed the blocker**. Publication for CI is now allowed.

## PR and first CI receipt

- PR [#222](https://github.com/NguyenHaiHung0510/microSched/pull/222) opened non-draft into `develop`; first published head `a868fd06fa0ed47518272c60dab83e0e6992ccb2`, base `7806f4e9f75ef66110ae3d485cffd036d42d94c1`, mergeable and 21-file P0 scope.
- On that exact head: Backend checks, Frontend checks, Repository hooks, Secret scan, Production dependency check, Migration QA, Frontend e2e, CodeQL Python and CodeQL JavaScript/TypeScript all PASS; Frontend e2e duration 7m29s. No repo labels named `codex` or `codex-automation` existed, so none were invented.
- This receipt commit changed docs only and therefore created a new PR head. The required fresh exact-head checks and `gh pr merge --match-head-commit` action were completed as recorded below. No cleanup.

## Final P0 delivery receipt — 2026-09-14

- Final PR head `1c45f865f6210026a72c5217973ad2847c12751f` was receipt-only over frozen application candidate `1c7af66582d574f43ab34493d4e3d8af856dbb23`. Fresh audit observed PR #222 OPEN/non-draft, base `develop@7806f4e9f75ef66110ae3d485cffd036d42d94c1`, head exact, mergeable/CLEAN, and the expected 21-file P0 diff.
- All final exact-head gates passed: Backend checks, Frontend checks, Repository hooks, Secret scan, Production dependency check, Migration QA, Frontend e2e, CodeQL Python and CodeQL JavaScript/TypeScript.
- CAS merge command `gh pr merge 222 --merge --match-head-commit 1c45f865f6210026a72c5217973ad2847c12751f` exited 0. PR merged at 2026-09-14T15:01:26Z as `2f06ddca28ea5570f5d1bad018ce574b9f782881`; refreshed `origin/develop` matched that SHA.
- Ordinary `develop` deployment run [34859437210](https://github.com/NguyenHaiHung0510/microSched/actions/runs/34859437210) passed. Direct production `/api/readyz` returned `status=ok`, `db=up`, `commit=2f06ddca28ea5570f5d1bad018ce574b9f782881`.
- The post-merge `develop` CI run [34859437135](https://github.com/NguyenHaiHung0510/microSched/actions/runs/34859437135) passed every lane, including Frontend e2e in 7m54s. The parallel CodeQL push run 34859437148 also passed.
- Non-blocking GitHub annotation: actions pinned to Node.js 20-compatible releases are being forced onto Node.js 24 by the runner. No workflow/dependency expansion was authorized in this P0 delivery.
- Local synthetic sandbox is stopped; its named volume and evidence are retained. No branch/worktree/container-volume cleanup was authorized or performed.

P0 delivery proves only the synthetic local substrate, contracts, repository gates and ordinary production deployment of that code. Physical iPhone/Safari, real OAuth/browser profile, real data, live provider portability, combined 512 MB resource tests and every Mimi P1+ acceptance ID remain **NOT_RUN**.

Next action is Owner review of the P1 decision packet only: exact TTL; per-run/per-chat/global caps; warning threshold/UX; verified export/extension; deletion mapping; key isolation; backup-aging truth; and the proposed Task STANDARD read/create walking skeleton. Do not start P1 from this closeout. When feedback capture/review becomes usable in P1, remind Owner to choose a three-day review schedule; at L2 remind Owner to retrieve the real planning Codex chat from about one month earlier.
