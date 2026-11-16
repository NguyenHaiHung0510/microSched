"""Exact durable execution projections shared by Chat, Voice and UI."""

import json
from uuid import UUID

from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from sqlalchemy import select

from app.agent import crypto
from app.agent.contracts import ChangeOperation, FrozenChangeSet
from app.agent.models import (
    MimiChangeSet,
    MimiConversation,
    MimiEvent,
    MimiExecutionReceipt,
    MimiRun,
)
from app.agent.task_collection import (
    COLLECTION_TOOL,
    TASK_FIELDS,
    ChildCommand,
    PreparedCollection,
    PreparedEntry,
    TaskCommand,
    digest,
    freeze_undo,
    locked_state,
    snapshot,
)
from app.domain.models import Task
from app.domain.tasks import TaskCreate


async def bound_receipt(db, auth, receipt_id, *, lock=False):
    from app.agent.service import _conversation_scope

    statement = (
        select(MimiExecutionReceipt, MimiChangeSet, MimiRun, MimiConversation)
        .join(MimiChangeSet, MimiExecutionReceipt.change_set_id == MimiChangeSet.id)
        .join(MimiRun, MimiChangeSet.run_id == MimiRun.id)
        .join(MimiConversation, MimiRun.conversation_id == MimiConversation.id)
        .where(MimiExecutionReceipt.id == receipt_id, _conversation_scope(auth))
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    else:
        statement = statement.with_for_update(read=True, of=MimiConversation)
    found = (await db.execute(statement)).first()
    if found is None:
        raise HTTPException(404, "mimi_receipt_unavailable")
    receipt, change, run, conversation = found
    events = (
        await db.scalars(
            select(MimiEvent)
            .where(
                MimiEvent.run_id == run.id,
                MimiEvent.kind == "change_set.executed",
                MimiEvent.payload["receipt_id"].astext == str(receipt.id),
            )
            .limit(2)
        )
    ).all()
    if (
        change.state != "executed"
        or run.state != "completed"
        or receipt.digest_sha256 != change.digest_sha256
        or len(events) != 1
    ):
        raise HTTPException(409, "receipt_commit_binding_invalid")
    return receipt, change, run, conversation


async def capture_single_create(db, task_id, payload):
    """Capture the real post-commit candidate using the existing single-create path."""
    state = await locked_state(db, [task_id])
    after = snapshot(*state[task_id])
    command = TaskCommand(
        action="create",
        fields=payload.model_dump(mode="json", include=TASK_FIELDS),
        children=tuple(
            ChildCommand(action="append", fields={"content": text}) for text in payload.items
        ),
    )
    plan = PreparedCollection(
        selection_id=None,
        entries=(
            PreparedEntry(
                id=task_id,
                command=command,
                before=None,
                after={key: after[key] for key in ("fields", "children", "deleted_at")},
                reminder_effect={"action": "none", "before": None},
            ),
        ),
    )
    return {
        "schema_version": "mimi.task-collection-recovery.v1",
        "before": [None],
        "after": [after],
        "plan": plan.model_dump(mode="json"),
    }


def recovery_for(receipt, change, conversation, dek):
    if receipt.result_ciphertext is None:
        raise HTTPException(409, "receipt_has_no_durable_inverse")
    try:
        operation = ChangeOperation.model_validate(
            json.loads(
                crypto.open_content(
                    dek,
                    change.operation_ciphertext,
                    aad=crypto.change_set_aad(conversation.id, change.id),
                )
            )
        )
        frozen = FrozenChangeSet(
            change_set_id=change.id,
            run_id=change.run_id,
            operations=(operation,),
            expires_at=change.expires_at,
            nonce=change.nonce,
            digest_sha256=change.digest_sha256,
            idempotency_key=f"preview:{change.id}",
        )
        recovery = json.loads(
            crypto.open_content(
                dek,
                receipt.result_ciphertext,
                aad=f"mimi-receipt:{conversation.id}:{receipt.id}:recovery",
            )
        )
        plan = PreparedCollection.model_validate(recovery["plan"])
        if (
            operation.operation_id != receipt.operation_id
            or frozen.calculated_digest() != change.digest_sha256
            or recovery["schema_version"] != "mimi.task-collection-recovery.v1"
            or len(plan.entries) != len(recovery["before"])
            or len(plan.entries) != len(recovery["after"])
        ):
            raise ValueError("receipt_recovery_binding_invalid")
        if operation.tool == COLLECTION_TOOL:
            if digest(operation.args) != digest(plan.model_dump(mode="json")):
                raise ValueError("receipt_recovery_binding_invalid")
        elif operation.tool == "task.create.v1":
            payload = TaskCreate.model_validate(operation.args)
            if (
                len(plan.entries) != 1
                or plan.entries[0].id != receipt.task_id
                or payload.id != receipt.task_id
                or payload.is_private
                or plan.entries[0].before is not None
                or plan.entries[0].command.action != "create"
                or plan.entries[0].command.fields
                != payload.model_dump(mode="json", include=TASK_FIELDS)
            ):
                raise ValueError("receipt_recovery_binding_invalid")
        else:
            raise ValueError("receipt_recovery_binding_invalid")
        for entry, before, after in zip(
            plan.entries, recovery["before"], recovery["after"], strict=True
        ):
            if (
                digest(entry.before) != digest(before)
                or after["id"] != str(entry.id)
                or digest(entry.after["fields"]) != digest(after["fields"])
                or entry.after["deleted_at"] != after["deleted_at"]
            ):
                raise ValueError("receipt_recovery_binding_invalid")
        return recovery
    except InvalidTag, ValueError, TypeError, KeyError, UnicodeError:
        raise HTTPException(409, "receipt_recovery_binding_invalid") from None


async def latest_receipt(db, conversation_id):
    # Never skip a newer stale/legacy/inverse receipt to find an older eligible one.
    return await db.scalar(
        select(MimiExecutionReceipt.id)
        .join(MimiChangeSet, MimiExecutionReceipt.change_set_id == MimiChangeSet.id)
        .join(MimiRun, MimiChangeSet.run_id == MimiRun.id)
        .where(MimiRun.conversation_id == conversation_id)
        .order_by(MimiExecutionReceipt.executed_at.desc(), MimiExecutionReceipt.id.desc())
        .limit(1)
    )


async def message_receipts(db, conversation, messages, provenance, dek):
    targets = {}
    for message in messages:
        source = provenance.get(message.id) or {}
        if (
            message.role == "assistant"
            and message.run_id is not None
            and source.get("source") == "server_verified"
            and source.get("producer_code") in {"operation_committed", "collection_committed"}
        ):
            targets.setdefault(message.run_id, []).append(message)
    if not targets:
        return {}
    # Query by message run, independently of the truncated latest-runs window.
    rows = (
        await db.execute(
            select(MimiExecutionReceipt, MimiChangeSet, MimiRun)
            .join(MimiChangeSet, MimiExecutionReceipt.change_set_id == MimiChangeSet.id)
            .join(MimiRun, MimiChangeSet.run_id == MimiRun.id)
            .where(MimiRun.conversation_id == conversation.id, MimiRun.id.in_(targets))
        )
    ).all()
    events = {}
    for event in await db.scalars(
        select(MimiEvent).where(
            MimiEvent.run_id.in_(targets),
            MimiEvent.kind == "change_set.executed",
        )
    ):
        events.setdefault(event.run_id, []).append(event.payload)
    result = {}
    for receipt, change, run in rows:
        if (
            run.state != "completed"
            or change.state != "executed"
            or receipt.digest_sha256 != change.digest_sha256
        ):
            continue
        try:
            operation = ChangeOperation.model_validate(
                json.loads(
                    crypto.open_content(
                        dek,
                        change.operation_ciphertext,
                        aad=crypto.change_set_aad(conversation.id, change.id),
                    )
                )
            )
            frozen = FrozenChangeSet(
                change_set_id=change.id,
                run_id=run.id,
                operations=(operation,),
                expires_at=change.expires_at,
                nonce=change.nonce,
                digest_sha256=change.digest_sha256,
                idempotency_key=f"preview:{change.id}",
            )
        except InvalidTag, ValueError, KeyError, TypeError:
            continue
        expected = {
            COLLECTION_TOOL: "collection_committed",
            "task.create.v1": "operation_committed",
        }.get(operation.tool)
        matches = [e for e in events.get(run.id, []) if e.get("receipt_id") == str(receipt.id)]
        if (
            operation.operation_id != receipt.operation_id
            or frozen.calculated_digest() != change.digest_sha256
            or expected is None
            or len(matches) != 1
        ):
            continue
        marker_id = matches[0].get("message_id")
        messages_for_receipt = [
            message
            for message in targets[run.id]
            if provenance[message.id]["producer_code"] == expected
            and (marker_id is None or str(message.id) == marker_id)
        ]
        if len(messages_for_receipt) == 1:
            result[messages_for_receipt[0].id] = str(receipt.id)
    return result


async def receipt_diff(db, auth, receipt_id):
    from app.core.settings import get_settings

    receipt, change, _, conversation = await bound_receipt(db, auth, receipt_id)
    # Only scalar current eligibility is loaded before decrypting history.
    if receipt.result_ciphertext is None:
        raise HTTPException(409, "receipt_has_no_durable_inverse")
    ids = receipt.result.get("task_ids") or [str(receipt.task_id)]
    try:
        target_ids = [UUID(value) for value in ids]
    except ValueError, TypeError:
        raise HTTPException(409, "receipt_targets_invalid") from None
    eligible = set(
        await db.scalars(
            select(Task.id)
            .where(
                Task.id.in_(target_ids),
                Task.is_private.is_(False),
                Task.deleted_at.is_(None),
            )
            .order_by(Task.id)
            .with_for_update()
        )
    )
    if eligible != set(target_ids):
        raise HTTPException(410, "receipt_sources_unavailable")
    dek = crypto.unwrap_dek(conversation.dek_wrapped)
    recovery = recovery_for(receipt, change, conversation, dek)
    original = PreparedCollection.model_validate(recovery["plan"])
    if [str(e.id) for e in original.entries] != ids:
        raise HTTPException(409, "receipt_targets_invalid")
    # The public plan shows actual committed before/after, including generated
    # checklist identities. It is never a reconstructed inverse or latest preview.
    actual = original.model_dump(mode="json")
    for entry, before, after in zip(
        actual["entries"], recovery["before"], recovery["after"], strict=True
    ):
        entry["before"] = before
        entry["after"] = {key: after[key] for key in ("fields", "children", "deleted_at")}
    available = get_settings().mimi_collection_enabled
    if available:
        try:
            await freeze_undo(db, receipt.id, recovery)
        except HTTPException:
            available = False
    return {
        "receipt_id": str(receipt.id),
        "plan": actual,
        "undo_available": available,
        "executed_at": receipt.executed_at.isoformat(),
    }
