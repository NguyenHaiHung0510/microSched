"""task_item privacy invariant enforced by two DB triggers

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-24 16:20:00.000000

task.title/body_md already carry the ``private ⇒ enc:v1:`` CHECK from 0001, but
``task_item.content`` cannot: a row-level CHECK cannot see the parent task, and K11
forbids pushing ``is_private`` down onto the child table. tracking-brief.md §6 first
placed this invariant app-side; 2026-07-24 (008 Phase 0) reverses that to a DB
trigger so the guarantee cannot break silently on an executor bug, and 009-012
inherit a database-enforced invariant rather than a convention.

Two directions, because either side can be the one that moves:

  * enforce_task_item_privacy  - a plaintext item must not be written under a task
    that is already private (INSERT or UPDATE on task_item).
  * enforce_task_children_privacy - a task must not flip to private while it still
    has any plaintext child (UPDATE OF is_private on task).

Neither trigger is sufficient under concurrency: two READ COMMITTED transactions do
not see each other's uncommitted work, so A(toggle→private) racing B(add plaintext
item) can straddle both checks. The write path therefore takes ``SELECT ... FOR
UPDATE`` on the parent task row (spec §2.5) to serialize them; the triggers are the
last net, the row lock is the primary one. test_task_item_trigger.py case #6 proves
both halves.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Install both privacy-invariant trigger functions and their triggers."""
    # Direction 1: block writing a plaintext item under an already-private parent.
    op.execute(
        """
        CREATE FUNCTION microsched.enforce_task_item_privacy()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM microsched.task
                WHERE id = NEW.task_id AND is_private
            ) THEN
                IF NEW.content NOT LIKE 'enc:v1:%' THEN
                    RAISE EXCEPTION
                        'task_item.content must be ciphertext when parent task is private';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_task_item_privacy
        BEFORE INSERT OR UPDATE ON microsched.task_item
        FOR EACH ROW EXECUTE FUNCTION microsched.enforce_task_item_privacy()
        """
    )

    # Direction 2: block flipping a task to private while a plaintext child remains.
    op.execute(
        """
        CREATE FUNCTION microsched.enforce_task_children_privacy()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.is_private AND NOT OLD.is_private THEN
                IF EXISTS (
                    SELECT 1 FROM microsched.task_item
                    WHERE task_id = NEW.id AND content NOT LIKE 'enc:v1:%'
                ) THEN
                    RAISE EXCEPTION
                        'cannot make task private while it has plaintext task_item children';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_task_children_privacy
        BEFORE UPDATE OF is_private ON microsched.task
        FOR EACH ROW EXECUTE FUNCTION microsched.enforce_task_children_privacy()
        """
    )


def downgrade() -> None:
    """Remove both triggers and their functions, leaving 0002 intact."""
    op.execute("DROP TRIGGER IF EXISTS trg_task_children_privacy ON microsched.task")
    op.execute("DROP FUNCTION IF EXISTS microsched.enforce_task_children_privacy()")
    op.execute("DROP TRIGGER IF EXISTS trg_task_item_privacy ON microsched.task_item")
    op.execute("DROP FUNCTION IF EXISTS microsched.enforce_task_item_privacy()")
