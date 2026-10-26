"""Actual six HTTP handlers: wire ACK must follow commit, including ambiguous loss.

The staged store double isolates the transaction/HTTP boundary. Actual domain
idempotency and PostgreSQL integration are separate companion receipts.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4, uuid7

import httpx
import pytest
from fastapi import FastAPI

from app.domain.models import AuthSession
from app.web import mimi_csrf
from app.web.deps import get_session, require_session
from app.web.routers import mimi, notes, reminder_history

CASES = ("timing", "feedback", "note_top", "history_handle", "history_prepare", "history_commit")


class StagedStore:
    def __init__(self, failure):
        self.failure = failure
        self.pending = None
        self.durable = None
        self.effects = 0
        self.rollbacks = 0
        self.commits = 0

    def stage(self, result):
        if self.durable is None:
            self.pending = result
        return self.durable if self.durable is not None else result

    async def commit(self):
        self.commits += 1
        failure, self.failure = self.failure, None
        if failure == "before":
            raise OSError("synthetic-private-driver-detail")
        if self.pending is not None:
            self.durable, self.pending = self.pending, None
            self.effects += 1
        if failure == "after":
            raise OSError("synthetic-private-driver-detail")

    async def rollback(self):
        self.rollbacks += 1
        self.pending = None


def wire_app(monkeypatch, case, failure):
    db, app, wire = StagedStore(failure), FastAPI(), []
    identifier, target, client = uuid7(), uuid4(), "synthetic-ack-key"
    monkeypatch.setattr(mimi, "get_settings", lambda: SimpleNamespace(is_production=False))
    monkeypatch.setattr(mimi_csrf, "get_settings", lambda: SimpleNamespace(mimi_public_origin=None))

    async def actor():
        return AuthSession(
            token_hash="synthetic-ack",
            user_email="owner@example.test",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )

    async def session():
        yield db
        # Reproduce the actual request-scoped yield cleanup ordering, without
        # replacing the handlers or masking a success already emitted on wire.
        if db.pending is not None:
            await db.commit()

    app.dependency_overrides[require_session] = actor
    app.dependency_overrides[get_session] = session
    item = {
        "id": str(target),
        "content": "Synthetic item",
        "position": 0,
        "is_completed": False,
        "created_at": None,
        "updated_at": None,
    }
    if case == "timing":
        method, path = "POST", f"/api/mimi/conversations/{identifier}/response-timings"
        payload = {
            "version": 1,
            "client_id": client,
            "run_id": str(identifier),
            "target_id": str(target),
            "phase": "send",
            "source_id": client,
            "observation": "visible_paint",
            "elapsed_ms": 2000,
        }
        module, name, result = mimi, "save_response_timing", payload
    elif case == "feedback":
        method, path = "POST", f"/api/mimi/conversations/{identifier}/feedback"
        payload = {
            "client_id": client,
            "target_type": "turn",
            "target_id": str(target),
            "comment": "Synthetic feedback",
            "expected": "Keep original expected",
        }
        module, name = mimi, "save_feedback"
        result = {"id": str(identifier), **payload, "state": "new"}
    elif case == "note_top":
        method, path = "POST", f"/api/notes/{identifier}/items/{target}/move-to-top"
        payload = {"expected_items": [{"id": str(target), "position": 0, "is_completed": False}]}
        module, name, result = notes.store, "move_item_to_top", [item]
    elif case == "history_handle":
        method, path = "PUT", f"/api/reminder-history/one_shot/{target}/handled"
        payload = {"handled": True}
        module, name, result = reminder_history, "mark_handled", {"handled": True}
    elif case == "history_prepare":
        method, path = "POST", "/api/reminder-history/handled-batches/prepare"
        payload = {"batch_id": str(identifier), "filter": {}}
        module, name, result = reminder_history, "prepare_batch", {"batch_id": str(identifier)}
    else:
        method, path = "POST", f"/api/reminder-history/handled-batches/{identifier}/commit"
        payload = {}
        module, name, result = (
            reminder_history,
            "commit_batch",
            {"batch_id": str(identifier), "committed": True},
        )

    async def stage(*args, **kwargs):
        return db.stage(result)

    monkeypatch.setattr(module, name, stage)
    for router in (mimi.router, notes.router, reminder_history.router):
        app.include_router(router, prefix="/api")

    async def observe(scope, receive, send):
        async def boundary(message):
            if message["type"] == "http.response.start":
                wire.append({"status": message["status"], "durable": db.durable is not None})
            await send(message)

        await app(scope, receive, boundary)

    return observe, db, wire, method, path, payload


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("failure", ["before", "after"])
def test_commit_failure_never_emits_success_and_replay_keeps_one_effect(
    monkeypatch, caplog, case, failure
):
    app, db, wire, method, path, body = wire_app(monkeypatch, case, failure)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            headers = {"Origin": "http://test", "Sec-Fetch-Site": "same-origin", "X-Mimi-CSRF": "1"}
            first = await client.request(method, path, json=body, headers=headers)
            assert first.status_code == 503, (case, first.status_code, first.text)
            assert first.json()["detail"].endswith("_commit_unknown")
            assert "synthetic-private-driver-detail" not in first.text
            assert wire[0]["status"] == 503 and db.rollbacks == 1
            second = await client.request(method, path, json=body, headers=headers)
            assert second.status_code in {200, 201}
            third = await client.request(method, path, json=body, headers=headers)
            assert third.json() == second.json() and db.effects == 1
            assert all(row["durable"] for row in wire if row["status"] < 300)

    asyncio.run(scenario())
    assert "synthetic-private-driver-detail" not in caplog.text


@pytest.mark.parametrize("case", CASES)
def test_normal_and_replay_are_committed_before_wire_ack(monkeypatch, case):
    app, db, wire, method, path, body = wire_app(monkeypatch, case, None)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"Origin": "http://test", "Sec-Fetch-Site": "same-origin", "X-Mimi-CSRF": "1"}
            first = await client.request(method, path, json=body, headers=headers)
            second = await client.request(method, path, json=body, headers=headers)
            assert first.status_code in {200, 201} and second.json() == first.json()
            assert len(wire) == 2 and all(row["durable"] for row in wire)
            assert db.effects == 1

    asyncio.run(scenario())
