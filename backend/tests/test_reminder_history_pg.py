"""Real isolated PG projection/HTTP oracles; no dispatcher/provider or source ACKs."""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid7

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import delete, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import crypto as mc
from app.agent.models import (
    MimiConversation,
    MimiDevicePreference,
    MimiEvent,
    MimiNotificationDelivery,
    MimiNotificationIntent,
    MimiRun,
)
from app.agent.notifications import copy_aad
from app.agent.service import _owner_id
from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain import reminder_history as h
from app.domain.models import (
    AuthSession,
    CalendarEvent,
    CalendarSource,
    DayAnnotation,
    OneShotReminder,
    PushSubscription,
    ReminderDispatch,
    Subscription,
    Task,
    TaskItem,
    Tracker,
    TrackerReminderBatch,
    TrackerReminderBatchItem,
)
from app.web.deps import get_session, require_session
from app.web.routers.reminder_history import router

pytestmark = pytest.mark.pg
NOW = datetime(2026, 10, 23, 10, tzinfo=UTC)


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("MIMI_NOTIFICATIONS_ENABLED", "true")
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def actor(unlocked=False):
    return AuthSession(
        token_hash="history-test",
        user_email="history@example.test",
        last_seen_at=NOW,
        expires_at=NOW + timedelta(days=1),
        private_until=datetime.now(UTC) + timedelta(hours=1) if unlocked else None,
    )


@asynccontextmanager
async def database(pg_dsn):
    engine = create_async_engine(async_postgres_url(pg_dsn))
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            async with async_sessionmaker(bind=conn, expire_on_commit=False)() as db:
                yield db, engine
            await transaction.rollback()
    finally:
        await engine.dispose()


async def task(db, title="Current public title", **kwargs):
    row = Task(title=title, **kwargs)
    db.add(row)
    await db.flush()
    return row


async def shot(db, source, *, due=NOW, status="sent", created=NOW - timedelta(days=3), **kwargs):
    fk = {
        Task: "task_id",
        Tracker: "tracker_id",
        CalendarEvent: "event_id",
        DayAnnotation: "annotation_id",
    }[type(source)]
    row = OneShotReminder(
        **{fk: source.id}, mode="absolute", due_at=due, status=status, created_at=created, **kwargs
    )
    db.add(row)
    await db.flush()
    return row


async def tracker(db, private=False):
    t = Tracker(
        name=crypto.encrypt("Private tracker" if private else "Public tracker"),
        kind="general",
        input_mode="event",
        is_private=private,
    )
    db.add(t)
    await db.flush()
    return t


async def intent(db, auth, *, deliveries=2, private=False, other_owner=False):
    owner = uuid7() if other_owner else _owner_id(auth)
    c = MimiConversation(
        owner_id=owner,
        sensitivity="private" if private else "standard",
        is_private=private,
        dek_wrapped=mc.create_wrapped_dek(),
    )
    db.add(c)
    await db.flush()
    run = MimiRun(conversation_id=c.id, generation=1, state="completed", deadline=NOW)
    db.add(run)
    await db.flush()
    e = MimiEvent(run_id=run.id, sequence=1, kind="run.terminal")
    db.add(e)
    await db.flush()
    i = MimiNotificationIntent(
        id=uuid7(),
        owner_id=owner,
        conversation_id=c.id,
        run_id=run.id,
        event_id=e.id,
        kind="completed",
        locator=str(uuid7()),
        expires_at=NOW + timedelta(hours=1),
        copy_ciphertext="mimi:v1:pending",
        created_at=NOW,
    )
    i.copy_ciphertext = mc.seal_content(
        mc.unwrap_dek(c.dek_wrapped),
        json.dumps({"title": "Intent snapshot", "body": "Synthetic original copy"}),
        aad=copy_aad(i),
    )
    db.add(i)
    await db.flush()
    for index in range(deliveries):
        sub = PushSubscription(
            endpoint="https://example.invalid/" + str(uuid7()), p256dh="synthetic", auth="synthetic"
        )
        db.add(sub)
        await db.flush()
        pref = MimiDevicePreference(owner_id=owner, subscription_id=sub.id, enabled=True)
        db.add(pref)
        await db.flush()
        db.add(
            MimiNotificationDelivery(
                intent_id=i.id,
                preference_id=pref.id,
                state="accepted" if index == 0 else "unknown",
                attempt_count=index + 1,
            )
        )
    await db.flush()
    return i


def test_all_origins_dedup_current_content_and_read_does_not_ack(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            auth = actor()
            t = await task(db, body_md="Full public body")
            db.add(TaskItem(task_id=t.id, content="Full public child", position=0))
            tr = await tracker(db)
            cal = CalendarSource(name="Synthetic", kind="manual")
            db.add(cal)
            await db.flush()
            ev = CalendarEvent(
                source_id=cal.id, title="Event", starts_at=NOW, ends_at=NOW + timedelta(hours=1)
            )
            an = DayAnnotation(
                starts_on=NOW.date(), ends_on=NOW.date(), label="Marker", note_md="Marker full note"
            )
            db.add_all([ev, an])
            await db.flush()
            shots = [await shot(db, s, sent_at=NOW + timedelta(minutes=2)) for s in [t, tr, ev, an]]
            sub = Subscription(
                name=crypto.encrypt("Current subscription"),
                amount=crypto.encrypt("35000"),
                tracker_id=tr.id,
                started_on=date(2026, 1, 1),
                expires_on=date(2027, 1, 1),
            )
            db.add(sub)
            await db.flush()
            d = ReminderDispatch(
                subject_type="tracker",
                subject_id=tr.id,
                dispatched_on=NOW.date(),
                status="sent",
                created_at=NOW,
            )
            sd = ReminderDispatch(
                subject_type="subscription",
                subject_id=sub.id,
                dispatched_on=NOW.date(),
                status="no_device",
                created_at=NOW,
            )
            db.add_all([d, sd])
            await db.flush()
            batch = TrackerReminderBatch(
                occurrence_on=NOW.date(), reminder_time=time(16), status="sent"
            )
            db.add(batch)
            await db.flush()
            db.add(
                TrackerReminderBatchItem(
                    batch_id=batch.id,
                    dispatch_id=d.id,
                    reminder_mode="fixed",
                    reminder_interval_days=1,
                    reminder_action="confirm_event",
                    input_mode="event",
                    state="sent",
                )
            )
            i = await intent(db, auth)
            result = await h.list_history(
                db, auth, h.HistoryFilter(), now=NOW + timedelta(minutes=5)
            )
            assert len(result["items"]) == 7
            refs = [tuple(x["occurrence_ref"].values()) for x in result["items"]]
            assert len(set(refs)) == 7
            assert {x["origin"] for x in result["items"]} == {
                "one_shot",
                "tracker_dispatch",
                "subscription_dispatch",
                "mimi_intent",
            }
            one = next(x for x in result["items"] if x["source_kind"] == "task")
            assert "Full public body" in one["body"] and "Full public child" in one["body"]
            assert one["accepted_at"] == NOW + timedelta(minutes=2) and one["occurrence_at"] == NOW
            recurring = next(x for x in result["items"] if x["origin"] == "tracker_dispatch")
            assert recurring["occurrence_at"] == datetime(2026, 10, 23, 9, tzinfo=UTC)
            legacy = next(x for x in result["items"] if x["origin"] == "subscription_dispatch")
            assert (
                legacy["occurrence_at"] is None
                and legacy["time_basis"] == "dispatch_day"
                and legacy["accepted_at"] is None
            )
            mimi = next(x for x in result["items"] if x["origin"] == "mimi_intent")
            assert mimi["status"] == "accepted" and mimi["content_basis"] == "intent_snapshot"
            assert mimi["attempt_count"] == 2 and mimi["accepted_at"] is None
            assert mimi["delivery_basis"].startswith("at_least_one_provider_accepted")
            assert result["items"][0]["origin"] == "mimi_intent"
            assert result["items"][-1]["origin"] == "subscription_dispatch"
            assert not any(key in mimi for key in ("endpoint", "preference_id", "p256dh", "auth"))
            assert i.read_at is None and d.confirmed_at is None and t.status == "open"
            assert all(not x["can_handle"] and x["handled_at"] is None for x in result["items"])
            assert [s.status for s in shots] == ["sent"] * 4
            assert "note" not in result["coverage"]["supported_sources"]

    asyncio.run(scenario())


def test_keyset_more_than_fifty_ties_day_boundary_and_cursor_view_binding(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            auth = actor()
            t = await task(db)
            ids = []
            for n in range(63):
                ids.append((await shot(db, t, due=NOW - timedelta(days=n // 31))).id)
            first = await h.list_history(db, auth, h.HistoryFilter(), now=NOW, limit=50)
            assert len(first["items"]) == 50 and first["has_more"] and first["total"] is None
            second = await h.list_history(
                db, auth, h.HistoryFilter(), now=NOW, limit=50, cursor=first["next_cursor"]
            )
            assert len(second["items"]) == 13 and not second["has_more"]
            ordered = [x["occurrence_ref"]["id"] for x in first["items"] + second["items"]]
            assert len(set(ordered)) == 63 and set(ordered) == set(ids)
            assert ordered[:31] == sorted(ids[:31], reverse=True)
            for filters, who in [
                (h.HistoryFilter(status="failed"), auth),
                (h.HistoryFilter(), actor(True)),
            ]:
                with pytest.raises(HTTPException) as e:
                    await h.list_history(db, who, filters, now=NOW, cursor=first["next_cursor"])
                assert e.value.status_code == 422
            other = actor()
            other.user_email = "different@example.test"
            with pytest.raises(HTTPException):
                await h.list_history(
                    db, other, h.HistoryFilter(), now=NOW, cursor=first["next_cursor"]
                )
            with pytest.raises(HTTPException):
                await h.list_history(
                    db, auth, h.HistoryFilter(), now=NOW, cursor=first["next_cursor"] + "x"
                )
            incoming = await shot(db, t, due=NOW, created=NOW + timedelta(seconds=1))
            stable = await h.list_history(
                db,
                auth,
                h.HistoryFilter(),
                now=NOW + timedelta(seconds=2),
                cursor=first["next_cursor"],
            )
            assert incoming.id not in [x["occurrence_ref"]["id"] for x in stable["items"]]
            refresh = await h.list_history(
                db, auth, h.HistoryFilter(), now=NOW + timedelta(seconds=2), limit=100
            )
            assert len(refresh["items"]) == 64

    asyncio.run(scenario())


def test_privacy_before_limit_decrypt_and_constant_abstract(pg_dsn, monkeypatch):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            auth = actor()
            public = await task(db)
            expected = await shot(db, public, due=NOW - timedelta(days=1))
            public_only = await h.list_history(db, auth, h.HistoryFilter(), now=NOW, limit=1)
            p = await task(
                db,
                title=crypto.encrypt("Private title canary"),
                body_md=crypto.encrypt("Private body canary"),
                is_private=True,
            )
            for _ in range(70):
                await shot(db, p)
            original = crypto.decrypt

            def guard(value):
                assert value not in (p.title, p.body_md), "locked private content reached decrypt"
                return original(value)

            monkeypatch.setattr(crypto, "decrypt", guard)
            locked = await h.list_history(db, auth, h.HistoryFilter(), now=NOW, limit=1)
            assert (
                len(locked["items"]) == 1
                and locked["items"][0]["occurrence_ref"]["id"] == expected.id
            )
            assert (
                not locked["has_more"] and locked["next_cursor"] is None and locked["total"] is None
            )
            encoded = json.dumps(locked, default=str)
            assert str(p.id) not in encoded and "canary" not in encoded
            assert (
                locked == public_only
            )  # Adding70private receipts changes no public metadata/count.
            monkeypatch.setattr(crypto, "decrypt", original)
            unlocked = await h.list_history(db, actor(True), h.HistoryFilter(), now=NOW, limit=1)
            assert unlocked["items"][0]["title"] == "Private title canary"
            assert unlocked["items"][0]["body"] == "Private body canary"
            assert unlocked["private_notice"] is None
            relocked = await h.list_history(db, auth, h.HistoryFilter(), now=NOW, limit=1)
            assert relocked == locked

    asyncio.run(scenario())


def test_occurrence_clock_cancelled_future_and_filters(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            auth = actor()
            t = await task(db, status="completed", completed_at=NOW)
            old = await shot(
                db, t, due=NOW - timedelta(days=1), created=NOW - timedelta(days=10), sent_at=NOW
            )
            cancel = await shot(
                db,
                t,
                due=NOW + timedelta(days=4),
                status="cancelled",
                created=NOW - timedelta(hours=1),
            )
            future = await shot(db, t, due=NOW + timedelta(days=1), status="pending")
            midnight = await shot(
                db, t, due=datetime(2026, 10, 22, 17, tzinfo=UTC), status="failed"
            )
            result = await h.list_history(db, auth, h.HistoryFilter(), now=NOW)
            assert [x["occurrence_ref"]["id"] for x in result["items"]] == [
                cancel.id,
                midnight.id,
                old.id,
            ]
            assert future.id not in [x["occurrence_ref"]["id"] for x in result["items"]]
            assert result["items"][0]["time_basis"] == "recorded_only"
            assert all(not item["can_open"] for item in result["items"])
            assert result["items"][0]["scheduled_at"] == NOW + timedelta(days=4)
            result = await h.list_history(
                db,
                auth,
                h.HistoryFilter(
                    day_from=date(2026, 10, 23),
                    day_to=date(2026, 10, 23),
                    status="failed",
                    source="task",
                    origin="one_shot",
                ),
                now=NOW,
            )
            assert [x["occurrence_ref"]["id"] for x in result["items"]] == [midnight.id]
            with pytest.raises(HTTPException):
                await h.list_history(
                    db,
                    auth,
                    h.HistoryFilter(day_from=date(2026, 10, 24), day_to=date(2026, 10, 23)),
                    now=NOW,
                )

    asyncio.run(scenario())


def test_mimi_owner_standard_and_feature_before_decrypt(pg_dsn, monkeypatch):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            auth = actor(True)
            allowed = await intent(db, auth)
            hidden = await intent(db, auth, private=True)
            foreign = await intent(db, auth, other_owner=True)
            original = mc.open_content

            def guard(dek, value, **kw):
                assert value not in (hidden.copy_ciphertext, foreign.copy_ciphertext)
                return original(dek, value, **kw)

            monkeypatch.setattr(mc, "open_content", guard)
            result = await h.list_history(db, auth, h.HistoryFilter(), now=NOW)
            assert [x["occurrence_ref"]["id"] for x in result["items"]] == [allowed.id]
            monkeypatch.setenv("MIMI_NOTIFICATIONS_ENABLED", "false")
            get_settings.cache_clear()
            assert (await h.list_history(db, auth, h.HistoryFilter(), now=NOW))["items"] == []

    asyncio.run(scenario())


def test_deleted_hidden_orphan_omitted_without_reconstructing(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            deleted = await task(db, deleted_at=NOW)
            await shot(db, deleted)
            db.add(
                ReminderDispatch(
                    subject_type="tracker",
                    subject_id=uuid7(),
                    dispatched_on=NOW.date(),
                    status="sent",
                    created_at=NOW,
                )
            )
            cal = CalendarSource(name="Hidden test", kind="manual")
            db.add(cal)
            await db.flush()
            ev = CalendarEvent(
                source_id=cal.id,
                title="hidden",
                starts_at=NOW,
                ends_at=NOW + timedelta(hours=1),
                is_hidden=True,
            )
            db.add(ev)
            await db.flush()
            await shot(db, ev)
            result = await h.list_history(db, actor(), h.HistoryFilter(), now=NOW)
            assert result["items"] == [] and not result["has_more"]

    asyncio.run(scenario())


def test_http_auth_validation_cache_contract_and_readonly_transaction(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            t = await task(db)
            await shot(db, t, due=datetime.now(UTC) - timedelta(minutes=1))
            await db.flush()
            app = FastAPI()
            app.include_router(router, prefix="/api")

            async def dependency():
                yield db

            app.dependency_overrides[get_session] = dependency
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                assert (await client.get("/api/reminder-history")).status_code == 401
                app.dependency_overrides[require_session] = lambda: actor()
                assert (await client.get("/api/reminder-history?source=note")).status_code == 422
                assert (
                    await client.get("/api/reminder-history?handled=handled")
                ).status_code == 422
                assert (await client.get("/api/reminder-history?limit=101")).status_code == 422
                response = await client.get("/api/reminder-history")
                assert response.status_code == 200, response.text
                assert response.headers["cache-control"] == "no-store"
                assert len(response.json()["items"]) == 1

    asyncio.run(scenario())


def test_constant_query_count_no_n_plus_one_and_no_dml(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, engine):
            for _ in range(10):
                await shot(db, await task(db))
            calls = []

            def observe(conn, cursor, statement, parameters, context, many):
                calls.append(statement)

            event.listen(engine.sync_engine, "before_cursor_execute", observe)
            one = await h.list_history(db, actor(), h.HistoryFilter(), now=NOW, limit=1)
            count = len(calls)
            calls.clear()
            many = await h.list_history(db, actor(), h.HistoryFilter(), now=NOW, limit=10)
            event.remove(engine.sync_engine, "before_cursor_execute", observe)
            assert len(one["items"]) == 1 and len(many["items"]) == 10
            assert len(calls) == count
            assert all(s.lstrip().upper().startswith("SELECT") for s in calls)

    asyncio.run(scenario())


def test_mixed_batch_private_subscription_and_after_entry_are_independent(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            public, private = await tracker(db), await tracker(db, private=True)
            batch = TrackerReminderBatch(occurrence_on=NOW.date(), reminder_time=time(16))
            db.add(batch)
            await db.flush()
            for tr, mode in [(public, "after_entry"), (private, "fixed")]:
                d = ReminderDispatch(
                    subject_type="tracker",
                    subject_id=tr.id,
                    dispatched_on=NOW.date(),
                    status="sent",
                    created_at=NOW,
                )
                db.add(d)
                await db.flush()
                db.add(
                    TrackerReminderBatchItem(
                        batch_id=batch.id,
                        dispatch_id=d.id,
                        reminder_mode=mode,
                        reminder_interval_days=1,
                        reminder_action="confirm_event",
                        input_mode="event",
                        state="sent",
                    )
                )
            sub = Subscription(
                name=crypto.encrypt("Private subscription canary"),
                amount=crypto.encrypt("35000"),
                tracker_id=private.id,
                started_on=date(2026, 1, 1),
                expires_on=date(2027, 1, 1),
            )
            db.add(sub)
            await db.flush()
            db.add(
                ReminderDispatch(
                    subject_type="subscription",
                    subject_id=sub.id,
                    dispatched_on=NOW.date(),
                    status="sent",
                    created_at=NOW,
                )
            )
            await db.flush()
            locked = await h.list_history(db, actor(), h.HistoryFilter(), now=NOW)
            assert len(locked["items"]) == 1 and not locked["has_more"]
            assert locked["items"][0]["source_ref"]["id"] == public.id
            assert str(private.id) not in json.dumps(locked, default=str)
            opened = await h.list_history(db, actor(True), h.HistoryFilter(), now=NOW)
            assert len(opened["items"]) == 3
            child = next(x for x in opened["items"] if x["source_kind"] == "subscription")
            assert child["is_private"] and child["title"] == "Private subscription canary"
            assert not any("batch" in x["occurrence_ref"] for x in opened["items"])

    asyncio.run(scenario())


def test_legacy_day_never_uses_current_clock_and_future_batch_stays_upcoming(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            legacy, upcoming = await tracker(db), await tracker(db)
            legacy.reminder_time = time(22)
            d = ReminderDispatch(
                subject_type="tracker",
                subject_id=legacy.id,
                dispatched_on=NOW.date(),
                status="sent",
                created_at=NOW,
            )
            f = ReminderDispatch(
                subject_type="tracker",
                subject_id=upcoming.id,
                dispatched_on=NOW.date(),
                status="pending",
                created_at=NOW,
            )
            db.add_all([d, f])
            await db.flush()
            batch = TrackerReminderBatch(occurrence_on=NOW.date(), reminder_time=time(23))
            db.add(batch)
            await db.flush()
            db.add(
                TrackerReminderBatchItem(
                    batch_id=batch.id,
                    dispatch_id=f.id,
                    reminder_mode="fixed",
                    reminder_interval_days=1,
                    reminder_action="confirm_event",
                    input_mode="event",
                    state="pending",
                )
            )
            await db.flush()
            result = await h.list_history(db, actor(), h.HistoryFilter(), now=NOW)
            assert len(result["items"]) == 1
            row = result["items"][0]
            assert row["occurrence_ref"]["id"] == d.id and row["time_precision"] == "day"
            assert row["occurrence_at"] is None and row["scheduled_at"] is None
            assert row["accepted_at"] is None and row["time_basis"] == "dispatch_day"

    asyncio.run(scenario())


def test_visibility_loss_between_metadata_and_hydration_returns_no_partial_page(
    pg_dsn, monkeypatch
):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            t = await task(db)
            await shot(db, t)
            hydrate = h._hydrate

            async def relock(db, auth, rows):
                t.title = crypto.encrypt("Private after metadata")
                t.is_private = True
                await db.flush()
                return await hydrate(db, auth, rows)

            monkeypatch.setattr(h, "_hydrate", relock)
            with pytest.raises(HTTPException) as e:
                await h.list_history(db, actor(), h.HistoryFilter(), now=NOW)
            assert e.value.status_code == 409 and e.value.detail == "history_view_changed"

    asyncio.run(scenario())


def test_application_role_can_read_full_page_in_actual_readonly_transaction(pg_dsn):
    async def scenario():
        owner_engine = create_async_engine(async_postgres_url(pg_dsn))
        # Inherit ONLY the already-guarded disposable host/port/database, never another URL.
        app_url = (
            make_url(pg_dsn)
            .set(username="microsched_app", password=os.environ["CI_APP_PASSWORD"])
            .render_as_string(hide_password=False)
        )
        app_engine = create_async_engine(async_postgres_url(app_url))
        tid = None
        try:
            async with async_sessionmaker(owner_engine, expire_on_commit=False)() as db:
                t = await task(db)
                tid = t.id
                await shot(db, t)
                await db.commit()
            async with app_engine.connect() as connection:
                await connection.execution_options(postgresql_readonly=True)
                async with connection.begin():
                    async with async_sessionmaker(bind=connection)() as db:
                        assert (
                            await db.execute(text("SHOW transaction_read_only"))
                        ).scalar_one() == "on"
                        assert (
                            await db.execute(text("SELECT current_user"))
                        ).scalar_one() == "microsched_app"
                        result = await h.list_history(db, actor(), h.HistoryFilter(), now=NOW)
                        assert [x["source_ref"]["id"] for x in result["items"]] == [tid]
        finally:
            if tid is not None:
                async with async_sessionmaker(owner_engine)() as db:
                    await db.execute(delete(Task).where(Task.id == tid))
                    await db.commit()
            await app_engine.dispose()
            await owner_engine.dispose()

    asyncio.run(scenario())
