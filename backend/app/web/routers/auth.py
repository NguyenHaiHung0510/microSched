"""Google login, logout, and the allowlist gate (auth-brief §1-§2)."""

import logging
from urllib.parse import parse_qs, urlparse

import httpx
from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.sessions import SESSION_COOKIE_NAME
from app.core.settings import get_settings
from app.domain.auth import SessionStore
from app.web.deps import get_session_store
from app.web.oauth import get_oauth

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1"})
AUTHLIB_GOOGLE_STATE_PREFIX = "_state_google_"
DEV_SESSION_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})

# Deliberately static: never reflect the submitted address back into the page, and
# never offer a way to request access. There is no sign-up for a single-user app.
DENIED_HTML = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Không được phép — microSched</title>
</head>
<body style="margin:0;background:#fafafa;color:#171717;
             font-family:system-ui,-apple-system,sans-serif">
<main style="max-width:30rem;margin:0 auto;padding:5rem 1.5rem">
  <p style="margin:0;font-size:.875rem;font-weight:500;color:#737373">microSched</p>
  <h1 style="margin:.5rem 0 0;font-size:1.875rem;font-weight:600;letter-spacing:-.02em">
    Không được phép
  </h1>
  <p style="margin:1.5rem 0 0;line-height:1.6;color:#404040">
    microSched là <strong>dự án cá nhân</strong>, chỉ mở cho tài khoản của chủ sở hữu.
    Tài khoản Google bạn vừa dùng không nằm trong danh sách được phép.
  </p>
  <p style="margin:1rem 0 0;line-height:1.6;color:#737373;font-size:.875rem">
    Đây không phải lỗi — ứng dụng không có đăng ký, và không có cách nào xin quyền truy cập.
  </p>
  <p style="margin:2rem 0 0">
    <a href="/" style="color:#171717;font-size:.875rem">← Quay lại trang chủ</a>
  </p>
</main>
</body>
</html>"""


def sanitize_return_to(target: str | None) -> str:
    """Validate that target is a safe relative path starting with a single slash."""
    if not target or not isinstance(target, str):
        return "/"
    target = target.strip()
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    first_segment = target[1:].split("/")[0]
    if ":" in first_segment:
        return "/"
    return target


def _oauth_state_from_redirect(response: Response) -> str | None:
    """Extract Authlib's generated state from its provider redirect response."""
    location = response.headers.get("location")
    if not location:
        return None
    states = parse_qs(urlparse(location).query).get("state", [])
    return states[0] if len(states) == 1 and states[0] else None


def _state_return_to(request: Request, state: str | None) -> str | None:
    """Read the return target bound to one Authlib state record, if it exists."""
    if not state:
        return None
    record = request.session.get(f"{AUTHLIB_GOOGLE_STATE_PREFIX}{state}")
    if not isinstance(record, dict):
        return None
    data = record.get("data")
    if not isinstance(data, dict):
        return None
    target = data.get("return_to")
    return target if isinstance(target, str) else None


def _remember_return_to(request: Request, state: str, return_to: str) -> None:
    """Attach a safe target to Authlib's signed data for exactly this state."""
    key = f"{AUTHLIB_GOOGLE_STATE_PREFIX}{state}"
    record = request.session.get(key)
    if not isinstance(record, dict):
        return
    data = record.get("data")
    if not isinstance(data, dict):
        return
    updated_record = dict(record)
    updated_data = dict(data)
    updated_data["return_to"] = return_to
    updated_record["data"] = updated_data
    request.session[key] = updated_record


def callback_url(request: Request) -> str:
    """Build the redirect URI exactly as registered in Google Cloud Console.

    Fly terminates TLS at its proxy, so the app itself sees a plain http request and
    would otherwise hand Google a redirect_uri it has never seen. Only loopback,
    where the owner really does browse over http, keeps the original scheme.
    """
    url = request.url_for("auth_callback")
    if url.hostname not in LOOPBACK_HOSTS:
        url = url.replace(scheme="https")
    return str(url)


def _set_session_cookie(response: Response, token: str) -> None:
    """Attach the opaque session token to the response."""
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.get("/login")
async def login(request: Request) -> Response:
    """Send the browser to Google and bind return_to to its signed OAuth state.

    `prompt=select_account` forces the account chooser every time. Without it,
    Google silently reuses its own session, so signing out of microSched and
    signing back in happens with no visible Google step at all - which makes the
    logout button feel like it did nothing.
    """
    return_to = sanitize_return_to(request.query_params.get("return_to"))
    # Authlib 1.7.2 drops previous ``_state_google_*`` records when creating a
    # new one. Keep those signed records so two tabs can finish independently;
    # each callback still consumes only its own state through Authlib.
    existing_states = {
        key: value
        for key, value in request.session.items()
        if key.startswith(AUTHLIB_GOOGLE_STATE_PREFIX)
    }
    response = await get_oauth().google.authorize_redirect(
        request,
        callback_url(request),
        prompt="select_account",
    )
    state = _oauth_state_from_redirect(response)
    if state is not None:
        _remember_return_to(request, state, return_to)
    request.session.update(existing_states)
    return response


@router.get("/denied")
async def access_denied() -> Response:
    """Serve the refusal page at a URL of its own."""
    return HTMLResponse(content=DENIED_HTML, status_code=status.HTTP_403_FORBIDDEN)


@router.get("/callback", name="auth_callback")
async def auth_callback(
    request: Request,
    store: SessionStore | None = Depends(get_session_store),
) -> Response:
    """Verify Google's response, apply the allowlist, then open a session."""
    callback_state = request.query_params.get("state")
    # This value is only used after authorize_access_token succeeds. Authlib
    # validates and consumes the same signed state record during that call.
    state_return_to = _state_return_to(request, callback_state)
    try:
        token = await get_oauth().google.authorize_access_token(request)
    except OAuthError as error:
        # Invalid/mismatched state and provider refusals are expected when a callback
        # is stale, malformed, or being probed. Never log the code or state values.
        logger.warning(
            "Google OAuth callback rejected by protocol validation (%s)",
            error.error or type(error).__name__,
        )
        token = None
    except httpx.HTTPError as error:
        # This is operationally different from a bad callback: Google or the network
        # failed while exchanging the code. Log only the class, never request data.
        logger.error("Google OAuth token exchange unavailable (%s)", type(error).__name__)
        token = None
    except Exception:
        # Preserve the fail-closed 303 behavior for unexpected library failures while
        # keeping them visibly distinct from rejected callbacks and upstream outages.
        logger.exception("Unexpected Google OAuth callback failure")
        token = None
    finally:
        # Authlib clears this on a normal token exchange. Also clear the exact
        # state on provider refusal/failure, but retain another tab's valid
        # pending state instead of clearing the whole signed-session cookie.
        if callback_state:
            request.session.pop(f"{AUTHLIB_GOOGLE_STATE_PREFIX}{callback_state}", None)

    # Protocol validation above is a precondition for ever using this target;
    # sanitize again at the redirect boundary in case stored state is malformed.
    safe_target = sanitize_return_to(state_return_to) if token is not None else "/"

    claims = (token or {}).get("userinfo") or {}
    email = str(claims.get("email") or "").strip().lower()

    # An unverified address is not proof of ownership, so it never passes the gate.
    if not claims.get("email_verified") or email not in get_settings().allowed_email_set:
        # Redirect rather than render in place. Rendering would leave the browser
        # parked on /auth/callback?code=... so the authorization code stays in the
        # address bar and in history. The code is single-use, already spent, and
        # worthless without the client secret - but it has no reason to linger.
        return RedirectResponse(url="/auth/denied", status_code=status.HTTP_303_SEE_OTHER)

    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured",
        )

    response = RedirectResponse(url=safe_target, status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, await store.create(email))
    return response


@router.post("/logout")
async def logout(
    request: Request,
    store: SessionStore | None = Depends(get_session_store),
) -> Response:
    """Delete the session row so the cookie stops working immediately."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token and store is not None:
        await store.delete(token)

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


@router.get("/dev-session")
async def dev_session(
    request: Request,
    store: SessionStore | None = Depends(get_session_store),
) -> Response:
    """Dev/QA only: generate a valid local session for owner@test.local and redirect home."""
    settings = get_settings()
    if settings.app_env != "local":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not available")
    client_host = request.client.host if request.client else ""
    if client_host not in DEV_SESSION_LOOPBACK_HOSTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not available")
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured",
        )
    token = await store.create("owner@test.local")
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, token)
    return response
