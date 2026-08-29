"""Domain logic for reminder payloads, dispatcher execution, and confirmation."""

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from enum import StrEnum
from typing import Awaitable, Callable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.domain.models import (
    AuthSession,
    Entry,
    PushSubscription,
    ReminderDispatch,
    Subscription,
    Tracker,
    TrackerReminderBatch,
    TrackerReminderBatchItem,
)
from app.domain.push import ProviderWorkTracker, PushResult, send_push
from app.domain.tracker import EntryCreate, TrackerStore

logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))


class DispatchOutcome(StrEnum):
    """Outcome status returned by the reminder dispatcher."""

    SENT = "sent"
    TEMPORARY_FAILURE = "temporary_failure"
    NO_DEVICE = "no_device"
    EXHAUSTED = "exhausted"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class DispatchTelemetry:
    """Durable dispatcher state exposed to an optional in-process observer."""

    attempt_count: int
    outcome: DispatchOutcome | None = None


@dataclass(frozen=True, slots=True)
class TrackerBatchCandidate:
    """Heap snapshot passed into the transactional tracker-batch claim."""

    tracker_id: UUID
    occurrence_on: date
    reminder_time: time
    reminder_mode: str
    reminder_interval_days: int
    reminder_action: str


@dataclass(frozen=True, slots=True)
class BatchFanout:
    """Provider result counts for one aggregate payload attempt."""

    current_count: int = 0
    sent_count: int = 0
    temporary_failure_count: int = 0
    dead_count: int = 0


@dataclass(frozen=True, slots=True)
class _ActiveBatchMember:
    item: TrackerReminderBatchItem
    dispatch: ReminderDispatch
    tracker: Tracker


def build_tracker_reminder_payload(
    tracker: Tracker,
    dispatch_id: UUID,
    *,
    reminder_mode: str,
    reminder_interval_days: int,
    reminder_action: str,
    today_vn: date,
    last_entry_date: date | None = None,
) -> dict:
    """Build the one generic, public-safe tracker reminder notification.

    ``last_entry_date`` is scheduling metadata only. It is never included for a
    private tracker and is deliberately not inferred from dispatch history.
    """
    title = "Nhắc nhở microSched"

    # Privacy rule: if reminder_text is provided by user, use it directly (public surface).
    # Otherwise, if tracker is private, MUST NOT reveal tracker name or ciphertext.
    if tracker.reminder_text and tracker.reminder_text.strip():
        body = tracker.reminder_text.strip()
    elif tracker.is_private:
        body = "Đã tới hạn ghi nhận."
    else:
        name = _public_name(tracker.name)
        if reminder_mode == "after_entry" and last_entry_date is not None and name:
            days_overdue = max(reminder_interval_days, (today_vn - last_entry_date).days)
            body = f"Đã {days_overdue} ngày chưa ghi nhận: {name}"
        else:
            body = f"Đã tới hạn: {name}" if name else "Đã tới hạn ghi nhận."

    url = (
        f"/reminder-confirm?dispatch={dispatch_id}"
        if reminder_action == "confirm_event"
        else "/trackers"
    )
    return {"title": title, "body": body, "url": url}


def build_medication_payload(tracker: Tracker, dispatch_id: UUID) -> dict:
    """Compatibility wrapper for the pre-031 medication payload call site."""
    return build_tracker_reminder_payload(
        tracker,
        dispatch_id,
        reminder_mode="fixed",
        reminder_interval_days=1,
        reminder_action="confirm_event",
        today_vn=datetime.now(VN_TZ).date(),
    )


def build_subscription_expiry_payload(
    subscription: Subscription,
    parent_tracker: Tracker | None,
    lead_days: int,
    today: date | None = None,
) -> dict:
    """Build the public-safe Web Push notification payload for subscription expiry.

    ``today`` is the business day in Vietnam (+07:00), passed in by the caller
    so the "days left" cut-over at midnight VN cannot drift with the server's
    local clock (F13 — ``date.today()`` in UTC is a whole day behind at
    00:00 UTC / 07:00 VN).
    """
    title = "Hạn đăng ký microSched"
    today = today or datetime.now(VN_TZ).date()
    days_left = max(0, (subscription.expires_on - today).days)

    is_private = parent_tracker is not None and parent_tracker.is_private

    if is_private:
        body = f"Một đăng ký sắp hết hạn trong {days_left} ngày"
    else:
        name = _public_name(subscription.name)
        body = (
            f"Đăng ký {name} sắp hết hạn trong {days_left} ngày"
            if name
            else f"Một đăng ký sắp hết hạn trong {days_left} ngày"
        )

    url = f"/subscription?highlight={subscription.id}"
    return {"title": title, "body": body, "url": url}


def _public_name(stored_name: str | None) -> str | None:
    """Return a decrypted public label without ever putting ciphertext in a push."""
    if not stored_name:
        return None
    if not crypto.is_encrypted(stored_name):
        return stored_name
    try:
        return crypto.decrypt(stored_name)
    except Exception:
        # A corrupt/wrong-key name is not a reason to leak its ciphertext to a
        # lock screen. The generic payload keeps the delivery safe and useful.
        logger.warning("Unable to decrypt a public reminder label; using generic payload")
        return None


class ReminderDispatcher:
    """Core dispatcher for claiming reminder occurrences and sending Web Push."""

    def __init__(self) -> None:
        # The production contract is exactly one app process. A process-local
        # mutex serializes the network phase without holding a PostgreSQL
        # connection or row lock across Web Push; durable dispatch state still
        # covers crash/redeploy recovery.
        self._delivery_locks: dict[tuple[str, UUID, date], asyncio.Lock] = {}
        self._provider_work = ProviderWorkTracker()

    @property
    def provider_work(self) -> ProviderWorkTracker:
        """Expose only bounded shutdown coordination, never provider details."""
        return self._provider_work

    async def claim_or_get_dispatch(
        self,
        db: AsyncSession,
        subject_type: str,
        subject_id: UUID,
        dispatched_on: date,
    ) -> ReminderDispatch:
        """Insert or fetch the reminder_dispatch row with FOR UPDATE locking."""
        # ON CONFLICT DO NOTHING insert
        insert_stmt = text(
            """
            INSERT INTO microsched.reminder_dispatch
                (id, subject_type, subject_id, dispatched_on, status, attempt_count, created_at)
            VALUES
                (uuidv7(), :subject_type, :subject_id, :dispatched_on, 'pending', 0, NOW())
            ON CONFLICT (subject_type, subject_id, dispatched_on) DO NOTHING
            """
        )
        await db.execute(
            insert_stmt,
            {
                "subject_type": subject_type,
                "subject_id": subject_id,
                "dispatched_on": dispatched_on,
            },
        )
        await db.flush()

        # SELECT FOR UPDATE
        select_stmt = (
            select(ReminderDispatch)
            .where(
                ReminderDispatch.subject_type == subject_type,
                ReminderDispatch.subject_id == subject_id,
                ReminderDispatch.dispatched_on == dispatched_on,
            )
            .with_for_update()
        )
        result = await db.execute(select_stmt)
        dispatch = result.scalar_one()
        return dispatch

    async def dispatch_item(
        self,
        db: AsyncSession,
        subject_type: str,
        subject_id: UUID,
        dispatched_on: date,
        payload_builder: Callable[[UUID], dict],
        *,
        telemetry: Callable[[DispatchTelemetry], None] | None = None,
        ownership_guard: Callable[[], Awaitable[None]] | None = None,
    ) -> DispatchOutcome:
        """Execute one occurrence without keeping a database lock over network I/O."""
        key = (subject_type, subject_id, dispatched_on)
        lock = self._delivery_locks.setdefault(key, asyncio.Lock())
        async with lock:
            dispatch = await self.claim_or_get_dispatch(db, subject_type, subject_id, dispatched_on)

            if dispatch.status in (DispatchOutcome.SENT, DispatchOutcome.NO_DEVICE):
                outcome = DispatchOutcome(dispatch.status)
                if telemetry is not None:
                    telemetry(DispatchTelemetry(attempt_count=dispatch.attempt_count))
                    telemetry(
                        DispatchTelemetry(attempt_count=dispatch.attempt_count, outcome=outcome)
                    )
                return outcome

            if dispatch.attempt_count >= 4:
                if telemetry is not None:
                    telemetry(DispatchTelemetry(attempt_count=dispatch.attempt_count))
                    telemetry(
                        DispatchTelemetry(
                            attempt_count=dispatch.attempt_count,
                            outcome=DispatchOutcome.EXHAUSTED,
                        )
                    )
                return DispatchOutcome.EXHAUSTED

            # Claim delivery attempt
            dispatch.attempt_count += 1
            dispatch.last_attempt_at = datetime.now(UTC)
            await db.commit()
            if telemetry is not None:
                telemetry(DispatchTelemetry(attempt_count=dispatch.attempt_count))

            # Build payload with stable dispatch ID
            payload = payload_builder(dispatch.id)

            # Query all active push subscriptions
            sub_stmt = select(PushSubscription)
            sub_result = await db.execute(sub_stmt)
            subscriptions = list(sub_result.scalars().all())

            # Do not retain the SELECT transaction/pooled connection while
            # waiting on the network. The application sessionmaker uses
            # expire_on_commit=False, so these immutable subscription values
            # remain available to send_push after the short read transaction.
            await db.commit()

            if not subscriptions:
                dispatch.status = DispatchOutcome.NO_DEVICE
                await db.commit()
                if telemetry is not None:
                    telemetry(
                        DispatchTelemetry(
                            attempt_count=dispatch.attempt_count,
                            outcome=DispatchOutcome.NO_DEVICE,
                        )
                    )
                return DispatchOutcome.NO_DEVICE

            # 035A checks the dedicated session-level advisory-lock connection
            # at the final boundary before any provider I/O.  A loss after a
            # provider accepts remains the documented at-least-once window;
            # a loss before this guard must not begin a new call.
            if ownership_guard is not None:
                await ownership_guard()

            sent_count = 0
            temp_fail_count = 0

            for sub in subscriptions:
                if ownership_guard is not None:
                    await ownership_guard()
                res = await send_push(
                    db,
                    sub,
                    payload,
                    provider_work_tracker=self._provider_work,
                )
                if res == PushResult.SENT:
                    sent_count += 1
                elif res == PushResult.TEMPORARY_FAILURE:
                    temp_fail_count += 1

            if sent_count >= 1:
                dispatch.status = DispatchOutcome.SENT
                await db.commit()
                if telemetry is not None:
                    telemetry(
                        DispatchTelemetry(
                            attempt_count=dispatch.attempt_count,
                            outcome=DispatchOutcome.SENT,
                        )
                    )
                return DispatchOutcome.SENT

            if temp_fail_count >= 1:
                # Remain pending for retry with same dispatch ID
                await db.commit()
                if telemetry is not None:
                    telemetry(
                        DispatchTelemetry(
                            attempt_count=dispatch.attempt_count,
                            outcome=DispatchOutcome.TEMPORARY_FAILURE,
                        )
                    )
                return DispatchOutcome.TEMPORARY_FAILURE

            # Only dead subscriptions or list emptied
            dispatch.status = DispatchOutcome.NO_DEVICE
            await db.commit()
            if telemetry is not None:
                telemetry(
                    DispatchTelemetry(
                        attempt_count=dispatch.attempt_count,
                        outcome=DispatchOutcome.NO_DEVICE,
                    )
                )
            return DispatchOutcome.NO_DEVICE


class TrackerBatchDispatcher:
    """Durably claim and fan out one payload per current push endpoint.

    Membership is immutable after :meth:`claim_batch` commits. Retry and restart
    always address the batch id, never reconstruct a group from the current heap.
    """

    _ADVISORY_NAMESPACE = 0x35B01201
    _TERMINAL = frozenset({"sent", "no_device", "cancelled", "exhausted"})

    def __init__(self) -> None:
        self._delivery_locks: dict[UUID, asyncio.Lock] = {}
        self._provider_work = ProviderWorkTracker()

    @property
    def provider_work(self) -> ProviderWorkTracker:
        return self._provider_work

    @staticmethod
    def _effective_config(tracker: Tracker) -> tuple[str, int, str, time] | None:
        if tracker.reminder_time is None or tracker.reminder_time.microsecond:
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
            or tracker.reminder_interval_days < 1
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
    def _signed_int32(value: int) -> int:
        return value - (1 << 32) if value >= (1 << 31) else value

    @classmethod
    def _advisory_key(cls, occurrence_on: date, reminder_time: time) -> int:
        canonical = f"{occurrence_on.isoformat()}\x1f{reminder_time.strftime('%H:%M:%S')}"
        raw = int.from_bytes(hashlib.sha256(canonical.encode("utf-8")).digest()[:4], "big")
        return cls._signed_int32(raw)

    @staticmethod
    def _batch_ref(batch_id: UUID) -> str:
        return hashlib.sha256(batch_id.bytes).hexdigest()[:20]

    @staticmethod
    def _notification_tag(batch_id: UUID) -> str:
        return f"msb-{hashlib.sha256(batch_id.bytes).hexdigest()[:24]}"

    async def _lock_entries_and_latest_dates(
        self, db: AsyncSession, tracker_ids: list[UUID]
    ) -> dict[UUID, date]:
        if not tracker_ids:
            return {}
        rows = await db.execute(
            select(Entry)
            .where(
                Entry.tracker_id.in_(tracker_ids),
                Entry.deleted_at.is_(None),
                Entry.occurred_at.is_not(None),
            )
            .order_by(Entry.id)
            .with_for_update()
        )
        latest: dict[UUID, date] = {}
        for entry in rows.scalars().all():
            occurred_at = entry.occurred_at
            if occurred_at is None:
                continue
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=UTC)
            occurred_on = occurred_at.astimezone(VN_TZ).date()
            previous = latest.get(entry.tracker_id)
            if previous is None or occurred_on > previous:
                latest[entry.tracker_id] = occurred_on
        return latest

    @staticmethod
    def _candidate_is_due(
        *, candidate: TrackerBatchCandidate, tracker: Tracker, latest_entry_on: date | None
    ) -> bool:
        config = TrackerBatchDispatcher._effective_config(tracker)
        expected = (
            candidate.reminder_mode,
            candidate.reminder_interval_days,
            candidate.reminder_action,
            candidate.reminder_time,
        )
        if config != expected:
            return False
        if candidate.reminder_mode != "after_entry" or latest_entry_on is None:
            return True
        return latest_entry_on + timedelta(days=candidate.reminder_interval_days) <= (
            candidate.occurrence_on
        )

    async def claim_batch(
        self,
        db: AsyncSession,
        candidates: list[TrackerBatchCandidate],
    ) -> UUID | None:
        """Claim valid candidates under one key lock and commit immutable membership."""
        if not candidates:
            return None
        occurrence_on = candidates[0].occurrence_on
        reminder_time = candidates[0].reminder_time
        if reminder_time.microsecond:
            raise ValueError("batch reminder_time must be a whole second")
        if any(
            candidate.occurrence_on != occurrence_on or candidate.reminder_time != reminder_time
            for candidate in candidates
        ):
            raise ValueError("all batch candidates must share one exact civil key")

        await db.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :key_hash)"),
            {
                "namespace": self._signed_int32(self._ADVISORY_NAMESPACE),
                "key_hash": self._advisory_key(occurrence_on, reminder_time),
            },
        )
        candidate_by_id = {candidate.tracker_id: candidate for candidate in candidates}
        tracker_ids = sorted(candidate_by_id)
        result = await db.execute(
            select(Tracker)
            .where(Tracker.id.in_(tracker_ids))
            .order_by(Tracker.id)
            .with_for_update()
        )
        trackers = {tracker.id: tracker for tracker in result.scalars().all()}
        latest_dates = await self._lock_entries_and_latest_dates(db, tracker_ids)

        claimed: list[tuple[Tracker, TrackerBatchCandidate, UUID]] = []
        for tracker_id in tracker_ids:
            tracker = trackers.get(tracker_id)
            candidate = candidate_by_id[tracker_id]
            if (
                tracker is None
                or tracker.deleted_at is not None
                or not self._candidate_is_due(
                    candidate=candidate,
                    tracker=tracker,
                    latest_entry_on=latest_dates.get(tracker_id),
                )
            ):
                continue
            dispatch_id = (
                await db.execute(
                    text(
                        """
                        INSERT INTO microsched.reminder_dispatch
                            (id, subject_type, subject_id, dispatched_on, status,
                             attempt_count, created_at)
                        VALUES (uuidv7(), 'tracker', :tracker_id, :occurrence_on,
                                'pending', 0, NOW())
                        ON CONFLICT (subject_type, subject_id, dispatched_on) DO NOTHING
                        RETURNING id
                        """
                    ),
                    {"tracker_id": tracker_id, "occurrence_on": occurrence_on},
                )
            ).scalar_one_or_none()
            if dispatch_id is not None:
                claimed.append((tracker, candidate, dispatch_id))

        if not claimed:
            await db.commit()
            return None

        max_generation = (
            await db.execute(
                select(func.max(TrackerReminderBatch.generation)).where(
                    TrackerReminderBatch.occurrence_on == occurrence_on,
                    TrackerReminderBatch.reminder_time == reminder_time,
                )
            )
        ).scalar_one()
        batch = TrackerReminderBatch(
            occurrence_on=occurrence_on,
            reminder_time=reminder_time,
            generation=(max_generation or 0) + 1,
        )
        db.add(batch)
        await db.flush()
        for tracker, candidate, dispatch_id in claimed:
            db.add(
                TrackerReminderBatchItem(
                    batch_id=batch.id,
                    dispatch_id=dispatch_id,
                    reminder_mode=candidate.reminder_mode,
                    reminder_interval_days=candidate.reminder_interval_days,
                    reminder_action=candidate.reminder_action,
                    input_mode=tracker.input_mode,
                )
            )
        await db.commit()
        return batch.id

    async def select_current_push_subscriptions(self, db: AsyncSession) -> list[PushSubscription]:
        """Return exactly the rows that still exist at selector snapshot time."""
        result = await db.execute(select(PushSubscription).order_by(PushSubscription.id))
        subscriptions = list(result.scalars().all())
        await db.commit()
        return subscriptions

    async def fanout_current_subscriptions(
        self,
        db: AsyncSession,
        *,
        batch_status: str,
        payload: dict,
        ownership_guard: Callable[[], Awaitable[None]] | None = None,
    ) -> BatchFanout:
        """Send once per current row; terminal batches perform zero selector/network work."""
        if batch_status in self._TERMINAL:
            return BatchFanout()
        subscriptions = await self.select_current_push_subscriptions(db)
        sent = temporary = dead = 0
        for subscription in subscriptions:
            if ownership_guard is not None:
                await ownership_guard()
            outcome = await send_push(
                db,
                subscription,
                payload,
                provider_work_tracker=self._provider_work,
            )
            if outcome == PushResult.SENT:
                sent += 1
            elif outcome == PushResult.TEMPORARY_FAILURE:
                temporary += 1
            else:
                dead += 1
        return BatchFanout(
            current_count=len(subscriptions),
            sent_count=sent,
            temporary_failure_count=temporary,
            dead_count=dead,
        )

    def _build_payload(
        self,
        batch: TrackerReminderBatch,
        active: list[_ActiveBatchMember],
    ) -> dict:
        title = "Hi, it's microSched 🌸"
        if len(active) > 1:
            body = f"Bạn có {len(active)} thông báo từ app"
            url = "/trackers"
        else:
            member = active[0]
            if member.tracker.is_private:
                body = "Bạn có 1 thông báo từ app"
            else:
                try:
                    body = crypto.decrypt(member.tracker.name)
                except Exception:
                    body = "Bạn có 1 thông báo từ app"
                    logger.warning(
                        "tracker_reminder_batch_receipt batch_ref=%s occurrence_on=%s "
                        "reminder_time=%s outcome=public_name_decrypt_fallback",
                        self._batch_ref(batch.id),
                        batch.occurrence_on,
                        batch.reminder_time.isoformat(),
                    )
            url = (
                f"/reminder-confirm?dispatch={member.dispatch.id}"
                if member.item.reminder_action == "confirm_event"
                else "/trackers"
            )
        return {
            "title": title,
            "body": body,
            "url": url,
            "tag": self._notification_tag(batch.id),
        }

    async def _lock_members_for_send(
        self, db: AsyncSession, batch_id: UUID
    ) -> tuple[TrackerReminderBatch | None, list[_ActiveBatchMember]]:
        probe = await db.execute(
            select(TrackerReminderBatchItem.dispatch_id, ReminderDispatch.subject_id)
            .join(ReminderDispatch, ReminderDispatch.id == TrackerReminderBatchItem.dispatch_id)
            .where(TrackerReminderBatchItem.batch_id == batch_id)
            .order_by(TrackerReminderBatchItem.dispatch_id)
        )
        probed = list(probe.all())
        tracker_ids = sorted({subject_id for _dispatch_id, subject_id in probed})
        trackers_result = await db.execute(
            select(Tracker)
            .where(Tracker.id.in_(tracker_ids))
            .order_by(Tracker.id)
            .with_for_update()
        )
        trackers = {tracker.id: tracker for tracker in trackers_result.scalars().all()}
        latest_dates = await self._lock_entries_and_latest_dates(db, tracker_ids)

        batch = (
            await db.execute(
                select(TrackerReminderBatch)
                .where(TrackerReminderBatch.id == batch_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if batch is None:
            return None, []
        items = list(
            (
                await db.execute(
                    select(TrackerReminderBatchItem)
                    .where(TrackerReminderBatchItem.batch_id == batch_id)
                    .order_by(TrackerReminderBatchItem.dispatch_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        dispatch_result = await db.execute(
            select(ReminderDispatch)
            .where(ReminderDispatch.id.in_([item.dispatch_id for item in items]))
            .order_by(ReminderDispatch.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        dispatches = {dispatch.id: dispatch for dispatch in dispatch_result.scalars().all()}

        active: list[_ActiveBatchMember] = []
        for item in items:
            dispatch = dispatches.get(item.dispatch_id)
            if dispatch is None:
                item.state = "cancelled"
                continue
            tracker = trackers.get(dispatch.subject_id)
            valid = False
            if tracker is not None and tracker.deleted_at is None:
                candidate = TrackerBatchCandidate(
                    tracker_id=tracker.id,
                    occurrence_on=batch.occurrence_on,
                    reminder_time=batch.reminder_time,
                    reminder_mode=item.reminder_mode,
                    reminder_interval_days=item.reminder_interval_days,
                    reminder_action=item.reminder_action,
                )
                valid = tracker.input_mode == item.input_mode and self._candidate_is_due(
                    candidate=candidate,
                    tracker=tracker,
                    latest_entry_on=latest_dates.get(tracker.id),
                )
            if not valid:
                item.state = "cancelled"
                dispatch.status = "cancelled"
            elif item.state == "pending" and dispatch.status == "pending":
                active.append(_ActiveBatchMember(item=item, dispatch=dispatch, tracker=tracker))
        return batch, active

    async def _lock_terminal_rows(
        self, db: AsyncSession, batch_id: UUID
    ) -> tuple[TrackerReminderBatch, list[tuple[TrackerReminderBatchItem, ReminderDispatch]]]:
        """Lock Batch → Items → Dispatches explicitly in the global order."""
        batch = (
            await db.execute(
                select(TrackerReminderBatch)
                .where(TrackerReminderBatch.id == batch_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        items = list(
            (
                await db.execute(
                    select(TrackerReminderBatchItem)
                    .where(TrackerReminderBatchItem.batch_id == batch_id)
                    .order_by(TrackerReminderBatchItem.dispatch_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        dispatch_result = await db.execute(
            select(ReminderDispatch)
            .where(ReminderDispatch.id.in_([item.dispatch_id for item in items]))
            .order_by(ReminderDispatch.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        dispatches = {dispatch.id: dispatch for dispatch in dispatch_result.scalars().all()}
        return batch, [
            (item, dispatches[item.dispatch_id]) for item in items if item.dispatch_id in dispatches
        ]

    async def _mirror_terminal(
        self,
        db: AsyncSession,
        *,
        batch_id: UUID,
        tracker_ids: list[UUID],
        status_value: str,
    ) -> None:
        if tracker_ids:
            await db.execute(
                select(Tracker)
                .where(Tracker.id.in_(sorted(tracker_ids)))
                .order_by(Tracker.id)
                .with_for_update()
            )
        batch, rows = await self._lock_terminal_rows(db, batch_id)
        batch.status = status_value
        for item, dispatch in rows:
            if item.state != "cancelled":
                item.state = status_value
                dispatch.status = status_value
        await db.commit()

    async def dispatch_batch(
        self,
        db: AsyncSession,
        batch_id: UUID,
        *,
        telemetry: Callable[[DispatchTelemetry], None] | None = None,
        ownership_guard: Callable[[], Awaitable[None]] | None = None,
    ) -> DispatchOutcome:
        """Revalidate, consume one attempt, fan out once, and mirror terminal state."""
        lock = self._delivery_locks.setdefault(batch_id, asyncio.Lock())
        async with lock:
            probe = (
                await db.execute(
                    select(TrackerReminderBatch).where(TrackerReminderBatch.id == batch_id)
                )
            ).scalar_one_or_none()
            if probe is None:
                raise RuntimeError("tracker reminder batch disappeared")
            if probe.status in self._TERMINAL:
                return DispatchOutcome(probe.status)

            batch, active = await self._lock_members_for_send(db, batch_id)
            if batch is None:
                raise RuntimeError("tracker reminder batch disappeared")
            if batch.status in self._TERMINAL:
                await db.commit()
                return DispatchOutcome(batch.status)
            if not active:
                batch.status = "cancelled"
                await db.commit()
                return DispatchOutcome.CANCELLED
            if batch.attempt_count >= 4:
                for member in active:
                    member.item.state = "exhausted"
                    member.dispatch.status = "exhausted"
                batch.status = "exhausted"
                await db.commit()
                logger.warning(
                    "tracker_reminder_batch_receipt batch_ref=%s occurrence_on=%s "
                    "reminder_time=%s attempt_count=%d sent_count=0 "
                    "temporary_failure_count=0 dead_count=0 outcome=manual_required",
                    self._batch_ref(batch_id),
                    batch.occurrence_on,
                    batch.reminder_time.isoformat(),
                    batch.attempt_count,
                )
                return DispatchOutcome.EXHAUSTED

            payload = self._build_payload(batch, active)
            tracker_ids = [member.tracker.id for member in active]
            batch.attempt_count += 1
            batch.last_attempt_at = datetime.now(UTC)
            attempt_count = batch.attempt_count
            await db.commit()
            if telemetry is not None:
                telemetry(DispatchTelemetry(attempt_count=attempt_count))
            if ownership_guard is not None:
                await ownership_guard()

            fanout = await self.fanout_current_subscriptions(
                db,
                batch_status="pending",
                payload=payload,
                ownership_guard=ownership_guard,
            )
            if fanout.sent_count:
                terminal = "sent"
                outcome = DispatchOutcome.SENT
            elif fanout.temporary_failure_count and attempt_count < 4:
                await db.commit()
                outcome = DispatchOutcome.TEMPORARY_FAILURE
                if telemetry is not None:
                    telemetry(DispatchTelemetry(attempt_count=attempt_count, outcome=outcome))
                return outcome
            elif fanout.temporary_failure_count:
                terminal = "exhausted"
                outcome = DispatchOutcome.EXHAUSTED
            else:
                terminal = "no_device"
                outcome = DispatchOutcome.NO_DEVICE

            await self._mirror_terminal(
                db,
                batch_id=batch_id,
                tracker_ids=tracker_ids,
                status_value=terminal,
            )
            if terminal == "exhausted":
                logger.warning(
                    "tracker_reminder_batch_receipt batch_ref=%s occurrence_on=%s "
                    "reminder_time=%s attempt_count=%d sent_count=%d "
                    "temporary_failure_count=%d dead_count=%d outcome=manual_required",
                    self._batch_ref(batch_id),
                    batch.occurrence_on,
                    batch.reminder_time.isoformat(),
                    attempt_count,
                    fanout.sent_count,
                    fanout.temporary_failure_count,
                    fanout.dead_count,
                )
            if telemetry is not None:
                telemetry(DispatchTelemetry(attempt_count=attempt_count, outcome=outcome))
            return outcome


async def confirm_reminder_dispatch(
    db: AsyncSession,
    dispatch_id: UUID,
    entry_id: UUID,
    occurred_at: datetime,
    auth: AuthSession,
) -> tuple[object, bool]:
    """Confirm an eligible tracker reminder and idempotently record an Entry.

    ``auth`` is always the real verified session from the router. The private
    unlock fact is derived here, at the domain boundary, so no caller can
    fabricate a gate-only session or proxy device state through a boolean.
    """
    now_utc = datetime.now(UTC)
    is_private_unlocked = bool(auth.private_until and auth.private_until > now_utc)

    # Probe identity without a row lock.  The 035A global lock order is
    # tracker → dispatch → entry, so taking this dispatch lock first would
    # deadlock against pre-send code that already owns the tracker row.
    probe_stmt = select(ReminderDispatch).where(ReminderDispatch.id == dispatch_id)
    res = await db.execute(probe_stmt)
    dispatch = res.scalar_one_or_none()

    if dispatch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reminder dispatch not found",
        )

    if dispatch.subject_type != "tracker":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only tracker reminders can be confirmed",
        )

    # A confirmation is an occurrence-level idempotency key.  This fast path
    # deliberately happens before reading the tracker: the entry remains the
    # original (possibly soft-deleted) record even if the tracker was later
    # changed or soft-deleted.  Do not use the normal readable() helper here.
    if dispatch.confirmed_entry_id is not None:
        entry_stmt = select(Entry).where(Entry.id == dispatch.confirmed_entry_id)
        entry_res = await db.execute(entry_stmt)
        existing_entry = entry_res.scalar_one_or_none()
        if existing_entry is not None:
            return existing_entry, False

    # Lock the parent before the dispatch and then re-read the dispatch under
    # that order.  No writer may commit a freshness/configuration mutation
    # between this boundary and the entry creation below.
    tracker_stmt = (
        select(Tracker)
        .where(Tracker.id == dispatch.subject_id, Tracker.deleted_at.is_(None))
        .with_for_update()
    )
    tracker_res = await db.execute(tracker_stmt)
    tracker = tracker_res.scalar_one_or_none()

    if tracker is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tracker has been deleted or is unavailable",
        )

    dispatch_stmt = (
        select(ReminderDispatch)
        .where(ReminderDispatch.id == dispatch_id)
        .with_for_update()
        # The unlocked identity probe above may already have placed an old
        # row in this session's identity map.  The lock-order re-read is the
        # authority boundary, so it must overwrite that snapshot after a
        # competing confirmation commits while this request waits on Tracker.
        .execution_options(populate_existing=True)
    )
    dispatch_res = await db.execute(dispatch_stmt)
    dispatch = dispatch_res.scalar_one_or_none()
    if dispatch is None or dispatch.subject_type != "tracker" or dispatch.subject_id != tracker.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reminder dispatch changed or is unavailable",
        )

    # Re-check the fast path after the ordered lock.  Another confirmation may
    # have committed between the unlocked probe and the tracker lock.
    if dispatch.confirmed_entry_id is not None:
        entry_stmt = select(Entry).where(Entry.id == dispatch.confirmed_entry_id)
        entry_res = await db.execute(entry_stmt)
        existing_entry = entry_res.scalar_one_or_none()
        if existing_entry is not None:
            return existing_entry, False

    # Only a not-yet-terminal occurrence can create an entry.  Unknown future
    # statuses intentionally fail closed so rollback to this binary cannot
    # reopen cancelled/exhausted links created by a later schema release.
    if dispatch.status not in {"pending", "sent"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reminder dispatch is no longer eligible for confirmation",
        )

    # Write gate check
    if tracker.is_private and not is_private_unlocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PRIVATE_UNLOCK_REQUIRED",
                "message": "Unlock private mode to confirm this tracker reminder",
            },
        )

    action = tracker.reminder_action
    if (
        action is None
        and tracker.kind == "health"
        and tracker.input_mode == "event"
        and tracker.reminder_time is not None
        and tracker.reminder_mode is None
        and tracker.reminder_interval_days is None
    ):
        # Old notifications remain confirmable through the rolling deploy window.
        action = "confirm_event"
    if action != "confirm_event" or tracker.input_mode != "event":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tracker configuration is no longer eligible for one-tap reminder confirmation",
        )

    # Create the entry through the 011a helper with its real contract:
    # ``create_entry(db, auth, payload: EntryCreate, *, subscription_id=None)``
    # returns ``(entry_id, created)`` — the confirmation link is the returned
    # id, not an attribute of a model object (F1).
    entry_payload = EntryCreate(
        id=entry_id,
        tracker_id=tracker.id,
        occurred_at=occurred_at,
    )
    confirmed_entry_id, created = await TrackerStore().create_entry(db, auth, entry_payload)

    dispatch.confirmed_entry_id = confirmed_entry_id
    dispatch.confirmed_at = datetime.now(UTC)
    await db.commit()

    entry_stmt = select(Entry).where(Entry.id == confirmed_entry_id)
    entry_res = await db.execute(entry_stmt)
    entry = entry_res.scalar_one()
    return entry, created
