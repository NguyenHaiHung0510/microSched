"""Postgres proofs for the 0007 day_annotation constraint-name reconciliation."""

import asyncio
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config

from alembic import command

LEGACY_NAME = "ck_day_annotation_day_range"
EXACT_NAME = "day_range"


def migration_config() -> Config:
    """Build the repository Alembic configuration used by the PG QA lane."""
    return Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


def constraint_names(pg_dsn: str) -> set[str]:
    """Read the physical CHECK constraint names from PostgreSQL's catalog."""

    async def query() -> set[str]:
        connection = await asyncpg.connect(pg_dsn)
        try:
            rows = await connection.fetch(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'microsched.day_annotation'::regclass
                  AND contype = 'c'
                """
            )
        finally:
            await connection.close()
        return {row["conname"] for row in rows}

    return asyncio.run(query())


@pytest.mark.pg
def test_0007_renames_legacy_constraint_to_exact_name(pg_dsn: str) -> None:
    """An existing 0006 production schema is upgraded to the exact name."""
    config = migration_config()
    try:
        command.downgrade(config, "0006")
        assert constraint_names(pg_dsn) == {LEGACY_NAME}

        command.upgrade(config, "head")
        assert constraint_names(pg_dsn) == {EXACT_NAME}
    finally:
        command.upgrade(config, "head")


@pytest.mark.pg
def test_0007_is_noop_for_fresh_0006_exact_constraint(pg_dsn: str) -> None:
    """A fresh 0006 schema keeps day_range when 0007 is applied."""
    config = migration_config()
    try:
        command.downgrade(config, "0006")

        # 0007's downgrade leaves a valid 0006 table with the legacy name.
        # Recreate the state produced by a fresh, corrected 0006 before upgrading.
        async def rename_to_exact() -> None:
            connection = await asyncpg.connect(pg_dsn)
            try:
                await connection.execute(
                    """
                    ALTER TABLE microsched.day_annotation
                        RENAME CONSTRAINT ck_day_annotation_day_range TO day_range
                    """
                )
            finally:
                await connection.close()

        asyncio.run(rename_to_exact())
        assert constraint_names(pg_dsn) == {EXACT_NAME}

        command.upgrade(config, "head")
        assert constraint_names(pg_dsn) == {EXACT_NAME}
        command.downgrade(config, "0006")
        assert constraint_names(pg_dsn) == {LEGACY_NAME}
        command.upgrade(config, "head")
        assert constraint_names(pg_dsn) == {EXACT_NAME}
    finally:
        command.upgrade(config, "head")
