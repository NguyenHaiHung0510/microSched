# Task 041: Scheduler Resilience, Auto-Reconnection & Graceful Fallback

## 1. Problem Statement
In Task 035A, PostgreSQL advisory locks were introduced to ensure single-node scheduler ownership (CronTimer).
However, under Neon Serverless PostgreSQL and cloud deployments:
1. **Silent Zombie Task Failure**: When Neon suspends compute due to idle (~5 minutes) or transient network drops, the asyncpg connection is terminated. The termination listener sets _ownership_lost_event. The timer loop wakes up and raises CronTimerOwnershipLost, causing CronTimer.run() to terminate permanently.
2. **Uncaught Background Lifespan Failure**: In app.main.lifespan, task_group.create_task(timer.run()) is called before yield. Because yield suspends the context manager while FastAPI serves HTTP, the task death does not crash Uvicorn. The app continues serving HTTP 200 OK (including /api/healthz), while the background scheduler is dead forever.
3. **Missing DB Schema Fragility (Migration 0012)**: In Task 035B, _process_due_tracker_batch queries microsched.tracker_reminder_batch. If migration 0012 has not been applied to the target database, claim_batch raises UndefinedTableError, aborting dispatch.

## 2. Invariants & Requirements

### 2.1 Self-Healing Scheduler Loop
- When CronTimer loses connection / ownership (CronTimerOwnershipLost or connection termination):
  - It must NOT terminate timer.run().
  - It must transition status to 'standby'.
  - It must immediately cancel any pending dispatch or recovery work (fail-closed, no split-brain).
  - It must clear the active schedule heap to prevent unauthorized firing while unowned.
  - It must enter _acquire_ownership() with bounded backoff, continuously attempting to re-establish the connection and acquire the advisory lock.
  - Upon re-acquiring ownership, it must reload the durable snapshot from the database (_load_snapshot_with_retries) and resume normal timer operations.

### 2.2 Preserving Shutdown Semantics
- If timer.stop() is called (app shutdown), _is_stopped is set:
  - The acquisition and reconnect loop must exit cleanly and promptly.
  - timer.run() must return cleanly without hanging.

### 2.3 Graceful Fallback When Batch Tables Are Missing
- In _process_due_tracker_batch, verify if tracker_reminder_batch exists (via has_batch_items or table check):
  - If the table does not exist, do not raise an unhandled exception.
  - Log a warning and fall back to individual item processing via _process_due_item.

### 2.4 Healthz & Observability
- Expose scheduler status in /api/healthz:
  - If enable_inprocess_cron is true, report cron_timer_status (owner, standby, degraded, stopped).
  - Ensure process health checks reflect scheduler health without running DB queries on liveness.

## 3. Test Plan
1. Unit Test: Disconnection & Reconnection.
2. Unit Test: Graceful Fallback Without Batch Table.
3. PG Integration Test.

## 4. Acceptance Criteria
- pytest backend/tests/test_cron_timer.py passes 100%.
- pytest backend/tests/test_scheduler_ownership_pg.py passes 100%.
- Frontend and backend lint/build pass.
- Independent adversarial review passes.
