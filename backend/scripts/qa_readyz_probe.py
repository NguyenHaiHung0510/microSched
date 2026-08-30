"""Probe local readyz from inside the candidate container without external networking."""

from __future__ import annotations

import argparse
import errno
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any


class ReadyzProbeError(RuntimeError):
    """A redacted, stable readyz failure code."""


class _TransientStartup(RuntimeError):
    pass


def _is_connection_refused(error: urllib.error.URLError) -> bool:
    reason = error.reason
    return isinstance(reason, ConnectionRefusedError) or (
        isinstance(reason, OSError) and reason.errno == errno.ECONNREFUSED
    )


def _read_readyz_once(
    *,
    url: str,
    expected_commit: str,
    request_timeout: float,
    open_fn: Callable[..., Any],
) -> None:
    try:
        response_context = open_fn(url, timeout=request_timeout)
    except urllib.error.HTTPError as error:
        if error.code == 503:
            raise _TransientStartup from None
        raise ReadyzProbeError("FAIL_STATUS_CODE") from None
    except urllib.error.URLError as error:
        if _is_connection_refused(error):
            raise _TransientStartup from None
        raise ReadyzProbeError("FAIL_CONNECTION") from None

    with response_context as response:
        if response.status == 503:
            raise _TransientStartup
        if response.status != 200:
            raise ReadyzProbeError("FAIL_STATUS_CODE")
        try:
            payload = json.load(response)
        except TypeError, ValueError, UnicodeError:
            raise ReadyzProbeError("FAIL_PAYLOAD") from None
    if not isinstance(payload, dict):
        raise ReadyzProbeError("FAIL_PAYLOAD")
    if payload.get("status") != "ok" or payload.get("db") != "up":
        raise ReadyzProbeError("FAIL_HEALTH")
    if payload.get("commit") != expected_commit:
        raise ReadyzProbeError("FAIL_COMMIT")


def wait_for_readyz(
    *,
    expected_commit: str,
    url: str,
    timeout_seconds: float,
    open_fn: Callable[..., Any] = urllib.request.urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> None:
    """Wait at most 90s, retrying only refusal or explicit HTTP 503 startup states."""
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise ReadyzProbeError("FAIL_EXPECTED_COMMIT")
    if timeout_seconds <= 0 or timeout_seconds > 90:
        raise ReadyzProbeError("FAIL_TIMEOUT_BOUND")
    deadline = monotonic_fn() + timeout_seconds
    while True:
        remaining = deadline - monotonic_fn()
        if remaining <= 0:
            raise ReadyzProbeError("FAIL_STARTUP_TIMEOUT")
        try:
            _read_readyz_once(
                url=url,
                expected_commit=expected_commit,
                request_timeout=min(10.0, remaining),
                open_fn=open_fn,
            )
            return
        except _TransientStartup:
            remaining = deadline - monotonic_fn()
            if remaining <= 0:
                raise ReadyzProbeError("FAIL_STARTUP_TIMEOUT") from None
            sleep_fn(min(1.0, remaining))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/readyz")
    parser.add_argument("--timeout-seconds", type=float, default=90)
    args = parser.parse_args()
    try:
        wait_for_readyz(
            expected_commit=args.expected_commit,
            url=args.url,
            timeout_seconds=args.timeout_seconds,
        )
    except ReadyzProbeError as error:
        raise SystemExit(f"readyz_probe={error}") from None
    print("readyz_probe=PASS")
    print(f"commit={args.expected_commit}")


if __name__ == "__main__":
    main()
