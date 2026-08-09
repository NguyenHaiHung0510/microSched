"""Reconcile the physical day_annotation CHECK constraint name.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-04 00:00:00.000000

Production may already have revision 0006 with the naming-convention-expanded
constraint name. Fresh databases created from the corrected 0006 already have
the exact physical name ``day_range``.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename only the legacy physical name; leave fresh schemas unchanged."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'microsched.day_annotation'::regclass
                  AND conname = 'ck_day_annotation_day_range'
            )
            AND NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'microsched.day_annotation'::regclass
                  AND conname = 'day_range'
            ) THEN
                ALTER TABLE microsched.day_annotation
                    RENAME CONSTRAINT ck_day_annotation_day_range TO day_range;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    """Restore the legacy name only when the exact name is present alone."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'microsched.day_annotation'::regclass
                  AND conname = 'day_range'
            )
            AND NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'microsched.day_annotation'::regclass
                  AND conname = 'ck_day_annotation_day_range'
            ) THEN
                ALTER TABLE microsched.day_annotation
                    RENAME CONSTRAINT day_range TO ck_day_annotation_day_range;
            END IF;
        END
        $$;
        """
    )
