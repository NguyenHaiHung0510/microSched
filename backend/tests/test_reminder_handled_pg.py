"""Actual disposable PG transactions for independent ACK and exact confirmed bulk."""

import asyncio
import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid7

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_reminder_history_pg import NOW, actor, database, intent, shot, task, tracker
from test_reminder_history_pg import settings as settings

from app.agent.models import MimiNotificationIntent
from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.domain import reminder_handled as ack
from app.domain import reminder_history as history
from app.domain.models import (
    ReminderDispatch,
    ReminderHandledBatch,
    ReminderOccurrenceHandled,
    Subscription,
    Task,
)
from app.web.deps import get_session, require_session
from app.web.routers.reminder_history import router

pytestmark = pytest.mark.pg


def prepared(**kwargs):
    return ack.PrepareHandled(batch_id=uuid7(), filter=history.HistoryFilter(), **kwargs)


async def count(db):
    return await db.scalar(select(func.count()).select_from(ReminderOccurrenceHandled))


def test_single_idempotent_all_origins_and_no_source_delivery_effects(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            auth = actor()
            t = await task(db)
            one = await shot(db, t)
            tr = await tracker(db)
            sub = Subscription(
                name=crypto.encrypt("Synthetic subscription"),
                amount=crypto.encrypt("100"),
                tracker_id=tr.id,
                started_on=date(2026, 1, 1),
                expires_on=date(2027, 1, 1),
            )
            db.add(sub)
            await db.flush()
            dispatches = [
                ReminderDispatch(
                    subject_type=kind,
                    subject_id=source.id,
                    dispatched_on=NOW.date(),
                    status="sent",
                    created_at=NOW,
                )
                for kind, source in [("tracker", tr), ("subscription", sub)]
            ]
            db.add_all(dispatches)
            await db.flush()
            mi = await intent(db, auth)
            refs = [
                ("one_shot", one),
                ("tracker_dispatch", dispatches[0]),
                ("subscription_dispatch", dispatches[1]),
                ("mimi_intent", mi),
            ]
            for origin, receipt in refs:
                first = await ack.mark_handled(db, auth, origin, receipt.id)
                second = await ack.mark_handled(db, auth, origin, receipt.id)
                assert first == second and first["handled"] is True
            assert await count(db) == 4
            assert t.completed_at is None and one.status == "sent" and mi.read_at is None
            assert all(d.status == "sent" and d.attempt_count == 0 for d in dispatches)
            rows = await history.list_history(db, auth, history.HistoryFilter(handled="handled"))
            assert len(rows["items"]) == 4 and all(r["handled_at"] for r in rows["items"])
            assert not (
                await history.list_history(db, auth, history.HistoryFilter(handled="unhandled"))
            )["items"]

    asyncio.run(scenario())


def test_full_filter_manifest_exceeds_page_and_never_retargets_late_arrival(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            auth = actor()
            t = await task(db)
            for index in range(57):
                await shot(db, t, due=NOW - timedelta(minutes=index))
            page = await history.list_history(db, auth, history.HistoryFilter(), limit=50)
            assert len(page["items"]) == 50 and page["has_more"]
            payload = prepared()
            manifest = await ack.prepare_batch(db, auth, payload)
            assert manifest["selected_count"] == 57
            late = await shot(db, t, due=NOW - timedelta(days=1))
            assert await ack.prepare_batch(db, auth, payload) == manifest
            one = page["items"][0]["occurrence_ref"]
            await ack.mark_handled(db, auth, one["origin"], one["id"])
            result = await ack.commit_batch(db, auth, payload.batch_id)
            assert result["result"] == {"selected_count": 57, "new_count": 56, "already_count": 1}
            assert await ack.commit_batch(db, auth, payload.batch_id) == result
            assert await count(db) == 57
            assert not await db.scalar(
                select(ReminderOccurrenceHandled.id).where(
                    ReminderOccurrenceHandled.one_shot_id == late.id
                )
            )

    asyncio.run(scenario())


def test_selected_manifest_exact_set_and_identity_payload_conflict(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            auth = actor()
            t = await task(db)
            receipts = [await shot(db, t) for _ in range(3)]
            payload = prepared(
                selected_refs=[ack.OccurrenceRef(origin="one_shot", id=r.id) for r in receipts[:2]]
            )
            result = await ack.prepare_batch(db, auth, payload)
            assert result["selected_count"] == 2
            reused = payload.model_copy(update={"selected_refs": None})
            with pytest.raises(HTTPException, match="identity_reused"):
                await ack.prepare_batch(db, auth, reused)
            await ack.commit_batch(db, auth, payload.batch_id)
            assert await count(db) == 2

    asyncio.run(scenario())


def test_private_loss_aborts_whole_manifest_then_applied_replay_is_coarse(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            auth = actor(unlocked=True)
            public = await task(db)
            private = await task(db, title=crypto.encrypt("Synthetic private"), is_private=True)
            await shot(db, public)
            await shot(db, private)
            payload = prepared()
            assert (await ack.prepare_batch(db, auth, payload))["selected_count"] == 2
            auth.private_until = None
            with pytest.raises(HTTPException, match="selection_stale"):
                await ack.commit_batch(db, auth, payload.batch_id)
            assert await count(db) == 0
            assert (await db.get(ReminderHandledBatch, payload.batch_id)).committed_at is None
            auth.private_until = datetime.now(UTC) + timedelta(hours=1)
            await ack.commit_batch(db, auth, payload.batch_id)
            auth.private_until = None
            replay = await ack.commit_batch(db, auth, payload.batch_id)
            assert replay["committed"] and not replay["scope_visible"]
            assert not {"selected_count", "filter", "result", "target_refs"} & replay.keys()
            assert await count(db) == 2

    asyncio.run(scenario())


def test_expiry_requires_new_confirmation_and_other_owner_cannot_replay(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            auth = actor()
            await shot(db, await task(db))
            payload = prepared()
            start = datetime.now(UTC)
            await ack.prepare_batch(db, auth, payload, now=start)
            with pytest.raises(HTTPException, match="expired"):
                await ack.commit_batch(
                    db, auth, payload.batch_id, now=start + timedelta(minutes=16)
                )
            other = actor()
            other.user_email = "other-synthetic@example.test"
            with pytest.raises(HTTPException) as failure:
                await ack.commit_batch(db, other, payload.batch_id)
            assert failure.value.status_code == 404 and await count(db) == 0

    asyncio.run(scenario())


def test_missing_or_reclassified_member_aborts_without_partial_ack(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            auth = actor()
            t = await task(db)
            await shot(db, t)
            second = await task(db)
            await shot(db, second)
            payload = prepared()
            await ack.prepare_batch(db, auth, payload)
            second.is_private = True
            second.title = crypto.encrypt("Changed to private")
            await db.flush()
            with pytest.raises(HTTPException, match="selection_stale"):
                await ack.commit_batch(db, auth, payload.batch_id)
            assert await count(db) == 0

    asyncio.run(scenario())


def test_constraints_reject_untyped_and_duplicate_associations(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            auth = actor()
            one = await shot(db, await task(db))
            await ack.mark_handled(db, auth, "one_shot", one.id)
            for values in [{}, {"one_shot_id": one.id}]:
                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        db.add(ReminderOccurrenceHandled(owner_id=ack._owner_id(auth), **values))
                        await db.flush()
            assert await count(db) == 1

    asyncio.run(scenario())


def test_http_strict_desired_value_no_store_and_missing_receipt(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (db, _):
            app = FastAPI()
            app.include_router(router, prefix="/api")

            async def session():
                yield db

            app.dependency_overrides[get_session] = session
            app.dependency_overrides[require_session] = lambda: actor()
            one = await shot(db, await task(db))
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                path = f"/api/reminder-history/one_shot/{one.id}/handled"
                for value in [False, "true", 1]:
                    assert (await client.put(path, json={"handled": value})).status_code == 422
                response = await client.put(path, json={"handled": True})
                assert (
                    response.status_code == 200 and response.headers["cache-control"] == "no-store"
                )
                assert (
                    await client.put(
                        f"/api/reminder-history/one_shot/{uuid7()}/handled", json={"handled": True}
                    )
                ).status_code == 404
                assert await count(db) == 1
            assert await db.scalar(select(func.count()).select_from(MimiNotificationIntent)) == 0
            assert (await db.execute(text("SHOW transaction_read_only"))).scalar_one() == "off"

    asyncio.run(scenario())


def test_two_actual_connections_commit_same_manifest_once(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        payload, tid = prepared(), None
        try:
            async with factory() as db:
                t = await task(db)
                tid = t.id
                receipts = [await shot(db, t) for _ in range(3)]
                payload.selected_refs = [
                    ack.OccurrenceRef(origin="one_shot", id=r.id) for r in receipts
                ]
                await ack.prepare_batch(db, actor(), payload)
                await db.commit()

            async def commit():
                async with factory() as db:
                    result = await ack.commit_batch(db, actor(), payload.batch_id)
                    await db.commit()
                    return result

            left, right = await asyncio.gather(commit(), commit())
            assert left == right and left["result"] == {
                "selected_count": 3,
                "new_count": 3,
                "already_count": 0,
            }
            async with factory() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ReminderOccurrenceHandled)
                        .where(ReminderOccurrenceHandled.one_shot_id.in_([r.id for r in receipts]))
                    )
                    == 3
                )
        finally:
            async with factory() as db:
                await db.execute(
                    delete(ReminderHandledBatch).where(ReminderHandledBatch.id == payload.batch_id)
                )
                if tid:
                    await db.execute(delete(Task).where(Task.id == tid))
                await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_minimal_actual_app_role_valid_ack_batch_and_write_refusals(pg_dsn):
    async def scenario():
        owner_engine = create_async_engine(async_postgres_url(pg_dsn))
        app_url = (
            make_url(pg_dsn)
            .set(username="microsched_app", password=os.environ["CI_APP_PASSWORD"])
            .render_as_string(hide_password=False)
        )
        app_engine = create_async_engine(async_postgres_url(app_url))
        tid, batch_id = None, None
        try:
            async with async_sessionmaker(owner_engine, expire_on_commit=False)() as db:
                t = await task(db)
                tid = t.id
                first, second = await shot(db, t), await shot(db, t)
                await db.commit()
            async with async_sessionmaker(app_engine, expire_on_commit=False)() as db:
                assert await db.scalar(text("SELECT current_user")) == "microsched_app"
                auth = actor()
                result = await ack.mark_handled(db, auth, "one_shot", first.id)
                assert await ack.mark_handled(db, auth, "one_shot", first.id) == result
                payload = prepared(
                    selected_refs=[ack.OccurrenceRef(origin="one_shot", id=second.id)]
                )
                batch_id = payload.batch_id
                assert (await ack.prepare_batch(db, auth, payload))["selected_count"] == 1
                assert (await ack.commit_batch(db, auth, batch_id))["result"]["new_count"] == 1
                for query in [
                    "UPDATE microsched.reminder_occurrence_handled "
                    "SET handled_at=handled_at WHERE false",
                    "DELETE FROM microsched.reminder_occurrence_handled WHERE false",
                    "DELETE FROM microsched.reminder_handled_batch WHERE false",
                    "CREATE TABLE microsched.r3_forbidden_app_ddl(id integer)",
                ]:
                    with pytest.raises(DBAPIError) as failure:
                        async with db.begin_nested():
                            await db.execute(text(query))
                    assert getattr(failure.value.orig, "sqlstate", None) == "42501"
                assert (await ack.commit_batch(db, auth, batch_id))["result"]["selected_count"] == 1
                await db.rollback()
        finally:
            async with async_sessionmaker(owner_engine)() as db:
                if batch_id:
                    await db.execute(
                        delete(ReminderHandledBatch).where(ReminderHandledBatch.id == batch_id)
                    )
                if tid:
                    await db.execute(delete(Task).where(Task.id == tid))
                await db.commit()
            await app_engine.dispose()
            await owner_engine.dispose()

    asyncio.run(scenario())
