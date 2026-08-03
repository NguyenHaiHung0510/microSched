"""Regression tests for one-way physical-schema decisions."""

import asyncio

import asyncpg
import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Text
from sqlmodel import SQLModel

import app.domain.models  # noqa: F401 - importing registers every table
from app.domain.models import Gate

EXPECTED_TABLES = {
    "app_setting",
    "audit_log",
    "calendar_event",
    "calendar_source",
    "day_annotation",
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

GATE_AXES = {
    "__privacy_gate__": "is_private",
    "__delete_gate__": "deleted_at",
}

# Alembic revision bookkeeping created by the migration runner; deliberately has no model.
_NON_DOMAIN_TABLES = frozenset({"alembic_version"})


def table(name: str):
    """Return an application table from SQLModel metadata."""
    return SQLModel.metadata.tables[f"microsched.{name}"]


def table_models() -> dict[str, type[SQLModel]]:
    """Discover every table=True model recursively, without a copied model list."""
    discovered: dict[str, type[SQLModel]] = {}
    pending = [SQLModel]
    seen: set[type[SQLModel]] = set()
    while pending:
        parent = pending.pop()
        for model in parent.__subclasses__():
            if model in seen:
                continue
            seen.add(model)
            pending.append(model)
            model_table = vars(model).get("__table__")
            if model_table is not None:
                assert model_table.fullname not in discovered
                discovered[model_table.fullname] = model
    return discovered


def assert_gate_declarations_match_columns(
    models: dict[str, type[SQLModel]],
    columns_by_table: dict[str, set[str]],
) -> None:
    """Check both gate axes and every VIA_PARENT FK contract."""
    for fullname, model in models.items():
        table_name = fullname.removeprefix("microsched.")
        for flag_name, column_name in GATE_AXES.items():
            assert flag_name in vars(model), f"{table_name} chưa khai {flag_name}"
            gate = vars(model)[flag_name]
            assert isinstance(gate, Gate), f"{table_name}.{flag_name} phải là Gate, nhận {gate!r}"
            has_column = column_name in columns_by_table[fullname]
            assert (gate is Gate.APPLIES) == has_column, (
                f"{table_name}.{flag_name}={gate.name} nhưng "
                f"{'có' if has_column else 'không có'} cột {column_name}"
            )

            for foreign_key in vars(model)["__table__"].foreign_keys:
                parent_table = foreign_key.column.table
                parent_model = models.get(parent_table.fullname)
                if parent_model is None:
                    continue
                parent_gate = vars(parent_model).get(flag_name)
                if parent_gate not in {Gate.APPLIES, Gate.VIA_PARENT}:
                    continue
                assert gate is not Gate.NONE, (
                    f"{model.__name__}.{flag_name}=Gate.NONE nhưng parent "
                    f"{parent_model.__name__}.{flag_name}=Gate.{parent_gate.name}; "
                    f"đổi {model.__name__}.{flag_name} thành Gate.VIA_PARENT"
                )

            if gate is not Gate.VIA_PARENT:
                continue
            model_table = vars(model)["__table__"]
            parent_fullnames = {
                foreign_key.column.table.fullname for foreign_key in model_table.foreign_keys
            }
            guarded_parents = [
                parent_name
                for parent_name in parent_fullnames
                if parent_name in models
                and vars(models[parent_name]).get(flag_name) is Gate.APPLIES
            ]
            assert guarded_parents, (
                f"{table_name}.{flag_name}=VIA_PARENT nhưng không có FK tới "
                "model cha khai APPLIES trên cùng trục"
            )


def test_reading_gate_declarations_match_metadata() -> None:
    """Every model declares both axes and the declarations match ORM schema metadata."""
    models = table_models()
    metadata_tables = {
        item.fullname: {column.name for column in item.columns}
        for item in SQLModel.metadata.tables.values()
    }

    assert set(models) == set(metadata_tables)
    assert_gate_declarations_match_columns(models, metadata_tables)


@pytest.mark.pg
def test_reading_gate_registry_matches_live_schema(pg_dsn: str) -> None:
    """The live schema has exactly the modeled tables and matching gate columns."""

    async def scenario() -> None:
        connection = await asyncpg.connect(pg_dsn)
        try:
            table_rows = await connection.fetch(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'microsched'
                  AND table_type = 'BASE TABLE'
                """
            )
            column_rows = await connection.fetch(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'microsched'
                """
            )
        finally:
            await connection.close()

        models = table_models()
        db_tables = {f"microsched.{row['table_name']}" for row in table_rows}
        domain_db_tables = {
            t for t in db_tables if t.removeprefix("microsched.") not in _NON_DOMAIN_TABLES
        }
        columns_by_table = {table_name: set() for table_name in db_tables}
        for row in column_rows:
            columns_by_table[f"microsched.{row['table_name']}"].add(row["column_name"])

        assert domain_db_tables == set(models)
        assert_gate_declarations_match_columns(models, columns_by_table)

    asyncio.run(scenario())


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


def test_calendar_010a_columns_are_nullable_or_defaulted_as_locked() -> None:
    """The 010a migration seam is visible in ORM metadata before a live DB exists."""
    source = table("calendar_source")
    event = table("calendar_event")
    assert source.c.is_visible.nullable is False
    assert str(source.c.is_visible.server_default.arg) == "true"
    assert event.c.description_md.nullable is True
    assert event.c.all_day.nullable is False
    assert str(event.c.all_day.server_default.arg) == "false"


def test_day_annotation_0006_shape_is_locked() -> None:
    """The 010b table is a DATE-range marker with the privacy gate from day one."""
    annotation = table("day_annotation")

    assert annotation.c.starts_on.nullable is False
    assert annotation.c.ends_on.nullable is False
    assert annotation.c.label.nullable is False
    assert annotation.c.is_private.nullable is False
    assert str(annotation.c.is_private.server_default.arg) == "false"
    assert annotation.c.note_md.nullable is True
    assert annotation.c.color.nullable is True
    assert not hasattr(annotation.c, "deleted_at")

    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in annotation.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_day_annotation_day_range" in checks
    assert "ends_on >= starts_on" in checks["ck_day_annotation_day_range"]

    index_columns = {index.name: [c.name for c in index.columns] for index in annotation.indexes}
    assert index_columns["ix_day_annotation_starts_on"] == ["starts_on"]
    assert index_columns["ix_day_annotation_ends_on"] == ["ends_on"]
