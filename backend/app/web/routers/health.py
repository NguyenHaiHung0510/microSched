"""Health-check API endpoint."""

from fastapi import APIRouter

from app.core.db import check_database
from app.core.settings import get_settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Report process availability and database reachability independently."""
    settings = get_settings()
    return {
        "status": "ok",
        "version": settings.app_version,
        "db": await check_database(),
    }
