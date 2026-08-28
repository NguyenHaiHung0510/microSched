# 035A scheduler ownership — local receipt

## Scope and immutable inputs

- Worktree: `worktrees/035a-scheduler-ownership`
- Branch: `feat/035a-scheduler-ownership`
- Baseline: `fcdacdf7a0ef0cca8e47bbac0878ec0b3e9b53db`
- Reviewed PASS_SPEC: `agent-tasks/035-reminder-batching.md`
- PASS_SPEC SHA-256: `01A039FDE1FF9E5AACC82CBF6797C78AEA9B7F9F839E8C65101C2AB566B3384F`

This receipt covers §6 / 035A only: the session-level PostgreSQL advisory-lock
fence, future-schema recovery and confirmation guards, shutdown ordering, and
their local tests. It does not claim CI, deployment, topology, Neon,
production, device, browser, or provider acceptance. No database URL, PID,
UUID, endpoint, or credential is recorded here.

## Semantic files

- `backend/app/core/cron_timer.py` — ownership state machine, dedicated lock
  connection, liveness checks, bounded standby backoff, loss propagation,
  future-schema anti-join, and worker-before-unlock shutdown.
- `backend/app/domain/push.py` — tracks real shielded `asyncio.to_thread` work.
- `backend/app/domain/reminder.py` — provider guard plus confirmation's
  tracker → dispatch → Entry order and terminal-status guard.
- `backend/app/domain/tracker.py` — tracker-before-Entry order for create,
  update-occurrence, soft-delete, and restore.
- `backend/scripts/scheduler_ownership_receipt.py` — one-shot, read-only exact
  advisory-holder receipt.
- `backend/tests/test_cron_timer.py`,
  `backend/tests/test_scheduler_ownership_pg.py`,
  `backend/tests/test_scheduler_ownership_receipt.py`,
  `backend/tests/test_reminder_domain.py`, and
  `backend/tests/test_push_api.py` — unit and real-PG receipts.

Final-review additions:

- The one-shot receipt query now requires the current database, the exact
  two-key advisory-lock identity, `mode = 'ExclusiveLock'`, and `granted`.
- The real-PG receipt test proves shared, wrong-key, and other-database locks
  count as zero while the exact exclusive holder counts as one.
- The real-PG confirmation matrix proves pre-0012 `pending` and `sent` create
  exactly one idempotent Entry; `no_device`, simulated `cancelled` and
  `exhausted`, and a simulated unknown future terminal status return 409 and
  create zero Entries. The simulation changes only the local test constraint;
  035A does not implement migration `0012`.

## Deliberate RED → restored GREEN

The implementation was temporarily changed only for this proof so graceful
shutdown called advisory unlock before waiting for the registered provider
worker. The exact focused command and observed terminal output were:

```text
uv run pytest tests/test_cron_timer.py -m "not pg" -k graceful_stop_waits_for_uncancellable_provider_thread -vv -s

tests/test_cron_timer.py::test_graceful_stop_waits_for_uncancellable_provider_thread[asyncio] FAILED

================================== FAILURES ===================================
_____ test_graceful_stop_waits_for_uncancellable_provider_thread[asyncio] _____

>           assert connection.unlock_calls == 0
E           assert 1 == 0

=========================== short test summary info ===========================
FAILED tests/test_cron_timer.py::test_graceful_stop_waits_for_uncancellable_provider_thread[asyncio] - assert 1 == 0
 +  where 1 = <test_cron_timer.FakeLockConnection object at ...>.unlock_calls
====================== 1 failed, 39 deselected in 1.13s =======================
```

The temporary change was restored before the following focused GREEN command:

```text
uv run pytest tests/test_cron_timer.py -m "not pg" -k graceful_stop_waits_for_uncancellable_provider_thread -vv -s

tests/test_cron_timer.py::test_graceful_stop_waits_for_uncancellable_provider_thread[asyncio] PASSED

====================== 1 passed, 39 deselected in 0.70s =======================
```

The future-schema anti-join guard also had a prior deliberate proof:

```text
uv run pytest tests/test_cron_timer.py -m "not pg" -k future_batch_schema_adds_pending_recovery_antijoin
1 failed, 35 deselected

# restored
1 passed, 35 deselected
```

## Local PASS receipts observed before this final review

```text
uv run ruff format .
2 files reformatted, 113 files left unchanged

uv run ruff format --check .
115 files already formatted

uv run ruff check .
All checks passed!

uv run pytest -m "not pg"
315 passed, 174 deselected, 1 warning in 10.67s

uv run pytest tests/test_scheduler_ownership_pg.py -vv -s --log-cli-level=ERROR
6 passed in 2.41s
```

## Full PostgreSQL lane boundary

The local throwaway PG18 container was reachable and targeted 035A PG tests
passed. The two full commands below did not reach an observable terminal
summary through this harness, so this gate is `NOT_RUN`, not PASS or FAIL:

```text
uv run pytest -m pg
collected 489 items / 315 deselected / 174 selected
tests/test_annotations_api.py ..
tests/test_calendar_api.py .
tests/test_cutover_v2_pg.py ...............................

uv run pytest -m pg -q
. ...................
```

Read-only process and database checks then showed local pytest runners still
live but no database lock wait. Per the two-repeat stop rule, no uncertain
runner was killed. Exact-head CI must provide the remaining full-PG receipt.

## Final-review local receipts

```text
uv run ruff format scripts/scheduler_ownership_receipt.py tests/test_scheduler_ownership_receipt.py tests/test_scheduler_ownership_pg.py
3 files left unchanged

uv run ruff check scripts/scheduler_ownership_receipt.py tests/test_scheduler_ownership_receipt.py tests/test_scheduler_ownership_pg.py
All checks passed!

uv run pytest tests/test_scheduler_ownership_receipt.py tests/test_scheduler_ownership_pg.py -vv -s --log-cli-level=ERROR
9 passed in 2.91s

uv run ruff format --check .
115 files already formatted

uv run ruff check .
All checks passed!

uv run pytest -m "not pg"
315 passed, 176 deselected, 1 warning in 9.76s
```

Before the final full-PG command, a read-only local process check returned no
existing pytest runner. The command was run once with its durable raw stream
captured in `agent-tasks/035a-full-pg-output.txt`; its observed output was:

```text
uv run pytest -m pg 2>&1 | Tee-Object -FilePath agent-tasks/035a-full-pg-output.txt

collected 491 items / 315 deselected / 176 selected

tests/test_annotations_api.py ..                                         [  1%]
tests/test_calendar_api.py .                                             [  1%]
```

The terminal stream detached and the retained log remained at that partial
output while a local pytest runner was still live. It is therefore `NOT_RUN`;
no process was terminated and no full-PG PASS/FAIL is inferred.

The durable log later reached a terminal failure rather than the earlier
partial stream. It found a concrete concurrent-confirmation regression:

```text
FAILED tests/test_push_api.py::test_two_devices_confirm_same_dispatch_create_one_entry
E           assert [True, True] == [False, True]
=== 1 failed, 175 passed, 315 deselected, 19 warnings in 114.84s (0:01:54) ===
```

Cause: the post-tracker-lock `ReminderDispatch` re-read reused the session's
unlocked probe object, so the second confirmation did not observe the first
commit. The fix uses a `FOR UPDATE` re-read with `populate_existing=True` and
returns the actual `(entry_id, created)` result from `TrackerStore`.

The focused restored-GREEN receipt is:

```text
uv run pytest tests/test_push_api.py::test_two_devices_confirm_same_dispatch_create_one_entry tests/test_scheduler_ownership_pg.py::test_pg_confirmation_matrix_pre_and_post_future_schema tests/test_scheduler_ownership_pg.py::test_pg_confirmation_and_after_entry_writers_take_tracker_before_children -vv -s --log-cli-level=ERROR

3 passed in 2.29s
```

The previous full terminal result belongs to the pre-fix state. A subsequent
fixed exact-head full run retained its terminal receipt in
`agent-tasks/035a-full-pg-output.txt`:

```text
uv run pytest -m pg 2>&1 | Tee-Object -FilePath agent-tasks/035a-full-pg-output.txt

======== 176 passed, 315 deselected, 19 warnings in 106.96s (0:01:46) =========
```

This is local throwaway-PG evidence only; it is not CI, deployment, topology,
Neon, production, device, or provider acceptance.
