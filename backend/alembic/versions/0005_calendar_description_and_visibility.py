"""Add calendar descriptions, source visibility, and all-day events.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the calendar fields required by the 010a slice."""
    op.add_column(
        "calendar_event",
        sa.Column("description_md", sa.Text(), nullable=True),
        schema="microsched",
    )
    op.add_column(
        "calendar_event",
        sa.Column(
            "all_day",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema="microsched",
    )
    op.add_column(
        "calendar_source",
        sa.Column(
            "is_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        schema="microsched",
    )


def downgrade() -> None:
    """Remove only the three 010a calendar columns."""
    op.drop_column("calendar_source", "is_visible", schema="microsched")
    op.drop_column("calendar_event", "all_day", schema="microsched")
    op.drop_column("calendar_event", "description_md", schema="microsched")
