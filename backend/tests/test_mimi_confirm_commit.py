"""HTTP must report success only after the Task/receipt transaction commits."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.models import AuthSession
from app.main import create_app
from app.web import deps
from app.web.routers import mimi


@pytest.mark.parametrize("commit_failure", [False, True])
def test_confirmation_http_stays_behind_commit(monkeypatch, caplog, commit_failure):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "synthetic-commit-order")
    monkeypatch.setenv("MIMI_PUBLIC_ORIGIN", "http://test")
    from app.core.settings import get_settings

    get_settings.cache_clear()

    class Transaction:
        committed = False
        rolled_back = False
        info = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def commit(self):
            await asyncio.sleep(0)
            if commit_failure:
                raise RuntimeError("synthetic storage unavailable")
            self.committed = True

        async def rollback(self):
            self.rolled_back = True

    async def scenario():
        tx = Transaction()
        monkeypatch.setattr(deps, "get_sessionmaker", lambda: lambda: tx)
        receipt = {"id": str(uuid4()), "task_id": str(uuid4())}

        async def confirm(*args, **kwargs):
            return receipt

        monkeypatch.setattr(mimi, "confirm_change_set", confirm)
        app = create_app()
        auth = AuthSession(
            user_email="owner@example.test",
            token_hash="synthetic-nonlogin",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        app.dependency_overrides[deps.require_session] = lambda: auth
        import json

        body = json.dumps(
            {"digest": "a" * 64, "nonce": str(uuid4()), "decision": "confirm"}
        ).encode()
        path = "/api/mimi/change-sets/" + str(uuid4()) + "/decision"
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"test"),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"origin", b"http://test"),
                (b"sec-fetch-site", b"same-origin"),
                (b"x-mimi-csrf", b"1"),
                (b"idempotency-key", b"synthetic-commit-order"),
            ],
            "server": ("test", 80),
            "client": ("127.0.0.1", 40000),
        }
        sent = []
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.Future()

        async def send(message):
            sent.append((message, tx.committed))

        try:
            await app(scope, receive, send)
        except RuntimeError:
            if not commit_failure:
                raise
        start = [item for item in sent if item[0]["type"] == "http.response.start"]
        assert len(start) == 1
        if commit_failure:
            assert start[0][0]["status"] == 503, "failed commit must not leak success headers"
            assert tx.rolled_back and not tx.committed
            response = b"".join(m.get("body", b"") for m, _ in sent).decode()
            assert "mimi_confirmation_commit_failed" in response
            assert receipt["task_id"] not in response
            assert "mimi_confirmation_commit_failed" in caplog.text
            assert "synthetic storage unavailable" not in response
        else:
            assert start[0][0]["status"] == 200 and start[0][1], (
                "success escaped before durable commit"
            )
            assert tx.committed and not tx.rolled_back

    try:
        asyncio.run(scenario())
    finally:
        get_settings.cache_clear()
