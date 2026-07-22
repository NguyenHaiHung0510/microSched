"""Sparse external-cron entrypoints, authenticated separately from user sessions."""

import logging

from fastapi import APIRouter, Depends

from app.web.deps import require_cron_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/cron",
    tags=["cron"],
    dependencies=[Depends(require_cron_token)],
)


@router.post("/heartbeat")
async def heartbeat() -> dict[str, str]:
    """Prove the scheduled-job wire without polling or touching the database."""
    logger.info("Cron heartbeat received")
    return {"status": "ok"}
