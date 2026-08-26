"""Throwaway-Postgres receipts for the generic tracker reminder expansion."""

import asyncio
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from alembic import command

pytestmark = pytest.mark.pg


def _config() -> Config:
    return Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


def test_0011_backfills_legacy_and_enforces_generic_constraints(pg_dsn: str) -> None:
    async def seed_legacy() -> object:
        conn = await asyncpg.connect(pg_dsn)
        try:
            return await conn.fetchval(
                """
                INSERT INTO microsched.tracker (name, kind, input_mode, reminder_time)
                VALUES ('enc:v1:bGVnYWN5', 'health', 'event', TIME '08:30')
                RETURNING id
                """
            )
        finally:
            await conn.close()

    async def assert_upgrade(tracker_id: object) -> None:
        conn = await asyncpg.connect(pg_dsn)
        try:
            row = await conn.fetchrow(
                """
                SELECT reminder_mode, reminder_interval_days, reminder_action, reminder_time
                FROM microsched.tracker WHERE id = $1
                """,
                tracker_id,
            )
            assert tuple(row.values()) == ("fixed", 1, "confirm_event", row["reminder_time"])
            assert row["reminder_time"].isoformat() == "08:30:00"
            group_id = await conn.fetchval(
                "INSERT INTO microsched.tracker_group (name, kind) VALUES ('G chung', 'general') "
                "RETURNING id"
            )
            general_id = await conn.fetchval(
                """
                INSERT INTO microsched.tracker (name, kind, input_mode, group_id)
                VALUES ('enc:v1:Z2VuZXJhbA==', 'general', 'event', $1) RETURNING id
                """,
                group_id,
            )
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    """
                    INSERT INTO microsched.tracker
                        (name, kind, input_mode, reminder_mode, reminder_interval_days,
                         reminder_action, reminder_time)
                    VALUES ('enc:v1:aW52YWxpZA==', 'general', 'money', 'fixed', 1,
                            'confirm_event', TIME '08:30')
                    """
                )
            await conn.execute("DELETE FROM microsched.tracker WHERE id = $1", general_id)
            await conn.execute("DELETE FROM microsched.tracker_group WHERE id = $1", group_id)
        finally:
            await conn.close()

    tracker_id = None
    config = _config()
    try:
        command.downgrade(config, "0010")
        tracker_id = asyncio.run(seed_legacy())
        command.upgrade(config, "head")
        asyncio.run(assert_upgrade(tracker_id))
    finally:
        command.upgrade(config, "head")
        if tracker_id is not None:

            async def cleanup() -> None:
                conn = await asyncpg.connect(pg_dsn)
                try:
                    await conn.execute("DELETE FROM microsched.tracker WHERE id = $1", tracker_id)
                finally:
                    await conn.close()

            asyncio.run(cleanup())


def test_0011_downgrade_refuses_advanced_reminder(pg_dsn: str) -> None:
    async def seed_advanced() -> object:
        conn = await asyncpg.connect(pg_dsn)
        try:
            return await conn.fetchval(
                """
                INSERT INTO microsched.tracker
                    (name, kind, input_mode, reminder_mode, reminder_interval_days,
                     reminder_action, reminder_time)
                VALUES ('enc:v1:YWR2YW5jZWQ=', 'general', 'event', 'after_entry', 3,
                        'open_tracker', TIME '08:30')
                RETURNING id
                """
            )
        finally:
            await conn.close()

    tracker_id = asyncio.run(seed_advanced())
    config = _config()
    try:
        with pytest.raises(IntegrityError, match="general or advanced reminder data would be lost"):
            command.downgrade(config, "0010")
    finally:

        async def cleanup() -> None:
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute("DELETE FROM microsched.tracker WHERE id = $1", tracker_id)
            finally:
                await conn.close()

        asyncio.run(cleanup())
        command.upgrade(config, "head")
