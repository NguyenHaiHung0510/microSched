"""Regression tests for one-way physical-schema decisions."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Text
from sqlmodel import SQLModel

import app.domain.models  # noqa: F401 - importing registers every table

EXPECTED_TABLES = {
    "app_setting",
    "audit_log",
    "calendar_event",
    "calendar_source",
    "entry",
    "message",
    "note",
    "note_item",
    "session",
    "subscription",
    "task",
    "task_item",
    "tracker",
    "tracker_group",
}


def table(name: str):
    """Return an application table from SQLModel metadata."""
    return SQLModel.metadata.tables[f"microsched.{name}"]


def test_every_table_uses_uuidv7_and_uniform_timestamps() -> None:
    """B1/B2 apply without an app_setting or child-table exception."""
    assert {item.name for item in SQLModel.metadata.tables.values()} == EXPECTED_TABLES

    for item in SQLModel.metadata.tables.values():
        assert item.c.id.primary_key
        assert str(item.c.id.server_default.arg) == "uuidv7()"
        assert item.c.created_at.type.timezone is True
        assert item.c.updated_at.type.timezone is True


def test_vector_placeholder_has_no_dimension_or_index() -> None:
    """Embedding model coupling remains deferred to AI Step 1."""
    note = table("note")

    assert isinstance(note.c.embedding.type, Vector)
    assert note.c.embedding.type.dim is None
    assert all("embedding" not in index.columns for index in note.indexes)


def test_encrypted_money_is_text_and_names_are_not_unique() -> None:
    """K18-K20 keep ciphertext out of numeric and deterministic-name constraints."""
    entry = table("entry")
    tracker = table("tracker")
    subscription = table("subscription")

    assert isinstance(entry.c.amount.type, Text)
    assert isinstance(entry.c.list_amount.type, Text)
    assert isinstance(subscription.c.amount.type, Text)
    assert not any(index.unique and "name" in index.columns for index in tracker.indexes)
    assert not any(index.unique and "name" in index.columns for index in subscription.indexes)


def test_private_note_requires_ciphertext_title_and_body() -> None:
    """A private note hides title as well as body: note now matches task (§6, 2026-07-23).

    The invariant is DB-enforced (unlike note_item/task_item, which are app-side per §6);
    this test guards the ORM half so a rename or a dropped clause fails loudly here.
    """
    note = table("note")

    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in note.constraints
        if isinstance(constraint, CheckConstraint)
    }

    # Renamed to match task's private_ciphertext; the old body-only name is gone.
    assert "ck_note_private_ciphertext" in checks
    assert "ck_note_private_body_ciphertext" not in checks

    condition = checks["ck_note_private_ciphertext"]
    assert "title IS NULL OR title LIKE 'enc:v1:%'" in condition
    assert "body_md IS NULL OR body_md LIKE 'enc:v1:%'" in condition


def test_app_setting_has_uuid_identity_and_unique_key() -> None:
    """K24 keeps app_setting on the common UUID base while preserving key lookup."""
    setting = table("app_setting")

    assert setting.c.id.primary_key
    assert any(constraint.name == "uq_app_setting_key" for constraint in setting.constraints)
