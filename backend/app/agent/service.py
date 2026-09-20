"""Bounded Mimi P1 orchestration over the existing Task transaction seam."""

from __future__ import annotations

import hashlib
import hmac
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import and_, false, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import crypto as mimi_crypto
from app.agent.contracts import ChangeOperation, ExecutionLease, FrozenChangeSet, Sensitivity
from app.agent.models import (
    MimiChangeSet,
    MimiConversation,
    MimiEvent,
    MimiExecutionReceipt,
    MimiFeedback,
    MimiMessage,
    MimiProviderCall,
    MimiRefreshMarker,
    MimiRun,
)
from app.agent.openrouter import (
    ProviderDispatchError,
    RouteContractError,
)
from app.agent.openrouter import (
    complete as openrouter_complete,
)
from app.agent.openrouter import complete_stream as openrouter_complete_stream
from app.agent.openrouter import get_generation as openrouter_get_generation
from app.core.settings import get_settings
from app.domain.models import AuditLog, AuthSession, Task
from app.domain.tasks import TaskCreate, TaskStore
from app.web.deps import CRON_TIMER_RELOAD_INFO_KEY

POLICY_VERSION = "mimi-standard-task-create.v1"
TOOL_VERSION = "task.create.v1"
MAX_MESSAGES = 100
MAX_EVENTS = 100
MAX_CONVERSATION_TITLE = 80
PROVIDER_HISTORY_MESSAGES = 24
PROVIDER_HISTORY_BYTES = 65_536
OWNER_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


class MessageCreate(BaseModel):
    client_id: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=12_000)
    expected_generation: int | None = Field(default=None, ge=1)
    intent: Literal["auto", "revise_pending_preview"] = "auto"
    expected_change_set_id: UUID | None = None
    expected_change_set_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class ConfirmationDecision(BaseModel):
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    nonce: UUID
    decision: Literal["confirm", "reject"]


class FeedbackCreate(BaseModel):
    client_id: str = Field(min_length=1, max_length=160)
    target_type: Literal["turn", "run", "call", "operation", "receipt"]
    target_id: str = Field(min_length=1, max_length=200)
    comment: str = Field(min_length=1, max_length=10_000)
    expected: str | None = Field(default=None, max_length=10_000)
    evidence_bundle_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @field_validator("comment")
    @classmethod
    def reject_blank_comment(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("comment must not be blank")
        return value

    @model_validator(mode="after")
    def bind_revision_to_pending_preview(self) -> MessageCreate:
        target = (self.expected_change_set_id, self.expected_change_set_digest)
        if self.intent == "revise_pending_preview" and any(item is None for item in target):
            raise ValueError("preview revision requires id and digest")
        if self.intent == "auto" and any(item is not None for item in target):
            raise ValueError("preview target requires revise_pending_preview intent")
        return self


class ConversationCreate(BaseModel):
    client_id: str | None = Field(default=None, min_length=1, max_length=160)


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_CONVERSATION_TITLE)
    expected_metadata_version: int = Field(ge=1)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized


class ConversationStateChange(BaseModel):
    expected_metadata_version: int = Field(ge=1)


def _owner_id(auth: AuthSession) -> UUID:
    """Derive a stable opaque owner UUID without persisting the login address."""
    secret = (get_settings().oauth_state_secret or get_settings().app_name).encode("utf-8")
    digest = hmac.new(secret, auth.user_email.strip().lower().encode("utf-8"), hashlib.sha256)
    return UUID(bytes=digest.digest()[:16], version=5)


def _canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _provider_session_id(conversation_id: UUID) -> str:
    secret = (get_settings().oauth_state_secret or get_settings().app_name).encode("utf-8")
    digest = hmac.new(secret, conversation_id.bytes, hashlib.sha256).hexdigest()
    return f"mimi-{digest[:32]}"


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mimi resource not found")


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def _append_event(
    db: AsyncSession,
    run_id: UUID,
    kind: str,
    payload: dict[str, Any],
) -> int:
    # The run row is the per-run append fence. Cancellation, provider progress,
    # confirmation and reconciliation can therefore never reuse a sequence.
    await db.execute(select(MimiRun.id).where(MimiRun.id == run_id).with_for_update())
    latest = (
        await db.execute(select(func.max(MimiEvent.sequence)).where(MimiEvent.run_id == run_id))
    ).scalar_one()
    sequence = (latest or 0) + 1
    db.add(MimiEvent(run_id=run_id, sequence=sequence, kind=kind, payload=payload))
    await db.flush()
    return sequence


def _task_title(content: str) -> str:
    """Build a bounded deterministic preview title for the local route."""
    title = " ".join(content.strip().split())
    lowered = title.lower()
    for prefix in ("tạo task ", "tạo việc ", "create task "):
        if lowered.startswith(prefix):
            title = title[len(prefix) :].strip()
            break
    return (title or "Task từ Mimi")[:200]


def _conversation_title(content: str) -> str:
    normalized = " ".join(content.split())
    return (normalized or "Hội thoại mới")[:MAX_CONVERSATION_TITLE]


def _fallback_conversation_title(value: datetime) -> str:
    return f"Hội thoại mới · {value.astimezone(OWNER_TIMEZONE):%d/%m %H:%M}"


def _seal_conversation_title(conversation: MimiConversation, title: str) -> str:
    dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
    return mimi_crypto.seal_content(
        dek,
        title,
        aad=mimi_crypto.conversation_title_aad(conversation.id),
    )


def _open_conversation_title(conversation: MimiConversation) -> str:
    if conversation.title_ciphertext is None:
        return _fallback_conversation_title(conversation.created_at)
    dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
    return mimi_crypto.open_content(
        dek,
        conversation.title_ciphertext,
        aad=mimi_crypto.conversation_title_aad(conversation.id),
    )


def _encode_conversation_cursor(updated_at: datetime, conversation_id: UUID) -> str:
    raw = json.dumps(
        {"updated_at": updated_at.isoformat(), "id": str(conversation_id)},
        separators=(",", ":"),
    ).encode("utf-8")
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_conversation_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(urlsafe_b64decode(padded).decode("utf-8"))
        updated_at = datetime.fromisoformat(decoded["updated_at"])
        conversation_id = UUID(decoded["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=422, detail="invalid_conversation_cursor") from error
    if updated_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="invalid_conversation_cursor")
    return updated_at, conversation_id


async def _conversation(
    db: AsyncSession, auth: AuthSession, conversation_id: UUID, *, lock: bool = False
) -> MimiConversation:
    statement = select(MimiConversation).where(
        MimiConversation.id == conversation_id,
        MimiConversation.owner_id == _owner_id(auth),
    )
    if lock:
        statement = statement.with_for_update()
    row = (await db.execute(statement)).scalar_one_or_none()
    if row is None:
        raise _not_found()
    return row


def _message_read(row: MimiMessage, dek: bytes) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "client_id": row.client_id,
        "sequence": row.sequence,
        "role": row.role,
        "content": mimi_crypto.open_content(
            dek,
            row.content_ciphertext,
            aad=mimi_crypto.message_aad(row.conversation_id, row.sequence, row.role),
        ),
        "created_at": row.created_at,
    }


def _receipt_read(row: MimiExecutionReceipt) -> dict[str, Any]:
    return {
        "id": row.id,
        "change_set_id": row.change_set_id,
        "operation_id": row.operation_id,
        "task_id": row.task_id,
        "digest": row.digest_sha256,
        "result": row.result,
        "executed_at": row.executed_at,
    }


def _add_assistant_message(
    db: AsyncSession,
    conversation: MimiConversation,
    run_id: UUID,
    dek: bytes,
    content: str,
) -> None:
    sequence = conversation.next_message_sequence
    raw = content.encode("utf-8")
    db.add(
        MimiMessage(
            conversation_id=conversation.id,
            run_id=run_id,
            sequence=sequence,
            role="assistant",
            content_ciphertext=mimi_crypto.seal_content(
                dek,
                content,
                aad=mimi_crypto.message_aad(conversation.id, sequence, "assistant"),
            ),
            content_bytes=len(raw),
            content_sha256=hashlib.sha256(raw).hexdigest(),
        )
    )
    conversation.next_message_sequence += 1


async def create_conversation(
    db: AsyncSession, auth: AuthSession, payload: ConversationCreate
) -> dict[str, Any]:
    owner_id = _owner_id(auth)
    if payload.client_id is not None:
        existing = (
            await db.execute(
                select(MimiConversation).where(
                    MimiConversation.owner_id == owner_id,
                    MimiConversation.client_id == payload.client_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return _conversation_summary(existing, latest_run_state=None)
    now = datetime.now(UTC)
    row = MimiConversation(
        id=uuid7(),
        owner_id=owner_id,
        client_id=payload.client_id,
        sensitivity=Sensitivity.STANDARD.value,
        dek_wrapped=mimi_crypto.create_wrapped_dek(),
    )
    row.title_ciphertext = _seal_conversation_title(row, _fallback_conversation_title(now))
    db.add(row)
    await db.flush()
    return _conversation_summary(row, latest_run_state=None)


def _conversation_summary(
    row: MimiConversation, *, latest_run_state: str | None
) -> dict[str, Any]:
    return {
        "id": row.id,
        "sensitivity": row.sensitivity,
        "title": _open_conversation_title(row),
        "title_source": row.title_source,
        "title_locked": row.title_locked,
        "generation": row.generation,
        "metadata_version": row.metadata_version,
        "archived_at": row.archived_at,
        "updated_at": row.updated_at,
        "latest_run_state": latest_run_state,
    }


async def _provider_history(
    db: AsyncSession,
    conversation: MimiConversation,
    dek: bytes,
) -> list[dict[str, str]]:
    """Return a newest-bounded, complete-message provider history window."""
    rows = (
        (
            await db.execute(
                select(MimiMessage)
                .where(
                    MimiMessage.conversation_id == conversation.id,
                    MimiMessage.role.in_(("user", "assistant")),
                )
                .order_by(MimiMessage.sequence.desc())
                .limit(PROVIDER_HISTORY_MESSAGES)
            )
        )
        .scalars()
        .all()
    )
    selected: list[MimiMessage] = []
    used_bytes = 0
    for row in rows:
        if used_bytes + row.content_bytes > PROVIDER_HISTORY_BYTES:
            break
        selected.append(row)
        used_bytes += row.content_bytes
    return [
        {
            "role": row.role,
            "content": mimi_crypto.open_content(
                dek,
                row.content_ciphertext,
                aad=mimi_crypto.message_aad(
                    conversation.id,
                    row.sequence,
                    row.role,
                ),
            ),
        }
        for row in reversed(selected)
    ]


def _event_read(row: MimiEvent, dek: bytes) -> dict[str, Any]:
    payload = row.payload
    if row.kind == "assistant.delta" and "content_ciphertext" in payload:
        payload = {
            "text": mimi_crypto.open_content(
                dek,
                str(payload["content_ciphertext"]),
                aad=mimi_crypto.event_content_aad(row.run_id, row.sequence, row.kind),
            ),
            "content_bytes": payload.get("content_bytes"),
        }
    return {
        "id": row.id,
        "run_id": row.run_id,
        "sequence": row.sequence,
        "kind": row.kind,
        "payload": payload,
        "created_at": row.created_at,
    }


async def list_conversations(
    db: AsyncSession,
    auth: AuthSession,
    *,
    state: Literal["active", "archived", "all"],
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    latest_run_state = (
        select(MimiRun.state)
        .where(MimiRun.conversation_id == MimiConversation.id)
        .order_by(MimiRun.created_at.desc(), MimiRun.id.desc())
        .limit(1)
        .correlate(MimiConversation)
        .scalar_subquery()
    )
    statement = select(MimiConversation, latest_run_state.label("latest_run_state")).where(
        MimiConversation.owner_id == _owner_id(auth)
    )
    if state == "active":
        statement = statement.where(MimiConversation.archived_at.is_(None))
    elif state == "archived":
        statement = statement.where(MimiConversation.archived_at.is_not(None))
    if cursor:
        cursor_at, cursor_id = _decode_conversation_cursor(cursor)
        statement = statement.where(
            or_(
                MimiConversation.updated_at < cursor_at,
                and_(
                    MimiConversation.updated_at == cursor_at,
                    MimiConversation.id < cursor_id,
                ),
            )
        )
    rows = (
        await db.execute(
            statement.order_by(MimiConversation.updated_at.desc(), MimiConversation.id.desc())
            .limit(limit + 1)
        )
    ).all()
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = None
    if has_more and page:
        last = page[-1][0]
        next_cursor = _encode_conversation_cursor(last.updated_at, last.id)
    return {
        "items": [
            _conversation_summary(row, latest_run_state=run_state) for row, run_state in page
        ],
        "next_cursor": next_cursor,
    }


async def rename_conversation(
    db: AsyncSession,
    auth: AuthSession,
    conversation_id: UUID,
    payload: ConversationRename,
) -> dict[str, Any]:
    row = await _conversation(db, auth, conversation_id, lock=True)
    current_title = _open_conversation_title(row)
    if row.title_locked and current_title == payload.title:
        return _conversation_summary(row, latest_run_state=None)
    if row.metadata_version != payload.expected_metadata_version:
        raise _conflict("conversation_metadata_stale")
    row.title_ciphertext = _seal_conversation_title(row, payload.title)
    row.title_source = "owner"
    row.title_locked = True
    row.metadata_version += 1
    await db.flush()
    return _conversation_summary(row, latest_run_state=None)


async def set_conversation_archived(
    db: AsyncSession,
    auth: AuthSession,
    conversation_id: UUID,
    payload: ConversationStateChange,
    *,
    archived: bool,
) -> dict[str, Any]:
    row = await _conversation(db, auth, conversation_id, lock=True)
    if (row.archived_at is not None) == archived:
        return _conversation_summary(row, latest_run_state=None)
    if row.metadata_version != payload.expected_metadata_version:
        raise _conflict("conversation_metadata_stale")
    row.archived_at = datetime.now(UTC) if archived else None
    row.metadata_version += 1
    await db.flush()
    return _conversation_summary(row, latest_run_state=None)


async def current_conversation(db: AsyncSession, auth: AuthSession) -> dict[str, Any] | None:
    conversation_id = (
        await db.execute(
            select(MimiConversation.id)
            .where(
                MimiConversation.owner_id == _owner_id(auth),
                MimiConversation.archived_at.is_(None),
            )
            .order_by(MimiConversation.updated_at.desc(), MimiConversation.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if conversation_id is None:
        return None
    return await conversation_view(db, auth, conversation_id)


async def list_standard_tasks(
    db: AsyncSession, auth: AuthSession, *, limit: int
) -> list[dict[str, Any]]:
    """Read bounded public Task rows; filter private rows before DTO/provider assembly."""
    del auth  # session presence is the authority; STANDARD never receives private rows.
    rows = (
        await db.execute(
            select(Task)
            .where(Task.deleted_at.is_(None), Task.is_private == false())
            .order_by(Task.updated_at.desc(), Task.id.desc())
            .limit(limit)
        )
    ).scalars()
    return [
        {
            "id": row.id,
            "title": row.title,
            "status": row.status,
            "priority": row.priority,
            "due_precision": row.due_precision or ("datetime" if row.due_at else "none"),
            "due_on": row.due_on,
            "due_at": row.due_at,
            "source_version": row.updated_at,
            "provenance": "microsched.task.standard.v1",
        }
        for row in rows
    ]


async def send_message(
    db: AsyncSession,
    auth: AuthSession,
    conversation_id: UUID,
    payload: MessageCreate,
    *,
    reserved_run_id: UUID | None = None,
    provider_stream: bool = False,
    on_run_accepted: Callable[[UUID], Awaitable[None]] | None = None,
    record_user_message: bool = True,
    parent_run_id: UUID | None = None,
) -> dict[str, Any]:
    conversation = await _conversation(db, auth, conversation_id, lock=True)
    existing = None
    if record_user_message:
        existing = (
            await db.execute(
                select(MimiMessage).where(
                    MimiMessage.conversation_id == conversation.id,
                    MimiMessage.client_id == payload.client_id,
                )
            )
        ).scalar_one_or_none()
    if existing is not None:
        if existing.content_sha256 != hashlib.sha256(payload.content.encode("utf-8")).hexdigest():
            raise _conflict("message_client_id_reused_with_different_content")
        return await conversation_view(db, auth, conversation_id)
    if (
        payload.expected_generation is not None
        and payload.expected_generation != conversation.generation
    ):
        raise _conflict("conversation_generation_stale")

    if (
        record_user_message
        and conversation.next_message_sequence == 1
        and not conversation.title_locked
    ):
        conversation.title_ciphertext = _seal_conversation_title(
            conversation, _conversation_title(payload.content)
        )

    dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
    provider_history = await _provider_history(db, conversation, dek)

    # Keep the existing preview confirmable until a typed replacement has
    # validated. A provider failure or ordinary text must never erase the
    # Owner's pending decision.
    pending_previews = (
        await db.execute(
            select(MimiChangeSet, MimiRun)
            .join(MimiRun, MimiChangeSet.run_id == MimiRun.id)
            .where(
                MimiRun.conversation_id == conversation.id,
                MimiChangeSet.state == "pending",
            )
            .with_for_update()
        )
    ).all()
    if len(pending_previews) > 1:
        raise _conflict("multiple_pending_previews_require_reconciliation")
    observed_pending = pending_previews[0] if pending_previews else None
    if payload.intent == "revise_pending_preview":
        if observed_pending is None:
            raise _conflict("pending_preview_missing")
        observed_change_set, _ = observed_pending
        if (
            observed_change_set.id != payload.expected_change_set_id
            or observed_change_set.digest_sha256 != payload.expected_change_set_digest
        ):
            raise _conflict("pending_preview_stale")
    prior_preview_operations = [
        json.loads(
            mimi_crypto.open_content(
                dek,
                old_change_set.operation_ciphertext,
                aad=mimi_crypto.change_set_aad(conversation.id, old_change_set.id),
            )
        )
        for old_change_set, _ in pending_previews
    ]
    force_task_tool = payload.intent == "revise_pending_preview"
    observed_pending_id = observed_pending[0].id if observed_pending else None
    observed_pending_digest = (
        observed_pending[0].digest_sha256 if observed_pending else None
    )

    now = datetime.now(UTC)
    settings = get_settings()
    if settings.is_production and not settings.mimi_live_provider_enabled:
        raise HTTPException(status_code=503, detail="mimi_live_route_not_enabled")
    task_context = await list_standard_tasks(db, auth, limit=10)
    source_versions = {
        f"task:{item['id']}": item["source_version"].isoformat()
        for item in task_context
        if item["source_version"] is not None
    }
    run_id = reserved_run_id or uuid7()
    task_id = uuid7()
    generation = conversation.generation
    deadline = now + timedelta(seconds=settings.mimi_run_deadline_seconds)
    lease = ExecutionLease(
        lease_id=uuid7(),
        owner_id=conversation.owner_id,
        run_id=run_id,
        capabilities=(TOOL_VERSION, "task.read.standard.v1"),
        issued_at=now,
        deadline=deadline,
        max_turns=1,
        max_tool_calls=1,
        cost_cap_minor=0,
        sensitivity=Sensitivity.STANDARD,
        source_versions=source_versions,
    )
    run = MimiRun(
        id=run_id,
        conversation_id=conversation.id,
        generation=generation,
        state="accepted",
        execution_lease=lease.model_dump(mode="json"),
        source_versions=source_versions,
        deadline=deadline,
    )
    db.add(run)
    # These ledger rows intentionally expose only scalar foreign keys rather
    # than ORM relationships. Establish the parent durably before SQLAlchemy
    # batches event/message/provider-call inserts, otherwise PostgreSQL may
    # order independent pending INSERTs ahead of mimi_run.
    await db.flush()
    await _append_event(db, run_id, "run.accepted", {})
    await _append_event(
        db,
        run_id,
        "context.tasks_read",
        {"count": len(task_context), "private_allowed": False},
    )

    user_sequence = conversation.next_message_sequence
    user_bytes = payload.content.encode("utf-8")
    if record_user_message:
        db.add(
            MimiMessage(
                conversation_id=conversation.id,
                run_id=run_id,
                client_id=payload.client_id,
                sequence=user_sequence,
                role="user",
                content_ciphertext=mimi_crypto.seal_content(
                    dek,
                    payload.content,
                    aad=mimi_crypto.message_aad(conversation.id, user_sequence, "user"),
                ),
                content_bytes=len(user_bytes),
                content_sha256=hashlib.sha256(user_bytes).hexdigest(),
            )
        )
        conversation.next_message_sequence += 1
    conversation.generation += 1

    live_messages = [
        {
            "role": "system",
            "content": (
                "Bạn là Mimi, trợ lý hội thoại của microSched. Trả lời bằng văn bản cho "
                "lời chào, câu hỏi, trao đổi thông thường và yêu cầu chưa đủ dữ kiện. "
                "QUY TẮC NGÔN NGỮ BẮT BUỘC: luôn trả lời user bằng tiếng Việt, trừ khi "
                "user yêu cầu rõ ràng một ngôn ngữ khác. Một lời chào đơn lẻ như 'hello' "
                "không phải yêu cầu đổi ngôn ngữ; hãy đáp ngắn gọn bằng tiếng Việt. "
                "MANDATORY LANGUAGE RULE: default every user-facing response to Vietnamese. "
                "Do not infer a language switch from a greeting or isolated foreign word. "
                "Không gọi tool cho lời chào hoặc khi user chưa rõ ràng muốn tạo, thêm "
                "hay lên lịch một Task. Khi thiếu dữ kiện cần thiết, hãy hỏi lại ngắn gọn "
                "bằng văn bản. Trong P1 chỉ tạo Task STANDARD: title là dữ kiện bắt buộc "
                "duy nhất; body, lịch, priority và checklist đều tùy chọn. Nếu user chỉ nói "
                "'Tạo task', chỉ hỏi title bằng một câu ngắn và không hỏi về private. "
                "Chỉ gọi task.create.v1 khi user rõ ràng yêu cầu tạo một "
                "Task; tối đa một proposal STANDARD và tuyệt đối không tự thực thi. "
                "Nếu user yêu cầu sửa preview đang chờ, hãy dùng previous pending preview "
                "bên dưới làm nền và tạo một proposal thay thế duy nhất. "
                "Mốc thời gian hiện tại của Owner là "
                f"{now.astimezone(OWNER_TIMEZONE).isoformat(timespec='seconds')} "
                "(Asia/Ho_Chi_Minh, UTC+07:00). Hãy diễn giải hôm nay, ngày mai và các "
                "mốc tương đối từ chính mốc này; không hỏi lại ngày tuyệt đối nếu đã đủ rõ. "
                f"Server-reserved task id: {task_id}. Current STANDARD Task context: "
                + json.dumps(task_context, ensure_ascii=False, default=str)
                + ". Previous pending preview: "
                + json.dumps(prior_preview_operations, ensure_ascii=False, default=str)
            ),
        },
        *provider_history,
        {"role": "user", "content": payload.content},
    ]
    route_kind = (
        f"openrouter-{settings.mimi_route_mode}-v1"
        if settings.mimi_live_provider_enabled
        else "deterministic-local-v1"
    )
    request_body = {
        "route": route_kind,
        "message_sha256": hashlib.sha256(user_bytes).hexdigest(),
        "history_sha256": _canonical_digest(provider_history),
        "prior_preview_sha256": _canonical_digest(prior_preview_operations),
        "tools": [TOOL_VERSION],
        "source_versions": source_versions,
    }
    call = MimiProviderCall(
        run_id=run_id,
        attempt=1,
        state="intent",
        request_fingerprint=_canonical_digest(request_body),
        route=(
            {
                "kind": "openrouter",
                "mode": settings.mimi_route_mode,
                "model": settings.mimi_route_model,
                "providers": (
                    [settings.mimi_route_provider]
                    if settings.mimi_route_mode == "exact"
                    else list(settings.mimi_allowed_provider_list)
                ),
                "quantizations": (
                    [settings.mimi_route_quantization]
                    if settings.mimi_route_mode == "exact"
                    else list(settings.mimi_allowed_quantization_list)
                ),
                "reasoning_effort": settings.mimi_route_reasoning_effort,
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "checkpoint": "provider_dispatch",
            }
            if settings.mimi_live_provider_enabled
            else {
                "kind": "deterministic",
                "environment": "local",
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "checkpoint": "provider_dispatch",
            }
        ),
    )
    db.add(call)
    await db.flush()

    if on_run_accepted is not None:
        await on_run_accepted(run_id)

    if settings.mimi_live_provider_enabled:
        # The external dispatch is separated by two durable boundaries: intent
        # commits before network I/O; terminal result commits before a canonical
        # change set is materialized. Unknown outcomes never auto-retry.
        run.state = "running"
        await db.commit()
        try:
            if provider_stream:
                stream_buffer: list[str] = []

                async def flush_stream_buffer() -> None:
                    nonlocal stream_buffer
                    if not stream_buffer:
                        return
                    text_delta = "".join(stream_buffer)
                    stream_buffer = []
                    sequence = await _append_event(db, run_id, "assistant.delta", {})
                    event = (
                        await db.execute(
                            select(MimiEvent).where(
                                MimiEvent.run_id == run_id,
                                MimiEvent.sequence == sequence,
                            )
                        )
                    ).scalar_one()
                    event.payload = {
                        "content_ciphertext": mimi_crypto.seal_content(
                            dek,
                            text_delta,
                            aad=mimi_crypto.event_content_aad(
                                run_id, sequence, "assistant.delta"
                            ),
                        ),
                        "content_bytes": len(text_delta.encode("utf-8")),
                    }
                    await db.commit()

                async def persist_stream_event(kind: str, event_payload: dict[str, Any]) -> None:
                    if kind == "assistant.delta":
                        text_delta = str(event_payload.get("text", ""))
                        if not text_delta:
                            return
                        stream_buffer.append(text_delta)
                        # Keep the durable ledger useful without turning every token into
                        # its own PostgreSQL write. The final callback flushes any tail.
                        if sum(map(len, stream_buffer)) < 256:
                            return
                        await flush_stream_buffer()
                    else:
                        if kind == "provider.connected":
                            call.state = "dispatched"
                        await _append_event(db, run_id, kind, event_payload)
                        await db.commit()

                completion = await openrouter_complete_stream(
                    live_messages,
                    settings=settings,
                    session_id=_provider_session_id(conversation.id),
                    on_event=persist_stream_event,
                    force_task_tool=force_task_tool,
                )
                await flush_stream_buffer()
            else:
                completion = await openrouter_complete(
                    live_messages,
                    settings=settings,
                    session_id=_provider_session_id(conversation.id),
                    force_task_tool=force_task_tool,
                )
            if force_task_tool and completion.kind != "task":
                raise RouteContractError("provider_revision_must_return_task_tool")
        except (ProviderDispatchError, RouteContractError) as error:
            outcome = error.outcome if isinstance(error, ProviderDispatchError) else "failed"
            status_code = error.status if isinstance(error, ProviderDispatchError) else None
            contract_error = str(error) if isinstance(error, RouteContractError) else None
            conversation = await _conversation(db, auth, conversation_id, lock=True)
            run = (
                await db.execute(select(MimiRun).where(MimiRun.id == run_id).with_for_update())
            ).scalar_one()
            call = (
                await db.execute(
                    select(MimiProviderCall)
                    .where(MimiProviderCall.run_id == run_id, MimiProviderCall.attempt == 1)
                    .with_for_update()
                )
            ).scalar_one()
            call.state = "unknown" if outcome == "unknown" else "failed"
            call.result = {
                "terminal": outcome,
                "status": status_code,
                "contract_error": contract_error,
                "response_id": (
                    error.response_id if isinstance(error, ProviderDispatchError) else None
                ),
            }
            run.provider_outcome = "unknown" if outcome == "unknown" else "failed"
            terminal_at = datetime.now(UTC)
            deadline_hit = terminal_at >= run.deadline
            run.state = (
                "deadline_exceeded"
                if deadline_hit
                else {
                    "unknown": "outcome_unknown",
                    "retryable": "retryable",
                    "failed": "halted",
                }[outcome]
            )
            run.error_code = (
                "run_deadline_exceeded"
                if deadline_hit
                else (
                    f"provider_contract_{contract_error}"
                    if contract_error
                    else f"provider_{outcome}"
                )
            )
            run.completed_at = terminal_at
            await _append_event(
                db,
                run_id,
                "run.deadline_exceeded" if deadline_hit else f"provider.{outcome}",
                {"status": status_code, "provider_outcome": run.provider_outcome},
            )
            assistant = (
                "Kết quả provider chưa xác định; Mimi sẽ không tự gửi lại yêu cầu."
                if outcome == "unknown"
                else (
                    "Provider chưa hoàn tất được lượt này. Bạn có thể chủ động thử lượt mới."
                    if outcome == "retryable"
                    else "Route hiện tại không đáp ứng contract; lượt chạy đã dừng."
                )
            )
            _add_assistant_message(db, conversation, run_id, dek, assistant)
            await db.flush()
            return await conversation_view(db, auth, conversation_id)

        conversation = await _conversation(db, auth, conversation_id, lock=True)
        dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
        run = (
            await db.execute(select(MimiRun).where(MimiRun.id == run_id).with_for_update())
        ).scalar_one()
        call = (
            await db.execute(
                select(MimiProviderCall)
                .where(MimiProviderCall.run_id == run_id, MimiProviderCall.attempt == 1)
                .with_for_update()
            )
        ).scalar_one()
        provider_args: dict[str, Any] | None = None
        if completion.kind == "text":
            if completion.text is None:
                raise RouteContractError("provider_text_result_missing")
            call.result = {
                "response_id": completion.response_id,
                "kind": "text",
                "result_sha256": hashlib.sha256(completion.text.encode("utf-8")).hexdigest(),
            }
        else:
            if completion.task is None:
                raise RouteContractError("provider_task_result_missing")
            provider_args = completion.task.model_dump(mode="json")
            provider_args["id"] = str(task_id)
            provider_args["is_private"] = False
            call.result = {
                "response_id": completion.response_id,
                "kind": "task",
                "result_sha256": _canonical_digest(provider_args),
                "tool": TOOL_VERSION,
            }
        call.state = "succeeded"
        call.usage = completion.usage
        call.route = {
            **call.route,
            "actual_provider": completion.provider,
            "actual_model": completion.model,
        }
        run.provider_outcome = "succeeded"
        await _append_event(
            db,
            run_id,
            "provider.succeeded",
            {"attempt": 1, "provider": completion.provider},
        )
        await db.flush()
        await db.commit()
        conversation = await _conversation(db, auth, conversation_id, lock=True)
        dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
        run = (
            await db.execute(select(MimiRun).where(MimiRun.id == run_id).with_for_update())
        ).scalar_one()
        if completion.kind == "text":
            assert completion.text is not None
            _add_assistant_message(db, conversation, run_id, dek, completion.text)
            run.state = "completed"
            run.completed_at = datetime.now(UTC)
            await _append_event(
                db,
                run_id,
                "run.terminal",
                {"state": "completed", "result": "text"},
            )
            await db.flush()
            return await conversation_view(db, auth, conversation_id)
        assert provider_args is not None
        operation_args = provider_args
    else:
        run.state = "running"
        call.state = "succeeded"
        operation_args = {
            "id": str(task_id),
            "title": _task_title(payload.content),
            "status": "open",
            "priority": None,
            "due_precision": "none",
            "due_on": None,
            "due_at": None,
            "body_md": None,
            "is_private": False,
            "items": [],
        }
        call.result = {
            "kind": "task_preview",
            "tool": TOOL_VERSION,
            "result_sha256": _canonical_digest(operation_args),
        }
        call.usage = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost": 0}
        run.provider_outcome = "succeeded"
        await _append_event(db, run_id, "provider.succeeded", {"attempt": 1})

    # Only a validated task proposal may replace pending authority. Re-query
    # after provider I/O because the conversation lock was released while the
    # external request ran.
    expected_generation_after_accept = generation + 1
    if conversation.generation != expected_generation_after_accept:
        run.state = "halted"
        run.error_code = "preview_frontier_changed"
        run.completed_at = datetime.now(UTC)
        await _append_event(db, run_id, "change_set.frontier_changed", {})
        _add_assistant_message(
            db,
            conversation,
            run_id,
            dek,
            "Conversation đã thay đổi trong lúc Mimi chuẩn bị preview; "
            "preview hiện tại được giữ nguyên.",
        )
        await db.flush()
        return await conversation_view(db, auth, conversation_id)

    current_pending_preview: tuple[MimiChangeSet, MimiRun] | None = None
    if observed_pending_id is not None:
        current_pending_preview = (
            await db.execute(
                select(MimiChangeSet, MimiRun)
                .join(MimiRun, MimiChangeSet.run_id == MimiRun.id)
                .where(
                    MimiRun.conversation_id == conversation.id,
                    MimiChangeSet.id == observed_pending_id,
                    MimiChangeSet.digest_sha256 == observed_pending_digest,
                    MimiChangeSet.state == "pending",
                )
                .with_for_update()
            )
        ).one_or_none()
        if current_pending_preview is None:
            run.state = "halted"
            run.error_code = "preview_frontier_changed"
            run.completed_at = datetime.now(UTC)
            await _append_event(db, run_id, "change_set.frontier_changed", {})
            _add_assistant_message(
                db,
                conversation,
                run_id,
                dek,
                "Preview nền đã thay đổi; Mimi không thay thế quyết định mới hơn của bạn.",
            )
            await db.flush()
            return await conversation_view(db, auth, conversation_id)

    if current_pending_preview is not None:
        old_change_set, old_run = current_pending_preview
        old_change_set.state = "stale"
        old_run.state = "halted"
        old_run.error_code = "superseded_by_validated_preview"
        old_run.completed_at = datetime.now(UTC)
        await _append_event(
            db,
            old_run.id,
            "change_set.superseded",
            {"change_set_id": str(old_change_set.id)},
        )

    change_set_id = uuid7()
    operation_id = uuid7()
    nonce = uuid7()
    expires_at = now + timedelta(minutes=settings.mimi_preview_ttl_minutes)
    operation = ChangeOperation(
        operation_id=operation_id,
        tool=TOOL_VERSION,
        args=operation_args,
        expected_entity_version=None,
        reversible=True,
    )
    frozen = FrozenChangeSet(
        change_set_id=change_set_id,
        run_id=run_id,
        operations=(operation,),
        expires_at=expires_at,
        nonce=nonce,
        digest_sha256="0" * 64,
        idempotency_key=f"preview:{change_set_id}",
    )
    digest = frozen.calculated_digest()
    change_set = MimiChangeSet(
        id=change_set_id,
        run_id=run_id,
        state="pending",
        digest_sha256=digest,
        nonce=nonce,
        expires_at=expires_at,
        operation_ciphertext=mimi_crypto.seal_content(
            dek,
            json.dumps(operation.model_dump(mode="json"), ensure_ascii=False),
            aad=mimi_crypto.change_set_aad(conversation.id, change_set_id),
        ),
        policy_version=POLICY_VERSION,
    )
    db.add(change_set)
    run.state = "waiting_confirmation"

    assistant = "Mình đã đóng băng một preview tạo Task. Hãy kiểm tra nội dung rồi xác nhận."
    _add_assistant_message(db, conversation, run_id, dek, assistant)
    await _append_event(
        db,
        run_id,
        "change_set.ready",
        {"change_set_id": str(change_set_id), "digest": digest},
    )
    await db.flush()
    return await conversation_view(db, auth, conversation_id)


async def confirm_change_set(
    db: AsyncSession,
    auth: AuthSession,
    change_set_id: UUID,
    payload: ConfirmationDecision,
    idempotency_key: str,
) -> dict[str, Any]:
    if not 1 <= len(idempotency_key) <= 160:
        raise HTTPException(status_code=422, detail="Idempotency-Key must be 1..160 characters")

    existing_by_key = (
        await db.execute(
            select(MimiExecutionReceipt, MimiChangeSet, MimiRun, MimiConversation)
            .join(MimiChangeSet, MimiExecutionReceipt.change_set_id == MimiChangeSet.id)
            .join(MimiRun, MimiChangeSet.run_id == MimiRun.id)
            .join(MimiConversation, MimiRun.conversation_id == MimiConversation.id)
            .where(
                MimiExecutionReceipt.idempotency_key == idempotency_key,
                MimiConversation.owner_id == _owner_id(auth),
            )
        )
    ).first()
    if existing_by_key is not None:
        receipt, existing_change_set, _, _ = existing_by_key
        if (
            existing_change_set.id != change_set_id
            or receipt.digest_sha256 != payload.digest
            or existing_change_set.nonce != payload.nonce
        ):
            raise _conflict("idempotency_key_reused_with_different_digest")
        return _receipt_read(receipt)

    result = await db.execute(
        select(MimiChangeSet, MimiRun, MimiConversation)
        .join(MimiRun, MimiChangeSet.run_id == MimiRun.id)
        .join(MimiConversation, MimiRun.conversation_id == MimiConversation.id)
        .where(
            MimiChangeSet.id == change_set_id,
            MimiConversation.owner_id == _owner_id(auth),
        )
        .with_for_update()
    )
    found = result.first()
    if found is None:
        raise _not_found()
    change_set, run, conversation = found

    existing_for_change_set = (
        await db.execute(
            select(MimiExecutionReceipt).where(MimiExecutionReceipt.change_set_id == change_set.id)
        )
    ).scalar_one_or_none()
    if existing_for_change_set is not None:
        raise _conflict("change_set_already_executed_with_different_idempotency_key")
    if payload.digest != change_set.digest_sha256 or payload.nonce != change_set.nonce:
        raise _conflict("change_set_binding_mismatch")
    if change_set.state != "pending":
        raise _conflict(f"change_set_{change_set.state}")
    now = datetime.now(UTC)
    if change_set.expires_at <= now:
        change_set.state = "expired"
        run.state = "deadline_exceeded"
        run.completed_at = now
        await _append_event(db, run.id, "change_set.expired", {})
        await db.flush()
        # Preserve the terminal expiry even though FastAPI will unwind the
        # request with 410 and the request dependency will roll back its next
        # empty transaction.
        await db.commit()
        raise HTTPException(status_code=410, detail="change_set_expired")

    if payload.decision == "reject":
        change_set.state = "rejected"
        run.state = "cancelled"
        run.completed_at = now
        await _append_event(db, run.id, "change_set.rejected", {})
        await db.flush()
        return {"change_set_id": change_set.id, "state": "rejected"}

    run.state = "executing"
    dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
    try:
        operation = json.loads(
            mimi_crypto.open_content(
                dek,
                change_set.operation_ciphertext,
                aad=mimi_crypto.change_set_aad(conversation.id, change_set.id),
            )
        )
    except (ValueError, json.JSONDecodeError) as error:
        change_set.state = "stale"
        raise _conflict("change_set_ciphertext_invalid") from error
    if operation.get("tool") != TOOL_VERSION:
        change_set.state = "stale"
        raise _conflict("unsupported_or_stale_tool_version")
    task_payload = TaskCreate.model_validate(operation["args"])
    if task_payload.is_private:
        raise _conflict("standard_change_set_cannot_create_private_task")
    task = await TaskStore().create(db, auth, task_payload)
    receipt = MimiExecutionReceipt(
        id=uuid7(),
        change_set_id=change_set.id,
        operation_id=UUID(operation["operation_id"]),
        task_id=task.id,
        digest_sha256=change_set.digest_sha256,
        idempotency_key=idempotency_key,
        result={"schema_version": "mimi.execution-receipt.v1", "task_id": str(task.id)},
        executed_at=now,
    )
    db.add(receipt)
    await db.flush()
    db.add(
        MimiRefreshMarker(
            receipt_id=receipt.id,
            state="pending",
            reason="mimi.task.create.committed",
        )
    )
    db.add(
        AuditLog(
            trace_id=conversation.id,
            turn_id=run.id,
            action="mimi.task.create.executed",
            tool=TOOL_VERSION,
            entity_type="task",
            entity_id=task.id,
            payload={"receipt_id": str(receipt.id), "digest": change_set.digest_sha256},
        )
    )
    await _append_event(
        db,
        run.id,
        "change_set.executed",
        {"receipt_id": str(receipt.id), "task_id": str(task.id)},
    )
    change_set.state = "executed"
    run.state = "completed"
    run.completed_at = now
    db.info[CRON_TIMER_RELOAD_INFO_KEY] = "mimi_task_create"
    await db.flush()
    return _receipt_read(receipt)


async def save_feedback(
    db: AsyncSession,
    auth: AuthSession,
    conversation_id: UUID,
    payload: FeedbackCreate,
) -> dict[str, Any]:
    conversation = await _conversation(db, auth, conversation_id, lock=True)
    existing = (
        await db.execute(
            select(MimiFeedback).where(
                MimiFeedback.conversation_id == conversation.id,
                MimiFeedback.client_id == payload.client_id,
            )
        )
    ).scalar_one_or_none()
    dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
    if existing is None:
        feedback_id = uuid7()
        existing = MimiFeedback(
            id=feedback_id,
            conversation_id=conversation.id,
            client_id=payload.client_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            comment_ciphertext=mimi_crypto.seal_content(
                dek,
                payload.comment,
                aad=mimi_crypto.feedback_aad(conversation.id, feedback_id, "comment"),
            ),
            expected_ciphertext=(
                mimi_crypto.seal_content(
                    dek,
                    payload.expected,
                    aad=mimi_crypto.feedback_aad(conversation.id, feedback_id, "expected"),
                )
                if payload.expected is not None
                else None
            ),
            evidence_bundle_ids=[str(item) for item in payload.evidence_bundle_ids],
        )
        db.add(existing)
        await db.flush()
    else:
        existing_comment = mimi_crypto.open_content(
            dek,
            existing.comment_ciphertext,
            aad=mimi_crypto.feedback_aad(conversation.id, existing.id, "comment"),
        )
        existing_expected = (
            mimi_crypto.open_content(
                dek,
                existing.expected_ciphertext,
                aad=mimi_crypto.feedback_aad(conversation.id, existing.id, "expected"),
            )
            if existing.expected_ciphertext is not None
            else None
        )
        if (
            existing.target_type != payload.target_type
            or existing.target_id != payload.target_id
            or existing_comment != payload.comment
            or existing_expected != payload.expected
            or existing.evidence_bundle_ids != [str(item) for item in payload.evidence_bundle_ids]
        ):
            raise _conflict("feedback_client_id_reused_with_different_content")
    return {
        "id": existing.id,
        "client_id": existing.client_id,
        "target_type": existing.target_type,
        "target_id": existing.target_id,
        "state": existing.state,
        "unresolved": existing.unresolved,
        "created_at": existing.created_at,
    }


async def conversation_view(
    db: AsyncSession, auth: AuthSession, conversation_id: UUID
) -> dict[str, Any]:
    conversation = await _conversation(db, auth, conversation_id)
    dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
    messages = (
        (
            await db.execute(
                select(MimiMessage)
                .where(MimiMessage.conversation_id == conversation.id)
                .order_by(MimiMessage.sequence)
                .limit(MAX_MESSAGES)
            )
        )
        .scalars()
        .all()
    )
    runs = (
        (
            await db.execute(
                select(MimiRun)
                .where(MimiRun.conversation_id == conversation.id)
                .order_by(MimiRun.generation.desc())
                .limit(MAX_MESSAGES)
            )
        )
        .scalars()
        .all()
    )
    run_ids = [run.id for run in runs]
    change_sets = []
    receipts = []
    events = []
    if run_ids:
        change_sets = (
            (
                await db.execute(
                    select(MimiChangeSet)
                    .where(MimiChangeSet.run_id.in_(run_ids))
                    .order_by(MimiChangeSet.created_at)
                )
            )
            .scalars()
            .all()
        )
        change_set_ids = [item.id for item in change_sets]
        if change_set_ids:
            receipts = (
                (
                    await db.execute(
                        select(MimiExecutionReceipt)
                        .where(MimiExecutionReceipt.change_set_id.in_(change_set_ids))
                        .order_by(MimiExecutionReceipt.executed_at)
                    )
                )
                .scalars()
                .all()
            )
        events = (
            (
                await db.execute(
                    select(MimiEvent)
                    .where(MimiEvent.run_id.in_(run_ids))
                    .order_by(MimiEvent.created_at, MimiEvent.sequence)
                    .limit(MAX_EVENTS)
                )
            )
            .scalars()
            .all()
        )
    feedback = (
        (
            await db.execute(
                select(MimiFeedback)
                .where(MimiFeedback.conversation_id == conversation.id)
                .order_by(MimiFeedback.created_at)
                .limit(MAX_MESSAGES)
            )
        )
        .scalars()
        .all()
    )
    return {
        "id": conversation.id,
        "sensitivity": conversation.sensitivity,
        "title": _open_conversation_title(conversation),
        "title_source": conversation.title_source,
        "title_locked": conversation.title_locked,
        "generation": conversation.generation,
        "metadata_version": conversation.metadata_version,
        "archived_at": conversation.archived_at,
        "updated_at": conversation.updated_at,
        "messages": [_message_read(row, dek) for row in messages],
        "runs": [
            {
                "id": row.id,
                "generation": row.generation,
                "state": row.state,
                "provider_outcome": row.provider_outcome,
                "deadline": row.deadline,
                "error_code": row.error_code,
                "created_at": row.created_at,
                "completed_at": row.completed_at,
            }
            for row in reversed(runs)
        ],
        "change_sets": [
            {
                "id": row.id,
                "run_id": row.run_id,
                "state": row.state,
                "digest": row.digest_sha256,
                "nonce": row.nonce,
                "expires_at": row.expires_at,
                "operation": json.loads(
                    mimi_crypto.open_content(
                        dek,
                        row.operation_ciphertext,
                        aad=mimi_crypto.change_set_aad(conversation.id, row.id),
                    )
                ),
                "policy_version": row.policy_version,
            }
            for row in change_sets
        ],
        "receipts": [_receipt_read(row) for row in receipts],
        "events": [_event_read(row, dek) for row in events],
        "feedback": [
            {
                "id": row.id,
                "client_id": row.client_id,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "state": row.state,
                "unresolved": row.unresolved,
                "created_at": row.created_at,
            }
            for row in feedback
        ],
    }


async def run_events_after(
    db: AsyncSession,
    auth: AuthSession,
    run_id: UUID,
    *,
    after: int = 0,
) -> dict[str, Any]:
    found = (
        await db.execute(
            select(MimiRun, MimiConversation)
            .join(MimiConversation, MimiRun.conversation_id == MimiConversation.id)
            .where(
                MimiRun.id == run_id,
                MimiConversation.owner_id == _owner_id(auth),
            )
        )
    ).first()
    if found is None:
        raise _not_found()
    run, conversation = found
    dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
    events = (
        (
            await db.execute(
                select(MimiEvent)
                .where(MimiEvent.run_id == run.id, MimiEvent.sequence > after)
                .order_by(MimiEvent.sequence)
                .limit(MAX_EVENTS)
            )
        )
        .scalars()
        .all()
    )
    return {
        "run_id": run.id,
        "conversation_id": conversation.id,
        "state": run.state,
        "provider_outcome": run.provider_outcome,
        "deadline": run.deadline,
        "completed_at": run.completed_at,
        "events": [_event_read(row, dek) for row in events],
    }


async def prepare_run_resume(
    db: AsyncSession,
    auth: AuthSession,
    run_id: UUID,
) -> tuple[UUID, UUID, MessageCreate]:
    """Fence one safe successor without redispatching an unknown outcome."""
    found = (
        await db.execute(
            select(MimiRun, MimiConversation)
            .join(MimiConversation, MimiRun.conversation_id == MimiConversation.id)
            .where(
                MimiRun.id == run_id,
                MimiConversation.owner_id == _owner_id(auth),
            )
            .with_for_update()
        )
    ).first()
    if found is None:
        raise _not_found()
    run, conversation = found
    if run.provider_outcome == "unknown" or run.state == "outcome_unknown":
        raise _conflict("mimi_run_outcome_unknown_reconciliation_required")
    if run.state not in {"retryable", "deadline_exceeded"}:
        raise _conflict(f"mimi_run_{run.state}_cannot_resume")
    if run.error_code and run.error_code.startswith("resumed_by:"):
        raise _conflict(run.error_code)

    source_message = (
        await db.execute(
            select(MimiMessage).where(
                MimiMessage.run_id == run.id,
                MimiMessage.role == "user",
            )
        )
    ).scalar_one_or_none()
    if source_message is None:
        raise _conflict("mimi_run_resume_source_missing")
    dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
    content = mimi_crypto.open_content(
        dek,
        source_message.content_ciphertext,
        aad=mimi_crypto.message_aad(
            conversation.id, source_message.sequence, source_message.role
        ),
    )
    successor_id = uuid7()
    run.error_code = f"resumed_by:{successor_id}"
    await _append_event(
        db,
        run.id,
        "run.resume_reserved",
        {"successor_run_id": str(successor_id), "checkpoint": "provider_dispatch"},
    )
    return (
        conversation.id,
        successor_id,
        MessageCreate(
            client_id=f"resume:{run.id}:{successor_id}",
            content=content,
            expected_generation=conversation.generation,
        ),
    )


async def reconcile_unknown_run(
    db: AsyncSession,
    auth: AuthSession,
    run_id: UUID,
) -> dict[str, Any]:
    def needs_reconciliation(candidate: MimiRun) -> bool:
        return candidate.state == "outcome_unknown" or (
            candidate.state in {"cancelled", "deadline_exceeded"}
            and candidate.provider_outcome == "unknown"
        )

    run = (
        await db.execute(
            select(MimiRun)
            .join(MimiConversation, MimiRun.conversation_id == MimiConversation.id)
            .where(
                MimiRun.id == run_id,
                MimiConversation.owner_id == _owner_id(auth),
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise _not_found()
    if not needs_reconciliation(run):
        raise _conflict(f"mimi_run_{run.state}_does_not_need_reconciliation")
    call = (
        await db.execute(
            select(MimiProviderCall)
            .where(MimiProviderCall.run_id == run.id)
            .order_by(MimiProviderCall.attempt.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    call_id = call.id if call is not None else None
    response_id = call.result.get("response_id") if call and call.result else None
    if not isinstance(response_id, str) or not response_id:
        raise _conflict("provider_generation_id_unavailable")
    await db.rollback()
    try:
        metadata = await openrouter_get_generation(response_id)
    except (ProviderDispatchError, RouteContractError) as error:
        raise _conflict("provider_reconciliation_unavailable") from error

    # Do not hold a database row lock across provider I/O. Re-lock and verify
    # that cancel/resume/reconcile did not advance the run while we waited.
    run = (
        await db.execute(select(MimiRun).where(MimiRun.id == run_id).with_for_update())
    ).scalar_one()
    if not needs_reconciliation(run):
        raise _conflict(f"mimi_run_{run.state}_changed_during_reconciliation")
    call = (
        await db.execute(
            select(MimiProviderCall).where(MimiProviderCall.id == call_id).with_for_update()
        )
    ).scalar_one()
    locked_response_id = call.result.get("response_id") if call.result else None
    if locked_response_id != response_id:
        raise _conflict("provider_generation_changed_during_reconciliation")

    safe_fields = {
        key: metadata[key]
        for key in (
            "id",
            "model",
            "provider_name",
            "created_at",
            "tokens_prompt",
            "tokens_completion",
            "native_tokens_prompt",
            "native_tokens_completion",
            "cache_discount",
            "total_cost",
            "latency",
            "generation_time",
        )
        if key in metadata
    }
    call.state = "succeeded"
    call.result = {
        **(call.result or {}),
        "terminal": "reconciled_generation_exists",
        "generation": safe_fields,
    }
    run.provider_outcome = "succeeded"
    run.state = "halted"
    run.error_code = "provider_result_unavailable_after_reconcile"
    run.completed_at = datetime.now(UTC)
    await _append_event(
        db,
        run.id,
        "run.reconciled",
        {"provider_outcome": "succeeded", "result_available": False},
    )
    await db.flush()
    return {
        "run_id": run.id,
        "state": run.state,
        "provider_outcome": run.provider_outcome,
        "result_available": False,
    }


async def finish_interrupted_run(
    db: AsyncSession,
    auth: AuthSession,
    run_id: UUID,
    *,
    cancelled: bool,
) -> None:
    found = (
        await db.execute(
            select(MimiRun)
            .join(MimiConversation, MimiRun.conversation_id == MimiConversation.id)
            .where(
                MimiRun.id == run_id,
                MimiConversation.owner_id == _owner_id(auth),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if found is None:
        return
    run = found
    call = (
        await db.execute(
            select(MimiProviderCall)
            .where(MimiProviderCall.run_id == run.id)
            .order_by(MimiProviderCall.attempt.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if run.completed_at is not None or run.state in {
        "completed",
        "waiting_confirmation",
        "cancelled",
        "halted",
        "retryable",
        "outcome_unknown",
        "deadline_exceeded",
    }:
        return

    provider_may_have_received_request = call is not None and call.state == "dispatched"
    run.completed_at = datetime.now(UTC)
    if cancelled:
        run.state = "cancelled"
        run.error_code = "owner_cancelled"
    else:
        run.state = "halted"
        run.error_code = "worker_failed"
    if provider_may_have_received_request:
        run.provider_outcome = "unknown"
        call.state = "unknown"
        call.result = {"terminal": "unknown", "reason": run.error_code}
    elif call is not None:
        call.state = "failed"
        call.result = {"terminal": "failed", "reason": run.error_code}
    await _append_event(
        db,
        run.id,
        "run.cancelled" if cancelled else "run.halted",
        {"provider_outcome": run.provider_outcome},
    )
    await db.flush()


async def reconcile_refresh_markers(db: AsyncSession) -> int:
    """Acknowledge durable pending markers after the scheduler has reloaded state."""
    table = await db.execute(text("SELECT to_regclass('microsched.mimi_refresh_marker')"))
    if table.scalar_one_or_none() is None:
        return 0
    rows = (
        (
            await db.execute(
                select(MimiRefreshMarker)
                .where(MimiRefreshMarker.state == "pending")
                .order_by(MimiRefreshMarker.created_at)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now(UTC)
    for row in rows:
        row.state = "reconciled"
        row.attempt_count += 1
        row.reconciled_at = now
    await db.flush()
    return len(rows)


async def reconcile_refresh_markers_after_snapshot(db: AsyncSession) -> None:
    """Cron hook: ACK markers only after a successful durable-state snapshot."""
    if await reconcile_refresh_markers(db):
        await db.commit()
