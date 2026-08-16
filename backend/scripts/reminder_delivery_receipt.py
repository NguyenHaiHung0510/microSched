"""One-shot, read-only reminder delivery aggregate for production diagnosis."""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from app.core.database_urls import asyncpg_dsn

PUSH_SUBSCRIPTION_COUNT_QUERY = """
SELECT count(*)::bigint
FROM microsched.push_subscription
"""

DISPATCH_GROUPS_QUERY = """
SELECT
    subject_type AS kind,
    dispatched_on AS occurrence_on,
    status,
    attempt_count,
    count(*)::bigint AS dispatch_count,
    min(created_at) AS earliest_created_at,
    max(created_at) AS latest_created_at,
    min(last_attempt_at) AS earliest_last_attempt_at,
    max(last_attempt_at) AS latest_last_attempt_at,
    count(confirmed_entry_id)::bigint AS confirmed_count
FROM microsched.reminder_dispatch
WHERE
    (created_at BETWEEN $1 AND $2)
    OR (last_attempt_at BETWEEN $1 AND $2)
GROUP BY subject_type, dispatched_on, status, attempt_count
ORDER BY subject_type, dispatched_on, status, attempt_count
"""

_UTC_RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)")


def _utc_rfc3339(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def resolve_window(
    *,
    window_minutes: int | None,
    since: str | None,
    observed_at: datetime,
) -> tuple[datetime, int | None]:
    """Validate mutually exclusive window inputs and return the UTC start."""
    if observed_at.tzinfo is None or observed_at.utcoffset() != timedelta(0):
        raise ValueError("observed_at must be UTC")

    if (window_minutes is None) == (since is None):
        raise ValueError("exactly one window option is required")

    if window_minutes is not None:
        if not 1 <= window_minutes <= 1440:
            raise ValueError("window_minutes outside allowed range")
        return observed_at - timedelta(minutes=window_minutes), window_minutes

    assert since is not None
    if _UTC_RFC3339.fullmatch(since) is None:
        raise ValueError("since must be RFC3339 UTC")
    parsed = datetime.fromisoformat(since.replace("Z", "+00:00"))
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("since must be UTC")
    parsed = parsed.astimezone(UTC)
    if parsed > observed_at:
        raise ValueError("since cannot be in the future")
    if observed_at - parsed > timedelta(hours=24):
        raise ValueError("since is older than 24 hours")
    return parsed, None


def _format_group(row: Any) -> dict[str, object]:
    return {
        "kind": row["kind"],
        "occurrence_on": row["occurrence_on"].isoformat(),
        "status": row["status"],
        "attempt_count": row["attempt_count"],
        "dispatch_count": row["dispatch_count"],
        "earliest_created_at": _utc_rfc3339(row["earliest_created_at"]),
        "latest_created_at": _utc_rfc3339(row["latest_created_at"]),
        "earliest_last_attempt_at": _utc_rfc3339(row["earliest_last_attempt_at"]),
        "latest_last_attempt_at": _utc_rfc3339(row["latest_last_attempt_at"]),
        "confirmed_count": row["confirmed_count"],
    }


async def collect_receipt(
    database_url: str,
    *,
    observed_at: datetime,
    window_started_at: datetime,
    window_minutes: int | None,
    commit: str,
) -> dict[str, object]:
    """Run the two aggregate SELECTs and close the one-shot connection."""
    connection = None
    try:
        connection = await asyncpg.connect(asyncpg_dsn(database_url))
        push_subscription_count = await connection.fetchval(PUSH_SUBSCRIPTION_COUNT_QUERY)
        rows = await connection.fetch(
            DISPATCH_GROUPS_QUERY,
            window_started_at,
            observed_at,
        )
    finally:
        if connection is not None:
            await connection.close()

    return {
        "commit": commit,
        "observed_at": _utc_rfc3339(observed_at),
        "window_started_at": _utc_rfc3339(window_started_at),
        "window_minutes": window_minutes,
        "push_subscription_count": push_subscription_count,
        "dispatch_groups": [_format_group(row) for row in rows],
    }


class _SafeArgumentParser(argparse.ArgumentParser):
    """Reject invalid CLI input without echoing the original argv to stderr."""

    def error(self, message: str) -> None:
        raise ValueError("invalid command arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(description=__doc__)
    window = parser.add_mutually_exclusive_group(required=True)
    window.add_argument("--window-minutes", type=int)
    window.add_argument("--since")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        observed_at = datetime.now(UTC)
        window_started_at, window_minutes = resolve_window(
            window_minutes=args.window_minutes,
            since=args.since,
            observed_at=observed_at,
        )
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")
        receipt = asyncio.run(
            collect_receipt(
                database_url,
                observed_at=observed_at,
                window_started_at=window_started_at,
                window_minutes=window_minutes,
                commit=os.environ.get("GIT_SHA", "unknown"),
            )
        )
    except Exception as exc:
        print(f"error_type={type(exc).__name__}", file=sys.stderr)
        return 1

    print(json.dumps(receipt, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
