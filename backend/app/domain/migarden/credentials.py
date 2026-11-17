"""Scoped single-device credential; the database never receives the raw token."""

import hashlib
import hmac
import re

from app.domain.migarden.models import ZoneState

TOKEN = re.compile(r"^[a-zA-Z0-9_-]{43}$")
DUMMY = "0" * 64


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def allows(zone: ZoneState | None, token_hash: str, production: bool) -> bool:
    stored = zone.token_hash if zone and zone.token_hash else DUMMY
    matches = hmac.compare_digest(stored, token_hash)
    environment = "production" if production else "qa"
    return bool(
        matches
        and zone
        and zone.device_id
        and zone.device_environment == environment
        and zone.revoked_at is None
    )
