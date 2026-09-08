"""Source-owned, one-shot reminder scheduling and read/write contracts."""

from datetime import UTC, datetime, time, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.domain.models import AuthSession, CalendarEvent, OneShotReminder, Task, Tracker
from app.domain.reading import readable
from app.web.deps import CRON_TIMER_RELOAD_INFO_KEY

VN = ZoneInfo("Asia/Ho_Chi_Minh")
LATE_WINDOW = timedelta(minutes=45)
ACTIVE = ("pending", "sending", "needs_reschedule")
ATTENTION = ("needs_reschedule", "missed", "failed", "no_device")
SourceKind = Literal["task", "event", "tracker"]
SOURCES = {
    "task": (Task, "task_id"),
    "event": (CalendarEvent, "event_id"),
    "tracker": (Tracker, "tracker_id"),
}


class ReminderWrite(BaseModel):
    mode: Literal["absolute", "relative"]
    due_at: AwareDatetime | None = None
    offset_minutes: int | None = Field(default=None, ge=-525600, le=525600, strict=True)
    anchor_time: time | None = None
    expected_id: UUID | None = None
    expected_revision: int | None = Field(default=None, ge=1)
    expected_source_updated_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def valid_configuration(self):
        if self.mode == "absolute":
            if self.due_at is None or self.offset_minutes is not None or self.anchor_time:
                raise ValueError("Chọn ngày giờ nhắc cụ thể.")
        elif self.due_at is not None or self.offset_minutes is None:
            raise ValueError("Chọn khoảng thời gian trước/sau mốc.")
        if self.anchor_time and (
            self.anchor_time.tzinfo or self.anchor_time.second or self.anchor_time.microsecond
        ):
            raise ValueError("Giờ mốc phải là giờ và phút tại Việt Nam.")
        if (self.expected_id is None) != (self.expected_revision is None):
            raise ValueError("Thiếu phiên bản lời nhắc.")
        return self


class ReminderRead(BaseModel):
    id: UUID
    source_kind: SourceKind
    source_id: UUID
    source_title: str
    is_private: bool
    source_open: bool
    mode: str
    offset_minutes: int | None
    anchor_time: time | None
    due_at: datetime
    status: str
    revision: int
    attempt_count: int
    sent_at: datetime | None
    created_at: datetime


def source_open(source) -> bool:
    if isinstance(source, Task):
        return source.deleted_at is None and source.status == "open"
    if isinstance(source, Tracker):
        return source.deleted_at is None
    return not source.is_hidden


def resolve_due(source, payload: ReminderWrite) -> datetime:
    if payload.mode == "absolute":
        return payload.due_at.astimezone(UTC)
    anchor = None
    if isinstance(source, Task):
        precision = source.due_precision or ("datetime" if source.due_at else "none")
        if precision == "datetime":
            anchor = source.due_at
        elif precision == "date" and source.due_on and payload.anchor_time:
            anchor = datetime.combine(source.due_on, payload.anchor_time, VN)
    elif isinstance(source, CalendarEvent):
        if source.all_day:
            if payload.anchor_time:
                anchor = datetime.combine(
                    source.starts_at.astimezone(VN).date(), payload.anchor_time, VN
                )
        else:
            anchor = source.starts_at
    if anchor is None:
        raise HTTPException(422, "Nguồn chưa có mốc giờ. Chọn ngày giờ riêng hoặc bổ sung giờ mốc.")
    try:
        return (anchor + timedelta(minutes=payload.offset_minutes)).astimezone(UTC)
    except OverflowError as exc:
        raise HTTPException(422, "Thời gian nhắc nằm ngoài khoảng hỗ trợ.") from exc


async def get_source(
    db: AsyncSession, kind: str, source_id: UUID, auth: AuthSession | None = None, *, lock=False
):
    model, _ = SOURCES[kind]
    stmt = select(model).where(model.id == source_id).execution_options(populate_existing=True)
    if auth is not None:
        stmt = readable(stmt, model, auth)
        if kind == "event":
            stmt = stmt.where(CalendarEvent.is_hidden.is_(False))
    if lock:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


def as_read(row: OneShotReminder, kind: str, source) -> ReminderRead:
    stored_title = source.name if kind == "tracker" else source.title
    title = crypto.decrypt(stored_title) if crypto.is_encrypted(stored_title) else stored_title
    return ReminderRead(
        id=row.id,
        source_kind=kind,
        source_id=source.id,
        source_title=title,
        is_private=getattr(source, "is_private", False),
        source_open=source_open(source),
        mode=row.mode,
        offset_minutes=row.offset_minutes,
        anchor_time=row.anchor_time,
        due_at=row.due_at,
        status=row.status,
        revision=row.revision,
        attempt_count=row.attempt_count,
        sent_at=row.sent_at,
        created_at=row.created_at,
    )


async def list_reminders(
    db: AsyncSession,
    auth: AuthSession,
    *,
    kind: str | None = None,
    source_id: UUID | None = None,
    section="upcoming",
    offset=0,
    limit=50,
):
    # Each arm applies the parent's gates before any title is loaded/decrypted.
    # Bounded three-arm merge; no per-row source lookups and no count-all query.
    records = []
    for source_kind, (model, column) in SOURCES.items():
        if kind is not None and kind != source_kind:
            continue
        stmt = select(OneShotReminder, model).join(
            model, getattr(OneShotReminder, column) == model.id
        )
        stmt = readable(stmt, model, auth)
        if source_kind == "event":
            stmt = stmt.where(CalendarEvent.is_hidden.is_(False))
        if source_id:
            stmt = stmt.where(model.id == source_id)
        if section == "active":
            stmt = stmt.where(OneShotReminder.status.in_(ACTIVE))
        elif section == "upcoming":
            stmt = stmt.where(OneShotReminder.status.in_(("pending", "sending")))
        elif section == "attention":
            stmt = stmt.where(OneShotReminder.status.in_(ATTENTION))
        elif section == "history":
            stmt = stmt.where(OneShotReminder.status.in_(("sent", "cancelled")))
        order = (
            (OneShotReminder.due_at, OneShotReminder.id)
            if section == "upcoming"
            else (OneShotReminder.created_at.desc(), OneShotReminder.id.desc())
        )
        rows = (await db.execute(stmt.order_by(*order).limit(offset + limit + 1))).all()
        records.extend(as_read(row, source_kind, source) for row, source in rows)
    records.sort(
        key=lambda r: (r.due_at if section == "upcoming" else r.created_at, r.id),
        reverse=section != "upcoming",
    )
    return {"items": records[offset : offset + limit], "has_more": len(records) > offset + limit}


async def save_reminder(
    db: AsyncSession,
    auth: AuthSession,
    kind: str,
    source_id: UUID,
    payload: ReminderWrite,
    *,
    now: datetime | None = None,
):
    source = await get_source(db, kind, source_id, auth, lock=True)
    if source is None:
        raise HTTPException(404, "Không tìm thấy đối tượng.")
    if not source_open(source):
        raise HTTPException(409, "Đối tượng đã hoàn thành hoặc bị xoá.")
    if payload.expected_source_updated_at is not None and (
        source.updated_at != payload.expected_source_updated_at
    ):
        raise HTTPException(409, "Mốc của đối tượng đã thay đổi. Tải lại trước khi đặt nhắc.")
    due = resolve_due(source, payload)
    if due <= (now or datetime.now(UTC)):
        raise HTTPException(422, "Giờ nhắc đã qua. Hãy chọn thời điểm trong tương lai.")
    _, column = SOURCES[kind]
    active = (
        await db.execute(
            select(OneShotReminder)
            .where(
                getattr(OneShotReminder, column) == source_id, OneShotReminder.status.in_(ACTIVE)
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if active is not None:
        if active.id != payload.expected_id or active.revision != payload.expected_revision:
            raise HTTPException(409, "Lời nhắc đã thay đổi. Tải lại trước khi lưu.")
        if active.status == "sending":
            raise HTTPException(409, "Lời nhắc đang gửi. Kiểm tra trạng thái trước khi đặt lại.")
        active.status = "cancelled"
        active.revision += 1
        await db.flush()
    elif payload.expected_id is not None:
        raise HTTPException(409, "Lời nhắc đã kết thúc. Tải lại rồi chọn Đặt nhắc mới.")
    row = OneShotReminder(
        **{column: source_id},
        mode=payload.mode,
        due_at=due,
        offset_minutes=payload.offset_minutes,
        anchor_time=payload.anchor_time,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    db.info[CRON_TIMER_RELOAD_INFO_KEY] = "one_shot_saved"
    return as_read(row, kind, source)


async def cancel_reminder(db: AsyncSession, auth: AuthSession, reminder_id: UUID, revision: int):
    probe = await db.get(OneShotReminder, reminder_id)
    if probe is None:
        raise HTTPException(404, "Không tìm thấy lời nhắc.")
    kind, column = next((k, c) for k, (_, c) in SOURCES.items() if getattr(probe, c))
    source = await get_source(db, kind, getattr(probe, column), auth, lock=True)
    if source is None:
        raise HTTPException(404, "Không tìm thấy lời nhắc.")
    row = (
        await db.execute(
            select(OneShotReminder)
            .where(OneShotReminder.id == reminder_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if row.revision != revision or row.status not in ACTIVE:
        raise HTTPException(409, "Lời nhắc đã thay đổi. Tải lại trạng thái mới.")
    row.status = "cancelled"
    row.revision += 1
    db.info[CRON_TIMER_RELOAD_INFO_KEY] = "one_shot_cancelled"


def identity(row):
    return next(
        (kind, getattr(row, col))
        for kind, (_, col) in SOURCES.items()
        if getattr(row, col) is not None
    )
