"""Disposable-Postgres proofs for one-shot request fingerprint migration 0016."""

import asyncio
import os
from pathlib import Path
from uuid import uuid7

import asyncpg
import pytest
from alembic.config import Config

from alembic import command

pytestmark = pytest.mark.pg


def _config() -> Config:
    return Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


async def _seed_reminder(*, fingerprint: str | None):
    connection = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
    task_id = uuid7()
    reminder_id = uuid7()
    try:
        await connection.execute(
            "INSERT INTO microsched.task (id, title, status, due_precision, due_at) "
            "VALUES ($1, 'synthetic migration fixture', 'open', 'datetime', "
            "now() + interval '2 days')",
            task_id,
        )
        await connection.execute(
            "INSERT INTO microsched.one_shot_reminder "
            "(id, task_id, mode, due_at, request_fingerprint_sha256) "
            "VALUES ($1, $2, 'absolute', now() + interval '1 day', $3)",
            reminder_id,
            task_id,
            fingerprint,
        )
        return task_id, reminder_id
    finally:
        await connection.close()


async def _cleanup(task_id, reminder_id) -> None:
    connection = await asyncpg.connect(os.environ["NEON_MIGRATOR_URL"])
    try:
        await connection.execute(
            "DELETE FROM microsched.one_shot_reminder WHERE id = $1", reminder_id
        )
        await connection.execute("DELETE FROM microsched.task WHERE id = $1", task_id)
    finally:
        await connection.close()


def test_0016_existing_reminders_survive_roundtrip_with_null_fingerprint(pg_dsn: str) -> None:
    task_id, reminder_id = asyncio.run(_seed_reminder(fingerprint=None))
    try:
        command.downgrade(_config(), "0015")

        async def assert_legacy_row_survived() -> None:
            connection = await asyncpg.connect(pg_dsn)
            try:
                assert (
                    await connection.fetchval(
                        "SELECT count(*) FROM microsched.one_shot_reminder WHERE id=$1", reminder_id
                    )
                    == 1
                )
            finally:
                await connection.close()

        asyncio.run(assert_legacy_row_survived())
        command.upgrade(_config(), "head")

        async def assert_nullable_legacy_value() -> None:
            connection = await asyncpg.connect(pg_dsn)
            try:
                assert (
                    await connection.fetchval(
                        "SELECT request_fingerprint_sha256 FROM microsched.one_shot_reminder "
                        "WHERE id=$1",
                        reminder_id,
                    )
                    is None
                )
            finally:
                await connection.close()

        asyncio.run(assert_nullable_legacy_value())
    finally:
        command.upgrade(_config(), "head")
        asyncio.run(_cleanup(task_id, reminder_id))


def test_0016_fingerprint_is_immutable_and_blocks_lossy_downgrade(pg_dsn: str) -> None:
    fingerprint = "a" * 64
    task_id, reminder_id = asyncio.run(_seed_reminder(fingerprint=fingerprint))
    try:

        async def assert_immutable() -> None:
            connection = await asyncpg.connect(pg_dsn)
            try:
                with pytest.raises(asyncpg.CheckViolationError, match="fingerprint is immutable"):
                    await connection.execute(
                        "UPDATE microsched.one_shot_reminder SET request_fingerprint_sha256=$1 "
                        "WHERE id=$2",
                        "b" * 64,
                        reminder_id,
                    )
            finally:
                await connection.close()

        asyncio.run(assert_immutable())
        with pytest.raises(RuntimeError, match="refusing to drop persisted"):
            command.downgrade(_config(), "0015")

        async def assert_schema_and_row_unchanged() -> None:
            connection = await asyncpg.connect(pg_dsn)
            try:
                assert (
                    await connection.fetchval("SELECT version_num FROM microsched.alembic_version")
                    == "0016"
                )
                assert (
                    await connection.fetchval(
                        "SELECT request_fingerprint_sha256 FROM microsched.one_shot_reminder "
                        "WHERE id=$1",
                        reminder_id,
                    )
                    == fingerprint
                )
            finally:
                await connection.close()

        asyncio.run(assert_schema_and_row_unchanged())
    finally:
        command.upgrade(_config(), "head")
        asyncio.run(_cleanup(task_id, reminder_id))
