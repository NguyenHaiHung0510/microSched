"""P2 uses the assigned synthetic DB, with no schema/retention or provider changes."""

import asyncio
import base64
import hashlib
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid7

import pytest
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import crypto as mimi_crypto
from app.agent import service
from app.agent.models import MimiConversation, MimiEvent, MimiMessage, MimiProviderCall, MimiRun
from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession

pytestmark = pytest.mark.pg


def test_snapshot_aggregates_beyond_public_limits_and_late_usage_replaces(pg_dsn, monkeypatch):
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("OAUTH_STATE_SECRET", "p2-synthetic-only")
    get_settings.cache_clear()
    crypto._cipher.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = AuthSession(
            token_hash="p2-synthetic",
            user_email="p2@example.invalid",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        other = auth.model_copy(update={"user_email": "other-p2@example.invalid"})
        conversation_id, unrelated_id = uuid7(), uuid7()
        wrapped = mimi_crypto.create_wrapped_dek()
        dek = mimi_crypto.unwrap_dek(wrapped)
        last_call_id = None
        try:
            async with maker() as db:
                db.add_all(
                    [
                        MimiConversation(
                            id=identity,
                            owner_id=service._owner_id(auth),
                            sensitivity="standard",
                            dek_wrapped=wrapped,
                            generation=101,
                            next_message_sequence=102,
                        )
                        for identity in [conversation_id, unrelated_id]
                    ]
                )
                await db.flush()
                for i in range(101):
                    run_id = uuid7()
                    db.add(
                        MimiRun(
                            id=run_id,
                            conversation_id=conversation_id,
                            generation=i + 1,
                            state="completed",
                            deadline=datetime.now(UTC),
                        )
                    )
                    await db.flush()
                    text = f"Synthetic answer {i}"
                    db.add(
                        MimiMessage(
                            conversation_id=conversation_id,
                            run_id=run_id,
                            sequence=i + 1,
                            role="assistant",
                            content_bytes=len(text),
                            content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                            content_ciphertext=mimi_crypto.seal_content(
                                dek,
                                text,
                                aad=mimi_crypto.message_aad(conversation_id, i + 1, "assistant"),
                            ),
                        )
                    )
                    for j in range(10):
                        last_call_id = uuid7()
                        db.add(
                            MimiProviderCall(
                                id=last_call_id,
                                run_id=run_id,
                                attempt=j + 1,
                                state="succeeded",
                                request_fingerprint="synthetic-hash",
                                route={
                                    "kind": "openrouter",
                                    "mode": "native",
                                    "purpose": "compaction" if j == 0 else "main",
                                    "model": "synthetic",
                                    "actual_model": "synthetic",
                                    "actual_provider": "synthetic",
                                },
                                result={"response_id": f"synthetic-{i}-{j}"},
                                usage={
                                    "prompt_tokens": i * 10 + j + 1,
                                    "completion_tokens": 10,
                                    "reasoning_tokens": 4,
                                    "cached_tokens": 0,
                                    "cost": "0.1",
                                },
                            )
                        )
                unrelated_run = MimiRun(
                    id=uuid7(),
                    conversation_id=unrelated_id,
                    generation=1,
                    state="completed",
                    deadline=datetime.now(UTC),
                )
                db.add(unrelated_run)
                await db.flush()
                db.add(
                    MimiProviderCall(
                        run_id=unrelated_run.id,
                        attempt=1,
                        state="unknown",
                        request_fingerprint="unrelated",
                        route={"kind": "openrouter"},
                        usage={"cost": "99999"},
                        result={"response_id": "unrelated"},
                    )
                )
                db.add(
                    MimiEvent(
                        run_id=run_id,
                        sequence=1,
                        kind="tool.read_result",
                        payload={
                            "tool": "task.query.v1",
                            "body_ciphertext": mimi_crypto.seal_content(
                                dek,
                                '{"arguments":{"projection":["title"]},"result":{"count":0,"coverage":"complete"}}',
                                aad=mimi_crypto.event_content_aad(run_id, 1, "tool.read_result"),
                            ),
                        },
                    )
                )
                await db.commit()
            async with maker() as db:
                view = await service.conversation_view(db, auth, conversation_id)
                metrics = view["metrics"]
                assert len(view["runs"]) == 100 and len(view["messages"]) == 100
                assert len(view["provider_calls"]) == 801
                assert metrics["eligible_dispatches"] == 1010
                assert len(metrics["responses"]) == 101
                assert all(row["assistant_message_id"] for row in metrics["responses"])
                assert Decimal(metrics["usd"]["known"]) == Decimal("101.0")
                assert metrics["output"]["known"] == 10100
                assert metrics["reasoning"]["known"] == 4040
                assert metrics["last_measured_input"]["tokens"] == 1010
                assert sum(Decimal(r["usd"]["known"]) for r in metrics["responses"]) == Decimal(
                    "101"
                )
                assert view["events"][-1]["payload"]["activity"]["query"]["count"] == 0
                assert not db.new and not db.dirty
                with pytest.raises(HTTPException) as denied:
                    await service.conversation_view(db, other, conversation_id)
                assert denied.value.status_code == 404
                last = await db.get(MimiProviderCall, last_call_id)
                last.usage = {"prompt_tokens": 1010, "completion_tokens": 10}
                last.result = {
                    **last.result,
                    "generation": {
                        "id": "synthetic-100-9",
                        "native_tokens_prompt": 1010,
                        "native_tokens_completion": 10,
                        "total_cost": "0.2",
                    },
                }
                await db.commit()
            async with maker() as db:
                reloaded = (await service.conversation_view(db, auth, conversation_id))["metrics"]
                assert reloaded["eligible_dispatches"] == 1010
                assert Decimal(reloaded["usd"]["known"]) == Decimal("101.1")
                assert reloaded["reasoning"]["missing"] == 1
        finally:
            async with maker() as db:
                await db.execute(
                    delete(MimiConversation).where(
                        MimiConversation.id.in_([conversation_id, unrelated_id])
                    )
                )
                await db.commit()
            await engine.dispose()

    try:
        asyncio.run(scenario())
    finally:
        get_settings.cache_clear()
        crypto._cipher.cache_clear()
