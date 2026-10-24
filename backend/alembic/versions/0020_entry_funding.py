"""Optional expense reference to one income Entry; historical expenses stay unlinked."""

import sqlalchemy as sa

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "entry", sa.Column("funding_entry_id", sa.UUID(), nullable=True), schema="microsched"
    )
    op.create_foreign_key(
        "fk_entry_funding_entry_id_entry",
        "entry",
        "entry",
        ["funding_entry_id"],
        ["id"],
        source_schema="microsched",
        referent_schema="microsched",
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_entry_funding_not_self"),
        "entry",
        "funding_entry_id IS NULL OR funding_entry_id <> id",
        schema="microsched",
    )
    op.create_index("ix_entry_funding_entry_id", "entry", ["funding_entry_id"], schema="microsched")


def downgrade():
    op.drop_index("ix_entry_funding_entry_id", table_name="entry", schema="microsched")
    op.drop_constraint(
        op.f("ck_entry_funding_not_self"), "entry", schema="microsched", type_="check"
    )
    op.drop_constraint(
        "fk_entry_funding_entry_id_entry", "entry", schema="microsched", type_="foreignkey"
    )
    op.drop_column("entry", "funding_entry_id", schema="microsched")
