"""Expand tracker reminders from medication-only to generic daily schedules.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_and_validate_check(name: str, expression: str) -> None:
    op.execute(
        text(f"ALTER TABLE microsched.tracker ADD CONSTRAINT {name} CHECK ({expression}) NOT VALID")
    )
    op.execute(text(f"ALTER TABLE microsched.tracker VALIDATE CONSTRAINT {name}"))


def upgrade() -> None:
    """Add nullable config, fail on ambiguous legacy rows, then widen checks."""
    bind = op.get_bind()
    ambiguous = bind.execute(
        text(
            """
            SELECT count(*) FROM microsched.tracker
            WHERE reminder_time IS NOT NULL
              AND NOT (kind = 'health' AND input_mode = 'event')
            """
        )
    ).scalar_one()
    if ambiguous:
        raise RuntimeError(
            f"cannot upgrade 0011: found {ambiguous} reminder_time rows outside health+event"
        )

    op.add_column(
        "tracker", sa.Column("reminder_mode", sa.Text(), nullable=True), schema="microsched"
    )
    op.add_column(
        "tracker",
        sa.Column("reminder_interval_days", sa.Integer(), nullable=True),
        schema="microsched",
    )
    op.add_column(
        "tracker", sa.Column("reminder_action", sa.Text(), nullable=True), schema="microsched"
    )
    op.execute(
        text(
            """
            UPDATE microsched.tracker
            SET reminder_mode = 'fixed',
                reminder_interval_days = 1,
                reminder_action = 'confirm_event'
            WHERE kind = 'health'
              AND input_mode = 'event'
              AND reminder_time IS NOT NULL
              AND reminder_mode IS NULL
              AND reminder_interval_days IS NULL
              AND reminder_action IS NULL
            """
        )
    )

    op.drop_constraint("ck_tracker_group_kind_values", "tracker_group", schema="microsched")
    op.execute(
        text(
            "ALTER TABLE microsched.tracker_group "
            "ADD CONSTRAINT ck_tracker_group_kind_values "
            "CHECK (kind IN ('health', 'finance', 'general')) NOT VALID"
        )
    )
    op.execute(
        text(
            "ALTER TABLE microsched.tracker_group VALIDATE CONSTRAINT ck_tracker_group_kind_values"
        )
    )
    op.drop_constraint("ck_tracker_kind_values", "tracker", schema="microsched")
    _add_and_validate_check("ck_tracker_kind_values", "kind IN ('health', 'finance', 'general')")
    _add_and_validate_check(
        "ck_tracker_reminder_mode_values",
        "reminder_mode IS NULL OR reminder_mode IN ('fixed', 'after_entry')",
    )
    _add_and_validate_check(
        "ck_tracker_reminder_interval_days_positive",
        "reminder_interval_days IS NULL OR reminder_interval_days > 0",
    )
    _add_and_validate_check(
        "ck_tracker_reminder_action_values",
        "reminder_action IS NULL OR reminder_action IN ('confirm_event', 'open_tracker')",
    )
    _add_and_validate_check(
        "ck_tracker_reminder_action_input_mode",
        "reminder_action IS NULL OR reminder_action = 'open_tracker' OR "
        "(reminder_action = 'confirm_event' AND input_mode = 'event')",
    )


def downgrade() -> None:
    """Refuse to discard general rows or any non-legacy reminder semantics."""
    op.execute(
        text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM microsched.tracker_group WHERE kind = 'general'
                ) OR EXISTS (
                    SELECT 1 FROM microsched.tracker
                    WHERE kind = 'general'
                       OR reminder_mode = 'after_entry'
                       OR reminder_interval_days IS DISTINCT FROM CASE
                            WHEN reminder_time IS NOT NULL THEN 1 ELSE NULL END
                       OR reminder_action IS DISTINCT FROM CASE
                            WHEN reminder_time IS NOT NULL THEN 'confirm_event' ELSE NULL END
                       OR (reminder_time IS NOT NULL AND NOT (
                            kind = 'health' AND input_mode = 'event'
                       ))
                       OR (reminder_time IS NULL AND (
                            reminder_mode IS NOT NULL OR reminder_interval_days IS NOT NULL
                            OR reminder_action IS NOT NULL OR reminder_text IS NOT NULL
                       ))
                ) THEN
                    RAISE EXCEPTION
                        'cannot downgrade 0011: general or advanced reminder data would be lost'
                        USING ERRCODE = 'check_violation';
                END IF;
            END;
            $$
            """
        )
    )
    for name in (
        "ck_tracker_reminder_action_input_mode",
        "ck_tracker_reminder_action_values",
        "ck_tracker_reminder_interval_days_positive",
        "ck_tracker_reminder_mode_values",
    ):
        op.drop_constraint(name, "tracker", schema="microsched")
    op.drop_constraint("ck_tracker_kind_values", "tracker", schema="microsched")
    op.execute(
        text(
            "ALTER TABLE microsched.tracker ADD CONSTRAINT ck_tracker_kind_values "
            "CHECK (kind IN ('health', 'finance'))"
        )
    )
    op.drop_constraint("ck_tracker_group_kind_values", "tracker_group", schema="microsched")
    op.execute(
        text(
            "ALTER TABLE microsched.tracker_group ADD CONSTRAINT ck_tracker_group_kind_values "
            "CHECK (kind IN ('health', 'finance'))"
        )
    )
    op.drop_column("tracker", "reminder_action", schema="microsched")
    op.drop_column("tracker", "reminder_interval_days", schema="microsched")
    op.drop_column("tracker", "reminder_mode", schema="microsched")
