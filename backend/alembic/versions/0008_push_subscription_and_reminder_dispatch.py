"""Add push_subscription and reminder_dispatch tables for Web Push and Dispatcher.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create push_subscription and reminder_dispatch tables with indexes and constraints."""
    op.create_table(
        "push_subscription",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
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
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscription")),
        sa.UniqueConstraint("endpoint", name=op.f("uq_push_subscription_endpoint")),
        schema="microsched",
    )
    op.create_index(
        "ix_push_subscription_endpoint",
        "push_subscription",
        ["endpoint"],
        unique=False,
        schema="microsched",
    )

    op.create_table(
        "reminder_dispatch",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("dispatched_on", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_entry_id", sa.UUID(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminder_dispatch")),
        sa.UniqueConstraint(
            "subject_type",
            "subject_id",
            "dispatched_on",
            name=op.f("uq_reminder_dispatch_subject_date"),
        ),
        sa.UniqueConstraint(
            "confirmed_entry_id",
            name=op.f("uq_reminder_dispatch_confirmed_entry_id"),
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_entry_id"],
            ["microsched.entry.id"],
            name=op.f("fk_reminder_dispatch_confirmed_entry_id"),
        ),
        sa.CheckConstraint(
            "subject_type IN ('tracker', 'subscription')",
            name=op.f("ck_reminder_dispatch_subject_type"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'no_device')",
            name=op.f("ck_reminder_dispatch_status"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_reminder_dispatch_attempt_count"),
        ),
        schema="microsched",
    )
    op.create_index(
        "ix_reminder_dispatch_subject",
        "reminder_dispatch",
        ["subject_type", "subject_id"],
        unique=False,
        schema="microsched",
    )
    op.create_index(
        "ix_reminder_dispatch_status",
        "reminder_dispatch",
        ["status"],
        unique=False,
        schema="microsched",
    )
    op.execute(
        "CREATE TRIGGER set_updated_at "
        "BEFORE UPDATE ON microsched.push_subscription "
        "FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at()"
    )
    op.execute(
        "CREATE TRIGGER set_updated_at "
        "BEFORE UPDATE ON microsched.reminder_dispatch "
        "FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at()"
    )


def downgrade() -> None:
    """Drop reminder_dispatch and push_subscription tables and indexes."""
    op.execute("DROP TRIGGER IF EXISTS set_updated_at ON microsched.reminder_dispatch")
    op.drop_index(
        "ix_reminder_dispatch_status",
        table_name="reminder_dispatch",
        schema="microsched",
    )
    op.drop_index(
        "ix_reminder_dispatch_subject",
        table_name="reminder_dispatch",
        schema="microsched",
    )
    op.drop_table("reminder_dispatch", schema="microsched")

    op.execute("DROP TRIGGER IF EXISTS set_updated_at ON microsched.push_subscription")
    op.drop_index(
        "ix_push_subscription_endpoint",
        table_name="push_subscription",
        schema="microsched",
    )
    op.drop_table("push_subscription", schema="microsched")
