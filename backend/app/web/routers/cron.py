"""Sparse external-cron entrypoints, authenticated separately from user sessions."""

import logging

from fastapi import APIRouter, Depends

from app.core.process_stats import read_rss_kb
from app.web.deps import require_cron_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/cron",
    tags=["cron"],
    dependencies=[Depends(require_cron_token)],
)


@router.post("/heartbeat")
async def heartbeat() -> dict[str, str | int | None]:
    """Prove the scheduled-job wire without polling or touching the database."""
    rss_kb = read_rss_kb()
    if rss_kb is not None:
        logger.info("Cron heartbeat received rss_kb=%d", rss_kb)
    else:
        logger.info("Cron heartbeat received rss_kb=unavailable")
    return {"status": "ok", "rss_kb": rss_kb}
