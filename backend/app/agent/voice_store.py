"""Short transactions for same-conversation voice. No PCM or browser prose is stored."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

from fastapi import HTTPException
from sqlalchemy import select

from app.agent import crypto
from app.agent.models import MimiChangeSet, MimiEvent, MimiMessage, MimiProviderCall, MimiRun
from app.agent.service import (
    _add_assistant_message,
    _append_event,
    _canonical_digest,
    _conversation,
    _provider_history,
)
from app.agent.tools.calendar_reads import calendar_pairs_current, execute_calendar_tool
from app.agent.voice_protocol import (
    MAX_CONTEXT_BYTES,
    MAX_TOOL_BYTES,
    MODEL,
    TICKET_SECONDS,
    TOOL_NAMES,
    VoiceError,
    encoded,
    setup,
)
from app.domain.models import AuthSession
from app.domain.tasks import VIETNAM_TZ

ACTIVE = ("accepted", "building", "running", "executing", "waiting_confirmation")


def voice_available(settings) -> bool:
    return bool(
        settings.mimi_voice_enabled
        and settings.mimi_calendar_read_enabled
        and (
            not settings.is_production
            or (settings.mimi_real_chat_enabled and settings.mimi_public_origin)
        )
        and settings.mimi_gemini_api_key
        and settings.mimi_gemini_api_key.get_secret_value().strip()
    )


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value)


async def close_orphaned_voice(db, run, call):
    dispatched = call.state != "intent"
    run.state = "outcome_unknown" if dispatched else "cancelled"
    run.provider_outcome = "unknown" if dispatched else None
    run.error_code = "voice_process_lost" if dispatched else "voice_dispatch_not_started"
    run.completed_at = datetime.now(UTC)
    run.execution_lease = {**run.execution_lease, "ticket_sha256": None, "ticket_used": True}
    call.state = "unknown" if dispatched else "fenced"
    call.result = {
        **(call.result or {}),
        "reason": run.error_code,
        "dispatch_not_started": not dispatched,
    }
    await _append_event(
        db,
        run.id,
        "run.terminal",
        {
            "mode": "voice",
            "state": run.state,
            "error_code": run.error_code,
        },
    )


async def assert_no_active_voice(db, conversation_id):
    rows = await db.scalars(
        select(MimiRun).where(
            MimiRun.conversation_id == conversation_id,
            MimiRun.state.in_(("accepted", "running")),
            MimiRun.execution_lease["mode"].astext == "voice",
        )
    )
    now = datetime.now(UTC)
    for run in rows:
        if run.deadline > now and (
            run.state == "running" or _time(run.execution_lease["ticket_expires_at"]) > now
        ):
            raise HTTPException(status_code=409, detail="finish_voice_before_text")


class VoiceStore:
    def __init__(self, factory, settings, auth, conversation_id: UUID, run_id: UUID):
        self.factory, self.settings, self.auth = factory, settings, auth
        self.conversation_id, self.run_id = conversation_id, run_id

    async def live_auth(self, db, *, lock=False):
        auth = await db.get(
            AuthSession,
            self.auth.id,
            populate_existing=True,
            with_for_update={"read": True} if lock else None,
        )
        if (
            auth is None
            or auth.token_hash != self.auth.token_hash
            or auth.expires_at <= datetime.now(UTC)
        ):
            raise VoiceError("voice_session_expired")
        return auth

    async def boundary(self, db, *, lock=True):
        if not voice_available(self.settings):
            raise VoiceError("voice_unavailable")
        auth = await self.live_auth(db, lock=lock)
        conversation = await _conversation(db, auth, self.conversation_id, lock=lock)
        run = await db.get(MimiRun, self.run_id, with_for_update=lock)
        if (
            run is None
            or run.conversation_id != conversation.id
            or run.execution_lease.get("mode") != "voice"
            or run.execution_lease.get("auth_session_id") != str(auth.id)
            or run.execution_lease.get("stop_requested")
            or run.state not in {"accepted", "running"}
            or run.deadline <= datetime.now(UTC)
            or conversation.is_private
            or conversation.sensitivity != "standard"
            or conversation.archived_at is not None
            or conversation.generation != run.generation + 1
            or conversation.context_frontier_sequence != run.execution_lease["frontier"]
            or conversation.next_message_sequence != run.execution_lease["next_sequence"]
        ):
            raise VoiceError("voice_conversation_changed_or_expired")
        return conversation, run

    async def check(self):
        async with self.factory() as db:
            await self.boundary(db, lock=False)

    @classmethod
    async def mint(cls, db, factory, settings, auth, conversation_id, expected_generation):
        if not voice_available(settings):
            raise HTTPException(404, "voice_unavailable")
        run_id = uuid7()
        store = cls(factory, settings, auth, conversation_id, run_id)
        await store.live_auth(db, lock=True)
        conversation = await _conversation(db, auth, conversation_id, lock=True)
        if (
            conversation.is_private
            or conversation.sensitivity != "standard"
            or conversation.archived_at is not None
            or conversation.generation != expected_generation
        ):
            raise HTTPException(409, "voice_conversation_unavailable")
        now = datetime.now(UTC)
        active = (
            await db.scalars(
                select(MimiRun)
                .where(MimiRun.conversation_id == conversation.id, MimiRun.state.in_(ACTIVE))
                .with_for_update()
            )
        ).all()
        for old in active:
            if old.state == "waiting_confirmation" and not await db.scalar(
                select(MimiChangeSet.id).where(
                    MimiChangeSet.run_id == old.id,
                    MimiChangeSet.state == "pending",
                    MimiChangeSet.expires_at > now,
                )
            ):
                continue
            if old.execution_lease.get("mode") == "voice" and (
                old.deadline <= now
                or (
                    old.state == "accepted"
                    and _time(old.execution_lease["ticket_expires_at"]) <= now
                )
            ):
                call = (
                    await db.scalars(
                        select(MimiProviderCall).where(MimiProviderCall.run_id == old.id)
                    )
                ).one()
                await close_orphaned_voice(db, old, call)
            else:
                raise HTTPException(409, "finish_active_run_before_voice")
        ticket = secrets.token_urlsafe(32)
        run = MimiRun(
            id=run_id,
            conversation_id=conversation.id,
            generation=conversation.generation,
            state="accepted",
            deadline=now + timedelta(seconds=settings.mimi_voice_max_seconds),
            execution_lease={
                "mode": "voice",
                "auth_session_id": str(auth.id),
                "ticket_sha256": hashlib.sha256(ticket.encode()).hexdigest(),
                "ticket_expires_at": (now + timedelta(seconds=TICKET_SECONDS)).isoformat(),
                "ticket_used": False,
                "frontier": conversation.context_frontier_sequence,
                "next_sequence": conversation.next_message_sequence,
                "last_turn": 0,
                "capabilities": sorted(TOOL_NAMES.values()),
                "sensitivity": "standard",
            },
        )
        conversation.generation += 1
        db.add(run)
        await db.flush()
        db.add(
            MimiProviderCall(
                run_id=run.id,
                attempt=1,
                state="intent",
                request_fingerprint="voice_not_dispatched",
                route={
                    "purpose": "main",
                    "transport": "google_live",
                    "model": MODEL,
                    "run_guard_version": 1,
                    "paid_dispatch": False,
                    "dispatch_not_started": True,
                },
            )
        )
        await _append_event(db, run.id, "run.accepted", {"mode": "voice"})
        return {
            "ticket": ticket,
            "run_id": str(run.id),
            "expires_in": TICKET_SECONDS,
            "max_seconds": settings.mimi_voice_max_seconds,
        }

    async def consume(self, ticket: str):
        async with self.factory() as db:
            conversation, run = await self.boundary(db)
            lease = run.execution_lease
            if (
                not isinstance(ticket, str)
                or len(ticket) > 128
                or lease["ticket_used"]
                or _time(lease["ticket_expires_at"]) <= datetime.now(UTC)
                or not hmac.compare_digest(
                    hashlib.sha256(ticket.encode()).hexdigest(), lease.get("ticket_sha256", "")
                )
            ):
                raise VoiceError("voice_ticket_invalid_or_expired")
            history = await _provider_history(
                db, conversation, crypto.unwrap_dek(conversation.dek_wrapped)
            )
            turns = [
                {
                    "role": "model" if m["role"] == "assistant" else "user",
                    "parts": [{"text": m["content"]}],
                }
                for m in history
            ]
            config = setup(datetime.now(VIETNAM_TZ))
            # Bound complete messages only; an oversized recent message stays
            # available in the chat UI but isn't sliced into a misleading quote.
            seed = None
            limited = False
            while turns:
                candidate = {"clientContent": {"turns": turns, "turnComplete": True}}
                if (
                    len(encoded({"setup": config, "history": candidate}).encode()) + 128
                    <= MAX_CONTEXT_BYTES
                ):
                    seed = candidate
                    break
                turns = turns[1:]
                limited = True
            if seed is not None:
                config["setup"]["historyConfig"] = {"initialHistoryInClientContent": True}
            await _append_event(
                db,
                run.id,
                "voice.history",
                {
                    "included_messages": len(turns),
                    "limited_by_voice_bytes": limited,
                },
            )
            run.execution_lease = {**lease, "ticket_used": True, "ticket_sha256": None}
            call = (
                await db.scalars(select(MimiProviderCall).where(MimiProviderCall.run_id == run.id))
            ).one()
            call.request_fingerprint = _canonical_digest({"setup": config, "history": seed})
            await db.commit()
            return config, seed, run.deadline

    async def dispatched(self):
        async with self.factory() as db:
            _, run = await self.boundary(db)
            if not run.execution_lease["ticket_used"] or (
                _time(run.execution_lease["ticket_expires_at"]) <= datetime.now(UTC)
            ):
                raise VoiceError("voice_ticket_required")
            run.state = "running"
            call = (
                await db.scalars(select(MimiProviderCall).where(MimiProviderCall.run_id == run.id))
            ).one()
            if call.state != "intent":
                raise VoiceError("voice_dispatch_already_attempted")
            call.state = "dispatched"
            call.route = {**call.route, "paid_dispatch": True, "dispatch_not_started": False}
            await _append_event(db, run.id, "provider.dispatched", {"transport": "google_live"})
            await db.commit()

    async def event(self, kind, payload):
        async with self.factory() as db:
            await self.boundary(db)
            if kind == "voice.connected":
                call = (
                    await db.scalars(
                        select(MimiProviderCall).where(MimiProviderCall.run_id == self.run_id)
                    )
                ).one()
                call.route = {**call.route, "actual_model": MODEL, "actual_provider": "Google"}
            await _append_event(db, self.run_id, kind, payload)
            await db.commit()

    async def read_tool(self, wire, arguments):
        async with self.factory() as db:
            await self.boundary(db, lock=False)
            try:
                return await execute_calendar_tool(
                    db, TOOL_NAMES[wire], arguments, settings=self.settings
                )
            except ValueError:
                return {"error": {"code": "calendar_arguments_invalid"}, "coverage": "unavailable"}

    async def tool_receipt(self, identity, wire, arguments, result):
        if len(encoded(result).encode()) > MAX_TOOL_BYTES:
            result = {
                "error": {
                    "code": "calendar_voice_result_limit",
                    "message": ("Use fewer days or kinds. No rows or coverage were sent."),
                },
                "coverage": "unavailable",
            }
        canonical = TOOL_NAMES[wire]
        async with self.factory() as db:
            conversation, _ = await self.boundary(db)
            pair = [
                {"tool_calls": [{"function": {"name": canonical}}]},
                {"content": encoded(result)},
            ]
            if not await calendar_pairs_current(db, [pair]):
                result = {
                    "error": {
                        "code": "calendar_source_changed",
                        "message": (
                            "Calendar data changed before delivery. Read it again before answering."
                        ),
                    },
                    "coverage": "unavailable",
                }
            sequence = await _append_event(
                db,
                self.run_id,
                "tool.read_result",
                {
                    "tool": canonical,
                    "provider_call_id": identity,
                    "arguments_sha256": _canonical_digest(arguments),
                    "result_sha256": _canonical_digest(result),
                    "coverage": result.get("coverage"),
                },
            )
            event = (
                await db.scalars(
                    select(MimiEvent).where(
                        MimiEvent.run_id == self.run_id, MimiEvent.sequence == sequence
                    )
                )
            ).one()
            event.payload = {
                **event.payload,
                "body_ciphertext": crypto.seal_content(
                    crypto.unwrap_dek(conversation.dek_wrapped),
                    encoded({"arguments": arguments, "result": result}),
                    aad=crypto.event_content_aad(self.run_id, sequence, "tool.read_result"),
                ),
            }
            await db.commit()
            return result

    async def transcript(self, turn: int, input_text: str, output_text: str, *, partial: bool):
        async with self.factory() as db:
            conversation, run = await self.boundary(db)
            if turn <= run.execution_lease["last_turn"]:
                return  # Idempotent server turn, never a client-selected allocation.
            dek = crypto.unwrap_dek(conversation.dek_wrapped)
            call = (
                await db.scalars(select(MimiProviderCall).where(MimiProviderCall.run_id == run.id))
            ).one()
            call.result = {**(call.result or {}), "transcripts_received": True}
            ids = {}
            if input_text.strip():
                sequence = conversation.next_message_sequence
                message = MimiMessage(
                    id=uuid7(),
                    conversation_id=conversation.id,
                    run_id=run.id,
                    client_id=f"voice:{run.id}:{turn}:input",
                    sequence=sequence,
                    role="user",
                    content_ciphertext=crypto.seal_content(
                        dek, input_text, aad=crypto.message_aad(conversation.id, sequence, "user")
                    ),
                    content_bytes=len(input_text.encode()),
                    content_sha256=hashlib.sha256(input_text.encode()).hexdigest(),
                )
                db.add(message)
                conversation.next_message_sequence += 1
                ids["input_message_id"] = str(message.id)
            if output_text.strip():
                if partial:
                    message = await _add_assistant_message(
                        db,
                        conversation,
                        run.id,
                        dek,
                        output_text,
                        producer_code="provider_voice_partial",
                        provider_call_id=call.id,
                    )
                else:
                    message = await _add_assistant_message(
                        db,
                        conversation,
                        run.id,
                        dek,
                        output_text,
                        producer_code="provider_voice",
                        provider_call_id=call.id,
                    )
                ids["output_message_id"] = str(message.id)
            await _append_event(
                db,
                run.id,
                "voice.transcript",
                {
                    "segment": turn,
                    "partial": partial,
                    "provider_call_id": str(call.id),
                    "input_correlation": "provider_does_not_supply_turn_id",
                    **ids,
                },
            )
            run.execution_lease = {
                **run.execution_lease,
                "last_turn": turn,
                "next_sequence": conversation.next_message_sequence,
            }
            await db.commit()

    async def finish(self, *, reason, connected, completed_turns, usage, counters):
        # Lifecycle is recorded even if auth/frontier has since been revoked. No
        # content is materialized here and no provider operation is authorized.
        async with self.factory() as db:
            run = await db.get(MimiRun, self.run_id, with_for_update=True)
            if run is None or run.execution_lease.get("mode") != "voice":
                return
            call = (
                await db.scalars(select(MimiProviderCall).where(MimiProviderCall.run_id == run.id))
            ).one()
            if run.completed_at is not None:
                return
            dispatched = call.state != "intent"
            succeeded = connected and completed_turns > 0 and reason == "voice_stopped"
            call.state = "succeeded" if succeeded else "unknown" if dispatched else "fenced"
            call.result = {
                **(call.result or {}),
                "reason": reason,
                "connected": connected,
                "completed_turns": completed_turns,
                "dispatch_not_started": not dispatched,
                "actual_model": MODEL if connected else None,
                "actual_provider": "Google" if connected else None,
                **counters,
            }
            call.usage = (
                {
                    "google_live_samples": usage,
                    "semantics": "uninterpreted",
                    "cost_state": "unknown",
                }
                if dispatched
                else None
            )
            run.state = (
                "completed"
                if succeeded
                else "cancelled"
                if not dispatched or reason == "voice_stopped"
                else "outcome_unknown"
            )
            run.provider_outcome = "succeeded" if succeeded else "unknown" if dispatched else None
            run.error_code = None if succeeded else reason
            run.completed_at = datetime.now(UTC)
            run.execution_lease = {
                **run.execution_lease,
                "ticket_sha256": None,
                "ticket_used": True,
            }
            await _append_event(
                db,
                run.id,
                "run.terminal",
                {
                    "state": run.state,
                    "error_code": run.error_code,
                    "mode": "voice",
                    "provider_outcome": run.provider_outcome,
                },
            )
            await db.commit()

    async def stop(self):
        async with self.factory() as db:
            await self.live_auth(db)
            await _conversation(db, self.auth, self.conversation_id, lock=True)
            run = await db.get(MimiRun, self.run_id, with_for_update=True)
            if (
                run is None
                or run.conversation_id != self.conversation_id
                or (
                    run.execution_lease.get("mode") != "voice"
                    or run.execution_lease.get("auth_session_id") != str(self.auth.id)
                )
            ):
                raise HTTPException(404, "voice_session_unavailable")
            run.execution_lease = {
                **run.execution_lease,
                "stop_requested": True,
                "ticket_sha256": None,
                "ticket_used": True,
            }
            await db.commit()
        if run.state == "accepted":
            await self.finish(
                reason="voice_stopped", connected=False, completed_turns=0, usage=[], counters={}
            )
