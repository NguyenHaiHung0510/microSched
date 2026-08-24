"""In-process async CRON timer for medication and subscription expiry reminders."""

import asyncio
import hashlib
import heapq
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.process_stats import read_rss_kb, read_uptime_s
from app.core.settings import get_settings
from app.domain.models import ReminderDispatch, Subscription, Tracker
from app.domain.reminder import (
    DispatchOutcome,
    DispatchTelemetry,
    ReminderDispatcher,
    build_medication_payload,
    build_subscription_expiry_payload,
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


class CronTimerReloadFailure(RuntimeError):
    """Raised after the bounded snapshot-reload retries are exhausted."""


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
    expires_on: date | None = None
    retry_count: int = 0
    dispatch_id: UUID | None = None
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
    """Single in-process async timer maintaining an in-memory priority queue."""

    def __init__(self, session_factory: Any, reminder_dispatcher: Any | None = None):
        self.session_factory = session_factory
        # The dispatcher owns process-local delivery locks, so it belongs to
        # this enabled timer instance rather than module import state.
        self._dispatcher = reminder_dispatcher or ReminderDispatcher()
        self._heap: list[tuple[datetime, int, int, date, int, TimerItem]] = []
        self.reload_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._reload_reason: str = "init"
        self._status: str = "starting"
        self._last_reload_at: datetime | None = None
        self._last_dispatch_at: datetime | None = None
        self._last_dispatch_outcome: str | None = None
        self._loop_task: asyncio.Task[None] | None = None
        self._is_stopped = False
        self._loop_failures = 0
        self._pending_manual_required: dict[str, int] = {
            "expired": 0,
            "exhausted": 0,
            "ineligible": 0,
        }
        self._pending_recovered_count = 0
        self._stale_logged = False

    @property
    def status(self) -> str:
        return self._status

    def request_reload(self, reason: str) -> None:
        """Signal the timer loop to reload the schedule snapshot from DB."""
        self._reload_reason = reason
        self.reload_event.set()

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
        if is_stale and effective_status == "running":
            effective_status = "stale"

        if is_stale and not self._stale_logged:
            logger.warning("cron_timer_stale next_due_at=%s", next_due_iso)
            self._stale_logged = True
        elif not is_stale:
            self._stale_logged = False

        return {
            "enabled": True,
            "running": effective_status == "running",
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
            "degraded": effective_status in ("degraded", "stale"),
            "stale": is_stale,
            "uptime_s": read_uptime_s(),
            "rss_kb": read_rss_kb(),
        }

    async def load_snapshot(self, db: AsyncSession, *, now: datetime | None = None) -> None:
        """Load active tracker and subscription schedules and pending recoveries into RAM.

        ``now`` is a test seam: the production loop passes nothing and uses the
        real VN clock; unit tests inject a fixed instant for boundary cases.
        """
        now_vn = now or datetime.now(VN_TZ)
        today_vn = now_vn.date()
        new_heap: list[tuple[datetime, int, int, date, int, TimerItem]] = []
        pending_keys: set[tuple[ScheduleKind, UUID, date]] = set()

        # 1. Load every pending reminder_dispatch row; dead rows (>24h old or
        #    attempt_count >= 4) are NOT silently dropped — 011d §1.4.3/§5.3
        #    requires a structured manual-handling receipt (F11). Eligibility
        #    against the current schedule is classified after the subject
        #    queries below.
        cutoff = now_vn - PENDING_RECOVERY_TIMEOUT
        stmt_pending = select(ReminderDispatch).where(ReminderDispatch.status == "pending")
        res_pending = await db.execute(stmt_pending)
        pending_rows = list(res_pending.scalars().all())

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

        # 2. Load active tracker medication schedules
        stmt_trackers = select(Tracker).where(
            Tracker.deleted_at.is_(None),
            Tracker.reminder_time.is_not(None),
            Tracker.kind == "health",
            Tracker.input_mode == "event",
        )
        res_trackers = await db.execute(stmt_trackers)
        trackers = res_trackers.scalars().all()
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

        for t in trackers:
            r_time = t.reminder_time
            if r_time is None:
                continue

            candidate_date = today_vn
            due_at = datetime.combine(candidate_date, r_time, tzinfo=VN_TZ)

            if due_at < (now_vn - GRACE_WINDOW):
                candidate_date = today_vn + timedelta(days=1)
                due_at = datetime.combine(candidate_date, r_time, tzinfo=VN_TZ)

            key = (ScheduleKind.TRACKER, t.id, candidate_date)
            if key not in pending_keys:
                item = TimerItem(
                    due_at=due_at,
                    occurrence_on=candidate_date,
                    kind=ScheduleKind.TRACKER,
                    subject_id=t.id,
                    reminder_time=r_time,
                )
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
            "pending_manual_required_count=%d",
            self._reload_reason,
            len(trackers),
            len(sub_tuples),
            lead_days,
            len(self._heap),
            next_due_at,
            self._pending_recovered_count,
            sum(self._pending_manual_required.values()),
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
            next_due = datetime.combine(next_date, item.reminder_time, tzinfo=VN_TZ)
            if next_due < (now - GRACE_WINDOW):
                next_date += timedelta(days=1)
                next_due = datetime.combine(next_date, item.reminder_time, tzinfo=VN_TZ)
            next_item = TimerItem(
                due_at=next_due,
                occurrence_on=next_date,
                kind=ScheduleKind.TRACKER,
                subject_id=item.subject_id,
                reminder_time=item.reminder_time,
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

    async def _process_due_item(self, item: TimerItem, *, now: datetime | None = None) -> None:
        """Execute a single due item from the heap."""
        now_vn = now or datetime.now(VN_TZ)
        today_vn = now_vn.date()

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
                    Tracker.reminder_time.is_not(None),
                    Tracker.kind == "health",
                    Tracker.input_mode == "event",
                )
                res = await db.execute(stmt)
                tracker = res.scalar_one_or_none()

                if tracker is None:
                    return

                def payload_builder(d_id: UUID) -> dict:
                    return build_medication_payload(tracker, d_id)

                outcome = await self._dispatcher.dispatch_item(
                    db,
                    "tracker",
                    tracker.id,
                    item.occurrence_on,
                    payload_builder,
                    telemetry=self._dispatch_telemetry(item),
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
                        reminder_time=tracker.reminder_time,
                        retry_count=item.retry_count + 1,
                        dispatch_id=item.dispatch_id,
                        is_pending_recovery=True,
                    )
                    heapq.heappush(self._heap, retry_item.heap_tuple())
                else:
                    # F10: the next occurrence is scheduled even when the last
                    # retry failed terminally — a dead attempt must not swallow
                    # tomorrow's reminder.
                    next_date = item.occurrence_on + timedelta(days=1)
                    next_due = datetime.combine(next_date, tracker.reminder_time, tzinfo=VN_TZ)
                    next_item = TimerItem(
                        due_at=next_due,
                        occurrence_on=next_date,
                        kind=ScheduleKind.TRACKER,
                        subject_id=tracker.id,
                        reminder_time=tracker.reminder_time,
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
                async with self.session_factory() as db:
                    await self.load_snapshot(db)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._loop_failures += 1
                self._status = "degraded"
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
                self._status = "running"
                self._loop_failures = 0
                return True

        if self._is_stopped:
            self._status = "stopped"
            return False

        try:
            async with self.session_factory() as db:
                await self.load_snapshot(db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._loop_failures += 1
            self._status = "degraded"
            logger.error(
                "cron_timer_loop_failed phase=reload failures=%d error=%s",
                self._loop_failures,
                type(exc).__name__,
            )
            raise CronTimerReloadFailure("CronTimer snapshot reload retries exhausted") from exc
        else:
            self._status = "running"
            self._loop_failures = 0
            return True

    async def run(self) -> None:
        """Main timer loop."""
        self._status = "running"
        logger.warning("cron_timer_started mode=inprocess")
        if not await self._load_snapshot_with_retries("startup"):
            return

        while not self._is_stopped:
            try:
                if self.reload_event.is_set():
                    self.reload_event.clear()
                    if not await self._load_snapshot_with_retries("reload"):
                        break

                now_vn = datetime.now(VN_TZ)

                # Pop all items that are due now
                due_items: list[TimerItem] = []
                while self._heap and self._heap[0][0] <= now_vn:
                    _, _, _, _, _, item = heapq.heappop(self._heap)
                    due_items.append(item)

                if due_items:
                    for item in due_items:
                        try:
                            await self._process_due_item(item)
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            logger.error(
                                "cron_timer_dispatch_failed kind=%s occurrence_on=%s "
                                "occurrence_ref=%s error_type=%s",
                                item.kind.value,
                                item.occurrence_on,
                                _occurrence_ref(item.kind, item.subject_id, item.occurrence_on),
                                type(exc).__name__,
                            )
                            # A DB failure before a durable claim must not drop
                            # the occurrence. Reload immediately: a claimed row
                            # rehydrates as pending; an unclaimed item remains
                            # eligible through the 15-minute grace window.
                            self.request_reload("dispatch_error")

                # Calculate sleep duration to next item, or wait forever for a
                # reload event when the heap is empty (no tick, no query).
                now_vn = datetime.now(VN_TZ)
                if self._heap:
                    sleep_sec = max(0.0, (self._heap[0][0] - now_vn).total_seconds())
                    await asyncio.wait_for(self.reload_event.wait(), timeout=sleep_sec)
                else:
                    await self.reload_event.wait()
            except asyncio.CancelledError:
                logger.info("CronTimer loop cancelled")
                raise
            except CronTimerReloadFailure:
                raise
            except TimeoutError:
                # Normal wake-up: the wait-for-next-due deadline elapsed.
                pass
            except Exception as exc:
                # Bacon-F2 (011d §5.3): an unexpected top-level failure must
                # never kill the task silently while the app thinks reminders
                # are running. Log, go DEGRADED, wait a bounded backoff, then
                # continue the loop.
                self._loop_failures += 1
                self._status = "degraded"
                logger.error(
                    "cron_timer_loop_failed failures=%d error=%s",
                    self._loop_failures,
                    type(exc).__name__,
                )
                if await self._wait_for_stop(LOOP_FAILURE_BACKOFF_SECONDS):
                    break

    async def stop(self) -> None:
        """Clean shutdown for the timer loop."""
        self._is_stopped = True
        self.reload_event.set()
        self._stop_event.set()
        self._status = "stopped"


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

    return CronTimer(session_factory)
