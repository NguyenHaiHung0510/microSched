"""Prepared production SQL is rehearsed only in a named throwaway local database."""

import asyncio
import hashlib
import os
import secrets
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.engine import make_url

from scripts.bootstrap_neon import bootstrap
from scripts.prepare_migarden_commission import transaction

pytestmark = pytest.mark.pg


def test_prepared_binding_forward_rehearsal_cas_revoke_history_and_unknown_guard(pg_dsn):
    async def scenario():
        root = make_url(pg_dsn)
        assert root.host in {"127.0.0.1", "localhost", "::1"}
        name = "microsched_n01_commission_" + uuid4().hex[:12]
        admin = await asyncpg.connect(pg_dsn)
        await admin.execute(f'CREATE DATABASE "{name}"')
        owner = root.set(database=name).render_as_string(hide_password=False)
        migrator = root.set(
            database=name,
            username="microsched_migrator",
            password=os.environ["CI_MIGRATOR_PASSWORD"],
        ).render_as_string(hide_password=False)
        app_url = root.set(
            database=name, username="microsched_app", password=os.environ["CI_APP_PASSWORD"]
        ).render_as_string(hide_password=False)
        try:
            await bootstrap(
                {"NEON_OWNER_URL": owner, "NEON_MIGRATOR_URL": migrator, "DATABASE_URL": app_url}
            )
            env = dict(os.environ) | {"NEON_MIGRATOR_URL": migrator, "CI_MIGRATOR_URL": migrator}
            for target in ("0021", "0022"):
                result = await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, "-m", "alembic", "upgrade", target],
                    cwd=Path(__file__).resolve().parents[1],
                    env=env,
                    capture_output=True,
                )
                assert result.returncode == 0, "forward-only migration rehearsal failed"
            app = await asyncpg.connect(app_url)
            try:

                async def state():
                    row = await app.fetchrow(
                        "SELECT device_id,device_environment,token_hash,revoked_at "
                        "FROM microsched.migarden_zone WHERE zone_id='zone-a'"
                    )
                    result = dict(row)
                    if result["revoked_at"]:
                        result["revoked_at"] = result["revoked_at"].isoformat()
                    return result

                def script(action, expected, new_hash=None):
                    return transaction(
                        action=action,
                        environment="production",
                        device_id="prod-controller-synthetic",
                        database=name,
                        expected=expected,
                        token_hash=new_hash,
                        operation_id=uuid4().hex,
                    )

                raw = secrets.token_urlsafe(32)
                new_hash = hashlib.sha256(raw.encode()).hexdigest()
                initial = dict(
                    device_id=None, device_environment=None, token_hash=None, revoked_at=None
                )
                issue = script("issue", initial, new_hash)
                assert raw not in issue
                await app.execute(issue)
                installed = await state()
                assert installed["device_environment"] == "production"
                assert installed["token_hash"] == new_hash
                with pytest.raises(asyncpg.RaiseError, match="CAS conflict"):
                    await app.execute(issue)
                await app.execute("ROLLBACK")
                bad = installed | {"token_hash": "f" * 64}
                with pytest.raises(asyncpg.RaiseError, match="CAS conflict"):
                    await app.execute(script("revoke", bad))
                await app.execute("ROLLBACK")
                assert (
                    await app.fetchval(
                        "SELECT count(*) FROM microsched.audit_log "
                        "WHERE action LIKE 'migarden.credential.%'"
                    )
                    == 1
                )
                await app.execute("UPDATE microsched.migarden_zone SET unidentified_execution=true")
                await app.execute(script("revoke", installed))
                revoked = await state()
                rotate = script("issue", revoked, "e" * 64)
                with pytest.raises(asyncpg.RaiseError, match="unresolved execution"):
                    await app.execute(rotate)
                await app.execute("ROLLBACK")
                assert await app.fetchval(
                    "SELECT unidentified_execution FROM microsched.migarden_zone"
                )
                # Restore only the deliberately injected synthetic oracle condition.
                await app.execute(
                    "UPDATE microsched.migarden_zone SET unidentified_execution=false"
                )
                await app.execute(rotate)
                events = await app.fetch(
                    "SELECT action,payload FROM microsched.audit_log "
                    "WHERE action LIKE 'migarden.credential.%' ORDER BY created_at,id"
                )
                assert [row["action"] for row in events] == [
                    "migarden.credential.issue",
                    "migarden.credential.revoke",
                    "migarden.credential.issue",
                ]
                assert all(raw not in row["payload"] for row in events)
                assert (await state())["token_hash"] == "e" * 64
            finally:
                await app.close()
        finally:
            await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=$1 "
                "AND pid<>pg_backend_pid()",
                name,
            )
            await admin.execute(f'DROP DATABASE "{name}"')
            await admin.close()

    asyncio.run(scenario())
