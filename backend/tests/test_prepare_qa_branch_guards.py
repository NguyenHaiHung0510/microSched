"""Guard contracts for the destructive prepare_qa_branch script."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.core.settings import get_settings
from scripts.prepare_qa_branch import main  # noqa: E402

PROD_URL = "postgresql://u:p@ep-prod-fake.example.neon.tech/db"
DEV_URL = "postgresql://u:p@ep-dev-fake-pooler.example.neon.tech/db"


def _run_main(monkeypatch, *, database_url: str, branch_key: str):
    """Drive main() with fake hosts so no real network is ever touched."""
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("NEON_DEVELOP_BRANCH_KEY", branch_key)
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", "AAAA")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "x" * 32)
    monkeypatch.setattr(sys, "argv", ["prepare_qa_branch.py"])
    get_settings.cache_clear()
    try:
        main()
    except ValueError as error:
        return error
    finally:
        get_settings.cache_clear()


def test_local_scrub_of_declared_branch_is_allowed(monkeypatch) -> None:
    """The develop target must pass every guard and reach the network layer."""
    # Guards pass, then the fake DNS host fails inside asyncpg - that exact
    # failure point is the receipt that no guard blocked a legitimate target.
    with pytest.raises(OSError) as exc_info:
        _run_main(monkeypatch, database_url=PROD_URL, branch_key=DEV_URL)
    assert "getaddrinfo failed" in str(exc_info.value)


def test_scrub_refuses_the_raw_production_host(monkeypatch) -> None:
    """A prod-host target must be rejected before any network attempt."""
    error = _run_main(monkeypatch, database_url=PROD_URL, branch_key=PROD_URL)
    assert error is not None and "production host" in str(error)
