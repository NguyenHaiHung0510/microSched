"""Bounded finalized working history in the existing encrypted Mimi event lifecycle.

Only actual permitted tool-call/result pairs are replayable. Canonical prose stays
referenced, and historical evidence never supplies a current execution lease.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from app.agent.tools.registry import READ_TOOLS, validate_read_arguments

KIND = "context.working.finalized.v1"
VERSION = "mimi.working-projection.v1"
MAX_PAIRS = 64  # Existing collection run tool allowance, not another execution budget.


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def exact_pairs(messages: list[dict[str, Any]], *, max_bytes: int) -> list[list[dict[str, Any]]]:
    pairs = []
    index = 0
    seen = set()
    while index < len(messages):
        assistant = messages[index]
        if assistant.get("role") == "system":
            index += 1  # Ephemeral finalization/budget notices never become history.
            continue
        if (
            set(assistant) != {"role", "content", "tool_calls"}
            or assistant.get("role") != "assistant"
            or assistant.get("content") is not None
            or not isinstance(assistant.get("tool_calls"), list)
            or len(assistant["tool_calls"]) != 1
            or index + 1 >= len(messages)
        ):
            raise ValueError("working_pair_shape_invalid")
        call = assistant["tool_calls"][0]
        result = messages[index + 1]
        if (
            set(call) != {"id", "type", "function"}
            or call["type"] != "function"
            or not isinstance(call["id"], str)
            or not 1 <= len(call["id"]) <= 200
            or call["id"] in seen
            or set(call["function"]) != {"name", "arguments"}
            or call["function"]["name"] not in READ_TOOLS
            or set(result) != {"role", "tool_call_id", "content"}
            or result["role"] != "tool"
            or result["tool_call_id"] != call["id"]
            or not isinstance(result["content"], str)
        ):
            raise ValueError("working_pair_identity_invalid")
        arguments = json.loads(call["function"]["arguments"])
        validate_read_arguments(call["function"]["name"], arguments)
        if not isinstance(json.loads(result["content"]), dict):
            raise ValueError("working_result_shape_invalid")
        seen.add(call["id"])
        pairs.append([assistant, result])
        index += 2
    if len(pairs) > MAX_PAIRS or len(canonical(pairs).encode()) > max_bytes:
        raise ValueError("working_projection_oversize")
    return pairs


def message_ref(row: Any) -> dict[str, Any]:
    return {"id": str(row.id), "sequence": row.sequence, "sha256": row.content_sha256}


def projection_body(
    user: Any,
    assistant: Any,
    messages: list[dict[str, Any]],
    *,
    outcome: str,
    max_bytes: int,
    terminal: dict | None = None,
) -> dict[str, Any]:
    body = {
        "schema_version": VERSION,
        "user": message_ref(user) if user else None,
        "assistant": message_ref(assistant),
        "outcome": outcome,
        "pairs": exact_pairs(messages, max_bytes=max_bytes),
        "terminal": terminal,
    }
    if len(canonical(body).encode()) > max_bytes:
        raise ValueError("working_projection_oversize")
    return body


def validate_body(body: Any, user: Any, assistant: Any, *, max_bytes: int) -> None:
    if (
        not isinstance(body, dict)
        or set(body) != {"schema_version", "user", "assistant", "outcome", "pairs", "terminal"}
        or body["schema_version"] != VERSION
        or body["user"] != (message_ref(user) if user else None)
        or body["assistant"] != message_ref(assistant)
        or body["outcome"]
        not in {
            "assistant_text",
            "clarification",
            "draft",
            "preview_candidate",
            "confirmed_execution",
        }
        or not isinstance(body["pairs"], list)
        or any(not isinstance(pair, list) or len(pair) != 2 for pair in body["pairs"])
    ):
        raise ValueError("working_projection_binding_invalid")
    terminal = body["terminal"]
    if body["outcome"] == "confirmed_execution":
        if (
            user is not None
            or body["pairs"]
            or not isinstance(terminal, dict)
            or set(terminal)
            != {
                "receipt_id",
                "change_set_id",
                "state",
                "executed_at",
                "count",
                "task_ids",
                "changes",
            }
            or terminal["state"] != "executed"
            or type(terminal["count"]) is not int
            or not 1 <= terminal["count"] <= 200
            or not isinstance(terminal["task_ids"], list)
            or len(terminal["task_ids"]) != terminal["count"]
            or not isinstance(terminal["changes"], list)
        ):
            raise ValueError("working_terminal_receipt_invalid")
    elif user is None or terminal is not None:
        raise ValueError("working_projection_source_missing")
    validated = exact_pairs([m for pair in body["pairs"] for m in pair], max_bytes=max_bytes)
    if validated != body["pairs"] or len(canonical(body).encode()) > max_bytes:
        raise ValueError("working_projection_invalid")


def task_ids(pairs: list[list[dict[str, Any]]]) -> set[str]:
    ids = set()
    for _, result_message in pairs:
        result = json.loads(result_message["content"])
        for row in result.get("rows", []):
            if isinstance(row, dict) and row.get("id"):
                ids.add(str(row["id"]))
        selection = result.get("selection")
        if isinstance(selection, dict):
            ids.update(
                str(m["id"])
                for m in selection.get("members", [])
                if isinstance(m, dict) and m.get("id")
            )
    return ids


@dataclass
class WorkingHistory:
    """Ephemeral projection shared by the main request and compaction builder."""

    by_assistant: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    refs: dict[int, dict[str, Any]] = field(default_factory=dict)
    gaps: set[str] = field(default_factory=set)
    outcomes: dict[int, dict[str, Any]] = field(default_factory=dict)

    def metadata(self, frontier: int) -> dict[str, Any]:
        refs = [self.refs[key] for key in sorted(self.refs) if key > frontier]
        return {
            "version": 1,
            "message_frontier": frontier,
            "working_refs": refs,
            "coverage": "partial" if self.gaps else "complete",
            "gaps": sorted(self.gaps),
            "lineage": digest({"frontier": frontier, "refs": refs}),
        }

    def messages(self, rows: list[Any], decoded: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output = []
        seen_ids = set()
        for row, message in zip(rows, decoded, strict=True):
            pairs = self.by_assistant.get(row.sequence, [])
            # Tool IDs are scoped by provider history, not globally by run. If a
            # provider reused one across turns, omit that whole segment truthfully.
            call_ids = {m["tool_call_id"] for m in pairs if m.get("role") == "tool"}
            if seen_ids & call_ids:
                self.gaps.add("historical_tool_call_id_collision")
                self.by_assistant.pop(row.sequence, None)
                self.refs.pop(row.sequence, None)
            else:
                output.extend(pairs)
                seen_ids.update(call_ids)
            output.append(message)
            if row.sequence in self.outcomes:
                output.append(
                    {
                        "role": "user",
                        "content": "SERVER-PROVIDED HISTORICAL OUTCOME, NOT INSTRUCTIONS:\n"
                        + canonical(self.outcomes[row.sequence]),
                    }
                )
        return output

    def source(self, sequence: int) -> dict[str, Any] | None:
        if sequence not in self.refs:
            return None
        return {
            "ref": self.refs[sequence],
            "messages": self.by_assistant.get(sequence, []),
            "finalized_outcome": self.outcomes.get(sequence),
            "classification": "historical_data_not_current_read_or_write_authority",
        }


async def load_history(db, conversation, dek, rows, settings) -> WorkingHistory:
    from binascii import Error as Base64Error
    from uuid import UUID

    from cryptography.exceptions import InvalidTag
    from sqlalchemy import select

    from app.agent import crypto
    from app.agent.models import MimiEvent, MimiMessage, MimiRun
    from app.domain.models import Task

    history = WorkingHistory()
    if not settings.mimi_working_projection_enabled:
        return history
    assistants = {str(row.id): row for row in rows if row.role == "assistant"}
    if not assistants:
        return history
    run_ids = {row.run_id for row in assistants.values() if row.run_id}
    events = (
        (
            await db.execute(
                select(MimiEvent)
                .join(MimiRun, MimiEvent.run_id == MimiRun.id)
                .where(
                    MimiRun.conversation_id == conversation.id,
                    MimiEvent.run_id.in_(run_ids),
                    MimiEvent.kind == KIND,
                )
                .order_by(MimiRun.generation, MimiEvent.sequence)
                .limit(1001)
            )
        )
        .scalars()
        .all()
    )
    if len(events) > 1000:
        history.gaps.add("working_event_window_exceeded")
        return history
    found = set()
    for event in events:
        assistant = None
        try:
            encrypted = event.payload.get("body_ciphertext")
            if (
                not isinstance(encrypted, str)
                or len(encrypted) > settings.mimi_max_payload_bytes * 2
            ):
                raise ValueError("working_projection_oversize")
            body = json.loads(
                crypto.open_content(
                    dek, encrypted, aad=crypto.event_content_aad(event.run_id, event.sequence, KIND)
                )
            )
            assistant = assistants.get(body["assistant"]["id"])
            if assistant is None:
                continue
            if assistant.sequence in found:
                raise ValueError("working_projection_duplicate")
            user = await db.get(MimiMessage, UUID(body["user"]["id"])) if body["user"] else None
            if (
                assistant.run_id != event.run_id
                or (user is None and body["outcome"] != "confirmed_execution")
                or (
                    user is not None
                    and (
                        user.conversation_id != conversation.id
                        or user.role != "user"
                        or user.sequence >= assistant.sequence
                    )
                )
            ):
                raise ValueError("working_projection_source_missing")
            validate_body(body, user, assistant, max_bytes=settings.mimi_max_payload_bytes)
            if digest(body) != event.payload.get("sha256"):
                raise ValueError("working_projection_hash_invalid")
            read_ids = task_ids(body["pairs"])
            ids = read_ids | set((body["terminal"] or {}).get("task_ids", []))
            if ids:
                # Receipt scalars remain historical truth after soft-delete.
                # Raw read pairs still require active STANDARD sources. Both
                # retain the current privacy gate, never restoring deleted content.
                eligible = (
                    (
                        await db.execute(
                            select(Task.id).where(
                                Task.id.in_([UUID(identity) for identity in ids]),
                                Task.is_private.is_(False),
                                (
                                    Task.deleted_at.is_(None)
                                    | Task.id.not_in([UUID(identity) for identity in read_ids])
                                ),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                if {str(identity) for identity in eligible} != ids:
                    raise ValueError("working_history_source_no_longer_eligible")
            if body["terminal"]:
                if not await terminal_receipt_current(
                    db, conversation.id, event.run_id, body["terminal"]
                ):
                    raise ValueError("working_terminal_receipt_missing")
                history.outcomes[assistant.sequence] = body["terminal"]
            found.add(assistant.sequence)
            history.by_assistant[assistant.sequence] = [m for pair in body["pairs"] for m in pair]
            history.refs[assistant.sequence] = {
                "event_id": str(event.id),
                "run_id": str(event.run_id),
                "sequence": event.sequence,
                "sha256": event.payload["sha256"],
                "message_sequence": assistant.sequence,
                "storage_sha256": digest(event.payload),
            }
        except ValueError, TypeError, KeyError, AttributeError, InvalidTag, Base64Error:
            history.gaps.add("working_projection_invalid_or_ineligible")
            if assistant is not None:
                history.by_assistant.pop(assistant.sequence, None)
                history.refs.pop(assistant.sequence, None)
                history.outcomes.pop(assistant.sequence, None)
    if any(row.run_id and row.sequence not in found for row in assistants.values()):
        history.gaps.add("legacy_or_interrupted_working_history_missing")
    return history


async def persist_finalized(
    db,
    conversation,
    run,
    dek,
    messages,
    outcome,
    settings,
    append_event,
    current_user_message_id=None,
    terminal=None,
):
    from sqlalchemy import select
    from sqlalchemy.exc import SQLAlchemyError

    from app.agent import crypto
    from app.agent.models import MimiEvent, MimiMessage

    if (
        not settings.mimi_working_projection_enabled
        or messages is None
        or run.state not in {"completed", "waiting_confirmation"}
        or outcome
        not in {
            "assistant_text",
            "clarification",
            "draft",
            "preview_candidate",
            "confirmed_execution",
        }
    ):
        return
    user = (
        await db.execute(
            select(MimiMessage)
            .where(
                MimiMessage.conversation_id == conversation.id,
                MimiMessage.role == "user",
                MimiMessage.id == current_user_message_id
                if current_user_message_id
                else MimiMessage.run_id == run.id,
            )
            .order_by(MimiMessage.sequence.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    assistant = (
        await db.execute(
            select(MimiMessage)
            .where(
                MimiMessage.conversation_id == conversation.id,
                MimiMessage.run_id == run.id,
                MimiMessage.role == "assistant",
            )
            .order_by(MimiMessage.sequence.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    try:
        if (user is None and outcome != "confirmed_execution") or assistant is None:
            raise ValueError("working_finalization_source_missing")
        body = projection_body(
            user if outcome != "confirmed_execution" else None,
            assistant,
            messages,
            outcome=outcome,
            max_bytes=settings.mimi_max_payload_bytes,
            terminal=terminal,
        )
        validate_body(
            body,
            user if outcome != "confirmed_execution" else None,
            assistant,
            max_bytes=settings.mimi_max_payload_bytes,
        )
        # Flush canonical outcome first. A projection failure rolls back only its
        # savepoint, never a validated answer/preview in the outer transaction.
        await db.flush()
        async with db.begin_nested():
            sequence = await append_event(db, run.id, KIND, {})
            event = (
                await db.execute(
                    select(MimiEvent).where(
                        MimiEvent.run_id == run.id,
                        MimiEvent.sequence == sequence,
                    )
                )
            ).scalar_one()
            event.payload = {
                "version": 1,
                "pair_count": len(body["pairs"]),
                "sha256": digest(body),
                "body_ciphertext": crypto.seal_content(
                    dek, canonical(body), aad=crypto.event_content_aad(run.id, sequence, KIND)
                ),
            }
            await db.flush()
    except ValueError, TypeError, KeyError, AttributeError, SQLAlchemyError:
        await append_event(
            db,
            run.id,
            "context.working.gap",
            {
                "coverage": "partial",
                "reason": "finalized_working_projection_unavailable",
            },
        )


async def working_refs_current(db, conversation_id, refs, dek=None, settings=None) -> bool:
    """Check frozen event identity; optional egress mode also checks source eligibility."""
    from binascii import Error as Base64Error
    from uuid import UUID

    from cryptography.exceptions import InvalidTag
    from sqlalchemy import select

    from app.agent import crypto
    from app.agent.models import MimiEvent, MimiMessage, MimiRun
    from app.domain.models import Task

    if not refs:
        return True
    if not isinstance(refs, list) or len(refs) > 1000:
        return False
    try:
        events = (
            (
                await db.execute(
                    select(MimiEvent)
                    .join(MimiRun, MimiEvent.run_id == MimiRun.id)
                    .where(
                        MimiRun.conversation_id == conversation_id,
                        MimiEvent.id.in_([UUID(ref["event_id"]) for ref in refs]),
                        MimiEvent.kind == KIND,
                    )
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        by_id = {str(event.id): event for event in events}
        task_refs = set()
        read_refs = set()
        for ref in refs:
            event = by_id.get(ref["event_id"])
            if (
                event is None
                or event.payload.get("sha256") != ref["sha256"]
                or digest(event.payload) != ref["storage_sha256"]
            ):
                return False
            if dek is not None:
                encrypted = event.payload.get("body_ciphertext")
                if (
                    not isinstance(encrypted, str)
                    or len(encrypted) > settings.mimi_max_payload_bytes * 2
                ):
                    return False
                body = json.loads(
                    crypto.open_content(
                        dek,
                        encrypted,
                        aad=crypto.event_content_aad(event.run_id, event.sequence, KIND),
                    )
                )
                if digest(body) != ref["sha256"]:
                    return False
                for key in ("user", "assistant"):
                    if body[key] is None:
                        continue
                    row = await db.get(MimiMessage, UUID(body[key]["id"]))
                    if row is None or message_ref(row) != body[key]:
                        return False
                if body["terminal"] and not await terminal_receipt_current(
                    db, conversation_id, event.run_id, body["terminal"]
                ):
                    return False
                read_refs.update(task_ids(body["pairs"]))
                task_refs.update(task_ids(body["pairs"]))
                task_refs.update((body["terminal"] or {}).get("task_ids", []))
        if task_refs:
            eligible = (
                (
                    await db.execute(
                        select(Task.id).where(
                            Task.id.in_([UUID(identity) for identity in task_refs]),
                            Task.is_private.is_(False),
                            (
                                Task.deleted_at.is_(None)
                                | Task.id.not_in([UUID(identity) for identity in read_refs])
                            ),
                        )
                    )
                )
                .scalars()
                .all()
            )
            return {str(identity) for identity in eligible} == task_refs
        return True
    except ValueError, TypeError, KeyError, AttributeError, InvalidTag, Base64Error:
        return False


async def preview_lifecycle_context(db, conversation_id, *, dek, settings):
    """Bounded scalar state only; no frozen payload, nonce, lease or recovery data."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from sqlalchemy import select

    from app.agent.models import (
        MimiChangeSet,
        MimiEvent,
        MimiExecutionReceipt,
        MimiMessage,
        MimiRun,
    )

    superseded = (
        select(MimiEvent.id)
        .where(
            MimiEvent.run_id == MimiChangeSet.run_id,
            MimiEvent.kind == "change_set.superseded",
        )
        .exists()
    )
    rows = (
        await db.execute(
            select(
                MimiChangeSet.id,
                MimiChangeSet.run_id,
                MimiChangeSet.state,
                MimiChangeSet.digest_sha256,
                MimiChangeSet.expires_at,
                MimiExecutionReceipt.id.label("receipt_id"),
                superseded.label("superseded"),
            )
            .join(MimiRun, MimiChangeSet.run_id == MimiRun.id)
            .outerjoin(MimiExecutionReceipt, MimiExecutionReceipt.change_set_id == MimiChangeSet.id)
            .where(MimiRun.conversation_id == conversation_id)
            .order_by(MimiChangeSet.created_at.desc(), MimiChangeSet.id.desc())
            .limit(21)
        )
    ).all()
    # Rehydrate only validated scalar receipt events independently of the prose
    # checkpoint frontier. A checkpoint containing a now-ineligible raw read may
    # be withheld in full; that must not erase otherwise eligible receipt facts.
    receipt_runs = [row.run_id for row in rows[:20] if row.receipt_id]
    history = WorkingHistory()
    if receipt_runs:
        assistants = (
            await db.scalars(
                select(MimiMessage)
                .where(
                    MimiMessage.conversation_id == conversation_id,
                    MimiMessage.run_id.in_(receipt_runs),
                    MimiMessage.role == "assistant",
                )
                .order_by(MimiMessage.sequence)
                .limit(1001)
            )
        ).all()
        if len(assistants) <= 1000:
            history = await load_history(
                db, SimpleNamespace(id=conversation_id), dek, assistants, settings
            )
        else:
            history.gaps.add("working_event_window_exceeded")
    now = datetime.now(UTC)
    return {
        "classification": "historical_state_not_current_read_or_write_authority",
        "coverage": "partial" if len(rows) > 20 else "complete",
        "order": "newest_first",
        "data_as_of": now.isoformat(),
        "historical_outcomes": [history.outcomes[key] for key in sorted(history.outcomes)],
        "receipt_history_coverage": "complete"
        if not history.gaps and len(history.outcomes) == len(receipt_runs) and len(rows) <= 20
        else "partial",
        "previews": [
            {
                "id": str(row.id),
                "run_id": str(row.run_id),
                "digest": row.digest_sha256,
                "state": row.state,
                "effective_state": "expired"
                if row.state == "pending" and row.expires_at <= now
                else row.state,
                "expiry": row.expires_at.isoformat(),
                "receipt_id": str(row.receipt_id) if row.receipt_id else None,
                "reason": "superseded_by_validated_preview"
                if row.superseded
                else "rejected"
                if row.state == "rejected"
                else "unknown"
                if row.state == "stale"
                else None,
                "successor_id": None,  # No canonical successor link; never infer one.
            }
            for row in rows[:20]
        ],
    }


def checkpoint_for_egress(checkpoint, allowed):
    if checkpoint is None or allowed:
        return checkpoint
    return {
        **checkpoint,
        "summary": (
            "Historical working summary withheld: source eligibility or receipt changed. "
            "Available suffix only."
        ),
    }


async def terminal_receipt_current(db, conversation_id, run_id, terminal):
    from uuid import UUID

    from sqlalchemy import select

    from app.agent.models import MimiChangeSet, MimiExecutionReceipt, MimiRun

    receipt = (
        await db.execute(
            select(MimiExecutionReceipt)
            .join(MimiChangeSet, MimiExecutionReceipt.change_set_id == MimiChangeSet.id)
            .join(MimiRun, MimiChangeSet.run_id == MimiRun.id)
            .where(
                MimiExecutionReceipt.id == UUID(terminal["receipt_id"]),
                MimiRun.conversation_id == conversation_id,
                MimiRun.id == run_id,
                MimiChangeSet.state == "executed",
            )
        )
    ).scalar_one_or_none()
    if receipt is None:
        return False
    ids = receipt.result.get("task_ids") or [str(receipt.task_id)]
    return (
        str(receipt.change_set_id) == terminal["change_set_id"]
        and receipt.executed_at.isoformat() == terminal["executed_at"]
        and ids == terminal["task_ids"]
        and len(ids) == terminal["count"]
    )


async def persist_confirmed(db, conversation, run, dek, receipt, operation, settings, append_event):
    """Called after canonical commit outcome, inside the existing confirmation transaction.

    Scalar receipt meaning is historical evidence. It carries no nonce, lease,
    selection authorization, recovery snapshot, raw field values or inverse.
    """
    entries = operation.args.get("entries") if operation.tool == "task.collection.v1" else None
    terminal = {
        "receipt_id": str(receipt.id),
        "change_set_id": str(receipt.change_set_id),
        "state": "executed",
        "executed_at": receipt.executed_at.isoformat(),
        "task_ids": receipt.result.get("task_ids") or [str(receipt.task_id)],
        "count": receipt.result.get("count", 1),
        "changes": [
            {"action": e["command"]["action"], "fields": sorted(e["command"].get("fields", {}))}
            for e in entries
        ]
        if entries
        else [{"action": "create", "fields": sorted(operation.args)}],
    }
    await persist_finalized(
        db,
        conversation,
        run,
        dek,
        [],
        "confirmed_execution",
        settings,
        append_event,
        terminal=terminal,
    )
