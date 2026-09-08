# Task 048 — Neon idle recovery

Status: IMPLEMENTED LOCALLY / CI and runtime acceptance pending.

## Owner grant (2026-09-08)

Owner requested autonomous continuation: investigate Neon usage first, preserve harness-core in a reviewed private GitHub repository, review security using selected ASVS requirements, then perform minimal low-risk homepage optimization. Read-only Neon console access was explicitly authorized and browser profile confirmation received. No live fault/load tests, migration, credentials, new infrastructure/costs, or auth/private/crypto boundary changes are authorized by this task. Ordinary implementation, proportional QA, PR/develop delivery follows project policy. Harness content stays outside this public repository.

## Observed evidence

- Base develop verified remotely: 0960262baf0949fe0723a8b1cdb3c42073e73a43.
- Administrative usage and operation logs were inspected under Owner authorization. Their values, timestamps, endpoint identifiers and screenshots remain outside this public repository.
- Source: termination callback wakes timer; auto_reconnect immediately reacquires connection/lock and reloads. Normal timer sleeps in RAM. The synthetic regression below reproduces this unwanted idle reconnect without production fixtures.
- Foreground task polling is one second; other selected query families fifteen seconds; background polling disabled. Do not attribute all usage to owner leaving a computer on.
- Fly health probe uses DB-free healthz; do not use readiness polling to measure autosuspend.

## Intended correction and gates

Investigate event/deadline-driven recovery after ownership loss while idle. Retain a wake deadline from the last successful schedule only as a hint; never treat it as authority to send. On actual work/reload, reacquire lock and reload authoritative state before dispatch. Preserve fail-closed provider fencing, termination cancellation, recovery of in-flight/failed work, source edits, shutdown, takeover, and legacy auto_reconnect=False behavior. No new periodic database wakeup or unbounded cache.

Required evidence: fail-for-intended-violation then green regression tests; scheduler/one-shot/ownership tests and appropriate full checks; synthetic local/PG behavior as applicable; fresh exact PR head/base/gates and CAS merge; exact production readyz commit/db and non-invasive Neon Operations observation after delivery. Do not claim full-month savings from a short interval.

## Continuation

Worktree: worktrees/048-neon-idle-recovery, branch feat/048-neon-idle-recovery. Idle loss now clears the active heap and waits with only a deadline/version hint; explicit source changes cannot be lost during cleanup. Reacquisition and authoritative reload remain mandatory before processing. Active snapshot interruption still reconnects immediately. Health reports idle_unowned without a DB query. Task041 immediate recovery is narrowed only for idle loss.

Local receipts (2026-09-08): new empty-queue loss test RED on original implementation (observed two connections instead of one), then GREEN. Scheduler suite 58 PASS. Scheduler + health 65 PASS. Full non-PG suite 430 PASS, 211 deselected, exit0 using isolated basetemp with elevated filesystem permissions; earlier sandbox attempts had two filesystem fixture errors and are not PASS. Ruff app/tests PASS; diff whitespace check PASS. New coverage includes idle empty queue, due wake with authoritative snapshot removing stale item, source-edit race, idle shutdown, and immediate active-snapshot recovery. Self-review only; no independent review claimed. Local PostgreSQL and production changes NOT_RUN; PostgreSQL/required CI still required before acceptance. No frontend code change. Harness private repo and security/homepage work pending separately.

Rollback: prior app can run unchanged against this schema (no migration). Reverting this patch restores old immediate reconnect behavior and its quota risk; it is not a long-term cost fix. Runtime validation must show sleep persists beyond the former 5–6-minute cycle and that a later normal source edit/deadline resumes ownership. Live artificial data or fault injection remains prohibited.

Hourly continuation uses existing automation microsched-reminders-hourly-continuation, ACTIVE with updated scope; no second automation. Pause on completion or when no independent work remains. Preserve all unrelated/root user work.
