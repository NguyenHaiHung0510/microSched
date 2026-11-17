"""migarden zone a

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-17 23:48:49.053027
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def audit_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "migarden_boot",
        *audit_columns(),
        sa.Column("boot_id", sa.String(length=128), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_migarden_boot")),
        sa.UniqueConstraint("boot_id", name=op.f("uq_migarden_boot_boot_id")),
        schema="microsched",
    )
    op.create_table(
        "migarden_config",
        *audit_columns(),
        sa.Column("config_ref", sa.String(length=128), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "bundle", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_migarden_config")),
        sa.UniqueConstraint("config_ref", name=op.f("uq_migarden_config_config_ref")),
        schema="microsched",
    )
    op.create_table(
        "migarden_report",
        *audit_columns(),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("boot_id", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("config_ref", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=True),
        sa.Column("result", sa.String(length=24), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "body", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_migarden_report")),
        sa.UniqueConstraint("event_id", name=op.f("uq_migarden_report_event_id")),
        sa.UniqueConstraint("boot_id", "sequence", name="uq_migarden_report_boot_sequence"),
        schema="microsched",
    )
    op.create_index(
        "ix_migarden_report_history",
        "migarden_report",
        ["kind", "sort_at", "event_id"],
        unique=False,
        schema="microsched",
    )
    op.create_index(
        "ix_migarden_report_kind_ref",
        "migarden_report",
        ["kind", "config_ref"],
        unique=False,
        schema="microsched",
    )
    op.create_table(
        "migarden_command",
        *audit_columns(),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("session_owner_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("config_ref", sa.String(), nullable=True),
        sa.Column("boot_id", sa.String(length=128), nullable=False),
        sa.Column("control_epoch", sa.BigInteger(), nullable=False),
        sa.Column("candidate_offered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grant_id", sa.String(length=128), nullable=True),
        sa.Column("last_report_sequence", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("kind IN ('start', 'stop')", name=op.f("ck_migarden_command_kind")),
        sa.ForeignKeyConstraint(
            ["config_ref"],
            ["microsched.migarden_config.config_ref"],
            name=op.f("fk_migarden_command_config_ref_migarden_config"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_migarden_command")),
        sa.UniqueConstraint("request_id", name=op.f("uq_migarden_command_request_id")),
        schema="microsched",
    )
    op.create_index(
        "ix_migarden_command_inflight",
        "migarden_command",
        ["kind", "status"],
        unique=False,
        schema="microsched",
        postgresql_where=sa.text(
            "status IN ('pending', 'received', 'granted', 'started', 'unknown', "
            "'stop_requested', 'stop_received')"
        ),
    )
    op.create_index(
        "ix_migarden_command_kind_confirmed",
        "migarden_command",
        ["kind", "confirmed_at", "request_id"],
        unique=False,
        schema="microsched",
    )
    op.create_table(
        "migarden_session",
        *audit_columns(),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("boot_id", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("config_ref", sa.String(length=128), nullable=False),
        sa.Column("planned_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("reason", sa.String(length=256), nullable=True),
        sa.Column("started_event_id", sa.String(), nullable=True),
        sa.Column("ended_event_id", sa.String(), nullable=True),
        sa.Column("start_sort_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_sort_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["ended_event_id"],
            ["microsched.migarden_report.event_id"],
            name=op.f("fk_migarden_session_ended_event_id_migarden_report"),
        ),
        sa.ForeignKeyConstraint(
            ["started_event_id"],
            ["microsched.migarden_report.event_id"],
            name=op.f("fk_migarden_session_started_event_id_migarden_report"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_migarden_session")),
        sa.UniqueConstraint("session_id", name=op.f("uq_migarden_session_session_id")),
        sa.UniqueConstraint("request_id", name=op.f("uq_migarden_session_request_id")),
        schema="microsched",
    )
    op.create_index(
        "ix_migarden_session_end_history",
        "migarden_session",
        ["end_sort_at", "session_id"],
        unique=False,
        schema="microsched",
    )
    op.create_index(
        "ix_migarden_session_start_history",
        "migarden_session",
        ["start_sort_at", "session_id"],
        unique=False,
        schema="microsched",
    )
    op.create_index(
        "ix_migarden_session_terminal",
        "migarden_session",
        ["ended_at", "session_id"],
        unique=False,
        schema="microsched",
    )
    op.create_index(
        "ix_migarden_session_unresolved",
        "migarden_session",
        ["session_id"],
        unique=False,
        schema="microsched",
        postgresql_where=sa.text("outcome IS NULL OR outcome = 'unknown'"),
    )
    op.create_table(
        "migarden_zone",
        *audit_columns(),
        sa.Column("zone_id", sa.String(length=32), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=True),
        sa.Column("device_environment", sa.String(length=16), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("desired_ref", sa.String(), nullable=True),
        sa.Column("applied_ref", sa.String(), nullable=True),
        sa.Column("applied_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("boot_id", sa.String(length=128), nullable=True),
        sa.Column("control_epoch", sa.BigInteger(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "snapshot", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "preview", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "unidentified_execution", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.CheckConstraint(
            "device_environment IN ('qa', 'production')",
            name=op.f("ck_migarden_zone_device_environment"),
        ),
        sa.CheckConstraint("zone_id = 'zone-a'", name=op.f("ck_migarden_zone_single_binding")),
        sa.CheckConstraint(
            "(device_id IS NULL) = (device_environment IS NULL)"
            " AND (device_id IS NULL) = (token_hash IS NULL)",
            name=op.f("ck_migarden_zone_credential_complete"),
        ),
        sa.ForeignKeyConstraint(
            ["applied_ref"],
            ["microsched.migarden_config.config_ref"],
            name=op.f("fk_migarden_zone_applied_ref_migarden_config"),
        ),
        sa.ForeignKeyConstraint(
            ["desired_ref"],
            ["microsched.migarden_config.config_ref"],
            name=op.f("fk_migarden_zone_desired_ref_migarden_config"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_migarden_zone")),
        sa.UniqueConstraint("zone_id", name=op.f("uq_migarden_zone_zone_id")),
        schema="microsched",
    )
    for table in ("migarden_command", "migarden_session", "migarden_zone"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON microsched.{table} "
            "FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at()"
        )
    # Configuration and raw receipt identity must survive runtime mistakes.
    op.execute(
        "REVOKE UPDATE, DELETE, TRUNCATE ON microsched.migarden_config, "
        "microsched.migarden_report, microsched.migarden_boot FROM microsched_app"
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_table("migarden_zone", schema="microsched")
    op.drop_index(
        "ix_migarden_session_unresolved",
        table_name="migarden_session",
        schema="microsched",
        postgresql_where=sa.text("outcome IS NULL OR outcome = 'unknown'"),
    )
    op.drop_index(
        "ix_migarden_session_terminal", table_name="migarden_session", schema="microsched"
    )
    op.drop_index(
        "ix_migarden_session_start_history", table_name="migarden_session", schema="microsched"
    )
    op.drop_index(
        "ix_migarden_session_end_history", table_name="migarden_session", schema="microsched"
    )
    op.drop_table("migarden_session", schema="microsched")
    op.drop_index(
        "ix_migarden_command_kind_confirmed", table_name="migarden_command", schema="microsched"
    )
    op.drop_index(
        "ix_migarden_command_inflight",
        table_name="migarden_command",
        schema="microsched",
        postgresql_where=sa.text(
            "status IN ('pending', 'received', 'granted', 'started', 'unknown', "
            "'stop_requested', 'stop_received')"
        ),
    )
    op.drop_table("migarden_command", schema="microsched")
    op.drop_index("ix_migarden_report_kind_ref", table_name="migarden_report", schema="microsched")
    op.drop_index("ix_migarden_report_history", table_name="migarden_report", schema="microsched")
    op.drop_table("migarden_report", schema="microsched")
    op.drop_table("migarden_config", schema="microsched")
    op.drop_table("migarden_boot", schema="microsched")
