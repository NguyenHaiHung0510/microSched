"""Google OIDC client, registered login-only (auth-brief §1)."""

from functools import lru_cache

from authlib.integrations.starlette_client import OAuth

from app.core.settings import get_settings

GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"

# The handshake cookie only has to survive one redirect to Google and back.
OAUTH_STATE_COOKIE = "ms_oauth_state"
OAUTH_STATE_TTL_SECONDS = 300


@lru_cache
def get_oauth() -> OAuth:
    """Return the process-wide Authlib registry with Google registered."""
    settings = get_settings()
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url=GOOGLE_METADATA_URL,
        # Login only: no Drive/Calendar scope, no offline access, no refresh token.
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth
