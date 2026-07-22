"""Tests for the liveness and readiness API endpoints."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.main import create_app


def test_healthz_reports_liveness_without_database(monkeypatch) -> None:
    """Liveness answers from the process alone."""
    database_check = AsyncMock(return_value="up")
    monkeypatch.setattr("app.web.routers.health.check_database", database_check)
    client = TestClient(create_app())

    response = client.get("/api/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_healthz_never_queries_the_database(monkeypatch) -> None:
    """Guard the Neon CU-hr budget, which no other test can see.

    Fly probes this path every 30s while Neon autosuspends after 5 minutes idle, so
    a single query here is the difference between a database that sleeps and one
    billed around the clock until the free allowance runs out and the compute is
    suspended mid-month. The regression is invisible - nothing errors, nothing slows
    down, the bill just arrives as an outage two weeks later - so it is asserted
    here rather than left to review.
    """
    database_check = AsyncMock(return_value="up")
    monkeypatch.setattr("app.web.routers.health.check_database", database_check)
    client = TestClient(create_app())

    client.get("/api/healthz")

    database_check.assert_not_awaited()


def test_readyz_reports_database_reachability(monkeypatch) -> None:
    """Readiness spends the query that liveness refuses to."""
    database_check = AsyncMock(return_value="up")
    monkeypatch.setattr("app.web.routers.health.check_database", database_check)
    client = TestClient(create_app())

    response = client.get("/api/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0", "db": "up"}
    database_check.assert_awaited_once_with()


def test_readyz_stays_200_when_database_is_down(monkeypatch) -> None:
    """A database outage is reported in the body, never as a status code.

    Returning 503 would invite exactly one catastrophic misconfiguration: pointing
    the Fly health check at this path, which would turn every Neon autosuspend into
    a machine restart loop.
    """
    monkeypatch.setattr("app.web.routers.health.check_database", AsyncMock(return_value="down"))
    client = TestClient(create_app())

    response = client.get("/api/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["db"] == "down"
