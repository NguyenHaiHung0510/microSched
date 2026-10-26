"""Actual PG + route + wire: commit loss never ACKs or duplicates Mimi writes."""

import asyncio
import hashlib
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from test_mimi_collection_service_pg import local_contract  # noqa: F401
from test_mimi_message_provenance_pg import append, fixture_scenario

from app.agent import crypto
from app.agent.models import MimiConversation, MimiEvent, MimiFeedback, MimiMessage, MimiRun
from app.agent.response_timing import KIND
from app.web.deps import get_session, require_session
from app.web.routers.mimi import router

pytestmark = pytest.mark.pg


@pytest.mark.parametrize("kind", ["timing", "feedback"])
@pytest.mark.parametrize("failure", ["before", "after"])
def test_actual_commit_failure_before_wire_and_original_replay(pg_dsn, kind, failure):
    async def action(maker, actor, cid, rid):
        async with maker() as db:
            conv = await db.get(MimiConversation, cid)
            text = "Owned ACK fixture"
            db.add(
                MimiMessage(
                    conversation_id=cid,
                    run_id=rid,
                    client_id="source-ack-pg",
                    sequence=1,
                    role="user",
                    content_bytes=len(text.encode()),
                    content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    content_ciphertext=crypto.seal_content(
                        crypto.unwrap_dek(conv.dek_wrapped),
                        text,
                        aad=crypto.message_aad(cid, 1, "user"),
                    ),
                )
            )
            conv.next_message_sequence = 2
            target = await append(db, cid, rid, "local_deterministic_result")
            run = await db.get(MimiRun, rid)
            run.state, run.completed_at = "completed", datetime.now(UTC)
            await db.commit()
            mid = str(target.id)
        app, wire, fault = FastAPI(), [], [failure]

        async def actor_dependency():
            return actor

        async def session_dependency():
            async with maker() as db:
                real_commit = db.commit

                async def commit():
                    mode = fault.pop() if fault else None
                    if mode == "after":
                        await real_commit()
                    if mode:
                        raise OSError("synthetic-private-driver-detail")
                    await real_commit()

                db.commit = commit
                try:
                    yield db
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise

        app.dependency_overrides[require_session] = actor_dependency
        app.dependency_overrides[get_session] = session_dependency
        app.include_router(router, prefix="/api")

        async def count():
            async with maker() as db:
                statement = (
                    select(func.count())
                    .select_from(MimiEvent)
                    .where(MimiEvent.run_id == rid, MimiEvent.kind == KIND)
                    if kind == "timing"
                    else select(func.count())
                    .select_from(MimiFeedback)
                    .where(MimiFeedback.conversation_id == cid)
                )
                return await db.scalar(statement)

        async def observed_app(scope, receive, send):
            async def boundary(message):
                if message["type"] == "http.response.start":
                    wire.append({"status": message["status"], "durable_rows": await count()})
                await send(message)

            await app(scope, receive, boundary)

        if kind == "timing":
            suffix = "response-timings"
            body = {
                "version": 1,
                "client_id": "timing-ack-pg",
                "run_id": str(rid),
                "target_id": mid,
                "source_id": "source-ack-pg",
                "phase": "send",
                "observation": "visible_paint",
                "elapsed_ms": 2000,
            }
        else:
            suffix = "feedback"
            body = {
                "client_id": "feedback-ack-pg",
                "target_type": "turn",
                "target_id": mid,
                "comment": "🌸" * 8000,
                "expected": "ệ" * 8000,
            }
        path = f"/api/mimi/conversations/{cid}/{suffix}"
        headers = {"Origin": "http://test", "Sec-Fetch-Site": "same-origin", "X-Mimi-CSRF": "1"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=observed_app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            first = await client.post(path, json=body, headers=headers)
            assert first.status_code == 503 and first.json()["detail"].endswith("_commit_unknown")
            assert "synthetic-private-driver-detail" not in first.text
            assert wire[0] == {"status": 503, "durable_rows": int(failure == "after")}
            saved = await client.post(path, json=body, headers=headers)
            replay = await client.post(path, json=body, headers=headers)
            assert saved.status_code == replay.status_code == 201
            assert saved.json() == replay.json() and await count() == 1
            assert all(w["durable_rows"] == 1 for w in wire if w["status"] < 300)

    asyncio.run(fixture_scenario(pg_dsn, action))
