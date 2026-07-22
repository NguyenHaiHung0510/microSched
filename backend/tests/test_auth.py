"""Tests for Google login, the allowlist gate, the session guard, and cron auth."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from authlib.integrations.base_client.errors import OAuthError
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.sessions import (
    SESSION_COOKIE_NAME,
    hash_session_token,
    new_session_token,
    rolling_expiry,
)
from app.core.settings import Settings, get_settings
from app.domain.auth import PostgresSessionStore
from app.domain.models import AuthSession
from app.main import create_app
from app.web.deps import get_session_store, require_cron_token, require_session

ALLOWED_EMAIL = "owner@example.com"
BLOCKED_EMAIL = "stranger@example.com"
CRON_TOKEN = "cron-token-used-only-by-tests"
TTL_DAYS = 90


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    """Pin auth configuration so a developer's real .env never reaches the tests."""
    monkeypatch.setenv("ALLOWED_EMAILS", f"{ALLOWED_EMAIL}, Second@Example.COM ")
    monkeypatch.setenv("CRON_TOKEN", CRON_TOKEN)
    monkeypatch.setenv("SESSION_TTL_DAYS", str(TTL_DAYS))
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "state-secret-used-only-by-tests")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class InMemorySessionStore:
    """A `SessionStore` double implementing the same contract without Postgres."""

    def __init__(self, ttl_days: int = TTL_DAYS) -> None:
        self.rows: dict[str, AuthSession] = {}
        self._ttl_days = ttl_days

    async def create(self, email: str) -> str:
        token = new_session_token()
        now = datetime.now(UTC)
        digest = hash_session_token(token)
        self.rows[digest] = AuthSession(
            token_hash=digest,
            user_email=email,
            last_seen_at=now,
            expires_at=rolling_expiry(self._ttl_days, now),
        )
        return token

    async def load_valid(self, token: str) -> AuthSession | None:
        digest = hash_session_token(token)
        row = self.rows.get(digest)
        if row is None:
            return None

        now = datetime.now(UTC)
        if row.expires_at <= now:
            del self.rows[digest]
            return None

        row.last_seen_at = now
        row.expires_at = rolling_expiry(self._ttl_days, now)
        return row

    async def delete(self, token: str) -> None:
        self.rows.pop(hash_session_token(token), None)


class _FakeGoogleClient:
    """Stands in for Authlib's Google client so CI never calls Google."""

    def __init__(self, claims: dict | None, failure: Exception | None = None) -> None:
        self._claims = claims
        self._failure = failure

    async def authorize_access_token(self, request) -> dict:
        if self._failure:
            raise self._failure
        return {"userinfo": self._claims}


class _FakeOAuth:
    def __init__(self, claims: dict | None, failure: Exception | None = None) -> None:
        self.google = _FakeGoogleClient(claims, failure)


def build_client(store: InMemorySessionStore) -> TestClient:
    """Return a client whose session storage is the in-memory double."""
    app = create_app()
    app.dependency_overrides[get_session_store] = lambda: store
    return TestClient(app)


def complete_login(client: TestClient, monkeypatch, email: str, verified: bool = True):
    """Drive the callback with a mocked Google response."""
    claims = {"email": email, "email_verified": verified}
    monkeypatch.setattr("app.web.routers.auth.get_oauth", lambda: _FakeOAuth(claims))
    return client.get("/auth/callback?code=x&state=y", follow_redirects=False)


def test_allowlisted_email_gets_a_session_and_reaches_the_api(monkeypatch) -> None:
    """The happy path: Google says who you are, the allowlist says you may in."""
    store = InMemorySessionStore()
    client = build_client(store)

    response = complete_login(client, monkeypatch, ALLOWED_EMAIL)

    assert response.status_code == 303
    assert len(store.rows) == 1

    body = client.get("/api/me").json()
    assert body["email"] == ALLOWED_EMAIL
    assert body["expires_at"] is not None


def test_allowlist_comparison_ignores_case_and_padding(monkeypatch) -> None:
    """Google's claim and the env list are normalized the same way before matching."""
    store = InMemorySessionStore()
    client = build_client(store)

    response = complete_login(client, monkeypatch, "SECOND@example.com")

    assert response.status_code == 303
    assert store.rows.popitem()[1].user_email == "second@example.com"


def test_email_outside_allowlist_is_refused_without_creating_a_session(monkeypatch) -> None:
    """A valid Google account that is not the owner gets nothing at all."""
    store = InMemorySessionStore()
    client = build_client(store)

    response = complete_login(client, monkeypatch, BLOCKED_EMAIL)

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/denied"
    assert store.rows == {}
    assert SESSION_COOKIE_NAME not in response.cookies


def test_refusal_redirects_away_from_the_authorization_code(monkeypatch) -> None:
    """Refusal must not park the browser on the callback URL.

    Rendering the page in place would leave `?code=...` in the address bar and in
    history. The code is single-use, already spent, and useless without the client
    secret - but it has no reason to linger there.
    """
    client = build_client(InMemorySessionStore())

    response = complete_login(client, monkeypatch, BLOCKED_EMAIL)
    target = response.headers["location"]

    assert "code" not in target
    assert "?" not in target
    assert client.get(target).status_code == 403


def test_unverified_google_address_is_refused(monkeypatch) -> None:
    """An unverified claim is not proof of ownership even if the address matches."""
    store = InMemorySessionStore()
    client = build_client(store)

    response = complete_login(client, monkeypatch, ALLOWED_EMAIL, verified=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/denied"
    assert store.rows == {}


def test_failed_google_handshake_is_refused(monkeypatch) -> None:
    """A broken or forged callback is a refused login, not a server error."""
    store = InMemorySessionStore()
    client = build_client(store)
    failure = OAuthError(error="mismatching_state", description="test-only refusal")
    monkeypatch.setattr("app.web.routers.auth.get_oauth", lambda: _FakeOAuth(None, failure))

    response = client.get("/auth/callback?code=x&state=y", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/denied"
    assert store.rows == {}


def test_unexpected_google_failure_still_redirects_to_denied(monkeypatch) -> None:
    """Unexpected client failures stay fail-closed without leaving code in the URL."""
    store = InMemorySessionStore()
    client = build_client(store)
    monkeypatch.setattr(
        "app.web.routers.auth.get_oauth",
        lambda: _FakeOAuth(None, RuntimeError("unexpected test failure")),
    )

    response = client.get("/auth/callback?code=x&state=y", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/denied"
    assert store.rows == {}


def test_missing_oauth_state_secret_stops_production_startup(monkeypatch) -> None:
    """A restart must not silently invalidate every in-flight production handshake."""
    monkeypatch.setenv("OAUTH_STATE_SECRET", "")
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="OAUTH_STATE_SECRET"):
        create_app()


def test_production_is_the_default_when_app_env_is_unset(monkeypatch) -> None:
    """Forgetting APP_ENV must fail closed: the lenient value is never the default.

    Asserted against the class default with the .env file disabled, not against this
    machine's environment - otherwise a developer's local APP_ENV=local would make the
    test pass here and fail in CI, or worse, the reverse.
    """
    monkeypatch.delenv("APP_ENV", raising=False)

    assert Settings(_env_file=None).is_production is True


def test_a_misspelled_app_env_is_rejected_instead_of_read_as_lenient(monkeypatch) -> None:
    """APP_ENV=prod must not quietly mean 'not production' and drop the guards."""
    monkeypatch.setenv("APP_ENV", "prod")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_missing_oauth_state_secret_is_allowed_only_for_local_development(
    monkeypatch, caplog
) -> None:
    """Local HTTP remains zero-config but emits an actionable warning."""
    monkeypatch.setenv("OAUTH_STATE_SECRET", "")
    monkeypatch.setenv("APP_ENV", "local")
    get_settings.cache_clear()

    app = create_app()

    assert app is not None
    assert "OAUTH_STATE_SECRET is not configured" in caplog.text


def test_login_always_forces_the_google_account_chooser(monkeypatch) -> None:
    """Without prompt=select_account, signing back in after logout skips Google."""
    captured: dict[str, object] = {}

    class _Google:
        async def authorize_redirect(self, request, redirect_uri: str, **params):
            captured.update(params)
            return RedirectResponse("https://accounts.google.com", status_code=302)

    monkeypatch.setattr(
        "app.web.routers.auth.get_oauth",
        lambda: type("_Registry", (), {"google": _Google()})(),
    )
    build_client(InMemorySessionStore()).get("/auth/login", follow_redirects=False)

    assert captured["prompt"] == "select_account"


def test_session_cookie_carries_the_expected_flags(monkeypatch) -> None:
    """HttpOnly and SameSite=Lax are set on the cookie itself, not just documented."""
    client = build_client(InMemorySessionStore())

    response = complete_login(client, monkeypatch, ALLOWED_EMAIL)
    header = response.headers["set-cookie"]

    assert header.startswith(f"{SESSION_COOKIE_NAME}=")
    assert "HttpOnly" in header
    assert "SameSite=lax" in header


def test_oauth_state_cookie_does_not_outlive_the_handshake(monkeypatch) -> None:
    """The handshake cookie is cleared at the callback so it can never act as a session."""
    client = build_client(InMemorySessionStore())

    complete_login(client, monkeypatch, ALLOWED_EMAIL)

    assert client.cookies.get("ms_oauth_state") is None


class _CapturingGoogleClient:
    """Records the redirect_uri instead of bouncing the browser to Google."""

    def __init__(self) -> None:
        self.redirect_uri: str | None = None

    async def authorize_redirect(self, request, redirect_uri: str, **params):
        self.redirect_uri = redirect_uri
        return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth", status_code=302)


def capture_redirect_uri(monkeypatch, base_url: str) -> str:
    """Return the redirect_uri the app would hand Google from a given origin."""
    google = _CapturingGoogleClient()
    monkeypatch.setattr(
        "app.web.routers.auth.get_oauth",
        lambda: type("_Registry", (), {"google": google})(),
    )
    client = TestClient(create_app(), base_url=base_url)

    client.get("/auth/login", follow_redirects=False)

    assert google.redirect_uri is not None
    return google.redirect_uri


def test_local_development_keeps_the_http_callback(monkeypatch) -> None:
    """Loopback really is browsed over http, so its registered URI stays http."""
    assert (
        capture_redirect_uri(monkeypatch, "http://localhost:8000")
        == "http://localhost:8000/auth/callback"
    )


def test_deployed_callback_is_forced_to_https(monkeypatch) -> None:
    """Fly terminates TLS, so the app sees http and must not hand Google that URI.

    Getting this wrong is invisible in tests that only check status codes: Google
    answers redirect_uri_mismatch and login simply never works.
    """
    assert (
        capture_redirect_uri(monkeypatch, "http://microsched.fly.dev")
        == "https://microsched.fly.dev/auth/callback"
    )


def test_api_rejects_a_request_without_a_cookie() -> None:
    """The guard answers 401 before it ever looks for a database."""
    response = build_client(InMemorySessionStore()).get("/api/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_api_rejects_an_unknown_token() -> None:
    """A forged cookie matches no row and is refused."""
    client = build_client(InMemorySessionStore())
    client.cookies.set(SESSION_COOKIE_NAME, new_session_token())

    assert client.get("/api/me").status_code == 401


def test_api_rejects_an_expired_session() -> None:
    """An expired row is refused and removed rather than left behind."""
    store = InMemorySessionStore()
    token = asyncio.run(store.create(ALLOWED_EMAIL))
    digest = hash_session_token(token)
    store.rows[digest].expires_at = datetime.now(UTC) - timedelta(seconds=1)
    client = build_client(store)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    assert client.get("/api/me").status_code == 401
    assert digest not in store.rows


def test_each_authenticated_request_extends_the_rolling_window() -> None:
    """A session about to lapse is pushed back to a full TTL by simply being used."""
    store = InMemorySessionStore()
    token = asyncio.run(store.create(ALLOWED_EMAIL))
    digest = hash_session_token(token)
    store.rows[digest].expires_at = datetime.now(UTC) + timedelta(days=1)
    client = build_client(store)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    assert client.get("/api/me").status_code == 200
    assert store.rows[digest].expires_at > datetime.now(UTC) + timedelta(days=TTL_DAYS - 1)


def test_logout_deletes_the_row_and_the_cookie_stops_working() -> None:
    """Logout revokes server-side; a copied cookie is worthless afterwards."""
    store = InMemorySessionStore()
    token = asyncio.run(store.create(ALLOWED_EMAIL))
    client = build_client(store)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    assert client.post("/auth/logout").status_code == 204
    assert store.rows == {}

    client.cookies.set(SESSION_COOKIE_NAME, token)
    assert client.get("/api/me").status_code == 401


def test_healthz_stays_reachable_without_a_session() -> None:
    """Fly's health check must not need a login."""
    assert build_client(InMemorySessionStore()).get("/api/healthz").status_code == 200


def test_every_api_route_except_healthz_is_guarded() -> None:
    """Structural check: a future slice cannot ship an unguarded /api route."""

    def guarded(route: APIRoute) -> bool:
        pending = list(route.dependant.dependencies)
        while pending:
            dependency = pending.pop()
            if dependency.call is require_session:
                return True
            pending.extend(dependency.dependencies)
        return False

    unguarded = [
        route.path
        for route in create_app().routes
        if isinstance(route, APIRoute)
        and route.path.startswith("/api")
        and route.path != "/api/healthz"
        and not guarded(route)
    ]

    assert unguarded == []


def test_postgres_store_persists_only_the_token_digest() -> None:
    """The real store must never put a replayable token in the table."""

    class _RecordingSession:
        def __init__(self) -> None:
            self.added: list[AuthSession] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_) -> bool:
            return False

        def add(self, row: AuthSession) -> None:
            self.added.append(row)

        async def commit(self) -> None:
            return None

    recorder = _RecordingSession()
    store = PostgresSessionStore(lambda: recorder, TTL_DAYS)

    token = asyncio.run(store.create(ALLOWED_EMAIL))
    row = recorder.added[0]

    assert row.token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert all(token not in str(value) for value in row.model_dump().values())


def test_session_token_carries_256_bits_of_entropy() -> None:
    """Tokens are unguessable and never repeat."""
    tokens = {new_session_token() for _ in range(100)}

    assert len(tokens) == 100
    assert all(len(token) >= 43 for token in tokens)


def test_cron_endpoint_accepts_the_configured_bearer_token() -> None:
    """The scheduled-job guard lets the real token through."""
    assert asyncio.run(require_cron_token(f"Bearer {CRON_TOKEN}")) is None


def test_cron_heartbeat_uses_bearer_auth_not_a_user_session() -> None:
    """The real route is independently guarded and never needs a login cookie."""
    client = build_client(InMemorySessionStore())

    assert client.post("/api/cron/heartbeat").status_code == 401
    assert (
        client.post(
            "/api/cron/heartbeat", headers={"Authorization": "Bearer wrong-token"}
        ).status_code
        == 401
    )
    response = client.post("/api/cron/heartbeat", headers={"Authorization": f"Bearer {CRON_TOKEN}"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cron_heartbeat_is_closed_and_noisy_when_unconfigured(monkeypatch) -> None:
    """A missing shared secret is a 503 configuration fault, never an auth bypass."""
    monkeypatch.setenv("CRON_TOKEN", "")
    get_settings.cache_clear()
    client = build_client(InMemorySessionStore())

    response = client.post("/api/cron/heartbeat")

    assert response.status_code == 503
    assert response.json() == {"detail": "Cron token is not configured"}


@pytest.mark.parametrize(
    "header",
    [None, "", f"Basic {CRON_TOKEN}", "Bearer wrong-token", "Bearer "],
)
def test_cron_endpoint_rejects_anything_else(header) -> None:
    """Wrong scheme, wrong value, or no header at all are all refused."""
    with pytest.raises(HTTPException) as error:
        asyncio.run(require_cron_token(header))

    assert error.value.status_code == 401
