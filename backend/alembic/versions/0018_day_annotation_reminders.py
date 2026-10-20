"""Expand one-shot reminders to calendar day annotations without rewriting sources."""

from sqlalchemy import text

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
ALTER TABLE microsched.one_shot_reminder ADD COLUMN annotation_id UUID,
  ADD CONSTRAINT fk_one_shot_reminder_annotation_id_day_annotation
    FOREIGN KEY (annotation_id) REFERENCES microsched.day_annotation(id) ON DELETE CASCADE
""")
    op.drop_constraint(
        op.f("ck_one_shot_reminder_one_source"), "one_shot_reminder", schema="microsched"
    )
    op.create_check_constraint(
        op.f("ck_one_shot_reminder_one_source"),
        "one_shot_reminder",
        "num_nonnulls(task_id, event_id, tracker_id, annotation_id) = 1",
        schema="microsched",
    )
    op.execute("""
CREATE UNIQUE INDEX uq_one_shot_reminder_active_annotation_id
ON microsched.one_shot_reminder (annotation_id)
WHERE status IN ('pending', 'sending', 'needs_reschedule')
""")
    op.execute("""
CREATE FUNCTION microsched.sync_one_shot_annotation() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE item record; new_due timestamptz;
BEGIN
  IF NEW.starts_on IS DISTINCT FROM OLD.starts_on THEN
    FOR item IN SELECT * FROM microsched.one_shot_reminder
      WHERE annotation_id = NEW.id AND mode = 'relative'
        AND status IN ('pending', 'sending') FOR UPDATE
    LOOP
      new_due := ((NEW.starts_on + item.anchor_time) AT TIME ZONE 'Asia/Ho_Chi_Minh')
                 + make_interval(mins => item.offset_minutes);
      UPDATE microsched.one_shot_reminder
      SET due_at = COALESCE(new_due, due_at), revision = revision + 1,
          status = CASE WHEN item.status = 'sending' OR new_due IS NULL OR new_due <= now()
                        THEN 'needs_reschedule' ELSE 'pending' END,
          next_attempt_at = NULL, attempt_count = 0
      WHERE id = item.id;
    END LOOP;
  END IF;
  RETURN NEW;
END $$
""")
    op.execute("""
CREATE TRIGGER sync_one_shot_annotation AFTER UPDATE ON microsched.day_annotation
FOR EACH ROW EXECUTE FUNCTION microsched.sync_one_shot_annotation()
""")


def downgrade():
    bind = op.get_bind()
    bind.execute(text("LOCK TABLE microsched.one_shot_reminder IN ACCESS EXCLUSIVE MODE"))
    if bind.execute(
        text(
            "SELECT EXISTS(SELECT 1 FROM microsched.one_shot_reminder "
            "WHERE annotation_id IS NOT NULL)"
        )
    ).scalar_one():
        raise RuntimeError("cannot downgrade 0018 with day-annotation reminder data")
    op.execute("DROP TRIGGER sync_one_shot_annotation ON microsched.day_annotation")
    op.execute("DROP FUNCTION microsched.sync_one_shot_annotation()")
    op.drop_index("uq_one_shot_reminder_active_annotation_id", schema="microsched")
    op.drop_constraint(
        op.f("ck_one_shot_reminder_one_source"), "one_shot_reminder", schema="microsched"
    )
    op.drop_column("one_shot_reminder", "annotation_id", schema="microsched")
    op.create_check_constraint(
        op.f("ck_one_shot_reminder_one_source"),
        "one_shot_reminder",
        "num_nonnulls(task_id, event_id, tracker_id) = 1",
        schema="microsched",
    )
