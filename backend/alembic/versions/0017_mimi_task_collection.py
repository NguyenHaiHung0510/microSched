"""Add Task aggregate CAS/recovery and approved STANDARD Mimi attention.

Revision0017; additive forward migration, never automatically applied at deploy.
"""

# DDL expressions stay literal for the Owner hash card.
# ruff: noqa: E501

from sqlalchemy import text

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
ALTER TABLE microsched.task ADD COLUMN collection_version BIGINT NOT NULL DEFAULT 1,
  ADD CONSTRAINT ck_task_collection_version CHECK (collection_version >= 1)
"""
    )
    op.execute("ALTER TABLE microsched.task_item ADD COLUMN deleted_at timestamptz")
    op.execute(
        "CREATE INDEX ix_task_item_active_position ON microsched.task_item(task_id,position,id) WHERE deleted_at IS NULL"
    )
    op.execute("""
CREATE FUNCTION microsched.bump_task_collection_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.collection_version := OLD.collection_version + 1;
  RETURN NEW;
END $$
""")
    op.execute(
        "CREATE TRIGGER bump_task_collection_version BEFORE UPDATE ON microsched.task FOR EACH ROW EXECUTE FUNCTION microsched.bump_task_collection_version()"
    )
    op.execute("""
CREATE FUNCTION microsched.touch_task_item_parent() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_id uuid; parent_private boolean;
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.task_id IS DISTINCT FROM OLD.task_id THEN
    RAISE EXCEPTION 'task_item.task_id is immutable';
  END IF;
  IF TG_OP = 'DELETE' THEN parent_id := OLD.task_id; ELSE parent_id := NEW.task_id; END IF;
  UPDATE microsched.task SET collection_version = collection_version WHERE id = parent_id
    RETURNING is_private INTO parent_private;
  -- The initial BEFORE privacy check can see the old READ COMMITTED parent.
  -- Recheck after obtaining its current committed version/row lock; a failed
  -- child command rolls back its insert and the aggregate bump together.
  IF TG_OP <> 'DELETE' AND parent_private AND NEW.content NOT LIKE 'enc:v1:%' THEN
    RAISE EXCEPTION 'task_item.content must be ciphertext when parent task is private';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$
""")
    # Application writers lock parents before children. Raw concurrent inversions
    # can be aborted by PG deadlock detection; committed child writes always bump CAS.
    op.execute(
        "CREATE TRIGGER touch_task_item_parent AFTER INSERT OR UPDATE OR DELETE ON microsched.task_item FOR EACH ROW EXECUTE FUNCTION microsched.touch_task_item_parent()"
    )
    for table, column in (
        ("mimi_execution_receipt", "result_ciphertext"),
        ("mimi_evidence", "content_ciphertext"),
    ):
        op.execute(
            f"ALTER TABLE microsched.{table} ADD COLUMN {column} TEXT, ADD CONSTRAINT ck_{table}_{column} CHECK ({column} IS NULL OR {column} LIKE 'mimi:v1:%')"
        )
    base = "id uuid PRIMARY KEY DEFAULT uuidv7(), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()"
    op.execute(f"""
CREATE TABLE microsched.mimi_device_preference (
 {base}, owner_id uuid NOT NULL,
 subscription_id uuid NOT NULL REFERENCES microsched.push_subscription(id) ON DELETE CASCADE,
 enabled boolean NOT NULL DEFAULT false, revision integer NOT NULL DEFAULT 1,
 CONSTRAINT ck_mimi_device_preference_revision CHECK (revision >= 1),
 CONSTRAINT uq_mimi_device_preference_subscription UNIQUE(subscription_id)
)
""")
    op.execute(f"""
CREATE TABLE microsched.mimi_notification_intent (
 {base}, owner_id uuid NOT NULL,
 conversation_id uuid NOT NULL REFERENCES microsched.mimi_conversation(id) ON DELETE CASCADE,
 run_id uuid NOT NULL REFERENCES microsched.mimi_run(id) ON DELETE CASCADE,
 event_id uuid NOT NULL REFERENCES microsched.mimi_event(id) ON DELETE CASCADE,
 kind text NOT NULL CONSTRAINT ck_mimi_notification_intent_kind CHECK(kind IN ('completed','approval_ready')),
 copy_ciphertext text NOT NULL CONSTRAINT ck_mimi_notification_intent_copy_ciphertext CHECK(copy_ciphertext LIKE 'mimi:v1:%'),
 locator text NOT NULL, expires_at timestamptz NOT NULL, read_at timestamptz,
 CONSTRAINT uq_mimi_notification_intent_event_kind UNIQUE(event_id,kind),
 CONSTRAINT uq_mimi_notification_intent_locator UNIQUE(locator)
)
""")
    op.execute(f"""
CREATE TABLE microsched.mimi_notification_delivery (
 {base}, intent_id uuid NOT NULL REFERENCES microsched.mimi_notification_intent(id) ON DELETE CASCADE,
 preference_id uuid NOT NULL REFERENCES microsched.mimi_device_preference(id) ON DELETE CASCADE,
 state text NOT NULL DEFAULT 'pending' CONSTRAINT ck_mimi_notification_delivery_state CHECK(state IN ('pending','sending','accepted','unknown','retryable','expired','suppressed')),
 attempt_count integer NOT NULL DEFAULT 0 CONSTRAINT ck_mimi_notification_delivery_attempt_count CHECK(attempt_count BETWEEN 0 AND 4),
 next_at timestamptz NOT NULL DEFAULT now(), last_error text,
 CONSTRAINT uq_mimi_notification_delivery_target UNIQUE(intent_id,preference_id)
)
""")
    op.execute(
        "CREATE INDEX ix_mimi_notification_intent_unread ON microsched.mimi_notification_intent(owner_id,created_at) WHERE read_at IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_mimi_notification_delivery_pending ON microsched.mimi_notification_delivery(next_at) WHERE state IN ('pending','retryable')"
    )
    for table in (
        "mimi_device_preference",
        "mimi_notification_intent",
        "mimi_notification_delivery",
    ):
        op.execute(
            f"CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.{table} FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at()"
        )


def downgrade():
    occupied = (
        op.get_bind()
        .execute(
            text(
                """
SELECT EXISTS(SELECT 1 FROM microsched.task_item WHERE deleted_at IS NOT NULL)
 OR EXISTS(SELECT 1 FROM microsched.mimi_execution_receipt WHERE result_ciphertext IS NOT NULL)
 OR EXISTS(SELECT 1 FROM microsched.mimi_evidence WHERE content_ciphertext IS NOT NULL)
 OR EXISTS(SELECT 1 FROM microsched.mimi_device_preference)
 OR EXISTS(SELECT 1 FROM microsched.mimi_notification_intent)
 OR EXISTS(SELECT 1 FROM microsched.mimi_notification_delivery)
"""
            )
        )
        .scalar()
    )
    if occupied:
        raise RuntimeError(
            "refusing to drop Task/Mimi recovery or notification data; disable features and roll forward"
        )
    # reviewed: intentional drop — disposable empty local/CI only; production rollback retains schema.
    for table in (
        "mimi_notification_delivery",
        "mimi_notification_intent",
        "mimi_device_preference",
    ):
        op.execute(f"DROP TABLE microsched.{table}")
    for table, column in (
        ("mimi_execution_receipt", "result_ciphertext"),
        ("mimi_evidence", "content_ciphertext"),
    ):
        op.execute(
            f"ALTER TABLE microsched.{table} DROP CONSTRAINT ck_{table}_{column}, DROP COLUMN {column}"
        )
    op.execute("DROP TRIGGER touch_task_item_parent ON microsched.task_item")
    op.execute("DROP FUNCTION microsched.touch_task_item_parent()")
    op.execute("DROP TRIGGER bump_task_collection_version ON microsched.task")
    op.execute("DROP FUNCTION microsched.bump_task_collection_version()")
    op.execute("DROP INDEX microsched.ix_task_item_active_position")
    op.execute("ALTER TABLE microsched.task_item DROP COLUMN deleted_at")
    op.execute(
        "ALTER TABLE microsched.task DROP CONSTRAINT ck_task_collection_version, DROP COLUMN collection_version"
    )
