"""Request-scoped guards and transaction dependencies for protected routes."""

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker
from app.core.sessions import SESSION_COOKIE_NAME
from app.core.settings import get_settings
from app.domain.auth import PostgresSessionStore, SessionStore
from app.domain.models import AuthSession


def _unauthenticated() -> HTTPException:
    """Build the single 401 used for every failed authentication path.

    Every failure returns the same body on purpose: telling a caller whether a
    session was missing, unknown, or expired only helps someone probing tokens.
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


def get_session_store() -> SessionStore | None:
    """Return the session store, or None when the database is not configured.

    Constructing the store opens no connection, so this stays cheap enough to
    resolve before the guard has decided whether a request is worth a lookup.
    Tests override this with an in-memory double.
    """
    factory = get_sessionmaker()
    if factory is None:
        return None

    return PostgresSessionStore(factory, get_settings().session_ttl_days)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield one transaction-scoped database session for the whole HTTP request."""
    factory = get_sessionmaker()
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured",
        )

    async with factory() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def require_session(
    request: Request,
    store: SessionStore | None = Depends(get_session_store),
) -> AuthSession:
    """Reject any request that does not carry a live session cookie."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise _unauthenticated()

    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured",
        )

    session = await store.load_valid(token)
    if session is None:
        raise _unauthenticated()

    return session
