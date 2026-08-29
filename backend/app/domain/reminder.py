"""Domain logic for reminder payloads, dispatcher execution, and confirmation."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from enum import StrEnum
from typing import Awaitable, Callable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.domain.models import (
    AuthSession,
    Entry,
    PushSubscription,
    ReminderDispatch,
    Subscription,
    Tracker,
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


@dataclass(frozen=True, slots=True)
class DispatchTelemetry:
    """Durable dispatcher state exposed to an optional in-process observer."""

    attempt_count: int
    outcome: DispatchOutcome | None = None


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
