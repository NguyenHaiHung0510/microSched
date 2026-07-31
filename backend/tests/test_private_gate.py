"""Postgres-backed contract for private unlock, throttle, and hard TTL."""

import asyncio
import base64
import json
import os
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.auth import PostgresSessionStore
from app.domain.models import AppSetting, AuthSession
from app.domain.private_gate import (
    PIN_SETTING_KEY,
    THROTTLE_SETTING_KEY,
    ThrottleLockedError,
    WrongPinError,
    _verify_under_throttle,
    lock_now,
    set_pin,
    unlock,
)
from app.domain.tasks import PrivateWriteLocked, TaskCreate, TaskStore, TaskUpdate

pytestmark = pytest.mark.pg


def generated_pin() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    bootstrap = generated_pin()
    changed = generated_pin()
    wrong = generated_pin()
    while len({bootstrap, changed, wrong}) != 3:
        changed = generated_pin()
        wrong = generated_pin()

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "private-gate-test-state-secret")
    monkeypatch.setenv("PRIVATE_PIN_BOOTSTRAP", bootstrap)
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield bootstrap, changed, wrong
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


@asynccontextmanager
async def session_factory(pg_dsn: str):
    engine = create_async_engine(async_postgres_url(pg_dsn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield maker
    finally:
        await engine.dispose()


async def raw_setting(pg_dsn: str, key: str) -> dict | None:
    conn = await asyncpg.connect(pg_dsn)
    try:
        value = await conn.fetchval(
            "SELECT value FROM microsched.app_setting WHERE key = $1",
            key,
        )
        return json.loads(value) if isinstance(value, str) else value
    finally:
        await conn.close()


async def raw_private_until(pg_dsn: str, session_id):
    conn = await asyncpg.connect(pg_dsn)
    try:
        return await conn.fetchval(
            "SELECT private_until FROM microsched.session WHERE id = $1",
            session_id,
        )
    finally:
        await conn.close()


async def expire_throttle(maker: async_sessionmaker) -> None:
    async with maker() as db:
        result = await db.execute(
            select(AppSetting).where(AppSetting.key == THROTTLE_SETTING_KEY).with_for_update()
        )
        row = result.scalar_one()
        row.value = {
            **row.value,
            "locked_until": (datetime.now(UTC) - timedelta(seconds=1))
            .isoformat()
            .replace("+00:00", "Z"),
        }
        await db.commit()


def test_throttle_locks_exactly_at_10_20_36_and_resets_after_final_lock(
    pg_dsn,
    seed_auth_session,
    isolated_settings,
    monkeypatch,
):
    del seed_auth_session
    bootstrap, _changed, wrong = isolated_settings

    async def scenario():
        async with session_factory(pg_dsn) as maker:
            for attempt in range(1, 10):
                async with maker() as db:
                    assert await _verify_under_throttle(db, wrong) == (
                        "WRONG",
                        10 - attempt,
                    )
                    await db.commit()

            async with maker() as db:
                tenth = await _verify_under_throttle(db, wrong)
                await db.commit()
            assert tenth[0] == "LOCKED"

            before = await raw_setting(pg_dsn, THROTTLE_SETTING_KEY)
            assert before["locked_until"].endswith("Z")
            original_verify = __import__(
                "app.domain.private_gate", fromlist=["verify_pin"]
            ).verify_pin

            def must_not_verify(*_args):
                raise AssertionError("PIN verification ran while throttle was locked")

            monkeypatch.setattr("app.domain.private_gate.verify_pin", must_not_verify)
            async with maker() as db:
                still_locked = await _verify_under_throttle(db, wrong)
                await db.commit()
            assert still_locked[0] == "LOCKED"
            assert await raw_setting(pg_dsn, THROTTLE_SETTING_KEY) == before
            monkeypatch.setattr("app.domain.private_gate.verify_pin", original_verify)

            await expire_throttle(maker)
            for attempt in range(11, 20):
                async with maker() as db:
                    assert await _verify_under_throttle(db, wrong) == (
                        "WRONG",
                        20 - attempt,
                    )
                    await db.commit()
            async with maker() as db:
                twentieth = await _verify_under_throttle(db, wrong)
                await db.commit()
            assert twentieth[0] == "LOCKED"

            await expire_throttle(maker)
            for attempt in range(21, 36):
                async with maker() as db:
                    assert await _verify_under_throttle(db, wrong) == (
                        "WRONG",
                        36 - attempt,
                    )
                    await db.commit()
            async with maker() as db:
                thirty_sixth = await _verify_under_throttle(db, wrong)
                await db.commit()
            assert thirty_sixth[0] == "LOCKED"
            final_state = await raw_setting(pg_dsn, THROTTLE_SETTING_KEY)
            assert final_state["fail_count"] == 0

            await expire_throttle(maker)
            async with maker() as db:
                assert await _verify_under_throttle(db, wrong) == ("WRONG", 9)
                await db.commit()

            # The correct bootstrap remains valid throughout all three tiers.
            async with maker() as db:
                assert await _verify_under_throttle(db, bootstrap) == "OK"
                await db.commit()

    asyncio.run(scenario())


def test_throttle_jsonb_and_correct_reset_survive_a_new_connection(
    pg_dsn,
    seed_auth_session,
    isolated_settings,
):
    del seed_auth_session
    bootstrap, _changed, wrong = isolated_settings

    async def scenario():
        async with session_factory(pg_dsn) as maker:
            for _ in range(3):
                async with maker() as db:
                    await _verify_under_throttle(db, wrong)
                    await db.commit()

            persisted = await raw_setting(pg_dsn, THROTTLE_SETTING_KEY)
            assert persisted == {"fail_count": 3, "locked_until": None}

            async with maker() as db:
                assert await _verify_under_throttle(db, bootstrap) == "OK"
                await db.commit()

            reset = await raw_setting(pg_dsn, THROTTLE_SETTING_KEY)
            assert reset == {"fail_count": 0, "locked_until": None}

    asyncio.run(scenario())


def test_unlock_and_lock_now_reload_the_real_session_row(
    pg_dsn,
    seed_auth_session: AuthSession,
    isolated_settings,
):
    bootstrap, changed, _wrong = isolated_settings

    async def scenario():
        async with session_factory(pg_dsn) as maker:
            async with maker() as db:
                outcome = await unlock(db, seed_auth_session, bootstrap)
                assert outcome[0] == "OK"
                await db.commit()
            stored = await raw_private_until(pg_dsn, seed_auth_session.id)
            assert stored is not None
            remaining = stored - datetime.now(UTC)
            assert timedelta(minutes=35, seconds=30) < remaining <= timedelta(minutes=36)

            async with maker() as db:
                await set_pin(db, seed_auth_session, bootstrap, changed)
                await db.commit()
            assert await raw_private_until(pg_dsn, seed_auth_session.id) == stored

            # Pass the detached fixture object again: lock_now must select by ID in
            # this request's session rather than mutating that object in RAM.
            async with maker() as db:
                await lock_now(db, seed_auth_session)
                await db.commit()
            assert await raw_private_until(pg_dsn, seed_auth_session.id) is None

    asyncio.run(scenario())


def test_authenticated_reads_never_roll_private_until(
    pg_dsn,
    seed_auth_session,
    isolated_settings,
):
    del seed_auth_session
    bootstrap, _changed, _wrong = isolated_settings

    async def scenario():
        async with session_factory(pg_dsn) as maker:
            store = PostgresSessionStore(maker, ttl_days=90)
            token = await store.create("owner@example.test")
            try:
                session = await store.load_valid(token)
                assert session is not None
                async with maker() as db:
                    outcome = await unlock(db, session, bootstrap)
                    assert outcome[0] == "OK"
                    await db.commit()
                before = await raw_private_until(pg_dsn, session.id)

                for _ in range(5):
                    assert await store.load_valid(token) is not None

                after = await raw_private_until(pg_dsn, session.id)
                assert after == before
            finally:
                await store.delete(token)

    asyncio.run(scenario())


def test_set_pin_shares_throttle_and_serializes_with_lazy_bootstrap(
    pg_dsn,
    seed_auth_session: AuthSession,
    isolated_settings,
    monkeypatch,
):
    bootstrap, changed, wrong = isolated_settings

    async def scenario():
        async with session_factory(pg_dsn) as maker:
            for _ in range(9):
                async with maker() as db:
                    with pytest.raises(WrongPinError):
                        await set_pin(db, seed_auth_session, wrong, changed)
                    await db.commit()
            async with maker() as db:
                with pytest.raises(ThrottleLockedError):
                    await set_pin(db, seed_auth_session, wrong, changed)
                await db.commit()

            await expire_throttle(maker)

            async def open_with_bootstrap():
                async with maker() as db:
                    result = await unlock(db, seed_auth_session, bootstrap)
                    await db.commit()
                    return result

            async def rotate_from_bootstrap():
                async with maker() as db:
                    await set_pin(db, seed_auth_session, bootstrap, changed)
                    await db.commit()

            unlock_result, _ = await asyncio.wait_for(
                asyncio.gather(open_with_bootstrap(), rotate_from_bootstrap()),
                timeout=10,
            )
            assert isinstance(unlock_result, tuple)
            assert unlock_result[0] in {"OK", "WRONG"}

            pin_state = await raw_setting(pg_dsn, PIN_SETTING_KEY)
            assert pin_state["bootstrap"] is False

            replacement_bootstrap = generated_pin()
            monkeypatch.setenv("PRIVATE_PIN_BOOTSTRAP", replacement_bootstrap)
            get_settings.cache_clear()
            async with maker() as db:
                old_seed = await _verify_under_throttle(db, replacement_bootstrap)
                await db.commit()
            assert old_seed[0] == "WRONG"
            async with maker() as db:
                assert await _verify_under_throttle(db, changed) == "OK"
                await db.commit()

    asyncio.run(scenario())


def test_task_store_rejects_private_create_and_toggle_while_locked(
    pg_dsn,
    seed_auth_session: AuthSession,
    isolated_settings,
):
    del isolated_settings
    store = TaskStore()
    task_id = None

    async def scenario():
        nonlocal task_id
        async with session_factory(pg_dsn) as maker:
            async with maker() as db:
                with pytest.raises(PrivateWriteLocked):
                    await store.create(
                        db,
                        seed_auth_session,
                        TaskCreate(title="private gate redaction probe", is_private=True),
                    )

                public = await store.create(
                    db,
                    seed_auth_session,
                    TaskCreate(title="public gate probe"),
                )
                task_id = public.id
                with pytest.raises(PrivateWriteLocked):
                    await store.update(
                        db,
                        seed_auth_session,
                        public.id,
                        TaskUpdate(is_private=True),
                    )
                await db.commit()

        conn = await asyncpg.connect(pg_dsn)
        try:
            assert (
                await conn.fetchval(
                    "SELECT is_private FROM microsched.task WHERE id = $1",
                    task_id,
                )
                is False
            )
        finally:
            await conn.execute("DELETE FROM microsched.task WHERE id = $1", task_id)
            await conn.close()

    asyncio.run(scenario())
