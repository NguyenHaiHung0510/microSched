"""Health-check API endpoint."""

from fastapi import APIRouter

from app.core.settings import get_settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Report that the API process is available."""
    settings = get_settings()
    return {"status": "ok", "version": settings.app_version}
