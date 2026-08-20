"""Disposable-Postgres rehearsal for Task 012.

The fixture is deliberately opt-in through the existing ``pg`` lane.  CI's
Postgres service is throwaway; the source identity override is only for that
service database name and the production default remains ``microschedule_v2``.
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database_urls import async_postgres_url
from scripts.cutover_v2 import (
    assert_app_cannot_read_alembic,
    assert_source_read_only,
    attest_schema,
    build_manifest,
    collect_target_inventory_as_app,
    load_source_snapshot,
    run_commit,
    run_verify,
    transform_source,
)

pytestmark = pytest.mark.pg

NOW = datetime(2026, 8, 20, 12, 34, 56, tzinfo=UTC)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def rehearsal(pg_dsn: str):
    admin_url = os.environ["NEON_MIGRATOR_URL"]
    parsed = make_url(admin_url)
    db = parsed.database
    app_url = parsed.set(username="microsched_app", password="synthetic-app").render_as_string(
        hide_password=False
    )
    migrator_url = parsed.set(
        username="microsched_migrator", password="synthetic-migrator"
    ).render_as_string(hide_password=False)

    async def prepare() -> None:
        conn = await asyncpg.connect(pg_dsn)
        try:
            await conn.execute(
                "DROP TABLE IF EXISTS public.calendar_events, public.calendar_sources, "
                "public.note_items, public.notes, public.task_items, public.tasks, "
                "public.priorities CASCADE"
            )
            await conn.execute(
                "CREATE TABLE public.priorities (id uuid PRIMARY KEY, name text NOT NULL)"
            )
            await conn.execute(
                "CREATE TABLE public.tasks (id uuid PRIMARY KEY, title text NOT NULL, note text, "
                "status text NOT NULL, priority_id uuid, due_at timestamptz, "
                "completed_at timestamptz, created_at timestamptz NOT NULL, "
                "updated_at timestamptz NOT NULL)"
            )
            await conn.execute(
                "CREATE TABLE public.task_items (id uuid PRIMARY KEY, task_id uuid NOT NULL "
                "REFERENCES public.tasks(id), content text NOT NULL, "
                "is_completed boolean NOT NULL, "
                "position integer NOT NULL, created_at timestamptz NOT NULL, "
                "updated_at timestamptz NOT NULL)"
            )
            await conn.execute(
                "CREATE TABLE public.notes (id uuid PRIMARY KEY, title text, body text, "
                "pinned boolean NOT NULL, priority_id uuid, archived_at timestamptz, "
                "created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL)"
            )
            await conn.execute(
                "CREATE TABLE public.note_items (id uuid PRIMARY KEY, note_id uuid NOT NULL "
                "REFERENCES public.notes(id), content text NOT NULL, is_done boolean NOT NULL, "
                "position integer NOT NULL, created_at timestamptz NOT NULL, "
                "updated_at timestamptz NOT NULL)"
            )
            await conn.execute(
                "CREATE TABLE public.calendar_sources (id uuid PRIMARY KEY, display_name text)"
            )
            await conn.execute(
                "CREATE TABLE public.calendar_events (id uuid PRIMARY KEY, source_id uuid "
                "REFERENCES public.calendar_sources(id), title text NOT NULL, location text, "
                "starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL, description text, "
                "user_cancelled boolean, status text, external_uid text, "
                "created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL)"
            )
            priority_id, task_id, note_id = uuid4(), uuid4(), uuid4()
            source_id = uuid4()
            await conn.execute(
                "INSERT INTO public.priorities VALUES ($1,$2)", priority_id, "Quan trọng hơn TN"
            )
            await conn.execute(
                "INSERT INTO public.tasks VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                task_id,
                "synthetic task",
                "synthetic body",
                "completed",
                priority_id,
                NOW,
                NOW,
                NOW,
                NOW,
            )
            await conn.execute(
                "INSERT INTO public.task_items VALUES ($1,$2,$3,$4,$5,$6,$7)",
                uuid4(),
                task_id,
                "synthetic item",
                True,
                0,
                NOW,
                NOW,
            )
            await conn.execute(
                "INSERT INTO public.notes VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                note_id,
                "synthetic note",
                "synthetic body",
                True,
                None,
                None,
                NOW,
                NOW,
            )
            await conn.execute(
                "INSERT INTO public.note_items VALUES ($1,$2,$3,$4,$5,$6,$7)",
                uuid4(),
                note_id,
                "synthetic note item",
                True,
                0,
                NOW,
                NOW,
            )
            await conn.execute(
                "INSERT INTO public.calendar_sources VALUES ($1,$2)",
                source_id,
                "v1_sqlite_schedule",
            )
            await conn.execute(
                "INSERT INTO public.calendar_events VALUES "
                "($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)",
                uuid4(),
                source_id,
                "synthetic manual",
                None,
                NOW,
                NOW + timedelta(hours=1),
                None,
                False,
                "scheduled",
                "manual_synthetic",
                NOW,
                NOW,
            )
            await conn.execute(
                "INSERT INTO public.calendar_events VALUES "
                "($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)",
                uuid4(),
                source_id,
                "synthetic imported",
                None,
                NOW,
                NOW + timedelta(hours=1),
                None,
                False,
                "scheduled",
                "v1-schedule-synthetic",
                NOW,
                NOW,
            )
            await conn.execute(
                "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles "
                "WHERE rolname='microsched_migrator') THEN "
                "CREATE ROLE microsched_migrator LOGIN PASSWORD 'synthetic-migrator'; "
                "END IF; END $$"
            )
            await conn.execute("ALTER ROLE microsched_app LOGIN PASSWORD 'synthetic-app'")
            await conn.execute(
                "GRANT USAGE ON SCHEMA microsched TO microsched_app, microsched_migrator"
            )
            await conn.execute(
                "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA "
                "microsched TO microsched_app"
            )
            await conn.execute(
                "GRANT SELECT ON ALL TABLES IN SCHEMA microsched TO microsched_migrator"
            )
            await conn.execute("REVOKE ALL ON microsched.alembic_version FROM microsched_app")
            await conn.execute(
                "GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA microsched TO microsched_app"
            )
        finally:
            await conn.close()

    _run(prepare())
    old_env = {
        key: os.environ.get(key)
        for key in (
            "CUTOVER_SOURCE_URL",
            "CUTOVER_TARGET_URL",
            "CUTOVER_MIGRATOR_URL",
            "CUTOVER_SOURCE_DATABASE",
        )
    }
    os.environ["CUTOVER_SOURCE_URL"] = admin_url
    os.environ["CUTOVER_TARGET_URL"] = app_url
    os.environ["CUTOVER_MIGRATOR_URL"] = migrator_url
    os.environ["CUTOVER_SOURCE_DATABASE"] = db or "microsched_ci"
    yield app_url, migrator_url
    for key, value in old_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_source_write_guard_is_real(rehearsal) -> None:
    async def run() -> None:
        engine = create_async_engine(async_postgres_url(os.environ["CUTOVER_SOURCE_URL"]))
        try:
            # source_engine's server setting is the contract under test
            from scripts.cutover_v2 import source_engine

            source = source_engine()
            try:
                await assert_source_read_only(source)
            finally:
                await source.dispose()
        finally:
            await engine.dispose()

    _run(run())


def _prepared_manifest(rehearsal):
    async def run():
        from scripts.cutover_v2 import migrator_engine, source_engine

        source = source_engine()
        migrator = migrator_engine()
        target = create_async_engine(async_postgres_url(rehearsal[0]))
        try:
            snapshot = await load_source_snapshot(source)
            transformed = transform_source(snapshot)
            attestation = await attest_schema(migrator)
            target_identity, target_snapshot = await collect_target_inventory_as_app(target)
            manifest = build_manifest(
                snapshot=snapshot,
                transformed=transformed,
                target_snapshot=target_snapshot,
                source_identity=await _identity(source),
                schema_attestation=attestation,
                target_host_name=make_url(rehearsal[0]).host or "localhost",
                target_identity=attestation["target_identity"],
                source_dump_sha256="e" * 64,
            )
            return manifest, transformed, target, source, migrator
        except Exception:
            await source.dispose()
            await migrator.dispose()
            await target.dispose()
            raise

    return _run(run())


async def _identity(engine):
    from scripts.cutover_v2 import read_connection_identity

    async with engine.connect() as conn:
        return await read_connection_identity(conn, "public")


def test_role_split_and_atomic_commit_idempotency(rehearsal) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        try:
            await assert_app_cannot_read_alembic(target)
            await run_commit(manifest, target, transformed)
            await run_commit(manifest, target, transformed)
            await run_verify(manifest, target)
        finally:
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


def test_mapped_verify_corruption_is_detected(rehearsal) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        admin = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
        try:
            await run_commit(manifest, target, transformed)
            task_id = str(transformed["task"][0]["id"])
            await admin.execute(
                "UPDATE microsched.task SET title='corrupted synthetic value' WHERE id=$1", task_id
            )
            with pytest.raises(Exception, match="mapped drift"):
                await run_verify(manifest, target)
        finally:
            await admin.close()
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


def test_commit_transaction_rolls_back_after_purge(monkeypatch, rehearsal) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        from scripts import cutover_v2

        async def fail_after_delete(session, current_manifest, current_transformed):
            await session.execute(text("DELETE FROM microsched.task"))
            raise cutover_v2.CutoverError("synthetic mid-transaction failure")

        original = cutover_v2.purge_import_assert
        monkeypatch.setattr(cutover_v2, "purge_import_assert", fail_after_delete)
        try:
            with pytest.raises(cutover_v2.CutoverError, match="mid-transaction"):
                await run_commit(manifest, target, transformed)
        finally:
            monkeypatch.setattr(cutover_v2, "purge_import_assert", original)
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


def test_target_role_mismatch_is_rejected(rehearsal) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        try:
            with pytest.raises(Exception, match="microsched_app"):
                await run_commit(manifest, migrator, transformed)
        finally:
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())
