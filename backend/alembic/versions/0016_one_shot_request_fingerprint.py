"""Bind one-shot reminder UUID replay to the full immutable write request."""

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        text(
            "ALTER TABLE microsched.one_shot_reminder "
            "ADD COLUMN request_fingerprint_sha256 TEXT NULL"
        )
    )
    op.execute(
        text(
            """
CREATE FUNCTION microsched.reject_one_shot_fingerprint_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.request_fingerprint_sha256 IS DISTINCT FROM OLD.request_fingerprint_sha256 THEN
        RAISE EXCEPTION 'one-shot request fingerprint is immutable'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$
"""
        )
    )
    op.execute(
        text(
            """
CREATE TRIGGER trg_one_shot_request_fingerprint_immutable
BEFORE UPDATE OF request_fingerprint_sha256 ON microsched.one_shot_reminder
FOR EACH ROW EXECUTE FUNCTION microsched.reject_one_shot_fingerprint_change()
"""
        )
    )
    op.execute(
        text(
            "ALTER TABLE microsched.one_shot_reminder "
            "ADD CONSTRAINT ck_one_shot_reminder_request_fingerprint_sha256 "
            "CHECK (request_fingerprint_sha256 IS NULL OR "
            "request_fingerprint_sha256 ~ '^[0-9a-f]{64}$')"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    # Exclude concurrent writers before deciding whether rollback can erase the column.
    # PostgreSQL retains this lock through the surrounding Alembic transaction/DDL.
    bind.execute(text("LOCK TABLE microsched.one_shot_reminder IN ACCESS EXCLUSIVE MODE"))
    has_fingerprints = bind.execute(
        text(
            "SELECT EXISTS(SELECT 1 FROM microsched.one_shot_reminder "
            "WHERE request_fingerprint_sha256 IS NOT NULL)"
        )
    ).scalar()
    if has_fingerprints:
        raise RuntimeError("refusing to drop persisted one-shot request fingerprints")
    op.execute(
        text(
            "DROP TRIGGER trg_one_shot_request_fingerprint_immutable "
            "ON microsched.one_shot_reminder"
        )
    )
    op.execute(text("DROP FUNCTION microsched.reject_one_shot_fingerprint_change()"))
    op.execute(
        text(
            "ALTER TABLE microsched.one_shot_reminder "
            "DROP CONSTRAINT ck_one_shot_reminder_request_fingerprint_sha256, "
            "DROP COLUMN request_fingerprint_sha256"
        )
    )
