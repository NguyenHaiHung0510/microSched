import asyncio
import os
import selectors
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import httpx
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.agent.workflow_pilot import TaskFrameStore
from app.agent.workflow_probe.store import checkpoint_thread
from app.core import crypto
from app.core.settings import get_settings
from app.domain.models import AuthSession
from app.main import create_app
from app.web.deps import require_session

CSRF = {"Origin": "http://test", "Sec-Fetch-Site": "same-origin", "X-Mimi-CSRF": "1"}


@pytest.mark.pg
def test_real_http_auth_csrf_disabled_owner_and_exact_confirm(monkeypatch):
    value = os.environ.get("MIMI_PILOT_APP_URL")
    if not value:
        pytest.skip("exclusive synthetic pilot database required")
    monkeypatch.setenv("MIMI_P0_DISABLE_DOTENV", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", value)
    monkeypatch.setenv("MIMI_WORKFLOW_PILOT_ENABLED", "true")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "synthetic-073-http-only")
    get_settings.cache_clear()
    monkeypatch.setattr(crypto, "_cipher", lambda: AESGCM(b"s" * 32))

    async def scenario():
        app = create_app()
        store = TaskFrameStore(value)
        connection = await asyncpg.connect(store._dsn)
        task_id, run_id = uuid4(), uuid4()
        auth = AuthSession(
            token_hash="synthetic-only",
            user_email="owner@test.local",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )

        async def session():
            return auth

        try:
            await connection.execute(
                "INSERT INTO microsched.task(id,title) VALUES($1,$2)",
                task_id,
                "QA_073 synthetic HTTP task",
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                assert (await client.get("/api/mimi/workflow-pilot/tasks")).status_code == 401
                app.dependency_overrides[require_session] = session
                assert (await client.get("/api/mimi/capabilities")).json()["workflow_pilot_enabled"]
                payload = {"run_id": str(run_id), "task_ids": [str(task_id)], "engine": "graph"}
                for headers in (
                    {},
                    CSRF | {"Origin": "http://foreign.example"},
                    CSRF | {"Sec-Fetch-Site": "cross-site"},
                ):
                    response = await client.post(
                        "/api/mimi/workflow-pilot/runs", json=payload, headers=headers
                    )
                    assert response.status_code == 403
                assert (
                    await connection.fetchval(
                        "SELECT count(*) FROM mimi_probe_068.run WHERE id=$1", run_id
                    )
                    == 0
                )
                response = await client.post(
                    "/api/mimi/workflow-pilot/runs", json=payload, headers=CSRF
                )
                assert response.status_code == 200, response.text
                state = response.json()
                assert state["phase"] == "direction"
                path = f"/api/mimi/workflow-pilot/runs/{run_id}"
                state = (
                    await client.post(
                        path + "/advance",
                        headers=CSRF,
                        json={"generation": 1, "direction": "apply_prefix"},
                    )
                ).json()
                assert state["phase"] == "confirmation"
                auth.user_email = "foreign@test.local"
                assert (await client.get(path)).status_code == 409
                assert (await client.get("/api/mimi/workflow-pilot/runs")).json()["items"] == []
                auth.user_email = "owner@test.local"
                assert (
                    await client.post(
                        path + "/advance",
                        headers=CSRF,
                        json={"generation": 1, "preview_digest": "0" * 64},
                    )
                ).status_code == 409
                state = (
                    await client.post(
                        path + "/advance",
                        headers=CSRF,
                        json={"generation": 1, "preview_digest": state["preview_digest"]},
                    )
                ).json()
                assert state["phase"] == "succeeded"
                assert (await client.get(path)).json()["receipt"]["changed"] == 1
                monkeypatch.setenv("MIMI_WORKFLOW_PILOT_ENABLED", "false")
                get_settings.cache_clear()
                assert (await client.get(path)).status_code == 404
                assert not (await client.get("/api/mimi/capabilities")).json()[
                    "workflow_pilot_enabled"
                ]
        finally:
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                await connection.execute(
                    f"DELETE FROM public.{table} WHERE thread_id=$1", checkpoint_thread(run_id, 1)
                )
            await connection.execute("DELETE FROM mimi_probe_068.run WHERE id=$1", run_id)
            await connection.execute("DELETE FROM microsched.task WHERE id=$1", task_id)
            await connection.close()
            get_settings.cache_clear()

    asyncio.run(
        scenario(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
    )
