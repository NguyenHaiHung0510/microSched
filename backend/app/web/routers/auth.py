"""Google login, logout, and the allowlist gate (auth-brief §1-§2)."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.sessions import SESSION_COOKIE_NAME
from app.core.settings import get_settings
from app.domain.auth import SessionStore
from app.web.deps import get_session_store
from app.web.oauth import get_oauth

router = APIRouter(prefix="/auth", tags=["auth"])

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1"})

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
    """Send the browser to Google, carrying a signed state parameter.

    `prompt=select_account` forces the account chooser every time. Without it,
    Google silently reuses its own session, so signing out of microSched and
    signing back in happens with no visible Google step at all - which makes the
    logout button feel like it did nothing.
    """
    return await get_oauth().google.authorize_redirect(
        request,
        callback_url(request),
        prompt="select_account",
    )


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
    try:
        token = await get_oauth().google.authorize_access_token(request)
    except Exception:  # any handshake failure is simply a refused login
        token = None

    # The handshake is finished either way, so the state cookie must not outlive it.
    request.session.clear()

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

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
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
