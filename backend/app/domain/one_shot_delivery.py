"""Bounded one-shot delivery using the existing scheduler ownership and push seam."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    CalendarEvent,
    DayAnnotation,
    OneShotReminder,
    PushSubscription,
    Task,
    TaskItem,
    Tracker,
)
from app.domain.notification_content import PRIVATE_BODY, PRIVATE_TITLE, public_text
from app.domain.one_shot import LATE_WINDOW, VN, get_source, identity, source_open, source_title
from app.domain.push import ProviderWorkTracker, PushResult, send_push

BACKOFF = (30, 120, 600)


def build_one_shot_payload(row, source, checklist=()) -> dict:
    payload = {
        "title": PRIVATE_TITLE,
        "body": PRIVATE_BODY,
        "url": f"/?reminders=1&reminder={row.id}",
        "tag": f"one-shot-{row.id}",
    }
    if getattr(source, "is_private", False):
        return payload
    label = source_title(source)
    payload["title"] = (
        f"Mốc ngày: {label}" if isinstance(source, DayAnnotation) else f"Nhắc: {label}"
    )
    details = [f"Giờ nhắc: {row.due_at.astimezone(VN):%H:%M %d/%m/%Y}"]
    if isinstance(source, Task):
        details.append(public_text(source.body_md))
        if source.due_precision == "date" and source.due_on:
            details.append(f"Hạn: {source.due_on:%d/%m/%Y}")
        elif source.due_at:
            details.append(f"Hạn: {source.due_at.astimezone(VN):%H:%M %d/%m/%Y}")
        details.extend(checklist)
    elif isinstance(source, CalendarEvent):
        if source.all_day:
            details.append(f"Cả ngày: {source.starts_at.astimezone(VN):%d/%m/%Y}")
        else:
            details.append(
                f"{source.starts_at.astimezone(VN):%H:%M %d/%m/%Y}"
                f" – {source.ends_at.astimezone(VN):%H:%M %d/%m/%Y}"
            )
        details.extend([public_text(source.location), public_text(source.description_md)])
    elif isinstance(source, Tracker):
        details.append(public_text(source.reminder_text))
    elif isinstance(source, DayAnnotation):
        period = f"{source.starts_on:%d/%m/%Y}"
        if source.ends_on != source.starts_on:
            period += f" – {source.ends_on:%d/%m/%Y}"
        details.extend([period, public_text(source.note_md)])
    payload["body"] = "\n".join(detail for detail in details if detail)
    return payload


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

        sent, temporary = False, False
        for subscription in subscriptions:
            if ownership_guard:
                await ownership_guard()
            current = await self._current(db, reminder_id, revision)
            if current is None:
                await db.commit()
                return
            if clock() > deadline:
                break
            kind, source_id = identity(current)
            source = await get_source(db, kind, source_id, lock=True)
            checklist = []
            if isinstance(source, Task) and not source.is_private:
                items = (
                    await db.scalars(
                        select(TaskItem)
                        .where(TaskItem.task_id == source.id, TaskItem.deleted_at.is_(None))
                        .order_by(TaskItem.position, TaskItem.created_at, TaskItem.id)
                    )
                ).all()
                checklist = [
                    ("☑ " if item.is_completed else "☐ ") + public_text(item.content)
                    for item in items
                ]
            # Rebuild from the current classification for each provider handoff.
            # Already handed-off public content cannot be recalled by a later privacy edit.
            payload = build_one_shot_payload(current, source, checklist)
            await db.commit()
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
