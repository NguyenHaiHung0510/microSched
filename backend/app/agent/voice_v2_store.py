"""Voice v2 reads, source fences, and typed actions in the existing Mimi store."""

from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

from fastapi import HTTPException
from sqlalchemy import func, select

from app.agent import crypto
from app.agent.models import MimiChangeSet, MimiEvent, MimiExecutionReceipt, MimiRun
from app.agent.openrouter import validate_task_candidate
from app.agent.selection import (
    SELECTION_TOOL,
    SelectionCorrection,
    covered_versions,
    load_selection,
    persist_selection,
)
from app.agent.service import (
    TOOL_VERSION,
    _append_event,
    _confirm_collection,
    _provider_history,
    _transaction_lock_key,
    add_preview_notice,
    freeze_change_set_row,
)
from app.agent.task_collection import (
    COLLECTION_CANDIDATE_TOOL,
    COLLECTION_TOOL,
    CollectionCandidate,
    TaskCommand,
    digest,
    freeze_collection,
    freeze_undo,
)
from app.agent.tools.calendar_reads import (
    CALENDAR_READ_TOOL,
    CALENDAR_READ_TOOLS,
    CalendarBindings,
    calendar_bindings_current,
    calendar_result_bindings,
)
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL, execute_read_tool
from app.agent.voice_preferences import voice_preference
from app.agent.voice_protocol import MAX_TOOL_BYTES, VoiceError, encoded
from app.agent.voice_store import VoiceStore
from app.agent.voice_v2_intent import FAST_APPLY_MAX, VoiceTurnBinding
from app.agent.voice_v2_outcome import VoiceActionOutcome, committed
from app.agent.voice_v2_protocol import UNDO_TOOL, VOICE_POLICY, v2_tools
from app.domain.models import Task

MAX_EXPOSED_ROWS = 2048
MAX_QUERY_OBSERVATIONS = 256
MAX_MEMBERSHIP_OBSERVATIONS = 8
_SET_READS = frozenset({"task.query.v1", "task.aggregate.v1", CALENDAR_READ_TOOL})


class VoiceContextChanged(VoiceError):
    def __init__(self):
        super().__init__("voice_source_changed")


async def execute_voice_read(db, name, arguments, *, settings):
    result = await execute_read_tool(db, name, arguments, settings=settings)
    # Preserve the public Calendar page/cursor contract. An independent bounded
    # annotation page gives day milestones equal visibility in Voice, even
    # when the first canonical page is full of Tasks.
    if (
        name == CALENDAR_READ_TOOL
        and result.get("coverage") != "unavailable"
        and not arguments.get("cursor")
        and "annotation" in arguments.get("kinds", ("task", "event", "annotation"))
    ):
        marks = await execute_read_tool(
            db,
            name,
            {**arguments, "kinds": ["annotation"], "cursor": None},
            settings=settings,
        )
        result = {**result, "day_milestones": marks}
    return result


def _read_digest(result):
    value = {k: v for k, v in result.items() if k != "data_as_of"}
    if "day_milestones" in value:
        value["day_milestones"] = {
            k: v for k, v in value["day_milestones"].items() if k != "data_as_of"
        }
    if "groups" in value:
        value["groups"] = sorted(value["groups"], key=lambda g: str(g["value"]))
    return digest(value)


@dataclass(frozen=True)
class VoiceReadObservation:
    name: str
    arguments: dict
    digest: str
    # A list, count, or missing ID can change without changing any returned row.
    membership: bool


@dataclass
class VoiceSources:
    """What this upstream context has seen; discarded on a fresh context."""

    tasks: dict[UUID, tuple] = field(default_factory=dict)
    calendar: CalendarBindings = field(default_factory=dict)
    queries: dict[str, VoiceReadObservation] = field(default_factory=dict)

    async def check_versions(self, db):
        if self.tasks:
            rows = (
                await db.execute(
                    select(Task.id, Task.updated_at, Task.collection_version, Task.deleted_at)
                    .where(Task.id.in_(self.tasks), Task.is_private.is_(False))
                    .order_by(Task.id)
                    .with_for_update(read=True)
                )
            ).all()
            actual = {
                tid: (version.isoformat(), collection, deleted is not None)
                for tid, version, collection, deleted in rows
            }
            if actual != self.tasks:
                raise VoiceContextChanged()
        if not await calendar_bindings_current(db, self.calendar, lock=True):
            raise VoiceContextChanged()

    async def check(self, db, settings, *, detail=False):
        """Check membership at every source gate; replay versioned reads only for full checks."""
        await self.check_versions(db)
        for read in self.queries.values():
            if not (detail or read.membership):
                continue
            try:
                result = await execute_voice_read(db, read.name, read.arguments, settings=settings)
            except ValueError:
                raise VoiceContextChanged() from None
            if _read_digest(result) != read.digest:
                raise VoiceContextChanged()

    def plus(self, name, arguments, result):
        tasks, calendar, queries = self.tasks.copy(), self.calendar.copy(), self.queries.copy()
        if result.get("coverage") != "unavailable":
            if name in CALENDAR_READ_TOOLS:
                bindings = calendar_result_bindings(name, result)
                if "day_milestones" in result:
                    bindings.update(calendar_result_bindings(name, result["day_milestones"]))
                for key, version in bindings.items():
                    if calendar.setdefault(key, version) != version:
                        raise VoiceContextChanged()
            elif name != SELECTION_TOOL:
                for row in result.get("rows", ()):
                    expected = (
                        row["source_version"],
                        row["collection_version"],
                        row.get("deleted_at") is not None,
                    )
                    if tasks.setdefault(UUID(row["id"]), expected) != expected:
                        raise VoiceContextChanged()
            if name != SELECTION_TOOL:
                key = digest([name, arguments])
                observed = VoiceReadObservation(
                    name,
                    arguments,
                    _read_digest(result),
                    name in _SET_READS or not result.get("rows") or bool(result.get("missing_ids")),
                )
                if queries.setdefault(key, observed).digest != observed.digest:
                    raise VoiceContextChanged()
        if (
            len(tasks) + len(calendar) > MAX_EXPOSED_ROWS
            or len(queries) > MAX_QUERY_OBSERVATIONS
            or sum(read.membership for read in queries.values()) > MAX_MEMBERSHIP_OBSERVATIONS
        ):
            # Retire this context; dropping a binding while the model still
            # has its result would make later output incorrectly look safe.
            raise VoiceContextChanged()
        return VoiceSources(tasks, calendar, queries)


def voice_candidate(calls, *, collection_enabled):
    """A whole request is exactly one typed proposal, never a surviving fragment."""
    if len(calls) > 1:
        raise ValueError("voice_single_proposal_required")
    if not calls:
        return None
    candidates, selections = [], set()
    for name, arguments in calls:
        if name == UNDO_TOOL and collection_enabled:
            if not arguments:
                return UNDO_TOOL, {"target": "latest"}
            if arguments == {"target": "latest"}:
                return UNDO_TOOL, arguments
            if (
                set(arguments) == {"target", "receipt_ref"}
                and arguments["target"] == "receipt"
                and isinstance(arguments["receipt_ref"], str)
                and len(arguments["receipt_ref"]) == 27
                and arguments["receipt_ref"].startswith("vr_")
                and all(c in "0123456789abcdef" for c in arguments["receipt_ref"][3:])
            ):
                return UNDO_TOOL, arguments
            raise ValueError("voice_undo_selector_invalid")
        if name == COLLECTION_CANDIDATE_TOOL and collection_enabled:
            candidate = CollectionCandidate.model_validate(arguments)
            candidates.extend(candidate.entries)
            if candidate.selection_id:
                selections.add(candidate.selection_id)
        elif name == CREATE_CANDIDATE_TOOL and set(arguments) == {"task"}:
            raw_task = arguments["task"]
            if not isinstance(raw_task, dict) or "id" in raw_task:
                raise ValueError("voice_task_identity_invalid")
            task = validate_task_candidate(raw_task, require_id=False)
            if not collection_enabled:
                if len(calls) != 1:
                    raise ValueError("voice_collection_not_leased")
                return TOOL_VERSION, task.model_copy(update={"id": uuid7()}).model_dump(mode="json")
            fields = task.model_dump(mode="json", exclude={"id", "items", "is_private"})
            candidates.append(
                TaskCommand(
                    action="create",
                    fields=fields,
                    children=tuple(
                        {"action": "append", "fields": {"content": c}} for c in task.items
                    ),
                )
            )
        else:
            raise ValueError("voice_action_not_leased")
    if len(selections) > 1:
        raise ValueError("voice_selection_fragments_do_not_match")
    return COLLECTION_TOOL, CollectionCandidate(
        selection_id=next(iter(selections), None), entries=tuple(candidates)
    )


def automatic_plan(plan, *, inverse=False):
    """Eligibility belongs to frozen IDs/effects, never natural-language text."""
    ids = [entry.id for entry in plan.entries]
    allowed = {"create", "edit", "soft_delete"} | ({"restore"} if inverse else set())
    return (
        1 <= len(ids) <= FAST_APPLY_MAX
        and len(set(ids)) == len(ids)
        and all(
            entry.command.action in allowed
            and entry.command.reminder.action == "keep"
            and entry.reminder_effect["action"] in {"keep", "none"}
            and "historical_rearm" not in entry.reminder_effect
            for entry in plan.entries
        )
    )


def receipt_ref(conversation_id, receipt_id):
    # Opaque, non-authorizing context identity. Raw receipt/Task IDs and
    # encrypted recovery/history never go into the live status projection.
    token = hashlib.sha256(f"mimi-voice-receipt-v1:{conversation_id}:{receipt_id}".encode())
    return "vr_" + token.hexdigest()[:24]


async def voice_receipt_context(db, auth, conversation):
    from app.agent.receipt_history import bound_receipt

    ids = (
        await db.scalars(
            select(MimiExecutionReceipt.id)
            .join(MimiChangeSet, MimiExecutionReceipt.change_set_id == MimiChangeSet.id)
            .join(MimiRun, MimiChangeSet.run_id == MimiRun.id)
            .where(MimiRun.conversation_id == conversation.id)
            .order_by(MimiExecutionReceipt.executed_at.desc(), MimiExecutionReceipt.id.desc())
            .limit(21)
        )
    ).all()
    recent = []
    for index, identity in enumerate(ids[:20]):
        try:
            receipt, _, _, bound_conversation = await bound_receipt(db, auth, identity)
        except HTTPException:
            continue
        if bound_conversation.id != conversation.id:
            continue
        target_ids = receipt.result.get("task_ids") or [str(receipt.task_id)]
        visible = set(
            await db.scalars(
                select(Task.id).where(
                    Task.id.in_([UUID(value) for value in target_ids]), Task.is_private.is_(False)
                )
            )
        )
        if len(visible) != len(target_ids):
            continue
        recent.append(
            {
                "receipt_ref": receipt_ref(conversation.id, identity),
                "latest": index == 0,
                "task_count": receipt.result.get("count", 1),
                "executed_at": receipt.executed_at.isoformat(),
            }
        )
    return {
        "classification": "historical_status_not_write_authority",
        "coverage": "partial" if len(ids) > 20 else "complete",
        "recent_receipts": recent,
    }


async def advance_voice_after_manual_confirm(db, conversation, child, before_sequence):
    """Advance only this active Voice parent after its exact immutable preview is confirmed."""
    lease = child.execution_lease
    if lease.get("voice_action_kind") != "preview":
        return
    try:
        parent_id = UUID(lease["voice_parent_run"])
    except KeyError, TypeError, ValueError:
        return
    parent = await db.get(MimiRun, parent_id, with_for_update=True, populate_existing=True)
    if parent is None or parent.conversation_id != conversation.id or parent.state != "running":
        return
    current = parent.execution_lease
    if (
        current.get("mode") != "voice"
        or current.get("voice_protocol") != 2
        or current.get("stop_requested")
        or current.get("last_action_turn") != lease.get("voice_turn")
        or current.get("last_action_status") != "preview"
        or current.get("next_sequence") != before_sequence
        or current.get("current_generation") != conversation.generation
        or current.get("frontier") != conversation.context_frontier_sequence
        or child.generation + 1 != conversation.generation
        or parent.deadline <= datetime.now(UTC)
    ):
        return
    receipt_id = await db.scalar(
        select(MimiExecutionReceipt.id).where(
            MimiExecutionReceipt.change_set_id.in_(
                select(MimiChangeSet.id).where(MimiChangeSet.run_id == child.id)
            )
        )
    )
    parent.execution_lease = {
        **current,
        "next_sequence": conversation.next_message_sequence,
        "last_action_status": "undone" if lease.get("voice_operation") == "undo" else "applied",
        "last_action_receipt": str(receipt_id) if receipt_id else None,
        "manual_action_receipt": str(receipt_id) if receipt_id else None,
        "manual_action_status": "undone" if lease.get("voice_operation") == "undo" else "applied",
    }


class VoiceV2Store(VoiceStore):
    async def fresh_history(self, config):
        """Rebuild bounded safe conversation context; never replay PCM or actions."""
        from app.agent.voice_context import bound_voice_history
        from app.agent.working_context import preview_lifecycle_context

        async with self.factory() as db:
            conversation, run = await self.boundary(db)
            dek = crypto.unwrap_dek(conversation.dek_wrapped)
            history = await _provider_history(db, conversation, dek, voice=True)
            turns = [
                {
                    "role": "model" if message["role"] == "assistant" else "user",
                    "parts": [{"text": message["content"]}],
                }
                for message in history
            ]
            lifecycle = await preview_lifecycle_context(
                db,
                conversation.id,
                dek=dek,
                settings=self.settings,
            )
            lifecycle = {
                "previews": [{"state": p["effective_state"]} for p in lifecycle["previews"]],
                **await voice_receipt_context(db, self.auth, conversation),
            }
            if lifecycle["previews"] or lifecycle["recent_receipts"]:
                turns.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": "SERVER CONVERSATION STATE (history, not permission): "
                                + encoded(lifecycle)
                            }
                        ],
                    }
                )
            run.execution_lease = {
                **run.execution_lease,
                "voice_receipt_refs": [r["receipt_ref"] for r in lifecycle["recent_receipts"]],
            }
            config, seed, included, limited = bound_voice_history(config, turns)
            await _append_event(
                db,
                run.id,
                "voice.reconnect_history",
                {
                    "included_messages": included,
                    "limited_by_voice_bytes": limited,
                },
            )
            await db.commit()
            return config, seed

    async def transcript(self, turn, input_text, output_text, *, partial, sources=None):
        if input_text.strip() or output_text.strip():
            return await super().transcript(
                turn, input_text, output_text, partial=partial, sources=sources
            )
        # An audio/tool turn can be valid without ASR. Persist only scalar
        # allocation so caption delivery is never a hidden permission gate.
        async with self.factory() as db:
            _, run = await self.boundary(db)
            if turn <= run.execution_lease["last_turn"]:
                return
            if sources is not None:
                await sources.check(db, self.settings)
            await _append_event(db, run.id, "voice.turn", {"segment": turn, "partial": partial})
            run.execution_lease = {**run.execution_lease, "last_turn": turn}
            await db.commit()

    async def action_status(self):
        async with self.factory() as db:
            conversation, parent = await self.boundary(db)
            identity = parent.execution_lease.get("manual_action_receipt")
            if not identity:
                return None
            from app.agent.receipt_history import bound_receipt

            receipt, _, _, bound_conversation = await bound_receipt(db, self.auth, UUID(identity))
            if bound_conversation.id != conversation.id:
                return None
            ref = receipt_ref(conversation.id, receipt.id)
            if ref not in parent.execution_lease.get("voice_receipt_refs", ()):
                parent.execution_lease = {
                    **parent.execution_lease,
                    "voice_receipt_refs": [
                        *parent.execution_lease.get("voice_receipt_refs", ())[-19:],
                        ref,
                    ],
                }
                await db.commit()
            return committed(
                parent.execution_lease["manual_action_status"],
                receipt_id=receipt.id,
                receipt_ref=receipt_ref(conversation.id, receipt.id),
            )

    @asynccontextmanager
    async def live_gate(self, sources=None, *, detail=False):
        """Hold the session/frontier and source locks through each actual wire write."""
        async with self.factory() as db:
            await self.boundary(db)
            if sources is not None:
                await sources.check(db, self.settings, detail=detail)
            yield

    @asynccontextmanager
    async def deliver_read(self, identity, name, arguments, epoch, sources):
        async with self.factory() as db:
            conversation, run = await self.boundary(db)
            await sources.check_versions(db)
            dek = crypto.unwrap_dek(conversation.dek_wrapped)
            try:
                if name not in v2_tools(self.settings):
                    raise ValueError("voice_read_not_leased")
                if name == SELECTION_TOOL:
                    result = await persist_selection(
                        db,
                        conversation.id,
                        run.id,
                        dek,
                        arguments,
                        _append_event,
                        voice_epoch=epoch,
                    )
                else:
                    result = await execute_voice_read(db, name, arguments, settings=self.settings)
            except SelectionCorrection as error:
                result = error.feedback()
            except ValueError:
                result = {
                    "error": {"code": "voice_read_arguments_invalid"},
                    "coverage": "unavailable",
                }
            if len(encoded(result).encode()) > MAX_TOOL_BYTES:
                result = {"error": {"code": "voice_result_limit"}, "coverage": "unavailable"}
            updated = sources.plus(name, arguments, result)
            sequence = await _append_event(
                db,
                run.id,
                "tool.read_result",
                {
                    "tool": name,
                    "provider_call_id": identity,
                    "voice_epoch": epoch,
                    "arguments_sha256": digest(arguments),
                    "result_sha256": digest(result),
                    "coverage": result.get("coverage"),
                },
            )
            event = await db.scalar(
                select(MimiEvent).where(MimiEvent.run_id == run.id, MimiEvent.sequence == sequence)
            )
            event.payload = {
                **event.payload,
                "body_ciphertext": crypto.seal_content(
                    dek,
                    encoded({"arguments": arguments, "result": result}),
                    aad=crypto.event_content_aad(run.id, sequence, "tool.read_result"),
                ),
            }
            # Check prior memberships and this result together at delivery.
            # A rejected tool response and its encrypted receipt both unwind.
            await updated.check(db, self.settings)
            yield result, updated
            await _append_event(db, run.id, "voice.tool_sent", {"provider_call_id": identity})
            await db.commit()

    async def _inverse(self, db, conversation, parent, dek, selector):
        from app.agent.receipt_history import bound_receipt, latest_receipt, recovery_for

        if selector["target"] == "latest":
            identity = await latest_receipt(db, conversation.id)
            if identity is None:
                raise HTTPException(409, "voice_undo_receipt_missing")
        else:
            if selector["receipt_ref"] not in parent.execution_lease.get("voice_receipt_refs", ()):
                raise HTTPException(409, "voice_undo_receipt_not_exposed")
            context = await voice_receipt_context(db, self.auth, conversation)
            if selector["receipt_ref"] not in {
                row["receipt_ref"] for row in context["recent_receipts"]
            }:
                raise HTTPException(409, "voice_undo_receipt_not_exposed")
            candidates = (
                await db.scalars(
                    select(MimiExecutionReceipt.id)
                    .join(MimiChangeSet, MimiExecutionReceipt.change_set_id == MimiChangeSet.id)
                    .join(MimiRun, MimiChangeSet.run_id == MimiRun.id)
                    .where(MimiRun.conversation_id == conversation.id)
                    .order_by(
                        MimiExecutionReceipt.executed_at.desc(), MimiExecutionReceipt.id.desc()
                    )
                    .limit(20)
                )
            ).all()
            matches = [
                value
                for value in candidates
                if receipt_ref(conversation.id, value) == selector["receipt_ref"]
            ]
            if len(matches) != 1:
                raise HTTPException(409, "voice_undo_receipt_ambiguous")
            identity = matches[0]
        receipt, change, _, bound_conversation = await bound_receipt(db, self.auth, identity)
        if bound_conversation.id != conversation.id:
            raise HTTPException(409, "voice_undo_receipt_scope_invalid")
        recovery = recovery_for(receipt, change, bound_conversation, dek)
        # Latest is never skipped, including when it is itself an Undo.
        if recovery["plan"].get("undo_receipt_id"):
            raise HTTPException(409, "voice_undo_latest_receipt_not_eligible")
        plan = await freeze_undo(db, receipt.id, recovery)
        original_has_effect = any(
            entry["command"]["reminder"]["action"] != "keep"
            or entry["reminder_effect"]["action"] not in {"keep", "none"}
            for entry in recovery["plan"]["entries"]
        )
        return plan, not original_has_effect

    async def _prepare(self, db, conversation, parent, dek, proposal, epoch):
        tool, args = proposal
        if tool == TOOL_VERSION:
            return tool, args
        ids = [entry.id for entry in args.entries if entry.id is not None]
        bound = {}
        if ids:
            current = await db.scalar(
                select(MimiEvent.id).where(
                    MimiEvent.run_id == parent.id,
                    MimiEvent.kind == "selection.frozen",
                    MimiEvent.payload["voice_epoch"].astext == str(epoch),
                    MimiEvent.payload["selection_id"].astext == str(args.selection_id),
                )
            )
            if current is None:
                raise HTTPException(409, "voice_current_selection_required")
            bound = covered_versions(
                await load_selection(db, conversation.id, args.selection_id, dek), ids
            )
        return COLLECTION_TOOL, await freeze_collection(db, args, covered_versions=bound)

    async def act(self, turn, epoch, calls, binding, transcript, sources, is_active):
        """A complete turn owns one opportunity; domain delta and receipt commit together."""
        try:
            proposal = voice_candidate(
                calls, collection_enabled=self.settings.mimi_collection_enabled
            )
        except ValueError:
            return VoiceActionOutcome("needs_clarification", "voice_plan_invalid")
        if proposal is None or not is_active():
            return VoiceActionOutcome("rejected", "voice_turn_expired")
        if not isinstance(binding, VoiceTurnBinding) or not binding.matches(
            turn, epoch, len(calls)
        ):
            return VoiceActionOutcome("needs_clarification", "voice_spoken_intent_unproven")
        try:
            return await self._act(
                turn,
                epoch,
                proposal,
                binding,
                sources,
                is_active,
            )
        except VoiceContextChanged:
            return VoiceActionOutcome("rejected", "voice_source_changed", reset_context=True)
        except HTTPException as error:
            if error.status_code not in {404, 409, 422}:
                raise
            if error.status_code == 404:
                return VoiceActionOutcome("rejected", "voice_action_not_authorized")
            if proposal[0] == UNDO_TOOL:
                return VoiceActionOutcome("rejected", "voice_undo_unavailable")
            code = error.detail
            if isinstance(code, str) and (
                "selection" in code or code.startswith("task_collection_source")
            ):
                return VoiceActionOutcome("rejected", "voice_selection_stale")
            return VoiceActionOutcome("rejected", "voice_plan_rejected")
        except ValueError:
            return VoiceActionOutcome("needs_clarification", "voice_plan_invalid")

    async def _act(self, turn, epoch, proposal, binding, sources, is_active):
        async with self.factory() as db:
            key = f"mimi-voice-v2:{self.run_id}:{turn}"
            # Same ordering as a manual Confirm: key, then conversation/run.
            await db.execute(
                select(func.pg_advisory_xact_lock(_transaction_lock_key("mimi-confirm", key)))
            )
            conversation, parent = await self.boundary(db)
            if not is_active() or turn != parent.execution_lease["last_turn"]:
                return VoiceActionOutcome("rejected", "voice_turn_expired")
            event_binding = digest(
                {
                    "epoch": epoch,
                    "turn": turn,
                    "tool_call_ids": binding.call_ids,
                    "audio_window": [binding.start_ms, binding.end_ms],
                    "proposal": [
                        proposal[0],
                        (
                            proposal[1].model_dump(mode="json")
                            if hasattr(proposal[1], "model_dump")
                            else proposal[1]
                        ),
                    ],
                }
            )
            if parent.execution_lease.get("last_action_turn") == turn:
                if parent.execution_lease.get("last_action_binding") != event_binding:
                    return VoiceActionOutcome("rejected", "voice_turn_expired")
                identity = parent.execution_lease.get("last_action_receipt")
                return committed(
                    parent.execution_lease["last_action_status"],
                    receipt_id=identity,
                    receipt_ref=receipt_ref(conversation.id, identity) if identity else None,
                )
            if await db.scalar(
                select(MimiExecutionReceipt.id).where(MimiExecutionReceipt.idempotency_key == key)
            ):
                return VoiceActionOutcome("rejected", "voice_result_ambiguous")
            now = datetime.now(UTC)
            if await db.scalar(
                select(MimiChangeSet.id)
                .join(MimiRun)
                .where(
                    MimiRun.conversation_id == conversation.id,
                    MimiChangeSet.state == "pending",
                    MimiChangeSet.expires_at > now,
                )
                .limit(1)
            ):
                return VoiceActionOutcome("rejected", "voice_preview_pending")
            dek = crypto.unwrap_dek(conversation.dek_wrapped)
            await sources.check(db, self.settings, detail=True)
            undo = proposal[0] == UNDO_TOOL
            if undo:
                tool = COLLECTION_TOOL
                plan, inverse_eligible = await self._inverse(
                    db, conversation, parent, dek, proposal[1]
                )
            else:
                tool, plan = await self._prepare(db, conversation, parent, dek, proposal, epoch)
            fast = False
            if tool == COLLECTION_TOOL:
                preference = await voice_preference(db, self.auth, lock=True)
                fast = (
                    preference.fast_apply
                    and automatic_plan(plan, inverse=undo)
                    and (not undo or inverse_eligible)
                )
            if not is_active():
                return VoiceActionOutcome("rejected", "voice_turn_expired")
            expires = now + timedelta(minutes=self.settings.mimi_preview_ttl_minutes)
            status = ("undone" if undo else "applied") if fast else "preview"
            child = MimiRun(
                id=uuid7(),
                conversation_id=conversation.id,
                generation=conversation.generation,
                state="waiting_confirmation",
                deadline=expires,
                execution_lease={
                    "mode": "voice_action",
                    "voice_parent_run": str(parent.id),
                    "voice_turn": turn,
                    "voice_action_kind": status,
                    "voice_operation": "undo" if undo else "change",
                    "capabilities": [tool],
                    "sensitivity": "standard",
                },
            )
            change, operation = freeze_change_set_row(
                conversation.id,
                child.id,
                dek,
                tool,
                plan.model_dump(mode="json") if tool == COLLECTION_TOOL else plan,
                expires,
                VOICE_POLICY,
            )
            db.add(child)
            conversation.generation += 1
            await db.flush()
            db.add(change)
            await db.flush()
            receipt = None
            if fast:

                async def invalidate(reason):
                    raise HTTPException(409, reason)

                receipt = await _confirm_collection(
                    db, self.auth, conversation, child, change, operation, key, dek, invalidate
                )
            else:
                await add_preview_notice(
                    db,
                    conversation,
                    child.id,
                    dek,
                    "Đã chuẩn bị bản xem trước. Hãy kiểm tra và xác nhận trong ứng dụng.",
                    undo=undo,
                )
                await _append_event(
                    db,
                    child.id,
                    "change_set.ready",
                    {"change_set_id": str(change.id), "mode": "voice"},
                )
            parent.execution_lease = {
                **parent.execution_lease,
                "last_action_turn": turn,
                "last_action_status": status,
                "last_action_binding": event_binding,
                "last_action_receipt": str(receipt["id"]) if receipt else None,
                "voice_receipt_refs": (
                    [
                        *parent.execution_lease.get("voice_receipt_refs", ())[-19:],
                        receipt_ref(conversation.id, receipt["id"]),
                    ]
                    if receipt
                    else parent.execution_lease.get("voice_receipt_refs", [])
                ),
                "current_generation": conversation.generation,
                "next_sequence": conversation.next_message_sequence,
            }
            await _append_event(
                db,
                parent.id,
                "voice.action",
                {
                    "voice_epoch": epoch,
                    "turn": turn,
                    "tool_call_ids": list(binding.call_ids),
                    "audio_start_ms": binding.start_ms,
                    "audio_end_ms": binding.end_ms,
                    "binding": event_binding,
                    "status": status,
                    "target_count": len(plan.entries) if tool == COLLECTION_TOOL else 1,
                },
            )
            if not is_active() or parent.deadline <= datetime.now(UTC):
                return VoiceActionOutcome("rejected", "voice_turn_expired")
            try:
                await db.commit()
            except Exception:
                # Commit response loss is indeterminate. The frozen receipt is
                # the only recovery authority; do not re-execute the request.
                return VoiceActionOutcome("rejected", "voice_result_ambiguous")
            identity = receipt["id"] if receipt else None
            return committed(
                status,
                receipt_id=identity,
                receipt_ref=receipt_ref(conversation.id, identity) if identity else None,
            )
