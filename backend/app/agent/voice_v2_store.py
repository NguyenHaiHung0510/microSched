"""Voice v2 reads, source fences, and typed actions in the existing Mimi store."""

from __future__ import annotations

import json
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
    _add_assistant_message,
    _append_event,
    _confirm_collection,
    _transaction_lock_key,
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
    CALENDAR_READ_TOOLS,
    CalendarBindings,
    calendar_bindings_current,
    calendar_result_bindings,
)
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL, execute_read_tool
from app.agent.voice_preferences import voice_preference
from app.agent.voice_protocol import MAX_TOOL_BYTES, VoiceError, encoded
from app.agent.voice_store import VoiceStore
from app.agent.voice_v2_intent import exact_plan_match, normalized, spoken_creates, spoken_undo
from app.agent.voice_v2_protocol import UNDO_TOOL, VOICE_POLICY, v2_tools
from app.domain.models import Task
from app.domain.tasks import VIETNAM_TZ

MAX_EXPOSED_ROWS = 2048
MAX_QUERY_OBSERVATIONS = 256


class VoiceContextChanged(VoiceError):
    def __init__(self):
        super().__init__("voice_source_changed")


def _read_digest(result):
    value = {k: v for k, v in result.items() if k != "data_as_of"}
    if "groups" in value:
        value["groups"] = sorted(value["groups"], key=lambda g: str(g["value"]))
    return digest(value)


@dataclass
class VoiceSources:
    """What this upstream context has seen; discarded on a fresh context."""

    tasks: dict[UUID, tuple] = field(default_factory=dict)
    calendar: CalendarBindings = field(default_factory=dict)
    queries: dict[str, tuple] = field(default_factory=dict)

    async def check(self, db, settings, *, detail=False):
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
        if detail:
            for name, args, expected in self.queries.values():
                try:
                    result = await execute_read_tool(db, name, args, settings=settings)
                except ValueError:
                    raise VoiceContextChanged() from None
                if _read_digest(result) != expected:
                    raise VoiceContextChanged()

    def plus(self, name, arguments, result):
        tasks, calendar, queries = self.tasks.copy(), self.calendar.copy(), self.queries.copy()
        if result.get("coverage") != "unavailable":
            if name in CALENDAR_READ_TOOLS:
                for key, version in calendar_result_bindings(name, result).items():
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
                expected = _read_digest(result)
                if queries.setdefault(key, (name, arguments, expected))[2] != expected:
                    raise VoiceContextChanged()
        if len(tasks) + len(calendar) > MAX_EXPOSED_ROWS or len(queries) > MAX_QUERY_OBSERVATIONS:
            raise VoiceContextChanged()
        return VoiceSources(tasks, calendar, queries)


def voice_candidate(calls, *, collection_enabled):
    """Coalesce a split proposal into ONE plan, or reject it as unbound."""
    if not calls:
        return None
    candidates, selections = [], set()
    for name, arguments in calls:
        if name == UNDO_TOOL and not arguments and len(calls) == 1 and collection_enabled:
            return UNDO_TOOL, None
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


async def _unique_spoken_targets(db, plan):
    targets = {normalized(e.before["fields"]["title"]): e.id for e in plan.entries if e.before}
    if not targets:
        return True
    # At the decision, every spoken title must uniquely designate the selected
    # STANDARD row. Refuse bounded scans that cannot prove uniqueness.
    rows = (
        await db.execute(
            select(Task.id, Task.title)
            .where(Task.is_private.is_(False), Task.deleted_at.is_(None))
            .limit(10_001)
        )
    ).all()
    return len(rows) <= 10_000 and all(
        [tid for tid, title in rows if normalized(title) == name] == [wanted]
        for name, wanted in targets.items()
    )


class VoiceV2Store(VoiceStore):
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
            await sources.check(db, self.settings, detail=True)
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
                    result = await execute_read_tool(db, name, arguments, settings=self.settings)
            except SelectionCorrection as error:
                result = {"error": error.feedback(), "coverage": "unavailable"}
            except ValueError:
                result = {
                    "error": {"code": "voice_read_arguments_invalid"},
                    "coverage": "unavailable",
                }
            if len(encoded(result).encode()) > MAX_TOOL_BYTES:
                result = {"error": {"code": "voice_result_limit"}, "coverage": "unavailable"}
            updated = sources.plus(name, arguments, result)
            await updated.check(db, self.settings)
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
            yield result, updated
            await _append_event(db, run.id, "voice.tool_sent", {"provider_call_id": identity})
            await db.commit()

    async def _latest_inverse(self, db, conversation, parent, dek):
        # A newer action or a different Voice call must not retarget bare Undo
        # to an older result. Explicit Chat receipt Undo remains available.
        found = (
            await db.execute(
                select(MimiExecutionReceipt, MimiRun)
                .join(MimiChangeSet, MimiChangeSet.id == MimiExecutionReceipt.change_set_id)
                .join(MimiRun, MimiRun.id == MimiChangeSet.run_id)
                .where(MimiRun.conversation_id == conversation.id)
                .order_by(MimiRun.generation.desc(), MimiExecutionReceipt.id.desc())
                .limit(1)
            )
        ).first()
        if not found:
            raise HTTPException(409, "voice_undo_receipt_missing")
        receipt, action_run = found
        if (
            action_run.execution_lease.get("voice_parent_run") != str(parent.id)
            or action_run.execution_lease.get("voice_action_kind") != "applied"
            or receipt.result_ciphertext is None
        ):
            raise HTTPException(409, "voice_undo_latest_receipt_not_eligible")
        recovery = json.loads(
            crypto.open_content(
                dek,
                receipt.result_ciphertext,
                aad=f"mimi-receipt:{conversation.id}:{receipt.id}:recovery",
            )
        )
        return await freeze_undo(db, receipt.id, recovery)

    async def _prepare(self, db, conversation, parent, dek, proposal, epoch):
        tool, args = proposal
        if tool == UNDO_TOOL:
            return COLLECTION_TOOL, await self._latest_inverse(db, conversation, parent, dek)
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

    async def act(self, turn, epoch, calls, speech, transcript, sources, is_active):
        """A complete turn owns one opportunity; domain delta and receipt commit together."""
        try:
            proposal = voice_candidate(
                calls, collection_enabled=self.settings.mimi_collection_enabled
            )
        except ValueError:
            return None
        if proposal is None or not is_active():
            return None
        try:
            return await self._act(turn, epoch, proposal, speech, transcript, sources, is_active)
        except HTTPException as error:
            if error.status_code not in {404, 409, 422}:
                raise
            # Normal stale/selection/undo failures roll back the whole attempt.
            # Source drift is a separate signal and must invalidate native state.
            return None
        except ValueError:
            return None

    async def _act(self, turn, epoch, proposal, speech, transcript, sources, is_active):
        async with self.factory() as db:
            key = f"mimi-voice-v2:{self.run_id}:{turn}"
            # Same ordering as a manual Confirm: key, then conversation/run.
            await db.execute(
                select(func.pg_advisory_xact_lock(_transaction_lock_key("mimi-confirm", key)))
            )
            conversation, parent = await self.boundary(db)
            if not is_active() or turn != parent.execution_lease["last_turn"]:
                return None
            if parent.execution_lease.get("last_action_turn") == turn:
                return parent.execution_lease["last_action_status"]
            if await db.scalar(
                select(MimiExecutionReceipt.id).where(MimiExecutionReceipt.idempotency_key == key)
            ):
                return None
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
                return None
            dek = crypto.unwrap_dek(conversation.dek_wrapped)
            await sources.check(db, self.settings, detail=True)
            today = now.astimezone(VIETNAM_TZ).date()
            named_creates = spoken_creates(speech or transcript, today)
            size = len(proposal[1].entries) if proposal[0] == COLLECTION_TOOL else 1
            if len(named_creates) > 1 and size != len(named_creates):
                return None  # Even a manual preview must not freeze a known fragment.
            tool, plan = await self._prepare(db, conversation, parent, dek, proposal, epoch)
            undo = proposal[0] == UNDO_TOOL
            fast = False
            if tool == COLLECTION_TOOL:
                preference = await voice_preference(db, self.auth, lock=True)
                if undo:
                    fast = (
                        preference.fast_apply
                        and spoken_undo(speech)
                        and all(
                            entry.reminder_effect["action"] in {"keep", "none"}
                            for entry in plan.entries
                        )
                    )
                    if not spoken_undo(speech):
                        return None  # A tool suggestion cannot target an implicit receipt.
                else:
                    fast = (
                        preference.fast_apply
                        and exact_plan_match(speech, plan, today=today)
                        and await _unique_spoken_targets(db, plan)
                    )
            if not is_active():
                return None
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
            if fast:

                async def invalidate(reason):
                    raise HTTPException(409, reason)

                await _confirm_collection(
                    db, self.auth, conversation, child, change, operation, key, dek, invalidate
                )
            else:
                await _add_assistant_message(
                    db,
                    conversation,
                    child.id,
                    dek,
                    "Đã chuẩn bị bản xem trước. Hãy kiểm tra và xác nhận trong ứng dụng.",
                    producer_code="undo_prepared" if undo else "preview_prepared",
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
                "current_generation": conversation.generation,
                "next_sequence": conversation.next_message_sequence,
            }
            if not is_active() or parent.deadline <= datetime.now(UTC):
                return None
            await db.commit()
            return status
