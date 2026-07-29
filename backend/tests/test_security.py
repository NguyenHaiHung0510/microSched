"""Tests for security enhancements."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_security_headers_are_present() -> None:
    """All responses must carry basic defense-in-depth security headers."""
    client = TestClient(create_app())

    # We use a known endpoint to check for headers, like /api/healthz
    response = client.get("/api/healthz")

    assert response.status_code == 200
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert (
        response.headers.get("Strict-Transport-Security") == "max-age=31536000; includeSubDomains"
    )
