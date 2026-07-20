"""FastAPI application factory."""

from fastapi import FastAPI

from app.core.settings import Settings
from app.web.routers.health import router as health_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = Settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.include_router(health_router)
    return app
