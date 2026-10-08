"""Real local-PG N2 lifecycle oracles; fake sends prove no OS delivery."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import cleanup, local_contract, prepare  # noqa: F401

from app.agent import crypto, service
from app.agent import notifications as n
from app.agent.models import (
    MimiConversation,
    MimiDevicePreference,
    MimiEvent,
    MimiNotificationDelivery,
    MimiNotificationIntent,
)
from app.core.database_urls import async_postgres_url
from app.domain.models import PushSubscription, Task

pytestmark = pytest.mark.pg


async def device(maker, owner_id, enabled=True):
    async with maker() as db:
        sub = PushSubscription(
            endpoint=f"https://push.example.invalid/{uuid4()}",
            p256dh="synthetic-key",
            auth="synthetic-proof",
        )
        db.add(sub)
        await db.flush()
        sid = sub.id
        payload = n.DevicePreferenceChange(
            subscription_id=sid,
            endpoint=sub.endpoint,
            p256dh=sub.p256dh,
            auth=sub.auth,
            enabled=enabled,
        )
        pref = await n.set_preference(db, owner_id, payload)
        await db.commit()
    return sid, pref


async def drop_device(maker, sid):
    async with maker() as db:
        await db.execute(delete(PushSubscription).where(PushSubscription.id == sid))
        await db.commit()


def test_notification_intent_atomic_copy_dedup_ack_and_opaque_owner_resolver(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, ch, decision = await prepare(maker)
        try:
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                owner = conv.owner_id
                intent = (
                    await db.scalars(
                        select(MimiNotificationIntent).where(MimiNotificationIntent.run_id == rid)
                    )
                ).one()
                content = json.loads(
                    crypto.open_content(
                        crypto.unwrap_dek(conv.dek_wrapped),
                        intent.copy_ciphertext,
                        aad=n.copy_aad(intent),
                    )
                )
                assert "Chờ bạn duyệt" in content["body"] and "Chưa áp dụng" in content["body"]
                assert len(content["title"]) <= 80 and len(content["body"]) <= 240
                event = await db.get(MimiEvent, intent.event_id)
                await n.queue_completion(db, rid, event.sequence, "change_set.ready")
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiNotificationIntent)
                        .where(MimiNotificationIntent.run_id == rid)
                    )
                    == 1
                )
                result = await n.resolve_locator(db, owner, intent.locator)
                assert result["path"] == "/mimi" and result["conversation_id"] == str(cid)
                assert intent.read_at is None
                with pytest.raises(HTTPException):
                    await n.resolve_locator(db, uuid4(), intent.locator)
                with pytest.raises(HTTPException):
                    await n.resolve_locator(db, owner, intent.locator + "tampered")
                await n.acknowledge(db, owner, intent.id)
                await db.commit()
            async with maker() as db:
                await service.confirm_change_set(db, actor, ch, decision, "notification-rollback")
                await db.rollback()
            async with maker() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiNotificationIntent)
                        .where(
                            MimiNotificationIntent.run_id == rid,
                            MimiNotificationIntent.kind == "completed",
                        )
                    )
                    == 0
                )
                await service.confirm_change_set(db, actor, ch, decision, "notification-commit")
                await db.commit()
                completed = (
                    await db.scalars(
                        select(MimiNotificationIntent).where(
                            MimiNotificationIntent.run_id == rid,
                            MimiNotificationIntent.kind == "completed",
                        )
                    )
                ).one()
                copy = json.loads(
                    crypto.open_content(
                        crypto.unwrap_dek((await db.get(MimiConversation, cid)).dek_wrapped),
                        completed.copy_ciphertext,
                        aad=n.copy_aad(completed),
                    )
                )
                assert "Đã áp dụng" in copy["body"] and "Chưa áp dụng" not in copy["body"]
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_explicit_device_ownership_consent_private_and_stale_preview_suppression(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, ch, decision = await prepare(maker)
        sid = None
        try:
            async with maker() as db:
                owner = (await db.get(MimiConversation, cid)).owner_id
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiNotificationDelivery)
                        .join(MimiNotificationIntent)
                        .where(MimiNotificationIntent.run_id == rid)
                    )
                    == 0
                )
            sid, record = await device(maker, owner, False)
            async with maker() as db:
                pref = (
                    await db.scalars(
                        select(MimiDevicePreference).where(
                            MimiDevicePreference.subscription_id == sid
                        )
                    )
                ).one()
                intent = (
                    await db.scalars(
                        select(MimiNotificationIntent).where(MimiNotificationIntent.run_id == rid)
                    )
                ).one()
                assert not await n.eligible_delivery(db, intent, pref)
                sub = await db.get(PushSubscription, sid)
                bad = n.DevicePreferenceChange(
                    subscription_id=sid,
                    endpoint=sub.endpoint,
                    p256dh=sub.p256dh,
                    auth="wrong",
                    enabled=True,
                    expected_revision=1,
                )
                with pytest.raises(HTTPException):
                    await n.set_preference(db, owner, bad)
                proof = bad.model_copy(update={"auth": sub.auth})
                with pytest.raises(HTTPException):
                    await n.set_preference(db, uuid4(), proof)
                await n.set_preference(db, owner, proof)
                assert await n.eligible_delivery(db, intent, pref)
                async with maker() as concurrent:
                    task = await concurrent.get(Task, ids[0])
                    task.title = "Concurrent edit invalidates approval-ready copy"
                    await concurrent.commit()
                assert not await n.eligible_delivery(db, intent, pref), (
                    "source-stale approval preview must be suppressed before Push dispatch"
                )
                with pytest.raises(HTTPException, match="stale"):
                    await n.set_preference(db, owner, proof)
                conv = await db.get(MimiConversation, cid)
                conv.generation += 1
                assert not await n.eligible_delivery(db, intent, pref)
                conv.generation -= 1
                conv.sensitivity = "private"
                conv.is_private = True
                await db.flush()
                assert not await n.eligible_delivery(db, intent, pref)
                assert await n.list_attention(db, owner) == []
                await db.rollback()
        finally:
            await cleanup(maker, cid, ids)
            if sid:
                await drop_device(maker, sid)
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["accepted", "unknown", "retryable", "exception"])
def test_send_fence_bounded_retries_and_ambiguous_no_redispatch(pg_dsn, outcome):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, ch, decision = await prepare(maker)
        sid = None
        calls = []
        try:
            async with maker() as db:
                owner = (await db.get(MimiConversation, cid)).owner_id
            sid, _ = await device(maker, owner)
            async with maker() as db:
                intent = (
                    await db.scalars(
                        select(MimiNotificationIntent).where(MimiNotificationIntent.run_id == rid)
                    )
                ).one()
                pref = (
                    await db.scalars(
                        select(MimiDevicePreference).where(
                            MimiDevicePreference.subscription_id == sid
                        )
                    )
                ).one()
                delivery = MimiNotificationDelivery(intent_id=intent.id, preference_id=pref.id)
                db.add(delivery)
                await db.flush()
                did = delivery.id
                await db.commit()

            async def send(sub, payload, **kwargs):
                async with maker() as db:
                    d = await db.get(MimiNotificationDelivery, did)
                    assert d.state == "sending" and d.attempt_count == len(calls) + 1
                calls.append(payload)
                assert (
                    payload["url"].startswith("/mimi?attention=")
                    and "Chờ bạn duyệt" in payload["body"]
                )
                if outcome == "exception":
                    raise TimeoutError("synthetic dispatched unknown")
                return outcome

            dispatcher = n.NotificationDispatcher(maker, send=send)
            await dispatcher.deliver(did)
            async with maker() as db:
                delivery = await db.get(MimiNotificationDelivery, did)
                expected = "unknown" if outcome == "exception" else outcome
                assert delivery.state == expected and delivery.attempt_count == 1
                if expected == "retryable":
                    assert 25 < (delivery.next_at - datetime.now(UTC)).total_seconds() <= 30
            if outcome == "retryable":
                for i in range(3):
                    await dispatcher.deliver(did)
                async with maker() as db:
                    assert (await db.get(MimiNotificationDelivery, did)).state == "expired"
                assert len(calls) == 4
            else:
                await dispatcher.deliver(did)
                assert len(calls) == 1
                # Simulate process loss after durable sending fence. Startup
                # reconciles that exact attempt to unknown without any send.
                async with maker() as db:
                    delivery = await db.get(MimiNotificationDelivery, did)
                    delivery.state = "sending"
                    await db.commit()

                async def forbidden(*a, **k):
                    pytest.fail("restart must not replay uncertain send")

                restart = n.NotificationDispatcher(maker, send=forbidden)
                await restart.start()
                await restart.stop()
                async with maker() as db:
                    assert (await db.get(MimiNotificationDelivery, did)).state == "unknown"
        finally:
            await cleanup(maker, cid, ids)
            if sid:
                await drop_device(maker, sid)
            await engine.dispose()

    asyncio.run(scenario())
