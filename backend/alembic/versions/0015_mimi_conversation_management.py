"""Add encrypted Mimi conversation presentation metadata.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-17
"""

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        text(
            """
ALTER TABLE microsched.mimi_conversation
    ADD COLUMN client_id TEXT,
    ADD COLUMN title_ciphertext TEXT,
    ADD COLUMN title_source TEXT NOT NULL DEFAULT 'auto',
    ADD COLUMN title_locked BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN metadata_version INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN archived_at TIMESTAMPTZ,
    ADD CONSTRAINT ck_mimi_conversation_title_ciphertext
        CHECK (title_ciphertext IS NULL OR title_ciphertext LIKE 'mimi:v1:%'),
    ADD CONSTRAINT ck_mimi_conversation_title_source
        CHECK (title_source IN ('auto', 'owner')),
    ADD CONSTRAINT ck_mimi_conversation_title_lock
        CHECK ((title_source = 'owner') = title_locked),
    ADD CONSTRAINT ck_mimi_conversation_metadata_version
        CHECK (metadata_version >= 1)
"""
        )
    )
    op.execute(
        text(
            """
CREATE INDEX ix_mimi_conversation_owner_archive_updated
    ON microsched.mimi_conversation(owner_id, archived_at, updated_at DESC, id DESC)
"""
        )
    )
    op.execute(
        text(
            """
CREATE UNIQUE INDEX uq_mimi_conversation_owner_client
    ON microsched.mimi_conversation(owner_id, client_id)
    WHERE client_id IS NOT NULL
"""
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(text("SELECT EXISTS(SELECT 1 FROM microsched.mimi_conversation)")).scalar():
        raise RuntimeError(
            "refusing to drop Mimi conversation metadata while conversation rows exist"
        )
    op.execute(text("DROP INDEX IF EXISTS microsched.ix_mimi_conversation_owner_archive_updated"))
    op.execute(text("DROP INDEX IF EXISTS microsched.uq_mimi_conversation_owner_client"))
    op.execute(
        text(
            """
ALTER TABLE microsched.mimi_conversation
    DROP CONSTRAINT IF EXISTS ck_mimi_conversation_metadata_version,
    DROP CONSTRAINT IF EXISTS ck_mimi_conversation_title_lock,
    DROP CONSTRAINT IF EXISTS ck_mimi_conversation_title_source,
    DROP CONSTRAINT IF EXISTS ck_mimi_conversation_title_ciphertext,
    DROP COLUMN IF EXISTS archived_at,
    DROP COLUMN IF EXISTS metadata_version,
    DROP COLUMN IF EXISTS title_locked,
    DROP COLUMN IF EXISTS title_source,
    DROP COLUMN IF EXISTS title_ciphertext,
    DROP COLUMN IF EXISTS client_id
"""
        )
    )
