"""F7 real-role failure/restore proof across bootstrap, migration and bootstrap."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.engine import make_url

from scripts.bootstrap_neon import bootstrap

pytestmark = pytest.mark.pg


def test_bootstrap_migration_bootstrap_preserves_appendonly(pg_dsn):
    async def scenario():
        owner = make_url(pg_dsn)
        assert owner.host in {"127.0.0.1", "localhost", "::1"}
        name = "microsched_n01_grants_" + uuid4().hex[:12]
        conn = await asyncpg.connect(pg_dsn)
        await conn.execute(f'CREATE DATABASE "{name}"')
        values = {
            "NEON_OWNER_URL": owner.set(database=name).render_as_string(hide_password=False),
            "DATABASE_URL": owner.set(
                database=name,
                username="microsched_app",
                password=os.environ["CI_APP_PASSWORD"],
            ).render_as_string(hide_password=False),
            "NEON_MIGRATOR_URL": owner.set(
                database=name,
                username="microsched_migrator",
                password=os.environ["CI_MIGRATOR_PASSWORD"],
            ).render_as_string(hide_password=False),
        }
        env = dict(os.environ) | {
            "NEON_MIGRATOR_URL": values["NEON_MIGRATOR_URL"],
            "CI_MIGRATOR_URL": values["NEON_MIGRATOR_URL"],
        }
        backend = Path(__file__).resolve().parents[1]

        async def migrate(target):
            result = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-m", "alembic", "upgrade", target],
                cwd=backend,
                env=env,
                capture_output=True,
            )
            assert result.returncode == 0, (
                "migration process failed (secret-safe output suppressed)"
            )

        async def privileges():
            app = await asyncpg.connect(values["DATABASE_URL"])
            try:
                return [
                    await app.fetchval(
                        "SELECT has_table_privilege($1, $2)", "microsched." + table, privilege
                    )
                    for table in (
                        "migarden_config",
                        "migarden_report",
                        "migarden_boot",
                        "migarden_health",
                    )
                    for privilege in ("UPDATE", "DELETE", "TRUNCATE")
                ]
            finally:
                await app.close()

        try:
            await bootstrap(values)
            await migrate("0020")
            await bootstrap(values)
            await migrate("head")
            assert await privileges() == [False] * 12
            # Intentional local violation: reproduce the historical broad grant.
            admin = await asyncpg.connect(values["NEON_OWNER_URL"])
            try:
                await admin.execute(
                    "GRANT UPDATE, DELETE ON microsched.migarden_config, "
                    "microsched.migarden_report, microsched.migarden_boot, "
                    "microsched.migarden_health TO microsched_app"
                )
            finally:
                await admin.close()
            assert any(await privileges()), "intended violation must be detectable"
            await bootstrap(values)
            assert await privileges() == [False] * 12
            await bootstrap(values)
            assert await privileges() == [False] * 12
        finally:
            await conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=$1 "
                "AND pid <> pg_backend_pid()",
                name,
            )
            await conn.execute(f'DROP DATABASE "{name}"')
            await conn.close()

    asyncio.run(scenario())
