"""Tests for the health API endpoint."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.main import create_app


def test_healthz_returns_service_and_database_status(monkeypatch) -> None:
    """The health endpoint exposes process and database status independently."""
    database_check = AsyncMock(return_value="up")
    monkeypatch.setattr("app.web.routers.health.check_database", database_check)
    client = TestClient(create_app())

    response = client.get("/api/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0", "db": "up"}
    database_check.assert_awaited_once_with()


def test_healthz_stays_up_when_database_is_down(monkeypatch) -> None:
    """A database outage is reported without failing the Fly process health check."""
    monkeypatch.setattr("app.web.routers.health.check_database", AsyncMock(return_value="down"))
    client = TestClient(create_app())

    response = client.get("/api/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["db"] == "down"
