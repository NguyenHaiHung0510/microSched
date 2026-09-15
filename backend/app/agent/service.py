"""Bounded Mimi P1 orchestration over the existing Task transaction seam."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid7

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import false, select, text
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
from app.core.settings import get_settings
from app.domain.models import AuditLog, AuthSession, Task
from app.domain.tasks import TaskCreate, TaskStore
from app.web.deps import CRON_TIMER_RELOAD_INFO_KEY

POLICY_VERSION = "mimi-standard-task-create.v1"
TOOL_VERSION = "task.create.v1"
MAX_MESSAGES = 100
MAX_EVENTS = 100


class MessageCreate(BaseModel):
    client_id: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=12_000)
    expected_generation: int | None = Field(default=None, ge=1)

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


def _owner_id(auth: AuthSession) -> UUID:
    """Derive a stable opaque owner UUID without persisting the login address."""
    secret = (get_settings().oauth_state_secret or get_settings().app_name).encode("utf-8")
    digest = hmac.new(secret, auth.user_email.strip().lower().encode("utf-8"), hashlib.sha256)
    return UUID(bytes=digest.digest()[:16], version=5)


def _canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mimi resource not found")


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _task_title(content: str) -> str:
    """Build a bounded deterministic preview title for the local route."""
    title = " ".join(content.strip().split())
    lowered = title.lower()
    for prefix in ("tạo task ", "tạo việc ", "create task "):
        if lowered.startswith(prefix):
            title = title[len(prefix) :].strip()
            break
    return (title or "Task từ Mimi")[:200]


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


async def create_conversation(db: AsyncSession, auth: AuthSession) -> dict[str, Any]:
    row = MimiConversation(
        owner_id=_owner_id(auth),
        sensitivity=Sensitivity.STANDARD.value,
        dek_wrapped=mimi_crypto.create_wrapped_dek(),
    )
    db.add(row)
    await db.flush()
    return {"id": row.id, "sensitivity": row.sensitivity, "generation": row.generation}


async def current_conversation(db: AsyncSession, auth: AuthSession) -> dict[str, Any] | None:
    conversation_id = (
        await db.execute(
            select(MimiConversation.id)
            .where(MimiConversation.owner_id == _owner_id(auth))
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
) -> dict[str, Any]:
    conversation = await _conversation(db, auth, conversation_id, lock=True)
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

    # This P1 route cannot prove a supplement is harmless, so every distinct
    # new user turn conservatively revises the frontier and invalidates an old
    # preview. It never leaves two confirmable mutations behind the UI.
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
    for old_change_set, old_run in pending_previews:
        old_change_set.state = "stale"
        old_run.state = "halted"
        old_run.error_code = "superseded_by_new_turn"
        old_run.completed_at = datetime.now(UTC)
        db.add(
            MimiEvent(
                run_id=old_run.id,
                sequence=5,
                kind="change_set.superseded",
                payload={"change_set_id": str(old_change_set.id)},
            )
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
    run_id = uuid7()
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
    db.add(MimiEvent(run_id=run_id, sequence=1, kind="run.accepted", payload={}))
    db.add(
        MimiEvent(
            run_id=run_id,
            sequence=2,
            kind="context.tasks_read",
            payload={"count": len(task_context), "private_allowed": False},
        )
    )

    dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
    user_sequence = conversation.next_message_sequence
    user_bytes = payload.content.encode("utf-8")
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
                "Bạn là Mimi. Chỉ đề xuất một task.create.v1 STANDARD; không thực thi. "
                f"Server-reserved task id: {task_id}. Current STANDARD Task context: "
                + json.dumps(task_context, ensure_ascii=False, default=str)
            ),
        },
        {"role": "user", "content": payload.content},
    ]
    route_kind = (
        "openrouter-exact-v1" if settings.mimi_live_provider_enabled else "deterministic-local-v1"
    )
    request_body = {
        "route": route_kind,
        "message_sha256": hashlib.sha256(user_bytes).hexdigest(),
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
                "model": settings.mimi_route_model,
                "provider": settings.mimi_route_provider,
                "quantization": settings.mimi_route_quantization,
                "reasoning_effort": settings.mimi_route_reasoning_effort,
            }
            if settings.mimi_live_provider_enabled
            else {"kind": "deterministic", "environment": "local"}
        ),
    )
    db.add(call)
    await db.flush()

    if settings.mimi_live_provider_enabled:
        # The external dispatch is separated by two durable boundaries: intent
        # commits before network I/O; terminal result commits before a canonical
        # change set is materialized. Unknown outcomes never auto-retry.
        run.state = "running"
        await db.commit()
        try:
            completion = await openrouter_complete(live_messages, settings=settings)
        except (ProviderDispatchError, RouteContractError) as error:
            outcome = error.outcome if isinstance(error, ProviderDispatchError) else "failed"
            status_code = error.status if isinstance(error, ProviderDispatchError) else None
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
            call.result = {"terminal": outcome, "status": status_code}
            run.provider_outcome = "unknown" if outcome == "unknown" else "failed"
            run.state = {
                "unknown": "outcome_unknown",
                "retryable": "retryable",
                "failed": "halted",
            }[outcome]
            run.error_code = f"provider_{outcome}"
            db.add(
                MimiEvent(
                    run_id=run_id,
                    sequence=3,
                    kind=f"provider.{outcome}",
                    payload={"status": status_code},
                )
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
        provider_args = completion.task.model_dump(mode="json")
        provider_args["id"] = str(task_id)
        provider_args["is_private"] = False
        call.state = "succeeded"
        call.result = {
            "response_id": completion.response_id,
            "result_sha256": _canonical_digest(provider_args),
            "tool": TOOL_VERSION,
        }
        call.usage = completion.usage
        run.provider_outcome = "succeeded"
        db.add(
            MimiEvent(
                run_id=run_id,
                sequence=3,
                kind="provider.succeeded",
                payload={"attempt": 1, "provider": completion.provider},
            )
        )
        await db.flush()
        await db.commit()
        conversation = await _conversation(db, auth, conversation_id, lock=True)
        dek = mimi_crypto.unwrap_dek(conversation.dek_wrapped)
        run = (
            await db.execute(select(MimiRun).where(MimiRun.id == run_id).with_for_update())
        ).scalar_one()
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
        db.add(
            MimiEvent(
                run_id=run_id,
                sequence=3,
                kind="provider.succeeded",
                payload={"attempt": 1},
            )
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
    db.add(
        MimiEvent(
            run_id=run_id,
            sequence=4,
            kind="change_set.ready",
            payload={"change_set_id": str(change_set_id), "digest": digest},
        )
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
        db.add(MimiEvent(run_id=run.id, sequence=5, kind="change_set.expired", payload={}))
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
        db.add(MimiEvent(run_id=run.id, sequence=5, kind="change_set.rejected", payload={}))
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
    db.add(
        MimiEvent(
            run_id=run.id,
            sequence=5,
            kind="change_set.executed",
            payload={"receipt_id": str(receipt.id), "task_id": str(task.id)},
        )
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
        "generation": conversation.generation,
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
        "events": [
            {
                "id": row.id,
                "run_id": row.run_id,
                "sequence": row.sequence,
                "kind": row.kind,
                "payload": row.payload,
                "created_at": row.created_at,
            }
            for row in events
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
