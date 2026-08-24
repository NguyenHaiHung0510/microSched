"""Expand task scheduling to preserve date-only precision.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-24 00:00:00.000000

This is the compatibility/expand phase only. The columns intentionally remain
nullable until 026B can prove that every serving binary is a V2 writer.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the temporal triad and protect the rolling old-writer window."""
    op.add_column(
        "task",
        sa.Column("due_precision", sa.Text(), nullable=True),
        schema="microsched",
    )
    op.add_column(
        "task",
        sa.Column("due_on", sa.Date(), nullable=True),
        schema="microsched",
    )
    op.execute(
        """
        UPDATE microsched.task
        SET due_precision = CASE
            WHEN due_at IS NULL THEN 'none'
            ELSE 'datetime'
        END,
            due_on = NULL
        """
    )
    op.create_index("ix_task_due_on", "task", ["due_on"], schema="microsched")

    op.execute(
        """
        CREATE FUNCTION microsched.fn_task_due_legacy_insert_v1()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF current_setting('microsched.task_due_writer', true) = 'v2' THEN
                RETURN NEW;
            END IF;

            IF NEW.due_at IS NULL THEN
                NEW.due_precision := 'none';
            ELSE
                NEW.due_precision := 'datetime';
            END IF;
            NEW.due_on := NULL;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_task_due_legacy_insert_v1
        BEFORE INSERT ON microsched.task
        FOR EACH ROW
        EXECUTE FUNCTION microsched.fn_task_due_legacy_insert_v1()
        """
    )
    op.execute(
        """
        CREATE FUNCTION microsched.fn_task_due_legacy_update_v1()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF current_setting('microsched.task_due_writer', true) = 'v2' THEN
                RETURN NEW;
            END IF;

            IF NEW.due_at IS NULL THEN
                NEW.due_precision := 'none';
            ELSE
                NEW.due_precision := 'datetime';
            END IF;
            NEW.due_on := NULL;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_task_due_legacy_update_v1
        BEFORE UPDATE OF due_at ON microsched.task
        FOR EACH ROW
        EXECUTE FUNCTION microsched.fn_task_due_legacy_update_v1()
        """
    )


def downgrade() -> None:
    """Remove the expand seam only when doing so cannot discard a civil date."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM microsched.task
                WHERE due_precision = 'date' OR due_on IS NOT NULL
            ) THEN
                RAISE EXCEPTION
                    'cannot downgrade 0010: date-only task scheduling would be lost'
                    USING ERRCODE = 'check_violation';
            END IF;
        END;
        $$
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_task_due_legacy_update_v1 ON microsched.task")
    op.execute("DROP FUNCTION IF EXISTS microsched.fn_task_due_legacy_update_v1()")
    op.execute("DROP TRIGGER IF EXISTS trg_task_due_legacy_insert_v1 ON microsched.task")
    op.execute("DROP FUNCTION IF EXISTS microsched.fn_task_due_legacy_insert_v1()")
    op.drop_index("ix_task_due_on", table_name="task", schema="microsched")
    op.drop_column("task", "due_on", schema="microsched")
    op.drop_column("task", "due_precision", schema="microsched")
