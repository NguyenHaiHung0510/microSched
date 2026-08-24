"""Preserve legacy task completion and note organization fields.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the three destinations required by the legacy-data cutover."""
    op.add_column(
        "task",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema="microsched",
    )
    op.add_column(
        "note",
        sa.Column(
            "pinned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema="microsched",
    )
    op.add_column(
        "note",
        sa.Column("priority", sa.Text(), nullable=True),
        schema="microsched",
    )
    op.create_check_constraint(
        "priority_values",
        "note",
        "priority IS NULL OR priority IN ('p1', 'p2', 'p3')",
        schema="microsched",
    )


def downgrade() -> None:
    """Remove the cutover destination columns."""
    op.drop_constraint(
        op.f("ck_note_priority_values"),
        "note",
        schema="microsched",
        type_="check",
    )
    op.drop_column("note", "priority", schema="microsched")
    op.drop_column("note", "pinned", schema="microsched")
    op.drop_column("task", "completed_at", schema="microsched")
