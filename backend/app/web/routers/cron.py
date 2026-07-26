"""Sparse external-cron entrypoints, authenticated separately from user sessions."""

import logging

from fastapi import APIRouter, Depends

from app.core.process_stats import (
    calculate_rss_pct,
    read_mem_total_kb,
    read_rss_kb,
    read_uptime_s,
    restart_advised,
)
from app.web.deps import require_cron_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/cron",
    tags=["cron"],
    dependencies=[Depends(require_cron_token)],
)


@router.post("/heartbeat")
async def heartbeat() -> dict[str, str | int | float | bool | None]:
    """Prove the scheduled-job wire without polling or touching the database."""
    rss_kb = read_rss_kb()
    uptime_s = read_uptime_s()
    mem_total_kb = read_mem_total_kb()
    rss_pct = calculate_rss_pct(rss_kb, mem_total_kb)
    advised = restart_advised(rss_pct)
    logger.info(
        "Cron heartbeat received rss_kb=%s uptime_s=%s mem_total_kb=%s "
        "rss_pct=%s restart_advised=%s",
        rss_kb,
        uptime_s,
        mem_total_kb,
        rss_pct,
        advised,
    )
    return {
        "status": "ok",
        "rss_kb": rss_kb,
        "uptime_s": uptime_s,
        "mem_total_kb": mem_total_kb,
        "rss_pct": rss_pct,
        "restart_advised": advised,
    }
