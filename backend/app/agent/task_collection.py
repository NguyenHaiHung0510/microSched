"""Typed Task collection proposal, frozen plan, and same-transaction executor.

The model never calls execute_collection. The confirmation service validates its
encrypted ChangeOperation/digest/nonce/owner/lease before reaching this seam.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid7

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuthSession, OneShotReminder, Task, TaskItem
from app.domain.one_shot import ACTIVE, ReminderWrite, resolve_due, save_reminder
from app.domain.tasks import TaskCreate, TaskItemUpdate, TaskUpdate, _mark_v2_due_writer
from app.web.deps import CRON_TIMER_RELOAD_INFO_KEY

COLLECTION_TOOL = "task.collection.v1"
COLLECTION_CANDIDATE_TOOL = "task.collection_candidate.v1"
MAX_TARGETS = 200
MAX_COMMAND_BYTES = 1_048_576
TASK_FIELDS = frozenset(
    {"title", "body_md", "status", "priority", "due_precision", "due_on", "due_at", "pinned"}
)
SCHEDULE_FIELDS = frozenset({"due_precision", "due_on", "due_at"})


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def conflict(reason: str):
    raise HTTPException(409, reason)


class ChildCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action: Literal["append", "patch", "reorder", "remove", "restore"]
    id: UUID | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    ids: tuple[UUID, ...] = Field(default_factory=tuple, max_length=200)

    @model_validator(mode="after")
    def validate_shape(self):
        if self.action == "reorder":
            if self.id is not None or self.fields or len(self.ids) != len(set(self.ids)):
                raise ValueError("checklist_reorder_shape_invalid")
        elif self.action == "append":
            if self.id is not None or self.ids or set(self.fields) - {"content", "is_completed"}:
                raise ValueError("checklist_append_shape_invalid")
            TaskItemUpdate.model_validate({"content": self.fields.get("content"), **self.fields})
            if not self.fields.get("content"):
                raise ValueError("checklist_content_required")
        else:
            if self.id is None or self.ids:
                raise ValueError("checklist_exact_id_required")
            if self.action == "patch":
                if not self.fields or set(self.fields) - {"content", "is_completed", "position"}:
                    raise ValueError("checklist_patch_fields_invalid")
                TaskItemUpdate.model_validate(self.fields)
            elif self.fields:
                raise ValueError("checklist_lifecycle_fields_invalid")
        return self


class ReminderCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action: Literal["keep", "cancel", "configure"] = "keep"
    configuration: ReminderWrite | None = None

    @model_validator(mode="after")
    def validate_shape(self):
        if (self.action == "configure") != (self.configuration is not None):
            raise ValueError("reminder_command_configuration_invalid")
        if self.configuration is not None and (
            self.configuration.expected_id is not None
            or self.configuration.expected_revision is not None
            or self.configuration.expected_source_updated_at is not None
        ):
            raise ValueError("reminder_cas_is_server_owned")
        return self


class TaskCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action: Literal["create", "edit", "soft_delete", "restore"]
    id: UUID | None = None
    expected_collection_version: int | None = Field(default=None, ge=1, strict=True)
    fields: dict[str, Any] = Field(default_factory=dict)
    children: tuple[ChildCommand, ...] = Field(default_factory=tuple, max_length=200)
    reminder: ReminderCommand = Field(default_factory=ReminderCommand)

    @model_validator(mode="after")
    def validate_shape(self):
        if set(self.fields) - TASK_FIELDS:
            raise ValueError("task_collection_field_not_authorized")
        if self.fields.keys() & SCHEDULE_FIELDS and not SCHEDULE_FIELDS <= self.fields.keys():
            raise ValueError("task_due_triad_must_be_complete")
        if self.action == "create":
            if self.id is not None or self.expected_collection_version is not None:
                raise ValueError("task_create_identity_is_server_owned")
            TaskCreate.model_validate({k: v for k, v in self.fields.items() if k != "pinned"})
            if self.children and any(c.action != "append" for c in self.children):
                raise ValueError("new_task_children_must_append")
        elif self.id is None or self.expected_collection_version is None:
            raise ValueError("task_exact_id_and_version_required")
        else:
            TaskUpdate.model_validate(self.fields)
        if self.action == "soft_delete" and (
            self.fields or self.children or self.reminder.action != "keep"
        ):
            raise ValueError("task_delete_has_only_derived_effects")
        if self.action == "edit" and not (
            self.fields or self.children or self.reminder.action != "keep"
        ):
            raise ValueError("task_edit_is_empty")
        if len(canonical(self.fields).encode("utf-8")) > MAX_COMMAND_BYTES:
            raise ValueError("task_command_payload_exceeded")
        return self


class CollectionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["mimi.task-collection-candidate.v1"] = (
        "mimi.task-collection-candidate.v1"
    )
    selection_id: UUID | None = None
    entries: tuple[TaskCommand, ...] = Field(min_length=1, max_length=MAX_TARGETS)

    @model_validator(mode="after")
    def validate_bounds(self):
        ids = [entry.id for entry in self.entries if entry.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("task_collection_duplicate_target")
        if ids and self.selection_id is None:
            raise ValueError("task_collection_selection_required")
        if len(canonical(self.model_dump(mode="json")).encode("utf-8")) > MAX_COMMAND_BYTES:
            raise ValueError("task_collection_payload_exceeded")
        return self


class PreparedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    command: TaskCommand
    before: dict[str, Any] | None
    after: dict[str, Any]
    reminder_effect: dict[str, Any]


class PreparedCollection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["mimi.task-collection.v1"] = "mimi.task-collection.v1"
    selection_id: UUID | None
    entries: tuple[PreparedEntry, ...] = Field(min_length=1, max_length=MAX_TARGETS)
    undo_receipt_id: UUID | None = None

    @model_validator(mode="after")
    def validate_unique_and_size(self):
        if len({e.id for e in self.entries}) != len(self.entries):
            raise ValueError("task_collection_duplicate_target")
        if len(canonical(self.model_dump(mode="json")).encode("utf-8")) > MAX_COMMAND_BYTES:
            raise ValueError("task_collection_frozen_payload_exceeded")
        return self


def snapshot(task: Task, children: list[TaskItem], reminder: OneShotReminder | None) -> dict:
    return {
        "id": str(task.id),
        "collection_version": task.collection_version,
        "updated_at": task.updated_at.isoformat(),
        "fields": json.loads(canonical({k: getattr(task, k) for k in sorted(TASK_FIELDS)})),
        "deleted_at": task.deleted_at.isoformat() if task.deleted_at else None,
        "children": [
            {
                "id": str(c.id),
                "content": c.content,
                "is_completed": c.is_completed,
                "position": c.position,
                "deleted_at": c.deleted_at.isoformat() if c.deleted_at else None,
                "updated_at": c.updated_at.isoformat(),
            }
            for c in sorted(children, key=lambda c: str(c.id))
        ],
        "reminder": None
        if reminder is None
        else json.loads(
            canonical(
                {
                    k: getattr(reminder, k)
                    for k in (
                        "id",
                        "revision",
                        "status",
                        "mode",
                        "due_at",
                        "offset_minutes",
                        "anchor_time",
                    )
                }
            )
        ),
    }


async def locked_state(db: AsyncSession, ids: list[UUID]) -> dict[UUID, tuple]:
    # Stable lock ordering is shared by preview, confirm and undo; no model I/O here.
    tasks = list(
        (
            await db.scalars(
                select(Task)
                .where(Task.id.in_(ids))
                .order_by(Task.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if any(t.is_private for t in tasks):
        conflict("task_collection_source_not_eligible")
    children = list(
        (
            await db.scalars(
                select(TaskItem)
                .where(TaskItem.task_id.in_(ids))
                .order_by(TaskItem.task_id, TaskItem.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    reminders = list(
        (
            await db.scalars(
                select(OneShotReminder)
                .where(OneShotReminder.task_id.in_(ids), OneShotReminder.status.in_(ACTIVE))
                .order_by(OneShotReminder.task_id, OneShotReminder.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    return {
        t.id: (
            t,
            [c for c in children if c.task_id == t.id],
            next((r for r in reminders if r.task_id == t.id), None),
        )
        for t in tasks
    }


def proposed_fields(command: TaskCommand, before: dict | None) -> dict:
    if before is None:
        parsed = TaskCreate.model_validate(
            {k: v for k, v in command.fields.items() if k != "pinned"}
        )
        fields = parsed.model_dump(mode="json", include=TASK_FIELDS)
        fields["pinned"] = command.fields.get("pinned", False)
    else:
        fields = dict(before["fields"])
        parsed = TaskUpdate.model_validate(command.fields)
        fields.update(parsed.model_dump(mode="json", exclude_unset=True))
    # Revalidate the effective full logical shape, including omission/preserve semantics.
    TaskCreate.model_validate({k: v for k, v in fields.items() if k != "pinned"})
    if not isinstance(fields.get("pinned"), bool):
        raise ValueError("task_pinned_requires_boolean")
    return fields


def proposed_children(command: TaskCommand, before: dict | None, now: datetime) -> list[dict]:
    children = copy.deepcopy(before["children"]) if before else []
    handled = set()
    for change in command.children:
        if change.action == "append":
            positions = [c["position"] for c in children if c["deleted_at"] is None]
            children.append(
                {
                    "id": str(uuid7()),
                    "content": change.fields["content"],
                    "is_completed": change.fields.get("is_completed", False),
                    "position": max(positions, default=-1) + 1,
                    "deleted_at": None,
                    "updated_at": None,
                }
            )
        elif change.action == "reorder":
            active = {c["id"] for c in children if c["deleted_at"] is None}
            if {str(i) for i in change.ids} != active:
                conflict("checklist_reorder_must_cover_exact_active_ids")
            for position, cid in enumerate(change.ids):
                next(c for c in children if c["id"] == str(cid))["position"] = position
        else:
            if change.id in handled:
                conflict("checklist_multiple_changes_require_one_coherent_patch")
            handled.add(change.id)
            item = next((c for c in children if c["id"] == str(change.id)), None)
            if item is None:
                conflict("checklist_child_not_in_target")
            if change.action == "restore":
                if item["deleted_at"] is None:
                    conflict("checklist_restore_requires_tombstone")
                item["deleted_at"] = None
            else:
                if item["deleted_at"] is not None:
                    conflict("checklist_child_is_deleted")
                if change.action == "remove":
                    item["deleted_at"] = now.isoformat()
                else:
                    item.update(
                        TaskItemUpdate.model_validate(change.fields).model_dump(exclude_unset=True)
                    )
    return children


def reminder_effect(command: TaskCommand, fields: dict, before: dict | None, now: datetime) -> dict:
    active = before["reminder"] if before else None
    # Do not allow source UPDATE triggers to relabel a dispatched send as safely cancelled.
    effectful = bool(command.fields.keys() & (SCHEDULE_FIELDS | {"status"})) or (
        command.action in {"soft_delete", "restore"} or command.reminder.action != "keep"
    )
    if active and active["status"] == "sending" and effectful:
        conflict("task_reminder_send_requires_reconciliation")
    if command.action == "soft_delete" or fields["status"] == "completed":
        if command.reminder.action == "configure":
            raise ValueError("completed_or_deleted_task_cannot_configure_reminder")
        return {"action": "cancel" if active else "none", "before": active}
    if command.reminder.action == "cancel":
        if active is None:
            conflict("task_reminder_active_absence_changed")
        return {"action": "cancel", "before": active}
    fake = Task(
        **TaskCreate.model_validate({k: v for k, v in fields.items() if k != "pinned"}).model_dump(
            exclude={"items", "id"}
        )
    )
    if command.reminder.action == "configure":
        due = resolve_due(fake, command.reminder.configuration)
        if due <= now:
            raise ValueError("task_reminder_requires_future_occurrence")
        return {"action": "configure", "before": active, "due_at": due.isoformat()}
    if (
        active
        and active["mode"] == "relative"
        and before
        and any(fields[f] != before["fields"][f] for f in SCHEDULE_FIELDS)
    ):
        try:
            due = resolve_due(
                fake,
                ReminderWrite(
                    mode="relative",
                    offset_minutes=active["offset_minutes"],
                    anchor_time=active["anchor_time"],
                ),
            )
        except HTTPException:
            return {"action": "needs_reschedule", "before": active}
        return {
            "action": "reschedule" if due > now else "needs_reschedule",
            "before": active,
            "due_at": due.isoformat(),
        }
    return {"action": "keep", "before": active}


async def freeze_collection(
    db: AsyncSession,
    candidate: CollectionCandidate,
    *,
    covered_versions: dict[UUID, int],
    now: datetime | None = None,
) -> PreparedCollection:
    now = now or datetime.now(UTC)
    ids = [e.id for e in candidate.entries if e.id is not None]
    state = await locked_state(db, ids)
    plans = []
    for command in candidate.entries:
        before = None
        if command.id is not None:
            if (
                command.id not in state
                or covered_versions.get(command.id) != command.expected_collection_version
            ):
                conflict("task_collection_selection_not_bound")
            task, children, active = state[command.id]
            if task.collection_version != command.expected_collection_version:
                conflict("task_collection_source_stale")
            if (task.deleted_at is not None) != (command.action == "restore"):
                conflict("task_collection_lifecycle_stale")
            before = snapshot(task, children, active)
        fields = proposed_fields(command, before)
        children_after = proposed_children(command, before, now)
        plans.append(
            PreparedEntry(
                id=command.id or uuid7(),
                command=command,
                before=before,
                after={
                    "fields": fields,
                    "children": children_after,
                    "deleted_at": now.isoformat() if command.action == "soft_delete" else None,
                },
                reminder_effect=reminder_effect(command, fields, before, now),
            )
        )
    return PreparedCollection(selection_id=candidate.selection_id, entries=tuple(plans))


async def validate_prepared(db: AsyncSession, plan: PreparedCollection) -> dict[UUID, tuple]:
    state = await locked_state(db, [e.id for e in plan.entries])
    for entry in plan.entries:
        current = state.get(entry.id)
        if entry.before is None:
            if current is not None:
                conflict("task_collection_reserved_id_exists")
        elif current is None or digest(snapshot(*current)) != digest(entry.before):
            conflict("task_collection_source_stale")
        # Re-check time-dependent future effects, not just their frozen arithmetic.
        if entry.reminder_effect["action"] == "configure" and (
            datetime.fromisoformat(entry.reminder_effect["due_at"]) <= datetime.now(UTC)
        ):
            conflict("task_reminder_preview_occurrence_expired")
    return state


async def execute_collection(
    db: AsyncSession,
    auth: AuthSession,
    plan: PreparedCollection,
) -> dict[str, Any]:
    """Apply all validated targets; outer confirmation commits receipt/intents too."""
    state = await validate_prepared(db, plan)
    await _mark_v2_due_writer(db)
    now = datetime.now(UTC)
    for entry in sorted(plan.entries, key=lambda e: str(e.id)):
        logical = TaskCreate.model_validate(
            {k: v for k, v in entry.after["fields"].items() if k != "pinned"}
        )
        if entry.before is None:
            task = Task(id=entry.id, **logical.model_dump(exclude={"id", "items"}))
            db.add(task)
            existing_children = []
            if task.status == "completed":
                task.completed_at = now
        else:
            task, existing_children, _ = state[entry.id]
            old_status = task.status
            for name, value in logical.model_dump(include=TASK_FIELDS).items():
                setattr(task, name, value)
            if task.status != old_status:
                task.completed_at = now if task.status == "completed" else None
        task.pinned = entry.after["fields"]["pinned"]
        task.deleted_at = (
            datetime.fromisoformat(entry.after["deleted_at"]) if entry.after["deleted_at"] else None
        )
        await db.flush()
        by_id = {str(c.id): c for c in existing_children}
        for row in entry.after["children"]:
            child = by_id.get(row["id"])
            if child is None:
                child = TaskItem(id=UUID(row["id"]), task_id=entry.id, content=row["content"])
                db.add(child)
            for name in ("content", "is_completed", "position"):
                setattr(child, name, row[name])
            child.deleted_at = (
                datetime.fromisoformat(row["deleted_at"]) if row["deleted_at"] else None
            )
        await db.flush()
        if entry.command.reminder.action == "configure":
            # Source triggers may already have cancelled/rescheduled the old active row.
            active = (
                await db.scalars(
                    select(OneShotReminder)
                    .where(OneShotReminder.task_id == task.id, OneShotReminder.status.in_(ACTIVE))
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).one_or_none()
            await db.refresh(task)
            config = entry.command.reminder.configuration.model_copy(
                update={
                    "expected_id": active.id if active else None,
                    "expected_revision": active.revision if active else None,
                    "expected_source_updated_at": task.updated_at,
                }
            )
            await save_reminder(db, auth, "task", task.id, config)
        elif entry.command.reminder.action == "cancel":
            active = (
                await db.scalars(
                    select(OneShotReminder)
                    .where(OneShotReminder.task_id == task.id, OneShotReminder.status.in_(ACTIVE))
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).one_or_none()
            if active:
                active.status = "cancelled"
                active.revision += 1
                await db.flush()
    result_state = await locked_state(db, [e.id for e in plan.entries])
    db.info[CRON_TIMER_RELOAD_INFO_KEY] = "mimi_task_collection"
    return {
        "schema_version": "mimi.task-collection-recovery.v1",
        "before": [e.before for e in plan.entries],
        "after": [snapshot(*result_state[e.id]) for e in plan.entries],
        "plan": plan.model_dump(mode="json"),
    }


async def freeze_undo(db, receipt_id, recovery, *, now=None):
    """New inverse preview, exact post-version CAS; never rearm historical Push."""
    now = now or datetime.now(UTC)
    original = PreparedCollection.model_validate(recovery["plan"])
    if len(recovery["before"]) != len(original.entries) or len(recovery["after"]) != len(
        original.entries
    ):
        conflict("undo_recovery_shape_invalid")
    state = await locked_state(db, [e.id for e in original.entries])
    inverse = []
    for entry, before, post in zip(
        original.entries, recovery["before"], recovery["after"], strict=True
    ):
        current = state.get(entry.id)
        if current is None or digest(snapshot(*current)) != digest(post):
            conflict("undo_post_version_stale")
        if post["reminder"] and post["reminder"]["status"] == "sending":
            conflict("undo_reminder_send_requires_reconciliation")
        fields = dict(post["fields"])
        children = copy.deepcopy(post["children"])
        if before is None:
            deleted_at = now.isoformat()
            action = "soft_delete"
            patch = {}
        else:
            # Invert only the operation's changed fields. Exact post-CAS refuses
            # concurrent edits rather than overwriting newer unrelated values.
            patch = {
                k: before["fields"][k]
                for k in TASK_FIELDS
                if before["fields"][k] != entry.after["fields"][k]
            }
            if patch.keys() & SCHEDULE_FIELDS:
                patch.update({k: before["fields"][k] for k in SCHEDULE_FIELDS})
            fields.update(patch)
            deleted_at = before["deleted_at"]
            action = "restore" if post["deleted_at"] and not deleted_at else "edit"
            originals = {c["id"]: c for c in before["children"]}
            planned = {c["id"]: c for c in entry.after["children"]}
            for child in children:
                old = originals.get(child["id"])
                if old is None:
                    child["deleted_at"] = now.isoformat()
                else:
                    proposed = planned[child["id"]]
                    for field in ("content", "is_completed", "position", "deleted_at"):
                        if old[field] != proposed[field]:
                            child[field] = old[field]
        # Reminder state/history is not reverted blindly. Restore scheduling only
        # as a NEW future configure, and only if that schedule was changed here.
        reminder = ReminderCommand()
        pre = before["reminder"] if before else None
        after_active = post["reminder"]
        effect = {"action": "keep", "before": after_active}
        if before is None or fields["status"] == "completed" or deleted_at is not None:
            effect = {"action": "cancel" if after_active else "none", "before": after_active}
        elif pre and digest(pre) != digest(after_active):
            config = ReminderWrite(
                mode=pre["mode"],
                **(
                    {"due_at": pre["due_at"]}
                    if pre["mode"] == "absolute"
                    else {
                        "offset_minutes": pre["offset_minutes"],
                        "anchor_time": pre["anchor_time"],
                    }
                ),
            )
            fake = Task(
                **TaskCreate.model_validate(
                    {k: v for k, v in fields.items() if k != "pinned"}
                ).model_dump(exclude={"items", "id"})
            )
            try:
                due = resolve_due(fake, config)
            except HTTPException:
                due = None
            if due and due > now:
                reminder = ReminderCommand(action="configure", configuration=config)
                effect = {"action": "configure", "before": after_active, "due_at": due.isoformat()}
            else:
                effect = {
                    "action": "keep",
                    "before": after_active,
                    "historical_rearm": "not_performed",
                }
        elif pre is None and after_active:
            reminder = ReminderCommand(action="cancel")
            effect = {"action": "cancel", "before": after_active}
        # Fields are validated directly; inverse children/lifecycle are sealed in
        # the prepared after snapshot, not trusted model patch maps.
        command = (
            TaskCommand(
                action=action,
                id=entry.id,
                expected_collection_version=post["collection_version"],
                fields=patch,
                reminder=reminder,
            )
            if action != "edit" or patch or reminder.action != "keep"
            else TaskCommand(
                action="edit",
                id=entry.id,
                expected_collection_version=post["collection_version"],
                fields={"pinned": fields["pinned"]},
            )
        )
        inverse.append(
            PreparedEntry(
                id=entry.id,
                command=command,
                before=post,
                after={"fields": fields, "children": children, "deleted_at": deleted_at},
                reminder_effect=effect,
            )
        )
    return PreparedCollection(
        selection_id=original.selection_id, entries=tuple(inverse), undo_receipt_id=receipt_id
    )
