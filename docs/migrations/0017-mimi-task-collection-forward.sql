BEGIN;

-- Running upgrade 0016 -> 0017

ALTER TABLE microsched.task ADD COLUMN collection_version BIGINT NOT NULL DEFAULT 1,
  ADD CONSTRAINT ck_task_collection_version CHECK (collection_version >= 1);

ALTER TABLE microsched.task_item ADD COLUMN deleted_at timestamptz;

CREATE INDEX ix_task_item_active_position ON microsched.task_item(task_id,position,id) WHERE deleted_at IS NULL;

CREATE FUNCTION microsched.bump_task_collection_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.collection_version := OLD.collection_version + 1;
  RETURN NEW;
END $$;

CREATE TRIGGER bump_task_collection_version BEFORE UPDATE ON microsched.task FOR EACH ROW EXECUTE FUNCTION microsched.bump_task_collection_version();

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
END $$;

CREATE TRIGGER touch_task_item_parent AFTER INSERT OR UPDATE OR DELETE ON microsched.task_item FOR EACH ROW EXECUTE FUNCTION microsched.touch_task_item_parent();

ALTER TABLE microsched.mimi_execution_receipt ADD COLUMN result_ciphertext TEXT, ADD CONSTRAINT ck_mimi_execution_receipt_result_ciphertext CHECK (result_ciphertext IS NULL OR result_ciphertext LIKE 'mimi:v1:%');

ALTER TABLE microsched.mimi_evidence ADD COLUMN content_ciphertext TEXT, ADD CONSTRAINT ck_mimi_evidence_content_ciphertext CHECK (content_ciphertext IS NULL OR content_ciphertext LIKE 'mimi:v1:%');

CREATE TABLE microsched.mimi_device_preference (
 id uuid PRIMARY KEY DEFAULT uuidv7(), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), owner_id uuid NOT NULL,
 subscription_id uuid NOT NULL REFERENCES microsched.push_subscription(id) ON DELETE CASCADE,
 enabled boolean NOT NULL DEFAULT false, revision integer NOT NULL DEFAULT 1,
 CONSTRAINT ck_mimi_device_preference_revision CHECK (revision >= 1),
 CONSTRAINT uq_mimi_device_preference_subscription UNIQUE(subscription_id)
);

CREATE TABLE microsched.mimi_notification_intent (
 id uuid PRIMARY KEY DEFAULT uuidv7(), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), owner_id uuid NOT NULL,
 conversation_id uuid NOT NULL REFERENCES microsched.mimi_conversation(id) ON DELETE CASCADE,
 run_id uuid NOT NULL REFERENCES microsched.mimi_run(id) ON DELETE CASCADE,
 event_id uuid NOT NULL REFERENCES microsched.mimi_event(id) ON DELETE CASCADE,
 kind text NOT NULL CONSTRAINT ck_mimi_notification_intent_kind CHECK(kind IN ('completed','approval_ready')),
 copy_ciphertext text NOT NULL CONSTRAINT ck_mimi_notification_intent_copy_ciphertext CHECK(copy_ciphertext LIKE 'mimi:v1:%'),
 locator text NOT NULL, expires_at timestamptz NOT NULL, read_at timestamptz,
 CONSTRAINT uq_mimi_notification_intent_event_kind UNIQUE(event_id,kind),
 CONSTRAINT uq_mimi_notification_intent_locator UNIQUE(locator)
);

CREATE TABLE microsched.mimi_notification_delivery (
 id uuid PRIMARY KEY DEFAULT uuidv7(), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), intent_id uuid NOT NULL REFERENCES microsched.mimi_notification_intent(id) ON DELETE CASCADE,
 preference_id uuid NOT NULL REFERENCES microsched.mimi_device_preference(id) ON DELETE CASCADE,
 state text NOT NULL DEFAULT 'pending' CONSTRAINT ck_mimi_notification_delivery_state CHECK(state IN ('pending','sending','accepted','unknown','retryable','expired','suppressed')),
 attempt_count integer NOT NULL DEFAULT 0 CONSTRAINT ck_mimi_notification_delivery_attempt_count CHECK(attempt_count BETWEEN 0 AND 4),
 next_at timestamptz NOT NULL DEFAULT now(), last_error text,
 CONSTRAINT uq_mimi_notification_delivery_target UNIQUE(intent_id,preference_id)
);

CREATE INDEX ix_mimi_notification_intent_unread ON microsched.mimi_notification_intent(owner_id,created_at) WHERE read_at IS NULL;

CREATE INDEX ix_mimi_notification_delivery_pending ON microsched.mimi_notification_delivery(next_at) WHERE state IN ('pending','retryable');

CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.mimi_device_preference FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at();

CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.mimi_notification_intent FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at();

CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.mimi_notification_delivery FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at();

UPDATE microsched.alembic_version SET version_num='0017' WHERE microsched.alembic_version.version_num = '0016';

COMMIT;
