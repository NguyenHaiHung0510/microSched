"""Add the day_annotation table for 010b calendar markers.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-03 00:00:00.000000

``day_annotation`` stores date-range markers that have no clock time and no
timezone. It is the first table added since 0001, so it also receives the
shared ``set_updated_at`` trigger that every other domain table already has.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create day_annotation with its inclusive-range check and lookup indexes."""
    op.create_table(
        "day_annotation",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("note_md", sa.Text(), nullable=True),
        sa.Column("color", sa.Text(), nullable=True),
        sa.Column(
            "is_private",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ends_on >= starts_on",
            name=op.f("day_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_day_annotation")),
        schema="microsched",
    )
    op.create_index(
        "ix_day_annotation_starts_on",
        "day_annotation",
        ["starts_on"],
        unique=False,
        schema="microsched",
    )
    op.create_index(
        "ix_day_annotation_ends_on",
        "day_annotation",
        ["ends_on"],
        unique=False,
        schema="microsched",
    )
    op.execute(
        "CREATE TRIGGER set_updated_at "
        "BEFORE UPDATE ON microsched.day_annotation "
        "FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at()"
    )


def downgrade() -> None:
    """Drop the trigger and the day_annotation table."""
    op.execute("DROP TRIGGER set_updated_at ON microsched.day_annotation")
    op.drop_index(
        "ix_day_annotation_ends_on",
        table_name="day_annotation",
        schema="microsched",
    )
    op.drop_index(
        "ix_day_annotation_starts_on",
        table_name="day_annotation",
        schema="microsched",
    )
    op.drop_table("day_annotation", schema="microsched")
