"""Liveness and readiness endpoints, deliberately kept apart.

Splitting these is a cost decision, not a style one. Fly probes the liveness path
every 30 seconds (`fly.toml`). Neon's free plan autosuspends a compute after five
minutes idle and bills a 0.25 CU floor while it is awake, so *any* probe that runs
SQL keeps the database awake around the clock: 6 CU-hrs/day against a 100 CU-hr
monthly allowance, exhausted in ~17 days, after which Neon suspends the compute
until the next billing period - an outage, not a bill. `schema-physical-brief.md`
§185 called this out in advance ("cron đừng ping DB quá dày"); the 30s probe added
in 005 walked straight into it, because nothing tied the two files together.

Liveness answers "should this machine be restarted or routed to" - a sleeping
database is not a reason to kill the app process. Readiness answers "can this
process actually reach what it depends on", and is therefore allowed to spend a
query. Never point an automated probe at the readiness path.
"""

from fastapi import APIRouter

from app.core.db import check_database
from app.core.settings import get_settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Report process liveness. Must never touch the database - see module docstring."""
    settings = get_settings()
    return {
        "status": "ok",
        "version": settings.app_version,
    }


@router.get("/readyz")
async def readyz() -> dict[str, str]:
    """Report dependency reachability, spending one query to do it.

    Returns 200 even when the database is unreachable, reporting the failure in the
    body instead. A 503 here would be the more conventional choice, but it makes one
    specific mistake catastrophic: point `fly.toml` at this path and every Neon
    autosuspend turns into a machine restart loop. Callers that care read `status`.
    """
    settings = get_settings()
    database = await check_database()
    return {
        "status": "ok" if database == "up" else "degraded",
        "version": settings.app_version,
        "db": database,
    }
