"""Server-side session storage backed by the `session` table (auth-brief §2)."""

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.sessions import hash_session_token, new_session_token, rolling_expiry
from app.domain.models import AuthSession


class SessionStore(Protocol):
    """The session operations the web layer depends on."""

    async def create(self, email: str) -> str:
        """Persist a new session and return its raw token."""
        ...

    async def load_valid(self, token: str) -> AuthSession | None:
        """Return the live session for a token, refreshing its rolling window."""
        ...

    async def delete(self, token: str) -> None:
        """Remove a session so its cookie stops working immediately."""
        ...


class PostgresSessionStore:
    """The production `SessionStore`, storing only token digests.

    It holds the session factory rather than an open connection so that constructing
    the store costs nothing: the guard can reject a cookie-less request with 401
    before any database work happens.
    """

    def __init__(self, factory: async_sessionmaker[AsyncSession], ttl_days: int) -> None:
        self._factory = factory
        self._ttl_days = ttl_days

    async def create(self, email: str) -> str:
        """Persist a new session and return the raw token for the cookie."""
        token = new_session_token()
        now = datetime.now(UTC)
        async with self._factory() as db:
            db.add(
                AuthSession(
                    token_hash=hash_session_token(token),
                    user_email=email,
                    last_seen_at=now,
                    expires_at=rolling_expiry(self._ttl_days, now),
                )
            )
            await db.commit()
        return token

    async def load_valid(self, token: str) -> AuthSession | None:
        """Return the live session for a token, or None when absent or expired."""
        digest = hash_session_token(token)
        async with self._factory() as db:
            result = await db.execute(select(AuthSession).where(AuthSession.token_hash == digest))
            session = result.scalar_one_or_none()
            if session is None:
                return None

            now = datetime.now(UTC)
            if session.expires_at <= now:
                # Drop it rather than leaving dead rows for a later sweep to find.
                await db.execute(delete(AuthSession).where(AuthSession.token_hash == digest))
                await db.commit()
                return None

            # Rolling TTL: every authenticated request pushes the window forward.
            session.last_seen_at = now
            session.expires_at = rolling_expiry(self._ttl_days, now)
            await db.commit()
            return session

    async def delete(self, token: str) -> None:
        """Remove the session row so the cookie stops working immediately."""
        async with self._factory() as db:
            await db.execute(
                delete(AuthSession).where(AuthSession.token_hash == hash_session_token(token))
            )
            await db.commit()
