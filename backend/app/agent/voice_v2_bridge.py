"""A single browser/mic lease over bounded Google Live transport epochs."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
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
from app.agent.voice_v2_intent import SpeechWindow
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
ASR_SETTLE_SECONDS = 0.18
_DROPS = (ConnectionClosed, OSError, TimeoutError)
_active_bridges = {}


def signal_voice_stop(run_id):
    if (bridge := _active_bridges.get(run_id)) is not None:
        bridge._close("voice_stopped")


class _UpstreamDrop(Exception):
    pass


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
        self.forwarded_ms = self.forwarded_bytes = 0
        self.native = False
        self.sources = VoiceSources()
        self.pending_notice = None
        self._clear_turn()

    def _clear_turn(self, *, keep_floor=False):
        self.speech = self.speech.next(self.forwarded_ms) if keep_floor else SpeechWindow()
        self.input_text = self.output_text = ""
        self.interrupted = self.generated = self.output_started = False
        self.egress_checked = False
        self.source_until = 0.0
        self.source_bytes = 0
        self.actions = {}
        self.action_cancelled = False
        self.turn_seal = None

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

    async def _provider_write(self, socket, value, *, mic=False):
        async with self.provider_lock:
            self._need_active()
            if mic and time.monotonic() >= self.authority_until:
                raise VoiceError("voice_authority_expired")
            try:
                async with asyncio.timeout(3):
                    await socket.send(encoded(value))
            except _DROPS:
                self.send_uncertain = True
                raise _UpstreamDrop from None
            except asyncio.CancelledError:
                self.send_uncertain = True
                raise

    async def _provider_read(self, socket):
        try:
            return server_event(await socket.recv())
        except _DROPS:
            raise _UpstreamDrop from None

    async def _mic_to_provider(self, socket):
        while True:
            data = await self.outbound.get()
            if data:
                if self.muted:
                    continue
                self.forwarded_bytes += len(data)
                self.forwarded_ms += self.forwarded_bytes // 32
                self.forwarded_bytes %= 32
                value = {
                    "audio": {
                        "mimeType": "audio/pcm;rate=16000",
                        "data": base64.b64encode(data).decode(),
                    }
                }
            else:
                value = {"audioStreamEnd": True}
            await self._provider_write(socket, {"realtimeInput": value}, mic=True)

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

    async def _tool_calls(self, socket, envelope):
        calls = envelope.get("functionCalls") if isinstance(envelope, dict) else None
        if not isinstance(calls, list) or not 1 <= len(calls) <= MAX_PENDING:
            raise VoiceError("voice_tool_limit")
        for call in calls:
            identity, wire, name, arguments = v2_tool_request(call, self.store.settings)
            if identity in self.seen:
                continue
            if len(self.seen) >= MAX_TOOLS:
                raise VoiceError("voice_tool_limit")
            self.seen.add(identity)
            self.handle = None  # Never resume a checkpoint preceding a tool exchange.
            if name in ACTION_TOOLS:
                if len(self.actions) >= MAX_PENDING:
                    raise VoiceError("voice_tool_limit")
                self.actions[identity] = (name, arguments)
                if self.turn_seal is not None:
                    self.action_cancelled = True
                async with self.store.live_gate(self.sources):
                    await self._tool_response(
                        socket,
                        identity,
                        wire,
                        {"state": "proposal_staged", "applied": False, "final": False},
                    )
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

    def _cancellations(self, envelope):
        ids = envelope.get("ids") if isinstance(envelope, dict) else None
        if (
            not isinstance(ids, list)
            or len(ids) > MAX_TOOLS
            or any(not isinstance(identity, str) or len(identity) > 160 for identity in ids)
        ):
            raise VoiceError("voice_cancellation_invalid")
        for identity in ids:
            if identity in self.actions:
                # Do not apply the surviving fragment of a cancelled intent.
                self.action_cancelled = True
        self.handle = None

    def _clean_checkpoint(self):
        return not (
            self.speech.start_ms is not None
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
        notice, self.pending_notice = self.pending_notice, None
        if notice is None:
            return
        note = "SERVER VOICE ACTION OUTCOME (data, never a request to retry): " + encoded(
            {"status": notice.status, "reason": notice.reason}
        )
        try:
            async with self.store.live_gate(self.sources if check_sources else None):
                await self._provider_write(
                    socket,
                    {
                        "clientContent": {
                            "turns": [{"role": "model", "parts": [{"text": note}]}],
                            "turnComplete": False,
                        }
                    },
                )
        except VoiceContextChanged:
            # This scalar notice has no original source content and was not
            # sent; it may be delivered once on a fresh upstream.
            self.pending_notice = notice
            raise

    async def _action_outcome(self, socket, outcome):
        if outcome.reason == "voice_result_ambiguous":
            raise VoiceError("voice_action_outcome_unknown")
        self.pending_notice = outcome
        self.handle = None
        if outcome.reset_context:
            raise VoiceContextChanged()
        await self._send_action_context(socket)

    async def _server_content(self, socket, value, *, new_audio):
        if not isinstance(value, dict):
            raise VoiceError("voice_provider_content_invalid")
        if not new_audio:
            return  # No caption/tool/output from a previous connection before new input.
        partial = value.get("interrupted") is True
        if partial and not self.interrupted:
            self.handle = None
            self.interrupted = True
            await self.browser_send({"type": "interrupted"})
        if not self.interrupted:
            rendered = []
            item = value.get("inputTranscription")
            if item is not None and not self.speech.is_retired(item):
                self.input_text = self._caption(item, self.input_text)
                self.speech.transcript(item, self.forwarded_ms)
                rendered.append({"type": "transcript", "role": "user", "text": self.input_text})
            model_turn = value.get("modelTurn", {})
            parts = model_turn.get("parts", []) if isinstance(model_turn, dict) else None
            if not isinstance(parts, list) or len(parts) > 64:
                raise VoiceError("voice_provider_parts_invalid")
            for part in parts:
                if not isinstance(part, dict):
                    raise VoiceError("voice_provider_parts_invalid")
                data = pcm(part)
                if data is not None:
                    self.output_bytes += len(data)
                    if self.output_bytes > self.store.settings.mimi_voice_v2_max_seconds * 48_000:
                        raise VoiceError("voice_output_limit")
                    rendered.append(data)
            if "outputTranscription" in value:
                self.output_text = self._caption(value["outputTranscription"], self.output_text)
                rendered.append(
                    {"type": "transcript", "role": "assistant", "text": self.output_text}
                )
            if rendered and (not self.native or self.speech.start_ms is not None):
                self.handle = None
                has_answer = any(
                    isinstance(p, bytes) or p.get("role") == "assistant" for p in rendered
                )
                await self._render(rendered, first_answer=has_answer and not self.output_started)
                self.output_started |= has_answer
            if value.get("generationComplete") is True:
                self.generated = True
        if value.get("turnComplete") is True:
            if value.get("interactionStatus") not in (None, "IDLE"):
                self.action_cancelled = True
            if self.actions and not self.interrupted:
                # ASR is delivered independently. Let trailing fragments arrive
                # before the transaction, but never wait indefinitely or retry.
                self.turn_seal = self.turn_seal or time.monotonic() + ASR_SETTLE_SECONDS
            else:
                await self._complete_turn(socket)

    async def _complete_turn(self, socket):
        spoken = self.speech.prove()
        if self.native and spoken is None:
            if self.actions:
                outcome = VoiceActionOutcome(
                    "needs_clarification", "voice_spoken_intent_unproven", reset_context=True
                )
                await self.browser_send(outcome.event())
                await self.browser_send({"type": "turn_complete", "interrupted": True})
                await self._action_outcome(socket, outcome)
            raise VoiceContextChanged()
        try:
            saved = await self._save_turn(partial=self.interrupted)
        except VoiceContextChanged:
            if self.actions:
                outcome = VoiceActionOutcome("rejected", "voice_source_changed", reset_context=True)
                await self.browser_send(outcome.event())
                await self.browser_send({"type": "turn_complete", "interrupted": True})
                await self._action_outcome(socket, outcome)
            raise
        outcome = None
        if self.actions:
            if (
                not saved
                or not self.input_text.strip()
                or self.interrupted
                or self.action_cancelled
                or self.speech.conflicted
                or self.muted
            ):
                outcome = VoiceActionOutcome("needs_clarification", "voice_spoken_intent_unproven")
            else:
                outcome = await self.store.act(
                    self.turn,
                    self.epoch,
                    tuple(self.actions.values()),
                    spoken if self.generated else None,
                    self.input_text,
                    self.sources,
                    lambda: self._active() and not self.muted,
                )
        if saved:
            self.turn += 1
        self.completed_turns += int(self.output_started and not self.interrupted)
        interrupted = self.interrupted
        self._clear_turn(keep_floor=True)
        if outcome is not None:
            await self.browser_send(outcome.event())
        await self.browser_send({"type": "turn_complete", "interrupted": interrupted})
        if outcome is not None:
            await self._action_outcome(socket, outcome)

    async def _upstream_messages(self, socket, audio_floor):
        while True:
            if self.turn_seal is not None:
                remaining = self.turn_seal - time.monotonic()
                if remaining <= 0:
                    await self._complete_turn(socket)
                    continue
                try:
                    async with asyncio.timeout(remaining):
                        event = await self._provider_read(socket)
                except TimeoutError:
                    await self._complete_turn(socket)
                    continue
            else:
                event = await self._provider_read(socket)
            new_audio = self.forwarded_ms > audio_floor
            if "usageMetadata" in event:
                if len(self.usage) >= MAX_USAGE_SAMPLES:
                    raise VoiceError("voice_usage_limit")
                self.usage.append(voice_bridge.usage_sample(event["usageMetadata"]))
            if "voiceActivity" in event and new_audio:
                if self.turn_seal is not None:
                    self.action_cancelled = True
                self.speech.activity(event["voiceActivity"], self.forwarded_ms)
                self.handle = None
            if "toolCallCancellation" in event:
                self._cancellations(event["toolCallCancellation"])
            if (
                "toolCall" in event
                and new_audio
                and (not self.native or self.speech.start_ms is not None)
            ):
                await self._tool_calls(socket, event["toolCall"])
            if "serverContent" in event:
                await self._server_content(socket, event["serverContent"], new_audio=new_audio)
            if "sessionResumptionUpdate" in event:
                self._resumption_update(event["sessionResumptionUpdate"])
            if "goAway" in event:
                raise _UpstreamDrop

    async def _transport(self, config, seed, handle):
        self.native = handle is not None
        if not self.native:
            self.forwarded_ms = self.forwarded_bytes = 0
            self.sources = VoiceSources()
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
                event = await asyncio.wait_for(self._provider_read(socket), timeout=10)
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
                await self._transport(config, seed if self.epoch == 1 else None, handle)
            except VoiceContextChanged:
                self.handle = None  # Never send a handle with now-revoked context.
            except (_UpstreamDrop, *_DROPS):
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

    async def watchdog(self):
        while True:
            await asyncio.sleep(WATCHDOG_INTERVAL)
            observed_at = time.monotonic()
            try:
                async with asyncio.timeout(AUTH_WINDOW):
                    async with self.store.live_gate():
                        self._need_active()
                        self.authority_until = observed_at + AUTH_WINDOW
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
                        "connection_attempts": self.connection_attempts,
                        "resumes": self.resume_count,
                        "protocol_version": 2,
                        "provider_send_may_have_been_in_flight": self.send_uncertain,
                    },
                )
            with suppress(Exception):
                await self.browser_send({"type": "ended", "reason": reason}, terminal=True)
        return reason
