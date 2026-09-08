import gzip

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from app.core.settings import get_settings
from app.main import SPAStaticFiles, create_app


@pytest.fixture
def static_client(tmp_path):
    (tmp_path / "assets").mkdir()
    payload = b"console.log('synthetic static fixture');\n" * 100
    asset = tmp_path / "assets" / "app-AbCd1234.js"
    asset.write_bytes(payload)
    asset.with_suffix(".js.gz").write_bytes(gzip.compress(payload, mtime=0))
    (tmp_path / "index.html").write_text("<html>synthetic shell</html>")
    (tmp_path / "sw.js").write_text("// synthetic worker")
    app = Starlette()
    app.mount("/", SPAStaticFiles(directory=tmp_path, html=True))
    return TestClient(app), payload


def test_hashed_asset_compression_cache_and_conditional_request(static_client):
    client, payload = static_client
    response = client.get("/assets/app-AbCd1234.js", headers={"accept-encoding": "gzip"})
    assert response.content == payload
    assert response.headers["content-encoding"] == "gzip"
    assert "javascript" in response.headers["content-type"]
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["vary"] == "Accept-Encoding"
    cached = client.get(
        "/assets/app-AbCd1234.js",
        headers={"accept-encoding": "gzip", "if-none-match": response.headers["etag"]},
    )
    assert cached.status_code == 304
    assert cached.headers["cache-control"] == response.headers["cache-control"]


@pytest.mark.parametrize("encoding", ["identity", "gzip;q=0, *;q=1", "br", ""])
def test_plain_asset_fallback(static_client, encoding):
    client, payload = static_client
    response = client.get("/assets/app-AbCd1234.js", headers={"accept-encoding": encoding})
    assert response.content == payload
    assert "content-encoding" not in response.headers


def test_shell_worker_missing_asset_and_head(static_client):
    client, _ = static_client
    for path in ("/", "/home", "/sw.js"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"
        assert "content-encoding" not in response.headers
    assert client.get("/assets/missing-AbCd1234.js").status_code == 404
    head = client.head("/assets/app-AbCd1234.js", headers={"accept-encoding": "gzip"})
    assert head.content == b""
    assert head.headers["content-encoding"] == "gzip"


def test_missing_compressed_file_keeps_original_available(static_client, tmp_path):
    client, payload = static_client
    (tmp_path / "assets" / "app-AbCd1234.js.gz").unlink()
    response = client.get("/assets/app-AbCd1234.js", headers={"accept-encoding": "gzip"})
    assert response.status_code == 200
    assert response.content == payload
    assert "content-encoding" not in response.headers


def test_range_request_uses_original_representation(static_client):
    client, payload = static_client
    response = client.get(
        "/assets/app-AbCd1234.js", headers={"accept-encoding": "gzip", "range": "bytes=0-8"}
    )
    assert response.status_code == 206
    assert response.content == payload[:9]
    assert "content-encoding" not in response.headers


def test_api_and_auth_responses_are_not_shared_cached(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ENABLE_INPROCESS_CRON", "false")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        for path, expected in (("/api/me", 401), ("/auth/denied", 403), ("/api/healthz", 200)):
            response = client.get(path)
            assert response.status_code == expected
            assert response.headers["cache-control"] == "no-store"
    finally:
        get_settings.cache_clear()
