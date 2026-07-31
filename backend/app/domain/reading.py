"""The single visibility gate for parent entities with privacy and soft deletion."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.sql import Select

from app.domain import models as model_registry
from app.domain.models import AuthSession, Gate


class ReadingGateError(RuntimeError):
    """A model's read-gate declaration is missing, invalid, or misused."""


def _table_name(model: Any) -> str:
    table = vars(model).get("__table__")
    return table.name if table is not None else model.__name__


def _declared_gate(model: Any, flag_name: str) -> Gate:
    declarations = vars(model)
    if flag_name not in declarations:
        raise ReadingGateError(
            f"{_table_name(model)} chưa khai {flag_name}. "
            "Khai Gate.APPLIES, Gate.NONE hoặc Gate.VIA_PARENT; "
            "xem agent-tasks/008n-reading-gate-registry.md."
        )
    gate = declarations[flag_name]
    if not isinstance(gate, Gate):
        raise ReadingGateError(
            f"{_table_name(model)} khai {flag_name} không hợp lệ. "
            "Dùng Gate.APPLIES, Gate.NONE hoặc Gate.VIA_PARENT; "
            "xem agent-tasks/008n-reading-gate-registry.md."
        )
    return gate


def _direct_parent_models(model: Any, flag_name: str) -> list[type[Any]]:
    table = vars(model).get("__table__")
    if table is None:
        return []
    parent_tables = {foreign_key.column.table.fullname for foreign_key in table.foreign_keys}
    parents = []
    for candidate in vars(model_registry).values():
        if not isinstance(candidate, type):
            continue
        candidate_table = vars(candidate).get("__table__")
        if candidate_table is None or candidate_table.fullname not in parent_tables:
            continue
        if vars(candidate).get(flag_name) is Gate.APPLIES:
            parents.append(candidate)
    return sorted(parents, key=lambda parent: parent.__name__)


def _via_parent_error(model: Any, flag_name: str, function_name: str) -> ReadingGateError:
    parents = _direct_parent_models(model, flag_name)
    axis = "privacy" if flag_name == "__privacy_gate__" else "soft-delete"
    if parents:
        parent_names = " hoặc ".join(parent.__name__ for parent in parents)
        return ReadingGateError(
            f"{_table_name(model)} áp dụng {axis} qua {parent_names} cha; "
            f"JOIN {parent_names} rồi gọi {function_name}(stmt, {parent_names}"
            + (", session)." if function_name == "with_privacy_gate" else ").")
        )
    return ReadingGateError(
        f"{_table_name(model)} khai {flag_name}=Gate.VIA_PARENT nhưng không có FK "
        f"tới bảng cha khai Gate.APPLIES trên trục {axis}; sửa lời khai model."
    )


def _gate_column(model: Any, flag_name: str, column_name: str) -> Any:
    table = vars(model).get("__table__")
    if table is None or column_name not in table.columns:
        raise ReadingGateError(
            f"{_table_name(model)} khai {flag_name}=Gate.APPLIES nhưng không có cột "
            f"{column_name}; sửa lời khai hoặc schema theo agent-tasks/008n."
        )
    return table.columns[column_name]


def can_see_private(session: AuthSession) -> bool:
    """Return whether this authenticated session currently has its private gate open."""
    return session.private_until is not None and session.private_until > datetime.now(UTC)


def with_privacy_gate(stmt: Select[Any], model: Any, session: AuthSession) -> Select[Any]:
    """Restrict a query to rows visible through this session's private gate."""
    gate = _declared_gate(model, "__privacy_gate__")
    if gate is Gate.NONE:
        return stmt
    if gate is Gate.VIA_PARENT:
        raise _via_parent_error(model, "__privacy_gate__", "with_privacy_gate")
    is_private = _gate_column(model, "__privacy_gate__", "is_private")
    return stmt if can_see_private(session) else stmt.where(is_private.is_(False))


def not_deleted(stmt: Select[Any], model: Any) -> Select[Any]:
    """Restrict a query to rows that have not been soft-deleted."""
    gate = _declared_gate(model, "__delete_gate__")
    if gate is Gate.NONE:
        return stmt
    if gate is Gate.VIA_PARENT:
        raise _via_parent_error(model, "__delete_gate__", "not_deleted")
    deleted_at = _gate_column(model, "__delete_gate__", "deleted_at")
    return stmt.where(deleted_at.is_(None))


def readable(stmt: Select[Any], model: Any, session: AuthSession) -> Select[Any]:
    """Restrict a parent-entity query by privacy and soft deletion."""
    return not_deleted(with_privacy_gate(stmt, model, session), model)
