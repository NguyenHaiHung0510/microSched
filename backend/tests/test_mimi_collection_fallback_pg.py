"""Finite throwaway-PG fallback and retained recovery loss classes, never live/QA reset."""

import asyncio
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_migration_pg import migrate
from test_mimi_collection_service_pg import auth, local_contract  # noqa: F401
from test_mimi_collection_service_pg import (
    prepare as prepare_collection,
)
from test_mimi_notifications_pg import device

from app.agent import notifications, service
from app.agent.models import MimiConversation, MimiEvent
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.tasks import TaskStore
from scripts.prepare_ci_database import prepare

pytestmark = pytest.mark.pg


@pytest.fixture
def isolated_0017(pg_dsn):
    parsed = make_url(pg_dsn)
    assert parsed.host in {"127.0.0.1", "localhost", "::1"}
    name = "mimi086_a3_migration_" + uuid4().hex[:12]
    admin = parsed.set(database="postgres").render_as_string(hide_password=False)
    bootstrap = parsed.set(database=name).render_as_string(hide_password=False)
    migrator = parsed.set(
        database=name, username="microsched_migrator", password="synthetic-migrator"
    ).render_as_string(hide_password=False)

    async def create():
        c = await asyncpg.connect(admin)
        try:
            await c.execute(f'CREATE DATABASE "{name}"')
        finally:
            await c.close()
        await prepare(
            bootstrap_url=bootstrap,
            migrator_password="synthetic-migrator",
            app_password="synthetic-app",
        )

    asyncio.run(create())
    try:
        migrate(migrator, "upgrade", "0017")
        yield migrator
    finally:

        async def drop():
            c = await asyncpg.connect(admin)
            try:
                # Exact self-created disposable database, not caller's populated store.
                assert name.startswith("mimi086_a3_migration_") and name.replace("_", "").isalnum()
                await c.execute(f'DROP DATABASE "{name}"')
            finally:
                await c.close()

        asyncio.run(drop())


def test_feature_off_0017_existing_task_and_mimi_readers_before_activation(
    isolated_0017, monkeypatch
):
    monkeypatch.setenv("MIMI_COLLECTION_ENABLED", "0")
    monkeypatch.setenv("MIMI_NOTIFICATIONS_ENABLED", "0")
    monkeypatch.setenv("MIMI_LIVE_PROVIDER_ENABLED", "0")
    get_settings.cache_clear()

    async def scenario():
        url = isolated_0017
        c = await asyncpg.connect(url)
        try:
            tid = await c.fetchval(
                "INSERT INTO microsched.task(title,body_md) "
                "VALUES ('Legacy visible Task','Legacy full body') RETURNING id"
            )
            child = await c.fetchval(
                "INSERT INTO microsched.task_item(task_id,content,position) "
                "VALUES ($1,'Legacy checklist',0) RETURNING id",
                tid,
            )
            # Actual legacy projection succeeds before activation, no new columns needed.
            assert dict(
                await c.fetchrow("SELECT title,body_md FROM microsched.task WHERE id=$1", tid)
            ) == {"title": "Legacy visible Task", "body_md": "Legacy full body"}
            assert (
                await c.fetchval("SELECT content FROM microsched.task_item WHERE id=$1", child)
                == "Legacy checklist"
            )
        finally:
            await c.close()
        e = create_async_engine(async_postgres_url(url))
        maker = async_sessionmaker(e, expire_on_commit=False)
        actor = auth()
        try:
            async with maker() as db:
                view = await TaskStore().get(db, actor, tid)
                assert view.title == "Legacy visible Task" and view.body_md == "Legacy full body"
                assert [item.content for item in view.items] == ["Legacy checklist"]
                convo = await service.create_conversation(db, actor, service.ConversationCreate())
                await db.commit()
                snapshot = await service.conversation_view(db, actor, convo["id"])
                assert snapshot["sensitivity"] == "standard" and snapshot["change_sets"] == []
                assert not get_settings().mimi_collection_enabled
                assert not get_settings().mimi_notifications_enabled
                assert not get_settings().mimi_live_provider_enabled
        finally:
            await e.dispose()

    asyncio.run(scenario())


def execute_revision_downgrade(url, bypass=False):
    """Execute actual revision with real SQL inside a test-owned transaction.

    The negative variant changes only the guard read result in this test context.
    It is never an application/environment bypass in the production revision.
    """
    spec = importlib.util.spec_from_file_location(
        "mimi086_guard_test",
        Path(__file__).parents[1] / "alembic/versions/0017_mimi_task_collection.py",
    )
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        with engine.begin() as conn:
            ops = Operations(MigrationContext.configure(conn))

            class GuardBypass:
                def get_bind(self):
                    class FakeBind:
                        def execute(self, _statement):
                            class Empty:
                                def scalar(self):
                                    return False

                            return Empty()

                    return FakeBind()

                def execute(self, statement):
                    return ops.execute(statement)

            revision.op = GuardBypass() if bypass else ops
            with pytest.raises(RuntimeError, match="refusing to drop Task/Mimi recovery"):
                revision.downgrade()
    finally:
        engine.dispose()


@pytest.mark.parametrize("kind", ["receipt", "evidence", "notification_tree"])
def test_0017_downgrade_retains_encrypted_recovery_and_pending_notification_data(
    isolated_0017, monkeypatch, kind
):
    # Avoid another notification masking the receipt/evidence guard loss class.
    monkeypatch.setenv("MIMI_NOTIFICATIONS_ENABLED", "0")
    get_settings.cache_clear()

    async def seed_and_fingerprint():
        e = create_async_engine(async_postgres_url(isolated_0017))
        maker = async_sessionmaker(e, expire_on_commit=False)
        try:
            actor, cid, rid, ids, ch, decision = await prepare_collection(maker)
            async with maker() as db:
                if kind == "receipt":
                    await service.confirm_change_set(
                        db, actor, ch, decision, "guard-recovery-" + str(uuid4())
                    )
                elif kind == "evidence":
                    await service.save_feedback(
                        db,
                        actor,
                        cid,
                        service.FeedbackCreate(
                            client_id=str(uuid4()),
                            target_type="run",
                            target_id=str(rid),
                            comment="Synthetic durable evidence",
                            evidence_bundle_ids=[],
                        ),
                    )
                else:
                    monkeypatch.setenv("MIMI_NOTIFICATIONS_ENABLED", "1")
                    get_settings.cache_clear()
                    owner = (await db.get(MimiConversation, cid)).owner_id
                    await device(maker, owner)
                    event = (
                        await db.scalars(
                            select(MimiEvent).where(
                                MimiEvent.run_id == rid, MimiEvent.kind == "change_set.ready"
                            )
                        )
                    ).one()
                    await notifications.queue_completion(db, rid, event.sequence, event.kind)
                await db.commit()
        finally:
            await e.dispose()
        return await fingerprint()

    async def fingerprint():
        c = await asyncpg.connect(isolated_0017)
        try:
            data = {
                "revision": await c.fetchval("SELECT version_num FROM microsched.alembic_version")
            }
            for table, column in [
                ("mimi_execution_receipt", "result_ciphertext"),
                ("mimi_evidence", "content_ciphertext"),
            ]:
                data[table] = [
                    dict(r)
                    for r in await c.fetch(
                        f"SELECT id,{column} FROM microsched.{table} ORDER BY id"
                    )
                ]
            for table in (
                "mimi_device_preference",
                "mimi_notification_intent",
                "mimi_notification_delivery",
            ):
                data[table] = [
                    dict(r) for r in await c.fetch(f"SELECT * FROM microsched.{table} ORDER BY id")
                ]
            return data
        finally:
            await c.close()

    before = asyncio.run(seed_and_fingerprint())
    if kind == "receipt":
        assert len(before["mimi_execution_receipt"]) == 1
        assert before["mimi_execution_receipt"][0]["result_ciphertext"].startswith("mimi:v1:")
        assert not before["mimi_evidence"] and not before["mimi_device_preference"]
    elif kind == "evidence":
        assert len(before["mimi_evidence"]) == 1
        assert before["mimi_evidence"][0]["content_ciphertext"].startswith("mimi:v1:")
        assert not before["mimi_execution_receipt"] and not before["mimi_device_preference"]
    else:
        assert all(
            len(before[t]) == 1
            for t in (
                "mimi_device_preference",
                "mimi_notification_intent",
                "mimi_notification_delivery",
            )
        )
        assert not before["mimi_execution_receipt"] and not before["mimi_evidence"]
    execute_revision_downgrade(
        isolated_0017, bypass=os.environ.get("MIMI086_NEGATIVE_BYPASS_DOWNGRADE_GUARD") == "1"
    )
    output = migrate(isolated_0017, "downgrade", "0016", expected=1)
    assert "refusing to drop Task/Mimi recovery" in output
    assert asyncio.run(fingerprint()) == before
