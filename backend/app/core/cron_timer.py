"""In-process async CRON timer for medication and subscription expiry reminders."""

import asyncio
import hashlib
import heapq
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from typing import Any, Awaitable, Callable
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.process_stats import read_rss_kb, read_uptime_s
from app.core.settings import get_settings
from app.domain.models import Entry, ReminderDispatch, Subscription, Tracker, TrackerReminderBatch
from app.domain.reminder import (
    DispatchOutcome,
    DispatchTelemetry,
    ReminderDispatcher,
    TrackerBatchCandidate,
    TrackerBatchDispatcher,
    build_subscription_expiry_payload,
    build_tracker_reminder_payload,
)
from app.domain.settings import expiry_lead_days

logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))
SUBSCRIPTION_REMINDER_TIME = time(7, 0)
PENDING_RECOVERY_TIMEOUT = timedelta(hours=24)
GRACE_WINDOW = timedelta(minutes=15)
# 011d §5.3: a top-level loop failure must back off for a bounded window rather
# than hot-looping or dying silently; tests shorten this via monkeypatch.
LOOP_FAILURE_BACKOFF_SECONDS = 30
# A failed DB snapshot is a known recovery path, not a poller. After these
# three bounded retries the task must fail so lifespan supervision restarts it.
SNAPSHOT_RETRY_BACKOFF_SECONDS = (30, 120, 600)
PROVIDER_WORKER_SHUTDOWN_TIMEOUT_SECONDS = 20.0
# 035A: one deployment-wide, session-level ownership fence.  The two positive
# int32 values deliberately form an opaque namespace/key pair; they are safe to
# query from pg_locks without disclosing a connection, PID, or user data.
SCHEDULER_ADVISORY_LOCK_NAMESPACE = 35_035
SCHEDULER_ADVISORY_LOCK_KEY = 1
SCHEDULER_ADVISORY_LOCK_REF = "scheduler_035_v1"
# Standby processes do not inspect schedules while they wait.  These values are
# a bounded takeover backoff, not a database polling interval.
OWNERSHIP_ACQUIRE_BACKOFF_SECONDS = (1, 2, 5, 10, 30)
# A hung TCP connect or lock query must not keep lifespan shutdown hostage.
OWNERSHIP_CONNECTION_TIMEOUT_SECONDS = 10.0


class CronTimerReloadFailure(RuntimeError):
    """Raised after the bounded snapshot-reload retries are exhausted."""


class CronTimerOwnershipLost(RuntimeError):
    """Raised when the dedicated session-level advisory-lock connection dies."""


class CronTimerOwnershipError(RuntimeError):
    """Raised when a timer cannot safely establish or verify ownership."""


def _backoff_seconds(attempt_count: int) -> int:
    """Bounded retry backoff per 011b §1.4: 30s → 2m → 10m, then stop."""
    if attempt_count == 1:
        return 30
    if attempt_count == 2:
        return 120
    if attempt_count == 3:
        return 600
    return 0


def _occurrence_ref(kind: "ScheduleKind", subject_id: UUID, occurrence_on: date) -> str:
    """Return a stable, non-reversible correlation token for one occurrence."""
    canonical = f"{kind.value}:{subject_id}:{occurrence_on.isoformat()}"
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()[:16]


class ScheduleKind(StrEnum):
    """Subject type scheduled in the timer heap."""

    TRACKER = "tracker"
    SUBSCRIPTION = "subscription"


@dataclass(frozen=True, slots=True)
class TimerItem:
    """Scheduled occurrence held in the min-heap."""

    due_at: datetime
    occurrence_on: date
    kind: ScheduleKind
    subject_id: UUID
    reminder_time: time | None = None
    reminder_mode: str | None = None
    reminder_interval_days: int | None = None
    reminder_action: str | None = None
    last_entry_date: date | None = None
    expires_on: date | None = None
    retry_count: int = 0
    dispatch_id: UUID | None = None
    batch_id: UUID | None = None
    is_pending_recovery: bool = False

    def heap_tuple(self) -> tuple[datetime, int, int, date, int, "TimerItem"]:
        """Return deterministic tuple for min-heap ordering."""
        kind_order = 0 if self.kind == ScheduleKind.TRACKER else 1
        return (
            self.due_at,
            kind_order,
            self.subject_id.int,
            self.occurrence_on,
            self.retry_count,
            self,
        )


class ReloadSink:
    """ContextVar reload target for commit markers."""

    def __init__(self, timer: "CronTimer"):
        self.timer = timer

    def request_reload(self, reason: str) -> None:
        self.timer.request_reload(reason)


class CronTimer:
    """Single-owner in-process timer maintaining an in-memory priority queue."""

    def __init__(
        self,
        session_factory: Any,
        reminder_dispatcher: Any | None = None,
        *,
        tracker_batch_dispatcher: Any | None = None,
        lock_connection_factory: Callable[[], Awaitable[Any]] | None = None,
        auto_reconnect: bool = False,
    ):
        self.session_factory = session_factory
        # The dispatcher owns process-local delivery locks, so it belongs to
        # this enabled timer instance rather than module import state.
        self._dispatcher = reminder_dispatcher or ReminderDispatcher()
        self._batch_dispatcher = tracker_batch_dispatcher or TrackerBatchDispatcher()
        self._lock_connection_factory = lock_connection_factory
        self.auto_reconnect = auto_reconnect
        self._has_batch_items = True
        self._lock_connection: Any | None = None
        self._ownership_active = False
        self._ownership_lost_event = asyncio.Event()
        self._ownership_wake_event = asyncio.Event()
        self._dispatch_task: asyncio.Task[None] | None = None
        self._snapshot_task: asyncio.Task[None] | None = None
        self._heap: list[tuple[datetime, int, int, date, int, TimerItem]] = []
        self.reload_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._reload_reason: str = "init"
        self._status: str = "starting"
        self._last_reload_at: datetime | None = None
        self._last_dispatch_at: datetime | None = None
        self._last_dispatch_outcome: str | None = None
        self._is_stopped = False
        self._loop_failures = 0
        self._pending_manual_required: dict[str, int] = {
            "expired": 0,
            "exhausted": 0,
            "ineligible": 0,
        }
        self._pending_recovered_count = 0
        self._invalid_tracker_schedule_count = 0
        self._stale_logged = False

    @property
    def status(self) -> str:
        return self._status

    def _log_ownership_transition(self, state: str, *, level: int = logging.INFO) -> None:
        """Emit a privacy-safe ownership receipt without connection identity."""
        logger.log(
            level,
            "cron_timer_ownership_transition state=%s lock_ref=%s commit=%s",
            state,
            SCHEDULER_ADVISORY_LOCK_REF,
            get_settings().git_sha,
        )

    def request_reload(self, reason: str) -> None:
        """Signal the timer loop to reload the schedule snapshot from DB."""
        self._reload_reason = reason
        self.reload_event.set()

    async def _default_lock_connection(self) -> Any:
        """Open a dedicated asyncpg connection outside the session pool.

        Session-level advisory locks only remain held while this exact physical
        connection lives.  A pooled SQLAlchemy session cannot prove that, so the
        fence deliberately uses a direct connection configured from the same
        application URL only when the scheduler is enabled.
        """
        import asyncpg

        from app.core.database_urls import SchedulerLockUrlError, scheduler_lock_dsn

        database_url = get_settings().database_url
        if database_url is None:
            raise CronTimerOwnershipError("scheduler ownership requires a database URL")
        try:
            lock_dsn = scheduler_lock_dsn(database_url)
        except SchedulerLockUrlError as exc:
            raise CronTimerOwnershipError(
                "scheduler ownership requires a supported direct endpoint"
            ) from exc
        return await asyncpg.connect(lock_dsn)

    def _on_lock_connection_terminated(self, connection: Any) -> None:
        """Fail closed if the sole ownership proof disappears."""
        if (
            connection is not self._lock_connection
            or self._is_stopped
            or self._ownership_lost_event.is_set()
        ):
            return
        self._status = "ownership_lost"
        self._ownership_lost_event.set()
        self._ownership_wake_event.set()
        self.reload_event.set()
        dispatch_task = self._dispatch_task
        if dispatch_task is not None and not dispatch_task.done():
            # A provider may already have accepted the current request; that
            # remains the documented at-least-once window.  Cancelling now
            # prevents the task from beginning any later provider call.
            dispatch_task.cancel()
        snapshot_task = self._snapshot_task
        if snapshot_task is not None and not snapshot_task.done():
            snapshot_task.cancel()
        self._log_ownership_transition("ownership_lost", level=logging.ERROR)

    async def _acquire_ownership(self) -> bool:
        """Acquire the session lock, or enter standby without touching schedule state."""
        attempt = 0
        while not self._is_stopped:
            attempt += 1
            delay = OWNERSHIP_ACQUIRE_BACKOFF_SECONDS[
                min(attempt - 1, len(OWNERSHIP_ACQUIRE_BACKOFF_SECONDS) - 1)
            ]
            if self._is_stopped:
                return False
            factory = self._lock_connection_factory or self._default_lock_connection
            connection: Any | None = None
            try:
                stopped, connection = await self._await_acquisition_or_stop(
                    factory(), phase="connect"
                )
                if stopped:
                    return False
                stopped, acquired = await self._await_acquisition_or_stop(
                    connection.fetchval(
                        "SELECT pg_try_advisory_lock($1::integer, $2::integer)",
                        SCHEDULER_ADVISORY_LOCK_NAMESPACE,
                        SCHEDULER_ADVISORY_LOCK_KEY,
                    ),
                    phase="lock",
                )
                if stopped:
                    await self._close_lock_connection(connection)
                    return False
            except asyncio.CancelledError:
                if connection is not None:
                    await self._close_lock_connection(connection)
                raise
            except Exception as exc:
                if connection is not None:
                    await self._close_lock_connection(connection)
                self._status = "standby"
                logger.error(
                    "cron_timer_ownership_acquire_failed attempt=%d retry_in_seconds=%d "
                    "lock_ref=%s error_type=%s",
                    attempt,
                    delay,
                    SCHEDULER_ADVISORY_LOCK_REF,
                    type(exc).__name__,
                )
                if await self._wait_for_ownership_wake(delay):
                    return False
                continue

            if acquired:
                self._lock_connection = connection
                self._ownership_active = True
                add_listener = getattr(connection, "add_termination_listener", None)
                if add_listener is not None:
                    add_listener(self._on_lock_connection_terminated)
                self._status = "owner"
                self._log_ownership_transition("owner", level=logging.WARNING)
                return True

            await self._close_lock_connection(connection)
            self._status = "standby"
            self._log_ownership_transition("standby")
            if await self._wait_for_ownership_wake(delay):
                return False
        return False

    async def _await_acquisition_or_stop(
        self, awaitable: Awaitable[Any], *, phase: str
    ) -> tuple[bool, Any]:
        """Bound one acquisition stage and let shutdown cancel it immediately."""
        work = asyncio.create_task(awaitable, name=f"microsched-cron-acquire-{phase}")
        stop_wait = asyncio.create_task(self._stop_event.wait())
        try:
            done, pending = await asyncio.wait(
                {work, stop_wait},
                timeout=OWNERSHIP_CONNECTION_TIMEOUT_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)
                raise TimeoutError(f"scheduler ownership {phase} timed out")
            if stop_wait in done:
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)
                return True, None
            return False, await work
        finally:
            if not stop_wait.done():
                stop_wait.cancel()
                await asyncio.gather(stop_wait, return_exceptions=True)

    async def _wait_for_ownership_wake(self, timeout: float) -> bool:
        """Wake standby on stop/reload, not on a database tick."""
        if self._is_stopped:
            return True
        stop_wait = asyncio.create_task(self._stop_event.wait())
        reload_wait = asyncio.create_task(self.reload_event.wait())
        ownership_wait = asyncio.create_task(self._ownership_wake_event.wait())
        try:
            done, pending = await asyncio.wait(
                {stop_wait, reload_wait, ownership_wait},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if not done:
                return False
            if stop_wait in done:
                return True
            if reload_wait in done:
                self.reload_event.clear()
            if ownership_wait in done:
                self._ownership_wake_event.clear()
            return False
        finally:
            for task in (stop_wait, reload_wait, ownership_wait):
                if not task.done():
                    task.cancel()

    async def _close_lock_connection(self, connection: Any) -> None:
        close = getattr(connection, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result

    async def _release_ownership(self) -> None:
        """Release only after the sender has quiesced during graceful shutdown."""
        connection = self._lock_connection
        self._lock_connection = None
        self._ownership_active = False
        if connection is None:
            return
        try:
            if not self._ownership_lost_event.is_set():
                await connection.execute(
                    "SELECT pg_advisory_unlock($1::integer, $2::integer)",
                    SCHEDULER_ADVISORY_LOCK_NAMESPACE,
                    SCHEDULER_ADVISORY_LOCK_KEY,
                )
        finally:
            await self._close_lock_connection(connection)

    async def _wait_for_provider_workers(self) -> None:
        """Retain scheduler ownership until real Web Push workers are finished."""
        for dispatcher in (self._dispatcher, self._batch_dispatcher):
            provider_work = getattr(dispatcher, "provider_work", None)
            if provider_work is None:
                continue
            if await provider_work.wait_for_idle(PROVIDER_WORKER_SHUTDOWN_TIMEOUT_SECONDS):
                continue
            # A synchronous provider call in ``asyncio.to_thread`` survives task
            # cancellation.  The bounded wait is observability only: releasing
            # the session-level lock here would let a standby send while that old
            # worker can still complete.  Keep the process in shutdown and retain
            # ownership until the real worker exits (or process termination
            # closes the session).
            logger.error(
                "cron_timer_provider_worker_shutdown_timeout timeout_seconds=%s "
                "lock_ref=%s action=retain_ownership",
                PROVIDER_WORKER_SHUTDOWN_TIMEOUT_SECONDS,
                SCHEDULER_ADVISORY_LOCK_REF,
            )
            await provider_work.wait_for_idle(None)

    async def _assert_owner(self, phase: str) -> None:
        """Reject snapshot, recovery, or provider work without a live fence."""
        connection = self._lock_connection
        if self._ownership_lost_event.is_set() or connection is None:
            raise CronTimerOwnershipLost(f"scheduler ownership lost before {phase}")
        is_closed = getattr(connection, "is_closed", None)
        if callable(is_closed) and is_closed():
            self._on_lock_connection_terminated(connection)
            raise CronTimerOwnershipLost(f"scheduler ownership lost before {phase}")
        try:
            still_held = await connection.fetchval(
                "SELECT EXISTS ("
                "SELECT 1 FROM pg_locks "
                "WHERE locktype = 'advisory' AND pid = pg_backend_pid() "
                "AND classid = $1::oid AND objid = $2::oid AND objsubid = 2 "
                "AND granted"
                ")",
                SCHEDULER_ADVISORY_LOCK_NAMESPACE,
                SCHEDULER_ADVISORY_LOCK_KEY,
            )
        except Exception as exc:
            self._on_lock_connection_terminated(connection)
            raise CronTimerOwnershipLost(
                f"scheduler ownership liveness failed before {phase}"
            ) from exc
        if not still_held:
            self._on_lock_connection_terminated(connection)
            raise CronTimerOwnershipLost(f"scheduler ownership missing before {phase}")

    async def _guard_provider_attempt(self) -> None:
        """Check the fence at the last safe point before Web Push I/O."""
        await self._assert_owner("provider_attempt")

    def health_snapshot(self) -> dict[str, Any]:
        """Return RAM-only observability snapshot."""
        now_vn = datetime.now(VN_TZ)
        is_stale = False
        if self._heap and self._heap[0][0] < (now_vn - GRACE_WINDOW):
            is_stale = True

        next_due_iso = None
        if self._heap:
            next_due_iso = self._heap[0][0].isoformat()

        effective_status = self._status
        if is_stale and effective_status == "owner":
            effective_status = "stale"

        if is_stale and not self._stale_logged:
            logger.warning("cron_timer_stale next_due_at=%s", next_due_iso)
            self._stale_logged = True
        elif not is_stale:
            self._stale_logged = False

        return {
            "enabled": True,
            "running": effective_status == "owner",
            "status": effective_status,
            "queue_size": len(self._heap),
            "next_due_at": next_due_iso,
            "last_reload_at": self._last_reload_at.isoformat() if self._last_reload_at else None,
            "last_dispatch_at": (
                self._last_dispatch_at.isoformat() if self._last_dispatch_at else None
            ),
            "last_dispatch_outcome": self._last_dispatch_outcome,
            "mode": "inprocess",
            "consecutive_loop_failures": self._loop_failures,
            "pending_recovered_count": self._pending_recovered_count,
            "pending_expired_count": self._pending_manual_required["expired"],
            "pending_exhausted_count": self._pending_manual_required["exhausted"],
            "pending_manual_required_count": sum(self._pending_manual_required.values()),
            "pending_manual_required": dict(self._pending_manual_required),
            "invalid_tracker_schedule_count": self._invalid_tracker_schedule_count,
            "degraded": self._loop_failures > 0 or effective_status == "stale",
            "stale": is_stale,
            "uptime_s": read_uptime_s(),
            "rss_kb": read_rss_kb(),
        }

    @staticmethod
    def _effective_tracker_config(
        tracker: Tracker,
    ) -> tuple[str, int, str, time] | None:
        """Return an enabled config, including the rolling legacy writer shape."""
        if tracker.reminder_time is None:
            return None
        if tracker.reminder_time.microsecond:
            # 035A is deployed before the database CHECK arrives.  An old or
            # direct-SQL writer can still leave a fractional row, which must
            # never become a rounded or fractional batch key in RAM.
            return None
        if (
            tracker.kind == "health"
            and tracker.input_mode == "event"
            and tracker.reminder_mode is None
            and tracker.reminder_interval_days is None
            and tracker.reminder_action is None
        ):
            return "fixed", 1, "confirm_event", tracker.reminder_time
        if (
            tracker.reminder_mode not in {"fixed", "after_entry"}
            or tracker.reminder_interval_days is None
            or tracker.reminder_interval_days <= 0
            or tracker.reminder_action not in {"confirm_event", "open_tracker"}
            or (tracker.reminder_action == "confirm_event" and tracker.input_mode != "event")
        ):
            return None
        return (
            tracker.reminder_mode,
            tracker.reminder_interval_days,
            tracker.reminder_action,
            tracker.reminder_time,
        )

    @staticmethod
    def _fixed_candidate_date(
        *,
        now_vn: datetime,
        reminder_time: time,
        interval_days: int,
        last_scheduled_date: date | None,
    ) -> date:
        """Choose the next fixed cadence date without burst catch-up."""
        if last_scheduled_date is None:
            candidate = now_vn.date()
            if datetime.combine(candidate, reminder_time, tzinfo=VN_TZ) < now_vn - GRACE_WINDOW:
                candidate += timedelta(days=1)
            return candidate
        candidate = last_scheduled_date + timedelta(days=interval_days)
        while datetime.combine(candidate, reminder_time, tzinfo=VN_TZ) < now_vn - GRACE_WINDOW:
            candidate += timedelta(days=interval_days)
        return candidate

    @staticmethod
    def _after_entry_candidate_date(
        *,
        now_vn: datetime,
        reminder_time: time,
        interval_days: int,
        last_entry_date: date | None,
        dispatched_dates: set[date],
    ) -> date:
        """Choose a civil VN date, using entry freshness rather than notifications."""
        freshness = (
            last_entry_date + timedelta(days=interval_days) if last_entry_date is not None else None
        )
        if freshness is not None and datetime.combine(freshness, reminder_time, tzinfo=VN_TZ) >= (
            now_vn - GRACE_WINDOW
        ):
            candidate = freshness
        else:
            candidate = now_vn.date()
            if datetime.combine(candidate, reminder_time, tzinfo=VN_TZ) < now_vn - GRACE_WINDOW:
                candidate += timedelta(days=1)
        while candidate in dispatched_dates:
            candidate += timedelta(days=1)
        return candidate

    async def load_snapshot(self, db: AsyncSession, *, now: datetime | None = None) -> None:
        """Load active tracker and subscription schedules and pending recoveries into RAM.

        ``now`` is a test seam: the production loop passes nothing and uses the
        real VN clock; unit tests inject a fixed instant for boundary cases.
        """
        now_vn = now or datetime.now(VN_TZ)
        today_vn = now_vn.date()
        new_heap: list[tuple[datetime, int, int, date, int, TimerItem]] = []
        pending_keys: set[tuple[ScheduleKind, UUID, date]] = set()

        # 035A must stay safe when a later batching release has already
        # committed membership.  PostgreSQL cannot plan a reference to a table
        # that does not exist, so probe first and only add the anti-join on
        # schemas that actually carry the future table.
        batch_item_table = await db.execute(
            text("SELECT to_regclass('microsched.tracker_reminder_batch_item')")
        )
        has_batch_items = batch_item_table.scalar_one_or_none() is not None
        self._has_batch_items = has_batch_items

        # 1. Load every pending reminder_dispatch row; dead rows (>24h old or
        #    attempt_count >= 4) are NOT silently dropped — 011d §1.4.3/§5.3
        #    requires a structured manual-handling receipt (F11). Eligibility
        #    against the current schedule is classified after the subject
        #    queries below.
        cutoff = now_vn - PENDING_RECOVERY_TIMEOUT
        stmt_pending = select(ReminderDispatch).where(ReminderDispatch.status == "pending")
        if has_batch_items:
            stmt_pending = stmt_pending.where(
                text(
                    "NOT EXISTS ("
                    "SELECT 1 FROM microsched.tracker_reminder_batch_item AS batch_item "
                    "WHERE batch_item.dispatch_id = reminder_dispatch.id"
                    ")"
                )
            )
        res_pending = await db.execute(stmt_pending)
        pending_rows = list(res_pending.scalars().all())

        # 035B recovery authority is the pending batch, never one linked
        # dispatch per member. A single heap item therefore carries the durable
        # batch id and preserves the committed membership across restart.
        if has_batch_items:
            batch_rows = await db.execute(
                select(TrackerReminderBatch).where(TrackerReminderBatch.status == "pending")
            )
            for batch in batch_rows.scalars().all():
                last_at = batch.last_attempt_at or batch.created_at
                if last_at is None:
                    continue
                if last_at.tzinfo is None:
                    last_at = last_at.replace(tzinfo=timezone.utc)
                last_at_vn = last_at.astimezone(VN_TZ)
                if last_at_vn < cutoff:
                    terminalized = await self._batch_dispatcher.exhaust_stale_batch(
                        db,
                        batch.id,
                        stale_before=cutoff,
                    )
                    if terminalized:
                        self._log_pending_manual_required_exhausted(
                            ScheduleKind.TRACKER,
                            TimerItem(
                                due_at=now_vn,
                                occurrence_on=batch.occurrence_on,
                                kind=ScheduleKind.TRACKER,
                                subject_id=batch.id,
                                reminder_time=batch.reminder_time,
                                retry_count=batch.attempt_count,
                                batch_id=batch.id,
                                is_pending_recovery=True,
                            ),
                        )
                    continue
                heapq.heappush(
                    new_heap,
                    TimerItem(
                        due_at=(
                            now_vn
                            if batch.attempt_count >= 4
                            else max(
                                now_vn,
                                last_at_vn
                                + timedelta(seconds=_backoff_seconds(batch.attempt_count)),
                            )
                        ),
                        occurrence_on=batch.occurrence_on,
                        kind=ScheduleKind.TRACKER,
                        subject_id=batch.id,
                        reminder_time=batch.reminder_time,
                        retry_count=batch.attempt_count,
                        batch_id=batch.id,
                        is_pending_recovery=True,
                    ).heap_tuple(),
                )
                self._pending_recovered_count += 1

        pending_meta: list[tuple[ReminderDispatch, ScheduleKind, datetime]] = []
        for p in pending_rows:
            kind = (
                ScheduleKind.TRACKER if p.subject_type == "tracker" else ScheduleKind.SUBSCRIPTION
            )
            if p.attempt_count >= 4:
                self._log_pending_manual_required("exhausted", kind, p)
                continue
            last_at = p.last_attempt_at or p.created_at
            if last_at is None:
                self._log_pending_manual_required("expired", kind, p)
                continue
            if last_at.tzinfo is None:
                last_at = last_at.replace(tzinfo=timezone.utc)
            last_at_vn = last_at.astimezone(VN_TZ)
            if last_at_vn < cutoff:
                self._log_pending_manual_required("expired", kind, p)
                continue
            pending_meta.append((p, kind, last_at_vn))

        # 2. Load active generic tracker schedules. Validation stays in Python:
        # old writers are allowed during the expand window, while malformed
        # hybrid rows must be skipped rather than guessed or crashing the timer.
        stmt_trackers = select(Tracker).where(
            Tracker.deleted_at.is_(None),
            Tracker.reminder_time.is_not(None),
        )
        res_trackers = await db.execute(stmt_trackers)
        tracker_rows = res_trackers.scalars().all()
        tracker_configs: dict[UUID, tuple[str, int, str, time]] = {}
        for tracker in tracker_rows:
            config = self._effective_tracker_config(tracker)
            if config is None:
                self._invalid_tracker_schedule_count += 1
                logger.warning(
                    "cron_timer_invalid_tracker_schedule kind=%s mode=%s",
                    tracker.kind,
                    tracker.reminder_mode,
                )
                continue
            tracker_configs[tracker.id] = config
        trackers = [tracker for tracker in tracker_rows if tracker.id in tracker_configs]
        tracker_ids = {t.id for t in trackers}

        for p, kind, last_at_vn in pending_meta:
            if kind == ScheduleKind.TRACKER and p.subject_id not in tracker_ids:
                self._log_pending_manual_required("ineligible", kind, p)
                continue
            if kind == ScheduleKind.SUBSCRIPTION:
                continue  # classified after the subscription query below
            backoff_sec = _backoff_seconds(p.attempt_count)
            due_at = max(now_vn, last_at_vn + timedelta(seconds=backoff_sec))
            item = TimerItem(
                due_at=due_at,
                occurrence_on=p.dispatched_on,
                kind=kind,
                subject_id=p.subject_id,
                retry_count=p.attempt_count,
                dispatch_id=p.id,
                is_pending_recovery=True,
            )
            pending_keys.add((kind, p.subject_id, p.dispatched_on))
            self._pending_recovered_count += 1
            heapq.heappush(new_heap, item.heap_tuple())

        # 3. Load active subscription expiry schedules
        lead_days = await expiry_lead_days(db)

        stmt_subs = (
            select(Subscription, Tracker)
            .join(Tracker, Subscription.tracker_id == Tracker.id)
            .where(
                Subscription.deleted_at.is_(None),
                Subscription.canceled_at.is_(None),
                Subscription.expires_on >= today_vn,
                Tracker.deleted_at.is_(None),
            )
        )
        res_subs = await db.execute(stmt_subs)
        sub_tuples = res_subs.all()
        sub_ids = {sub.id for sub, _tr in sub_tuples}

        for p, kind, last_at_vn in pending_meta:
            if kind == ScheduleKind.SUBSCRIPTION and p.subject_id not in sub_ids:
                self._log_pending_manual_required("ineligible", kind, p)
                continue
            if kind != ScheduleKind.SUBSCRIPTION:
                continue  # trackers were classified above
            backoff_sec = _backoff_seconds(p.attempt_count)
            due_at = max(now_vn, last_at_vn + timedelta(seconds=backoff_sec))
            item = TimerItem(
                due_at=due_at,
                occurrence_on=p.dispatched_on,
                kind=kind,
                subject_id=p.subject_id,
                retry_count=p.attempt_count,
                dispatch_id=p.id,
                is_pending_recovery=True,
            )
            pending_keys.add((kind, p.subject_id, p.dispatched_on))
            self._pending_recovered_count += 1
            heapq.heappush(new_heap, item.heap_tuple())

        # 4. Bounded tracker aggregates. Both queries are constant regardless
        # of tracker count; reminder history is kept as at most 30 civil dates
        # per tracker in RAM for O(1) after-entry de-duplication.
        last_entries: dict[UUID, date] = {}
        dispatch_dates: dict[UUID, set[date]] = {tracker_id: set() for tracker_id in tracker_ids}
        last_dispatch: dict[UUID, date] = {}
        if tracker_ids:
            entry_rows = await db.execute(
                select(Entry.tracker_id, func.max(Entry.occurred_at))
                .where(
                    Entry.tracker_id.in_(tracker_ids),
                    Entry.deleted_at.is_(None),
                    Entry.occurred_at.is_not(None),
                )
                .group_by(Entry.tracker_id)
            )
            for tracker_id, occurred_at in entry_rows:
                if occurred_at is not None:
                    if occurred_at.tzinfo is None:
                        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
                    last_entries[tracker_id] = occurred_at.astimezone(VN_TZ).date()
            dispatch_rows = await db.execute(
                select(ReminderDispatch.subject_id, ReminderDispatch.dispatched_on).where(
                    ReminderDispatch.subject_type == "tracker",
                    ReminderDispatch.subject_id.in_(tracker_ids),
                )
            )
            recent_cutoff = today_vn - timedelta(days=30)
            for tracker_id, dispatched_on in dispatch_rows:
                prior = last_dispatch.get(tracker_id)
                if prior is None or dispatched_on > prior:
                    last_dispatch[tracker_id] = dispatched_on
                if dispatched_on >= recent_cutoff:
                    dispatch_dates[tracker_id].add(dispatched_on)

        for tracker in trackers:
            mode, interval_days, action, reminder_time = tracker_configs[tracker.id]
            if mode == "fixed":
                candidate_date = self._fixed_candidate_date(
                    now_vn=now_vn,
                    reminder_time=reminder_time,
                    interval_days=interval_days,
                    last_scheduled_date=last_dispatch.get(tracker.id),
                )
            else:
                candidate_date = self._after_entry_candidate_date(
                    now_vn=now_vn,
                    reminder_time=reminder_time,
                    interval_days=interval_days,
                    last_entry_date=last_entries.get(tracker.id),
                    dispatched_dates=dispatch_dates[tracker.id],
                )
            key = (ScheduleKind.TRACKER, tracker.id, candidate_date)
            if key not in pending_keys:
                item = TimerItem(
                    due_at=datetime.combine(candidate_date, reminder_time, tzinfo=VN_TZ),
                    occurrence_on=candidate_date,
                    kind=ScheduleKind.TRACKER,
                    subject_id=tracker.id,
                    reminder_time=reminder_time,
                    reminder_mode=mode,
                    reminder_interval_days=interval_days,
                    reminder_action=action,
                    last_entry_date=last_entries.get(tracker.id),
                )
                heapq.heappush(new_heap, item.heap_tuple())

        for sub, tr in sub_tuples:
            first_date = max(today_vn, sub.expires_on - timedelta(days=lead_days))
            if first_date > sub.expires_on:
                continue

            curr_date = first_date
            while curr_date <= sub.expires_on:
                due_at = datetime.combine(curr_date, SUBSCRIPTION_REMINDER_TIME, tzinfo=VN_TZ)
                if due_at >= (now_vn - GRACE_WINDOW):
                    key = (ScheduleKind.SUBSCRIPTION, sub.id, curr_date)
                    if key not in pending_keys:
                        item = TimerItem(
                            due_at=due_at,
                            occurrence_on=curr_date,
                            kind=ScheduleKind.SUBSCRIPTION,
                            subject_id=sub.id,
                            expires_on=sub.expires_on,
                        )
                        heapq.heappush(new_heap, item.heap_tuple())
                    break
                curr_date += timedelta(days=1)

        self._heap = new_heap
        self._last_reload_at = now_vn
        next_due_at = self._heap[0][0].isoformat() if self._heap else "none"
        logger.warning(
            "cron_timer_queue_loaded reason=%s tracker_count=%d subscription_count=%d "
            "lead_days=%d queue_size=%d next_due_at=%s pending_recovered_count=%d "
            "pending_manual_required_count=%d invalid_tracker_schedule_count=%d",
            self._reload_reason,
            len(trackers),
            len(sub_tuples),
            lead_days,
            len(self._heap),
            next_due_at,
            self._pending_recovered_count,
            sum(self._pending_manual_required.values()),
            self._invalid_tracker_schedule_count,
        )

    def _log_pending_manual_required(
        self, reason: str, kind: ScheduleKind, dispatch: ReminderDispatch
    ) -> None:
        """Structured receipt for a pending row the timer will never deliver (F11)."""
        self._pending_manual_required[reason] = self._pending_manual_required.get(reason, 0) + 1
        logger.warning(
            "cron_timer_pending_manual_required reason=%s kind=%s occurrence_on=%s "
            "occurrence_ref=%s",
            reason,
            kind.value,
            dispatch.dispatched_on,
            _occurrence_ref(kind, dispatch.subject_id, dispatch.dispatched_on),
        )

    def _dispatch_telemetry(self, item: TimerItem) -> Callable[[DispatchTelemetry], None]:
        """Build the sole logger for one dispatcher invocation."""
        occurrence_ref = _occurrence_ref(item.kind, item.subject_id, item.occurrence_on)

        def emit(event: DispatchTelemetry) -> None:
            if event.outcome is None:
                logger.warning(
                    "cron_timer_dispatch_started kind=%s due_at=%s occurrence_on=%s "
                    "attempt_count=%d occurrence_ref=%s",
                    item.kind.value,
                    item.due_at.isoformat(),
                    item.occurrence_on,
                    event.attempt_count,
                    occurrence_ref,
                )
                return

            logger.warning(
                "cron_timer_dispatch_finished kind=%s due_at=%s occurrence_on=%s "
                "outcome=%s attempt_count=%d occurrence_ref=%s",
                item.kind.value,
                item.due_at.isoformat(),
                item.occurrence_on,
                event.outcome.value,
                event.attempt_count,
                occurrence_ref,
            )

        return emit

    def _schedule_next_after_stale_item(self, item: TimerItem, *, now: datetime) -> None:
        """Keep a subject's future chain after dropping an overdue unclaimed occurrence."""
        next_date = now.date()

        if item.kind == ScheduleKind.TRACKER:
            if item.reminder_time is None:
                return
            step_days = item.reminder_interval_days or 1
            if item.reminder_mode == "fixed":
                next_date = item.occurrence_on + timedelta(days=step_days)
            next_due = datetime.combine(next_date, item.reminder_time, tzinfo=VN_TZ)
            while next_due < (now - GRACE_WINDOW):
                next_date += timedelta(days=step_days if item.reminder_mode == "fixed" else 1)
                next_due = datetime.combine(next_date, item.reminder_time, tzinfo=VN_TZ)
            next_item = TimerItem(
                due_at=next_due,
                occurrence_on=next_date,
                kind=ScheduleKind.TRACKER,
                subject_id=item.subject_id,
                reminder_time=item.reminder_time,
                reminder_mode=item.reminder_mode,
                reminder_interval_days=item.reminder_interval_days,
                reminder_action=item.reminder_action,
                last_entry_date=item.last_entry_date,
            )
        else:
            if item.expires_on is None:
                return
            next_due = datetime.combine(next_date, SUBSCRIPTION_REMINDER_TIME, tzinfo=VN_TZ)
            if next_due < (now - GRACE_WINDOW):
                next_date += timedelta(days=1)
                next_due = datetime.combine(next_date, SUBSCRIPTION_REMINDER_TIME, tzinfo=VN_TZ)
            if next_date > item.expires_on:
                return
            next_item = TimerItem(
                due_at=next_due,
                occurrence_on=next_date,
                kind=ScheduleKind.SUBSCRIPTION,
                subject_id=item.subject_id,
                expires_on=item.expires_on,
            )

        heapq.heappush(self._heap, next_item.heap_tuple())

    async def _process_due_tracker_batch(
        self, items: list[TimerItem], *, now: datetime | None = None
    ) -> None:
        """Claim all same-key tracker candidates and send one aggregate payload."""
        if self._ownership_active:
            await self._assert_owner("due_tracker_batch")
        if not getattr(self, "_has_batch_items", True):
            logger.warning(
                "cron_timer_batch_fallback_individual count=%d reason=missing_batch_schema",
                len(items),
            )
            for item in items:
                if self._is_stopped:
                    break
                await self._process_due_item(item, now=now)
            return
        now_vn = now or datetime.now(VN_TZ)
        candidates: list[TrackerBatchCandidate] = []
        for item in items:
            if item.due_at < (now_vn - GRACE_WINDOW):
                self._schedule_next_after_stale_item(item, now=now_vn)
                continue
            if (
                item.reminder_time is None
                or item.reminder_mode is None
                or item.reminder_interval_days is None
                or item.reminder_action is None
            ):
                continue
            candidates.append(
                TrackerBatchCandidate(
                    tracker_id=item.subject_id,
                    occurrence_on=item.occurrence_on,
                    reminder_time=item.reminder_time,
                    reminder_mode=item.reminder_mode,
                    reminder_interval_days=item.reminder_interval_days,
                    reminder_action=item.reminder_action,
                )
            )
        if not candidates:
            return

        batch_id = None
        async with self.session_factory() as db:
            try:
                batch_id = await self._batch_dispatcher.claim_batch(db, candidates)
            except Exception as exc:
                orig = getattr(exc, "orig", None)
                pgcode = getattr(orig, "pgcode", None) or getattr(exc, "pgcode", None)
                error_str = str(exc).lower()
                is_undefined_table = pgcode == "42P01" or (
                    (
                        "undefinedtable" in type(exc).__name__.lower()
                        or "programmingerror" in type(exc).__name__.lower()
                    )
                    and "tracker_reminder_batch" in error_str
                )
                if is_undefined_table:
                    self._has_batch_items = False
                    logger.warning(
                        "cron_timer_batch_table_missing_fallback count=%d error=%s",
                        len(items),
                        type(exc).__name__,
                    )
                    for item in items:
                        if self._is_stopped:
                            break
                        await self._process_due_item(item, now=now)
                    return
                raise

            if batch_id is None:
                self.request_reload("tracker_batch_already_claimed")
                return
            outcome = await self._batch_dispatcher.dispatch_batch(
                db,
                batch_id,
                telemetry=self._dispatch_telemetry(items[0]),
                ownership_guard=self._guard_provider_attempt if self._ownership_active else None,
            )
        self._last_dispatch_at = datetime.now(VN_TZ)
        self._last_dispatch_outcome = outcome.value
        if outcome == DispatchOutcome.TEMPORARY_FAILURE:
            heapq.heappush(
                self._heap,
                TimerItem(
                    due_at=now_vn + timedelta(seconds=_backoff_seconds(1)),
                    occurrence_on=items[0].occurrence_on,
                    kind=ScheduleKind.TRACKER,
                    subject_id=batch_id,
                    reminder_time=items[0].reminder_time,
                    retry_count=1,
                    batch_id=batch_id,
                    is_pending_recovery=True,
                ).heap_tuple(),
            )
        else:
            if outcome == DispatchOutcome.EXHAUSTED:
                self._log_pending_manual_required_exhausted(ScheduleKind.TRACKER, items[0])
            self.request_reload("tracker_batch_terminal")

    async def _process_due_item(self, item: TimerItem, *, now: datetime | None = None) -> None:
        """Execute a single due item from the heap."""
        if self._ownership_active:
            await self._assert_owner("due_item")
        now_vn = now or datetime.now(VN_TZ)
        today_vn = now_vn.date()

        if item.batch_id is not None:
            async with self.session_factory() as db:
                outcome = await self._batch_dispatcher.dispatch_batch(
                    db,
                    item.batch_id,
                    telemetry=self._dispatch_telemetry(item),
                    ownership_guard=self._guard_provider_attempt
                    if self._ownership_active
                    else None,
                )
            self._last_dispatch_at = datetime.now(VN_TZ)
            self._last_dispatch_outcome = outcome.value
            if outcome == DispatchOutcome.TEMPORARY_FAILURE and item.retry_count < 3:
                heapq.heappush(
                    self._heap,
                    TimerItem(
                        due_at=now_vn + timedelta(seconds=_backoff_seconds(item.retry_count + 1)),
                        occurrence_on=item.occurrence_on,
                        kind=ScheduleKind.TRACKER,
                        subject_id=item.subject_id,
                        reminder_time=item.reminder_time,
                        retry_count=item.retry_count + 1,
                        batch_id=item.batch_id,
                        is_pending_recovery=True,
                    ).heap_tuple(),
                )
            else:
                if outcome == DispatchOutcome.EXHAUSTED:
                    self._log_pending_manual_required_exhausted(ScheduleKind.TRACKER, item)
                self.request_reload("tracker_batch_terminal")
            return

        # Check grace window for non-pending items
        if not item.is_pending_recovery and item.due_at < (now_vn - GRACE_WINDOW):
            self._schedule_next_after_stale_item(item, now=now_vn)
            logger.warning(
                "cron_timer_stale reason=overdue_item kind=%s occurrence_on=%s due_at=%s "
                "occurrence_ref=%s",
                item.kind.value,
                item.occurrence_on,
                item.due_at.isoformat(),
                _occurrence_ref(item.kind, item.subject_id, item.occurrence_on),
            )
            return

        async with self.session_factory() as db:
            if item.kind == ScheduleKind.TRACKER:
                stmt = select(Tracker).where(
                    Tracker.id == item.subject_id,
                    Tracker.deleted_at.is_(None),
                )
                res = await db.execute(stmt)
                tracker = res.scalar_one_or_none()

                if tracker is None:
                    return
                config = self._effective_tracker_config(tracker)
                if config is None:
                    self._invalid_tracker_schedule_count += 1
                    return
                mode, interval_days, action, reminder_time = config
                if (
                    item.reminder_mode is not None
                    and (
                        item.reminder_mode,
                        item.reminder_interval_days,
                        item.reminder_action,
                        item.reminder_time,
                    )
                    != config
                ):
                    # A reload normally removes stale heap items. This second
                    # check closes the mutation-vs-dispatch race without sending
                    # an old occurrence under a newly edited action or cadence.
                    return

                def payload_builder(d_id: UUID) -> dict:
                    return build_tracker_reminder_payload(
                        tracker,
                        d_id,
                        reminder_mode=mode,
                        reminder_interval_days=interval_days,
                        reminder_action=action,
                        today_vn=today_vn,
                        last_entry_date=item.last_entry_date,
                    )

                outcome = await self._dispatcher.dispatch_item(
                    db,
                    "tracker",
                    tracker.id,
                    item.occurrence_on,
                    payload_builder,
                    telemetry=self._dispatch_telemetry(item),
                    ownership_guard=self._guard_provider_attempt
                    if self._ownership_active
                    else None,
                )
                self._last_dispatch_at = datetime.now(VN_TZ)
                self._last_dispatch_outcome = outcome.value

                if outcome == DispatchOutcome.EXHAUSTED:
                    self._log_pending_manual_required_exhausted(ScheduleKind.TRACKER, item)

                if outcome == DispatchOutcome.TEMPORARY_FAILURE and item.retry_count < 3:
                    retry_due = now_vn + timedelta(seconds=_backoff_seconds(item.retry_count + 1))
                    retry_item = TimerItem(
                        due_at=retry_due,
                        occurrence_on=item.occurrence_on,
                        kind=ScheduleKind.TRACKER,
                        subject_id=tracker.id,
                        reminder_time=reminder_time,
                        reminder_mode=mode,
                        reminder_interval_days=interval_days,
                        reminder_action=action,
                        last_entry_date=item.last_entry_date,
                        retry_count=item.retry_count + 1,
                        dispatch_id=item.dispatch_id,
                        is_pending_recovery=True,
                    )
                    heapq.heappush(self._heap, retry_item.heap_tuple())
                else:
                    # F10: the next occurrence is scheduled even when the last
                    # retry failed terminally — a dead attempt must not swallow
                    # tomorrow's reminder.
                    next_date = item.occurrence_on + timedelta(
                        days=interval_days if mode == "fixed" else 1
                    )
                    next_due = datetime.combine(next_date, reminder_time, tzinfo=VN_TZ)
                    next_item = TimerItem(
                        due_at=next_due,
                        occurrence_on=next_date,
                        kind=ScheduleKind.TRACKER,
                        subject_id=tracker.id,
                        reminder_time=reminder_time,
                        reminder_mode=mode,
                        reminder_interval_days=interval_days,
                        reminder_action=action,
                        last_entry_date=item.last_entry_date,
                    )
                    heapq.heappush(self._heap, next_item.heap_tuple())

            elif item.kind == ScheduleKind.SUBSCRIPTION:
                stmt = (
                    select(Subscription, Tracker)
                    .join(Tracker, Subscription.tracker_id == Tracker.id)
                    .where(
                        Subscription.id == item.subject_id,
                        Subscription.deleted_at.is_(None),
                        Subscription.canceled_at.is_(None),
                        Subscription.expires_on >= item.occurrence_on,
                        Tracker.deleted_at.is_(None),
                    )
                )
                res = await db.execute(stmt)
                sub_tuple = res.first()

                if sub_tuple is None:
                    return

                sub, tr = sub_tuple
                lead_days = await expiry_lead_days(db)

                def sub_payload_builder(d_id: UUID) -> dict:
                    return build_subscription_expiry_payload(sub, tr, lead_days, today=today_vn)

                outcome = await self._dispatcher.dispatch_item(
                    db,
                    "subscription",
                    sub.id,
                    item.occurrence_on,
                    sub_payload_builder,
                    telemetry=self._dispatch_telemetry(item),
                    ownership_guard=self._guard_provider_attempt
                    if self._ownership_active
                    else None,
                )
                self._last_dispatch_at = datetime.now(VN_TZ)
                self._last_dispatch_outcome = outcome.value

                if outcome == DispatchOutcome.EXHAUSTED:
                    self._log_pending_manual_required_exhausted(ScheduleKind.SUBSCRIPTION, item)

                if outcome == DispatchOutcome.TEMPORARY_FAILURE and item.retry_count < 3:
                    retry_due = now_vn + timedelta(seconds=_backoff_seconds(item.retry_count + 1))
                    retry_item = TimerItem(
                        due_at=retry_due,
                        occurrence_on=item.occurrence_on,
                        kind=ScheduleKind.SUBSCRIPTION,
                        subject_id=sub.id,
                        expires_on=sub.expires_on,
                        retry_count=item.retry_count + 1,
                        dispatch_id=item.dispatch_id,
                        is_pending_recovery=True,
                    )
                    heapq.heappush(self._heap, retry_item.heap_tuple())
                else:
                    # F6 + F10: the subscription chain must continue day by day
                    # until expires_on, and a terminally-failed attempt must
                    # not swallow the next day's occurrence.
                    next_date = item.occurrence_on + timedelta(days=1)
                    if next_date <= sub.expires_on:
                        next_due = datetime.combine(
                            next_date, SUBSCRIPTION_REMINDER_TIME, tzinfo=VN_TZ
                        )
                        next_item = TimerItem(
                            due_at=next_due,
                            occurrence_on=next_date,
                            kind=ScheduleKind.SUBSCRIPTION,
                            subject_id=sub.id,
                            expires_on=sub.expires_on,
                        )
                        heapq.heappush(self._heap, next_item.heap_tuple())

    def _log_pending_manual_required_exhausted(self, kind: ScheduleKind, item: TimerItem) -> None:
        """Receipt for an occurrence whose 4 delivery attempts are gone (F11)."""
        self._pending_manual_required["exhausted"] += 1
        logger.warning(
            "cron_timer_pending_manual_required reason=exhausted kind=%s "
            "occurrence_on=%s occurrence_ref=%s",
            kind.value,
            item.occurrence_on,
            _occurrence_ref(kind, item.subject_id, item.occurrence_on),
        )

    async def _wait_for_stop(self, timeout: float) -> bool:
        """Wait for a bounded backoff, returning early when shutdown starts."""
        if self._is_stopped:
            return True
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=timeout)
        except TimeoutError:
            return False
        return True

    async def _load_snapshot_with_retries(self, phase: str) -> bool:
        """Rebuild the heap with the exact bounded recovery contract.

        A normal empty queue never polls. This retry sequence only exists after
        a known DB snapshot failure; keeping the last valid heap until a
        successful replacement prevents an outage being misread as no work.
        """
        self._reload_reason = phase
        for attempt, delay in enumerate(SNAPSHOT_RETRY_BACKOFF_SECONDS, start=1):
            try:
                await self._assert_owner("snapshot")
                self._snapshot_task = asyncio.create_task(
                    self._load_snapshot_once(), name="microsched-cron-snapshot"
                )
                await self._await_ownership_or_task(self._snapshot_task, phase="snapshot")
            except asyncio.CancelledError:
                if self._is_stopped:
                    return False
                raise
            except CronTimerOwnershipLost:
                raise
            except Exception as exc:
                self._loop_failures += 1
                logger.error(
                    "cron_timer_snapshot_failed phase=%s attempt=%d retry_in_seconds=%d error=%s",
                    phase,
                    attempt,
                    delay,
                    type(exc).__name__,
                )
                if await self._wait_for_stop(delay):
                    self._status = "stopped"
                    return False
            else:
                self._loop_failures = 0
                return True

        if self._is_stopped:
            self._status = "stopped"
            return False

        try:
            await self._assert_owner("snapshot")
            self._snapshot_task = asyncio.create_task(
                self._load_snapshot_once(), name="microsched-cron-snapshot"
            )
            await self._await_ownership_or_task(self._snapshot_task, phase="snapshot")
        except asyncio.CancelledError:
            if self._is_stopped:
                return False
            raise
        except CronTimerOwnershipLost:
            raise
        except Exception as exc:
            self._loop_failures += 1
            logger.error(
                "cron_timer_loop_failed phase=reload failures=%d error=%s",
                self._loop_failures,
                type(exc).__name__,
            )
            raise CronTimerReloadFailure("CronTimer snapshot reload retries exhausted") from exc
        else:
            self._loop_failures = 0
            return True

    async def _load_snapshot_once(self) -> None:
        """Run the bounded database rebuild in a separately supervised task."""
        try:
            async with self.session_factory() as db:
                await self.load_snapshot(db)
        finally:
            self._snapshot_task = None

    async def _await_with_ownership(self, awaitable: Awaitable[Any], *, phase: str) -> Any:
        """Race a blocking recovery operation against loss of the lock session."""
        work_task = asyncio.create_task(awaitable, name=f"microsched-cron-{phase}")
        return await self._await_ownership_or_task(work_task, phase=phase)

    async def _await_ownership_or_task(self, task: asyncio.Task[Any], *, phase: str) -> Any:
        """Make lock loss preempt blocked snapshot or recovery work promptly."""
        ownership_wait = asyncio.create_task(self._ownership_lost_event.wait())
        try:
            done, pending = await asyncio.wait(
                {task, ownership_wait}, return_when=asyncio.FIRST_COMPLETED
            )
            if ownership_wait in done:
                if not task.done():
                    task.cancel()
                    # Do not leave a cancelled snapshot/recovery coroutine
                    # running behind the fatal lifespan error.  In particular,
                    # a session-context cleanup could otherwise begin later
                    # recovery work after the dedicated lock is gone.
                    await asyncio.gather(task, return_exceptions=True)
                raise CronTimerOwnershipLost(f"scheduler ownership lost during {phase}")
            return await task
        finally:
            if not ownership_wait.done():
                ownership_wait.cancel()
                await asyncio.gather(ownership_wait, return_exceptions=True)

    async def _cleanup_lost_ownership(self) -> None:
        """Reset state and disconnect when ownership is lost."""
        self._ownership_active = False
        self._status = "standby"
        self._heap = []
        self._ownership_lost_event.clear()
        self._ownership_wake_event.clear()
        conn = self._lock_connection
        self._lock_connection = None
        if conn is not None:
            await self._close_lock_connection(conn)

    async def run(self) -> None:
        """Run only while this process owns the PostgreSQL scheduler lock."""
        self._log_ownership_transition("starting", level=logging.WARNING)
        try:
            while not self._is_stopped:
                if not await self._acquire_ownership():
                    return
                try:
                    try:
                        if not await self._await_with_ownership(
                            self._load_snapshot_with_retries(
                                "startup" if self._last_reload_at is None else "recovery"
                            ),
                            phase="recovery",
                        ):
                            return
                    except CronTimerOwnershipLost:
                        raise

                    while not self._is_stopped:
                        if self._ownership_lost_event.is_set():
                            raise CronTimerOwnershipLost(
                                "scheduler ownership lost during timer loop"
                            )
                        try:
                            if self.reload_event.is_set():
                                self.reload_event.clear()
                                if not await self._await_with_ownership(
                                    self._load_snapshot_with_retries("reload"), phase="recovery"
                                ):
                                    break

                            now_vn = datetime.now(VN_TZ)
                            due_items: list[TimerItem] = []
                            while self._heap and self._heap[0][0] <= now_vn:
                                _, _, _, _, _, item = heapq.heappop(self._heap)
                                due_items.append(item)

                            grouped_tracker_items: dict[tuple[date, time], list[TimerItem]] = {}
                            individual_items: list[TimerItem] = []
                            for item in due_items:
                                if (
                                    item.kind == ScheduleKind.TRACKER
                                    and item.batch_id is None
                                    and item.reminder_time is not None
                                ):
                                    grouped_tracker_items.setdefault(
                                        (item.occurrence_on, item.reminder_time), []
                                    ).append(item)
                                else:
                                    individual_items.append(item)
                            work_items: list[TimerItem | list[TimerItem]] = [
                                grouped_tracker_items[key] for key in sorted(grouped_tracker_items)
                            ]
                            work_items.extend(individual_items)

                            for work_item in work_items:
                                if self._is_stopped:
                                    break
                                item = work_item[0] if isinstance(work_item, list) else work_item
                                self._dispatch_task = asyncio.create_task(
                                    self._process_due_tracker_batch(work_item)
                                    if isinstance(work_item, list)
                                    else self._process_due_item(item),
                                    name="microsched-cron-dispatch",
                                )
                                try:
                                    await self._dispatch_task
                                except asyncio.CancelledError:
                                    if self._ownership_lost_event.is_set():
                                        raise CronTimerOwnershipLost(
                                            "scheduler ownership lost during provider dispatch"
                                        )
                                    if self._is_stopped:
                                        break
                                    raise
                                except CronTimerOwnershipLost:
                                    raise
                                except Exception as exc:
                                    logger.error(
                                        "cron_timer_dispatch_failed kind=%s occurrence_on=%s "
                                        "occurrence_ref=%s error_type=%s",
                                        item.kind.value,
                                        item.occurrence_on,
                                        _occurrence_ref(
                                            item.kind, item.subject_id, item.occurrence_on
                                        ),
                                        type(exc).__name__,
                                    )
                                    self.request_reload("dispatch_error")
                                finally:
                                    self._dispatch_task = None

                            if self._is_stopped:
                                break
                            now_vn = datetime.now(VN_TZ)
                            if self._heap:
                                sleep_sec = max(0.0, (self._heap[0][0] - now_vn).total_seconds())
                                await asyncio.wait_for(self.reload_event.wait(), timeout=sleep_sec)
                            else:
                                await self.reload_event.wait()
                        except asyncio.CancelledError:
                            logger.info("CronTimer loop cancelled")
                            raise
                        except CronTimerOwnershipLost, CronTimerReloadFailure:
                            raise
                        except TimeoutError:
                            pass
                        except Exception as exc:
                            self._loop_failures += 1
                            logger.error(
                                "cron_timer_loop_failed failures=%d error=%s",
                                self._loop_failures,
                                type(exc).__name__,
                            )
                            if await self._wait_for_stop(LOOP_FAILURE_BACKOFF_SECONDS):
                                break
                except CronTimerOwnershipLost:
                    await self._cleanup_lost_ownership()
                    if not self.auto_reconnect:
                        raise
                    logger.warning(
                        "cron_timer_ownership_lost_reconnecting lock_ref=%s action=reacquire",
                        SCHEDULER_ADVISORY_LOCK_REF,
                    )
                    continue
        except CronTimerOwnershipLost:
            if self._status != "ownership_lost":
                self._status = "ownership_lost"
                self._log_ownership_transition("ownership_lost", level=logging.ERROR)
            if self.auto_reconnect and not self._is_stopped:
                await self._cleanup_lost_ownership()
                logger.warning(
                    "cron_timer_ownership_lost_reconnecting lock_ref=%s action=reacquire",
                    SCHEDULER_ADVISORY_LOCK_REF,
                )
                return await self.run()
            raise
        finally:
            if self._status != "stopped":
                self._status = "stopping"
                self._log_ownership_transition("stopping")
            await self._wait_for_provider_workers()
            await self._release_ownership()
            self._status = "stopped"
            self._log_ownership_transition("stopped")

    async def stop(self) -> None:
        """Clean shutdown for the timer loop."""
        if self._status == "stopped":
            return
        self._status = "stopping"
        self._log_ownership_transition("stopping")
        self._is_stopped = True
        self.reload_event.set()
        self._stop_event.set()
        self._ownership_wake_event.set()
        dispatch_task = self._dispatch_task
        if dispatch_task is not None and not dispatch_task.done():
            dispatch_task.cancel()
            await asyncio.gather(dispatch_task, return_exceptions=True)
        snapshot_task = self._snapshot_task
        if snapshot_task is not None and not snapshot_task.done():
            snapshot_task.cancel()
            await asyncio.gather(snapshot_task, return_exceptions=True)
        await self._wait_for_provider_workers()
        await self._release_ownership()
        self._status = "stopped"
        self._log_ownership_transition("stopped")


def build_cron_timer_if_enabled(session_factory: Any = None) -> CronTimer | None:
    """Build and return a CronTimer instance if ENABLE_INPROCESS_CRON is True."""
    settings = get_settings()
    if not settings.enable_inprocess_cron:
        return None

    if session_factory is None:
        from app.core.db import get_sessionmaker

        session_factory = get_sessionmaker()
        if session_factory is None:
            raise RuntimeError(
                "ENABLE_INPROCESS_CRON=true requires a configured DATABASE_URL "
                "(app.core.db.get_sessionmaker() returned None)"
            )

    return CronTimer(session_factory, auto_reconnect=True)
