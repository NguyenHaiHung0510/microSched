# 055 — Mimi P0 synthetic sandbox and contracts

Status: **IMPLEMENTED LOCALLY / P0 COMPLETE CANDIDATE (2026-09-14)**

> Executor/writer: T1 GPT-5.6 Sol/high, Economy · Owner grant: 2026-09-14 “còn lại đồng ý, thực thi” · Automation `mimi-p0-sol-handoff-once` · source task `01a05311-c272-7633-9ac0-5abdcf44c22e` · no merge/deploy/real data/paid provider/P1 start.

## Identity, grant and baseline

- Branch/worktree: `feat/055-mimi-p0-sandbox` at `C:/Users/os/Desktop/ai_eng_path/microsched/worktrees/055-mimi-p0-sandbox`.
- Refreshed base: `origin/develop@7806f4e9f75ef66110ae3d485cffd036d42d94c1`, fetched 2026-09-14; upstream commit timestamp 2026-09-09T18:10:24+07:00.
- Duplicate-writer inventory: no Mimi P0 task/branch/worktree/open PR existed before creation. Existing dirty root (`.gitignore`, Task031/doc drafts/backup script) and all unrelated worktrees were preserved.
- Canonical task/progress path: this file. Evidence directory: `agent-tasks/task-055/`. Contract/seam map: `docs/mimi-p0-contracts.md`.
- Frozen application/test candidate: `5ef0ba2c1a7656dd199c4ff545d777cf51ee84bd`; any later commit is receipt-only unless this line is explicitly revised with new verification.
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

- P0 implemented locally; no runtime Agent router/provider/orchestrator, production schema, real capture, migration beyond existing local migrations, Neon/Fly/R2 operation, paid model call, PR, push, merge, deploy, automation or P1 implementation.
- Production, CI, production-image, real OAuth/profile, physical iPhone/Safari, live-provider portability, combined 512 MB resource tests, and all Mimi P1+ acceptance IDs: **NOT_RUN**.
- Existing `npm ci` audit reported 6 dependency vulnerabilities (3 moderate, 3 high); no dependency changes were authorized or made. This is not a P0 acceptance claim.
- Before any live/full evidence capture, Owner decision is still required for exact TTL, per-run/per-chat/global caps, warning threshold/UX, verified export/extension, deletion mapping, key isolation and backup-aging truth. P0 enabled none of these.
- Safe next action: review local commit/diff and this handoff; propose detailed P1 Task STANDARD read/create slice from observed seams. Do not auto-start P1.
- Feedback review is not usable product functionality yet, so do **not** schedule the three-day review now. When P1 first makes capture/review usable, remind Owner to choose the CRON time/destination. At L2 remind Owner to retrieve the real planning Codex chat from about one month earlier.
