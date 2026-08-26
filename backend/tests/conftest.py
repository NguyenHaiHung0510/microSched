"""Shared fixtures for the DB-backed (``@pytest.mark.pg``) test lane.

The heavy invariants in this project - the private-ciphertext CHECKs and the 008
privacy triggers - are only real against a live Postgres, so those tests connect to
the schema-owner URL (``NEON_MIGRATOR_URL``) rather than an in-memory double
(spec §2.7). CI runs them in the Migration QA job, which already stands up a
``pgvector/pgvector:pg18`` service and applies every migration to head.

Three guards, on purpose:

  * the ``pg`` marker selects the lane - the ``backend`` CI job runs ``-m "not pg"``
    (fast, no database), Migration QA runs ``-m pg`` (against the migrated service);
  * ``pg_dsn`` skips rather than errors when no database URL is present, so a
    developer running the whole suite locally without Docker gets skips, not a wall
    of connection failures;
  * ``pg_dsn`` REFUSES a non-local host. ``NEON_MIGRATOR_URL`` is the same variable
    the owner exports from ``.env`` to apply migrations to the real Neon database by
    hand, so an ordinary ``pytest -m pg`` on a dev machine would otherwise DELETE
    rows and - via test_task_item_trigger.py's round-trip case - run
    ``alembic downgrade`` against production, stripping the privacy triggers. CI
    points the variable at the localhost pgvector service, so host-based refusal
    costs nothing there and turns the accident into a loud red instead of silent
    damage. Set ``NEON_QA_BRANCH=1`` (with a verified QA branch host) or
    ``ALLOW_REMOTE_PG_TESTS=1`` to override deliberately.
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.engine import make_url

from app.core.database_urls import asyncpg_dsn
from app.domain.models import AuthSession

# Hosts that can only ever be a throwaway database: the CI service container or a
# local Docker Postgres. Anything else (Neon, staging) is assumed to hold real data.
EPHEMERAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres", "db"})


@pytest.fixture
def pg_dsn() -> str:
    """Return a direct asyncpg DSN for the schema-owner URL, or skip without one."""
    url = os.environ.get("NEON_MIGRATOR_URL")
    if not url:
        pytest.skip(
            "NEON_MIGRATOR_URL is unset; DB-backed (@pytest.mark.pg) tests need a live Postgres"
        )
    host = (make_url(url).host or "").lower()
    is_qa_branch = (
        os.environ.get("NEON_QA_BRANCH") == "1"
        and ("qa" in host or "test" in host or host.startswith("ep-qa-"))
        and "prod" not in host
    )
    if (
        host not in EPHEMERAL_HOSTS
        and not is_qa_branch
        and os.environ.get("ALLOW_REMOTE_PG_TESTS") != "1"
    ):
        pytest.fail(
            f"refusing to run destructive DB-backed tests against non-local host {host!r}. "
            "These tests delete rows and downgrade the schema; point NEON_MIGRATOR_URL at a "
            "throwaway Postgres, set NEON_QA_BRANCH=1 for an ephemeral QA branch, "
            "or set ALLOW_REMOTE_PG_TESTS=1 if you really mean it.",
            pytrace=False,
        )
    return asyncpg_dsn(url)


@pytest.fixture
def seed_auth_session(pg_dsn: str):
    """Insert and return a real session row for APIs that update it by ID."""

    async def seed() -> AuthSession:
        now = datetime.now(UTC)
        conn = await asyncpg.connect(pg_dsn)
        try:
            await conn.execute(
                "DELETE FROM microsched.app_setting "
                "WHERE key IN ('private_pin', 'private_unlock_throttle')"
            )
            row = await conn.fetchrow(
                "INSERT INTO microsched.session "
                "(token_hash, user_email, last_seen_at, expires_at) "
                "VALUES ($1, $2, $3, $4) "
                "RETURNING id, token_hash, user_email, created_at, updated_at, "
                "last_seen_at, expires_at, private_until",
                f"private-api-test-{uuid4()}",
                "owner@example.test",
                now,
                now + timedelta(days=1),
            )
            return AuthSession(**dict(row))
        finally:
            await conn.close()

    session = asyncio.run(seed())
    yield session

    async def cleanup() -> None:
        conn = await asyncpg.connect(pg_dsn)
        try:
            await conn.execute("DELETE FROM microsched.session WHERE id = $1", session.id)
            await conn.execute(
                "DELETE FROM microsched.app_setting "
                "WHERE key IN ('private_pin', 'private_unlock_throttle')"
            )
        finally:
            await conn.close()

    asyncio.run(cleanup())
