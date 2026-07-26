"""Tests for RSS reading and the cron heartbeat endpoint (spec 014 §2.3)."""

import textwrap

from fastapi.testclient import TestClient

from app.core.process_stats import read_rss_kb
from app.core.settings import get_settings
from app.main import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CRON_TOKEN = "test-cron-token-used-only-by-tests"


def _make_client(monkeypatch, *, rss_kb_return: int | None = 42_000) -> TestClient:
    """Build a TestClient with CRON_TOKEN set and read_rss_kb patched."""
    monkeypatch.setenv("OAUTH_STATE_SECRET", "state-secret-used-only-by-tests")
    monkeypatch.setenv("CRON_TOKEN", _CRON_TOKEN)
    get_settings.cache_clear()
    monkeypatch.setattr("app.web.routers.cron.read_rss_kb", lambda: rss_kb_return)
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# 1. Parse — fake file with "VmRSS:   51234 kB" → returns 51234
# ---------------------------------------------------------------------------


def test_parse_vmrss_from_fake_file(tmp_path) -> None:
    """A well-formed /proc/self/status entry must yield the integer kB value."""
    fake = tmp_path / "status"
    fake.write_text(
        textwrap.dedent("""\
            Name:\tpython3
            VmPeak:\t  102400 kB
            VmRSS:\t  51234 kB
            VmSize:\t  98765 kB
        """)
    )
    assert read_rss_kb(path=str(fake)) == 51234


# ---------------------------------------------------------------------------
# 2. Missing file → None, no raise
# ---------------------------------------------------------------------------


def test_missing_file_returns_none(tmp_path) -> None:
    """A non-existent path must return None without raising."""
    result = read_rss_kb(path=str(tmp_path / "no_such_file"))
    assert result is None


# ---------------------------------------------------------------------------
# 3. Garbage content → None, no raise
# ---------------------------------------------------------------------------


def test_garbage_content_returns_none(tmp_path) -> None:
    """A file without a VmRSS line (or with unparseable numbers) must return None."""
    fake = tmp_path / "status"
    fake.write_text("this is not a proc status file\nrandom garbage\n")
    assert read_rss_kb(path=str(fake)) is None


# ---------------------------------------------------------------------------
# 4. Endpoint with a reading — 200 + rss_kb is int
# ---------------------------------------------------------------------------


def test_heartbeat_returns_rss_kb_int(monkeypatch) -> None:
    """POST /api/cron/heartbeat with a valid token and available RSS returns an int."""
    client = _make_client(monkeypatch, rss_kb_return=51234)

    response = client.post(
        "/api/cron/heartbeat",
        headers={"Authorization": f"Bearer {_CRON_TOKEN}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["rss_kb"] == 51234
    assert isinstance(body["rss_kb"], int)


# ---------------------------------------------------------------------------
# 5. Endpoint when RSS unavailable — 200 + rss_kb is null
# ---------------------------------------------------------------------------


def test_heartbeat_returns_null_rss_when_unavailable(monkeypatch) -> None:
    """When read_rss_kb returns None the endpoint still returns 200."""
    client = _make_client(monkeypatch, rss_kb_return=None)

    response = client.post(
        "/api/cron/heartbeat",
        headers={"Authorization": f"Bearer {_CRON_TOKEN}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["rss_kb"] is None


# ---------------------------------------------------------------------------
# 6. Auth unchanged — missing/wrong token → 401
# ---------------------------------------------------------------------------


def test_heartbeat_rejects_missing_token(monkeypatch) -> None:
    """No Authorization header must return 401."""
    client = _make_client(monkeypatch)

    response = client.post("/api/cron/heartbeat")

    assert response.status_code == 401


def test_heartbeat_rejects_wrong_token(monkeypatch) -> None:
    """A wrong bearer token must return 401."""
    client = _make_client(monkeypatch)

    response = client.post(
        "/api/cron/heartbeat",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401
