"""The single visibility gate for parent entities with privacy and soft deletion."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.sql import Select

from app.domain.models import AuthSession


def can_see_private(session: AuthSession) -> bool:
    """Return whether this authenticated session currently has its private gate open."""
    return session.private_until is not None and session.private_until > datetime.now(UTC)


def readable(stmt: Select[Any], model: Any, session: AuthSession) -> Select[Any]:
    """Restrict a parent-entity query to rows visible through this session."""
    stmt = stmt.where(model.deleted_at.is_(None))
    return stmt if can_see_private(session) else stmt.where(model.is_private.is_(False))
