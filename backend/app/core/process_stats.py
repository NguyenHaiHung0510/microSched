"""Read process-level memory statistics from /proc on Linux.

On systems without /proc (Windows, macOS) every function returns None — a missing
observation must never prevent the endpoint from responding 200.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_PROC_STATUS_PATH = "/proc/self/status"


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
