"""Calendar tool parity against the real migrated PostgreSQL schema."""

import asyncio
import base64
import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from uuid import UUID, uuid7

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.tools.calendar_reads import (
    CALENDAR_INSPECT_TOOL,
    CALENDAR_READ_TOOL,
    calendar_pairs_current,
    execute_calendar_tool,
)
from app.core import crypto as master_crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import Settings
from app.domain.annotations import AnnotationStore
from app.domain.calendar import CalendarStore
from app.domain.calendar_read import PAGE_SIZE
from app.domain.models import AuthSession, CalendarEvent, CalendarSource, DayAnnotation, Task
from app.domain.tasks import VIETNAM_TZ, TaskStore, _mark_v2_due_writer

pytestmark = pytest.mark.pg
EVENT_FIXTURE = Path(__file__).with_name("fixtures") / "mimi_calendar_membership.json"


def calendar_settings():
    synthetic_master_key = base64.urlsafe_b64encode(bytes(range(32))).decode()
    return Settings(
        _env_file=None,
        mimi_calendar_read_enabled=True,
        encryption_master_key=synthetic_master_key,
    )


def _actor(*, unlocked=False):
    now = datetime.now(UTC)
    return AuthSession(
        user_email="owner@example.test",
        token_hash="synthetic-calendar",
        expires_at=now + timedelta(days=1),
        private_until=now + timedelta(minutes=5) if unlocked else None,
    )


def _midnight(day):
    return datetime.combine(day, time.min, VIETNAM_TZ)


def _pair(name, result):
    return [
        {"tool_calls": [{"function": {"name": name}}]},
        {"content": json.dumps(result)},
    ]


def test_calendar_saved_parity_and_detail_visibility(pg_dsn, monkeypatch):
    monkeypatch.setattr(master_crypto, "_cipher", lambda: AESGCM(bytes(range(32))))

    async def scenario():
        config = calendar_settings()
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as db:
                manual = CalendarSource(
                    id=uuid7(), name=f"Synthetic manual {uuid7()}", kind="manual"
                )
                imported = CalendarSource(id=uuid7(), name=f"Synthetic ICS {uuid7()}", kind="ics")
                hidden = CalendarSource(
                    id=uuid7(), name=f"Synthetic hidden {uuid7()}", kind="ics", is_visible=False
                )
                db.add_all([manual, imported, hidden])
                await db.flush()
                fixture = json.loads(EVENT_FIXTURE.read_text(encoding="utf-8"))
                events = [
                    CalendarEvent(
                        title=item["id"],
                        source_id=manual.id if i == 0 else imported.id,
                        starts_at=datetime.fromisoformat(item["starts_at"]),
                        ends_at=datetime.fromisoformat(item["ends_at"]),
                        all_day=item["all_day"],
                        description_md="Đ" * 2050,
                    )
                    for i, item in enumerate(fixture)
                ]
                hidden_event = CalendarEvent(
                    source_id=hidden.id,
                    title="Hidden event",
                    starts_at=events[0].starts_at,
                    ends_at=events[0].ends_at,
                )
                first, last = date(2040, 8, 30), date(2040, 9, 3)
                dated = Task(
                    title="Date-only deadline",
                    due_precision="date",
                    due_on=first,
                    status="completed",
                    completed_at=datetime.now(UTC),
                    body_md="Not in a Calendar list",
                )
                timed = Task(
                    title="Late UTC deadline in the next Vietnam day",
                    due_precision="datetime",
                    due_at=datetime(2040, 8, 31, 17, 5, tzinfo=UTC),
                )
                deleted = Task(
                    title="Deleted",
                    due_on=first,
                    due_precision="date",
                    deleted_at=datetime.now(UTC),
                )
                private = Task(
                    title=master_crypto.encrypt("Synthetic private Task"),
                    due_on=first,
                    due_precision="date",
                    is_private=True,
                )
                marker = DayAnnotation(
                    starts_on=date(2040, 8, 31), ends_on=last, label="Multi-day", note_md="Đ" * 2050
                )
                private_marker = DayAnnotation(
                    starts_on=first,
                    ends_on=last,
                    label="Synthetic private annotation",
                    note_md="Synthetic private sentinel",
                    is_private=True,
                )
                await _mark_v2_due_writer(db)
                db.add_all(
                    [
                        *events,
                        hidden_event,
                        dated,
                        timed,
                        deleted,
                        private,
                        Task(title="Undated"),
                        marker,
                        private_marker,
                    ]
                )
                await db.flush()

                async def read(args):
                    return await execute_calendar_tool(
                        db, CALENDAR_READ_TOOL, args, settings=config
                    )

                # Use the same persistence readers as the locked UI, without chip limits.
                locked = _actor()
                unlocked = _actor(unlocked=True)
                day_count = (last - first).days + 1
                days = [first + timedelta(days=i) for i in range(day_count)]
                expected = {day.isoformat(): set() for day in days}
                for day in days:
                    key = day.isoformat()
                    start, stop = _midnight(day), _midnight(day + timedelta(days=1))
                    for row in await CalendarStore().list_events(db, locked, start, stop, False):
                        expected[key].add(("event", str(row.id)))
                    tasks = await TaskStore().list_cursor(
                        db, locked, status="all", from_instant=start, to_instant=stop
                    )
                    expected[key].update(("task", str(row.id)) for row in tasks.items)
                    marks = await AnnotationStore().list_annotations(db, locked, day, day)
                    expected[key].update(("annotation", str(row.id)) for row in marks)
                    single = await read({"date": key})
                    assert single["coverage"] == "complete"
                    assert {(r["kind"], r["id"]) for r in single["rows"]} == expected[key]

                # An open PIN changes the regular UI gate but cannot affect Mimi's facade.
                assert private_marker.id in {
                    item.id
                    for item in await AnnotationStore().list_annotations(db, unlocked, first, last)
                }
                unlocked_tasks = await TaskStore().list_cursor(
                    db,
                    unlocked,
                    status="all",
                    from_instant=_midnight(first),
                    to_instant=_midnight(first + timedelta(days=1)),
                )
                assert private.id in {item.id for item in unlocked_tasks.items}

                result = await read({"from_date": str(first), "through_date": str(last)})
                assert result["coverage"] == "complete" and result["next_cursor"] is None
                assert len({r["id"] for r in result["rows"]}) == result["count"] == 6
                for day, ids in expected.items():
                    assert {
                        (r["kind"], r["id"]) for r in result["rows"] if day in r["matched_dates"]
                    } == ids
                projected = {r["id"]: r for r in result["rows"]}
                for item, event in zip(fixture, events, strict=True):
                    row = projected[str(event.id)]
                    assert row["matched_dates"] == item["days"]
                    assert "description_md" not in row
                    assert row["source"]["id"] == str(event.source_id)
                    assert row["source"]["kind"] == ("manual" if event is events[0] else "ics")
                    assert row["source"]["source_version"]
                assert projected[str(dated.id)]["due_on"] == str(first)
                assert projected[str(timed.id)]["due_at"]
                assert "body_md" not in projected[str(dated.id)]
                assert "note_md" not in projected[str(marker.id)]
                sparse = await read({"dates": [str(last), str(first)], "kinds": ["event"]})
                assert [(r["id"], r["matched_dates"]) for r in sparse["rows"]] == [
                    (str(events[0].id), [str(first)])
                ]
                empty = await read({"date": "2040-09-04"})
                assert empty["coverage"] == "complete" and empty["rows"] == []

                async def inspect(kind, id_):
                    return await execute_calendar_tool(
                        db, CALENDAR_INSPECT_TOOL, {"kind": kind, "id": str(id_)}, settings=config
                    )

                visible = await inspect("event", events[1].id)
                assert visible["rows"][0]["description_md"] == "Đ" * 2000
                assert visible["rows"][0]["truncated_fields"] == ["description_md"]
                assert (await inspect("annotation", marker.id))["rows"][0]["note_md"] == "Đ" * 2000
                for kind, id_ in [("event", hidden_event.id), ("annotation", private_marker.id)]:
                    detail = await inspect(kind, id_)
                    assert detail["coverage"] == "unavailable" and detail["rows"] == []

                pairs = [_pair(CALENDAR_READ_TOOL, result), _pair(CALENDAR_INSPECT_TOOL, visible)]
                assert await calendar_pairs_current(db, pairs)
                imported.is_visible = False
                await db.flush()
                assert not await calendar_pairs_current(db, pairs)
                assert (await inspect("event", events[1].id))["rows"] == []
                await db.rollback()
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_calendar_keyset_dense_day_crosses_kind_boundary_without_false_completion(pg_dsn):
    async def scenario():
        config = calendar_settings()
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as db:
                day = date(2042, 11, 15)
                tasks = [
                    Task(title=f"Calendar page {i}", due_precision="date", due_on=day)
                    for i in range(PAGE_SIZE)
                ]
                marker = DayAnnotation(starts_on=day, ends_on=day, label="Page two")
                await _mark_v2_due_writer(db)
                db.add_all([*tasks, marker])
                await db.flush()
                args = {"date": str(day)}
                first = await execute_calendar_tool(db, CALENDAR_READ_TOOL, args, settings=config)
                assert first["count"] == PAGE_SIZE and first["coverage"] == "partial"
                assert first["has_more"] and first["next_cursor"]
                assert {row["id"] for row in first["rows"]} == {str(t.id) for t in tasks}
                args["cursor"] = first["next_cursor"]
                second = await execute_calendar_tool(db, CALENDAR_READ_TOOL, args, settings=config)
                assert second["coverage"] == "partial" and not second["has_more"]
                assert second["continued"]
                assert [row["id"] for row in second["rows"]] == [str(marker.id)]
                assert second["next_cursor"] is None
                for changed in [
                    {**args, "date": "2042-11-16"},
                    {**args, "kinds": ["task"]},
                    {**args, "cursor": args["cursor"] + "1"},
                ]:
                    rejected = await execute_calendar_tool(
                        db, CALENDAR_READ_TOOL, changed, settings=config
                    )
                    assert rejected["coverage"] == "unavailable" and rejected["rows"] == []
                    assert rejected["error"]["code"] == "invalid_calendar_cursor"
                await db.rollback()
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_live_continuation_cannot_certify_insertions_or_visibility_before_cursor(pg_dsn):
    async def scenario():
        config = calendar_settings()
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as db:
                try:
                    base = uuid7().int
                    visible = CalendarSource(name=f"Synthetic page {uuid7()}", kind="ics")
                    hidden = CalendarSource(
                        name=f"Synthetic newly visible {uuid7()}", kind="ics", is_visible=False
                    )
                    db.add_all([visible, hidden])
                    await db.flush()
                    day = date(2094, 4, 5)

                    def event(offset, source, title):
                        return CalendarEvent(
                            id=UUID(int=base + offset),
                            source_id=source.id,
                            title=title,
                            starts_at=datetime(2094, 4, 5, 1, tzinfo=UTC),
                            ends_at=datetime(2094, 4, 5, 2, tzinfo=UTC),
                        )

                    earlier = event(1, hidden, "New visibility before cursor")
                    db.add_all(
                        [
                            earlier,
                            *[
                                event(i + 100, visible, f"Page row {i}")
                                for i in range(PAGE_SIZE + 1)
                            ],
                        ]
                    )
                    await db.flush()
                    args = {"date": str(day), "kinds": ["event"]}
                    first = await execute_calendar_tool(
                        db, CALENDAR_READ_TOOL, args, settings=config
                    )
                    assert first["has_more"] and first["coverage"] == "partial"
                    inserted = event(2, hidden, "Inserted before cursor")
                    db.add(inserted)
                    hidden.is_visible = True
                    await db.flush()
                    # Unchanged emitted rows say nothing about newly eligible membership.
                    assert await calendar_pairs_current(db, [_pair(CALENDAR_READ_TOOL, first)])
                    continuation = {**args, "cursor": first["next_cursor"]}
                    final = await execute_calendar_tool(
                        db, CALENDAR_READ_TOOL, continuation, settings=config
                    )
                    assert final["continued"] and not final["has_more"]
                    assert final["coverage"] == "partial" and final["count"] == 1
                    assert not {str(earlier.id), str(inserted.id)} & {
                        r["id"] for r in final["rows"]
                    }
                    visible.is_visible = False
                    await db.flush()
                    empty = await execute_calendar_tool(
                        db, CALENDAR_READ_TOOL, continuation, settings=config
                    )
                    assert empty["rows"] == [] and not empty["has_more"]
                    assert empty["continued"] and empty["coverage"] == "partial"
                    fresh = await execute_calendar_tool(
                        db, CALENDAR_READ_TOOL, args, settings=config
                    )
                    assert fresh["coverage"] == "complete" and not fresh["continued"]
                    assert {r["id"] for r in fresh["rows"]} == {str(earlier.id), str(inserted.id)}
                finally:
                    # All fixtures stay in this test's uncommitted transaction.
                    await db.rollback()
        finally:
            await engine.dispose()

    asyncio.run(scenario())
