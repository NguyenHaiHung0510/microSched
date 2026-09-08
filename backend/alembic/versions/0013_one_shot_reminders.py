"""Add independent one-shot reminders (expand only)."""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE microsched.one_shot_reminder (
    id UUID DEFAULT uuidv7() NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    task_id UUID,
    event_id UUID,
    tracker_id UUID,
    mode TEXT NOT NULL,
    offset_minutes INTEGER,
    anchor_time TIME WITHOUT TIME ZONE,
    due_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status TEXT DEFAULT 'pending' NOT NULL,
    revision INTEGER DEFAULT 1 NOT NULL,
    attempt_count INTEGER DEFAULT 0 NOT NULL,
    next_attempt_at TIMESTAMP WITH TIME ZONE,
    last_attempt_at TIMESTAMP WITH TIME ZONE,
    sent_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT pk_one_shot_reminder PRIMARY KEY (id),
    CONSTRAINT ck_one_shot_reminder_one_source CHECK (num_nonnulls(task_id,
event_id, tracker_id) = 1),
    CONSTRAINT ck_one_shot_reminder_mode CHECK (mode IN ('absolute', 'relative')),
    CONSTRAINT ck_one_shot_reminder_schedule_config CHECK ((mode = 'absolute' AND
offset_minutes IS NULL AND anchor_time IS NULL) OR (mode = 'relative' AND
offset_minutes IS NOT NULL AND offset_minutes BETWEEN -525600 AND 525600
AND tracker_id IS NULL)),
    CONSTRAINT ck_one_shot_reminder_status CHECK (status IN ('pending', 'sending',
'sent', 'missed', 'needs_reschedule', 'no_device', 'failed', 'cancelled')),
    CONSTRAINT ck_one_shot_reminder_revision CHECK (revision >= 1),
    CONSTRAINT ck_one_shot_reminder_attempt_count CHECK (attempt_count BETWEEN 0 AND
4),
    CONSTRAINT fk_one_shot_reminder_task_id_task FOREIGN KEY(task_id) REFERENCES
microsched.task (id) ON DELETE CASCADE,
    CONSTRAINT fk_one_shot_reminder_event_id_calendar_event FOREIGN KEY(event_id)
REFERENCES microsched.calendar_event (id) ON DELETE CASCADE,
    CONSTRAINT fk_one_shot_reminder_tracker_id_tracker FOREIGN KEY(tracker_id)
REFERENCES microsched.tracker (id) ON DELETE CASCADE
)
    """)
    op.execute("""
CREATE INDEX ix_one_shot_reminder_due_at ON microsched.one_shot_reminder (due_at)
WHERE status IN ('pending', 'sending')
    """)
    op.execute("""
CREATE UNIQUE INDEX uq_one_shot_reminder_active_event_id ON
microsched.one_shot_reminder (event_id) WHERE status IN ('pending', 'sending',
'needs_reschedule')
    """)
    op.execute("""
CREATE UNIQUE INDEX uq_one_shot_reminder_active_task_id ON
microsched.one_shot_reminder (task_id) WHERE status IN ('pending', 'sending',
'needs_reschedule')
    """)
    op.execute("""
CREATE UNIQUE INDEX uq_one_shot_reminder_active_tracker_id ON
microsched.one_shot_reminder (tracker_id) WHERE status IN ('pending', 'sending',
'needs_reschedule')
    """)
    install_source_triggers()


def downgrade():
    from sqlalchemy import text

    if (
        op.get_bind()
        .execute(text("SELECT EXISTS(SELECT 1 FROM microsched.one_shot_reminder)"))
        .scalar_one()
    ):
        raise RuntimeError("cannot downgrade 0013 with one-shot reminder data")
    remove_source_triggers()
    op.drop_table("one_shot_reminder", schema="microsched")


def install_source_triggers():
    # Parent writes already own the parent lock. Every API/dispatcher follows
    # parent -> reminder, so source updates and eligibility changes are atomic.
    op.execute("""
CREATE FUNCTION microsched.sync_one_shot_source() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE source_col text; source_cancelled boolean := false;
            anchor_changed boolean := false; new_anchor timestamptz;
            item record; new_due timestamptz;
    BEGIN
      IF TG_TABLE_NAME = 'task' THEN
        source_col := 'task_id';
        source_cancelled := NEW.deleted_at IS NOT NULL OR NEW.status = 'completed';
        anchor_changed := ROW(NEW.due_at, NEW.due_on, NEW.due_precision)
                          IS DISTINCT FROM ROW(OLD.due_at, OLD.due_on,
OLD.due_precision);
      ELSIF TG_TABLE_NAME = 'calendar_event' THEN
        source_col := 'event_id'; source_cancelled := NEW.is_hidden;
        anchor_changed := ROW(NEW.starts_at, NEW.all_day)
                          IS DISTINCT FROM ROW(OLD.starts_at, OLD.all_day);
      ELSE
        source_col := 'tracker_id'; source_cancelled := NEW.deleted_at IS NOT NULL;
      END IF;
      IF source_cancelled THEN
        EXECUTE format('UPDATE microsched.one_shot_reminder SET status =
''cancelled'',
          revision = revision + 1 WHERE %I = $1
          AND status IN (''pending'', ''sending'', ''needs_reschedule'')',
source_col)
          USING NEW.id;
      ELSIF anchor_changed THEN
        FOR item IN EXECUTE format('SELECT * FROM microsched.one_shot_reminder
          WHERE %I = $1 AND mode = ''relative'' AND status IN (''pending'',
''sending'')
          FOR UPDATE', source_col) USING NEW.id
        LOOP
          new_anchor := NULL;
          IF TG_TABLE_NAME = 'task' THEN
            IF COALESCE(NEW.due_precision, CASE WHEN NEW.due_at IS NULL THEN 'none'
                                              ELSE 'datetime' END) = 'datetime' THEN
              new_anchor := NEW.due_at;
            ELSIF NEW.due_precision = 'date' AND item.anchor_time IS NOT NULL THEN
              new_anchor := (NEW.due_on + item.anchor_time) AT TIME ZONE
'Asia/Ho_Chi_Minh';
            END IF;
          ELSE
            IF NOT NEW.all_day THEN new_anchor := NEW.starts_at;
            ELSIF item.anchor_time IS NOT NULL THEN
              new_anchor := ((NEW.starts_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
                            + item.anchor_time) AT TIME ZONE 'Asia/Ho_Chi_Minh';
            END IF;
          END IF;
          new_due := new_anchor + make_interval(mins => item.offset_minutes);
          UPDATE microsched.one_shot_reminder
          SET due_at = COALESCE(new_due, due_at), revision = revision + 1,
              status = CASE WHEN item.status = 'sending' OR new_due IS NULL OR
new_due <= now()
                            THEN 'needs_reschedule' ELSE 'pending' END,
              next_attempt_at = NULL, attempt_count = 0
          WHERE id = item.id;
        END LOOP;
      END IF;
      RETURN NEW;
    END $$
    """)
    for table in ("task", "calendar_event", "tracker"):
        op.execute(
            f"CREATE TRIGGER sync_one_shot_source AFTER UPDATE ON microsched.{table} "
            "FOR EACH ROW EXECUTE FUNCTION microsched.sync_one_shot_source()"
        )
    op.execute(
        "CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.one_shot_reminder "
        "FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at()"
    )


def remove_source_triggers():
    for table in ("task", "calendar_event", "tracker"):
        op.execute(f"DROP TRIGGER sync_one_shot_source ON microsched.{table}")
    op.execute("DROP FUNCTION microsched.sync_one_shot_source()")
