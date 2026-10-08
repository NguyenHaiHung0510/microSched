"""Encrypted server-derived feedback evidence in the existing MimiEvidence table."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

from fastapi import HTTPException
from sqlalchemy import select

from app.agent import crypto
from app.agent.models import (
    MimiChangeSet,
    MimiEvent,
    MimiEvidence,
    MimiExecutionReceipt,
    MimiMessage,
    MimiProviderCall,
    MimiRun,
)
from app.agent.task_collection import canonical, digest

MAX_BYTES = 1_048_576


async def causal_run_id(db, conversation_id, target_type, target_id):
    try:
        tid = UUID(target_id)
    except ValueError:
        raise HTTPException(404, "Feedback target not found") from None
    if target_type == "run":
        rid = tid
    elif target_type == "turn":
        row = await db.get(MimiMessage, tid)
        rid = row.run_id if row else None
    elif target_type == "call":
        row = await db.get(MimiProviderCall, tid)
        rid = row.run_id if row else None
    elif target_type == "receipt":
        row = await db.get(MimiExecutionReceipt, tid)
        change = await db.get(MimiChangeSet, row.change_set_id) if row else None
        rid = change.run_id if change else None
    elif target_type == "operation":
        row = (
            await db.scalars(
                select(MimiExecutionReceipt).where(MimiExecutionReceipt.operation_id == tid)
            )
        ).one_or_none()
        if row:
            rid = (await db.get(MimiChangeSet, row.change_set_id)).run_id
        else:
            # Pending encrypted operations must be resolved by owner-scoped service,
            # never searched as arbitrary plaintext metadata.
            changes = (
                await db.scalars(
                    select(MimiChangeSet)
                    .join(MimiRun)
                    .where(MimiRun.conversation_id == conversation_id)
                    .limit(100)
                )
            ).all()
            return None, changes
    else:
        raise HTTPException(404, "Feedback target not found")
    run = await db.get(MimiRun, rid) if rid else None
    if run is None or run.conversation_id != conversation_id:
        raise HTTPException(404, "Feedback target not found")
    return run.id, []


async def target_run(db, conversation, target_type, target_id, dek):
    rid, pending = await causal_run_id(db, conversation.id, target_type, target_id)
    if rid is not None:
        return rid
    for change in pending:
        operation = json.loads(
            crypto.open_content(
                dek,
                change.operation_ciphertext,
                aad=crypto.change_set_aad(conversation.id, change.id),
            )
        )
        if operation.get("operation_id") == target_id:
            return change.run_id
    raise HTTPException(404, "Feedback target not found")


async def capture_feedback(db, conversation, target_type, target_id, provided_ids):
    dek = crypto.unwrap_dek(conversation.dek_wrapped)
    rid = await target_run(db, conversation, target_type, target_id, dek)
    for bid in provided_ids:
        existing = await db.get(MimiEvidence, bid)
        if (
            existing is None
            or existing.conversation_id != conversation.id
            or existing.run_id != rid
            or existing.metadata_json.get("target_type") != target_type
            or existing.metadata_json.get("target_id") != target_id
            or existing.expires_at <= datetime.now(UTC)
        ):
            raise HTTPException(409, "feedback_evidence_causal_binding_invalid")
    messages = (
        await db.scalars(
            select(MimiMessage)
            .where(MimiMessage.run_id == rid)
            .order_by(MimiMessage.sequence)
            .limit(1001)
        )
    ).all()
    calls = (
        await db.scalars(
            select(MimiProviderCall)
            .where(MimiProviderCall.run_id == rid)
            .order_by(MimiProviderCall.attempt)
            .limit(129)
        )
    ).all()
    events = (
        await db.scalars(
            select(MimiEvent)
            .where(MimiEvent.run_id == rid)
            .order_by(MimiEvent.sequence)
            .limit(1001)
        )
    ).all()
    changes = (await db.scalars(select(MimiChangeSet).where(MimiChangeSet.run_id == rid))).all()
    receipts = (
        await db.scalars(
            select(MimiExecutionReceipt).where(
                MimiExecutionReceipt.change_set_id.in_([c.id for c in changes])
            )
        )
    ).all()
    run = await db.get(MimiRun, rid)
    incomplete = len(messages) > 1000 or len(calls) > 128 or len(events) > 1000
    parts = {
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "sequence": m.sequence,
                "content": crypto.open_content(
                    dek,
                    m.content_ciphertext,
                    aad=crypto.message_aad(conversation.id, m.sequence, m.role),
                ),
            }
            for m in messages[:1000]
        ],
        "calls": [
            {
                "id": str(c.id),
                "attempt": c.attempt,
                "state": c.state,
                "route": c.route,
                "usage": c.usage,
                "request_fingerprint": c.request_fingerprint,
            }
            for c in calls[:128]
        ],
        "source_versions": run.source_versions,
        "execution_lease": run.execution_lease,
        "event_refs": [
            {
                "id": str(e.id),
                "sequence": e.sequence,
                "kind": e.kind,
                "payload_sha256": digest(e.payload),
            }
            for e in events[:1000]
        ],
        "operations": [
            json.loads(
                crypto.open_content(
                    dek, c.operation_ciphertext, aad=crypto.change_set_aad(conversation.id, c.id)
                )
            )
            for c in changes
        ],
        "receipts": [
            {
                "id": str(r.id),
                "operation_id": str(r.operation_id),
                "digest": r.digest_sha256,
                "result": r.result,
                "executed_at": r.executed_at.isoformat(),
            }
            for r in receipts
        ],
    }
    # Actual read arguments/results and selection are already encrypted canonical
    # data: export server-visible bodies only, never raw provider reasoning.
    parts["reads_and_selection"] = []
    parts["request_contexts"] = []
    for e in events[:1000]:
        if e.kind in {
            "tool.read_result",
            "selection.frozen",
            "provider.request_context",
        } and e.payload.get("body_ciphertext"):
            body = json.loads(
                crypto.open_content(
                    dek,
                    e.payload["body_ciphertext"],
                    aad=crypto.event_content_aad(rid, e.sequence, e.kind),
                )
            )
            part_name = (
                "request_contexts"
                if e.kind == "provider.request_context"
                else "reads_and_selection"
            )
            parts[part_name].append({"event_id": str(e.id), "kind": e.kind, "body": body})
    omissions = []
    if calls and not parts["request_contexts"]:
        incomplete = True
        omissions.append("request_contexts.NOT_CAPTURED")
    while len(canonical(parts).encode("utf-8")) > MAX_BYTES:
        incomplete = True
        # Preserve causal messages and IDs first; explicit omitted categories.
        for key in ("reads_and_selection", "operations", "messages", "request_contexts"):
            if parts[key]:
                parts[key].pop()
                omissions.append(key)
                break
        else:
            raise HTTPException(422, "feedback_evidence_metadata_exceeds_bound")
    content = canonical(parts)
    bundle = MimiEvidence(
        id=uuid7(),
        conversation_id=conversation.id,
        run_id=rid,
        capture_status="incomplete" if incomplete else "complete",
        content_bytes=len(content.encode("utf-8")),
        expires_at=datetime.now(UTC) + timedelta(days=90),
        metadata_json={
            "schema_version": "mimi.causal-feedback.v1",
            "target_type": target_type,
            "target_id": target_id,
            "sha256": digest(parts),
            "omitted_parts": sorted(set(omissions)),
            "message_count": len(parts["messages"]),
            "call_count": len(parts["calls"]),
            "provider_raw_response": "NOT_CAPTURED",
            "hidden_reasoning": "EXCLUDED",
        },
    )
    # The complete status covers declared captured parts only; raw provider
    # response never masquerades as captured semantic/transport evidence.
    bundle.content_ciphertext = crypto.seal_content(
        dek, content, aad=f"mimi-evidence:{conversation.id}:{bundle.id}:causal"
    )
    db.add(bundle)
    await db.flush()
    return bundle


async def read_evidence(db, conversation, bundle_id):
    row = await db.get(MimiEvidence, bundle_id)
    if row is None or row.conversation_id != conversation.id:
        raise HTTPException(404, "Mimi evidence not found")
    if row.expires_at <= datetime.now(UTC):
        raise HTTPException(410, "Mimi evidence expired")
    if row.content_ciphertext is None:
        return {
            "id": str(row.id),
            "capture_status": row.capture_status,
            "metadata": row.metadata_json,
            "content": None,
            "legacy_content": "NOT_CAPTURED",
        }
    body = json.loads(
        crypto.open_content(
            crypto.unwrap_dek(conversation.dek_wrapped),
            row.content_ciphertext,
            aad=f"mimi-evidence:{conversation.id}:{row.id}:causal",
        )
    )
    if digest(body) != row.metadata_json["sha256"]:
        raise HTTPException(409, "Mimi evidence hash invalid")
    return {
        "id": str(row.id),
        "capture_status": row.capture_status,
        "metadata": row.metadata_json,
        "content": body,
    }
