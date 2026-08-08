"""In-process async CRON timer for medication and subscription expiry reminders."""

import asyncio
import heapq
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.domain.models import ReminderDispatch, Subscription, Tracker
from app.domain.reminder import (
    DispatchOutcome,
    build_medication_payload,
    build_subscription_expiry_payload,
    dispatcher,
)

logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))
SUBSCRIPTION_REMINDER_TIME = time(7, 0)
PENDING_RECOVERY_TIMEOUT = timedelta(hours=24)
GRACE_WINDOW = timedelta(minutes=15)


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

    def __init__(self, session_factory: Any):
        self.session_factory = session_factory
        self._heap: list[tuple[datetime, int, int, date, int, TimerItem]] = []
        self.reload_event = asyncio.Event()
        self._reload_reason: str = "init"
        self._status: str = "starting"
        self._last_reload_at: datetime | None = None
        self._last_dispatch_at: datetime | None = None
        self._loop_task: asyncio.Task[None] | None = None
        self._is_stopped = False

    @property
    def status(self) -> str:
        return self._status

    def request_reload(self, reason: str) -> None:
        """Signal the timer loop to reload the schedule snapshot from DB."""
        self._reload_reason = reason
        self.reload_event.set()

    def health_snapshot(self) -> dict[str, Any]:
        """Return RAM-only observability snapshot."""
        next_due_iso = None
        if self._heap:
            next_due_iso = self._heap[0][0].isoformat()

        return {
            "status": self._status,
            "queue_size": len(self._heap),
            "next_due": next_due_iso,
            "last_reload": self._last_reload_at.isoformat() if self._last_reload_at else None,
            "last_dispatch": self._last_dispatch_at.isoformat() if self._last_dispatch_at else None,
            "mode": "inprocess",
        }

    async def load_snapshot(self, db: AsyncSession) -> None:
        """Load active tracker and subscription schedules and pending recoveries into RAM."""
        now_vn = datetime.now(VN_TZ)
        today_vn = now_vn.date()
        new_heap: list[tuple[datetime, int, int, date, int, TimerItem]] = []
        pending_keys: set[tuple[ScheduleKind, UUID, date]] = set()

        # 1. Load pending reminder_dispatch rows within recovery window (< 24h, attempt < 4)
        cutoff = now_vn - PENDING_RECOVERY_TIMEOUT
        stmt_pending = select(ReminderDispatch).where(
            ReminderDispatch.status == "pending",
            ReminderDispatch.attempt_count < 4,
            func.coalesce(ReminderDispatch.last_attempt_at, ReminderDispatch.created_at) >= cutoff,
        )
        res_pending = await db.execute(stmt_pending)
        pending_rows = res_pending.scalars().all()

        for p in pending_rows:
            kind = (
                ScheduleKind.TRACKER if p.subject_type == "tracker" else ScheduleKind.SUBSCRIPTION
            )
            backoff_sec = 0
            if p.attempt_count == 1:
                backoff_sec = 30
            elif p.attempt_count == 2:
                backoff_sec = 120
            elif p.attempt_count == 3:
                backoff_sec = 600

            last_at = p.last_attempt_at or p.created_at
            if last_at.tzinfo is None:
                last_at = last_at.replace(tzinfo=timezone.utc)
            last_at_vn = last_at.astimezone(VN_TZ)

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
            heapq.heappush(new_heap, item.heap_tuple())

        # 2. Load active tracker medication schedules
        stmt_trackers = select(Tracker).where(
            Tracker.deleted_at.is_(None),
            Tracker.reminder_time.is_not(None),
            Tracker.kind == "health",
            Tracker.input_mode == "event",
        )
        res_trackers = await db.execute(stmt_trackers)
        trackers = res_trackers.scalars().all()

        for t in trackers:
            r_time = t.reminder_time
            if r_time is None:
                continue

            candidate_date = today_vn
            due_at = datetime.combine(candidate_date, r_time, tzinfo=VN_TZ)

            if due_at < now_vn:
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
        from app.domain.settings import get_app_setting

        lead_days_str = await get_app_setting(db, "subscription_expiry_lead_days")
        try:
            lead_days = int(lead_days_str) if lead_days_str else 3
        except ValueError:
            lead_days = 3

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

        for sub, tr in sub_tuples:
            first_date = max(today_vn, sub.expires_on - timedelta(days=lead_days))
            if first_date > sub.expires_on:
                continue

            curr_date = first_date
            while curr_date <= sub.expires_on:
                due_at = datetime.combine(curr_date, SUBSCRIPTION_REMINDER_TIME, tzinfo=VN_TZ)
                if due_at >= now_vn or curr_date > today_vn:
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
        logger.info(
            "CronTimer loaded snapshot (reason=%s): %d items queued",
            self._reload_reason,
            len(self._heap),
        )

    async def _process_due_item(self, item: TimerItem) -> None:
        """Execute a single due item from the heap."""
        now_vn = datetime.now(VN_TZ)

        # Check grace window for non-pending items
        if not item.is_pending_recovery and item.due_at < (now_vn - GRACE_WINDOW):
            logger.warning(
                "CronTimer skipping stale item beyond grace window: kind=%s id=%s due=%s",
                item.kind,
                item.subject_id,
                item.due_at,
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

                outcome = await dispatcher.dispatch_item(
                    db, "tracker", tracker.id, item.occurrence_on, payload_builder
                )
                self._last_dispatch_at = datetime.now(VN_TZ)

                if outcome == DispatchOutcome.TEMPORARY_FAILURE and item.retry_count < 3:
                    backoff = (
                        30 if item.retry_count == 0 else (120 if item.retry_count == 1 else 600)
                    )
                    retry_due = now_vn + timedelta(seconds=backoff)
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
                elif tracker.reminder_time is not None:
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
                from app.domain.settings import get_app_setting

                lead_str = await get_app_setting(db, "subscription_expiry_lead_days")
                lead_days = int(lead_str) if lead_str and lead_str.isdigit() else 3

                def sub_payload_builder(d_id: UUID) -> dict:
                    return build_subscription_expiry_payload(sub, tr, lead_days)

                outcome = await dispatcher.dispatch_item(
                    db, "subscription", sub.id, item.occurrence_on, sub_payload_builder
                )
                self._last_dispatch_at = datetime.now(VN_TZ)

                if outcome == DispatchOutcome.TEMPORARY_FAILURE and item.retry_count < 3:
                    backoff = (
                        30 if item.retry_count == 0 else (120 if item.retry_count == 1 else 600)
                    )
                    retry_due = now_vn + timedelta(seconds=backoff)
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

    async def run(self) -> None:
        """Main timer loop."""
        self._status = "running"
        logger.info("CronTimer loop started")

        try:
            async with self.session_factory() as db:
                await self.load_snapshot(db)
        except Exception as exc:
            logger.error("Failed to load initial CronTimer snapshot: %s", exc)
            self._status = "degraded"

        while not self._is_stopped:
            if self.reload_event.is_set():
                self.reload_event.clear()
                try:
                    async with self.session_factory() as db:
                        await self.load_snapshot(db)
                    self._status = "running"
                except Exception as exc:
                    logger.error("Failed to reload CronTimer snapshot: %s", exc)
                    self._status = "degraded"

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
                            "Error processing CronTimer item kind=%s id=%s: %s",
                            item.kind,
                            item.subject_id,
                            exc,
                        )

            # Calculate sleep duration to next item or wait for reload event
            now_vn = datetime.now(VN_TZ)
            sleep_sec = 3600.0  # default 1 hour if heap empty
            if self._heap:
                sleep_sec = max(0.0, (self._heap[0][0] - now_vn).total_seconds())

            try:
                await asyncio.wait_for(self.reload_event.wait(), timeout=sleep_sec)
            except TimeoutError:
                pass
            except asyncio.CancelledError:
                logger.info("CronTimer loop cancelled")
                raise

    async def stop(self) -> None:
        """Clean shutdown for the timer loop."""
        self._is_stopped = True
        self.reload_event.set()
        self._status = "stopped"


def build_cron_timer_if_enabled(session_factory: Any = None) -> CronTimer | None:
    """Build and return a CronTimer instance if ENABLE_INPROCESS_CRON is True."""
    settings = get_settings()
    if not settings.enable_inprocess_cron:
        return None

    if session_factory is None:
        from app.db import async_session_factory

        session_factory = async_session_factory

    return CronTimer(session_factory)
