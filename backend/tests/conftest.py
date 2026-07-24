"""Shared fixtures for the DB-backed (``@pytest.mark.pg``) test lane.

The heavy invariants in this project - the private-ciphertext CHECKs and the 008
privacy triggers - are only real against a live Postgres, so those tests connect to
the schema-owner URL (``NEON_MIGRATOR_URL``) rather than an in-memory double
(spec §2.7). CI runs them in the Migration QA job, which already stands up a
``pgvector/pgvector:pg18`` service and applies every migration to head.

Two guards, on purpose:

  * the ``pg`` marker selects the lane - the ``backend`` CI job runs ``-m "not pg"``
    (fast, no database), Migration QA runs ``-m pg`` (against the migrated service);
  * ``pg_dsn`` skips rather than errors when no database URL is present, so a
    developer running the whole suite locally without Docker gets skips, not a wall
    of connection failures.
"""

import os

import pytest

from app.core.database_urls import asyncpg_dsn


@pytest.fixture
def pg_dsn() -> str:
    """Return a direct asyncpg DSN for the schema-owner URL, or skip without one."""
    url = os.environ.get("NEON_MIGRATOR_URL")
    if not url:
        pytest.skip(
            "NEON_MIGRATOR_URL is unset; DB-backed (@pytest.mark.pg) tests need a live Postgres"
        )
    return asyncpg_dsn(url)
