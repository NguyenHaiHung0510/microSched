"""Add independent occurrence handled state and exact confirmed bulk manifests."""

from sqlalchemy import text

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE microsched.reminder_occurrence_handled (
        id UUID DEFAULT uuidv7() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        owner_id UUID NOT NULL,
        one_shot_id UUID,
        dispatch_id UUID,
        mimi_intent_id UUID,
        handled_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        CONSTRAINT pk_reminder_occurrence_handled PRIMARY KEY (id),
        CONSTRAINT ck_reminder_occurrence_handled_one_receipt CHECK
(num_nonnulls(one_shot_id, dispatch_id, mimi_intent_id) = 1),
        CONSTRAINT uq_history_handled_one_shot UNIQUE (owner_id, one_shot_id),
        CONSTRAINT uq_history_handled_dispatch UNIQUE (owner_id, dispatch_id),
        CONSTRAINT uq_history_handled_mimi UNIQUE (owner_id, mimi_intent_id),
        CONSTRAINT fk_reminder_occurrence_handled_one_shot_id_one_shot_reminder FOREIGN
KEY(one_shot_id) REFERENCES microsched.one_shot_reminder (id) ON DELETE CASCADE,
        CONSTRAINT fk_reminder_occurrence_handled_dispatch_id_reminder_dispatch FOREIGN
KEY(dispatch_id) REFERENCES microsched.reminder_dispatch (id) ON DELETE CASCADE,
        CONSTRAINT fk_reminder_occurrence_handled_mimi_intent_id_mimi_noti_6560 FOREIGN
KEY(mimi_intent_id) REFERENCES microsched.mimi_notification_intent (id) ON DELETE
CASCADE
)
""")
    op.execute("""
CREATE INDEX ix_reminder_occurrence_handled_owner_id ON
microsched.reminder_occurrence_handled (owner_id)
""")
    op.execute("""
CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.reminder_occurrence_handled
FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at()
""")
    op.execute("""
REVOKE ALL ON TABLE microsched.reminder_occurrence_handled FROM PUBLIC
""")
    op.execute("""
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE microsched.reminder_occurrence_handled TO
microsched_app
""")
    op.execute("""
CREATE TABLE microsched.reminder_handled_batch (
        id UUID DEFAULT uuidv7() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        owner_id UUID NOT NULL,
        schema_version INTEGER DEFAULT 1 NOT NULL,
        normalized_filter JSONB NOT NULL,
        fingerprint TEXT NOT NULL,
        target_refs JSONB NOT NULL,
        selected_count INTEGER NOT NULL,
        cutoff TIMESTAMP WITH TIME ZONE NOT NULL,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        committed_at TIMESTAMP WITH TIME ZONE,
        result JSONB,
        CONSTRAINT pk_reminder_handled_batch PRIMARY KEY (id),
        CONSTRAINT ck_reminder_handled_batch_version CHECK (schema_version = 1),
        CONSTRAINT ck_reminder_handled_batch_target_count CHECK
(jsonb_typeof(target_refs) = 'array' AND jsonb_array_length(target_refs) =
selected_count),
        CONSTRAINT ck_reminder_handled_batch_scope CHECK (selected_count >= 0 AND
expires_at > cutoff),
        CONSTRAINT ck_reminder_handled_batch_filter_object CHECK
(jsonb_typeof(normalized_filter) = 'object'),
        CONSTRAINT ck_reminder_handled_batch_fingerprint CHECK (fingerprint ~
'^[0-9a-f]{64}$'),
        CONSTRAINT ck_reminder_handled_batch_result_state CHECK ((committed_at IS NULL)
= (result IS NULL))
)
""")
    op.execute("""
CREATE INDEX ix_reminder_handled_batch_owner_id ON microsched.reminder_handled_batch
(owner_id)
""")
    op.execute("""
CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.reminder_handled_batch FOR
EACH ROW EXECUTE FUNCTION microsched.set_updated_at()
""")
    op.execute("""
REVOKE ALL ON TABLE microsched.reminder_handled_batch FROM PUBLIC
""")
    op.execute("""
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE microsched.reminder_handled_batch TO
microsched_app
""")


def downgrade():
    bind = op.get_bind()
    bind.execute(
        text(
            "LOCK TABLE microsched.reminder_occurrence_handled, "
            "microsched.reminder_handled_batch IN ACCESS EXCLUSIVE MODE"
        )
    )
    for name in ("reminder_occurrence_handled", "reminder_handled_batch"):
        if bind.execute(text(f"SELECT EXISTS(SELECT 1 FROM microsched.{name})")).scalar_one():
            raise RuntimeError(
                "cannot downgrade 0019 with handled or prepared/committed manifest data"
            )
    op.drop_table("reminder_handled_batch", schema="microsched")
    op.drop_table("reminder_occurrence_handled", schema="microsched")
