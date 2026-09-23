"""Bounded Mimi P1 orchestration over the existing Task transaction seam."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy import and_, false, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import crypto as mimi_crypto
from app.agent.compaction import CheckpointSource, make_checkpoint
from app.agent.context import (
    AssistantText,
    Blocked,
    Clarification,
    ContextEnvelope,
    Draft,
    PendingDraft,
    PendingPreview,
    PreviewCandidate,
)
from app.agent.context_builder import assemble_context, rebind_after_read
from app.agent.contracts import ChangeOperation, ExecutionLease, FrozenChangeSet, Sensitivity
from app.agent.loop import LoopLimits, run_read_loop
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
    AgentCompletion,
    ProviderCompletion,
    ProviderDispatchError,
    RouteContractError,
)
from app.agent.openrouter import (
    complete as openrouter_complete,
)
from app.agent.openrouter import complete_stream as openrouter_complete_stream
from app.agent.openrouter import get_generation as openrouter_get_generation
from app.agent.policy import load_standard_policy
from app.agent.runtime import run_guard_key
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL, READ_TOOLS, execute_read_tool
from app.core.db import get_engine, get_sessionmaker
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
    expected_change_set_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value

    @model_validator(mode="after")
    def bind_revision_to_pending_preview(self) -> MessageCreate:
        target = (self.expected_change_set_id, self.expected_change_set_digest)
        if self.intent == "revise_pending_preview" and any(item is None for item in target):
            raise ValueError("preview revision requires id and digest")
        if self.intent == "auto" and any(item is not None for item in target):
            raise ValueError("preview target requires revise_pending_preview intent")
        return self


class ConfirmationDecision(BaseModel):
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    nonce: UUID
    decision: Literal["confirm", "reject"]


class DraftDirectionDecision(BaseModel):
    draft_id: UUID
    expected_revision: int = Field(ge=1)
    expected_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["approve", "reject"]


async def _latest_draft_state(
    db: AsyncSession, conversation_id: UUID
) -> tuple[PendingDraft | None, MimiEvent | None]:
    ready = (
        await db.execute(
            select(MimiEvent)
            .join(MimiRun, MimiEvent.run_id == MimiRun.id)
            .where(MimiRun.conversation_id == conversation_id, MimiEvent.kind == "draft.ready")
            .order_by(MimiEvent.created_at.desc(), MimiEvent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if ready is None:
        return None, None
    draft_id = str(ready.payload["draft_id"])
    decision = (
        await db.execute(
            select(MimiEvent)
            .join(MimiRun, MimiEvent.run_id == MimiRun.id)
            .where(
                MimiRun.conversation_id == conversation_id,
                MimiEvent.kind == "draft.direction_decision",
                MimiEvent.payload["draft_id"].as_string() == draft_id,
            )
            .order_by(MimiEvent.created_at.desc(), MimiEvent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    state = (
        "approved"
        if decision is not None and decision.payload.get("decision") == "approve"
        else "rejected"
        if decision is not None
        else "pending"
    )
    return (
        PendingDraft(
            id=UUID(draft_id),
            revision=int(ready.payload["revision"]),
            content_sha256=str(ready.payload["content_sha256"]),
            direction_state=state,
        ),
        ready,
    )


async def decide_draft_direction(
    db: AsyncSession,
    auth: AuthSession,
    conversation_id: UUID,
    payload: DraftDirectionDecision,
) -> dict[str, Any]:
    """Bind Owner direction to one exact draft; it never confirms a preview."""

    await _conversation(db, auth, conversation_id, lock=True)
    latest, ready = await _latest_draft_state(db, conversation_id)
    if (
        latest is None
        or ready is None
        or (
            latest.id != payload.draft_id
            or latest.revision != payload.expected_revision
            or latest.content_sha256 != payload.expected_content_sha256
        )
    ):
        raise _conflict("draft_direction_stale")
    if latest.direction_state != "pending":
        if latest.direction_state == ("approved" if payload.decision == "approve" else "rejected"):
            return {"draft_id": latest.id, "state": latest.direction_state}
        raise _conflict("draft_direction_already_decided")
    await _append_event(
        db,
        ready.run_id,
        "draft.direction_decision",
        {
            "draft_id": str(latest.id),
            "expected_revision": latest.revision,
            "expected_content_sha256": latest.content_sha256,
            "decision": payload.decision,
            "actor_id": str(_owner_id(auth)),
            "decided_at": datetime.now(UTC).isoformat(),
        },
    )
    await db.flush()
    return {
        "draft_id": latest.id,
        "state": "approved" if payload.decision == "approve" else "rejected",
    }


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


def _manifest_receipt(envelope: ContextEnvelope) -> dict[str, Any]:
    """Expose provenance metadata, never the source rows or untrusted query prose."""

    manifest = envelope.manifest
    return {
        "manifest_sha256": manifest.sha256(),
        "policy_id": manifest.policy_id,
        "policy_sha256": manifest.policy_sha256,
        "tool_registry_sha256": manifest.tool_registry_sha256,
        "output_schema_sha256": manifest.output_schema_sha256,
        "checkpoint_id": str(manifest.checkpoint_id) if manifest.checkpoint_id else None,
        "checkpoint_frontier": manifest.checkpoint_frontier,
        "transcript_range": manifest.transcript_range,
        "input_upper_bound": manifest.budget.serialized_input_upper_bound,
        "context_limit": manifest.budget.context_limit,
        "output_reserve": manifest.budget.output_reserve,
        "remaining_turns": manifest.budget.remaining_turns,
        "remaining_tool_calls": manifest.budget.remaining_tool_calls,
        "requested_model": manifest.route.requested_model,
        "requested_effort": manifest.route.requested_effort,
        "sources": [
            {
                "source_id": source.source_id,
                "count": source.count,
                "coverage": source.coverage,
                "omitted_fields": source.omitted_fields,
                "data_as_of": source.data_as_of.isoformat() if source.data_as_of else None,
                "has_next_cursor": source.next_cursor is not None,
                "content_sha256": source.content_sha256,
                "version": source.version,
            }
            for source in manifest.sources
        ],
    }


def _reported_usage(usage: dict[str, Any] | None) -> dict[str, int | float]:
    """Return only buyer-reported numeric usage; absence is not estimated as zero."""

    if not isinstance(usage, dict):
        return {}
    reported: dict[str, int | float] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost", "cached_tokens"):
        value = usage.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool) and value >= 0:
            reported[key] = value
    for field, output in (
        ("prompt_tokens_details", "cache_read_tokens"),
        ("completion_tokens_details", "reasoning_tokens"),
    ):
        details = usage.get(field)
        key = "cached_tokens" if field == "prompt_tokens_details" else "reasoning_tokens"
        if isinstance(details, dict):
            value = details.get(key)
            if isinstance(value, int | float) and not isinstance(value, bool) and value >= 0:
                reported[output] = value
    return reported


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


def _deterministic_turn(
    content: str,
    task_id: UUID,
    *,
    awaiting_task_title: bool,
) -> tuple[Literal["text", "task"], str | dict[str, Any]]:
    """Classify the local route without pretending every message is a write intent."""
    normalized = " ".join(content.strip().split())
    folded = normalized.casefold().rstrip(".!?")
    greetings = {
        "chào",
        "chào mimi",
        "xin chào",
        "xin chào mimi",
        "hello",
        "hello mimi",
        "hi",
        "hi mimi",
    }
    if folded in greetings:
        return "text", "Chào bạn! Mình là Mimi. Hôm nay mình có thể giúp gì cho bạn?"

    action = re.fullmatch(
        r"(?is)(?:hãy\s+)?(?:tạo|thêm|lên\s+lịch|create|add)\s+"
        r"(?:một\s+)?(?:task|việc|công\s+việc|nhiệm\s+vụ)"
        r"(?:\s*[:\-]\s*|\s+)?(.*)",
        normalized,
    )
    if action is None and not awaiting_task_title:
        return (
            "text",
            "Mình đã nhận được tin nhắn. Ở route local, mình chỉ tạo preview khi "
            "bạn yêu cầu rõ ràng tạo một Task.",
        )
    title = action.group(1).strip().strip('"“”') if action is not None else normalized.strip('"“”')
    if awaiting_task_title and title.casefold() in {
        "thôi",
        "không",
        "hủy",
        "huỷ",
        "bỏ qua",
    }:
        return "text", "Được, mình sẽ không tạo preview Task cho yêu cầu đó."
    if title.casefold() in {"", "giúp tôi", "giúp mình", "cho tôi", "cho mình", "mới"}:
        return "text", "Bạn muốn đặt tiêu đề Task là gì?"
    operation_args = {
        "id": str(task_id),
        "title": title[:200],
        "status": "open",
        "priority": None,
        "due_precision": "none",
        "due_on": None,
        "due_at": None,
        "body_md": None,
        "is_private": False,
        "items": [],
    }
    return "task", operation_args


def _provider_contract_code(error: str) -> str:
    stable = re.sub(r"[^a-z0-9_]+", "_", error.casefold()).strip("_")
    return stable[:120] or "invalid_terminal"


def _transaction_lock_key(namespace: str, value: str) -> int:
    raw = hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).digest()[:8]
    return int.from_bytes(raw, byteorder="big", signed=True)


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


def _conversation_summary(row: MimiConversation, *, latest_run_state: str | None) -> dict[str, Any]:
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


async def _prepare_context_history(
    db: AsyncSession,
    conversation: MimiConversation,
    dek: bytes,
    run_id: UUID,
    user_sequence: int,
    pending_preview: dict[str, Any] | None,
    pending_draft: dict[str, Any] | None,
) -> tuple[list[dict[str, str]], tuple[int, int] | None, dict[str, Any] | None, UUID | None]:
    """Use an active validated checkpoint, replacing it before any silent suffix loss."""

    policy = load_standard_policy()
    prior: dict[str, Any] | None = None
    checkpoint_id: UUID | None = None
    if conversation.context_frontier_sequence:
        active = (
            await db.execute(
                select(MimiEvent)
                .join(MimiRun, MimiEvent.run_id == MimiRun.id)
                .where(
                    MimiRun.conversation_id == conversation.id,
                    MimiEvent.kind == "context.checkpoint.activated",
                    MimiEvent.payload["frontier"].as_integer()
                    == conversation.context_frontier_sequence,
                )
                .order_by(MimiEvent.created_at.desc(), MimiEvent.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if active is None:
            raise _conflict("mimi_active_checkpoint_missing")
        prior = json.loads(
            mimi_crypto.open_content(
                dek,
                str(active.payload["content_ciphertext"]),
                aad=mimi_crypto.event_content_aad(active.run_id, active.sequence, active.kind),
            )
        )
        if (
            prior.get("frontier") != conversation.context_frontier_sequence
            or prior.get("policy_sha256") != policy.sha256
            or _canonical_digest(prior) != active.payload.get("content_sha256")
        ):
            raise _conflict("mimi_active_checkpoint_invalid")
        refs = prior.get("source_refs")
        if not isinstance(refs, list) or len(refs) > 1000:
            raise _conflict("mimi_active_checkpoint_sources_invalid")
        source_ids = [UUID(str(item["id"])) for item in refs]
        source_rows = (
            await db.execute(
                select(MimiMessage.id, MimiMessage.sequence, MimiMessage.content_sha256).where(
                    MimiMessage.conversation_id == conversation.id,
                    MimiMessage.id.in_(source_ids),
                )
            )
        ).all()
        by_id = {str(item.id): item for item in source_rows}
        if any(
            str(ref["id"]) not in by_id
            or by_id[str(ref["id"])].sequence != ref["sequence"]
            or by_id[str(ref["id"])].content_sha256 != ref["sha256"]
            for ref in refs
        ):
            raise _conflict("mimi_active_checkpoint_source_drift")
        checkpoint_id = active.id
    rows = (
        (
            await db.execute(
                select(MimiMessage)
                .where(
                    MimiMessage.conversation_id == conversation.id,
                    MimiMessage.role.in_(("user", "assistant")),
                    MimiMessage.sequence > conversation.context_frontier_sequence,
                    MimiMessage.sequence < user_sequence,
                )
                .order_by(MimiMessage.sequence)
                .limit(1001)
            )
        )
        .scalars()
        .all()
    )
    if len(rows) > 1000:
        raise _conflict("mimi_history_exceeds_compaction_window")
    compact_count = 0
    suffix_bytes = sum(row.content_bytes for row in rows)
    while len(rows) - compact_count > 12 or suffix_bytes > 32_768:
        if compact_count >= len(rows):
            raise _conflict("mimi_history_message_exceeds_context_window")
        suffix_bytes -= rows[compact_count].content_bytes
        compact_count += 1
    if compact_count:
        sources = [
            CheckpointSource(
                id=row.id,
                sequence=row.sequence,
                role=row.role,
                content_sha256=row.content_sha256,
                content=mimi_crypto.open_content(
                    dek,
                    row.content_ciphertext,
                    aad=mimi_crypto.message_aad(conversation.id, row.sequence, row.role),
                ),
            )
            for row in rows[:compact_count]
        ]
        checkpoint = make_checkpoint(
            sources=sources,
            prior=prior,
            policy_sha256=policy.sha256,
            pending_preview=pending_preview,
            pending_draft=pending_draft,
        )
        sequence = await _append_event(db, run_id, "context.checkpoint.activated", {})
        event = (
            await db.execute(
                select(MimiEvent).where(
                    MimiEvent.run_id == run_id,
                    MimiEvent.sequence == sequence,
                )
            )
        ).scalar_one()
        event.payload = {
            "frontier": checkpoint["frontier"],
            "source_count": len(sources),
            "content_sha256": _canonical_digest(checkpoint),
            "content_ciphertext": mimi_crypto.seal_content(
                dek,
                json.dumps(checkpoint, ensure_ascii=False),
                aad=mimi_crypto.event_content_aad(run_id, sequence, event.kind),
            ),
        }
        conversation.context_frontier_sequence = checkpoint["frontier"]
        await db.flush()
        prior = checkpoint
        checkpoint_id = event.id
        rows = rows[compact_count:]
    messages = [
        {
            "role": row.role,
            "content": mimi_crypto.open_content(
                dek,
                row.content_ciphertext,
                aad=mimi_crypto.message_aad(conversation.id, row.sequence, row.role),
            ),
        }
        for row in rows
    ]
    transcript_range = (rows[0].sequence, rows[-1].sequence) if rows else None
    return messages, transcript_range, prior, checkpoint_id


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
    elif row.kind == "context.checkpoint.activated":
        payload = {
            "frontier": payload.get("frontier"),
            "source_count": payload.get("source_count"),
            "content_sha256": payload.get("content_sha256"),
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
            statement.order_by(
                MimiConversation.updated_at.desc(), MimiConversation.id.desc()
            ).limit(limit + 1)
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
    settings = get_settings()
    if settings.mimi_context_v1_enabled and settings.mimi_live_provider_enabled:
        provider_history: list[dict[str, str]] = []
        transcript_range: tuple[int, int] | None = None
    else:
        provider_history = await _provider_history(db, conversation, dek)
        transcript_range = None

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
    pending_draft, draft_ready = await _latest_draft_state(db, conversation.id)
    pending_draft_content: str | None = None
    if settings.mimi_context_v1_enabled and settings.mimi_live_provider_enabled and draft_ready:
        draft_message = (
            await db.execute(
                select(MimiMessage).where(
                    MimiMessage.conversation_id == conversation.id,
                    MimiMessage.run_id == draft_ready.run_id,
                    MimiMessage.sequence == draft_ready.payload["message_sequence"],
                    MimiMessage.role == "assistant",
                )
            )
        ).scalar_one_or_none()
        if draft_message is None or draft_message.content_sha256 != pending_draft.content_sha256:
            raise _conflict("pending_draft_content_missing_or_changed")
        pending_draft_content = mimi_crypto.open_content(
            dek,
            draft_message.content_ciphertext,
            aad=mimi_crypto.message_aad(
                conversation.id, draft_message.sequence, draft_message.role
            ),
        )
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
    observed_pending_digest = observed_pending[0].digest_sha256 if observed_pending else None

    now = datetime.now(UTC)
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
        capabilities=(
            (*sorted(READ_TOOLS), CREATE_CANDIDATE_TOOL)
            if settings.mimi_context_v1_enabled and settings.mimi_live_provider_enabled
            else (TOOL_VERSION, "task.read.standard.v1")
        ),
        issued_at=now,
        deadline=deadline,
        max_turns=4 if settings.mimi_context_v1_enabled else 1,
        max_tool_calls=6 if settings.mimi_context_v1_enabled else 1,
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

    checkpoint: dict[str, Any] | None = None
    checkpoint_id: UUID | None = None
    if settings.mimi_context_v1_enabled and settings.mimi_live_provider_enabled:
        (
            provider_history,
            transcript_range,
            checkpoint,
            checkpoint_id,
        ) = await _prepare_context_history(
            db,
            conversation,
            dek,
            run_id,
            user_sequence,
            (
                {
                    "id": str(observed_pending[0].id),
                    "digest": observed_pending[0].digest_sha256,
                    "expiry": observed_pending[0].expires_at.isoformat(),
                    "source_versions": observed_pending[1].source_versions,
                }
                if observed_pending
                else None
            ),
            pending_draft.model_dump(mode="json") if pending_draft else None,
        )

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
    context_envelope = None
    if settings.mimi_context_v1_enabled and settings.mimi_live_provider_enabled:
        pending_preview = (
            PendingPreview(
                id=observed_pending[0].id,
                digest=observed_pending[0].digest_sha256,
                source_versions=observed_pending[1].source_versions,
                expiry=observed_pending[0].expires_at,
            )
            if observed_pending
            else None
        )
        try:
            context_envelope, live_messages = assemble_context(
                lease=lease,
                reserved_task_id=task_id,
                conversation_id=conversation.id,
                generation=generation,
                request_id=payload.client_id,
                transcript_suffix=provider_history,
                current_user_turn=payload.content,
                task_context=task_context,
                pending_preview_content=prior_preview_operations,
                pending_preview=pending_preview,
                pending_draft=pending_draft,
                checkpoint=checkpoint["summary"] if checkpoint else None,
                checkpoint_id=checkpoint_id,
                checkpoint_frontier=conversation.context_frontier_sequence,
                transcript_range=transcript_range,
                settings=settings,
                remaining_turns=lease.max_turns,
                remaining_tool_calls=lease.max_tool_calls,
                pending_draft_content=pending_draft_content,
            )
        except ValueError as error:
            run.state = "budget_exceeded"
            run.error_code = str(error)[:120]
            run.completed_at = datetime.now(UTC)
            _add_assistant_message(
                db,
                conversation,
                run_id,
                dek,
                "Ngữ cảnh vượt giới hạn an toàn của route; cần compact hoặc thu hẹp phạm vi.",
            )
            await _append_event(
                db, run_id, "run.terminal", {"state": run.state, "error_code": run.error_code}
            )
            await db.flush()
            return await conversation_view(db, auth, conversation_id)
        await _append_event(db, run_id, "context.manifest", _manifest_receipt(context_envelope))
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
        "tools": list(lease.capabilities),
        "source_versions": source_versions,
    }
    if context_envelope is not None:
        request_body["context_manifest_sha256"] = context_envelope.manifest.sha256()
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
                **(
                    {"run_guard_version": 1}
                    if settings.mimi_context_v1_enabled and settings.mimi_live_provider_enabled
                    else {}
                ),
            }
            if settings.mimi_live_provider_enabled
            else {
                "kind": "deterministic",
                "environment": "local",
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "checkpoint": "provider_dispatch",
                **(
                    {"run_guard_version": 1}
                    if settings.mimi_context_v1_enabled and settings.mimi_live_provider_enabled
                    else {}
                ),
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
        # Fence the may-have-been-sent boundary durably before entering the
        # transport. Cancellation or an unexpected worker failure after this
        # point is unknown unless the adapter returns a definitive outcome.
        call.state = "dispatched"
        await db.commit()
        agent_result_kind: str | None = None
        agent_stop_code: str | None = None
        try:
            if context_envelope is not None:
                aggregate_read_seen = False

                async def persist_agent_event(kind: str, event_payload: dict[str, Any]) -> None:
                    if kind == "provider.response_identity":
                        response_id = event_payload.get("response_id")
                        if isinstance(response_id, str) and response_id:
                            call.result = {**(call.result or {}), "response_id": response_id}
                            await _append_event(db, run_id, kind, {"response_id_recorded": True})
                    elif kind == "assistant.delta":
                        delta = str(event_payload.get("text", ""))
                        if not delta:
                            return
                        sequence = await _append_event(db, run_id, kind, {})
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
                                delta,
                                aad=mimi_crypto.event_content_aad(run_id, sequence, kind),
                            ),
                            "content_bytes": len(delta.encode("utf-8")),
                        }
                    else:
                        await _append_event(db, run_id, kind, event_payload)
                    await db.commit()

                async def invoke_agent_model(
                    messages: list[dict[str, Any]], turn: int
                ) -> AgentCompletion:
                    nonlocal call
                    if turn > 1:
                        call = MimiProviderCall(
                            run_id=run_id,
                            attempt=turn,
                            state="intent",
                            request_fingerprint=_canonical_digest(
                                {
                                    "messages": messages,
                                    "manifest": context_envelope.manifest.sha256(),
                                }
                            ),
                            route={
                                **call.route,
                                "agent_turn": turn,
                                "checkpoint": "provider_dispatch",
                            },
                        )
                        db.add(call)
                        await db.commit()
                        call.state = "dispatched"
                        await db.commit()
                    if provider_stream:
                        result = await openrouter_complete_stream(
                            messages,
                            settings=settings,
                            session_id=_provider_session_id(conversation.id),
                            on_event=persist_agent_event,
                            force_task_tool=force_task_tool,
                            agent_contract=True,
                        )
                    else:
                        result = await openrouter_complete(
                            messages,
                            settings=settings,
                            session_id=_provider_session_id(conversation.id),
                            force_task_tool=force_task_tool,
                            agent_contract=True,
                        )
                    if not isinstance(result, AgentCompletion):
                        raise RouteContractError("agent_provider_result_type_invalid")
                    call.state = "succeeded"
                    call.result = {
                        "response_id": result.response_id,
                        "kind": result.outcome.kind,
                        "result_sha256": _canonical_digest(result.outcome.model_dump(mode="json")),
                        "terminal_ciphertext": mimi_crypto.seal_content(
                            dek,
                            json.dumps(result.outcome.model_dump(mode="json"), ensure_ascii=False),
                            aad=mimi_crypto.provider_terminal_aad(run_id, turn),
                        ),
                    }
                    call.usage = result.usage
                    call.route = {
                        **call.route,
                        "actual_provider": result.provider,
                        "actual_model": result.model,
                    }
                    await _append_event(
                        db,
                        run_id,
                        "provider.succeeded",
                        {"attempt": turn, "provider": result.provider},
                    )
                    await db.commit()
                    return result

                async def execute_agent_read(
                    name: str, arguments: dict[str, Any]
                ) -> dict[str, Any]:
                    try:
                        read_factory = get_sessionmaker()
                        if read_factory is None:
                            raise RouteContractError("mimi_read_database_unavailable")
                        # A cancelled bounded read must not poison the ledger
                        # transaction used to record the run's terminal state.
                        async with read_factory() as read_db:
                            result = await execute_read_tool(read_db, name, arguments)
                    except ValueError as error:
                        raise RouteContractError(str(error)) from error
                    await _append_event(
                        db,
                        run_id,
                        "tool.read_result",
                        {
                            "tool": name,
                            "arguments_sha256": _canonical_digest(arguments),
                            "result_sha256": _canonical_digest(result),
                            "count": result.get("count", len(result.get("rows", []))),
                            "coverage": result.get("coverage", "unavailable"),
                            "has_next_cursor": bool(result.get("next_cursor")),
                        },
                    )
                    await db.commit()
                    return result

                async def persist_agent_stage(kind: str, details: dict[str, Any]) -> None:
                    await _append_event(db, run_id, f"agent.{kind}", details)
                    await db.commit()

                async def update_agent_context(
                    messages: list[dict[str, Any]],
                    tool_name: str,
                    call_id: str,
                    arguments: dict[str, Any],
                    result: dict[str, Any],
                    remaining_turns: int,
                    remaining_tool_calls: int,
                ) -> list[dict[str, Any]]:
                    nonlocal context_envelope, aggregate_read_seen
                    if context_envelope is None:
                        raise ValueError("mimi_context_envelope_missing")
                    if tool_name == "task.aggregate.v1":
                        # Counts do not carry per-Task versions. They can guide
                        # an answer or draft, but cannot safely ground a frozen
                        # write preview in this P1C-A contract.
                        aggregate_read_seen = True
                    bound_versions: dict[str, str] = {}
                    for row in result.get("rows", []):
                        if not isinstance(row, dict):
                            raise RouteContractError("task_read_row_invalid")
                        try:
                            task_id = UUID(str(row["id"]))
                            source_version = str(row["source_version"])
                            parsed_version = datetime.fromisoformat(source_version)
                        except (KeyError, TypeError, ValueError) as error:
                            raise RouteContractError("task_read_source_version_invalid") from error
                        if parsed_version.tzinfo is None:
                            raise RouteContractError("task_read_source_version_invalid")
                        source_key = f"task:{task_id}"
                        prior_version = bound_versions.get(source_key) or run.source_versions.get(
                            source_key
                        )
                        if prior_version is not None and prior_version != source_version:
                            raise RouteContractError("task_source_version_changed_during_run")
                        bound_versions[source_key] = source_version
                    if bound_versions:
                        run.source_versions = {**run.source_versions, **bound_versions}
                    context_envelope, rebound = rebind_after_read(
                        context_envelope,
                        messages,
                        tool_name=tool_name,
                        call_id=call_id,
                        arguments=arguments,
                        result=result,
                        remaining_turns=remaining_turns,
                        remaining_tool_calls=remaining_tool_calls,
                    )
                    await _append_event(
                        db, run_id, "context.manifest", _manifest_receipt(context_envelope)
                    )
                    await db.commit()
                    return rebound

                loop_result = await run_read_loop(
                    live_messages,
                    limits=LoopLimits(
                        max_turns=lease.max_turns,
                        max_tool_calls=lease.max_tool_calls,
                        max_serialized_bytes=(
                            settings.mimi_route_context_tokens
                            - settings.mimi_route_max_output_tokens
                        ),
                        deadline=deadline,
                    ),
                    invoke_model=invoke_agent_model,
                    execute_read=execute_agent_read,
                    on_stage=persist_agent_stage,
                    on_context_update=update_agent_context,
                )
                outcome = loop_result.outcome
                if isinstance(outcome, PreviewCandidate) and aggregate_read_seen:
                    outcome = Blocked(
                        reason=(
                            "Số liệu tổng hợp có thể đã đổi. Mimi chưa thể tạo preview "
                            "an toàn từ lượt đọc này; hãy yêu cầu kiểm tra lại dữ liệu cụ thể."
                        )
                    )
                agent_result_kind = outcome.kind
                agent_stop_code = loop_result.stop_code
                last = loop_result.completion
                common = {
                    "response_id": last.response_id if last else "",
                    "usage": last.usage if last else {},
                    "provider": last.provider if last else None,
                    "model": last.model if last else None,
                }
                if isinstance(outcome, PreviewCandidate):
                    if outcome.tool != CREATE_CANDIDATE_TOOL:
                        raise RouteContractError("preview_candidate_tool_invalid")
                    try:
                        candidate = TaskCreate.model_validate(outcome.arguments)
                    except ValidationError as error:
                        raise RouteContractError("preview_candidate_schema_invalid") from error
                    if candidate.is_private:
                        raise RouteContractError("standard_route_proposed_private_task")
                    completion = ProviderCompletion(
                        kind="task", task=candidate, text=None, **common
                    )
                else:
                    if isinstance(outcome, AssistantText):
                        text_result = outcome.text
                    elif isinstance(outcome, Clarification):
                        text_result = outcome.question
                    elif isinstance(outcome, Draft):
                        text_result = outcome.text
                    elif isinstance(outcome, Blocked):
                        text_result = outcome.reason
                    else:
                        raise RouteContractError("agent_loop_not_terminal")
                    completion = ProviderCompletion(
                        kind="text", task=None, text=text_result, **common
                    )
            elif provider_stream:
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
                            aad=mimi_crypto.event_content_aad(run_id, sequence, "assistant.delta"),
                        ),
                        "content_bytes": len(text_delta.encode("utf-8")),
                    }
                    await db.flush()

                async def persist_stream_event(kind: str, event_payload: dict[str, Any]) -> None:
                    if kind == "provider.response_identity":
                        response_id = event_payload.get("response_id")
                        if isinstance(response_id, str) and response_id:
                            call.result = {**(call.result or {}), "response_id": response_id}
                        await _append_event(db, run_id, kind, {"response_id_recorded": True})
                        await db.commit()
                    elif kind == "assistant.delta":
                        text_delta = str(event_payload.get("text", ""))
                        if not text_delta:
                            return
                        stream_buffer.append(text_delta)
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
            else:
                completion = await openrouter_complete(
                    live_messages,
                    settings=settings,
                    session_id=_provider_session_id(conversation.id),
                    force_task_tool=force_task_tool,
                )
            if force_task_tool and completion.kind != "task" and agent_stop_code is None:
                raise RouteContractError("provider_revision_must_return_task_tool")
            if (
                completion.kind == "task"
                and completion.task is not None
                and completion.task.id is not None
                and completion.task.id != task_id
            ):
                raise RouteContractError("provider_task_id_does_not_match_reservation")
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
                    .where(MimiProviderCall.run_id == run_id)
                    .order_by(MimiProviderCall.attempt.desc())
                    .limit(1)
                    .with_for_update()
                )
            ).scalar_one()
            call.state = "unknown" if outcome == "unknown" else "failed"
            retained_response_id = (call.result or {}).get("response_id")
            call.result = {
                "terminal": outcome,
                "status": status_code,
                "contract_error": contract_error,
                "response_id": (
                    error.response_id if isinstance(error, ProviderDispatchError) else None
                ),
            }
            if call.result["response_id"] is None and retained_response_id:
                call.result["response_id"] = retained_response_id
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
                    f"provider_contract_{_provider_contract_code(contract_error)}"
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
            await _append_event(
                db,
                run_id,
                "run.terminal",
                {"state": run.state, "error_code": run.error_code},
            )
            if conversation.generation == generation + 1:
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
                .where(MimiProviderCall.run_id == run_id)
                .order_by(MimiProviderCall.attempt.desc())
                .limit(1)
                .with_for_update()
            )
        ).scalar_one()
        provider_args: dict[str, Any] | None = None
        if completion.kind == "text":
            if completion.text is None:
                raise RouteContractError("provider_text_result_missing")
            if context_envelope is None:
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
            if context_envelope is None:
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
        if context_envelope is None:
            await _append_event(
                db,
                run_id,
                "provider.succeeded",
                {"attempt": call.attempt, "provider": completion.provider},
            )
        else:
            await _append_event(
                db,
                run_id,
                "agent.terminal",
                {"kind": agent_result_kind, "turns": call.attempt},
            )
        await db.flush()
        await db.commit()
        conversation = await _conversation(db, auth, conversation_id, lock=True)
        dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
        run = (
            await db.execute(select(MimiRun).where(MimiRun.id == run_id).with_for_update())
        ).scalar_one()
        # Every provider result, including plain text and clarification, is
        # accepted only on the generation that assembled its prompt. A newer
        # Owner turn must not receive a stale assistant answer or preview.
        expected_generation_after_accept = generation + 1
        if run.state != "running":
            return await conversation_view(db, auth, conversation_id)
        if conversation.generation != expected_generation_after_accept:
            run.state = "halted"
            run.error_code = "response_frontier_changed"
            run.completed_at = datetime.now(UTC)
            await _append_event(db, run_id, "response.frontier_changed", {})
            await _append_event(
                db,
                run_id,
                "run.terminal",
                {"state": "halted", "error_code": run.error_code},
            )
            await db.flush()
            return await conversation_view(db, auth, conversation_id)
        if completion.kind == "text":
            assert completion.text is not None
            if provider_stream and context_envelope is None:
                await flush_stream_buffer()
            _add_assistant_message(db, conversation, run_id, dek, completion.text)
            if agent_result_kind == "draft":
                draft_id = uuid7()
                await _append_event(
                    db,
                    run_id,
                    "draft.ready",
                    {
                        "draft_id": str(draft_id),
                        "revision": 1,
                        "content_sha256": hashlib.sha256(
                            completion.text.encode("utf-8")
                        ).hexdigest(),
                        "message_sequence": conversation.next_message_sequence - 1,
                        "state": "pending",
                    },
                )
            if agent_result_kind == "blocked":
                run.state = (
                    agent_stop_code
                    if agent_stop_code in {"deadline_exceeded", "budget_exceeded"}
                    else "halted"
                )
                run.error_code = agent_stop_code or "provider_blocked"
            else:
                run.state = "completed"
            run.completed_at = datetime.now(UTC)
            await _append_event(
                db,
                run_id,
                "run.terminal",
                {"state": run.state, "result": agent_result_kind or "text"},
            )
            await db.flush()
            return await conversation_view(db, auth, conversation_id)
        assert provider_args is not None
        operation_args = provider_args
    else:
        run.state = "running"
        call.state = "succeeded"
        awaiting_task_title = bool(
            provider_history
            and provider_history[-1].get("role") == "assistant"
            and provider_history[-1].get("content") == "Bạn muốn đặt tiêu đề Task là gì?"
        )
        local_kind, local_result = _deterministic_turn(
            payload.content,
            task_id,
            awaiting_task_title=awaiting_task_title,
        )
        if force_task_tool and local_kind != "task":
            # Explicit revisions are already bound to a pending preview. Keep
            # the old authority intact unless a complete replacement exists.
            local_kind = "text"
            local_result = "Hãy nêu tiêu đề Task mới để mình thay preview đang chờ."
        if local_kind == "text":
            assert isinstance(local_result, str)
            call.result = {
                "kind": "text",
                "result_sha256": hashlib.sha256(local_result.encode("utf-8")).hexdigest(),
            }
        else:
            assert isinstance(local_result, dict)
            operation_args = local_result
            call.result = {
                "kind": "task_preview",
                "tool": TOOL_VERSION,
                "result_sha256": _canonical_digest(operation_args),
            }
        call.usage = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost": 0}
        run.provider_outcome = "succeeded"
        await _append_event(db, run_id, "provider.succeeded", {"attempt": 1})
        if local_kind == "text":
            assert isinstance(local_result, str)
            _add_assistant_message(db, conversation, run_id, dek, local_result)
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

    # Only a validated task proposal may replace pending authority. Re-query
    # after provider I/O because the conversation lock was released while the
    # external request ran.
    expected_generation_after_accept = generation + 1
    if conversation.generation != expected_generation_after_accept:
        run.state = "halted"
        run.error_code = "preview_frontier_changed"
        run.completed_at = datetime.now(UTC)
        await _append_event(db, run_id, "change_set.frontier_changed", {})
        await _append_event(
            db,
            run_id,
            "run.terminal",
            {"state": "halted", "error_code": run.error_code},
        )
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
            await _append_event(
                db,
                run_id,
                "run.terminal",
                {"state": "halted", "error_code": run.error_code},
            )
            _add_assistant_message(
                db,
                conversation,
                run_id,
                dek,
                "Preview nền đã thay đổi; Mimi không thay thế quyết định mới hơn của bạn.",
            )
            await db.flush()
            return await conversation_view(db, auth, conversation_id)

    if current_pending_preview is not None and not force_task_tool:
        run.state = "halted"
        run.error_code = "pending_preview_requires_decision"
        run.completed_at = datetime.now(UTC)
        await _append_event(
            db,
            run_id,
            "run.terminal",
            {"state": "halted", "error_code": run.error_code},
        )
        _add_assistant_message(
            db,
            conversation,
            run_id,
            dek,
            "Bạn đang có một preview chờ quyết định. Hãy xác nhận, từ chối hoặc sửa preview đó "
            "trước khi tạo preview mới.",
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
        policy_version=(
            context_envelope.manifest.policy_id if context_envelope is not None else POLICY_VERSION
        ),
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

    # Serialize the global idempotency namespace before checking either the
    # key or change-set row. Concurrent decisions on different change sets can
    # no longer escape as a database uniqueness error.
    await db.execute(
        select(func.pg_advisory_xact_lock(_transaction_lock_key("mimi-confirm", idempotency_key)))
    )

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

    async def invalidate_frozen_change_set(detail: str) -> None:
        change_set.state = "stale"
        run.state = "halted"
        run.error_code = detail
        run.completed_at = datetime.now(UTC)
        await _append_event(db, run.id, "change_set.invalid", {"reason": detail})
        await _append_event(
            db,
            run.id,
            "run.terminal",
            {"state": "halted", "error_code": detail},
        )
        await db.flush()
        await db.commit()
        raise _conflict(detail)

    existing_for_change_set = (
        await db.execute(
            select(MimiExecutionReceipt).where(MimiExecutionReceipt.change_set_id == change_set.id)
        )
    ).scalar_one_or_none()
    if existing_for_change_set is not None:
        raise _conflict("change_set_already_executed_with_different_idempotency_key")
    if payload.digest != change_set.digest_sha256 or payload.nonce != change_set.nonce:
        raise _conflict("change_set_binding_mismatch")
    if change_set.state == "rejected" and payload.decision == "reject":
        return {"change_set_id": change_set.id, "state": "rejected"}
    if change_set.state != "pending":
        raise _conflict(f"change_set_{change_set.state}")
    now = datetime.now(UTC)
    if change_set.expires_at <= now:
        change_set.state = "expired"
        run.state = "deadline_exceeded"
        run.completed_at = now
        await _append_event(db, run.id, "change_set.expired", {})
        await _append_event(
            db,
            run.id,
            "run.terminal",
            {"state": "deadline_exceeded", "error_code": "change_set_expired"},
        )
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
        await _append_event(
            db,
            run.id,
            "run.terminal",
            {"state": "cancelled", "result": "change_set_rejected"},
        )
        await db.flush()
        return {"change_set_id": change_set.id, "state": "rejected"}

    # A preview is bound to the versioned Task evidence the model saw. Hold
    # read locks through the domain write so a concurrent edit cannot pass the
    # check and then change the source before this confirmation commits.
    if run.source_versions:
        try:
            expected_sources = {
                UUID(key.removeprefix("task:")): value
                for key, value in run.source_versions.items()
                if isinstance(key, str) and key.startswith("task:") and isinstance(value, str)
            }
        except ValueError:
            await invalidate_frozen_change_set("change_set_source_binding_invalid")
            raise AssertionError("unreachable")
        if len(expected_sources) != len(run.source_versions):
            await invalidate_frozen_change_set("change_set_source_binding_invalid")
            raise AssertionError("unreachable")
        source_rows = (
            (
                await db.execute(
                    select(Task).where(Task.id.in_(expected_sources)).with_for_update(read=True)
                )
            )
            .scalars()
            .all()
        )
        if len(source_rows) != len(expected_sources) or any(
            row.is_private
            or row.deleted_at is not None
            or row.updated_at is None
            or row.updated_at.isoformat() != expected_sources[row.id]
            for row in source_rows
        ):
            await invalidate_frozen_change_set("change_set_source_stale")
            raise AssertionError("unreachable")

    run.state = "executing"
    dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
    try:
        raw_operation = json.loads(
            mimi_crypto.open_content(
                dek,
                change_set.operation_ciphertext,
                aad=mimi_crypto.change_set_aad(conversation.id, change_set.id),
            )
        )
        operation = ChangeOperation.model_validate(raw_operation)
    except ValueError, json.JSONDecodeError, ValidationError:
        await invalidate_frozen_change_set("change_set_ciphertext_invalid")
        raise AssertionError("unreachable")
    if operation.tool != TOOL_VERSION:
        await invalidate_frozen_change_set("unsupported_or_stale_tool_version")
        raise AssertionError("unreachable")
    frozen = FrozenChangeSet(
        change_set_id=change_set.id,
        run_id=run.id,
        operations=(operation,),
        expires_at=change_set.expires_at,
        nonce=change_set.nonce,
        digest_sha256=change_set.digest_sha256,
        idempotency_key=f"preview:{change_set.id}",
    )
    if frozen.calculated_digest() != change_set.digest_sha256:
        await invalidate_frozen_change_set("change_set_digest_invalid")
        raise AssertionError("unreachable")
    try:
        task_payload = TaskCreate.model_validate(operation.args)
    except ValidationError:
        await invalidate_frozen_change_set("change_set_task_payload_invalid")
        raise AssertionError("unreachable")
    if task_payload.is_private:
        await invalidate_frozen_change_set("standard_change_set_cannot_create_private_task")
        raise AssertionError("unreachable")
    task = await TaskStore().create(db, auth, task_payload)
    receipt = MimiExecutionReceipt(
        id=uuid7(),
        change_set_id=change_set.id,
        operation_id=operation.operation_id,
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
    await _append_event(
        db,
        run.id,
        "run.terminal",
        {"state": "completed", "result": "change_set_executed"},
    )
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
    current_draft, _ = await _latest_draft_state(db, conversation.id)
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
    provider_calls = []
    if run_ids:
        provider_calls = (
            (
                await db.execute(
                    select(MimiProviderCall)
                    .where(MimiProviderCall.run_id.in_(run_ids))
                    .order_by(MimiProviderCall.created_at, MimiProviderCall.attempt)
                    .limit(MAX_EVENTS)
                )
            )
            .scalars()
            .all()
        )
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
        "draft": current_draft.model_dump(mode="json") if current_draft else None,
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
        "provider_calls": [
            {
                "run_id": row.run_id,
                "attempt": row.attempt,
                "state": row.state,
                "requested_model": row.route.get("model"),
                "requested_effort": row.route.get("reasoning_effort"),
                "actual_model": row.route.get("actual_model"),
                "actual_provider": row.route.get("actual_provider"),
                "usage": _reported_usage(row.usage),
            }
            for row in provider_calls
        ],
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
        aad=mimi_crypto.message_aad(conversation.id, source_message.sequence, source_message.role),
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
    if call is not None and call.state == "succeeded":
        # A local materialization failure after the durable provider terminal
        # must not rewrite a known provider success into a provider failure.
        run.provider_outcome = "succeeded"
    elif provider_may_have_received_request:
        run.provider_outcome = "unknown"
        call.state = "unknown"
        call.result = {
            "terminal": "unknown",
            "reason": run.error_code,
            "response_id": (call.result or {}).get("response_id"),
        }
    elif call is not None:
        call.state = "failed"
        call.result = {"terminal": "failed", "reason": run.error_code}
    await _append_event(
        db,
        run.id,
        "run.cancelled" if cancelled else "run.halted",
        {"provider_outcome": run.provider_outcome},
    )
    await _append_event(
        db,
        run.id,
        "run.terminal",
        {"state": run.state, "error_code": run.error_code},
    )
    await db.flush()


async def reconcile_orphaned_mimi_runs(db: AsyncSession) -> int:
    """Classify guarded runs abandoned by a crashed process, never redispatch them.

    A live old Fly Machine holds the transaction advisory lock and is left
    untouched. Runs from before this guard protocol are also left untouched:
    they may still be active during an immediate rolling deploy.
    """

    engine = get_engine()
    if engine is None:
        return 0
    recovered = 0
    last_id: UUID | None = None
    while True:
        query = select(MimiRun.id).where(
            MimiRun.state.in_(("accepted", "running")),
            MimiRun.completed_at.is_(None),
        )
        if last_id is not None:
            query = query.where(MimiRun.id > last_id)
        ids = (await db.execute(query.order_by(MimiRun.id).limit(100))).scalars().all()
        if not ids:
            break
        for candidate_id in ids:
            async with engine.connect() as guard:
                async with guard.begin():
                    acquired = (
                        await guard.execute(
                            text("SELECT pg_try_advisory_xact_lock(:key)"),
                            {"key": run_guard_key(candidate_id)},
                        )
                    ).scalar_one()
                    if not acquired:
                        continue
                    run = (
                        await db.execute(
                            select(MimiRun).where(MimiRun.id == candidate_id).with_for_update()
                        )
                    ).scalar_one_or_none()
                    if run is None or run.state not in {"accepted", "running"}:
                        continue
                    call = (
                        await db.execute(
                            select(MimiProviderCall)
                            .where(MimiProviderCall.run_id == candidate_id)
                            .order_by(MimiProviderCall.attempt.desc())
                            .limit(1)
                            .with_for_update()
                        )
                    ).scalar_one_or_none()
                    if call is None or call.route.get("run_guard_version") != 1:
                        continue
                    if call.state == "intent":
                        call.state = "fenced"
                        run.state = "retryable"
                        run.provider_outcome = "failed"
                        run.error_code = "process_lost_before_dispatch"
                        call.result = {"terminal": "not_dispatched", "reason": run.error_code}
                    elif call.state in {"dispatched", "unknown"}:
                        response_id = (call.result or {}).get("response_id")
                        call.state = "unknown"
                        run.state = "outcome_unknown"
                        run.provider_outcome = "unknown"
                        run.error_code = "process_lost_after_dispatch"
                        call.result = {
                            "terminal": "unknown",
                            "reason": run.error_code,
                            "response_id": response_id,
                        }
                    else:
                        run.state = "halted"
                        run.provider_outcome = (
                            "succeeded" if call.state == "succeeded" else "failed"
                        )
                        # A successful provider turn is not yet an authorized
                        # preview or delivered answer. Preserve its encrypted
                        # terminal payload for diagnosis, but do not guess a
                        # missing loop continuation or replay an external call.
                        run.error_code = (
                            "provider_result_not_delivered_after_restart"
                            if call.state == "succeeded"
                            else "process_lost_after_provider_result"
                        )
                        if call.state == "succeeded":
                            conversation = (
                                await db.execute(
                                    select(MimiConversation)
                                    .where(MimiConversation.id == run.conversation_id)
                                    .with_for_update()
                                )
                            ).scalar_one()
                            if conversation.generation == run.generation + 1:
                                dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
                                _add_assistant_message(
                                    db,
                                    conversation,
                                    run.id,
                                    dek,
                                    "Mimi đã nhận phản hồi từ model nhưng server bị ngắt trước khi "
                                    "hoàn tất câu trả lời hoặc preview. Chưa có thay đổi nào được "
                                    "ghi vào microSched. Bạn có thể gửi lại yêu cầu; Mimi sẽ "
                                    "không tự gọi model lần nữa.",
                                )
                    run.completed_at = datetime.now(UTC)
                    await _append_event(
                        db,
                        run.id,
                        "run.recovered_after_process_loss",
                        {"state": run.state, "provider_outcome": run.provider_outcome},
                    )
                    await _append_event(
                        db,
                        run.id,
                        "run.terminal",
                        {"state": run.state, "error_code": run.error_code},
                    )
                    await db.commit()
                    recovered += 1
        last_id = ids[-1]
    return recovered


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
