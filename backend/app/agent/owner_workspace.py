"""Single-Owner Mimi namespace policy; login identities remain authentication only.

Legacy namespaces are aliases, never rewritten. Only server-allowlisted identities
can contribute aliases. Empty local allowlists retain deterministic identity-scoped
fixtures; production always fails closed without an eligible identity.
"""

from __future__ import annotations

import hashlib
import hmac
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException

from app.core.settings import Settings, get_settings
from app.domain.models import AuthSession

OWNER_WORKSPACE_ID = uuid5(NAMESPACE_URL, "microsched:mimi:single-owner-workspace:v1")


def legacy_owner_id(email: str, settings: Settings | None = None) -> UUID:
    """Keep the exact pre-workspace HMAC, including its local fallback."""
    settings = settings or get_settings()
    secret = (settings.oauth_state_secret or settings.app_name).encode("utf-8")
    digest = hmac.new(secret, email.strip().lower().encode("utf-8"), hashlib.sha256)
    return UUID(bytes=digest.digest()[:16], version=5)


def _configured_aliases(settings: Settings) -> tuple[UUID, ...]:
    return (
        OWNER_WORKSPACE_ID,
        *(legacy_owner_id(email, settings) for email in sorted(settings.allowed_email_set)),
    )


def require_workspace_login(auth: AuthSession, settings: Settings) -> None:
    """Recheck server allowlist membership for an already authenticated session."""
    allowed = settings.allowed_email_set
    if (allowed or settings.is_production) and auth.user_email.strip().lower() not in allowed:
        raise HTTPException(404, "Mimi resource not found")


def owner_id(auth: AuthSession) -> UUID:
    """Resolve the write namespace without granting another login access."""
    settings = get_settings()
    require_workspace_login(auth, settings)
    if settings.mimi_owner_workspace_enabled and settings.allowed_email_set:
        return OWNER_WORKSPACE_ID
    return legacy_owner_id(auth.user_email, settings)


def related_owner_ids(owner: UUID) -> tuple[UUID, ...]:
    """Resolve eligible stored parents/preferences without enumerating DB owners.

    Background notification work has a stored owner UUID rather than a session.
    Foreign UUIDs keep exact identity semantics and can never join this workspace.
    """
    settings = get_settings()
    if settings.mimi_owner_workspace_enabled and settings.allowed_email_set:
        aliases = _configured_aliases(settings)
        if owner in aliases:
            return aliases
    return (owner,)


def owner_ids(auth: AuthSession) -> tuple[UUID, ...]:
    return related_owner_ids(owner_id(auth))
