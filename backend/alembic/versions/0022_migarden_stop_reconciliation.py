"""Add bounded STOP provenance and failed-ingest reconciliation, preserving 0021."""

import sqlalchemy as sa

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "migarden_zone",
        sa.Column("stop_target_boot_id", sa.String(length=128), nullable=True),
        schema="microsched",
    )
    op.add_column(
        "migarden_zone",
        sa.Column("stop_target_epoch", sa.BigInteger(), nullable=True),
        schema="microsched",
    )
    op.add_column(
        "migarden_zone",
        sa.Column(
            "report_reconciliation", sa.dialects.postgresql.JSONB(none_as_null=True), nullable=True
        ),
        schema="microsched",
    )
    op.drop_index(
        "ix_migarden_command_inflight", table_name="migarden_command", schema="microsched"
    )
    op.create_index(
        "ix_migarden_command_inflight",
        "migarden_command",
        ["kind", "status"],
        schema="microsched",
        postgresql_where=sa.text(
            "status IN ('pending', 'received', 'granted', 'started', 'unknown', "
            "'stop_requested', 'stop_received', 'stop_unconfirmed')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_migarden_command_inflight", table_name="migarden_command", schema="microsched"
    )
    op.create_index(
        "ix_migarden_command_inflight",
        "migarden_command",
        ["kind", "status"],
        schema="microsched",
        postgresql_where=sa.text(
            "status IN ('pending', 'received', 'granted', 'started', 'unknown', "
            "'stop_requested', 'stop_received')"
        ),
    )
    op.drop_column("migarden_zone", "report_reconciliation", schema="microsched")
    op.drop_column("migarden_zone", "stop_target_epoch", schema="microsched")
    op.drop_column("migarden_zone", "stop_target_boot_id", schema="microsched")
