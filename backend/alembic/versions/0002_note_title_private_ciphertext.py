"""note.title joins the private-ciphertext invariant

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-24 13:26:17.542330
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Old constraint (0001): only body_md had to be ciphertext when private, so a
# private note could still keep a plaintext title. New constraint matches `task`
# (tracking-brief.md §6, note 2026-07-23): both title and body must be ciphertext
# when is_private, each NULL-tolerant because both columns are nullable on `note`.
NEW_CONDITION = (
    "NOT is_private OR ("
    "(title IS NULL OR title LIKE 'enc:v1:%') "
    "AND (body_md IS NULL OR body_md LIKE 'enc:v1:%'))"
)
OLD_CONDITION = "NOT is_private OR body_md IS NULL OR body_md LIKE 'enc:v1:%'"


def upgrade() -> None:
    """Apply this revision."""
    op.drop_constraint(
        op.f("ck_note_private_body_ciphertext"),
        "note",
        schema="microsched",
        type_="check",
    )
    op.create_check_constraint(
        "private_ciphertext",
        "note",
        NEW_CONDITION,
        schema="microsched",
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_constraint(
        op.f("ck_note_private_ciphertext"),
        "note",
        schema="microsched",
        type_="check",
    )
    op.create_check_constraint(
        "private_body_ciphertext",
        "note",
        OLD_CONDITION,
        schema="microsched",
    )
