"""One bounded, version-bound public Task content page; free text stays data."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.task_reads import _FIELDS, TaskFilter, _filter_query, _project
from app.domain.models import OneShotReminder, Task, TaskItem


class TaskContentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    include_deleted: bool = False
    include_deleted_items: bool = False
    body_offset: int = Field(default=0, ge=0, le=2_147_483_647)
    body_limit: int = Field(default=4000, ge=1, le=4000)
    items_offset: int = Field(default=0, ge=0, le=2_147_483_647)
    items_limit: int = Field(default=20, ge=1, le=20)
    item_content_offsets: dict[UUID, int] = Field(default_factory=dict, max_length=20)
    expected_version: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_continuation(self):
        if (
            self.body_offset or self.items_offset or self.item_content_offsets
        ) and not self.expected_version:
            raise ValueError("task_content_continuation_requires_version")
        if self.expected_version is not None:
            if datetime.fromisoformat(self.expected_version).tzinfo is None:
                raise ValueError("task_content_version_requires_timezone")
        if any(offset < 0 for offset in self.item_content_offsets.values()):
            raise ValueError("task_item_content_offset_invalid")
        return self


async def read_task_content(db: AsyncSession, request: TaskContentRead) -> dict[str, Any]:
    # App checklist writers lock this parent and advance its version. The shared
    # lock keeps metadata/body/checklist in one consistent authorized snapshot.
    row = (
        await db.execute(
            _filter_query(
                select(Task).where(Task.id == request.id),
                TaskFilter(lifecycle="all" if request.include_deleted else "active"),
            )
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    observed_at = datetime.now(UTC).isoformat()
    if row is None:
        return {
            "rows": [],
            "missing_ids": [str(request.id)],
            "count": 0,
            "coverage": "complete",
            "data_as_of": observed_at,
            "omitted_fields": [],
            "source": "microsched.task.content.standard.v1",
        }
    version = row.updated_at.isoformat()
    if request.expected_version is not None and request.expected_version != version:
        raise ValueError("task_content_source_changed")
    body = row.body_md or ""
    if request.body_offset > len(body):
        raise ValueError("task_content_body_offset_out_of_range")
    items = (
        (
            await db.execute(
                select(TaskItem)
                .where(
                    TaskItem.task_id == row.id,
                    True if request.include_deleted_items else TaskItem.deleted_at.is_(None),
                )
                .order_by(TaskItem.position, TaskItem.id)
                .offset(request.items_offset)
                .limit(request.items_limit + 1)
            )
        )
        .scalars()
        .all()
    )
    body_end = min(len(body), request.body_offset + request.body_limit)
    selected_items = items[: request.items_limit]
    if set(request.item_content_offsets) - {item.id for item in selected_items}:
        raise ValueError("task_item_content_offset_not_on_page")
    if any(
        request.item_content_offsets.get(item.id, 0) > len(item.content) for item in selected_items
    ):
        raise ValueError("task_item_content_offset_out_of_range")
    truncated_item_content = any(
        len(item.content) > request.item_content_offsets.get(item.id, 0) + 500
        for item in selected_items
    )
    more_body = body_end < len(body)
    more_items = len(items) > request.items_limit
    reminders = (
        await db.scalars(
            select(OneShotReminder)
            .where(OneShotReminder.task_id == row.id)
            .order_by(OneShotReminder.updated_at.desc())
            .limit(11)
        )
    ).all()
    result_row = _project(row, _FIELDS)
    result_row["reminders"] = [
        {
            "id": str(r.id),
            "revision": r.revision,
            "status": r.status,
            "mode": r.mode,
            "due_at": r.due_at.isoformat() if r.due_at else None,
            "offset_minutes": r.offset_minutes,
            "anchor_time": r.anchor_time.isoformat() if r.anchor_time else None,
            # The source is the live parent Task; occurrence freshness uses id/revision.
            "source_updated_at": version,
        }
        for r in reminders[:10]
    ]
    result_row["reminder_history_omitted"] = len(reminders) > 10
    result_row.update(
        {
            "body_md": None if row.body_md is None else body[request.body_offset : body_end],
            "body_range": [request.body_offset, body_end],
            "body_total_chars": len(body),
            "items": [
                {
                    "id": str(item.id),
                    "position": item.position,
                    "content": item.content[
                        request.item_content_offsets.get(
                            item.id, 0
                        ) : request.item_content_offsets.get(item.id, 0) + 500
                    ],
                    "content_range": [
                        request.item_content_offsets.get(item.id, 0),
                        min(len(item.content), request.item_content_offsets.get(item.id, 0) + 500),
                    ],
                    "next_content_offset": (
                        request.item_content_offsets.get(item.id, 0) + 500
                        if len(item.content) > request.item_content_offsets.get(item.id, 0) + 500
                        else None
                    ),
                    "content_total_chars": len(item.content),
                    "content_truncated": len(item.content)
                    > request.item_content_offsets.get(item.id, 0) + 500,
                    "is_completed": item.is_completed,
                    "deleted_at": item.deleted_at.isoformat() if item.deleted_at else None,
                }
                for item in selected_items
            ],
            "items_offset": request.items_offset,
        }
    )
    partial = bool(
        request.body_offset
        or request.items_offset
        or more_body
        or more_items
        or truncated_item_content
        or request.item_content_offsets
        or len(reminders) > 10
    )
    return {
        "rows": [result_row],
        "count": 1,
        "coverage": "partial" if partial else "complete",
        "next_body_offset": body_end if more_body else None,
        "next_items_offset": request.items_offset + len(selected_items) if more_items else None,
        "omitted_fields": (["body_md.outside_page"] if request.body_offset or more_body else [])
        + (["items.outside_page"] if request.items_offset or more_items else [])
        + (["items.content.after_500_chars"] if truncated_item_content else [])
        + (["reminder_history.after_10"] if len(reminders) > 10 else []),
        "projection": [*_FIELDS, "body_md", "items"],
        "data_as_of": observed_at,
        "source": "microsched.task.content.standard.v1",
    }
