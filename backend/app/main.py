"""FastAPI application factory."""

import logging
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import Scope

from app.core.settings import get_settings
from app.web.deps import require_session
from app.web.oauth import OAUTH_STATE_COOKIE, OAUTH_STATE_TTL_SECONDS
from app.web.routers.auth import router as auth_router
from app.web.routers.cron import router as cron_router
from app.web.routers.health import router as health_router
from app.web.routers.me import router as me_router

logger = logging.getLogger(__name__)


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
    oauth_state_secret = settings.oauth_state_secret
    if not oauth_state_secret:
        # Gated on APP_ENV rather than on a nearby setting like SESSION_COOKIE_SECURE.
        # Inferring the environment from an unrelated switch means that one day someone
        # flips that switch for its own reasons and silently disables this guard too -
        # the same shape as the Neon incident, where the damage lived in an invisible
        # link between two individually correct settings.
        if settings.is_production:
            raise RuntimeError("OAUTH_STATE_SECRET is required when APP_ENV=production")
        logger.warning(
            "OAUTH_STATE_SECRET is not configured; using an ephemeral local-development secret"
        )
        oauth_state_secret = secrets.token_urlsafe(32)

    app = FastAPI(title=settings.app_name, version=settings.app_version)

    # Signs the short-lived OAuth handshake cookie and NOTHING else. The login
    # session is an opaque token row in `session` (auth-brief §2) - never this
    # cookie. Keeping the two apart matters because merging them still demos fine.
    # The ephemeral fallback is allowed only for explicitly insecure local development.
    app.add_middleware(
        SessionMiddleware,
        secret_key=oauth_state_secret,
        session_cookie=OAUTH_STATE_COOKIE,
        max_age=OAUTH_STATE_TTL_SECONDS,
        same_site="lax",
        https_only=settings.session_cookie_secure,
    )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(cron_router)

    # Single mount point for authenticated API routes: including a router here is
    # what makes it reachable, so a new slice cannot ship without the guard.
    protected_api = APIRouter(prefix="/api", dependencies=[Depends(require_session)])
    protected_api.include_router(me_router)

    @protected_api.get("/{path:path}", include_in_schema=False)
    def api_not_found(path: str) -> None:
        """Keep unknown API paths out of the SPA fallback."""
        raise HTTPException(status_code=404, detail="Not Found")

    app.include_router(protected_api)

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", SPAStaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app
