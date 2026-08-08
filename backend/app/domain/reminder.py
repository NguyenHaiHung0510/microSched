"""Domain logic for reminder payloads, dispatcher execution, and confirmation."""

import logging
from datetime import UTC, date, datetime, timedelta, timezone
from enum import StrEnum
from typing import Callable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    AuthSession,
    Entry,
    PushSubscription,
    ReminderDispatch,
    Subscription,
    Tracker,
)
from app.domain.push import PushResult, send_push
from app.domain.tracker import EntryCreate, TrackerStore

logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))


class DispatchOutcome(StrEnum):
    """Outcome status returned by the reminder dispatcher."""

    SENT = "sent"
    TEMPORARY_FAILURE = "temporary_failure"
    NO_DEVICE = "no_device"
    EXHAUSTED = "exhausted"


def build_medication_payload(tracker: Tracker, dispatch_id: UUID) -> dict:
    """Build the public-safe Web Push notification payload for a medication tracker."""
    title = "Nhắc nhở microSched"

    # Privacy rule: if reminder_text is provided by user, use it directly (public surface).
    # Otherwise, if tracker is private, MUST NOT reveal tracker name or ciphertext.
    if tracker.reminder_text and tracker.reminder_text.strip():
        body = tracker.reminder_text.strip()
    elif tracker.is_private:
        body = "Đã tới giờ uống thuốc"
    else:
        name = tracker.name if hasattr(tracker, "name") else "thuốc"
        body = f"Đã tới giờ: {name}"

    url = f"/reminder-confirm?dispatch={dispatch_id}"
    return {"title": title, "body": body, "url": url}


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

    is_private = (parent_tracker is not None and parent_tracker.is_private) or (
        subscription.name and subscription.name.startswith("enc:v1:")
    )

    if is_private:
        body = f"Một đăng ký sắp hết hạn trong {days_left} ngày"
    else:
        name = subscription.name if hasattr(subscription, "name") else "dịch vụ"
        body = f"Đăng ký {name} sắp hết hạn trong {days_left} ngày"

    url = f"/subscription?highlight={subscription.id}"
    return {"title": title, "body": body, "url": url}


class ReminderDispatcher:
    """Core dispatcher for claiming reminder occurrences and sending Web Push."""

    @staticmethod
    def _lock_key(subject_type: str, subject_id: UUID, dispatched_on: date) -> str:
        """Stable advisory-lock key for one occurrence (serializes senders)."""
        return f"{subject_type}:{subject_id}:{dispatched_on.isoformat()}"

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
    ) -> DispatchOutcome:
        """Execute dispatch for a single reminder item following the 011b state machine.

        A session-level PostgreSQL advisory lock keyed on the occurrence is
        acquired BEFORE the claim so two workers can never send the same
        occurrence in parallel (F12 — claim/commit alone is not enough: worker
        B would claim attempt #2 after worker A commits attempt #1 and both
        would be inside the network loop at the same time). The lock is held
        across the send-loop commits (session-level, not transaction) and
        released in ``finally``.
        """
        lock_key = self._lock_key(subject_type, subject_id, dispatched_on)
        await db.execute(
            text("SELECT pg_advisory_lock(hashtextextended(:key, 0))"),
            {"key": lock_key},
        )
        try:
            dispatch = await self.claim_or_get_dispatch(db, subject_type, subject_id, dispatched_on)

            if dispatch.status in (DispatchOutcome.SENT, DispatchOutcome.NO_DEVICE):
                return DispatchOutcome(dispatch.status)

            if dispatch.attempt_count >= 4:
                return DispatchOutcome.EXHAUSTED

            # Claim delivery attempt
            dispatch.attempt_count += 1
            dispatch.last_attempt_at = datetime.now(UTC)
            await db.commit()

            # Build payload with stable dispatch ID
            payload = payload_builder(dispatch.id)

            # Query all active push subscriptions
            sub_stmt = select(PushSubscription)
            sub_result = await db.execute(sub_stmt)
            subscriptions = list(sub_result.scalars().all())

            if not subscriptions:
                dispatch.status = DispatchOutcome.NO_DEVICE
                await db.commit()
                return DispatchOutcome.NO_DEVICE

            sent_count = 0
            temp_fail_count = 0
            dead_count = 0

            for sub in subscriptions:
                res = await send_push(db, sub, payload)
                if res == PushResult.SENT:
                    sent_count += 1
                elif res == PushResult.TEMPORARY_FAILURE:
                    temp_fail_count += 1
                elif res == PushResult.DEAD_SUBSCRIPTION:
                    dead_count += 1

            if sent_count >= 1:
                dispatch.status = DispatchOutcome.SENT
                await db.commit()
                return DispatchOutcome.SENT

            if temp_fail_count >= 1:
                # Remain pending for retry with same dispatch ID
                await db.commit()
                return DispatchOutcome.TEMPORARY_FAILURE

            # Only dead subscriptions or list emptied
            dispatch.status = DispatchOutcome.NO_DEVICE
            await db.commit()
            return DispatchOutcome.NO_DEVICE
        finally:
            # Clear any aborted-transaction state first: a session-level
            # advisory lock survives a failed transaction, and the unlock must
            # run in a fresh one or it would raise InFailedSQLTransactionError
            # and leave the lock held on the pooled connection — blocking every
            # future dispatch of this occurrence.
            try:
                await db.rollback()
            except Exception:
                pass
            try:
                await db.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                    {"key": lock_key},
                )
                await db.commit()
            except Exception:
                # Closing the session releases the lock server-side.
                await db.rollback()


dispatcher = ReminderDispatcher()


async def confirm_reminder_dispatch(
    db: AsyncSession,
    dispatch_id: UUID,
    entry_id: UUID,
    occurred_at: datetime,
    is_private_unlocked: bool = False,
    auth: AuthSession | None = None,
) -> tuple[object, bool]:
    """Confirm a medication reminder dispatch and idempotently record an Entry.

    ``auth`` is the real verified session from the router. When a caller does
    not pass it, a gate-only session is built from ``is_private_unlocked`` —
    the same fact the router already verified — so the ``readable()`` call
    inside ``TrackerStore.create_entry`` sees exactly the tracker rows the
    session may write.
    """
    if auth is None:
        now = datetime.now(UTC)
        auth = AuthSession(
            token_hash="",
            user_email="",
            last_seen_at=now,
            expires_at=now + timedelta(minutes=5),
            private_until=(now + timedelta(minutes=5)) if is_private_unlocked else None,
        )

    # Lock dispatch row
    stmt = select(ReminderDispatch).where(ReminderDispatch.id == dispatch_id).with_for_update()
    res = await db.execute(stmt)
    dispatch = res.scalar_one_or_none()

    if dispatch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reminder dispatch not found",
        )

    # Idempotent check: already confirmed
    if dispatch.confirmed_entry_id is not None:
        entry_stmt = select(Entry).where(Entry.id == dispatch.confirmed_entry_id)
        entry_res = await db.execute(entry_stmt)
        existing_entry = entry_res.scalar_one_or_none()
        if existing_entry is not None:
            return existing_entry, False

    if dispatch.subject_type != "tracker":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only tracker reminders can be confirmed",
        )

    # Fetch parent tracker
    tracker_stmt = select(Tracker).where(
        Tracker.id == dispatch.subject_id, Tracker.deleted_at.is_(None)
    )
    tracker_res = await db.execute(tracker_stmt)
    tracker = tracker_res.scalar_one_or_none()

    if tracker is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tracker has been deleted or is unavailable",
        )

    # Write gate check
    if tracker.is_private and not is_private_unlocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PRIVATE_UNLOCK_REQUIRED",
                "message": "Unlock private mode to confirm this medication reminder",
            },
        )

    if tracker.kind != "health" or tracker.input_mode != "event":
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
    return entry, True
