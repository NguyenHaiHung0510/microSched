"""Real PostgreSQL workspace/crypto/session/confirmation contracts, no providers."""

import asyncio
import base64
import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_owner_workspace import actor

from app.agent import config_policy, crypto, notifications, service
from app.agent.compaction import CALENDAR_HISTORY_MARKER
from app.agent.context import AssistantText, ToolRequest, ToolRequests
from app.agent.models import (
    MimiConversation,
    MimiDevicePreference,
    MimiEvent,
    MimiExecutionReceipt,
    MimiMessage,
    MimiNotificationDelivery,
    MimiNotificationIntent,
    MimiRun,
)
from app.agent.openrouter import AgentCompletion
from app.agent.owner_workspace import OWNER_WORKSPACE_ID, legacy_owner_id
from app.agent.tools.calendar_reads import CALENDAR_READ_TOOL
from app.core import crypto as master_crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.auth import PostgresSessionStore
from app.domain.models import AppSetting, AuthSession, DayAnnotation, PushSubscription, Task
from app.main import create_app
from app.web.deps import get_session, get_session_store

pytestmark = pytest.mark.pg
A, B, FOREIGN = "a@example.test", "b@example.test", "foreign@example.test"
HEADERS = {"Origin": "http://test", "Sec-Fetch-Site": "same-origin", "X-Mimi-CSRF": "1"}


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    for key, value in {
        "MIMI_P0_DISABLE_DOTENV": "1",
        "APP_ENV": "local",
        "OAUTH_STATE_SECRET": "synthetic-owner-workspace-102",
        "ENCRYPTION_MASTER_KEY": base64.urlsafe_b64encode(bytes(range(32))).decode(),
        "ALLOWED_EMAILS": f"{A},{B}",
        "MIMI_OWNER_WORKSPACE_ENABLED": "true",
        "MIMI_REAL_CHAT_ENABLED": "true",
        "MIMI_LIVE_PROVIDER_ENABLED": "false",
        "MIMI_CONTEXT_V1_ENABLED": "false",
        "MIMI_COLLECTION_ENABLED": "true",
        "MIMI_NOTIFICATIONS_ENABLED": "false",
        "SESSION_COOKIE_SECURE": "false",
        "PRIVATE_PIN_BOOTSTRAP": "123456",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    master_crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    master_crypto._cipher.cache_clear()


@asynccontextmanager
async def database(pg_dsn):
    engine = create_async_engine(async_postgres_url(pg_dsn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    conversations, tasks, sessions, devices = [], [], [], []
    try:
        yield maker, conversations, tasks, sessions, devices
    finally:
        async with maker() as db:
            await db.execute(delete(MimiConversation).where(MimiConversation.id.in_(conversations)))
            await db.execute(delete(Task).where(Task.id.in_(tasks)))
            await db.execute(delete(AuthSession).where(AuthSession.id.in_(sessions)))
            await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(devices)))
            await db.commit()
        await engine.dispose()


async def legacy(db, ids, email, key, *, private=False, content=None):
    row = MimiConversation(
        id=uuid4(),
        owner_id=legacy_owner_id(email),
        client_id=key,
        sensitivity="private" if private else "standard",
        is_private=private,
        dek_wrapped=crypto.create_wrapped_dek(),
    )
    row.title_ciphertext = service._seal_conversation_title(row, "Same old title")
    db.add(row)
    await db.flush()
    ids.append(row.id)
    if content:
        db.add(
            MimiMessage(
                conversation_id=row.id,
                sequence=1,
                client_id="same-old-message-id",
                role="user",
                content_ciphertext=crypto.seal_content(
                    crypto.unwrap_dek(row.dek_wrapped),
                    content,
                    aad=crypto.message_aad(row.id, 1, "user"),
                ),
                content_bytes=len(content.encode()),
                content_sha256=service.hashlib.sha256(content.encode()).hexdigest(),
            )
        )
        row.next_message_sequence = 2
        await db.flush()
    return row.id


async def history(db, auth, *, limit=100, cursor=None):
    return await service.list_conversations(db, auth, state="all", limit=limit, cursor=cursor)


async def rows(db, model, condition):
    return [
        dict(r) for r in (await db.execute(select(model.__table__).where(condition))).mappings()
    ]


def test_legacy_union_order_crypto_duplicate_client_ids_and_foreign_private_guards(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (maker, ids, _, _, _):
            a, b = actor(A), actor(B)
            async with maker() as db:
                ca = await legacy(db, ids, A, "old-duplicate", content="Legacy A text")
                cb = await legacy(db, ids, B, "old-duplicate", content="Legacy B text")
                unique = await legacy(db, ids, A, "old-unique")
                null = await legacy(db, ids, B, None)
                foreign = await legacy(db, ids, FOREIGN, "old-duplicate")
                private = await legacy(db, ids, B, "old-private", private=True)
                await db.commit()
                before = await rows(db, MimiConversation, MimiConversation.id.in_(ids))
                messages = await rows(db, MimiMessage, MimiMessage.conversation_id.in_(ids))
            expected = [
                r["id"]
                for r in sorted(
                    (r for r in before if r["id"] in {ca, cb, unique, null}),
                    key=lambda r: (r["updated_at"], r["id"]),
                    reverse=True,
                )
            ]
            for auth in (a, b):
                async with maker() as db:
                    assert [r["id"] for r in (await history(db, auth))["items"]] == expected
                    assert (await service.current_conversation(db, auth))["id"] == expected[0]
                    seen, cursor = [], None
                    while True:
                        page = await history(db, auth, limit=1, cursor=cursor)
                        seen.extend(r["id"] for r in page["items"])
                        cursor = page["next_cursor"]
                        if not cursor:
                            break
                    assert seen == expected
                    assert (await service.conversation_view(db, auth, ca))["messages"][0][
                        "content"
                    ] == "Legacy A text"
                    assert (await service.conversation_view(db, auth, cb))["messages"][0][
                        "content"
                    ] == "Legacy B text"
                    for denied in (foreign, private):
                        with pytest.raises(HTTPException) as failure:
                            await service.conversation_view(db, auth, denied)
                        assert failure.value.status_code == 404
                    # The ambiguous old key must never select an arbitrary row or
                    # delete/rename/re-encrypt either conversation.
                    with pytest.raises(HTTPException) as conflict:
                        await service.create_conversation(
                            db, auth, service.ConversationCreate(client_id="old-duplicate")
                        )
                    assert conflict.value.status_code == 409
                    assert (
                        conflict.value.detail
                        == "conversation_client_id_ambiguous_use_conversation_id"
                    )
                    assert (
                        await service.create_conversation(
                            db, auth, service.ConversationCreate(client_id="old-unique")
                        )
                    )["id"] == unique
                    assert await rows(db, MimiConversation, MimiConversation.id.in_(ids)) == before
                    assert (
                        await rows(db, MimiMessage, MimiMessage.conversation_id.in_(ids))
                        == messages
                    )
            async with maker() as db:
                with pytest.raises(HTTPException):
                    await history(db, actor(FOREIGN))

    asyncio.run(scenario())


def test_cross_login_create_retry_serializes_and_message_ids_stay_per_conversation(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (maker, ids, _, _, _):
            key = f"shared-create-{uuid4()}"

            async def create(email):
                async with maker() as db:
                    result = await service.create_conversation(
                        db, actor(email), service.ConversationCreate(client_id=key)
                    )
                    await db.commit()
                    return result["id"]

            created = await asyncio.wait_for(asyncio.gather(*(create(e) for e in (A, B) * 4)), 15)
            ids.extend(set(created))
            assert len(set(created)) == 1
            async with maker() as db:
                cid = created[0]
                assert (await db.get(MimiConversation, cid)).owner_id == OWNER_WORKSPACE_ID
                other = (
                    await service.create_conversation(db, actor(B), service.ConversationCreate())
                )["id"]
                ids.append(other)
                for auth, selected in ((actor(A), cid), (actor(B), cid), (actor(B), other)):
                    result = await service.send_message(
                        db,
                        auth,
                        selected,
                        service.MessageCreate(client_id="same-turn", content="Hi"),
                    )
                    assert result["id"] == selected
                with pytest.raises(HTTPException) as conflict:
                    await service.send_message(
                        db,
                        actor(A),
                        cid,
                        service.MessageCreate(client_id="same-turn", content="Changed"),
                    )
                assert conflict.value.detail == "message_client_id_reused_with_different_content"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiMessage)
                        .where(MimiMessage.conversation_id == cid, MimiMessage.role == "user")
                    )
                    == 1
                )
                await db.commit()

    asyncio.run(scenario())


def test_hidden_physical_client_key_refuses_cleanly_then_restored_standard_retries(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (maker, ids, _, _, _):
            async with maker() as db:
                cid = await legacy(db, ids, A, "hidden-key", private=True)
                row = await db.get(MimiConversation, cid)
                row.owner_id = OWNER_WORKSPACE_ID
                await db.flush()
                with pytest.raises(HTTPException) as blocked:
                    await service.create_conversation(
                        db, actor(B), service.ConversationCreate(client_id="hidden-key")
                    )
                assert blocked.value.status_code == 409
                assert blocked.value.detail == "conversation_client_id_unavailable"
                row.is_private, row.sensitivity = False, "standard"
                await db.flush()
                result = await service.create_conversation(
                    db, actor(B), service.ConversationCreate(client_id="hidden-key")
                )
                assert result["id"] == cid
                await db.commit()

    asyncio.run(scenario())


def test_feature_off_on_keeps_rows_and_shared_metadata_cas_archive(pg_dsn, monkeypatch):
    async def scenario():
        async with database(pg_dsn) as (maker, ids, _, _, _):
            async with maker() as db:
                ca = await legacy(db, ids, A, "rollback-a")
                cb = await legacy(db, ids, B, "rollback-b")
                shared = (
                    await service.create_conversation(
                        db, actor(B), service.ConversationCreate(client_id="rollback-shared")
                    )
                )["id"]
                ids.append(shared)
                await db.commit()
                before = await rows(db, MimiConversation, MimiConversation.id.in_(ids))
                monkeypatch.setenv("MIMI_OWNER_WORKSPACE_ENABLED", "false")
                get_settings.cache_clear()
                assert [r["id"] for r in (await history(db, actor(A)))["items"]] == [ca]
                assert [r["id"] for r in (await history(db, actor(B)))["items"]] == [cb]
                for auth in (actor(A), actor(B)):
                    with pytest.raises(HTTPException) as reserved:
                        await service.create_conversation(
                            db, auth, service.ConversationCreate(client_id="rollback-shared")
                        )
                    assert reserved.value.status_code == 409
                    assert reserved.value.detail == "conversation_client_id_unavailable"
                    assert not await db.scalar(
                        select(MimiConversation.id).where(
                            MimiConversation.client_id == "rollback-shared",
                            MimiConversation.owner_id == legacy_owner_id(auth.user_email),
                        )
                    )
                monkeypatch.setenv("MIMI_OWNER_WORKSPACE_ENABLED", "true")
                get_settings.cache_clear()
                assert {r["id"] for r in (await history(db, actor(A)))["items"]} == set(ids)
                for auth in (actor(A), actor(B)):
                    assert (
                        await service.create_conversation(
                            db, auth, service.ConversationCreate(client_id="rollback-shared")
                        )
                    )["id"] == shared
                assert await rows(db, MimiConversation, MimiConversation.id.in_(ids)) == before
                await service.rename_conversation(
                    db,
                    actor(A),
                    cb,
                    service.ConversationRename(
                        title="Shared metadata", expected_metadata_version=1
                    ),
                )
                with pytest.raises(HTTPException) as stale:
                    await service.rename_conversation(
                        db,
                        actor(B),
                        cb,
                        service.ConversationRename(
                            title="Stale update", expected_metadata_version=1
                        ),
                    )
                assert stale.value.detail == "conversation_metadata_stale"
                await service.set_conversation_archived(
                    db,
                    actor(A),
                    shared,
                    service.ConversationStateChange(expected_metadata_version=1),
                    archived=True,
                )
                assert (await service.current_conversation(db, actor(B)))["id"] != shared
                restored = await service.set_conversation_archived(
                    db,
                    actor(B),
                    shared,
                    service.ConversationStateChange(expected_metadata_version=2),
                    archived=False,
                )
                assert restored["archived_at"] is None
                await db.commit()

    asyncio.run(scenario())


def test_legacy_preview_confirm_receipt_feedback_and_locators_across_entrances(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (maker, ids, tasks, _, _):
            a, b = actor(A), actor(B)
            async with maker() as db:
                cid = await legacy(db, ids, A, "legacy-confirm")
                view = await service.send_message(
                    db,
                    a,
                    cid,
                    service.MessageCreate(
                        client_id="legacy-create-task", content="Tạo task Synthetic workspace task"
                    ),
                )
                change = view["change_sets"][0]
                decision = service.ConfirmationDecision(
                    digest=change["digest"], nonce=change["nonce"], decision="confirm"
                )
                rid = view["runs"][-1]["id"]
                assert (await db.get(MimiRun, rid)).execution_lease["owner_id"] == str(
                    legacy_owner_id(A)
                )
                await db.commit()
            key = f"owner-confirm-{uuid4()}"
            async with maker() as db:
                with pytest.raises(HTTPException) as bad:
                    await service.confirm_change_set(
                        db, b, change["id"], decision.model_copy(update={"digest": "0" * 64}), key
                    )
                assert bad.value.status_code == 409
                await db.rollback()
            async with maker() as db:
                receipt = await service.confirm_change_set(db, b, change["id"], decision, key)
                tasks.append(receipt["task_id"])
                await db.commit()
            for auth in (a, b):
                async with maker() as db:
                    assert (
                        await service.confirm_change_set(db, auth, change["id"], decision, key)
                        == receipt
                    )
                    assert (
                        await service.read_execution_receipt(
                            db, auth, cid, change["id"], decision.digest, decision.nonce, key
                        )
                        == receipt
                    )
                    assert (await service.run_events_after(db, auth, rid, after=0))["events"]
                    assert (await service.conversation_view(db, auth, cid))["receipts"][
                        0
                    ] == receipt
            async with maker() as db:
                with pytest.raises(HTTPException):
                    await service.read_execution_receipt(
                        db, actor(FOREIGN), cid, change["id"], decision.digest, decision.nonce, key
                    )
                feedback = await service.save_feedback(
                    db,
                    b,
                    cid,
                    service.FeedbackCreate(
                        client_id="shared-feedback",
                        target_type="receipt",
                        target_id=str(receipt["id"]),
                        comment="Synthetic feedback",
                    ),
                )
                assert feedback["id"]
                assert (await db.get(MimiConversation, cid)).owner_id == legacy_owner_id(A)
                await db.commit()

    asyncio.run(scenario())


def test_actual_sessions_csrf_logout_relogin_pin_and_foreign_history(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (maker, ids, tasks, sessions, _):
            store = PostgresSessionStore(maker, 90)
            tokens = [await store.create(email) for email in (A, B, FOREIGN)]
            for token in tokens:
                sessions.append((await store.load_valid(token)).id)
            app = create_app()
            app.dependency_overrides[get_session_store] = lambda: store

            async def request_db():
                async with maker() as db:
                    try:
                        yield db
                        await db.commit()
                    except Exception:
                        await db.rollback()
                        raise

            app.dependency_overrides[get_session] = request_db
            transport = httpx.ASGITransport(app=app)
            async with (
                httpx.AsyncClient(
                    transport=transport, base_url="http://test", cookies={"ms_session": tokens[0]}
                ) as a,
                httpx.AsyncClient(
                    transport=transport, base_url="http://test", cookies={"ms_session": tokens[1]}
                ) as b,
                httpx.AsyncClient(
                    transport=transport, base_url="http://test", cookies={"ms_session": tokens[2]}
                ) as foreign,
            ):
                assert (await a.post("/api/mimi/conversations", json={})).status_code == 403
                assert (
                    await a.post(
                        "/api/mimi/conversations",
                        json={},
                        headers={**HEADERS, "Origin": "http://evil.test"},
                    )
                ).status_code == 403
                created = await a.post("/api/mimi/conversations", json={}, headers=HEADERS)
                assert created.status_code == 201
                cid = UUID(created.json()["id"])
                ids.append(cid)
                assert (await b.get(f"/api/mimi/conversations/{cid}")).status_code == 200
                assert (await foreign.get(f"/api/mimi/conversations/{cid}")).status_code == 404
                assert (await b.get("/api/mimi/conversations/current")).json()["id"] == str(cid)
                locked = await b.post(
                    "/api/tasks", json={"title": "Private synthetic", "is_private": True}
                )
                assert locked.status_code == 403
                wrong = await a.post("/api/private/unlock", json={"pin": "654321"})
                assert wrong.status_code == 401
                unlocked = await a.post("/api/private/unlock", json={"pin": "123456"})
                assert unlocked.status_code == 200
                assert (await b.get("/api/me")).json()["private_until"] is None
                private = await a.post(
                    "/api/tasks", json={"title": "Private synthetic", "is_private": True}
                )
                assert private.status_code == 201
                tasks.append(UUID(private.json()["id"]))
                assert (await b.get(f"/api/tasks/{private.json()['id']}")).status_code == 404
                assert (await a.post("/auth/logout")).status_code == 204
                a.cookies.set("ms_session", tokens[0])
                assert (await a.get(f"/api/mimi/conversations/{cid}")).status_code == 401
                new_token = await store.create(A)
                sessions.append((await store.load_valid(new_token)).id)
                a.cookies.clear()
                a.cookies.set("ms_session", new_token)
                assert (await a.get(f"/api/mimi/conversations/{cid}")).status_code == 200
                assert (await a.get("/api/me")).json()["private_until"] is None

    asyncio.run(scenario())


def test_removed_login_live_session_denied_all_mimi_common_endpoints(pg_dsn, monkeypatch):
    policy_key = f"synthetic.history-gate.{uuid4()}"
    monkeypatch.setattr(config_policy, "POLICY_KEY", policy_key)

    async def scenario():
        async with database(pg_dsn) as (maker, ids, _, sessions, _):
            store = PostgresSessionStore(maker, 90)
            tokens = [await store.create(email) for email in (A, B)]
            sessions.extend([(await store.load_valid(token)).id for token in tokens])
            app = create_app()
            app.dependency_overrides[get_session_store] = lambda: store

            async def request_db():
                async with maker() as db:
                    try:
                        yield db
                        await db.commit()
                    except Exception:
                        await db.rollback()
                        raise

            app.dependency_overrides[get_session] = request_db
            transport = httpx.ASGITransport(app=app)

            def client(token):
                return httpx.AsyncClient(
                    transport=transport, base_url="http://test", cookies={"ms_session": token}
                )

            policy_url = "/api/mimi/operating-policy"
            try:
                async with client(tokens[0]) as a, client(tokens[1]) as b:
                    conversation = await a.post("/api/mimi/conversations", json={}, headers=HEADERS)
                    assert conversation.status_code == 201
                    cid = UUID(conversation.json()["id"])
                    ids.append(cid)
                    reads = (
                        "/api/mimi/capabilities",
                        "/api/mimi/context/tasks",
                        policy_url,
                        f"/api/mimi/conversations/{cid}",
                    )
                    assert [((await a.get(path)).status_code) for path in reads] == [200] * 4
                    policy = (await b.get(policy_url)).json()["policy"]
                    update = {**policy, "expected_revision": policy["revision"]}
                    del update["revision"]
                    monkeypatch.setenv("ALLOWED_EMAILS", B)
                    get_settings.cache_clear()
                    assert (await a.get("/api/me")).status_code == 200  # Same live app cookie.
                    statuses = [(await a.get(path)).status_code for path in reads]
                    refused_write = await a.put(policy_url, json=update, headers=HEADERS)
                    assert statuses + [refused_write.status_code] == [404] * 5
                    assert [((await b.get(path)).status_code) for path in reads] == [200] * 4
                    assert (await b.get(policy_url)).json()["policy"] == policy
                    assert (await b.put(policy_url, json=update)).status_code == 403
                    allowed = await b.put(policy_url, json=update, headers=HEADERS)
                    assert allowed.status_code == 200
                    assert allowed.json()["policy"]["revision"] == policy["revision"] + 1
            finally:
                async with maker() as db:
                    await db.execute(delete(AppSetting).where(AppSetting.key == policy_key))
                    await db.commit()

    asyncio.run(scenario())


def test_confirm_receipt_cannot_satisfy_changed_decision_across_logins(pg_dsn):
    async def scenario():
        async with database(pg_dsn) as (maker, ids, tasks, _, _):
            a, b = actor(A), actor(B)
            title = f"Decision binding {uuid4()}"
            async with maker() as db:
                cid = await legacy(db, ids, A, "decision-binding")

                async def propose(client_id):
                    view = await service.send_message(
                        db,
                        a,
                        cid,
                        service.MessageCreate(client_id=client_id, content=f"Tạo task {title}"),
                    )
                    return view["change_sets"][-1]

                change = await propose("confirm-first")
                confirm = service.ConfirmationDecision(
                    digest=change["digest"], nonce=change["nonce"], decision="confirm"
                )
                reject = confirm.model_copy(update={"decision": "reject"})
                key = uuid4().hex
                receipt = await service.confirm_change_set(db, a, change["id"], confirm, key)
                tasks.append(receipt["task_id"])
                before = await rows(
                    db, MimiExecutionReceipt, MimiExecutionReceipt.id == receipt["id"]
                )
                for attempt, detail in (
                    (key, "idempotency_key_reused_with_different_decision"),
                    (uuid4().hex, "change_set_already_executed_with_different_idempotency_key"),
                ):
                    with pytest.raises(HTTPException) as conflict:
                        await service.confirm_change_set(db, b, change["id"], reject, attempt)
                    assert conflict.value.status_code == 409 and conflict.value.detail == detail
                assert (
                    await service.confirm_change_set(db, b, change["id"], confirm, key) == receipt
                )
                assert (
                    await rows(db, MimiExecutionReceipt, MimiExecutionReceipt.id == receipt["id"])
                    == before
                )

                second = await propose("reject-first")
                reject = service.ConfirmationDecision(
                    digest=second["digest"], nonce=second["nonce"], decision="reject"
                )
                second_key = uuid4().hex
                declined = await service.confirm_change_set(db, a, second["id"], reject, second_key)
                assert (
                    await service.confirm_change_set(db, b, second["id"], reject, second_key)
                    == declined
                )
                with pytest.raises(HTTPException, match="change_set_rejected"):
                    await service.confirm_change_set(
                        db,
                        b,
                        second["id"],
                        reject.model_copy(update={"decision": "confirm"}),
                        second_key,
                    )
                assert not await rows(
                    db, MimiExecutionReceipt, MimiExecutionReceipt.change_set_id == second["id"]
                )
                assert (
                    await db.scalar(
                        select(func.count()).select_from(Task).where(Task.title == title)
                    )
                    == 1
                )
                await db.commit()

    asyncio.run(scenario())


def test_native_context_uses_selected_legacy_conversation_not_workspace_union(pg_dsn, monkeypatch):
    for key, value in {
        "MIMI_LIVE_PROVIDER_ENABLED": "true",
        "MIMI_CONTEXT_V1_ENABLED": "true",
        "MIMI_STANDARD_API_KEY": "synthetic-not-sent",
        "MIMI_ROUTE_MODEL": "deepseek/deepseek-v4.1-flash-1017",
        "MIMI_ROUTE_REASONING_EFFORT": "high",
        "MIMI_ROUTE_PROVIDER": "Synthetic",
        "MIMI_ROUTE_QUANTIZATION": "fp16",
        "MIMI_ROUTE_MAX_INPUT_PRICE": "1",
        "MIMI_ROUTE_MAX_OUTPUT_PRICE": "1",
        "MIMI_RUNNER": "current",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    observed = []

    async def complete(messages, **kwargs):
        observed.append(messages)
        return AgentCompletion(
            outcome=AssistantText(text="Selected workspace history only"),
            response_id="synthetic-102",
            usage={},
            provider="Synthetic",
            model="deepseek/deepseek-v4.1-flash-1017",
        )

    monkeypatch.setattr(service, "openrouter_complete", complete)

    async def scenario():
        async with database(pg_dsn) as (maker, ids, _, _, _):
            async with maker() as db:
                cid = await legacy(db, ids, A, "selected", content="SELECTED-102-HISTORY")
                await legacy(db, ids, B, "unselected", content="UNSELECTED-102-HISTORY")
                view = await service.send_message(
                    db,
                    actor(B),
                    cid,
                    service.MessageCreate(
                        client_id="native-selected-turn", content="Continue selected conversation"
                    ),
                )
                assert view["runs"][-1]["state"] == "completed"
                assert view["messages"][-1]["content"] == "Selected workspace history only"
                assert len(observed) == 1
                assert "SELECTED-102-HISTORY" in json.dumps(observed)
                assert "UNSELECTED-102-HISTORY" not in json.dumps(observed)
                assert view["messages"][-1]["provenance"]["origin"] == "model_answer"
                await db.commit()

    asyncio.run(scenario())


def test_calendar_text_reloads_selected_legacy_thread_and_reads_current_standard_sources(
    pg_dsn, monkeypatch
):
    for key, value in {
        "MIMI_CALENDAR_READ_ENABLED": "true",
        "MIMI_LIVE_PROVIDER_ENABLED": "true",
        "MIMI_CONTEXT_V1_ENABLED": "true",
        "MIMI_STANDARD_API_KEY": "synthetic-not-sent",
        "MIMI_ROUTE_MODE": "native",
        "MIMI_TRANSPORT": "httpx",
        "MIMI_RUNNER": "current",
        "MIMI_ROUTE_MODEL": "deepseek/deepseek-v4.1-flash-1017",
        "MIMI_ROUTE_REASONING_EFFORT": "none",
        "MIMI_ROUTE_MAX_INPUT_PRICE": "1",
        "MIMI_ROUTE_MAX_OUTPUT_PRICE": "1",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(config_policy, "POLICY_KEY", f"synthetic.task102.{uuid4()}")
    get_settings.cache_clear()
    day = "2094-11-16"
    wires = []
    old = "OBSOLETE-102-CALENDAR-ANSWER"
    public, private = "CURRENT-102-CALENDAR", "PRIVATE-102-CALENDAR"

    async def completion(messages, **kwargs):
        wire = json.dumps(messages)
        wires.append(wire)
        assert old not in wire and private not in wire and "OTHER-102-THREAD" not in wire
        assert CALENDAR_HISTORY_MARKER in wire and "SELECTED-102-THREAD" in wire
        assert CALENDAR_READ_TOOL in wire
        if len(wires) == 1:
            outcome = ToolRequests(
                requests=(
                    ToolRequest(
                        call_id="synthetic-calendar-read",
                        name=CALENDAR_READ_TOOL,
                        arguments={"date": day, "kinds": ["annotation"]},
                    ),
                )
            )
        else:
            assert len(wires) == 2 and public in wire
            outcome = AssistantText(text="Synthetic current Calendar answer")
        return AgentCompletion(
            outcome=outcome,
            response_id=f"synthetic-history-calendar-{len(wires)}",
            usage={},
            provider="Synthetic",
            model=kwargs["settings"].mimi_route_model,
        )

    monkeypatch.setattr(service, "openrouter_complete", completion)

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        try:
            async with engine.connect() as connection, connection.begin() as transaction:
                maker = async_sessionmaker(
                    connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
                )
                monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
                async with maker() as db:
                    ids = []
                    a, b = actor(A), actor(B)
                    cid = await legacy(db, ids, A, "calendar-legacy", content="SELECTED-102-THREAD")
                    await legacy(db, ids, B, "calendar-other", content="OTHER-102-THREAD")
                    row = await db.get(MimiConversation, cid)
                    run = MimiRun(
                        id=uuid4(),
                        conversation_id=cid,
                        generation=1,
                        state="completed",
                        deadline=datetime.now(UTC) + timedelta(minutes=5),
                    )
                    db.add(run)
                    await db.flush()
                    db.add(
                        MimiEvent(
                            run_id=run.id,
                            sequence=1,
                            kind="tool.read_result",
                            payload={"tool": CALENDAR_READ_TOOL},
                        )
                    )
                    await service._add_assistant_message(
                        db,
                        row,
                        run.id,
                        crypto.unwrap_dek(row.dek_wrapped),
                        old,
                        producer_code="local_deterministic_result",
                    )
                    row.generation = 2
                    for label, hidden in ((public, False), (private, True)):
                        db.add(
                            DayAnnotation(
                                starts_on=date.fromisoformat(day),
                                ends_on=date.fromisoformat(day),
                                label=label,
                                is_private=hidden,
                            )
                        )
                    await db.flush()
                    original = await service.conversation_view(db, a, cid)
                    assert original["messages"][-1]["content"] == old
                    result = await service.send_message(
                        db,
                        b,
                        cid,
                        service.MessageCreate(client_id="calendar-next", content="Read the day"),
                    )
                    terminal = result["runs"][-1]
                    assert (len(wires), terminal["state"], terminal["error_code"]) == (
                        2,
                        "completed",
                        None,
                    )
                    assert [m["content"] for m in result["messages"]][-3:] == [
                        old,
                        "Read the day",
                        "Synthetic current Calendar answer",
                    ]
                    assert result["messages"][-1]["provenance"]["producer_code"] == "provider_text"
                    lease = (await db.get(MimiRun, result["runs"][-1]["id"])).execution_lease
                    assert lease["owner_id"] == str(legacy_owner_id(A))
                    assert CALENDAR_READ_TOOL in lease["capabilities"] and not result["change_sets"]
                await transaction.rollback()
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_notification_attention_uses_aliases_but_push_preserves_exact_opt_in_scope(
    pg_dsn, monkeypatch
):
    monkeypatch.setenv("MIMI_NOTIFICATIONS_ENABLED", "true")
    get_settings.cache_clear()

    async def scenario():
        async with database(pg_dsn) as (maker, ids, tasks, _, devices):
            async with maker() as db:
                cid = await legacy(db, ids, A, "notification-legacy")
                sub = PushSubscription(
                    endpoint=f"https://push.example.invalid/{uuid4()}",
                    p256dh="synthetic",
                    auth="synthetic",
                )
                db.add(sub)
                await db.flush()
                devices.append(sub.id)
                pref = MimiDevicePreference(
                    owner_id=legacy_owner_id(B), subscription_id=sub.id, enabled=True
                )
                same_sub = PushSubscription(
                    endpoint=f"https://push.example.invalid/{uuid4()}",
                    p256dh="synthetic",
                    auth="synthetic",
                )
                db.add_all([pref, same_sub])
                await db.flush()
                devices.append(same_sub.id)
                same_owner = MimiDevicePreference(
                    owner_id=legacy_owner_id(A), subscription_id=same_sub.id, enabled=True
                )
                db.add(same_owner)
                await db.flush()
                result = await service.send_message(
                    db,
                    actor(B),
                    cid,
                    service.MessageCreate(
                        client_id="notice-turn", content="Tạo task Synthetic notice task"
                    ),
                )
                change = result["change_sets"][0]
                notice = (
                    await db.scalars(
                        select(MimiNotificationIntent).where(
                            MimiNotificationIntent.conversation_id == cid
                        )
                    )
                ).one()
                delivery = (
                    await db.scalars(
                        select(MimiNotificationDelivery).where(
                            MimiNotificationDelivery.intent_id == notice.id
                        )
                    )
                ).one()
                assert delivery.preference_id == same_owner.id
                assert await notifications.eligible_delivery(db, notice, same_owner)
                assert not await notifications.eligible_delivery(db, notice, pref)
                assert (await notifications.list_attention(db, OWNER_WORKSPACE_ID))[0][
                    "conversation_id"
                ] == cid
                assert (
                    await notifications.resolve_locator(db, OWNER_WORKSPACE_ID, notice.locator)
                )["conversation_id"] == str(cid)
                proof = notifications.DevicePreferenceProof(
                    subscription_id=sub.id, endpoint=sub.endpoint, p256dh=sub.p256dh, auth=sub.auth
                )
                assert (await notifications.read_preference(db, OWNER_WORKSPACE_ID, proof))[
                    "enabled"
                ]
                with pytest.raises(HTTPException):
                    await notifications.read_preference(db, legacy_owner_id(FOREIGN), proof)
                decision = service.ConfirmationDecision(
                    digest=change["digest"], nonce=change["nonce"], decision="confirm"
                )
                receipt = await service.confirm_change_set(
                    db, actor(A), change["id"], decision, uuid4().hex
                )
                tasks.append(receipt["task_id"])
                await db.commit()

    asyncio.run(scenario())
