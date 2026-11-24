"""Prepared production SQL is rehearsed only in a named throwaway local database."""

import asyncio
import hashlib
import json
import os
import secrets
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest
from psycopg.errors import RaiseException
from sqlalchemy.engine import make_url

from app.domain.migarden.credentials import digest
from scripts import prepare_migarden_commission as commission
from scripts.bootstrap_neon import bootstrap
from scripts.prepare_migarden_commission import transaction

pytestmark = pytest.mark.pg


@asynccontextmanager
async def commission_cell(pg_dsn):
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
            yield app, app_url, name
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


def test_prepared_binding_forward_rehearsal_cas_revoke_history_and_unknown_guard(pg_dsn):
    async def scenario():
        async with commission_cell(pg_dsn) as (app, _, name):

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
            assert await app.fetchval("SELECT unidentified_execution FROM microsched.migarden_zone")
            # Restore only the deliberately injected synthetic oracle condition.
            await app.execute("UPDATE microsched.migarden_zone SET unidentified_execution=false")
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

    asyncio.run(scenario())


def test_pg_groupfix_qa_commission_actual_target_and_hash_only(pg_dsn, tmp_path, monkeypatch):
    async def scenario():
        async with commission_cell(pg_dsn) as (app, app_url, name):
            target = make_url(app_url)
            # Pin IPv4 localhost in the common CI/author cell; retain IPv6 loopback if named.
            host = "::1" if target.host == "::1" else "localhost"
            state = tmp_path / "expected.json"
            state.write_text(json.dumps(dict.fromkeys(commission.STATE_KEYS)), encoding="ascii")
            packet = tmp_path / ".local" / "packet"
            monkeypatch.setattr(commission, "CHECKOUT", tmp_path)
            monkeypatch.setenv(
                "MIGARDEN_COMMISSION_DATABASE_URL",
                target.set(host=host).render_as_string(hide_password=False),
            )
            for key in commission.QA_LIBPQ_OVERRIDES:
                monkeypatch.delenv(key, raising=False)
            monkeypatch.setenv("PGPORT", "1")
            monkeypatch.setenv("PGHOST", "not-local.example.invalid")
            monkeypatch.setenv("PGDATABASE", "not_n01")
            commission.prepare(
                SimpleNamespace(
                    operation="issue",
                    environment="qa",
                    device_id="qa-groupfix-synthetic",
                    expected_database=name,
                    expected_host=host,
                    expected_port=target.port,
                    expected_state_file=state,
                    output_dir=packet,
                )
            )
            token = (packet / "device.token").read_text(encoding="ascii").strip()
            args = SimpleNamespace(plan_dir=packet)
            await asyncio.to_thread(commission.apply_plan, args)
            with pytest.raises(RaiseException, match="CAS conflict"):
                await asyncio.to_thread(commission.apply_plan, args)
            bound = await app.fetchrow(
                "SELECT device_id,device_environment,token_hash FROM microsched.migarden_zone"
            )
            assert (bound["device_id"], bound["device_environment"]) == (
                "qa-groupfix-synthetic",
                "qa",
            )
            assert commission.TOKEN.fullmatch(token) and bound["token_hash"] == digest(token)
            assert token not in (packet / "binding.sql").read_text(encoding="ascii")
            assert token not in (packet / "plan.json").read_text(encoding="ascii")
            evidence = await app.fetch(
                "SELECT payload FROM microsched.audit_log WHERE action='migarden.credential.issue'"
            )
            assert len(evidence) == 1 and token not in evidence[0]["payload"]

    asyncio.run(scenario())
