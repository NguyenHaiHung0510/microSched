"""Real PostgreSQL source triggers, visibility, concurrency and provider recovery."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database_urls import async_postgres_url
from app.domain.models import AuthSession, OneShotReminder, PushSubscription, Task
from app.domain.one_shot import ReminderWrite, list_reminders, save_reminder
from app.domain.one_shot_delivery import OneShotDispatcher
from app.domain.push import PushResult

pytestmark = pytest.mark.pg


async def scenario(dsn, exercise):
    engine = create_async_engine(async_postgres_url(dsn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    auth = AuthSession(private_until=now + timedelta(hours=1))
    task_id = None
    try:
        async with maker() as db:
            task = Task(
                title="Synthetic reminder source",
                status="open",
                due_precision="datetime",
                due_at=now + timedelta(days=2),
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
            task_id = task.id
            await exercise(db, task, auth, now, maker)
    finally:
        if task_id:
            async with maker() as db:
                await db.execute(delete(Task).where(Task.id == task_id))
                await db.commit()
        await engine.dispose()


def test_source_reschedule_cancel_restore_and_sent_terminal(pg_dsn):
    async def exercise(db, task, auth, now, maker):
        result = await save_reminder(
            db, auth, "task", task.id, ReminderWrite(mode="relative", offset_minutes=-60)
        )
        await db.commit()
        await db.execute(
            text("UPDATE microsched.task SET due_at = :due WHERE id = :id"),
            {"due": now + timedelta(days=3), "id": task.id},
        )
        await db.commit()
        row = await db.get(OneShotReminder, result.id, populate_existing=True)
        assert row.due_at == now + timedelta(days=3, hours=-1)
        assert row.revision == 2 and row.status == "pending"
        await db.execute(
            text("UPDATE microsched.task SET due_at = :due WHERE id = :id"),
            {"due": now, "id": task.id},
        )
        await db.commit()
        await db.refresh(row)
        assert row.status == "needs_reschedule"
        await db.execute(
            text("UPDATE microsched.task SET status='completed' WHERE id=:id"), {"id": task.id}
        )
        await db.commit()
        await db.refresh(row)
        assert row.status == "cancelled"
        await db.execute(
            text("UPDATE microsched.task SET status='open' WHERE id=:id"), {"id": task.id}
        )
        await db.commit()
        await db.refresh(row)
        assert row.status == "cancelled"
        row.status = "sent"
        await db.commit()
        await db.execute(
            text("UPDATE microsched.task SET due_at=:due WHERE id=:id"),
            {"due": now + timedelta(days=5), "id": task.id},
        )
        await db.commit()
        await db.refresh(row)
        assert row.status == "sent"

    asyncio.run(scenario(pg_dsn, exercise))


def test_absolute_unchanged_and_duplicate_or_stale_write_rejected(pg_dsn):
    async def exercise(db, task, auth, now, maker):
        payload = ReminderWrite(mode="absolute", due_at=now + timedelta(hours=1))
        result = await save_reminder(db, auth, "task", task.id, payload)
        await db.commit()
        with pytest.raises(HTTPException) as error:
            await save_reminder(db, auth, "task", task.id, payload)
        assert error.value.status_code == 409
        await db.rollback()
        await db.execute(
            text("UPDATE microsched.task SET due_at=:due WHERE id=:id"),
            {"due": now + timedelta(days=5), "id": result.source_id},
        )
        await db.commit()
        row = await db.get(OneShotReminder, result.id, populate_existing=True)
        assert row.due_at == payload.due_at and row.revision == 1

    asyncio.run(scenario(pg_dsn, exercise))


def test_locked_list_cannot_load_or_decrypt_private_parent(pg_dsn, monkeypatch):
    def forbidden_decrypt(_value):
        raise AssertionError("private parent reached decrypt while locked")

    monkeypatch.setattr("app.domain.one_shot.crypto.decrypt", forbidden_decrypt)

    async def exercise(db, task, auth, now, maker):
        row = await save_reminder(
            db,
            auth,
            "task",
            task.id,
            ReminderWrite(mode="absolute", due_at=now + timedelta(hours=1)),
        )
        await db.commit()
        # Deliberately invalid ciphertext sentinel: any attempted decrypt fails.
        await db.execute(
            text(
                "UPDATE microsched.task SET is_private=true, title='enc:v1:sentinel' WHERE id=:id"
            ),
            {"id": task.id},
        )
        await db.commit()
        locked = AuthSession(private_until=None)
        listing = await list_reminders(db, locked, kind="task", source_id=task.id, section="all")
        assert listing["items"] == []
        with pytest.raises(HTTPException) as error:
            await save_reminder(
                db,
                locked,
                "task",
                task.id,
                ReminderWrite(
                    mode="absolute",
                    due_at=now + timedelta(hours=2),
                    expected_id=row.id,
                    expected_revision=1,
                ),
            )
        assert error.value.status_code == 404

    asyncio.run(scenario(pg_dsn, exercise))


@pytest.mark.parametrize(
    "late_seconds, expected", [(2699, "no_device"), (2700, "no_device"), (2701, "missed")]
)
def test_late_window_inclusive_without_device(pg_dsn, late_seconds, expected):
    async def exercise(db, task, auth, now, maker):
        row = OneShotReminder(
            task_id=task.id, mode="absolute", due_at=now - timedelta(seconds=late_seconds)
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        await OneShotDispatcher().dispatch(db, row.id, 1, now=now)
        await db.refresh(row)
        assert row.status == expected

    asyncio.run(scenario(pg_dsn, exercise))


def test_provider_retry_ttl_and_stale_revision(pg_dsn, monkeypatch):
    calls = []

    async def fake_push(db, subscription, payload, **kwargs):
        calls.append((payload, kwargs["ttl_seconds"]))
        return PushResult.TEMPORARY_FAILURE if len(calls) == 1 else PushResult.SENT

    monkeypatch.setattr("app.domain.one_shot_delivery.send_push", fake_push)

    async def exercise(db, task, auth, now, maker):
        # Synthetic provider never leaves the process.
        subscription = PushSubscription(
            endpoint="https://push.example.test/047", p256dh="synthetic", auth="synthetic"
        )
        db.add(subscription)
        row = OneShotReminder(task_id=task.id, mode="absolute", due_at=now)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        await db.refresh(subscription)
        try:
            dispatcher = OneShotDispatcher()
            await dispatcher.dispatch(db, row.id, 999, now=now)
            assert calls == []
            await dispatcher.dispatch(db, row.id, 1, now=now)
            await db.refresh(row)
            assert row.status == "pending" and row.attempt_count == 1
            await dispatcher.dispatch(db, row.id, 1, now=now + timedelta(seconds=29))
            assert len(calls) == 1
            await dispatcher.dispatch(db, row.id, 1, now=now + timedelta(seconds=30))
            await db.refresh(row)
            assert row.status == "sent" and row.attempt_count == 2
            assert [ttl for _, ttl in calls] == [2700, 2670]
            assert all(task.title not in str(payload) for payload, _ in calls)
            await dispatcher.dispatch(db, row.id, 1, now=now + timedelta(seconds=60))
            assert len(calls) == 2
        finally:
            await db.execute(delete(PushSubscription).where(PushSubscription.id == subscription.id))
            await db.commit()

    asyncio.run(scenario(pg_dsn, exercise))


def test_concurrent_creates_serialize_on_parent(pg_dsn):
    async def exercise(db, task, auth, now, maker):
        task_id = task.id

        async def create():
            async with maker() as session:
                try:
                    await save_reminder(
                        session,
                        auth,
                        "task",
                        task_id,
                        ReminderWrite(mode="absolute", due_at=now + timedelta(hours=1)),
                    )
                    await session.commit()
                    return 200
                except HTTPException as error:
                    await session.rollback()
                    return error.status_code

        assert sorted(await asyncio.gather(create(), create())) == [200, 409]
        rows = (
            (
                await db.execute(
                    select(OneShotReminder).where(
                        OneShotReminder.task_id == task_id, OneShotReminder.status == "pending"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1

    asyncio.run(scenario(pg_dsn, exercise))


def test_calendar_relative_date_and_source_deletion(pg_dsn):
    from datetime import time

    from app.domain.models import CalendarEvent, CalendarSource

    async def exercise(db, task, auth, now, maker):
        source = CalendarSource(name=f"047-{task.id}", kind="manual")
        db.add(source)
        await db.flush()
        event = CalendarEvent(
            source_id=source.id,
            title="Synthetic all-day",
            starts_at=now + timedelta(days=2),
            ends_at=now + timedelta(days=3),
            all_day=True,
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        try:
            result = await save_reminder(
                db,
                auth,
                "event",
                event.id,
                ReminderWrite(mode="relative", offset_minutes=-60, anchor_time=time(9)),
            )
            await db.commit()
            original_due = result.due_at
            await db.execute(
                text(
                    "UPDATE microsched.calendar_event SET starts_at=starts_at + "
                    "interval '1 day', ends_at=ends_at + interval '1 day' WHERE id=:id"
                ),
                {"id": event.id},
            )
            await db.commit()
            row = await db.get(OneShotReminder, result.id, populate_existing=True)
            assert row.due_at == original_due + timedelta(days=1)
            await db.delete(event)
            await db.commit()
            assert await db.get(OneShotReminder, result.id, populate_existing=True) is None
        finally:
            await db.execute(delete(CalendarSource).where(CalendarSource.id == source.id))
            await db.commit()

    asyncio.run(scenario(pg_dsn, exercise))


def test_recovery_exhaustion_and_cancel_during_provider_handoff(pg_dsn, monkeypatch):
    calls = []

    async def failure(db, subscription, payload, **kwargs):
        calls.append(payload)
        return PushResult.TEMPORARY_FAILURE

    monkeypatch.setattr("app.domain.one_shot_delivery.send_push", failure)

    async def exercise(db, task, auth, now, maker):
        sub = PushSubscription(
            endpoint=f"https://push.example.test/{task.id}", p256dh="fake", auth="fake"
        )
        row = OneShotReminder(task_id=task.id, mode="absolute", due_at=now)
        db.add_all([sub, row])
        await db.commit()
        await db.refresh(sub)
        await db.refresh(row)
        try:
            for seconds in [0, 30, 150, 750, 1400]:
                # A new dispatcher each time exercises durable recovery rather than RAM history.
                await OneShotDispatcher().dispatch(
                    db, row.id, 1, now=now + timedelta(seconds=seconds)
                )
            await db.refresh(row)
            assert len(calls) == 4 and row.status == "failed" and row.attempt_count == 4
            row.status = "pending"
            row.attempt_count = 0
            row.next_attempt_at = None
            await db.commit()

            async def handoff(db, subscription, payload, **kwargs):
                async with maker() as writer:
                    await writer.execute(
                        text("UPDATE microsched.task SET status='completed' WHERE id=:id"),
                        {"id": task.id},
                    )
                    await writer.commit()
                return PushResult.SENT

            monkeypatch.setattr("app.domain.one_shot_delivery.send_push", handoff)
            await OneShotDispatcher().dispatch(db, row.id, 1, now=now)
            await db.refresh(row)
            assert row.status == "cancelled" and row.revision == 2
        finally:
            await db.execute(delete(PushSubscription).where(PushSubscription.id == sub.id))
            await db.commit()

    asyncio.run(scenario(pg_dsn, exercise))


def test_timer_snapshot_and_dispatch_use_one_shot_path(pg_dsn):
    from app.core.cron_timer import CronTimer, ScheduleKind

    async def exercise(db, task, auth, now, maker):
        row = OneShotReminder(task_id=task.id, mode="absolute", due_at=now)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        timer = CronTimer(maker)
        await timer.load_snapshot(db, now=now)
        item = next(entry[-1] for entry in timer._heap if entry[-1].subject_id == row.id)
        assert item.kind == ScheduleKind.ONE_SHOT
        await db.rollback()
        await timer._process_due_item(item, now=now)
        updated = await db.get(OneShotReminder, item.subject_id, populate_existing=True)
        assert updated.status == "no_device" and timer.reload_event.is_set()

    asyncio.run(scenario(pg_dsn, exercise))
