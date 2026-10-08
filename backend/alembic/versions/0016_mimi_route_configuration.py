"""Persist owner-selected per-conversation route, never credentials.

Revision ID: 0016
Revises: 0015
"""

from sqlalchemy import text

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE microsched.mimi_conversation
ADD COLUMN route_config JSONB NOT NULL DEFAULT '{}'::jsonb,
ADD COLUMN route_config_version INTEGER NOT NULL DEFAULT 1,
ADD CONSTRAINT ck_mimi_conversation_route_config_version CHECK (route_config_version >= 1),
ADD CONSTRAINT ck_mimi_conversation_route_config_object
    CHECK (jsonb_typeof(route_config) = 'object')
""")


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(text("SELECT EXISTS(SELECT 1 FROM microsched.mimi_conversation)"))
        .scalar()
    ):
        raise RuntimeError(
            "refusing to drop Mimi route configuration while conversation rows exist"
        )
    op.execute("""
ALTER TABLE microsched.mimi_conversation
DROP CONSTRAINT ck_mimi_conversation_route_config_object,
DROP CONSTRAINT ck_mimi_conversation_route_config_version,
DROP COLUMN route_config_version, DROP COLUMN route_config
""")
