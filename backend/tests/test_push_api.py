"""Tests for Web Push subscription endpoints and endpoint validation."""

import httpx
import pytest

from app.domain.push import validate_push_endpoint
from app.main import create_app


def test_validate_push_endpoint_ssrf_guard():
    """Verify validate_push_endpoint rejects non-HTTPS and SSRF target URLs."""
    # Valid HTTPS push service endpoints
    assert validate_push_endpoint("https://fcm.googleapis.com/fcm/send/foo") is True
    assert validate_push_endpoint("https://updates.push.services.mozilla.com/wpush/v2/bar") is True

    # Invalid schemes
    assert validate_push_endpoint("http://fcm.googleapis.com/fcm/send/foo") is False
    assert validate_push_endpoint("ftp://example.com/push") is False
    assert validate_push_endpoint("javascript:alert(1)") is False

    # Loopback / internal IPs
    assert validate_push_endpoint("https://localhost/push") is False
    assert validate_push_endpoint("https://localhost.localdomain/push") is False
    assert validate_push_endpoint("https://127.0.0.1/push") is False
    assert validate_push_endpoint("https://10.0.0.1/push") is False
    assert validate_push_endpoint("https://192.168.1.1/push") is False
    assert validate_push_endpoint("https://169.254.169.254/latest/meta-data") is False
    assert validate_push_endpoint("https://::1/push") is False


@pytest.mark.anyio
async def test_vapid_public_key_unauthenticated():
    """Verify unauthenticated calls to GET /api/push/vapid-public-key return 401."""
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/push/vapid-public-key")
        assert res.status_code == 401
