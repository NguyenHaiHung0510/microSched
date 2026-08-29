"""Add durable tracker reminder batching and terminal outcomes.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _preflight_fractional_tracker_times() -> None:
    count = (
        op.get_bind()
        .execute(
            text(
                """
            SELECT count(*)
            FROM microsched.tracker
            WHERE reminder_time IS NOT NULL
              AND (EXTRACT(MICROSECONDS FROM reminder_time)::bigint % 1000000) <> 0
            """
            )
        )
        .scalar_one()
    )
    if count:
        raise RuntimeError(f"cannot upgrade 0012: found {count} fractional reminder_time rows")


def upgrade() -> None:
    """Add the whole-second guard, widen dispatch status, and create batch tables."""
    _preflight_fractional_tracker_times()
    op.execute(
        text(
            "ALTER TABLE microsched.tracker "
            "ADD CONSTRAINT ck_tracker_reminder_time_whole_second "
            "CHECK (reminder_time IS NULL OR "
            "(EXTRACT(MICROSECONDS FROM reminder_time)::bigint % 1000000) = 0) NOT VALID"
        )
    )
    op.execute(
        text(
            "ALTER TABLE microsched.tracker "
            "VALIDATE CONSTRAINT ck_tracker_reminder_time_whole_second"
        )
    )

    op.drop_constraint("ck_reminder_dispatch_status", "reminder_dispatch", schema="microsched")
    op.execute(
        text(
            "ALTER TABLE microsched.reminder_dispatch "
            "ADD CONSTRAINT ck_reminder_dispatch_status "
            "CHECK (status IN ('pending', 'sent', 'no_device', 'cancelled', 'exhausted'))"
        )
    )

    op.create_table(
        "tracker_reminder_batch",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("occurrence_on", sa.Date(), nullable=False),
        sa.Column("reminder_time", sa.Time(), nullable=False),
        sa.Column("generation", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tracker_reminder_batch")),
        sa.UniqueConstraint(
            "occurrence_on",
            "reminder_time",
            "generation",
            name=op.f("uq_tracker_reminder_batch_occurrence_time_generation"),
        ),
        sa.CheckConstraint("generation >= 1", name=op.f("ck_tracker_reminder_batch_generation")),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'no_device', 'cancelled', 'exhausted')",
            name=op.f("ck_tracker_reminder_batch_status"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= 4",
            name=op.f("ck_tracker_reminder_batch_attempt_count"),
        ),
        sa.CheckConstraint(
            "(EXTRACT(MICROSECONDS FROM reminder_time)::bigint % 1000000) = 0",
            name=op.f("ck_tracker_reminder_batch_time_whole_second"),
        ),
        schema="microsched",
    )
    op.create_index(
        "ix_tracker_reminder_batch_status",
        "tracker_reminder_batch",
        ["status"],
        unique=False,
        schema="microsched",
    )

    op.create_table(
        "tracker_reminder_batch_item",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("batch_id", sa.UUID(), nullable=False),
        sa.Column("dispatch_id", sa.UUID(), nullable=False),
        sa.Column("reminder_mode", sa.Text(), nullable=False),
        sa.Column("reminder_interval_days", sa.Integer(), nullable=False),
        sa.Column("reminder_action", sa.Text(), nullable=False),
        sa.Column("input_mode", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tracker_reminder_batch_item")),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["microsched.tracker_reminder_batch.id"],
            name=op.f("fk_tracker_reminder_batch_item_batch_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dispatch_id"],
            ["microsched.reminder_dispatch.id"],
            name=op.f("fk_tracker_reminder_batch_item_dispatch_id"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "batch_id",
            "dispatch_id",
            name=op.f("uq_tracker_reminder_batch_item_batch_dispatch"),
        ),
        sa.UniqueConstraint("dispatch_id", name=op.f("uq_tracker_reminder_batch_item_dispatch_id")),
        sa.CheckConstraint(
            "reminder_mode IN ('fixed', 'after_entry')",
            name=op.f("ck_tracker_reminder_batch_item_reminder_mode"),
        ),
        sa.CheckConstraint(
            "reminder_interval_days >= 1",
            name=op.f("ck_tracker_reminder_batch_item_reminder_interval_days"),
        ),
        sa.CheckConstraint(
            "reminder_action IN ('confirm_event', 'open_tracker')",
            name=op.f("ck_tracker_reminder_batch_item_reminder_action"),
        ),
        sa.CheckConstraint(
            "input_mode IN ('event', 'money', 'quantity')",
            name=op.f("ck_tracker_reminder_batch_item_input_mode"),
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'sent', 'no_device', 'cancelled', 'exhausted')",
            name=op.f("ck_tracker_reminder_batch_item_state"),
        ),
        schema="microsched",
    )

    for table_name in ("tracker_reminder_batch", "tracker_reminder_batch_item"):
        op.execute(
            text(
                f"CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.{table_name} "
                "FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at()"
            )
        )
        op.execute(text(f"ALTER TABLE microsched.{table_name} OWNER TO microsched_migrator"))
        op.execute(text(f"REVOKE ALL ON TABLE microsched.{table_name} FROM PUBLIC"))
        op.execute(
            text(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE microsched.{table_name} "
                "TO microsched_app"
            )
        )


def downgrade() -> None:
    """Fail before DDL when any 0012 data or widened terminal state would be lost."""
    op.execute(
        text(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM microsched.tracker_reminder_batch)
                   OR EXISTS (SELECT 1 FROM microsched.tracker_reminder_batch_item)
                   OR EXISTS (
                       SELECT 1 FROM microsched.reminder_dispatch
                       WHERE status IN ('cancelled', 'exhausted')
                   ) THEN
                    RAISE EXCEPTION 'cannot downgrade 0012: batching or terminal data would be lost'
                        USING ERRCODE = 'check_violation';
                END IF;
            END;
            $$
            """
        )
    )

    op.execute("DROP TRIGGER IF EXISTS set_updated_at ON microsched.tracker_reminder_batch_item")
    op.execute("DROP TRIGGER IF EXISTS set_updated_at ON microsched.tracker_reminder_batch")
    op.drop_table("tracker_reminder_batch_item", schema="microsched")
    op.drop_index(
        "ix_tracker_reminder_batch_status",
        table_name="tracker_reminder_batch",
        schema="microsched",
    )
    op.drop_table("tracker_reminder_batch", schema="microsched")
    op.drop_constraint("ck_tracker_reminder_time_whole_second", "tracker", schema="microsched")
    op.drop_constraint("ck_reminder_dispatch_status", "reminder_dispatch", schema="microsched")
    op.execute(
        text(
            "ALTER TABLE microsched.reminder_dispatch "
            "ADD CONSTRAINT ck_reminder_dispatch_status "
            "CHECK (status IN ('pending', 'sent', 'no_device'))"
        )
    )
