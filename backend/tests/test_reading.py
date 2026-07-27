"""Unit coverage for explicit read-gate declarations and runtime failures."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.domain.models import (
    AuthSession,
    CalendarSource,
    Entry,
    Gate,
    Task,
    TaskItem,
)
from app.domain.reading import ReadingGateError, not_deleted, readable, with_privacy_gate


def _auth(*, unlocked: bool) -> AuthSession:
    now = datetime.now(UTC)
    return AuthSession(
        token_hash="reading-test-session",
        user_email="owner@example.com",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=(now + timedelta(minutes=15)) if unlocked else None,
    )


def test_none_gate_returns_the_original_statement() -> None:
    """A table with no gate concept is a deliberate, silent no-op."""
    statement = select(CalendarSource)

    assert with_privacy_gate(statement, CalendarSource, _auth(unlocked=False)) is statement
    assert not_deleted(statement, CalendarSource) is statement


def test_task_readable_keeps_existing_privacy_and_delete_filters() -> None:
    """The Task composition still filters locked privacy and every soft delete."""
    locked_sql = str(readable(select(Task), Task, _auth(unlocked=False)))
    unlocked_sql = str(readable(select(Task), Task, _auth(unlocked=True)))

    assert "task.is_private IS false" in locked_sql
    assert "task.deleted_at IS NULL" in locked_sql
    assert "task.is_private IS false" not in unlocked_sql
    assert "task.deleted_at IS NULL" in unlocked_sql


def test_via_parent_privacy_gate_names_the_parent_and_action() -> None:
    """A child declaration cannot be mistaken for permission to skip filtering."""
    with pytest.raises(ReadingGateError) as caught:
        with_privacy_gate(select(Entry), Entry, _auth(unlocked=False))

    message = str(caught.value)
    assert "entry" in message
    assert "Tracker" in message
    assert "JOIN Tracker" in message
    assert "with_privacy_gate(stmt, Tracker, session)" in message


def test_via_parent_delete_gate_names_the_parent_and_action() -> None:
    """Soft deletion inherited from a parent also requires an explicit parent join."""
    with pytest.raises(ReadingGateError) as caught:
        not_deleted(select(TaskItem), TaskItem)

    message = str(caught.value)
    assert "task_item" in message
    assert "Task" in message
    assert "JOIN Task" in message
    assert "not_deleted(stmt, Task)" in message


def test_missing_declaration_raises_with_flag_and_action() -> None:
    """An undeclared model fails loudly instead of inheriting or guessing."""

    class UndeclaredModel:
        pass

    with pytest.raises(ReadingGateError) as caught:
        with_privacy_gate(select(Task), UndeclaredModel, _auth(unlocked=False))

    message = str(caught.value)
    assert "UndeclaredModel" in message
    assert "__privacy_gate__" in message
    assert "Khai Gate.APPLIES" in message


def test_applies_without_column_raises_schema_mismatch() -> None:
    """APPLIES is checked against table metadata before a filter is built."""

    class WrongDeclaration:
        __privacy_gate__ = Gate.APPLIES
        __table__ = CalendarSource.__table__

    with pytest.raises(ReadingGateError) as caught:
        with_privacy_gate(select(CalendarSource), WrongDeclaration, _auth(unlocked=False))

    message = str(caught.value)
    assert "calendar_source" in message
    assert "__privacy_gate__=Gate.APPLIES" in message
    assert "is_private" in message
