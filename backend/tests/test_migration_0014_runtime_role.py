"""Prove Mimi migrations run through the owner that has app-role defaults."""

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest

pytestmark = pytest.mark.pg

MIMI_TABLES = (
    "mimi_conversation",
    "mimi_run",
    "mimi_message",
    "mimi_event",
    "mimi_provider_call",
    "mimi_change_set",
    "mimi_execution_receipt",
    "mimi_refresh_marker",
    "mimi_feedback",
    "mimi_evidence",
)


def test_0014_app_role_has_crud_and_public_has_none(pg_dsn: str) -> None:
    async def scenario() -> None:
        owner = await asyncpg.connect(pg_dsn)
        try:
            app_grants = await owner.fetchval(
                """
                SELECT count(*) FROM information_schema.role_table_grants
                WHERE grantee = 'microsched_app'
                  AND table_schema = 'microsched'
                  AND table_name = ANY($1::text[])
                  AND privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
                """,
                list(MIMI_TABLES),
            )
            assert app_grants == len(MIMI_TABLES) * 4
            public_grants = await owner.fetchval(
                """
                SELECT count(*) FROM information_schema.role_table_grants
                WHERE grantee = 'PUBLIC'
                  AND table_schema = 'microsched'
                  AND table_name = ANY($1::text[])
                """,
                list(MIMI_TABLES),
            )
            assert public_grants == 0
        finally:
            await owner.close()

        app = await asyncpg.connect(os.environ["CI_APP_DATABASE_URL"])
        try:
            transaction = app.transaction()
            await transaction.start()
            conversation_id = await app.fetchval(
                """
                INSERT INTO microsched.mimi_conversation
                    (owner_id, sensitivity, dek_wrapped, is_private)
                VALUES ($1, 'standard', 'enc:v1:fixture', false)
                RETURNING id
                """,
                uuid4(),
            )
            assert await app.fetchval(
                "SELECT count(*) FROM microsched.mimi_conversation WHERE id = $1",
                conversation_id,
            ) == 1
            await app.execute(
                """
                UPDATE microsched.mimi_conversation
                SET metadata_version = metadata_version + 1
                WHERE id = $1
                """,
                conversation_id,
            )
            await app.execute(
                "DELETE FROM microsched.mimi_conversation WHERE id = $1",
                conversation_id,
            )
            await transaction.rollback()

            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await app.execute("CREATE TABLE microsched.mimi_role_must_not_ddl (id integer)")
        finally:
            await app.close()

    asyncio.run(scenario())
