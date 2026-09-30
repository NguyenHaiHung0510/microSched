"""PostgreSQL saver durability/encryption proof on the dedicated disposable DB."""

import asyncio
import base64
import os
import selectors
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import crypto as mimi_crypto
from app.agent.langgraph_runner import checkpoint_thread_id, run_langgraph
from app.agent.loop import LoopLimits
from app.agent.models import MimiConversation, MimiEvent, MimiRun
from app.agent.openrouter import ProviderDispatchError, RouteContractError
from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings

pytestmark = pytest.mark.pg
pytest.importorskip("langgraph", reason="install the optional prototype dependency group")
PLAINTEXT = "synthetic payload must remain encrypted"


@pytest.fixture
def app_database_url(monkeypatch):
    value = os.environ.get("MIMI_LANGGRAPH_APP_DATABASE_URL")
    if not value:
        pytest.skip("MIMI_LANGGRAPH_APP_DATABASE_URL is unset")
    url = make_url(value)
    if (
        url.host not in {"127.0.0.1", "localhost", "::1"}
        or url.port != 55466
        or url.database != "microsched_p1ca_066"
        or url.username != "microsched_app"
    ):
        pytest.fail("refusing LangGraph persistence proof outside the authorized local QA database")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "synthetic-langgraph-pg-test")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield value
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def test_postgres_checkpoint_survives_reopen_and_unknown_cannot_redispatch(app_database_url):
    async def scenario():
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        parsed = make_url(app_database_url)
        psycopg_url = parsed.render_as_string(hide_password=False)
        async_engine = create_async_engine(async_postgres_url(app_database_url))
        sessions = async_sessionmaker(async_engine, expire_on_commit=False)
        conversation_id, run_id, event_id = uuid7(), uuid7(), uuid7()
        wrapped_dek = mimi_crypto.create_wrapped_dek()
        dek = mimi_crypto.unwrap_dek(wrapped_dek)
        aad = mimi_crypto.event_content_aad(run_id, 1, "assistant.delta")
        ciphertext = mimi_crypto.seal_content(dek, PLAINTEXT, aad=aad)
        thread_id = checkpoint_thread_id(run_id, 1)
        model_calls = 0
        try:
            async with sessions() as db:
                db.add(
                    MimiConversation(
                        id=conversation_id,
                        owner_id=uuid7(),
                        sensitivity="standard",
                        dek_wrapped=wrapped_dek,
                    )
                )
                await db.flush()
                db.add(
                    MimiRun(
                        id=run_id,
                        conversation_id=conversation_id,
                        generation=1,
                        state="running",
                        execution_lease={},
                        source_versions={},
                        deadline=datetime.now(UTC) + timedelta(minutes=2),
                    )
                )
                await db.flush()
                db.add(
                    MimiEvent(
                        id=event_id,
                        run_id=run_id,
                        sequence=1,
                        kind="assistant.delta",
                        payload={"content_ciphertext": ciphertext, "content_bytes": len(PLAINTEXT)},
                    )
                )
                await db.commit()

            async def unknown_model(messages, turn):
                nonlocal model_calls
                model_calls += 1
                raise ProviderDispatchError("unknown", 503)

            async def invoke_once():
                return await run_langgraph(
                    [{"role": "user", "content": PLAINTEXT}],
                    limits=LoopLimits(
                        max_turns=3,
                        max_tool_calls=2,
                        max_serialized_bytes=10_000,
                        deadline=datetime.now(UTC) + timedelta(seconds=5),
                    ),
                    invoke_model=unknown_model,
                    execute_read=_unexpected_read,
                    run_id=run_id,
                    generation=1,
                    policy_sha256="a" * 64,
                    tool_registry_sha256="b" * 64,
                    output_schema_sha256="c" * 64,
                    database_url=app_database_url,
                )

            with pytest.raises(ProviderDispatchError):
                await invoke_once()
            assert model_calls == 1

            # A new saver connection models a process restart. It must observe
            # the persisted graph cursor, then refuse before any second call.
            async with AsyncPostgresSaver.from_conn_string(psycopg_url) as saver:
                first_checkpoint = await saver.aget_tuple(
                    {"configurable": {"thread_id": thread_id}}
                )
            assert first_checkpoint is not None, "initial graph cursor was not persisted"
            assert set(first_checkpoint.checkpoint["channel_values"]) - {
                "branch:to:model_step",
                "branch:to:read_step",
                "branch:to:finish",
            } == {
                "state_schema_version",
                "runner_version",
                "run_id",
                "generation",
                "policy_sha256",
                "tool_registry_sha256",
                "output_schema_sha256",
                "step",
                "turn",
                "tool_calls",
                "phase",
            }
            with pytest.raises(RouteContractError, match="resume_requires_reconcile"):
                await invoke_once()
            assert model_calls == 1
            config = {"configurable": {"thread_id": thread_id}}
            async with AsyncPostgresSaver.from_conn_string(psycopg_url) as saver:
                saved = await saver.aget_tuple(config)
            assert saved is not None
            values = saved.checkpoint["channel_values"]
            assert values["run_id"] == str(run_id)
            assert values["generation"] == 1
            assert "messages" not in values
            assert PLAINTEXT not in repr(saved.checkpoint)
            assert PLAINTEXT not in repr(saved.metadata)

            from psycopg import AsyncConnection

            async with await AsyncConnection.connect(psycopg_url) as connection:
                for table, column in (
                    ("checkpoints", "checkpoint::text || metadata::text"),
                    ("checkpoint_blobs", "encode(blob, 'escape')"),
                    ("checkpoint_writes", "encode(blob, 'escape')"),
                ):
                    rows = await connection.execute(
                        f"SELECT {column} FROM public.{table} WHERE thread_id = %s",
                        (thread_id,),
                    )
                    assert PLAINTEXT not in repr(await rows.fetchall())
                privileges = await connection.execute(
                    "SELECT "
                    "has_table_privilege(current_user, 'public.checkpoints', "
                    "'SELECT,INSERT,UPDATE,DELETE'), "
                    "has_table_privilege(current_user, 'public.checkpoint_blobs', "
                    "'SELECT,INSERT,UPDATE,DELETE'), "
                    "has_table_privilege(current_user, 'public.checkpoint_writes', "
                    "'SELECT,INSERT,UPDATE,DELETE'), "
                    "has_schema_privilege(current_user, 'public', 'CREATE')"
                )
                saver_dml, blobs_dml, writes_dml, public_create = await privileges.fetchone()
                assert saver_dml and blobs_dml and writes_dml
                assert public_create is False

            async with sessions() as db:
                event = await db.get(MimiEvent, event_id)
                assert event is not None
                stored = event.payload["content_ciphertext"]
                assert stored.startswith("mimi:v1:")
                assert PLAINTEXT not in stored
                assert mimi_crypto.open_content(dek, stored, aad=aad) == PLAINTEXT
        finally:
            # Delete only the three exact rows created by this test; saver keys
            # are separately cleaned by the exact thread id below.
            async with AsyncPostgresSaver.from_conn_string(psycopg_url) as saver:
                await saver.adelete_thread(thread_id)
            async with sessions() as db:
                for row in (
                    await db.execute(select(MimiEvent).where(MimiEvent.id == event_id))
                ).scalars():
                    await db.delete(row)
                run = await db.get(MimiRun, run_id)
                if run is not None:
                    await db.delete(run)
                conversation = await db.get(MimiConversation, conversation_id)
                if conversation is not None:
                    await db.delete(conversation)
                await db.commit()
            await async_engine.dispose()

    asyncio.run(
        scenario(),
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
    )


async def _unexpected_read(name, arguments):
    pytest.fail("unknown provider outcome must prevent tool execution")
