"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from app.core.settings import get_settings
from app.web.routers.health import router as health_router


class SPAStaticFiles(StaticFiles):
    """Serve the SPA entry point when a built frontend route is not a file."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if error.status_code != 404:
                raise
            return FileResponse(Path(self.directory) / "index.html")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.include_router(health_router)

    @app.get("/api/{path:path}", include_in_schema=False)
    def api_not_found(path: str) -> None:
        """Keep unknown API paths out of the SPA fallback."""
        raise HTTPException(status_code=404, detail="Not Found")

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", SPAStaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app
