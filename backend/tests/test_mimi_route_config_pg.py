"""Configuration CAS and active-run independence in disposable PostgreSQL."""

import asyncio
import base64
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import service
from app.agent.models import MimiConversation, MimiProviderCall, MimiRun
from app.agent.route_config import ConfigurationChange
from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession

pytestmark = pytest.mark.pg


def test_configuration_cas_changes_next_run_without_rewriting_active_receipt(pg_dsn, monkeypatch):
    monkeypatch.setenv("MIMI_P0_DISABLE_DOTENV", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "synthetic-configuration")
    monkeypatch.setenv("MIMI_REAL_CHAT_ENABLED", "true")
    monkeypatch.setenv("MIMI_LIVE_PROVIDER_ENABLED", "true")
    monkeypatch.setenv("MIMI_STANDARD_API_KEY", "synthetic-never-sent")
    monkeypatch.setenv("MIMI_ROUTE_MODEL", "deepseek/deepseek-v4.1-flash")
    monkeypatch.setenv("MIMI_ROUTE_PROVIDER", "deepinfra")
    monkeypatch.setenv("MIMI_ROUTE_QUANTIZATION", "fp8")
    monkeypatch.setenv("MIMI_ROUTE_MAX_INPUT_PRICE", "0.2")
    monkeypatch.setenv("MIMI_ROUTE_MAX_OUTPUT_PRICE", "0.6")
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    get_settings.cache_clear()
    crypto._cipher.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(UTC)
        auth = AuthSession(
            token_hash=str(uuid7()),
            user_email="owner@example.test",
            last_seen_at=now,
            expires_at=now + timedelta(days=1),
        )
        cid = None
        try:
            async with maker() as db:
                created = await service.create_conversation(db, auth, service.ConversationCreate())
                cid = UUID(str(created["id"]))
                before = await service.conversation_configuration(db, auth, cid)
                run = MimiRun(
                    id=uuid7(),
                    conversation_id=cid,
                    generation=1,
                    state="running",
                    execution_lease={"config_version": before["version"]},
                    source_versions={},
                    deadline=now + timedelta(minutes=5),
                )
                db.add(run)
                await db.flush()
                call = MimiProviderCall(
                    run_id=run.id,
                    attempt=1,
                    state="intent",
                    request_fingerprint="a" * 64,
                    route={
                        "model": "deepseek/deepseek-v4.1-flash",
                        "configuration_version": before["version"],
                    },
                )
                db.add(call)
                await db.commit()
                saved = await service.conversation_configuration(
                    db,
                    auth,
                    cid,
                    ConfigurationChange(
                        expected_version=before["version"],
                        profile_id="luna",
                        effort="medium",
                        input_tokens=32000,
                    ),
                )
                await db.commit()
                assert saved["version"] == before["version"] + 1
                assert saved["active_run_id"] == str(run.id)
                assert saved["applies_to"] == "next_run"
                assert saved["config"]["profile_id"] == "luna"
                await db.refresh(call)
                assert call.route["model"] == "deepseek/deepseek-v4.1-flash"
                assert call.route["configuration_version"] == before["version"]
                with pytest.raises(HTTPException) as stale:
                    await service.conversation_configuration(
                        db,
                        auth,
                        cid,
                        ConfigurationChange(
                            expected_version=before["version"],
                            profile_id="glm",
                            effort="high",
                            input_tokens=100000,
                        ),
                    )
                assert stale.value.status_code == 409
                await db.rollback()
                still = await service.conversation_configuration(db, auth, cid)
                assert still["config"] == saved["config"]
                assert still["version"] == saved["version"]
        finally:
            async with maker() as db:
                if cid and (row := await db.get(MimiConversation, cid)):
                    await db.delete(row)
                    await db.commit()
            await engine.dispose()

    try:
        asyncio.run(scenario())
    finally:
        get_settings.cache_clear()
        crypto._cipher.cache_clear()
