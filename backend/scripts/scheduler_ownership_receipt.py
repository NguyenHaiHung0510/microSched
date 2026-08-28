"""One-shot, read-only receipt for the 035A scheduler advisory-lock holder count."""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime

import asyncpg

from app.core.cron_timer import (
    SCHEDULER_ADVISORY_LOCK_KEY,
    SCHEDULER_ADVISORY_LOCK_NAMESPACE,
    SCHEDULER_ADVISORY_LOCK_REF,
)
from app.core.database_urls import asyncpg_dsn

HOLDER_COUNT_QUERY = """
SELECT count(*)::bigint
FROM pg_locks
WHERE locktype = 'advisory'
  AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND classid = $1::oid
  AND objid = $2::oid
  AND objsubid = 2
  AND mode = 'ExclusiveLock'
  AND granted
"""


def _utc_rfc3339(value: datetime) -> str:
    """Render an already-UTC observation time without locale-dependent output."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


async def collect_receipt(
    database_url: str, *, observed_at: datetime, commit: str
) -> dict[str, object]:
    """Count exactly this advisory lock and close the one-shot connection."""
    connection = None
    try:
        connection = await asyncpg.connect(asyncpg_dsn(database_url))
        holder_count = await connection.fetchval(
            HOLDER_COUNT_QUERY,
            SCHEDULER_ADVISORY_LOCK_NAMESPACE,
            SCHEDULER_ADVISORY_LOCK_KEY,
        )
    finally:
        if connection is not None:
            await connection.close()

    return {
        "commit": commit,
        "observed_at": _utc_rfc3339(observed_at),
        "scheduler_state": "observed",
        "lock_ref": SCHEDULER_ADVISORY_LOCK_REF,
        "holder_count": holder_count,
    }


def main() -> int:
    """Emit JSON only; never print a database URL or backend PID."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("error_type=RuntimeError", file=sys.stderr)
        return 1
    try:
        receipt = asyncio.run(
            collect_receipt(
                database_url,
                observed_at=datetime.now(UTC),
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
