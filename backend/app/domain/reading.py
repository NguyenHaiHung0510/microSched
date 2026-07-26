"""The single visibility gate for parent entities with privacy and soft deletion."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.sql import Select

from app.domain.models import AuthSession


def can_see_private(session: AuthSession) -> bool:
    """Return whether this authenticated session currently has its private gate open."""
    return session.private_until is not None and session.private_until > datetime.now(UTC)


def with_privacy_gate(
    stmt: Select[Any], model: Any, session: AuthSession
) -> Select[Any]:
    """Restrict a query to rows visible through this session's private gate."""
    return stmt if can_see_private(session) else stmt.where(model.is_private.is_(False))


def not_deleted(stmt: Select[Any], model: Any) -> Select[Any]:
    """Restrict a query to rows that have not been soft-deleted."""
    return stmt.where(model.deleted_at.is_(None))


def readable(stmt: Select[Any], model: Any, session: AuthSession) -> Select[Any]:
    """Restrict a parent-entity query by privacy and soft deletion."""
    return not_deleted(with_privacy_gate(stmt, model, session), model)
