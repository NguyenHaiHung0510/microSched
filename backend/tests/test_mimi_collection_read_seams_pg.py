"""Real-PG authenticated read seams; recovery must not replay writes or expose other owners."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import cleanup, local_contract, prepare  # noqa: F401
from test_mimi_notifications_pg import drop_device

from app.agent import notifications, service
from app.agent.models import (
    MimiConversation,
    MimiDevicePreference,
    MimiEvidence,
    MimiExecutionReceipt,
    MimiNotificationIntent,
)
from app.core.database_urls import async_postgres_url
from app.domain.models import PushSubscription, Task
from app.main import create_app
from app.web.deps import get_session, require_session

pytestmark = pytest.mark.pg
HEADERS = {"Origin": "http://test", "Sec-Fetch-Site": "same-origin", "X-Mimi-CSRF": "1"}


def client_app(maker, actor):
    app = create_app()

    async def current_actor():
        return actor

    async def session():
        async with maker() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    app.dependency_overrides[require_session] = current_actor
    app.dependency_overrides[get_session] = session
    return app


def foreign(actor):
    return actor.model_copy(update={"user_email": "other-owner@example.test"})


def test_device_preference_read_proof_default_off_reload_and_zero_writes(pg_dsn, monkeypatch):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, ch, decision = await prepare(maker)
        sid = None
        try:
            async with maker() as db:
                sub = PushSubscription(
                    endpoint=f"https://push.example.invalid/{uuid4()}",
                    p256dh="synthetic-read-key",
                    auth="synthetic-read-proof",
                )
                db.add(sub)
                await db.flush()
                sid = sub.id
                proof = {
                    "subscription_id": str(sid),
                    "endpoint": sub.endpoint,
                    "p256dh": sub.p256dh,
                    "auth": sub.auth,
                }
                await db.commit()
            if os.environ.get("MIMI086_NEGATIVE_BYPASS_DEVICE_PROOF") == "1":

                async def unchecked(db, payload, **kwargs):
                    return await db.get(PushSubscription, payload.subscription_id)

                monkeypatch.setattr(notifications, "_proved_subscription", unchecked)
            app = client_app(maker, actor)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as c:
                path = "/api/mimi/devices/preference/read"
                assert (await c.post(path, json=proof)).status_code == 403
                absent = await c.post(path, json=proof, headers=HEADERS)
                assert absent.status_code == 200, absent.text
                assert absent.json() == {
                    "subscription_id": str(sid),
                    "enabled": False,
                    "revision": None,
                    "registered": False,
                }
                bad = await c.post(path, json={**proof, "auth": "wrong"}, headers=HEADERS)
                assert bad.status_code == 404, "device proof guard was bypassed"
                async with maker() as db:
                    assert (
                        await db.scalar(
                            select(func.count())
                            .select_from(MimiDevicePreference)
                            .where(MimiDevicePreference.subscription_id == sid)
                        )
                        == 0
                    )
                saved = await c.post(
                    "/api/mimi/devices/preference", json={**proof, "enabled": True}, headers=HEADERS
                )
                assert saved.status_code == 200
                again = await c.post(path, json=proof, headers=HEADERS)
                assert again.json() == {
                    "subscription_id": str(sid),
                    "enabled": True,
                    "revision": 1,
                    "registered": True,
                }
            # New request app/session is a reload, no mutation response cache.
            app = client_app(maker, actor)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as c:
                assert (await c.post(path, json=proof, headers=HEADERS)).json()["revision"] == 1
            app = client_app(maker, foreign(actor))
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as c:
                assert (await c.post(path, json=proof, headers=HEADERS)).status_code == 404
            async with maker() as db:
                pref = (
                    await db.scalars(
                        select(MimiDevicePreference).where(
                            MimiDevicePreference.subscription_id == sid
                        )
                    )
                ).one()
                assert pref.enabled and pref.revision == 1
        finally:
            await cleanup(maker, cid, ids)
            if sid:
                await drop_device(maker, sid)
            await engine.dispose()

    asyncio.run(scenario())


def test_feedback_bundle_ids_survive_reload_with_causal_scope_and_expiry(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, ch, decision = await prepare(maker)
        other = None
        try:
            app = client_app(maker, actor)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as c:
                snap = (await c.get(f"/api/mimi/conversations/{cid}")).json()
                target = next(m["id"] for m in snap["messages"] if m["role"] == "assistant")
                saved = await c.post(
                    f"/api/mimi/conversations/{cid}/feedback",
                    headers=HEADERS,
                    json={
                        "client_id": str(uuid4()),
                        "target_type": "turn",
                        "target_id": target,
                        "comment": "Synthetic old-answer correction",
                        "evidence_bundle_ids": [],
                    },
                )
                assert saved.status_code == 201
                bundle_id = saved.json()["evidence_bundle_ids"][0]
            app = client_app(maker, actor)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as c:
                reloaded = (await c.get(f"/api/mimi/conversations/{cid}")).json()
                record = next(f for f in reloaded["feedback"] if f["id"] == saved.json()["id"])
                assert record["evidence_bundle_ids"] == [bundle_id]
                evidence = await c.get(f"/api/mimi/conversations/{cid}/evidence/{bundle_id}")
                assert evidence.status_code == 200
                assert evidence.json()["metadata"]["target_id"] == target
                assert evidence.json()["metadata"]["hidden_reasoning"] == "EXCLUDED"
                async with maker() as db:
                    view = await service.create_conversation(
                        db, actor, service.ConversationCreate()
                    )
                    other = view["id"]
                    await db.commit()
                assert (
                    await c.get(f"/api/mimi/conversations/{other}/evidence/{bundle_id}")
                ).status_code == 404
            app = client_app(maker, foreign(actor))
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as c:
                assert (
                    await c.get(f"/api/mimi/conversations/{cid}/evidence/{bundle_id}")
                ).status_code == 404
            async with maker() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiEvidence)
                        .where(MimiEvidence.conversation_id == cid)
                    )
                    == 1
                )
                bundle = await db.get(MimiEvidence, UUID(bundle_id))
                bundle.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                await db.commit()
            app = client_app(maker, actor)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as c:
                expired = await c.get(f"/api/mimi/conversations/{cid}/evidence/{bundle_id}")
                assert expired.status_code == 410
        finally:
            await cleanup(maker, cid, ids)
            if other:
                await cleanup(maker, other, [])
            await engine.dispose()

    asyncio.run(scenario())


def test_receipt_lookup_exact_owner_binding_outside_snapshot_window_zero_replay(
    pg_dsn, monkeypatch
):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, ch, decision = await prepare(maker)
        key = "synthetic-recovery-" + str(uuid4())
        try:
            app = client_app(maker, actor)
            path = f"/api/mimi/conversations/{cid}/change-sets/{ch}/receipt"
            params = {"digest": decision.digest, "nonce": str(decision.nonce)}
            headers = {"Idempotency-Key": key}
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as c:
                missing = await c.get(path, params=params, headers=headers)
                assert missing.status_code == 404
                async with maker() as db:
                    original = await service.confirm_change_set(db, actor, ch, decision, key)
                    await db.commit()  # Simulated lost HTTP success, never replay confirm.
                monkeypatch.setattr(service, "MAX_MESSAGES", 0)
                assert (await c.get(f"/api/mimi/conversations/{cid}")).json()["receipts"] == []
                found = await c.get(path, params=params, headers=headers)
                assert found.status_code == 200, found.text
                assert found.json()["id"] == str(original["id"])
                assert found.json()["result"]["task_ids"] == [str(i) for i in ids]
                for changed, h in [
                    ({**params, "digest": "f" * 64}, headers),
                    ({**params, "nonce": str(uuid4())}, headers),
                    (params, {"Idempotency-Key": key + "-different"}),
                ]:
                    assert (await c.get(path, params=changed, headers=h)).status_code == 409
                assert (
                    await c.get(path, params={**params, "digest": "x"}, headers=headers)
                ).status_code == 422
            if os.environ.get("MIMI086_NEGATIVE_BYPASS_READ_OWNER") == "1":
                rightful = service._owner_id(actor)
                monkeypatch.setattr(service, "_owner_id", lambda _actor: rightful)
            app = client_app(maker, foreign(actor))
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as c:
                denied = await c.get(path, params=params, headers=headers)
                assert denied.status_code == 404, "receipt owner read guard was bypassed"
            async with maker() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiExecutionReceipt)
                        .where(MimiExecutionReceipt.change_set_id == ch)
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiNotificationIntent)
                        .where(MimiNotificationIntent.run_id == rid)
                    )
                    == 2
                )
                versions = list(
                    (
                        await db.scalars(
                            select(Task.collection_version)
                            .where(Task.id.in_(ids))
                            .order_by(Task.id)
                        )
                    ).all()
                )
                assert versions == [2, 2]
                conv = await db.get(MimiConversation, cid)
                conv.sensitivity, conv.is_private = "private", True
                await db.commit()
            app = client_app(maker, actor)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as c:
                assert (await c.get(path, params=params, headers=headers)).status_code == 404
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_attention_http_owner_known_route_get_zero_domain_writes(pg_dsn, monkeypatch):
    import hashlib
    import json
    import re

    from sqlalchemy import delete, text

    from app.core.sessions import SESSION_COOKIE_NAME, hash_session_token
    from app.domain.auth import PostgresSessionStore
    from app.domain.models import AuthSession
    from app.web.deps import get_session_store
    from app.web.routers import mimi as router

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, ch, decision = await prepare(maker)
        session_ids = []
        counters = {"confirm": 0, "provider": 0}
        tables = (
            "task",
            "task_item",
            "one_shot_reminder",
            "reminder_dispatch",
            "mimi_conversation",
            "mimi_message",
            "mimi_run",
            "mimi_event",
            "mimi_provider_call",
            "mimi_change_set",
            "mimi_execution_receipt",
            "mimi_refresh_marker",
            "mimi_notification_intent",
            "mimi_notification_delivery",
            "mimi_device_preference",
            "mimi_feedback",
            "mimi_evidence",
        )

        async def snapshot():
            result = {}
            async with maker() as db:
                for table in tables:
                    value = (
                        await db.execute(
                            text(
                                f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id), '[]'::jsonb) "
                                f"FROM microsched.{table} t"
                            )
                        )
                    ).scalar_one()
                    result[table] = hashlib.sha256(
                        json.dumps(value, sort_keys=True).encode()
                    ).hexdigest()
            return result

        async def forbidden_confirm(*args, **kwargs):
            counters["confirm"] += 1
            pytest.fail("locator GET must not confirm")

        async def forbidden_provider(*args, **kwargs):
            counters["provider"] += 1
            pytest.fail("locator GET must not dispatch a provider")

        monkeypatch.setattr(router, "confirm_change_set", forbidden_confirm)
        monkeypatch.setattr(service, "openrouter_complete", forbidden_provider)
        try:
            store = PostgresSessionStore(maker, 30)
            tokens = [
                await store.create(actor.user_email),
                await store.create("foreign-last-http@example.test"),
                await store.create(actor.user_email),
            ]
            async with maker() as db:
                for token in tokens:
                    row = (
                        await db.scalars(
                            select(AuthSession).where(
                                AuthSession.token_hash == hash_session_token(token)
                            )
                        )
                    ).one()
                    session_ids.append(row.id)
                expired = await db.get(AuthSession, session_ids[2])
                expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                owner_session = await db.get(AuthSession, session_ids[0])
                initial_seen, initial_expiry = owner_session.last_seen_at, owner_session.expires_at
                intent = (
                    await db.scalars(
                        select(MimiNotificationIntent).where(MimiNotificationIntent.run_id == rid)
                    )
                ).one()
                iid, locator = intent.id, intent.locator
                owner_id = (await db.get(MimiConversation, cid)).owner_id
                assert re.fullmatch(r"[A-Za-z0-9_-]{32}", locator)
                await db.commit()
            app = create_app()
            app.dependency_overrides[get_session_store] = lambda: store

            async def db_session():
                async with maker() as db:
                    try:
                        yield db
                        await db.commit()
                    except Exception:
                        await db.rollback()
                        raise

            app.dependency_overrides[get_session] = db_session
            assert require_session not in app.dependency_overrides
            if os.environ.get("MIMI086_LAST_NEGATIVE") == "locator_owner":
                original_resolver = router.resolve_locator

                async def wrong_owner(db, _owner, supplied):
                    return await original_resolver(db, owner_id, supplied)

                monkeypatch.setattr(router, "resolve_locator", wrong_owner)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as client:
                path = "/api/mimi/attention/resolve/" + locator
                for token, suffix, expected in (
                    (None, "", 401),
                    ("synthetic-unknown-session", "", 401),
                    (tokens[2], "", 401),
                    (tokens[1], "", 404),
                    (tokens[0], "tampered", 404),
                    (tokens[0], "", 200),
                ):
                    client.cookies.clear()
                    if token is not None:
                        client.cookies.set(SESSION_COOKIE_NAME, token)
                    before = await snapshot()
                    response = await client.get(
                        path + suffix,
                        headers={"Origin": "http://test", "Sec-Fetch-Site": "same-origin"},
                    )
                    assert response.status_code == expected, (
                        "HTTP locator owner/auth guard was bypassed"
                    )
                    assert await snapshot() == before, "locator GET caused a business/Mimi write"
                    assert counters == {"confirm": 0, "provider": 0}
                    if expected == 200:
                        assert response.json()["path"] == "/mimi"
                        assert response.json()["conversation_id"] == str(cid)
                        assert response.json()["run_id"] == str(rid)
                        assert "access-control-allow-origin" not in response.headers
            async with maker() as db:
                owner_session = await db.get(AuthSession, session_ids[0])
                assert owner_session.last_seen_at > initial_seen
                assert owner_session.expires_at > initial_expiry
                assert await db.get(AuthSession, session_ids[2]) is None
                assert (await db.get(MimiNotificationIntent, iid)).read_at is None
                assert counters == {"confirm": 0, "provider": 0}
        finally:
            await cleanup(maker, cid, ids)
            async with maker() as db:
                await db.execute(delete(AuthSession).where(AuthSession.id.in_(session_ids)))
                await db.commit()
            await engine.dispose()

    asyncio.run(scenario())
