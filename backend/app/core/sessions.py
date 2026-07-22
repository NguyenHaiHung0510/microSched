"""Opaque session-token primitives (auth-brief §2).

The raw token only ever exists in the cookie; the database stores its digest, so a
leaked table dump cannot be replayed as a login.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

SESSION_COOKIE_NAME = "ms_session"

# 32 bytes = 256 bits of entropy, the floor required by the 007 spec.
TOKEN_BYTES = 32


def new_session_token() -> str:
    """Return a fresh opaque session token for the cookie."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """Return the digest persisted in place of the raw token.

    A plain SHA-256 is correct here (unlike for passwords): the input is already
    256 bits of uniform randomness, so there is nothing for a slow KDF to defend.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def rolling_expiry(ttl_days: int, now: datetime | None = None) -> datetime:
    """Return the refreshed expiry for a session touched at ``now``."""
    return (now or datetime.now(UTC)) + timedelta(days=ttl_days)
