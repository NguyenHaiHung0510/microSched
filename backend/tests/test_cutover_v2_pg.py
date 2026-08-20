"""Disposable-Postgres rehearsal for Task 012.

The fixture is deliberately opt-in through the existing ``pg`` lane.  CI's
Postgres service is throwaway; the source identity override is only for that
service database name and the production default remains ``microschedule_v2``.
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database_urls import async_postgres_url
from scripts.cutover_v2 import (
    DOMAIN_COMPONENTS,
    PURGE_ONLY_COMPONENTS,
    assert_app_cannot_read_alembic,
    assert_source_read_only,
    attest_schema,
    build_manifest,
    collect_target_inventory_as_app,
    expected_final_inventory,
    load_source_snapshot,
    parse_fly_status,
    read_connection_identity,
    restored_source_engine,
    run_commit,
    run_recover,
    run_verify,
    transform_source,
    verify_restored_source,
)

pytestmark = pytest.mark.pg

NOW = datetime(2026, 8, 20, 12, 34, 56, tzinfo=UTC)

NATIVE_FLY_STOPPED = {
    "PlatformVersion": "machines",
    "Machines": [
        {
            "id": "machine-synthetic",
            "state": "stopped",
            "events": [
                {
                    "type": "start",
                    "status": "started",
                    "source": "flyd",
                    "timestamp": 1724150000000,
                },
                {
                    "type": "launch",
                    "status": "created",
                    "source": "user",
                    "timestamp": 1724140000000,
                },
            ],
        }
    ],
}


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
                "TRUNCATE TABLE microsched.reminder_dispatch, microsched.entry, "
                "microsched.subscription, microsched.tracker, microsched.tracker_group, "
                "microsched.calendar_event, microsched.calendar_source, microsched.task_item, "
                "microsched.task, microsched.note_item, microsched.note, "
                "microsched.day_annotation, "
                "microsched.message, microsched.audit_log, microsched.app_setting, "
                "microsched.session, microsched.push_subscription CASCADE"
            )
            pre_task_id, pre_task_item_id = uuid4(), uuid4()
            pre_note_id, pre_note_item_id = uuid4(), uuid4()
            pre_calendar_source_id, pre_calendar_event_id = uuid4(), uuid4()
            await conn.execute(
                "INSERT INTO microsched.task (id,title,status) "
                "VALUES ($1,'synthetic prestate','open')",
                pre_task_id,
            )
            await conn.execute(
                "INSERT INTO microsched.task_item (id,task_id,content) "
                "VALUES ($1,$2,'synthetic item')",
                pre_task_item_id,
                pre_task_id,
            )
            await conn.execute(
                "INSERT INTO microsched.note (id,title,pinned) VALUES ($1,'synthetic note',false)",
                pre_note_id,
            )
            await conn.execute(
                "INSERT INTO microsched.note_item (id,note_id,content) "
                "VALUES ($1,$2,'synthetic note item')",
                pre_note_item_id,
                pre_note_id,
            )
            await conn.execute(
                "INSERT INTO microsched.calendar_source (id,name,kind) "
                "VALUES ($1,'synthetic source','manual')",
                pre_calendar_source_id,
            )
            await conn.execute(
                "INSERT INTO microsched.calendar_event "
                "(id,source_id,title,starts_at,ends_at) "
                "VALUES ($1,$2,'synthetic event',$3,$4)",
                pre_calendar_event_id,
                pre_calendar_source_id,
                NOW,
                NOW + timedelta(hours=1),
            )
            group_id, tracker_id, subscription_id = uuid4(), uuid4(), uuid4()
            await conn.execute(
                "INSERT INTO microsched.day_annotation "
                "(label,starts_on,ends_on) VALUES ('synthetic day','2026-08-20','2026-08-21')"
            )
            await conn.execute(
                "INSERT INTO microsched.tracker_group (id,name,kind,position) "
                "VALUES ($1,'synthetic group','health',0)",
                group_id,
            )
            await conn.execute(
                "INSERT INTO microsched.tracker "
                "(id,name,kind,direction,input_mode,group_id) "
                "VALUES ($1,'enc:v1:synthetic-tracker','health','out','event',$2)",
                tracker_id,
                group_id,
            )
            await conn.execute(
                "INSERT INTO microsched.subscription "
                "(id,name,tracker_id,amount,started_on,expires_on) "
                "VALUES ($1,'enc:v1:synthetic-sub',$2,'enc:v1:amount','2026-08-20','2026-08-21')",
                subscription_id,
                tracker_id,
            )
            await conn.execute(
                "INSERT INTO microsched.entry "
                "(tracker_id,subscription_id,quantity,occurred_at) VALUES ($1,$2,$3,$4)",
                tracker_id,
                subscription_id,
                Decimal("1.00"),
                NOW,
            )
            await conn.execute(
                "INSERT INTO microsched.reminder_dispatch "
                "(subject_type,subject_id,dispatched_on) VALUES ('tracker',$1,'2026-08-20')",
                tracker_id,
            )
            await conn.execute(
                "INSERT INTO microsched.message (role,content,trace_id) "
                "VALUES ('user','enc:v1:synthetic-message',$1)",
                uuid4(),
            )
            await conn.execute(
                "INSERT INTO microsched.audit_log "
                "(trace_id,turn_id,action,payload) VALUES ($1,$2,'synthetic-audit','{}'::jsonb)",
                uuid4(),
                uuid4(),
            )
            await conn.execute(
                "INSERT INTO microsched.app_setting (key,value) "
                "VALUES ('synthetic-preserve','{\"synthetic\":true}'::jsonb)"
            )
            await conn.execute(
                "INSERT INTO microsched.session (token_hash,user_email,expires_at) "
                "VALUES ('synthetic-session-hash','synthetic@example.invalid',$1)",
                NOW + timedelta(days=1),
            )
            await conn.execute(
                "INSERT INTO microsched.push_subscription (endpoint,p256dh,auth) "
                "VALUES ('https://push.invalid/synthetic','synthetic-p256dh','synthetic-auth')"
            )
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
                "($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
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
                "($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
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
    restore_db = f"microsched_restore_{uuid4().hex[:12]}"
    control_url = parsed.set(database="postgres").render_as_string(hide_password=False)

    async def create_restore() -> None:
        control = await asyncpg.connect(control_url)
        try:
            active_sessions = await control.fetchval(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname=$1 AND pid <> pg_backend_pid()",
                db,
            )
            if active_sessions:
                raise RuntimeError(
                    "throwaway restore refused: source database has "
                    f"{active_sessions} active session(s)"
                )
            await control.execute(f'CREATE DATABASE "{restore_db}" TEMPLATE "{db}"')
        finally:
            await control.close()

    _run(create_restore())
    restored_url = parsed.set(database=restore_db).render_as_string(hide_password=False)
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
    yield app_url, migrator_url, restored_url

    async def clear_target() -> None:
        cleanup = await asyncpg.connect(admin_url)
        try:
            await cleanup.execute(
                "TRUNCATE TABLE microsched.reminder_dispatch, microsched.entry, "
                "microsched.subscription, microsched.tracker, microsched.tracker_group, "
                "microsched.calendar_event, microsched.calendar_source, microsched.task_item, "
                "microsched.task, microsched.note_item, microsched.note, "
                "microsched.day_annotation, microsched.message, microsched.audit_log, "
                "microsched.app_setting, microsched.session, microsched.push_subscription CASCADE"
            )
        finally:
            await cleanup.close()

    _run(clear_target())

    async def drop_restore() -> None:
        drop_control = await asyncpg.connect(control_url)
        try:
            await drop_control.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=$1",
                restore_db,
            )
            await drop_control.execute(f'DROP DATABASE IF EXISTS "{restore_db}"')
        finally:
            await drop_control.close()

    _run(drop_restore())
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


@pytest.mark.parametrize(
    "table,index_name",
    (
        ("calendar_source", "uq_calendar_source_name_lower"),
        ("tracker_group", "uq_tracker_group_name_lower"),
    ),
)
def test_schema_attestation_red_green_for_indexes_and_grantees(
    rehearsal, table: str, index_name: str
) -> None:
    async def run() -> None:
        from scripts.cutover_v2 import migrator_engine

        admin = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
        migrator = migrator_engine()
        extra_role = f"cutover_attest_{uuid4().hex[:12]}"
        try:
            await attest_schema(migrator)
            await admin.execute(f'DROP INDEX microsched."{index_name}"')
            with pytest.raises(Exception, match="functional unique-index"):
                await attest_schema(migrator)
            await admin.execute(
                f'CREATE UNIQUE INDEX "{index_name}" ON microsched."{table}" (lower(name))'
            )
            await attest_schema(migrator)

            await admin.execute(f'CREATE ROLE "{extra_role}"')
            await admin.execute(f'GRANT USAGE ON SCHEMA microsched TO "{extra_role}"')
            with pytest.raises(Exception, match="grantee"):
                await attest_schema(migrator)
        finally:
            # Make teardown safe if the assertion itself fails halfway through
            # the deliberate RED/GREEN sequence.
            try:
                role_exists = await admin.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=$1)", extra_role
                )
                if role_exists:
                    await admin.execute(f'REASSIGN OWNED BY "{extra_role}" TO postgres')
                    await admin.execute(f'DROP OWNED BY "{extra_role}"')
                    await admin.execute(
                        f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA microsched "
                        f'FROM "{extra_role}"'
                    )
                    await admin.execute(f'REVOKE ALL ON SCHEMA microsched FROM "{extra_role}"')
                    await admin.execute(f'DROP ROLE "{extra_role}"')
            finally:
                try:
                    await admin.execute(
                        f'CREATE UNIQUE INDEX IF NOT EXISTS "{index_name}" '
                        f'ON microsched."{table}" (lower(name))'
                    )
                    await attest_schema(migrator)
                finally:
                    await admin.close()
                    await migrator.dispose()

    _run(run())


def test_restored_source_is_read_only_and_matches_inventory(rehearsal) -> None:
    async def run() -> None:
        source = restored_source_engine(os.environ["CUTOVER_SOURCE_URL"])
        try:
            snapshot = await load_source_snapshot(source)
            async with source.connect() as connection:
                identity = await read_connection_identity(connection, "public")
            with pytest.raises(Exception, match="distinct from the live source"):
                await verify_restored_source(source, snapshot.source_inventory, identity)
            await assert_source_read_only(source)
        finally:
            await source.dispose()

    _run(run())


def test_distinct_restored_source_identity_is_read_only(rehearsal) -> None:
    async def run() -> None:
        from scripts.cutover_v2 import source_engine

        live = source_engine()
        restored = restored_source_engine(rehearsal[2])
        try:
            snapshot = await load_source_snapshot(live)
            async with live.connect() as connection:
                live_identity = await read_connection_identity(connection, "public")
            restored_snapshot = await verify_restored_source(
                restored, snapshot.source_inventory, live_identity
            )
            assert restored_snapshot.source_inventory == snapshot.source_inventory
            async with restored.connect() as connection:
                restored_identity = await read_connection_identity(connection, "public")
            assert restored_identity["database"] != live_identity["database"]
            await assert_source_read_only(restored)
        finally:
            await live.dispose()
            await restored.dispose()

    _run(run())


def test_async_main_dry_run_reads_without_target_dml(rehearsal, capsys) -> None:
    async def run() -> int:
        from scripts.cutover_v2 import async_main, parser

        target = create_async_engine(async_postgres_url(rehearsal[0]))
        try:
            _, before = await collect_target_inventory_as_app(target)
            result = await async_main(parser().parse_args(["--dry-run"]))
            _, after = await collect_target_inventory_as_app(target)
        finally:
            await target.dispose()
        assert after == before
        return result

    assert _run(run()) == 0
    output = capsys.readouterr().out
    assert "calendar_bucket manual" in output
    assert "calendar_bucket ics_reimport" in output


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
            # The caller deliberately runs its assertions in a separate
            # asyncio.run loop.  Empty these pools before crossing that loop
            # boundary; AsyncEngine is reusable, but an asyncpg connection
            # retained by the first loop is not.
            await source.dispose()
            await migrator.dispose()
            await target.dispose()
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


MAPPED_DRIFT_CASES = (
    ("task", "title", "synthetic source task drift"),
    ("task_item", "content", "synthetic source item drift"),
    ("note", "title", "synthetic source note drift"),
    ("note_item", "content", "synthetic source note item drift"),
    ("calendar_source", "name", "synthetic source name drift"),
    ("calendar_event", "title", "synthetic source event drift"),
)

MAPPED_PREDELETE_DRIFT_CASES = (
    ("task", "title", "synthetic prestate", "synthetic pre-delete task drift"),
    ("task_item", "content", "synthetic item", "synthetic pre-delete item drift"),
    ("note", "title", "synthetic note", "synthetic pre-delete note drift"),
    ("note_item", "content", "synthetic note item", "synthetic pre-delete note item drift"),
    ("calendar_source", "name", "synthetic source", "synthetic pre-delete source drift"),
    ("calendar_event", "title", "synthetic event", "synthetic pre-delete event drift"),
)


async def _insert_residual_asyncpg(conn, component: str) -> None:
    """Insert one valid synthetic row, including its FK chain, for residual tests."""
    if component == "day_annotation":
        await conn.execute(
            "INSERT INTO microsched.day_annotation "
            "(label,starts_on,ends_on) VALUES ('enc:v1:residual-day','2026-08-20','2026-08-21')"
        )
        return
    if component == "tracker_group":
        await conn.execute(
            "INSERT INTO microsched.tracker_group (id,name,kind,position) "
            "VALUES ($1,'enc:v1:residual-group','health',0)",
            uuid4(),
        )
        return
    group_id, tracker_id = uuid4(), uuid4()
    if component in {"tracker", "entry", "subscription", "reminder_dispatch"}:
        await conn.execute(
            "INSERT INTO microsched.tracker_group (id,name,kind,position) "
            "VALUES ($1,$2,'health',0)",
            group_id,
            f"enc:v1:residual-group-{uuid4()}",
        )
        await conn.execute(
            "INSERT INTO microsched.tracker "
            "(id,name,kind,direction,input_mode,group_id) "
            "VALUES ($1,$2,'health','out','event',$3)",
            tracker_id,
            f"enc:v1:residual-tracker-{uuid4()}",
            group_id,
        )
    if component == "tracker":
        return
    if component == "subscription":
        await conn.execute(
            "INSERT INTO microsched.subscription "
            "(id,name,tracker_id,amount,started_on,expires_on) "
            "VALUES ($1,$2,$3,'enc:v1:residual-amount','2026-08-20','2026-08-21')",
            uuid4(),
            f"enc:v1:residual-sub-{uuid4()}",
            tracker_id,
        )
        return
    if component == "entry":
        await conn.execute(
            "INSERT INTO microsched.entry (tracker_id,quantity,occurred_at) VALUES ($1,1.00,$2)",
            tracker_id,
            NOW,
        )
        return
    if component == "reminder_dispatch":
        await conn.execute(
            "INSERT INTO microsched.reminder_dispatch "
            "(subject_type,subject_id,dispatched_on) VALUES ('tracker',$1,'2026-08-20')",
            tracker_id,
        )
        return
    if component == "message":
        await conn.execute(
            "INSERT INTO microsched.message (role,content,trace_id) VALUES ('user',$1,$2)",
            f"enc:v1:residual-message-{uuid4()}",
            uuid4(),
        )
        return
    if component == "audit_log":
        await conn.execute(
            "INSERT INTO microsched.audit_log "
            "(trace_id,turn_id,action,payload) VALUES ($1,$2,$3,'{}'::jsonb)",
            uuid4(),
            uuid4(),
            f"residual-{uuid4()}",
        )
        return
    raise AssertionError(f"unhandled residual component: {component}")


async def _insert_residual_session(session, component: str) -> None:
    """Session equivalent for same-transaction residual tests."""
    if component == "day_annotation":
        await session.execute(
            text(
                "INSERT INTO microsched.day_annotation "
                "(label,starts_on,ends_on) VALUES ('enc:v1:residual-day','2026-08-20','2026-08-21')"
            )
        )
        return
    if component == "tracker_group":
        await session.execute(
            text(
                "INSERT INTO microsched.tracker_group (id,name,kind,position) "
                "VALUES (:id,'enc:v1:residual-group','health',0)"
            ),
            {"id": uuid4()},
        )
        return
    group_id, tracker_id = uuid4(), uuid4()
    if component in {"tracker", "entry", "subscription", "reminder_dispatch"}:
        await session.execute(
            text(
                "INSERT INTO microsched.tracker_group (id,name,kind,position) "
                "VALUES (:id,:name,'health',0)"
            ),
            {"id": group_id, "name": f"enc:v1:residual-group-{uuid4()}"},
        )
        await session.execute(
            text(
                "INSERT INTO microsched.tracker "
                "(id,name,kind,direction,input_mode,group_id) "
                "VALUES (:id,:name,'health','out','event',:group_id)"
            ),
            {
                "id": tracker_id,
                "name": f"enc:v1:residual-tracker-{uuid4()}",
                "group_id": group_id,
            },
        )
    if component == "tracker":
        return
    if component == "subscription":
        await session.execute(
            text(
                "INSERT INTO microsched.subscription "
                "(id,name,tracker_id,amount,started_on,expires_on) "
                "VALUES (:id,:name,:tracker_id,'enc:v1:residual-amount',"
                "'2026-08-20','2026-08-21')"
            ),
            {
                "id": uuid4(),
                "name": f"enc:v1:residual-sub-{uuid4()}",
                "tracker_id": tracker_id,
            },
        )
        return
    if component == "entry":
        await session.execute(
            text(
                "INSERT INTO microsched.entry "
                "(tracker_id,quantity,occurred_at) VALUES (:tracker_id,1.00,:occurred_at)"
            ),
            {"tracker_id": tracker_id, "occurred_at": NOW},
        )
        return
    if component == "reminder_dispatch":
        await session.execute(
            text(
                "INSERT INTO microsched.reminder_dispatch "
                "(subject_type,subject_id,dispatched_on) "
                "VALUES ('tracker',:tracker_id,'2026-08-20')"
            ),
            {"tracker_id": tracker_id},
        )
        return
    if component == "message":
        await session.execute(
            text(
                "INSERT INTO microsched.message (role,content,trace_id) "
                "VALUES ('user',:content,:trace_id)"
            ),
            {"content": f"enc:v1:residual-message-{uuid4()}", "trace_id": uuid4()},
        )
        return
    if component == "audit_log":
        await session.execute(
            text(
                "INSERT INTO microsched.audit_log "
                "(trace_id,turn_id,action,payload) "
                "VALUES (:trace_id,:turn_id,:action,'{}'::jsonb)"
            ),
            {"trace_id": uuid4(), "turn_id": uuid4(), "action": f"residual-{uuid4()}"},
        )
        return
    raise AssertionError(f"unhandled residual component: {component}")


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


def test_predelete_mapped_drift_aborts_before_write(rehearsal) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        admin = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
        try:
            await admin.execute(
                "UPDATE microsched.task SET title='pre-delete drift' "
                "WHERE title='synthetic prestate'"
            )
            _, before = await collect_target_inventory_as_app(target)
            with pytest.raises(Exception, match="Phase-B snapshot drift"):
                await run_commit(manifest, target, transformed)
            _, after = await collect_target_inventory_as_app(target)
            assert after == before
        finally:
            await admin.close()
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


@pytest.mark.parametrize("component,field,original_value,drift_value", MAPPED_PREDELETE_DRIFT_CASES)
def test_predelete_each_mapped_component_real_row_drift_aborts(
    rehearsal, component: str, field: str, original_value: str, drift_value: str
) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        admin = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
        try:
            # This is a real target pre-state row mutation; changing only the
            # signed receipt would not exercise the Phase-B guard.
            updated = await admin.execute(
                f'UPDATE microsched."{component}" SET "{field}"=$1 WHERE "{field}"=$2',
                drift_value,
                original_value,
            )
            assert updated.endswith("1"), f"expected one target {component} prestate row"
            _, before = await collect_target_inventory_as_app(target)
            with pytest.raises(Exception, match="Phase-B snapshot drift"):
                await run_commit(manifest, target, transformed)
            _, after = await collect_target_inventory_as_app(target)
            assert after == before
        finally:
            await admin.execute(
                f'UPDATE microsched."{component}" SET "{field}"=$1 WHERE "{field}"=$2',
                original_value,
                drift_value,
            )
            await admin.close()
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


@pytest.mark.parametrize("component,field,drift_value", MAPPED_DRIFT_CASES)
def test_verify_each_mapped_component_real_row_corruption_is_detected(
    rehearsal, component: str, field: str, drift_value: str
) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)
    original_value = next(str(row[field]) for row in transformed[component])

    async def run() -> None:
        admin = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
        row_id = str(transformed[component][0]["id"])
        try:
            await run_commit(manifest, target, transformed)
            await admin.execute(
                f'UPDATE microsched."{component}" SET "{field}"=$1 WHERE id=$2',
                drift_value,
                row_id,
            )
            with pytest.raises(Exception, match="mapped drift"):
                await run_verify(manifest, target)
        finally:
            await admin.execute(
                f'UPDATE microsched."{component}" SET "{field}"=$1 WHERE id=$2',
                original_value,
                row_id,
            )
            await admin.close()
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


def test_predelete_real_component_and_preserve_field_drift_aborts(rehearsal) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        admin = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
        mutations = (
            (
                "day_annotation",
                "UPDATE microsched.day_annotation SET label='drift day' "
                "WHERE label='synthetic day'",
                "UPDATE microsched.day_annotation SET label='synthetic day' "
                "WHERE label='drift day'",
            ),
            (
                "tracker_group",
                "UPDATE microsched.tracker_group SET color='drift' WHERE name='synthetic group'",
                "UPDATE microsched.tracker_group SET color=NULL WHERE name='synthetic group'",
            ),
            (
                "tracker",
                "UPDATE microsched.tracker SET reminder_text='drift' "
                "WHERE name='enc:v1:synthetic-tracker'",
                "UPDATE microsched.tracker SET reminder_text=NULL "
                "WHERE name='enc:v1:synthetic-tracker'",
            ),
            (
                "entry",
                "UPDATE microsched.entry SET quantity=2.00 WHERE quantity=1.00",
                "UPDATE microsched.entry SET quantity=1.00 WHERE quantity=2.00",
            ),
            (
                "subscription",
                "UPDATE microsched.subscription SET note_md='enc:v1:drift' "
                "WHERE name='enc:v1:synthetic-sub'",
                "UPDATE microsched.subscription SET note_md=NULL WHERE name='enc:v1:synthetic-sub'",
            ),
            (
                "reminder_dispatch",
                "UPDATE microsched.reminder_dispatch SET status='sent' "
                "WHERE status='pending' AND subject_type='tracker'",
                "UPDATE microsched.reminder_dispatch SET status='pending' "
                "WHERE status='sent' AND subject_type='tracker'",
            ),
            (
                "message",
                "UPDATE microsched.message SET content='enc:v1:drift-message' "
                "WHERE content='enc:v1:synthetic-message'",
                "UPDATE microsched.message SET content='enc:v1:synthetic-message' "
                "WHERE content='enc:v1:drift-message'",
            ),
            (
                "audit_log",
                "UPDATE microsched.audit_log SET action='drift' WHERE action='synthetic-audit'",
                "UPDATE microsched.audit_log SET action='synthetic-audit' WHERE action='drift'",
            ),
            (
                "app_setting",
                "UPDATE microsched.app_setting SET value=jsonb_build_object('synthetic',false) "
                "WHERE key='synthetic-preserve'",
                "UPDATE microsched.app_setting SET value=jsonb_build_object('synthetic',true) "
                "WHERE key='synthetic-preserve'",
            ),
            (
                "session",
                "UPDATE microsched.session SET private_until=$1 "
                "WHERE token_hash='synthetic-session-hash'",
                "UPDATE microsched.session SET private_until=NULL "
                "WHERE token_hash='synthetic-session-hash'",
            ),
            (
                "push_subscription",
                "UPDATE microsched.push_subscription SET auth='synthetic-auth-drift' "
                "WHERE endpoint='https://push.invalid/synthetic'",
                "UPDATE microsched.push_subscription SET auth='synthetic-auth' "
                "WHERE endpoint='https://push.invalid/synthetic'",
            ),
        )
        try:
            for component, mutate_sql, restore_sql in mutations:
                if component == "session":
                    await admin.execute(mutate_sql, NOW)
                else:
                    await admin.execute(mutate_sql)
                _, before = await collect_target_inventory_as_app(target)
                try:
                    with pytest.raises(Exception, match="Phase-B snapshot drift"):
                        await run_commit(manifest, target, transformed)
                    _, after = await collect_target_inventory_as_app(target)
                    assert after == before
                finally:
                    await admin.execute(restore_sql)
        finally:
            await admin.close()
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


def test_recover_reimports_authorized_failed_inventory(rehearsal) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        admin = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
        try:
            await run_commit(manifest, target, transformed)
            task_id = str(transformed["task"][0]["id"])
            await admin.execute(
                "UPDATE microsched.task SET title='authorized failed state' WHERE id=$1", task_id
            )
            _, failed = await collect_target_inventory_as_app(target)
            receipt = {
                "failure_time": NOW.isoformat(),
                "target_state": parse_fly_status(NATIVE_FLY_STOPPED),
                "failed_run_domain_inventory": {
                    component: failed[component] for component in DOMAIN_COMPONENTS
                },
            }

            async def fly_state() -> dict[str, object]:
                return NATIVE_FLY_STOPPED

            await run_recover(
                manifest,
                receipt,
                target,
                transformed,
                fly_state_verifier=fly_state,
            )
            await run_verify(manifest, target)
        finally:
            await admin.close()
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


def test_recover_post_transaction_fly_audit_is_bounded(rehearsal) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        admin = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
        calls = 0
        restarted = {
            "PlatformVersion": "machines",
            "Machines": [
                {
                    "id": "machine-synthetic",
                    "state": "stopped",
                    "events": [
                        *NATIVE_FLY_STOPPED["Machines"][0]["events"],
                        {
                            "type": "start",
                            "status": "started",
                            "source": "flyd",
                            "timestamp": int((NOW + timedelta(seconds=1)).timestamp() * 1000),
                        },
                    ],
                }
            ],
        }

        async def fly_state() -> dict[str, object]:
            nonlocal calls
            calls += 1
            return NATIVE_FLY_STOPPED if calls == 1 else restarted

        try:
            await run_commit(manifest, target, transformed)
            task_id = str(transformed["task"][0]["id"])
            await admin.execute(
                "UPDATE microsched.task SET title='authorized failed state' WHERE id=$1", task_id
            )
            _, failed = await collect_target_inventory_as_app(target)
            with pytest.raises(Exception, match="restarted after"):
                await run_recover(
                    manifest,
                    {
                        "failure_time": NOW.isoformat(),
                        "target_state": parse_fly_status(NATIVE_FLY_STOPPED),
                        "failed_run_domain_inventory": {
                            component: failed[component] for component in DOMAIN_COMPONENTS
                        },
                    },
                    target,
                    transformed,
                    fly_state_verifier=fly_state,
                )
            after = await collect_target_inventory_as_app(target)
            # The owner-assisted stop has no external lease fence: the audit
            # detects a restart after the DB commit, so the committed target is
            # the finalized state and recovery must be investigated manually.
            assert after[1] == expected_final_inventory(manifest)
            assert calls == 2
        finally:
            await admin.close()
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


def test_recover_rejects_stale_failed_inventory(rehearsal) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        admin = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
        try:
            await run_commit(manifest, target, transformed)
            task_id = str(transformed["task"][0]["id"])
            await admin.execute(
                "UPDATE microsched.task SET title='stale receipt mismatch' WHERE id=$1", task_id
            )
            stale = {
                "failure_time": NOW.isoformat(),
                "target_state": parse_fly_status(NATIVE_FLY_STOPPED),
                "failed_run_domain_inventory": {
                    component: expected_final_inventory(manifest)[component]
                    for component in DOMAIN_COMPONENTS
                },
            }

            async def fly_state() -> dict[str, object]:
                return NATIVE_FLY_STOPPED

            with pytest.raises(Exception, match="authorized failed-run state"):
                await run_recover(
                    manifest,
                    stale,
                    target,
                    transformed,
                    fly_state_verifier=fly_state,
                )
        finally:
            await admin.close()
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


def test_recover_rejects_every_domain_inventory_perturbation(rehearsal) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        admin = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
        try:
            await run_commit(manifest, target, transformed)
            task_id = str(transformed["task"][0]["id"])
            await admin.execute(
                "UPDATE microsched.task SET title='authorized failed state' WHERE id=$1", task_id
            )
            _, failed = await collect_target_inventory_as_app(target)
            for component in DOMAIN_COMPONENTS:
                stale_inventory = {
                    name: dict(proof) for name, proof in failed.items() if name in DOMAIN_COMPONENTS
                }
                stale_inventory[component]["full_row_digest"] = "0" * 64
                with pytest.raises(Exception, match="authorized failed-run state"):
                    await run_recover(
                        manifest,
                        {
                            "failure_time": NOW.isoformat(),
                            "target_state": parse_fly_status(NATIVE_FLY_STOPPED),
                            "failed_run_domain_inventory": stale_inventory,
                        },
                        target,
                        transformed,
                        fly_state_verifier=lambda: NATIVE_FLY_STOPPED,
                    )
        finally:
            await admin.close()
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


def test_recover_rolls_back_mid_transaction_failure(monkeypatch, rehearsal) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        from scripts import cutover_v2

        admin = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
        try:
            await run_commit(manifest, target, transformed)
            task_id = str(transformed["task"][0]["id"])
            await admin.execute(
                "UPDATE microsched.task SET title='authorized failed state' WHERE id=$1", task_id
            )
            _, failed = await collect_target_inventory_as_app(target)
            before = await collect_target_inventory_as_app(target)

            async def fail_after_delete(session, current_manifest, current_transformed):
                await session.execute(text("DELETE FROM microsched.task"))
                raise cutover_v2.CutoverError("synthetic recovery mid-transaction failure")

            original = cutover_v2.purge_import_assert
            monkeypatch.setattr(cutover_v2, "purge_import_assert", fail_after_delete)
            try:
                with pytest.raises(Exception, match="recovery mid-transaction"):
                    await run_recover(
                        manifest,
                        {
                            "failure_time": NOW.isoformat(),
                            "target_state": parse_fly_status(NATIVE_FLY_STOPPED),
                            "failed_run_domain_inventory": {
                                component: failed[component] for component in DOMAIN_COMPONENTS
                            },
                        },
                        target,
                        transformed,
                        fly_state_verifier=lambda: NATIVE_FLY_STOPPED,
                    )
            finally:
                monkeypatch.setattr(cutover_v2, "purge_import_assert", original)
            after = await collect_target_inventory_as_app(target)
            assert after == before
        finally:
            await admin.close()
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


@pytest.mark.parametrize("component", PURGE_ONLY_COMPONENTS)
def test_verify_rejects_real_residual_for_each_purge_component(rehearsal, component: str) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        admin = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
        try:
            await run_commit(manifest, target, transformed)
            await _insert_residual_asyncpg(admin, component)
            with pytest.raises(Exception, match=f"residual purge-only row: {component}"):
                await run_verify(manifest, target)
        finally:
            # The fixture's next parameter starts from a clean state, but this
            # keeps this test independently safe if collection order changes.
            await admin.execute(
                "TRUNCATE TABLE microsched.reminder_dispatch, microsched.entry, "
                "microsched.subscription, microsched.tracker, microsched.tracker_group, "
                "microsched.day_annotation, microsched.message, microsched.audit_log CASCADE"
            )
            await admin.close()
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


@pytest.mark.parametrize("component", PURGE_ONLY_COMPONENTS)
def test_commit_rechecks_each_residual_inside_transaction(
    monkeypatch, rehearsal, component: str
) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        from scripts import cutover_v2

        original = cutover_v2.purge_import_assert

        async def add_residual(session, current_manifest, current_transformed):
            await original(session, current_manifest, current_transformed)
            await _insert_residual_session(session, component)

        monkeypatch.setattr(cutover_v2, "purge_import_assert", add_residual)
        try:
            with pytest.raises(Exception, match="post-purge final inventory drift"):
                await run_commit(manifest, target, transformed)
            # The residual and the purge/import must be rolled back together.
            _, after = await collect_target_inventory_as_app(target)
            assert after == manifest["phase_b_target_snapshot"]
        finally:
            monkeypatch.setattr(cutover_v2, "purge_import_assert", original)
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


def test_verify_rejects_purge_residual_and_preserve_drift(rehearsal) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        admin = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
        setting_key = f"synthetic-cutover-{uuid4()}"
        try:
            await run_commit(manifest, target, transformed)
            await admin.execute(
                "INSERT INTO microsched.message (role,content,trace_id) "
                "VALUES ('user','enc:v1:synthetic-residual',$1)",
                uuid4(),
            )
            with pytest.raises(Exception, match="residual purge-only"):
                await run_verify(manifest, target)
            await admin.execute(
                "DELETE FROM microsched.message WHERE content='enc:v1:synthetic-residual'"
            )
            preserve_rows = {
                "app_setting": (
                    "INSERT INTO microsched.app_setting (key,value) VALUES ($1,$2::jsonb)",
                    (setting_key, '{"synthetic":true}'),
                    f"DELETE FROM microsched.app_setting WHERE key='{setting_key}'",
                ),
                "session": (
                    "INSERT INTO microsched.session "
                    "(token_hash,user_email,expires_at) VALUES ($1,$2,$3)",
                    (f"hash-{uuid4()}", "synthetic@example.invalid", NOW + timedelta(days=1)),
                    "DELETE FROM microsched.session WHERE user_email='synthetic@example.invalid'",
                ),
                "push_subscription": (
                    "INSERT INTO microsched.push_subscription "
                    "(endpoint,p256dh,auth) VALUES ($1,$2,$3)",
                    (f"https://push.invalid/{uuid4()}", "synthetic-p256dh", "synthetic-auth"),
                    "DELETE FROM microsched.push_subscription WHERE p256dh='synthetic-p256dh'",
                ),
            }
            for insert_sql, values, cleanup_sql in preserve_rows.values():
                await admin.execute(insert_sql, *values)
                try:
                    with pytest.raises(Exception, match="preserve drift"):
                        await run_verify(manifest, target)
                finally:
                    await admin.execute(cleanup_sql)
        finally:
            await admin.execute(
                "DELETE FROM microsched.message WHERE content='enc:v1:synthetic-residual'"
            )
            await admin.execute("DELETE FROM microsched.app_setting WHERE key=$1", setting_key)
            await admin.close()
            await source.dispose()
            await migrator.dispose()
            await target.dispose()

    _run(run())


def test_non_null_vector_is_a_fail_closed_gate(rehearsal) -> None:
    manifest, transformed, target, source, migrator = _prepared_manifest(rehearsal)

    async def run() -> None:
        admin = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
        try:
            await run_commit(manifest, target, transformed)
            await admin.execute(
                "UPDATE microsched.note SET embedding='[1,2]'::vector WHERE id=$1",
                str(transformed["note"][0]["id"]),
            )
            with pytest.raises(Exception, match="embedding"):
                await collect_target_inventory_as_app(target)
        finally:
            await admin.execute(
                "UPDATE microsched.note SET embedding=NULL WHERE id=$1",
                str(transformed["note"][0]["id"]),
            )
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
            _, after_failure = await collect_target_inventory_as_app(target)
            assert after_failure == manifest["phase_b_target_snapshot"]
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
