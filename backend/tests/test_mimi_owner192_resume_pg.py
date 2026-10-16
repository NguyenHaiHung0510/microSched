"""Small real service/SDK/PG regression; current runner, no LangGraph bypass."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import httpx2
import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import auth, local_contract  # noqa: F401

from app.agent import config_policy, crypto, openai_sdk, service
from app.agent.models import MimiConversation, MimiEvent, MimiMessage, MimiProviderCall, MimiRun
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AppSetting

pytestmark = pytest.mark.pg


def test_ordinary_resume_first_typed_overflow_retains_recovery_and_user_source(pg_dsn, monkeypatch):
    for key, value in {
        "MIMI_LIVE_PROVIDER_ENABLED": "true",
        "MIMI_CONTEXT_V1_ENABLED": "true",
        "MIMI_STANDARD_API_KEY": "synthetic-never-sent",
        "MIMI_TRANSPORT": "openai_sdk",
        "MIMI_RUNNER": "current",
        "MIMI_ROUTE_MODE": "exact",
        "MIMI_ROUTE_MODEL": "deepseek/deepseek-v4.1-flash",
        "MIMI_ROUTE_PROVIDER": "deepinfra",
        "MIMI_ROUTE_QUANTIZATION": "fp8",
        "MIMI_ROUTE_MAX_INPUT_PRICE": ".36",
        "MIMI_ROUTE_MAX_OUTPUT_PRICE": "1.44",
    }.items():
        monkeypatch.setenv(key, value)
    policy_key = "mimi.owner192." + uuid7().hex
    monkeypatch.setattr(config_policy, "POLICY_KEY", policy_key)
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, original_id = auth(), uuid7()
        cid = None
        try:
            async with maker() as db:
                view = await service.create_conversation(db, actor, service.ConversationCreate())
                cid = view["id"]
                conv = await db.get(MimiConversation, cid)
                source_text = "Yêu cầu synthetic giữ nguyên 🌸"
                run = MimiRun(
                    id=original_id,
                    conversation_id=cid,
                    generation=conv.generation,
                    state="halted",
                    provider_outcome="failed",
                    error_code="owner_paused",
                    execution_lease={},
                    source_versions={},
                    deadline=datetime.now(UTC) + timedelta(minutes=5),
                )
                db.add(run)
                await db.flush()
                db.add(
                    MimiMessage(
                        conversation_id=cid,
                        run_id=original_id,
                        role="user",
                        sequence=1,
                        content_ciphertext=crypto.seal_content(
                            crypto.unwrap_dek(conv.dek_wrapped),
                            source_text,
                            aad=crypto.message_aad(cid, 1, "user"),
                        ),
                        content_sha256=hashlib.sha256(source_text.encode()).hexdigest(),
                        content_bytes=len(source_text.encode()),
                    )
                )
                conv.next_message_sequence = 2
                conv.generation += 1
                await db.commit()
            wires = []
            # The legacy direct-row/no-event case remains valid. A present
            # binding must agree even when that original row is still present.
            async with maker() as db:
                original_source, used = await service._resume_context(db, cid, original_id)
                assert original_source.run_id == original_id and used == 0
                valid_binding = {
                    "message_id": str(original_source.id),
                    "content_sha256": original_source.content_sha256,
                    "overflow_recovery_attempt": 0,
                }
                binding_event = MimiEvent(
                    run_id=original_id,
                    sequence=1,
                    kind="run.user_source",
                    payload=valid_binding,
                )
                db.add(binding_event)
                await db.flush()
                for changed in (
                    {**valid_binding, "content_sha256": "0" * 64},
                    {**valid_binding, "message_id": str(uuid7())},
                    {"overflow_recovery_attempt": 0},
                ):
                    binding_event.payload = changed
                    await db.flush()
                    with pytest.raises(HTTPException, match="resume_source_missing_or_changed"):
                        await service._resume_context(db, cid, original_id)
                binding_event.payload = valid_binding
                await db.flush()
                restored, used = await service._resume_context(db, cid, original_id)
                assert restored.id == original_source.id and used == 0
                await db.commit()
            native_factory = openai_sdk._client
            clients = []

            async def handler(request):
                wire = json.loads(request.content)
                wires.append(wire)
                if "summary" in wire.get("response_format", {}).get("json_schema", {}).get(
                    "schema", {}
                ).get("properties", {}):
                    return httpx2.Response(
                        200,
                        json={
                            "id": "synthetic-owner192-helper",
                            "object": "chat.completion",
                            "created": 1,
                            "model": wire["model"],
                            "provider": "DeepInfra",
                            "choices": [
                                {
                                    "index": 0,
                                    "finish_reason": "stop",
                                    "message": {
                                        "role": "assistant",
                                        "content": json.dumps(
                                            {
                                                "summary": "Giữ yêu cầu synthetic.",
                                                "constraints": [],
                                                "supersessions": [],
                                                "resolutions": [],
                                            }
                                        ),
                                    },
                                }
                            ],
                            "usage": {
                                "prompt_tokens": 10,
                                "completion_tokens": 5,
                                "total_tokens": 15,
                                "cost": 0,
                            },
                        },
                    )
                return httpx2.Response(400, json={"error": {"code": "context_length_exceeded"}})

            def factory(settings, *, api_key, client):
                transport = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
                clients.append(transport)
                return native_factory(settings, api_key="synthetic-never-sent", client=transport)

            monkeypatch.setattr(openai_sdk, "_client", factory)
            try:
                async with maker() as db:
                    _, successor, payload = await service.prepare_run_resume(db, actor, original_id)
                    await db.commit()
                async with maker() as db:
                    await service.send_message(
                        db,
                        actor,
                        cid,
                        payload,
                        reserved_run_id=successor,
                        parent_run_id=original_id,
                        record_user_message=False,
                    )
                    await db.commit()
                async with maker() as db:
                    run = await db.get(MimiRun, successor)
                    calls = (
                        (
                            await db.execute(
                                select(MimiProviderCall).where(MimiProviderCall.run_id == successor)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    assert len(wires) == len(calls) == 1
                    assert calls[0].route["input_overflow_refusal"] is True
                    assert run.state == "retryable", run.error_code
                    assert calls[0].route["overflow_recovery_attempt"] == 0
                    event = (
                        await db.execute(
                            select(MimiEvent).where(
                                MimiEvent.run_id == successor, MimiEvent.kind == "run.user_source"
                            )
                        )
                    ).scalar_one()
                    accepted_binding = dict(event.payload)
                    event.payload = {**accepted_binding, "content_sha256": "0" * 64}
                    await db.flush()
                    with pytest.raises(HTTPException, match="resume_source_missing_or_changed"):
                        await service.prepare_run_resume(db, actor, successor)
                    event.payload = accepted_binding
                    await db.flush()
                    original_state, original_outcome = run.state, run.provider_outcome
                    run.state, run.provider_outcome = "outcome_unknown", "unknown"
                    with pytest.raises(HTTPException, match="reconciliation_required"):
                        await service.prepare_run_resume(db, actor, successor)
                    run.state, run.provider_outcome = original_state, original_outcome
                    original_source, used = await service._resume_context(db, cid, successor)
                    assert used == 1 and original_source.run_id == original_id
                    _, recovery_id, following = await service.prepare_run_resume(
                        db, actor, successor
                    )
                    with pytest.raises(HTTPException, match="resumed_by:"):
                        await service.prepare_run_resume(db, actor, successor)
                    assert following.content == source_text
                    assert (
                        await db.execute(
                            select(func.count())
                            .select_from(MimiMessage)
                            .where(MimiMessage.conversation_id == cid, MimiMessage.role == "user")
                        )
                    ).scalar_one() == 1
                    await db.commit()
                async with maker() as db:
                    await service.send_message(
                        db,
                        actor,
                        cid,
                        following,
                        reserved_run_id=recovery_id,
                        parent_run_id=successor,
                        record_user_message=False,
                    )
                    await db.commit()
                async with maker() as db:
                    final_run = await db.get(MimiRun, recovery_id)
                    recovered_calls = (
                        (
                            await db.execute(
                                select(MimiProviderCall)
                                .where(MimiProviderCall.run_id == recovery_id)
                                .order_by(MimiProviderCall.attempt)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    mains = [
                        item for item in recovered_calls if item.route.get("purpose") == "main"
                    ]
                    assert final_run.state == "halted" and len(mains) == 1
                    assert mains[0].route["overflow_recovery_attempt"] == 1
                    assert mains[0].route["input_overflow_refusal"] is True
                    assert (
                        len(wires) == 3
                    )  # refused main, real SDK summary helper, second refused main
                    with pytest.raises(HTTPException, match="cannot_resume"):
                        await service.prepare_run_resume(db, actor, recovery_id)
                    assert (
                        await db.execute(
                            select(func.count())
                            .select_from(MimiMessage)
                            .where(MimiMessage.conversation_id == cid, MimiMessage.role == "user")
                        )
                    ).scalar_one() == 1
            finally:
                for client in clients:
                    await client.aclose()
        finally:
            try:
                async with maker() as db:
                    if cid is not None:
                        await db.execute(delete(MimiConversation).where(MimiConversation.id == cid))
                    await db.execute(delete(AppSetting).where(AppSetting.key == policy_key))
                    await db.commit()
            finally:
                await engine.dispose()

    asyncio.run(scenario())
