"""Bounded one-shot delivery using the existing scheduler ownership and push seam."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import OneShotReminder, PushSubscription
from app.domain.one_shot import LATE_WINDOW, get_source, identity, source_open
from app.domain.push import ProviderWorkTracker, PushResult, send_push

BACKOFF = (30, 120, 600)


class OneShotDispatcher:
    def __init__(self):
        self.provider_work = ProviderWorkTracker()

    async def _current(self, db, reminder_id, revision):
        probe = await db.get(OneShotReminder, reminder_id, populate_existing=True)
        if probe is None:
            return None
        kind, source_id = identity(probe)
        source = await get_source(db, kind, source_id, lock=True)
        row = (
            await db.execute(
                select(OneShotReminder)
                .where(OneShotReminder.id == reminder_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if row is None or row.revision != revision or row.status not in ("pending", "sending"):
            return None
        if source is None or not source_open(source):
            row.status = "cancelled"
            row.revision += 1
            return None
        return row

    async def dispatch(
        self,
        db: AsyncSession,
        reminder_id: UUID,
        revision: int,
        *,
        now: datetime | None = None,
        ownership_guard=None,
    ):
        def clock():
            return now or datetime.now(UTC)

        row = await self._current(db, reminder_id, revision)
        if row is None:
            await db.commit()
            return
        due, deadline = row.due_at, row.due_at + LATE_WINDOW
        if clock() < due or (row.next_attempt_at and clock() < row.next_attempt_at):
            await db.commit()
            return
        if clock() > deadline:
            row.status = "missed"
            await db.commit()
            return
        if row.attempt_count >= 4:
            row.status = "failed"
            await db.commit()
            return
        subscriptions = list(
            (
                await db.execute(
                    select(PushSubscription).order_by(PushSubscription.created_at).limit(100)
                )
            ).scalars()
        )
        if not subscriptions:
            row.status = "no_device"
            await db.commit()
            return
        row.status = "sending"
        row.attempt_count += 1
        attempt = row.attempt_count
        row.last_attempt_at = clock()
        row.next_attempt_at = min(
            deadline + timedelta(microseconds=1),
            clock() + timedelta(seconds=BACKOFF[min(attempt - 1, 2)]),
        )
        await db.commit()

        # Generic even for public sources: a concurrent public -> private change
        # can never leak previously assembled prose onto the lock screen.
        payload = {
            "title": "Nhắc nhở microSched",
            "body": "Đã đến giờ nhắc bạn đã đặt.",
            "url": f"/?reminders=1&reminder={reminder_id}",
            "tag": f"one-shot-{reminder_id}",
        }
        sent, temporary = False, False
        for subscription in subscriptions:
            current = await self._current(db, reminder_id, revision)
            if current is None:
                await db.commit()
                return
            if clock() > deadline:
                break
            await db.commit()
            if ownership_guard:
                await ownership_guard()
            result = await send_push(
                db,
                subscription,
                payload,
                timeout_seconds=min(20.0, max(1.0, (deadline - clock()).total_seconds())),
                provider_work_tracker=self.provider_work,
                ttl_seconds=max(0, int((deadline - clock()).total_seconds())),
            )
            sent |= result == PushResult.SENT
            temporary |= result == PushResult.TEMPORARY_FAILURE
        current = await self._current(db, reminder_id, revision)
        if current is None:
            await db.commit()
            return
        if sent:
            current.status = "sent"
            current.sent_at = clock()
        elif clock() > deadline:
            current.status = "missed"
        elif temporary:
            current.status = "pending" if attempt < 4 else "failed"
        else:
            current.status = "no_device"
        await db.commit()
