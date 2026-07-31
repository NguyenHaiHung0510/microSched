"""Tests for RSS reading and the cron heartbeat endpoint (spec 014 §2.3)."""

import textwrap
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

import app.core.process_stats as process_stats
from app.core.process_stats import (
    calculate_rss_pct,
    read_mem_total_kb,
    read_rss_kb,
    read_uptime_s,
    restart_advised,
)
from app.core.settings import get_settings
from app.main import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CRON_TOKEN = "test-cron-token-used-only-by-tests"
_HEARTBEAT_KEYS = {
    "status",
    "rss_kb",
    "uptime_s",
    "mem_total_kb",
    "rss_pct",
    "restart_advised",
}


def _make_client(
    monkeypatch,
    *,
    rss_kb_return: int | None = 42_000,
    uptime_s_return: int = 3_600,
    mem_total_kb_return: int | None = 256_000,
) -> TestClient:
    """Build a TestClient with auth and every OS-dependent reading patched."""
    monkeypatch.setenv("OAUTH_STATE_SECRET", "state-secret-used-only-by-tests")
    monkeypatch.setenv("CRON_TOKEN", _CRON_TOKEN)
    get_settings.cache_clear()
    monkeypatch.setattr("app.web.routers.cron.read_rss_kb", lambda: rss_kb_return)
    monkeypatch.setattr("app.web.routers.cron.read_uptime_s", lambda: uptime_s_return)
    monkeypatch.setattr("app.web.routers.cron.read_mem_total_kb", lambda: mem_total_kb_return)
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


def test_uptime_uses_process_import_time_and_wall_clock(monkeypatch) -> None:
    """Process age is anchored once at module import rather than per app instance."""
    started_at = datetime(2026, 7, 26, 1, 2, 3, tzinfo=UTC)
    monkeypatch.setattr(process_stats, "_PROCESS_STARTED_AT", started_at)

    assert read_uptime_s(now=started_at + timedelta(seconds=123)) == 123


def test_mem_total_uses_smaller_cgroup_or_proc_reading(tmp_path) -> None:
    """A host-wide MemTotal cannot override a smaller container limit."""
    cgroup_v2 = tmp_path / "memory.max"
    cgroup_v2.write_text(str(256 * 1024))
    cgroup_v1 = tmp_path / "memory.limit_in_bytes"
    cgroup_v1.write_text(str(1024 * 1024))
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       512 kB\n")

    assert (
        read_mem_total_kb(
            cgroup_v2_path=str(cgroup_v2),
            cgroup_v1_path=str(cgroup_v1),
            meminfo_path=str(meminfo),
        )
        == 256
    )


def test_rss_percentage_and_restart_threshold() -> None:
    """Percent calculation is rounded once and the threshold is inclusive."""
    assert calculate_rss_pct(899, 1000) == 89.9
    assert restart_advised(89.9) is False
    assert restart_advised(90.0) is True
    assert restart_advised(90.1) is True
    assert calculate_rss_pct(42, None) is None
    assert restart_advised(None) is None


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
    assert set(body) == _HEARTBEAT_KEYS
    assert body["uptime_s"] == 3_600
    assert body["mem_total_kb"] == 256_000
    assert body["rss_pct"] == 20.0
    assert body["restart_advised"] is False


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
    assert body["rss_pct"] is None
    assert body["restart_advised"] is None


def test_heartbeat_returns_200_when_mem_total_is_unavailable(monkeypatch) -> None:
    """Missing total memory disables the derived fields without failing heartbeat."""
    client = _make_client(monkeypatch, mem_total_kb_return=None)

    response = client.post(
        "/api/cron/heartbeat",
        headers={"Authorization": f"Bearer {_CRON_TOKEN}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == _HEARTBEAT_KEYS
    assert body["rss_pct"] is None
    assert body["restart_advised"] is None


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
