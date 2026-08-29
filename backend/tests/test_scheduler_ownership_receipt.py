"""Unit tests for the one-shot, privacy-safe scheduler ownership receipt."""

from datetime import UTC, datetime

import pytest

from app.core.cron_timer import (
    SCHEDULER_ADVISORY_LOCK_KEY,
    SCHEDULER_ADVISORY_LOCK_NAMESPACE,
    SCHEDULER_ADVISORY_LOCK_REF,
)
from scripts import scheduler_ownership_receipt as receipt_module


@pytest.mark.anyio
async def test_collect_receipt_counts_only_the_named_advisory_lock(monkeypatch):
    """The receipt must not expose a URL, PID, or any scheduler subject identity."""

    class Connection:
        def __init__(self):
            self.closed = False
            self.query = None
            self.arguments = None

        async def fetchval(self, query, *arguments):
            self.query = query
            self.arguments = arguments
            return 1

        async def close(self):
            self.closed = True

    connection = Connection()

    async def connect(database_url):
        assert "password" not in database_url
        return connection

    monkeypatch.setattr(receipt_module.asyncpg, "connect", connect)
    observed_at = datetime(2026, 8, 28, 1, 2, 3, tzinfo=UTC)

    receipt = await receipt_module.collect_receipt(
        "postgresql://microsched@localhost:5432/microsched",
        observed_at=observed_at,
        commit="c5f6530f4dc972999ef6bc53458d32f28c8b5583",
    )

    assert "pg_locks" in connection.query
    assert "current_database()" in connection.query
    assert "mode = 'ExclusiveLock'" in connection.query
    assert "objsubid = 2" in connection.query
    assert "granted" in connection.query
    assert connection.arguments == (
        SCHEDULER_ADVISORY_LOCK_NAMESPACE,
        SCHEDULER_ADVISORY_LOCK_KEY,
    )
    assert connection.closed is True
    assert receipt == {
        "commit": "c5f6530f4dc972999ef6bc53458d32f28c8b5583",
        "observed_at": "2026-08-28T01:02:03Z",
        "scheduler_state": "observed",
        "lock_ref": SCHEDULER_ADVISORY_LOCK_REF,
        "holder_count": 1,
    }


@pytest.mark.parametrize(
    "commit",
    (
        "unknown",
        " unknown ",
        "",
        " \t\n",
        "c5f6530f4dc972999ef6bc53458d32f28c8b558",
        "c5f6530f4dc972999ef6bc53458d32f28c8b55830",
        "C5F6530F4DC972999EF6BC53458D32F28C8B5583",
        "c5f6530f4dc972999ef6bc53458d32f28c8b558g",
        " c5f6530f4dc972999ef6bc53458d32f28c8b5583",
        "c5f6530f4dc972999ef6bc53458d32f28c8b5583 ",
    ),
)
def test_main_rejects_unusable_commit_without_connecting(monkeypatch, capsys, commit):
    """A receipt without an exact deployed commit cannot be used as evidence."""
    monkeypatch.setattr(
        receipt_module.os,
        "environ",
        {"DATABASE_URL": "postgresql://fixture", "GIT_SHA": commit},
    )
    monkeypatch.setattr(
        receipt_module.asyncpg,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("unknown commit must not connect"),
    )

    assert receipt_module.main() == 1
    assert capsys.readouterr().err == "error_type=RuntimeError\n"


@pytest.mark.anyio
async def test_collect_receipt_rejects_invalid_oid_before_connecting(monkeypatch):
    """The callable API preserves the same pre-connect immutable-ID guard."""
    monkeypatch.setattr(
        receipt_module.asyncpg,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("invalid commit must not connect"),
    )

    with pytest.raises(RuntimeError, match="40-character lowercase"):
        await receipt_module.collect_receipt(
            "postgresql://fixture",
            observed_at=datetime(2026, 8, 28, tzinfo=UTC),
            commit="not-an-oid",
        )
