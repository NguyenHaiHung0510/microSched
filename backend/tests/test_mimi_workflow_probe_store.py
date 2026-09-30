import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.agent.workflow_probe.contracts import ProbeBlocked, Record
from app.agent.workflow_probe.store import PgFrameStore, local_probe_dsn
from app.core import crypto


@pytest.mark.parametrize(
    "value",
    [
        "postgresql://microsched_app@remote.example:5432/microsched_p1ca_068",
        "postgresql://microsched_app@127.0.0.1:55466/microsched_p1ca_066",
        "postgresql://postgres@127.0.0.1:55466/microsched_p1ca_068",
        "postgresql://microsched_app@127.0.0.1:55466/microsched_p1ca_068?host=remote.example",
    ],
)
def test_probe_store_rejects_wrong_host_database_role_or_host_override(value):
    with pytest.raises(ProbeBlocked, match="local_probe_database_required"):
        local_probe_dsn(value)


def test_record_storage_budget_blocks_before_crypto_or_connection(monkeypatch):
    def forbidden_crypto():
        raise AssertionError("record_budget_guard_was_bypassed")

    monkeypatch.setattr(
        "app.agent.workflow_probe.store.create_wrapped_dek", forbidden_crypto
    )
    store = PgFrameStore("postgresql://microsched_app@127.0.0.1:55466/microsched_p1ca_068")
    now = datetime.now(UTC)
    with pytest.raises(ProbeBlocked, match="frame_budget_exceeded"):
        asyncio.run(
            store.create(
                uuid4(),
                owner="synthetic-budget",
                generation=1,
                engine="control",
                content={},
                now=now,
                expires_at=now + timedelta(hours=24),
                records=(Record("synthetic-record", 1, "x" * 65536),),
            )
        )


@pytest.mark.pg
def test_pg_frame_cipher_owner_cas_and_active_admission(monkeypatch):
    value = os.environ.get("MIMI_WORKFLOW_PROBE_APP_URL")
    if not value:
        pytest.skip("dedicated local 068 app URL required")
    dsn = local_probe_dsn(value)
    # Replace the lazy cipher, never load .env or inherit a real encryption key.
    monkeypatch.setattr(crypto, "_cipher", lambda: AESGCM(b"s" * 32))

    async def scenario():
        store = PgFrameStore(value)
        ids = [uuid4() for _ in range(9)]
        owner = f"synthetic-{uuid4()}"
        now = datetime.now(UTC)
        connection = await asyncpg.connect(dsn)
        try:
            for run_id in ids[:8]:
                await store.create(
                    run_id,
                    owner=owner,
                    generation=1,
                    engine="control",
                    content={"draft": "PRIVATE_SYNTHETIC_068", "events": [], "provider_calls": []},
                    now=now,
                    expires_at=now + timedelta(hours=24),
                )
            with pytest.raises(ProbeBlocked, match="active_quota_exceeded"):
                await store.create(
                    ids[8],
                    owner=owner,
                    generation=1,
                    engine="control",
                    content={},
                    now=now,
                    expires_at=now + timedelta(hours=24),
                )
            first = await store.load(ids[0], owner=owner)
            assert first.content["draft"] == "PRIVATE_SYNTHETIC_068"
            with pytest.raises(ProbeBlocked, match="owned_run_not_found"):
                await store.load(ids[0], owner="foreign-synthetic-owner")
            updated = await store.save(first, phase="direction", content=first.content)
            assert updated.revision == 1
            with pytest.raises(ProbeBlocked, match="stale_frame_revision"):
                await store.save(first, phase="execute", content=first.content)
            row = await connection.fetchrow(
                "SELECT wrapped_dek,content FROM mimi_probe_068.run WHERE id=$1", ids[0]
            )
            assert row["wrapped_dek"].startswith("enc:v1:")
            assert row["content"].startswith("mimi:v1:")
            assert "PRIVATE_SYNTHETIC_068" not in row["content"]
            # Ciphertext relocation to a different frame revision must fail closed.
            await connection.execute("UPDATE mimi_probe_068.run SET revision=2 WHERE id=$1", ids[0])
            with pytest.raises(InvalidTag):
                await store.load(ids[0], owner=owner)
        finally:
            # Exact generated IDs only; no shared fixture/global table deletion.
            await connection.execute("DELETE FROM mimi_probe_068.run WHERE id=ANY($1::uuid[])", ids)
            await connection.close()

    asyncio.run(scenario())
