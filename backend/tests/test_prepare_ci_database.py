"""Fail-closed guards for the disposable PostgreSQL role bootstrap."""

import sys
from types import SimpleNamespace

import pytest

from scripts import prepare_ci_database


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
