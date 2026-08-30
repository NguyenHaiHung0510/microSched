"""Fail-closed guards for the disposable PostgreSQL role bootstrap."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import prepare_ci_database


class _FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement: str) -> None:
        self.statements.append(statement)

    async def fetchval(self, statement: str, *args: object) -> object:
        if "pg_database" in statement:
            return True
        if "quote_literal" in statement:
            return f"'{args[0]}'"
        raise AssertionError(f"unexpected fetchval: {statement}")

    async def close(self) -> None:
        return None


def test_bootstrap_rejects_missing_explicit_synthetic_inputs(monkeypatch) -> None:
    """A legacy dotenv target must never receive fallback CI role passwords."""
    for name in ("CI_PG_BOOTSTRAP_URL", "CI_MIGRATOR_PASSWORD", "CI_APP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sys, "argv", ["prepare_ci_database"])
    monkeypatch.setattr(
        prepare_ci_database,
        "PrepareSettings",
        lambda: SimpleNamespace(neon_migrator_url="postgresql://legacy-target"),
        raising=False,
    )

    def close_without_running(coroutine) -> None:
        coroutine.close()

    monkeypatch.setattr(prepare_ci_database.asyncio, "run", close_without_running)

    with pytest.raises(SystemExit, match="explicit synthetic bootstrap inputs"):
        prepare_ci_database.main()


def test_bootstrap_preserves_public_usage_for_vector_resolution(monkeypatch) -> None:
    """The migrator must resolve the public pgvector type without gaining public DDL."""
    service = _FakeConnection()
    owner = _FakeConnection()
    migrator = _FakeConnection()
    connections = iter((service, owner, migrator))

    async def fake_connect(*_args: object, **_kwargs: object) -> _FakeConnection:
        return next(connections)

    monkeypatch.setattr(prepare_ci_database.asyncpg, "connect", fake_connect)

    prepare_ci_database.asyncio.run(
        prepare_ci_database.prepare(
            bootstrap_url="postgresql://postgres:postgres@localhost:5432/microsched_ci",
            migrator_password="synthetic-migrator",
            app_password="synthetic-app",
        )
    )

    assert "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public" in owner.statements
    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in owner.statements
    assert "REVOKE ALL ON SCHEMA public FROM PUBLIC" not in owner.statements


def test_pg_suite_keeps_bootstrap_owner_for_legacy_database_rehearsals() -> None:
    """Legacy PG tests create fixture databases; only migration steps use the split role."""
    workflow = (Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert (
        "      - run: uv run pytest -m pg\n"
        "        env:\n"
        "          NEON_MIGRATOR_URL: ${{ env.CI_PG_BOOTSTRAP_URL }}"
    ) in workflow
