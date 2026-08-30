"""Guard contracts for the destructive prepare_qa_branch script."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.core.settings import get_settings
from scripts.prepare_qa_branch import (  # noqa: E402
    main,
    scrub_branch_data,
    validate_declared_target,
)

PROD_URL = "postgresql://u:p@ep-prod-fake.example.neon.tech/db"
DEV_URL = "postgresql://u:p@ep-dev-fake-pooler.example.neon.tech/db"


def _set_target_env(monkeypatch, *, database_url: str, branch_key: str) -> None:
    """Set fake hosts without reading or touching a real target."""
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("NEON_DEVELOP_BRANCH_KEY", branch_key)
    # The real .env always declares the owner reference next to the prod URL;
    # the guard needs it to recognize which remote hosts are production.
    monkeypatch.setenv("NEON_OWNER_URL", PROD_URL)
    monkeypatch.delenv("ALLOW_PROD_DB_IN_LOCAL", raising=False)
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", "AAAA")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "x" * 32)
    get_settings.cache_clear()


def test_main_without_exact_authority_args_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["prepare_qa_branch.py"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_local_scrub_of_declared_branch_is_allowed(monkeypatch) -> None:
    """The declared develop target passes the host guard without connecting."""
    _set_target_env(monkeypatch, database_url=PROD_URL, branch_key=DEV_URL)
    validate_declared_target(DEV_URL, DEV_URL)
    get_settings.cache_clear()


def test_scrub_refuses_the_raw_production_host(monkeypatch) -> None:
    """A prod-host target must be rejected before any network attempt."""
    _set_target_env(monkeypatch, database_url=PROD_URL, branch_key=PROD_URL)
    with pytest.raises(ValueError, match="production host"):
        validate_declared_target(PROD_URL, PROD_URL)
    get_settings.cache_clear()


def test_scrub_delivery_truncate_is_pre_and_post_0012_safe(monkeypatch) -> None:
    """Optional batch tables are included only when to_regclass says they exist."""

    class Transaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class FakeConnection:
        def __init__(self, *, post_0012: bool):
            self.post_0012 = post_0012
            self.executed: list[str] = []

        def transaction(self):
            return Transaction()

        async def fetch(self, query, *_args):
            if "FROM microsched" in query:
                return []
            return []

        async def fetchval(self, query, *_args):
            if "to_regclass" in query:
                return "present" if self.post_0012 else None
            return None

        async def execute(self, query, *_args):
            self.executed.append(query)

        async def close(self):
            return None

    async def run_case(post_0012: bool) -> str:
        connection = FakeConnection(post_0012=post_0012)

        async def fake_connect(*_args, **_kwargs):
            return connection

        monkeypatch.setattr("scripts.prepare_qa_branch.asyncpg.connect", fake_connect)
        monkeypatch.setattr("scripts.prepare_qa_branch.hash_pin", lambda _pin: "hash")
        await scrub_branch_data(
            dsn="postgresql://fixture",
            prod_key_b64="AAAA",
            qa_key_b64="AAAA",
            test_pin="123456",
            salt="fixture",
        )
        return next(query for query in connection.executed if query.startswith("TRUNCATE TABLE"))

    pre = asyncio.run(run_case(False))
    post = asyncio.run(run_case(True))
    assert "tracker_reminder_batch" not in pre
    assert "tracker_reminder_batch_item" not in pre
    assert "microsched.tracker_reminder_batch_item" in post
    assert "microsched.tracker_reminder_batch" in post
