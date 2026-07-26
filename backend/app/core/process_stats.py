"""Read process-level uptime and memory statistics.

Unavailable operating-system observations return None and must never prevent the
heartbeat endpoint from responding 200.
"""

from __future__ import annotations

from datetime import UTC, datetime

_PROCESS_STARTED_AT = datetime.now(UTC)
_PROC_STATUS_PATH = "/proc/self/status"
_PROC_MEMINFO_PATH = "/proc/meminfo"
_CGROUP_V2_MEMORY_MAX_PATH = "/sys/fs/cgroup/memory.max"
_CGROUP_V1_MEMORY_LIMIT_PATH = "/sys/fs/cgroup/memory/memory.limit_in_bytes"


def read_uptime_s(now: datetime | None = None) -> int:
    """Return wall-clock process age in seconds, including time spent suspended."""
    elapsed = (now or datetime.now(UTC)) - _PROCESS_STARTED_AT
    return max(0, int(elapsed.total_seconds()))


def read_rss_kb(path: str = _PROC_STATUS_PATH) -> int | None:
    """Return the current Resident Set Size in kB, or None when unavailable.

    Reads ``VmRSS`` from ``path`` (default ``/proc/self/status``).  The value is
    returned **as-is** — ``/proc`` already reports kB, so no unit conversion is
    applied.

    Returns ``None`` (never raises) when:
    * the file does not exist or cannot be read,
    * the file does not contain a ``VmRSS:`` line, or
    * the numeric value cannot be parsed.
    """
    try:
        with open(path) as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    # Expected format: "VmRSS:   51234 kB"
                    return int(parts[1])
    except OSError, ValueError, IndexError:
        return None
    # No VmRSS line found.
    return None


def _read_cgroup_limit_kb(paths: tuple[str, ...]) -> int | None:
    for path in paths:
        try:
            with open(path) as file:
                raw_value = file.read().strip()
            if raw_value == "max":
                continue
            value_bytes = int(raw_value)
            if value_bytes > 0:
                return value_bytes // 1024
        except OSError, ValueError:
            continue
    return None


def _read_proc_mem_total_kb(path: str) -> int | None:
    try:
        with open(path) as file:
            for line in file:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    return int(parts[1])
    except OSError, ValueError, IndexError:
        return None
    return None


def read_mem_total_kb(
    *,
    cgroup_v2_path: str = _CGROUP_V2_MEMORY_MAX_PATH,
    cgroup_v1_path: str = _CGROUP_V1_MEMORY_LIMIT_PATH,
    meminfo_path: str = _PROC_MEMINFO_PATH,
) -> int | None:
    """Return the smaller readable cgroup or /proc memory total in kB."""
    readings = [
        reading
        for reading in (
            _read_cgroup_limit_kb((cgroup_v2_path, cgroup_v1_path)),
            _read_proc_mem_total_kb(meminfo_path),
        )
        if reading is not None
    ]
    return min(readings) if readings else None


def calculate_rss_pct(rss_kb: int | None, mem_total_kb: int | None) -> float | None:
    """Return RSS as a percentage of available memory, rounded to one decimal."""
    if rss_kb is None or mem_total_kb is None or mem_total_kb <= 0:
        return None
    return round(rss_kb / mem_total_kb * 100, 1)


def restart_advised(rss_pct: float | None) -> bool | None:
    """Recommend a restart only when measured RSS reaches 90 percent."""
    return None if rss_pct is None else rss_pct >= 90
