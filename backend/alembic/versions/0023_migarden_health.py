"""Optional hourly health evidence; additive and compatible with the old app."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "migarden_health",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("zone_id", sa.String(32), nullable=False),
        sa.Column("hour_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("boot_id", sa.String(128), nullable=False),
        sa.Column("sample", postgresql.JSONB(none_as_null=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_migarden_health")),
        sa.UniqueConstraint("zone_id", "hour_start", name="uq_migarden_health_zone_hour"),
        sa.CheckConstraint("zone_id = 'zone-a'", name=op.f("ck_migarden_health_single_binding")),
        schema="microsched",
    )
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON microsched.migarden_health FROM microsched_app")


def downgrade() -> None:
    # Throwaway local/CI round trips only. Rollback production keeps this table.
    op.drop_table("migarden_health", schema="microsched")
