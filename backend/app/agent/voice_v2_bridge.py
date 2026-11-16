"""A single browser/mic lease over bounded Google Live transport epochs."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from collections import Counter, deque
from contextlib import AsyncExitStack, suppress
from copy import deepcopy
from datetime import UTC, datetime

from fastapi import HTTPException
from starlette.websockets import WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from app.agent import voice_bridge
from app.agent.voice_protocol import (
    MAX_CHUNK_BYTES,
    MAX_PENDING,
    MAX_TRANSCRIPT_BYTES,
    VoiceError,
    encoded,
    pcm,
    server_event,
)
from app.agent.voice_v2_intent import SAMPLE_RATE, SignalWindow, SpeechWindow
from app.agent.voice_v2_outcome import VoiceActionOutcome
from app.agent.voice_v2_protocol import ACTION_TOOLS, v2_tool_request
from app.agent.voice_v2_store import VoiceContextChanged, VoiceSources

MAX_OPEN_ATTEMPTS = 13  # Includes ordinary provider rotation within 90 minutes.
MAX_CONSECUTIVE_FAILURES = 3
MAX_TURNS = 1024
MAX_TOOLS = 2048
MAX_TEXT_BYTES = 2_097_152
MAX_USAGE_SAMPLES = 2048
BACKOFF = (0.15, 0.5, 1.0)
AUTH_WINDOW = 2.5
WATCHDOG_INTERVAL = 0.75
SOURCE_WINDOW = 0.35
SOURCE_WINDOW_BYTES = 16_800
ACTION_SETTLE_SECONDS = 0.18
ACTION_ACTIVITY_WAIT_SECONDS = 2.5
_DROPS = (ConnectionClosed, OSError, TimeoutError)
_active_bridges = {}


def signal_voice_stop(run_id):
    if (bridge := _active_bridges.get(run_id)) is not None:
        bridge._close("voice_stopped")


class _UpstreamDrop(Exception):
    pass


class _LanguageHintRejected(Exception):
    pass


def _is_language_hint_rejection(error):
    close = error.rcvd if isinstance(error, ConnectionClosed) else None
    return (
        close is not None
        and close.code in {1007, 1008}
        and any(field in close.reason.lower() for field in ("languagecodes", "language_codes"))
    )


class VoiceV2Bridge:
    def __init__(self, browser, store):
        self.browser, self.store = browser, store
        self.browser_lock = asyncio.Lock()
        self.provider_lock = asyncio.Lock()
        self.stopping = asyncio.Event()
        self.outbound = asyncio.Queue(maxsize=4)
        self.close_reason = None
        self.ready = self.online = self.muted = False
        self.connected = False
        self.epoch = self.connection_attempts = self.resume_count = 0
        self.deadline = None
        self.started = time.monotonic()
        self.authority_until = 0.0
        self.turn, self.completed_turns = 1, 0
        self.input_bytes = self.output_bytes = self.text_bytes = 0
        self.send_uncertain = False
        self.usage, self.seen = [], set()
        self.handle = None
        self.forwarded_ms = 0
        self.signal = SignalWindow()
        self.native = False
        self.epoch_ambiguous = False
        self.awaiting_provider_boundary = False
        self.hint_fallback_used = False
        self.sources = VoiceSources()
        self.pending_notice = None
        self.deferred_events = deque()
        self.activity_serial = 0
        self.cancelled_ids = set()
        self.socket = None
        self.awaiting_manual = False
        self.last_manual_receipt = None
        self.action_outcomes = Counter()
        self.refresh_context_history = False
        self._clear_turn()

    def _clear_turn(self, *, keep_floor=False):
        self.speech = (
            self.speech.next(self.speech.end_ms or self.forwarded_ms)
            if keep_floor
            else SpeechWindow()
        )
        self.input_text = self.output_text = ""
        self.interrupted = self.output_started = False
        self.egress_checked = False
        self.source_until = 0.0
        self.source_bytes = 0
        self.actions = {}
        self.action_wires = {}
        self.action_deadline = None
        self.action_committing = False
        self.action_cancelled = False
        self.turn_seal = None
        self.provider_turn_complete = False
        self.unbound_action = False

    def _track_input_final(self, item):
        text = item.get("text", "")
        if not isinstance(text, str):
            raise VoiceError("voice_provider_transcript_invalid")
        # Transcription is asynchronous display/history data, never authority.
        return bool(text.strip()) and not self.speech.is_retired(item)

    def _clear_audio(self):
        while not self.outbound.empty():
            self.outbound.get_nowait()

    def _close(self, reason):
        self.close_reason = self.close_reason or reason
        self.online = False
        self.handle = None
        self.pending_notice = None
        self._clear_audio()
        self.stopping.set()
        return self.close_reason

    def _active(self):
        return self.close_reason is None and datetime.now(UTC) < self.deadline

    def _need_active(self):
        if not self._active():
            raise VoiceError(self.close_reason or "voice_time_limit")

    async def browser_send(self, value, *, binary=False, terminal=False):
        async with self.browser_lock:
            if not terminal:
                self._need_active()
            try:
                async with asyncio.timeout(3):
                    if binary:
                        await self.browser.send_bytes(value)
                    else:
                        await self.browser.send_json(value)
            except WebSocketDisconnect, OSError, RuntimeError, TimeoutError:
                raise VoiceError(self._close("voice_browser_disconnected")) from None

    async def receive_browser(self):
        try:
            while self._active():
                event = await self.browser.receive()
                if event["type"] == "websocket.disconnect":
                    return self._close("voice_browser_disconnected")
                data = event.get("bytes")
                if data is not None:
                    if not self.ready:
                        return self._close("voice_audio_before_setup")
                    if not data or len(data) % 2 or len(data) > MAX_CHUNK_BYTES:
                        return self._close("voice_audio_chunk_limit")
                    if not self.muted:
                        self.input_bytes += len(data)
                        if (
                            self.input_bytes
                            > self.store.settings.mimi_voice_v2_max_seconds * 32_000
                            or self.input_bytes > (time.monotonic() - self.started + 2) * 32_000
                        ):
                            return self._close("voice_input_limit")
                        if self.online:
                            if self.outbound.full():
                                self.speech.uncertain = True
                            else:
                                self.outbound.put_nowait(data)
                    continue
                raw = event.get("text")
                if not isinstance(raw, str) or len(raw) > 256:
                    return self._close("voice_browser_message_invalid")
                try:
                    control = json.loads(raw)
                except ValueError:
                    return self._close("voice_browser_message_invalid")
                if control == {"type": "stop"}:
                    return self._close("voice_stopped")
                if control == {"type": "microphone_lost"}:
                    return self._close("voice_microphone_lost")
                if (
                    self.ready
                    and isinstance(control, dict)
                    and set(control) == {"type", "muted"}
                    and control["type"] == "mute"
                    and type(control["muted"]) is bool
                ):
                    self.muted = control["muted"]
                    self.speech.uncertain = True
                    self.action_cancelled = True
                    if self.muted:
                        self._clear_audio()
                        if self.online:
                            self.outbound.put_nowait(b"")
                    await self.browser_send({"type": "muted", "muted": self.muted})
                else:
                    return self._close("voice_browser_message_forbidden")
        except WebSocketDisconnect, OSError, RuntimeError:
            return self._close("voice_browser_disconnected")
        return self._close("voice_time_limit")

    async def _provider_write(self, socket, value, *, mic=False, audio=None, skip_cancelled=False):
        async with self.provider_lock:
            self._need_active()
            if mic and time.monotonic() >= self.authority_until:
                raise VoiceError("voice_authority_expired")
            if audio and self.muted:
                return False
            if skip_cancelled:
                # Check after acquiring the send lock: cancellation may have
                # arrived while the action waited for the lease or this lock.
                responses = [
                    reply
                    for reply in value["toolResponse"]["functionResponses"]
                    if reply["id"] not in self.cancelled_ids
                ]
                if not responses:
                    return False
                value = {"toolResponse": {"functionResponses": responses}}
            try:
                async with asyncio.timeout(3):
                    await socket.send(encoded(value))
                if audio:
                    self.signal.record(audio)
                    self.forwarded_ms = self.signal.total * 1000 // SAMPLE_RATE
            except _DROPS as error:
                if self.ready and _is_language_hint_rejection(error):
                    raise VoiceError("voice_provider_setup_rejected") from None
                self.send_uncertain = True
                if mic:
                    self.action_cancelled = True
                    self.epoch_ambiguous = True
                raise _UpstreamDrop from None
            except asyncio.CancelledError:
                self.send_uncertain = True
                raise
            return True

    async def _provider_read(self, socket):
        try:
            return server_event(await socket.recv())
        except _DROPS as error:
            if self.ready and _is_language_hint_rejection(error):
                raise VoiceError("voice_provider_setup_rejected") from None
            raise _UpstreamDrop from None

    async def _mic_to_provider(self, socket):
        while True:
            data = await self.outbound.get()
            if data:
                if self.muted:
                    continue
                value = {
                    "audio": {
                        "mimeType": "audio/pcm;rate=16000",
                        "data": base64.b64encode(data).decode(),
                    }
                }
            else:
                value = {"audioStreamEnd": True}
            await self._provider_write(socket, {"realtimeInput": value}, mic=True, audio=data)

    async def _tool_response(self, socket, identity, wire, result):
        await self._provider_write(
            socket,
            {
                "toolResponse": {
                    "functionResponses": [
                        {"id": identity, "name": wire, "response": {"result": result}}
                    ]
                }
            },
        )

    async def _tool_calls(self, socket, envelope, *, new_audio):
        calls = envelope.get("functionCalls") if isinstance(envelope, dict) else None
        if not isinstance(calls, list) or not 1 <= len(calls) <= MAX_PENDING:
            raise VoiceError("voice_tool_limit")
        for call in calls:
            identity, wire, name, arguments = v2_tool_request(call, self.store.settings)
            if not new_audio:
                if name in ACTION_TOOLS:
                    self.epoch_ambiguous = True
                    self.handle = None
                continue
            if identity in self.seen:
                # An exact duplicate is inert. Mixed replay/new calls cannot
                # silently apply only the surviving fragment of a request.
                if self.speech.start_ms is not None or len(calls) > 1 or self.actions:
                    self.action_cancelled = True
                continue
            if identity in self.cancelled_ids:
                self.epoch_ambiguous = True
                self.action_cancelled = True
                self.seen.add(identity)
                continue
            if len(self.seen) >= MAX_TOOLS:
                raise VoiceError("voice_tool_limit")
            self.seen.add(identity)
            self.handle = None  # Never resume a checkpoint preceding a tool exchange.
            if name in ACTION_TOOLS:
                if self.native and self.speech.start_ms is None:
                    # Native checkpoints can replay an old function call before
                    # any new VAD. This makes even a first-unseen call later
                    # in this epoch ambiguous; keep reads available.
                    self.epoch_ambiguous = True
                    continue
                if len(self.actions) >= MAX_PENDING:
                    raise VoiceError("voice_tool_limit")
                self.actions[identity] = (name, arguments)
                if self.speech.start_ms is None:
                    # Never assign an earlier tool call to a later utterance.
                    self.unbound_action = True
                if self.provider_turn_complete:
                    self.action_cancelled = True
                self.action_wires[identity] = wire
                self.action_deadline = self.action_deadline or (
                    time.monotonic() + ACTION_ACTIVITY_WAIT_SECONDS
                )
                self._arm_action()
            else:
                async with (
                    asyncio.timeout(5),
                    self.store.deliver_read(
                        hashlib.sha256(identity.encode()).hexdigest(),
                        name,
                        arguments,
                        self.epoch,
                        self.sources,
                    ) as (result, updated),
                ):
                    await self._tool_response(socket, identity, wire, result)
                self.sources = updated
                self.egress_checked = False

    def _arm_action(self):
        # BLOCKING tools may wait for our result before turnComplete. VAD end
        # closes user input; a short event settle window admits cancellation.
        if self.actions and (
            self.speech.end_ms is not None or self.action_cancelled or self.provider_turn_complete
        ):
            now = time.monotonic()
            self.action_deadline = self.action_deadline or now + ACTION_ACTIVITY_WAIT_SECONDS
            self.turn_seal = min(
                self.turn_seal or self.action_deadline,
                self.action_deadline,
                now + ACTION_SETTLE_SECONDS,
            )

    def _cancellations(self, envelope):
        ids = envelope.get("ids") if isinstance(envelope, dict) else None
        if (
            not isinstance(ids, list)
            or len(ids) > MAX_TOOLS
            or any(not isinstance(identity, str) or len(identity) > 160 for identity in ids)
        ):
            raise VoiceError("voice_cancellation_invalid")
        if any(identity not in self.seen or identity in self.actions for identity in ids):
            self.epoch_ambiguous = True
        self.cancelled_ids.update(ids)
        if len(self.cancelled_ids) > MAX_TOOLS:
            raise VoiceError("voice_cancellation_invalid")
        for identity in ids:
            if identity in self.actions:
                # Do not apply the surviving fragment of a cancelled intent.
                self.action_cancelled = True
        self._arm_action()
        self.handle = None

    def _clean_checkpoint(self):
        return not (
            self.epoch_ambiguous
            or self.awaiting_provider_boundary
            or self.pending_notice is not None
            or self.speech.start_ms is not None
            or self.input_text
            or self.output_started
            or self.actions
            or self.interrupted
        )

    def _resumption_update(self, value):
        # A false/malformed/newer unusable update explicitly retires the old handle.
        handle = value.get("newHandle") if isinstance(value, dict) else None
        self.handle = (
            handle
            if isinstance(handle, str)
            and 0 < len(handle) <= 4096
            and value.get("resumable") is True
            and self._clean_checkpoint()
            else None
        )

    @staticmethod
    def _caption(value, previous):
        if not isinstance(value, dict) or not isinstance(value.get("text", ""), str):
            raise VoiceError("voice_provider_transcript_invalid")
        text = previous + value.get("text", "")
        if len(text.encode()) > MAX_TRANSCRIPT_BYTES:
            raise VoiceError("voice_transcript_limit")
        return text

    async def _save_turn(self, *, partial):
        if not self.input_text.strip() and not self.output_text.strip():
            return False
        if self.turn > MAX_TURNS:
            raise VoiceError("voice_turn_limit")
        self.text_bytes += len((self.input_text + self.output_text).encode())
        if self.text_bytes > MAX_TEXT_BYTES:
            raise VoiceError("voice_transcript_limit")
        await self.store.transcript(
            self.turn, self.input_text, self.output_text, partial=partial, sources=self.sources
        )
        await self.browser_send({"type": "transcript_saved", "turn": self.turn, "partial": partial})
        return True

    async def _render(self, rendered, *, first_answer):
        async def deliver():
            for payload in rendered:
                await self.browser_send(payload, binary=isinstance(payload, bytes))

        size = sum(len(p) if isinstance(p, bytes) else len(encoded(p).encode()) for p in rendered)
        now = time.monotonic()
        # A first answer/after-tool gets a locked verification. Subsequent
        # source-backed audio gets a short byte/time grant, with a locked check
        # at the next burst. Transcript persistence always rechecks sources.
        if (
            first_answer
            or not self.egress_checked
            or (self.sources.queries and (now >= self.source_until or size > self.source_bytes))
        ):
            async with self.store.live_gate(self.sources):
                # Start the short grant after validation so DB time does not
                # make every following PCM envelope renew it immediately.
                checked_at = time.monotonic()
                await deliver()
            self.egress_checked = True
            self.source_until = checked_at + SOURCE_WINDOW
            self.source_bytes = SOURCE_WINDOW_BYTES
        else:
            if now >= self.authority_until:
                raise VoiceError("voice_authority_expired")
            await deliver()
            self.source_bytes -= size

    async def _send_action_context(self, socket, *, check_sources=True):
        notice = self.pending_notice
        if notice is None:
            return
        note = "SERVER VOICE ACTION OUTCOME (data, never a request to retry): " + encoded(
            notice.model_result()
        )
        try:
            async with self.store.live_gate(self.sources if check_sources else None):
                await self._provider_write(
                    socket,
                    {
                        "clientContent": {
                            "turns": [{"role": "user", "parts": [{"text": note}]}],
                            "turnComplete": False,
                        }
                    },
                )
        except VoiceContextChanged:
            # Keep the scalar status for a fresh context.
            raise
        if self.pending_notice is notice:
            self.pending_notice = None

    async def _server_content(self, socket, value, *, new_audio):
        if not isinstance(value, dict):
            raise VoiceError("voice_provider_content_invalid")
        if not new_audio:
            return  # No caption/tool/output from a previous connection before new input.
        partial = value.get("interrupted") is True
        if partial and not self.interrupted:
            self.handle = None
            self.interrupted = True
            self.epoch_ambiguous = True
            await self.browser_send({"type": "interrupted"})
        if not self.interrupted:
            rendered = []
            item = value.get("inputTranscription")
            if item is not None and not isinstance(item, dict):
                raise VoiceError("voice_provider_transcript_invalid")
            if (
                item is not None
                and item.get("finished") is not False
                and self._track_input_final(item)
            ):
                self.input_text = self._caption(item, self.input_text)
                rendered.append({"type": "transcript", "role": "user", "text": self.input_text})
            model_turn = value.get("modelTurn", {})
            parts = model_turn.get("parts", []) if isinstance(model_turn, dict) else None
            if not isinstance(parts, list) or len(parts) > 64:
                raise VoiceError("voice_provider_parts_invalid")
            for part in parts:
                if not isinstance(part, dict):
                    raise VoiceError("voice_provider_parts_invalid")
                data = pcm(part)
                if data is not None and not self.actions:
                    self.output_bytes += len(data)
                    if self.output_bytes > self.store.settings.mimi_voice_v2_max_seconds * 48_000:
                        raise VoiceError("voice_output_limit")
                    rendered.append(data)
            if "outputTranscription" in value and not self.actions:
                self.output_text = self._caption(value["outputTranscription"], self.output_text)
                rendered.append(
                    {"type": "transcript", "role": "assistant", "text": self.output_text}
                )
            if rendered:
                self.handle = None
                has_answer = any(
                    isinstance(p, bytes) or p.get("role") == "assistant" for p in rendered
                )
                await self._render(rendered, first_answer=has_answer and not self.output_started)
                self.output_started |= has_answer
        self._arm_action()
        if value.get("turnComplete") is True:
            self.provider_turn_complete = True
            idle = value.get("interactionStatus") in (None, "IDLE")
            if idle:
                self.awaiting_provider_boundary = False
            else:
                self.action_cancelled = True
                self.epoch_ambiguous = True
            if self.actions and not self.interrupted:
                self._arm_action()
            else:
                await self._complete_turn(socket)

    async def _complete_turn(self, socket):
        binding = self.speech.bind(self.epoch, self.turn, self.actions)
        turn, epoch, serial = self.turn, self.epoch, self.activity_serial
        if self.speech.start_ms is not None and (
            self.speech.end_ms is None or self.speech.uncertain
        ):
            self.epoch_ambiguous = True
        # The tool call carries no provider audio-turn ID. Never promote a
        # previously tainted epoch merely because an unseen ID arrives.
        ambiguous_at_entry = self.epoch_ambiguous or self.unbound_action
        try:
            saved = await self._save_turn(partial=self.interrupted)
        except VoiceContextChanged:
            if self.actions:
                outcome = VoiceActionOutcome("rejected", "voice_source_changed", reset_context=True)
                self.handle = None
                self.pending_notice = outcome
                self.refresh_context_history = True
                await self.browser_send(outcome.event())
                await self.browser_send({"type": "turn_complete", "interrupted": True})
            raise
        outcome = None
        if self.actions:
            self.awaiting_provider_boundary |= not self.provider_turn_complete
            if (
                binding is None
                or ambiguous_at_entry
                or not self.speech.has_signal(self.signal)
                or self.interrupted
                or self.action_cancelled
                or self.speech.conflicted
                or self.muted
            ):
                outcome = VoiceActionOutcome(
                    "needs_clarification",
                    "voice_spoken_intent_unproven",
                    reset_context=self.epoch_ambiguous,
                )
            else:
                if not saved:
                    # Allocate a durable turn even when Gemini emits no caption.
                    await self.store.transcript(
                        self.turn, "", "", partial=False, sources=self.sources
                    )
                    saved = True
                outcome = await self.store.act(
                    self.turn,
                    self.epoch,
                    tuple(self.actions.values()),
                    binding,
                    self.sources,
                    lambda: (
                        self._active()
                        and not self.muted
                        and not self.action_cancelled
                        and not self.interrupted
                        and not self.speech.uncertain
                        and self.speech.has_signal(self.signal)
                        and not self.epoch_ambiguous
                        and self.turn == turn
                        and self.epoch == epoch
                        and self.activity_serial == serial
                    ),
                )
        responses = [(identity, self.action_wires[identity]) for identity in self.actions]
        if saved or self.actions:
            self.turn += 1
        self.completed_turns += int(
            not self.interrupted
            and (
                self.output_started
                or (
                    outcome is not None
                    and outcome.status
                    in {
                        "applied",
                        "undone",
                        "preview",
                    }
                )
            )
        )
        interrupted = self.interrupted
        self._clear_turn(keep_floor=True)
        if outcome is not None:
            self.action_outcomes[outcome.reason] += 1
            durable = outcome.status in {"applied", "undone", "preview"}
            if durable:
                # Hold the scalar truth before any socket await. If a result
                # cannot be delivered, the fresh context needs this status.
                self.pending_notice = outcome
            if outcome.status == "unknown":
                # The browser's terminal path already refreshes saved results.
                # A rejected action event would briefly claim "not applied".
                raise VoiceError("voice_action_outcome_unknown")
            self.awaiting_manual |= outcome.status == "preview"
            await self.browser_send(outcome.event())
            if outcome.reset_context:
                # Send the clarification to the current tool when safe, then
                # retire this context before accepting another proposal.
                self.refresh_context_history = True
            # A status result crosses no stale plaintext. If our own commit
            # invalidates prior tool facts, retire that model context and send
            # only a scalar outcome on the fresh connection.
            response_sent = False
            async with self.store.live_gate():
                if responses:
                    result = outcome.model_result()
                    response_sent = await self._provider_write(
                        socket,
                        {
                            "toolResponse": {
                                "functionResponses": [
                                    {"id": identity, "name": wire, "response": {"result": result}}
                                    for identity, wire in responses
                                ]
                            }
                        },
                        skip_cancelled=True,
                    )
            try:
                async with self.store.live_gate(self.sources, detail=True):
                    pass
                # A late cancel may retire the call after COMMIT submission.
                # Deliver its durable result as status on a fresh context.
                if outcome.reset_context or (durable and not response_sent):
                    raise VoiceContextChanged()
            except VoiceContextChanged:
                self.pending_notice = outcome
                self.refresh_context_history = True
                await self.browser_send({"type": "turn_complete", "interrupted": interrupted})
                raise
            if self.pending_notice is outcome:
                self.pending_notice = None
        await self.browser_send({"type": "turn_complete", "interrupted": interrupted})

    async def _complete_with_live_events(self, socket):
        """Keep receiving cancellation/barge-in during transaction awaits.

        Original content stays frozen until that action finishes. New speech
        events are processed as the next utterance, never swallowed by the
        previous turn's transcript or reset.
        """
        if not self.actions:
            return await self._complete_turn(socket)
        self.action_committing = True
        finishing = asyncio.create_task(self._complete_turn(socket))
        receiving = None
        try:
            while not finishing.done():
                receiving = asyncio.create_task(self._provider_read(socket))
                await asyncio.wait((finishing, receiving), return_when=asyncio.FIRST_COMPLETED)
                if receiving.done():
                    try:
                        event = receiving.result()
                    except _UpstreamDrop:
                        self.action_cancelled = True
                        # Let the transaction unwind/reconcile its own commit.
                        # The durable outcome, if already committed, stays true.
                        await finishing
                        raise
                    if len(self.deferred_events) >= 64:
                        raise VoiceError("voice_action_input_queue_limit")
                    self.deferred_events.append(event)
                    receiving = None
                    if self.action_committing and (
                        event.get("voiceActivity", {}).get("type") == "ACTIVITY_START"
                        or "toolCall" in event
                        or "goAway" in event
                        or event.get("serverContent", {}).get("interrupted") is True
                    ):
                        self.action_cancelled = True
                        self.epoch_ambiguous = True
                    if "toolCallCancellation" in event:
                        self._cancellations(event["toolCallCancellation"])
                    content = event.get("serverContent")
                    if (
                        self.action_committing
                        and isinstance(content, dict)
                        and content.get("interrupted") is True
                        and not self.interrupted
                    ):
                        self.interrupted = True
                        await self.browser_send({"type": "interrupted"})
            return await finishing
        finally:
            if receiving is not None:
                receiving.cancel()
                await asyncio.gather(receiving, return_exceptions=True)
            if not finishing.done():
                finishing.cancel()
            await asyncio.gather(finishing, return_exceptions=True)

    async def _upstream_messages(self, socket, audio_floor):
        while True:
            if self.deferred_events:
                event = self.deferred_events.popleft()
                await self._process_upstream_event(socket, event, audio_floor)
                continue
            wake = self.turn_seal or self.action_deadline
            if wake is not None:
                remaining = wake - time.monotonic()
                if remaining <= 0:
                    await self._complete_with_live_events(socket)
                    continue
                try:
                    async with asyncio.timeout(remaining):
                        event = await self._provider_read(socket)
                except TimeoutError:
                    await self._complete_with_live_events(socket)
                    continue
            else:
                event = await self._provider_read(socket)
            await self._process_upstream_event(socket, event, audio_floor)

    async def _process_upstream_event(self, socket, event, audio_floor):
        new_audio = self.forwarded_ms > audio_floor
        if "usageMetadata" in event:
            if len(self.usage) >= MAX_USAGE_SAMPLES:
                raise VoiceError("voice_usage_limit")
            self.usage.append(voice_bridge.usage_sample(event["usageMetadata"]))
        if "voiceActivity" in event and new_audio:
            activity = event["voiceActivity"]
            if (
                self.actions
                and self.speech.end_ms is not None
                and isinstance(activity, dict)
                and activity.get("type") == "ACTIVITY_START"
            ):
                self.action_cancelled = True
                self.interrupted = True
                self.epoch_ambiguous = True
                await self.browser_send({"type": "interrupted"})
                await self._complete_turn(socket)
            if isinstance(activity, dict) and activity.get("type") == "ACTIVITY_START":
                self.activity_serial += 1
                if self.awaiting_provider_boundary or self.speech.start_ms is not None:
                    self.epoch_ambiguous = True
            self.speech.activity(activity, self.forwarded_ms)
            if self.speech.conflicted:
                self.epoch_ambiguous = True
            self._arm_action()
            self.handle = None
        if "toolCallCancellation" in event:
            self._cancellations(event["toolCallCancellation"])
        if "toolCall" in event and (new_audio or self.native):
            await self._tool_calls(socket, event["toolCall"], new_audio=new_audio)
        if "serverContent" in event:
            await self._server_content(socket, event["serverContent"], new_audio=new_audio)
        if "sessionResumptionUpdate" in event:
            self._resumption_update(event["sessionResumptionUpdate"])
        if "goAway" in event:
            raise _UpstreamDrop

    async def _transport(self, config, seed, handle):
        self.deferred_events.clear()
        self.native = handle is not None
        if not self.native:
            self.forwarded_ms = 0
            self.sources = VoiceSources()
            # Fresh sockets get a new audio timeline and no old authority.
            self.epoch_ambiguous = False
        self.signal = SignalWindow(self.signal.total if self.native else 0)
        self.awaiting_provider_boundary = False
        floor = self.forwarded_ms
        self._clear_turn()
        if self.native:
            self.speech.floor_ms = floor
        setup = deepcopy(config)
        if self.native:
            setup["setup"]["sessionResumption"] = {"handle": handle}
        if seed is None:
            setup["setup"].pop("historyConfig", None)
        async with AsyncExitStack() as stack:
            try:
                # No dial, handle or seed crosses a revoked lease or source lock.
                async with self.store.live_gate(self.sources, detail=True):
                    self._need_active()
                    if self.ready and self.muted:
                        raise VoiceError("voice_provider_disconnected")
                    socket = await stack.enter_async_context(
                        voice_bridge.connect_provider(self.store.settings, run_id=self.store.run_id)
                    )
                    await self._provider_write(socket, setup)
                try:
                    raw = await asyncio.wait_for(socket.recv(), timeout=10)
                except ConnectionClosed as error:
                    close = error.rcvd
                    if close is not None and close.code in {1007, 1008}:
                        hint = (
                            setup["setup"].get("inputAudioTranscription", {}).get("languageCodes")
                        )
                        if (
                            not self.ready
                            and hint
                            and not self.hint_fallback_used
                            and _is_language_hint_rejection(error)
                        ):
                            raise _LanguageHintRejected from None
                        raise VoiceError("voice_provider_setup_rejected") from None
                    raise
                event = server_event(raw)
            except _DROPS:
                raise _UpstreamDrop from None
            if not isinstance(event.get("setupComplete"), dict):
                raise VoiceError("voice_provider_setup_rejected")
            if "sessionResumptionUpdate" in event:
                self._resumption_update(event["sessionResumptionUpdate"])
            if seed is not None:
                async with self.store.live_gate(self.sources, detail=True):
                    await self._provider_write(socket, seed)
            if self.pending_notice is not None:
                await self._send_action_context(socket, check_sources=False)
            first = not self.ready
            self.connected = True
            await self.store.event(
                "voice.connected" if first else "voice.resumed",
                {"transport": "google_live", "epoch": self.epoch, "context_retained": self.native},
            )
            async with self.store.live_gate():
                self._need_active()
                self.authority_until = time.monotonic() + AUTH_WINDOW
            self.socket = socket
            self.ready = self.online = True
            if not first:
                self.resume_count += 1
            await self.browser_send(
                {
                    "type": "ready",
                    "run_id": str(self.store.run_id),
                    "deadline": self.deadline.isoformat(),
                }
                if first
                else {"type": "resumed", "context_retained": self.native}
            )
            jobs = [
                asyncio.create_task(self._mic_to_provider(socket)),
                asyncio.create_task(self._upstream_messages(socket, floor)),
            ]
            try:
                await asyncio.wait(jobs, return_when=asyncio.FIRST_COMPLETED)
                for job in jobs:
                    if job.done():
                        job.result()
            finally:
                self.socket = None
                self.online = False
                self._clear_audio()
                for job in jobs:
                    job.cancel()
                await asyncio.gather(*jobs, return_exceptions=True)

    async def connect_loop(self, config, seed):
        self._need_active()
        await self.store.dispatched()
        failures = 0
        while self.connection_attempts < MAX_OPEN_ATTEMPTS:
            self._need_active()
            old_turns = self.completed_turns
            self.connection_attempts += 1
            self.epoch += 1
            handle, self.handle = self.handle, None
            try:
                epoch_config, epoch_seed = config, seed if not self.ready else None
                if handle is None and self.refresh_context_history:
                    self.refresh_context_history = False
                    if refresh := getattr(self.store, "fresh_history", None):
                        epoch_config, epoch_seed = await refresh(config)
                await self._transport(epoch_config, epoch_seed, handle)
            except _LanguageHintRejected:
                self.hint_fallback_used = True
                config = deepcopy(config)
                config["setup"]["inputAudioTranscription"] = {}
                await self.store.event("voice.language_hint_fallback", {"epoch": self.epoch})
                continue
            except VoiceContextChanged:
                self.handle = None  # Never send a handle with now-revoked context.
            except (_UpstreamDrop, *_DROPS):
                if self.pending_notice is not None:
                    self.handle = None
                    self.refresh_context_history = True
                if self.muted:
                    return "voice_provider_disconnected"
                if self.input_text or self.output_text:
                    try:
                        if await self._save_turn(partial=True):
                            self.turn += 1
                    except VoiceContextChanged:
                        self.handle = None
                if self.actions:
                    await self.browser_send(
                        VoiceActionOutcome("rejected", "voice_turn_expired").event()
                    )
            if self.close_reason is not None:
                return self.close_reason
            failures = 1 if self.completed_turns > old_turns else failures + 1
            if failures >= MAX_CONSECUTIVE_FAILURES:
                break
            # Reconnecting clears playback, but does not end or restart the mic.
            if self.ready:
                await self.browser_send({"type": "interrupted"})
                await self.browser_send({"type": "reconnecting"})
            await asyncio.sleep(BACKOFF[failures - 1])
        return "voice_provider_disconnected"

    async def _manual_status(self):
        read_status = getattr(self.store, "action_status", None)
        if read_status is None or not self.awaiting_manual or not self.online or self.actions:
            return
        outcome = await read_status()
        if outcome is None or outcome.receipt_id == self.last_manual_receipt or self.actions:
            return
        # Only a receipt observable in a new transaction reaches this channel.
        self.last_manual_receipt = outcome.receipt_id
        self.awaiting_manual = False
        self.pending_notice = outcome
        await self.browser_send(outcome.event())
        if self.socket is not None:
            try:
                await self._send_action_context(self.socket, check_sources=False)
            except _UpstreamDrop:
                # The transport reader owns reconnect; don't retry this send
                # if the wire acknowledgement was lost.
                self.refresh_context_history = True

    async def watchdog(self):
        while True:
            await asyncio.sleep(WATCHDOG_INTERVAL)
            observed_at = time.monotonic()
            try:
                async with asyncio.timeout(AUTH_WINDOW):
                    async with self.store.live_gate():
                        self._need_active()
                        self.authority_until = observed_at + AUTH_WINDOW
                    await self._manual_status()
            except TimeoutError:
                raise VoiceError("voice_authority_expired") from None

    async def run(self, config, seed, deadline):
        self.deadline = deadline
        remaining = max(0, (deadline - datetime.now(UTC)).total_seconds())
        jobs = []
        _active_bridges[self.store.run_id] = self
        try:
            async with asyncio.timeout(remaining):
                jobs = [
                    asyncio.create_task(self.receive_browser()),
                    asyncio.create_task(self.watchdog()),
                    asyncio.create_task(self.connect_loop(config, seed)),
                    asyncio.create_task(self.stopping.wait()),
                ]
                await asyncio.wait(jobs, return_when=asyncio.FIRST_COMPLETED)
                for job in jobs:
                    if job.done():
                        self._close(job.result() or "voice_server_stopped")
                        break
        except TimeoutError:
            self._close("voice_time_limit")
        except asyncio.CancelledError:
            self._close("voice_server_stopped")
        except VoiceError as error:
            self._close(str(error))
        except HTTPException:
            self._close("voice_conversation_changed_or_expired")
        except Exception:
            self._close("voice_server_error")
        finally:
            reason = self.close_reason or self._close("voice_server_stopped")
            _active_bridges.pop(self.store.run_id, None)
            for job in jobs:
                job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)
            # Save no unfinished turn after a revoked source/session/lease.
            if reason in {"voice_stopped", "voice_browser_disconnected", "voice_microphone_lost"}:
                if self.input_text.strip() or self.output_text.strip():
                    with suppress(Exception), asyncio.timeout(3):
                        await self.store.transcript(
                            self.turn,
                            self.input_text,
                            self.output_text,
                            partial=True,
                            sources=self.sources,
                        )
            async with asyncio.timeout(5):
                await self.store.finish(
                    reason=reason,
                    connected=self.connected,
                    completed_turns=self.completed_turns,
                    usage=self.usage,
                    counters={
                        "input_pcm_bytes": self.input_bytes,
                        "output_pcm_bytes": self.output_bytes,
                        "tool_calls": len(self.seen),
                        "action_outcome_reasons": dict(self.action_outcomes),
                        "connection_attempts": self.connection_attempts,
                        "resumes": self.resume_count,
                        "protocol_version": 2,
                        "provider_send_may_have_been_in_flight": self.send_uncertain,
                    },
                )
            with suppress(Exception):
                await self.browser_send({"type": "ended", "reason": reason}, terminal=True)
        return reason
