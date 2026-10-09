"""Additive encrypted per-message producer binding; never infer origin from prose."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from uuid import UUID, uuid7

from cryptography.exceptions import InvalidTag
from sqlalchemy import func, select

from app.agent import crypto
from app.agent.models import MimiEvent, MimiMessage, MimiProviderCall, MimiRun

KIND = "message.provenance.v1"
SCHEMA = "mimi.message-provenance.v1"
MAX_MESSAGES = 100
MAX_CIPHERTEXT = 16_384
PRODUCERS = {
    "provider_text": "model_answer",
    "context_budget_stop": "server_notice",
    "checkpoint_unknown": "server_notice",
    "checkpoint_materialization_failed": "server_notice",
    "provider_output_rejected": "server_notice",
    "provider_terminal": "server_notice",
    "local_deterministic_result": "server_notice",
    "conversation_frontier_changed": "server_notice",
    "preview_frontier_changed": "server_notice",
    "pending_preview_requires_decision": "server_notice",
    "preview_prepared": "server_notice",
    "operation_committed": "server_notice",
    "process_loss_recovery": "server_notice",
    "collection_committed": "server_notice",
    "undo_prepared": "server_notice",
}


def unknown():
    return {
        "origin": "unknown",
        "producer_code": None,
        "version": None,
        "event_sequence": None,
        "source": "absent_or_unverified",
    }


def binding_hash(conversation_id, run_id, message_id, sequence):
    value = [str(conversation_id), str(run_id), str(message_id), sequence]
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def valid_call(call, run_id):
    return (
        call is not None
        and call.run_id == run_id
        and call.state == "succeeded"
        and isinstance(call.route, dict)
        and call.route.get("purpose", "main") == "main"
    )


async def append_message(
    db, conversation, run_id, dek, content, *, producer_code, provider_call_id=None, append_event
):
    origin = PRODUCERS.get(producer_code)
    if origin is None:
        raise ValueError("message_producer_not_allowlisted")
    run = (
        await db.scalars(
            select(MimiRun)
            .where(MimiRun.id == run_id, MimiRun.conversation_id == conversation.id)
            .with_for_update()
        )
    ).one_or_none()
    if run is None:
        raise ValueError("message_provenance_run_binding_invalid")
    if origin == "model_answer":
        call = await db.get(MimiProviderCall, provider_call_id) if provider_call_id else None
        if not valid_call(call, run_id):
            raise ValueError("message_provenance_provider_binding_invalid")
    elif provider_call_id is not None:
        raise ValueError("server_notice_cannot_borrow_provider_call")

    # Nested transaction protects the pair even if an enclosing run handler
    # catches the error and records a terminal. No independent commit.
    async with db.begin_nested():
        sequence = conversation.next_message_sequence
        message = MimiMessage(
            id=uuid7(),
            conversation_id=conversation.id,
            run_id=run_id,
            sequence=sequence,
            role="assistant",
            content_ciphertext=crypto.seal_content(
                dek, content, aad=crypto.message_aad(conversation.id, sequence, "assistant")
            ),
            content_bytes=len(content.encode()),
            content_sha256=hashlib.sha256(content.encode()).hexdigest(),
        )
        db.add(message)
        conversation.next_message_sequence += 1
        digest = binding_hash(conversation.id, run_id, message.id, sequence)
        event_sequence = await append_event(
            db, run_id, KIND, {"schema_version": SCHEMA, "binding_sha256": digest}
        )
        body = {
            "schema_version": SCHEMA,
            "message_id": str(message.id),
            "message_sequence": sequence,
            "conversation_id": str(conversation.id),
            "run_id": str(run_id),
            "origin": origin,
            "producer_code": producer_code,
            "producer_version": 1,
            "provider_call_id": str(provider_call_id) if provider_call_id else None,
            "related_event_sequence": None,
        }
        event = (
            await db.scalars(
                select(MimiEvent).where(
                    MimiEvent.run_id == run_id,
                    MimiEvent.sequence == event_sequence,
                    MimiEvent.kind == KIND,
                )
            )
        ).one()
        event.payload = {
            **event.payload,
            "body_ciphertext": crypto.seal_content(
                dek,
                json.dumps(body, sort_keys=True, separators=(",", ":")),
                aad=crypto.event_content_aad(run_id, event_sequence, KIND),
            ),
        }
        await db.flush()
    return message


def decode_binding(event, message, conversation, dek):
    payload = event.payload
    ciphertext = payload.get("body_ciphertext")
    if (
        payload.get("schema_version") != SCHEMA
        or not isinstance(ciphertext, str)
        or len(ciphertext) > MAX_CIPHERTEXT
        or event.run_id != message.run_id
    ):
        return None
    body = json.loads(
        crypto.open_content(
            dek, ciphertext, aad=crypto.event_content_aad(event.run_id, event.sequence, KIND)
        )
    )
    expected = {
        "schema_version",
        "message_id",
        "message_sequence",
        "conversation_id",
        "run_id",
        "origin",
        "producer_code",
        "producer_version",
        "provider_call_id",
        "related_event_sequence",
    }
    if (
        not isinstance(body, dict)
        or set(body) != expected
        or not isinstance(body["producer_code"], str)
        or body["producer_code"] not in PRODUCERS
        or body["origin"] not in {"model_answer", "server_notice"}
    ):
        return None
    if (
        body["schema_version"] != SCHEMA
        or body["message_id"] != str(message.id)
        or type(body["message_sequence"]) is not int
        or body["message_sequence"] != message.sequence
        or body["conversation_id"] != str(conversation.id)
        or message.conversation_id != conversation.id
        or body["run_id"] != str(message.run_id)
        or type(body["producer_version"]) is not int
        or body["producer_version"] != 1
        or PRODUCERS.get(body["producer_code"]) != body["origin"]
        or body["related_event_sequence"] is not None
        or payload.get("binding_sha256")
        != binding_hash(conversation.id, message.run_id, message.id, message.sequence)
    ):
        return None
    if body["origin"] == "model_answer":
        body["provider_call_id"] = UUID(body["provider_call_id"])
    elif body["provider_call_id"] is not None:
        return None
    return body


async def read_message_provenance(db, conversation, messages, dek):
    if len(messages) > MAX_MESSAGES:
        raise ValueError("message_provenance_read_bound_exceeded")
    result = {message.id: unknown() for message in messages}
    if conversation.is_private or conversation.sensitivity != "standard":
        return result
    targets = {
        binding_hash(conversation.id, m.run_id, m.id, m.sequence): m
        for m in messages
        if m.role == "assistant" and m.run_id is not None and m.conversation_id == conversation.id
    }
    if not targets:
        return result
    # Two exact matches per hash suffice to reject duplicates, without letting
    # many duplicates for one message hide a later message's binding.
    ranked = (
        select(
            MimiEvent.id,
            func.row_number()
            .over(
                partition_by=MimiEvent.payload["binding_sha256"].astext,
                order_by=MimiEvent.id,
            )
            .label("position"),
        )
        .join(MimiRun, MimiRun.id == MimiEvent.run_id)
        .where(
            MimiRun.conversation_id == conversation.id,
            MimiEvent.kind == KIND,
            MimiEvent.payload["binding_sha256"].astext.in_(targets),
        )
        .subquery()
    )
    events = (
        await db.scalars(
            select(MimiEvent)
            .join(ranked, ranked.c.id == MimiEvent.id)
            .where(ranked.c.position <= 2)
        )
    ).all()
    by_hash = defaultdict(list)
    for event in events:
        by_hash[event.payload["binding_sha256"]].append(event)
    decoded = {}
    for digest, message in targets.items():
        rows = by_hash[digest]
        if len(rows) != 1:
            continue
        try:
            body = decode_binding(rows[0], message, conversation, dek)
        except InvalidTag, ValueError, TypeError, KeyError, UnicodeError:
            body = None
        if body is not None:
            decoded[message.id] = (rows[0], body)
    call_ids = [
        body["provider_call_id"] for _, body in decoded.values() if body["origin"] == "model_answer"
    ]
    calls = (
        (
            await db.scalars(
                select(MimiProviderCall)
                .join(MimiRun)
                .where(
                    MimiRun.conversation_id == conversation.id,
                    MimiProviderCall.id.in_(call_ids),
                )
            )
        ).all()
        if call_ids
        else []
    )
    call_map = {call.id: call for call in calls}
    for message in messages:
        match = decoded.get(message.id)
        if match is None:
            continue
        event, body = match
        if body["origin"] == "model_answer" and not valid_call(
            call_map.get(body["provider_call_id"]), message.run_id
        ):
            continue
        result[message.id] = {
            "origin": body["origin"],
            "producer_code": body["producer_code"],
            "version": 1,
            "event_sequence": event.sequence,
            "source": "server_verified",
        }
    return result
