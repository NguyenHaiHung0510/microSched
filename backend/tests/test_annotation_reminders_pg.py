"""Day-marker reminder lifecycle and privacy on disposable PostgreSQL only."""

import asyncio
from datetime import UTC, datetime, time, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database_urls import async_postgres_url
from app.domain.models import AuthSession, DayAnnotation, OneShotReminder, PushSubscription, Task
from app.domain.one_shot import (
    VN,
    ReminderWrite,
    get_source,
    list_reminders,
    read_reminder,
    save_reminder,
)
from app.domain.one_shot_delivery import OneShotDispatcher
from app.domain.push import PushResult

pytestmark = pytest.mark.pg


def test_annotation_send_rechecks_privacy_between_device_handoffs(pg_dsn, monkeypatch):
    calls = []

    async def exercise(db, source):
        source.label = "Synthetic public marker"
        source.note_md = "Synthetic private note canary"
        now = datetime.now(UTC)
        devices = [
            PushSubscription(
                endpoint=f"https://push.example.invalid/088-{index}",
                p256dh="synthetic",
                auth="synthetic",
            )
            for index in range(2)
        ]
        row = OneShotReminder(annotation_id=source.id, mode="absolute", due_at=now)
        db.add_all([*devices, row])
        await db.commit()
        await db.refresh(row)
        maker = async_sessionmaker(db.bind, expire_on_commit=False)

        async def fake_push(_db, _subscription, payload, **_kwargs):
            calls.append(payload)
            if len(calls) == 1:
                async with maker() as writer:
                    current = await writer.get(DayAnnotation, source.id)
                    current.is_private = True
                    await writer.commit()
            return PushResult.SENT

        monkeypatch.setattr("app.domain.one_shot_delivery.send_push", fake_push)
        try:
            await OneShotDispatcher().dispatch(db, row.id, row.revision, now=now)
            assert len(calls) == 2
            assert calls[0]["title"] == "Mốc ngày: Synthetic public marker"
            assert "Synthetic private note canary" in calls[0]["body"]
            assert calls[1]["body"] == "Có một lời nhắc bạn đã đặt. Mở microSched để xem."
            assert "Synthetic" not in str(calls[1])
            await db.refresh(row)
            assert row.status == "sent"
        finally:
            await db.execute(
                delete(PushSubscription).where(
                    PushSubscription.id.in_([device.id for device in devices])
                )
            )
            await db.commit()

    asyncio.run(annotation_scenario(pg_dsn, exercise))


async def annotation_scenario(dsn, exercise):
    engine = create_async_engine(async_postgres_url(dsn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    annotation_id = None
    try:
        async with maker() as db:
            start = (datetime.now(VN) + timedelta(days=5)).date()
            source = DayAnnotation(
                label="Synthetic day marker", starts_on=start, ends_on=start + timedelta(days=2)
            )
            db.add(source)
            await db.commit()
            await db.refresh(source)
            annotation_id = source.id
            await exercise(db, source)
    finally:
        if annotation_id:
            async with maker() as db:
                await db.execute(delete(DayAnnotation).where(DayAnnotation.id == annotation_id))
                await db.commit()
        await engine.dispose()


def test_annotation_relative_reschedules_only_from_start_and_delete_cascades(pg_dsn):
    async def exercise(db, source):
        auth = AuthSession()
        saved = await save_reminder(
            db,
            auth,
            "annotation",
            source.id,
            ReminderWrite(mode="relative", offset_minutes=-1440, anchor_time=time(9)),
        )
        await db.commit()
        expected = datetime.combine(source.starts_on, time(9), VN) - timedelta(days=1)
        assert saved.source_kind == "annotation" and saved.source_title == source.label
        assert saved.due_at == expected.astimezone(UTC)
        listed = await list_reminders(db, auth, kind="annotation", source_id=source.id)
        assert [row.id for row in listed["items"]] == [saved.id]

        # Extending the end day must not move a reminder anchored to the start day.
        source.ends_on += timedelta(days=2)
        await db.commit()
        row = await db.get(OneShotReminder, saved.id, populate_existing=True)
        assert row.revision == 1 and row.due_at == saved.due_at

        source.starts_on += timedelta(days=1)
        await db.commit()
        row = await db.get(OneShotReminder, saved.id, populate_existing=True)
        assert row.revision == 2 and row.due_at == saved.due_at + timedelta(days=1)
        assert row.status == "pending"

        await db.execute(delete(DayAnnotation).where(DayAnnotation.id == source.id))
        await db.commit()
        assert await db.get(OneShotReminder, saved.id, populate_existing=True) is None

    asyncio.run(annotation_scenario(pg_dsn, exercise))


def test_annotation_private_source_stays_behind_current_session_gate(pg_dsn):
    async def exercise(db, source):
        source.is_private = True
        source.label = "PRIVATE_SYNTHETIC_DAY_LABEL"
        source.note_md = "PRIVATE_SYNTHETIC_DAY_NOTE"
        await db.commit()
        unlocked = AuthSession(private_until=datetime.now(UTC) + timedelta(hours=1))
        locked = AuthSession()
        saved = await save_reminder(
            db,
            unlocked,
            "annotation",
            source.id,
            ReminderWrite(mode="absolute", due_at=datetime.now(UTC) + timedelta(days=1)),
        )
        await db.commit()
        assert await get_source(db, "annotation", source.id, locked) is None
        with pytest.raises(HTTPException) as blocked:
            await read_reminder(db, locked, saved.id)
        assert blocked.value.status_code == 404
        assert (await read_reminder(db, unlocked, saved.id)).source_id == source.id
        assert (await list_reminders(db, locked, kind="annotation"))["items"] == []
        visible = await list_reminders(db, unlocked, kind="annotation", source_id=source.id)
        assert [row.id for row in visible["items"]] == [saved.id]
        with pytest.raises(HTTPException) as error:
            await save_reminder(
                db,
                locked,
                "annotation",
                source.id,
                ReminderWrite(mode="absolute", due_at=datetime.now(UTC) + timedelta(days=2)),
            )
        assert error.value.status_code == 404

    asyncio.run(annotation_scenario(pg_dsn, exercise))


def test_annotation_absolute_reminder_does_not_follow_date_edit(pg_dsn):
    async def exercise(db, source):
        due = datetime.now(UTC) + timedelta(days=1)
        saved = await save_reminder(
            db,
            AuthSession(),
            "annotation",
            source.id,
            ReminderWrite(mode="absolute", due_at=due),
        )
        await db.commit()
        source.starts_on += timedelta(days=1)
        await db.commit()
        row = await db.get(OneShotReminder, saved.id, populate_existing=True)
        assert row.due_at == due and row.revision == 1

    asyncio.run(annotation_scenario(pg_dsn, exercise))


def test_annotation_reminder_db_rejects_multiple_sources_and_duplicate_active(pg_dsn):
    async def exercise(db, source):
        task = Task(title="Synthetic second reminder source", status="open")
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id = task.id
        try:
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    db.add(
                        OneShotReminder(
                            annotation_id=source.id,
                            task_id=task_id,
                            mode="absolute",
                            due_at=datetime.now(UTC) + timedelta(days=1),
                        )
                    )
                    await db.flush()
            saved = await save_reminder(
                db,
                AuthSession(),
                "annotation",
                source.id,
                ReminderWrite(mode="absolute", due_at=datetime.now(UTC) + timedelta(days=1)),
            )
            await db.commit()
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    db.add(
                        OneShotReminder(
                            annotation_id=source.id,
                            mode="absolute",
                            due_at=datetime.now(UTC) + timedelta(days=2),
                        )
                    )
                    await db.flush()
            assert (
                await db.scalar(
                    select(OneShotReminder.id).where(OneShotReminder.annotation_id == source.id)
                )
                == saved.id
            )
            # Metadata and database must expose the same canonical CHECK name.
            assert await db.scalar(
                text("""
SELECT EXISTS(SELECT 1 FROM pg_constraint
WHERE conrelid='microsched.one_shot_reminder'::regclass
  AND conname='ck_one_shot_reminder_one_source' AND convalidated)
""")
            )
        finally:
            await db.execute(delete(Task).where(Task.id == task_id))
            await db.commit()

    asyncio.run(annotation_scenario(pg_dsn, exercise))
