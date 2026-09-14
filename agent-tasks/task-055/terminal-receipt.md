# Task 055 terminal receipt

Run date/time: 2026-09-14 Asia/Saigon. Synthetic local data only.

## Baseline and runner

```text
task_id=mimi-p0-055
branch=feat/055-mimi-p0-sandbox
base=origin/develop
base_sha=7806f4e9f75ef66110ae3d485cffd036d42d94c1
docker_server=29.7.2
container=microsched-mimi-p0-055
container_label=microsched.synthetic=mimi-p0-055
database=microsched_mimi_p0_055
database_host=127.0.0.1
fixture_version=mimi-p0.v1
fixture_sha256=39661bc7b78d88b310257077e75834613ffc7e968062524022c0691b2f5003cc
```

## Database/start/reset

```text
alembic=upgrade 0001 -> 0013 PASS
migration_prerequisites=ok
seed_counts=tasks:3 notes:2 calendar_sources:1 calendar_events:1 day_annotations:1 tracker_groups:2 trackers:3 subscriptions:1 entries:5
repeat_start=PASS (no migration replay, no duplicate fixture IDs)
verify_before_reset=counts_match:true review_store_preserved:true
reset=exact manifest IDs only; reseed PASS
verify_after_reset=counts_match:true review_store_preserved:true
review_bundle_roundtrip_before_after_reset=true
feedback_acknowledged_before_after_reset=true
feedback_unresolved_before_after_reset=true
```

## Full app/browser

```text
backend_ready=true
backend_db=up
backend_commit=7806f4e9f75ef66110ae3d485cffd036d42d94c1
frontend_ready=true
browser=isolated Playwright CLI session mimi-p0-055
observed=authenticated app + STANDARD seeded Note/Tracker/Calendar data
private_state=locked; PRIVATE seeded rows not displayed
cleanup=dev-session logout + browser close
post_logout_console_401=/api/me on public page; expected auth check after logout
restart=start -> stop -> start -> verify -> stop PASS
restart_review_bundle_roundtrip=true
restart_feedback_acknowledged=true
restart_feedback_unresolved=true
final_state=backend false; frontend false; postgres false; volume/evidence retained
```

## Code checks

```text
uv run --frozen pytest tests/test_mimi_p0_contracts.py tests/test_mimi_p0_feedback_store.py tests/test_mimi_p0_testing.py tests/test_mimi_p0_sandbox.py -q
19 passed

uv run --frozen pytest -m "not pg" -q
459 passed, 211 deselected, one Starlette/httpx deprecation warning

uv run --frozen ruff check <P0 Python scope>
PASS

uv run --frozen ruff format --check <P0 Python scope>
PASS after applying project formatter

git diff --check
PASS
```

Resolved during verification: the first Windows stop implementation stored transient venv/npm launcher PIDs, so child listeners briefly survived and a restart failed closed on the occupied port. The corrected runner resolves/stores the actual loopback listener PIDs, waits for both ports to close, and uses a bounded exact-tree force only when graceful termination does not finish. The final two-cycle start/stop/restart/verify/stop receipt above passed.

The focused tests cover full encrypted payload roundtrip, stable client retry dedup/conflict, completeness truth, secret/header/cookie exclusion, acknowledged unresolved feedback persistence across store reopen and fixture reseed simulation, local-target guard, manifest-scoped reset, fake provider failure, fake clock and deterministic barrier delay.

## NOT_RUN / excluded

```text
CI=NOT_RUN
production_image=NOT_RUN
Neon/Fly/R2/production=NOT_RUN
real_data/real_browser_profile/real_OAuth=NOT_RUN
paid/live_model=NOT_RUN
physical_iPhone/Safari=NOT_RUN
Mimi orchestrator and P1 acceptance=NOT_RUN
P1 auto-start=NO
merge/deploy/PR/push=NO
```
