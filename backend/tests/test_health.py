"""Tests for the health API endpoint."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_healthz_returns_service_status() -> None:
    """The health endpoint exposes the running application version."""
    client = TestClient(create_app())

    response = client.get("/api/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
