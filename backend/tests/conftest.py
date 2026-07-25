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
    damage. Set ``ALLOW_REMOTE_PG_TESTS=1`` to override deliberately.
"""

import os

import pytest
from sqlalchemy.engine import make_url

from app.core.database_urls import asyncpg_dsn

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
    if host not in EPHEMERAL_HOSTS and os.environ.get("ALLOW_REMOTE_PG_TESTS") != "1":
        pytest.fail(
            f"refusing to run destructive DB-backed tests against non-local host {host!r}. "
            "These tests delete rows and downgrade the schema; point NEON_MIGRATOR_URL at a "
            "throwaway Postgres, or set ALLOW_REMOTE_PG_TESTS=1 if you really mean it.",
            pytrace=False,
        )
    return asyncpg_dsn(url)
