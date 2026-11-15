"""Continuous PCM bridge; the only injectable seam is the server provider connector."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime

from starlette.websockets import WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import SecurityError

from app.agent.tools.calendar_reads import CalendarBindings
from app.agent.voice_protocol import (
    ENDPOINT,
    MAX_CALLS,
    MAX_CHUNK_BYTES,
    MAX_OUTPUT_BYTES,
    MAX_PENDING,
    MAX_TRANSCRIPT_BYTES,
    MAX_TURNS,
    MAX_WIRE_BYTES,
    VoiceError,
    encoded,
    pcm,
    server_event,
    tool_request,
)


class _FixedEndpointConnect(connect):
    def process_redirect(self, exc):
        return SecurityError("voice_provider_redirect_forbidden")


_wire_logger = logging.Logger("mimi.voice.wire", level=logging.CRITICAL + 1)
_wire_logger.addHandler(logging.NullHandler())


@asynccontextmanager
async def connect_provider(settings, *, run_id):
    """QA monkeypatch: async context factory -> socket.send(str), socket.recv().

    PM can bind its accounting wrapper to run_id. Product never accepts an
    endpoint/key/setup from the browser; the key is header-only and never logged.
    """
    async with _FixedEndpointConnect(
        ENDPOINT,
        additional_headers={"x-goog-api-key": settings.mimi_gemini_api_key.get_secret_value()},
        proxy=None,
        open_timeout=10,
        close_timeout=3,
        max_size=MAX_WIRE_BYTES,
        max_queue=8,
        write_limit=65_536,
        compression=None,
        logger=_wire_logger,
    ) as provider:
        yield provider


def usage_sample(value):
    if not isinstance(value, dict) or len(encoded(value).encode()) > 8192:
        raise VoiceError("voice_usage_invalid")
    result = {}
    for key in (
        "promptTokenCount",
        "responseTokenCount",
        "totalTokenCount",
        "cachedContentTokenCount",
        "toolUsePromptTokenCount",
        "thoughtsTokenCount",
    ):
        if type(value.get(key)) is int and 0 <= value[key] <= 1_000_000_000:
            result[key] = value[key]
    for key in (
        "promptTokensDetails",
        "responseTokensDetails",
        "cacheTokensDetails",
        "toolUsePromptTokensDetails",
    ):
        rows = value.get(key)
        if isinstance(rows, list) and len(rows) <= 8:
            result[key] = [
                {"modality": r["modality"], "tokenCount": r["tokenCount"]}
                for r in rows
                if isinstance(r, dict)
                and r.get("modality") in {"TEXT", "AUDIO"}
                and type(r.get("tokenCount")) is int
                and 0 <= r["tokenCount"] <= 1_000_000_000
            ]
    return result


class VoiceBridge:
    def __init__(self, browser, store):
        self.browser, self.store = browser, store
        self.send_lock, self.browser_lock = asyncio.Lock(), asyncio.Lock()
        self.pending, self.seen = {}, set()
        self.exposed_calendar: CalendarBindings = {}
        self.closing = self.abandoned_tool = self.send_active = self.send_uncertain = False
        self.tool_wire_id = None
        self.input_text = self.output_text = ""
        self.overlap_input = ""
        self.output_started = self.interrupted_tail = False
        self.turn, self.completed_turns = 1, 0
        self.connected, self.ready, self.muted = False, False, False
        self.input_bytes = self.output_bytes = self.transcript_bytes = 0
        self.usage, self.tool_error = [], None
        self.started = time.monotonic()
        self.provider = None

    def stop_admission(self):
        if self.closing:
            return
        self.closing = True
        self.send_uncertain |= self.send_active or self.tool_wire_id is not None
        self.abandoned_tool = bool(self.pending)
        for task in self.pending.values():
            if task is not asyncio.current_task():
                task.cancel()

    async def send_frame(self, raw):
        # No yield or separate asyncio task between this check and entry into
        # socket IO. Once entered, a Stop/timeout cannot retract those bytes.
        if self.closing:
            raise VoiceError("voice_send_closed")
        self.send_active = True
        try:
            async with asyncio.timeout(5):
                await self.provider.send(raw)
        except BaseException:
            self.send_uncertain = True
            raise
        finally:
            self.send_active = False

    async def send(self, value):
        async with self.send_lock:
            await self.send_frame(encoded(value))

    async def notify(self, value, *, terminal=False):
        async with self.browser_lock:
            if not self.closing or terminal:
                async with asyncio.timeout(5):
                    await self.browser.send_json(value)

    async def flush(self, *, partial):
        if not self.input_text.strip() and not self.output_text.strip():
            return
        if self.turn > MAX_TURNS:
            raise VoiceError("voice_turn_limit")
        self.transcript_bytes += len((self.input_text + self.output_text).encode())
        if self.transcript_bytes > 131_072:
            raise VoiceError("voice_transcript_limit")
        await self.store.transcript(self.turn, self.input_text, self.output_text, partial=partial)
        turn = self.turn
        self.turn += 1
        self.input_text = self.output_text = ""
        await self.notify({"type": "transcript_saved", "turn": turn, "partial": partial})

    async def execute_tool(self, identity, wire, arguments):
        try:
            result = await asyncio.wait_for(self.store.read_tool(wire, arguments), timeout=8)
            async with self.send_lock:
                # Interruption alone does not cancel tools. Only the exact
                # provider cancellation ID (or session teardown) removes it.
                if self.closing or identity not in self.pending:
                    return
                async with (
                    asyncio.timeout(2),
                    self.store.tool_delivery(
                        identity, wire, arguments, result, self.exposed_calendar
                    ) as (result, bindings),
                ):
                    raw = encoded(
                        {
                            "toolResponse": {
                                "functionResponses": [
                                    {
                                        "id": identity,
                                        "name": wire,
                                        "response": {"result": result, "scheduling": "WHEN_IDLE"},
                                    }
                                ]
                            }
                        }
                    )
                    if self.closing or identity not in self.pending:
                        raise VoiceError("voice_send_closed")
                    self.tool_wire_id = identity
                    await self.send_frame(raw)
                self.exposed_calendar.update(bindings)
                self.tool_wire_id = None
        except asyncio.CancelledError:
            raise
        except VoiceError as error:
            self.tool_error = str(error)
            self.stop_admission()
        except Exception:
            self.tool_error = "voice_tool_failed"
            self.stop_admission()
        finally:
            if self.tool_wire_id == identity:
                self.tool_wire_id = None
            self.pending.pop(identity, None)

    async def process(self, event):
        if self.closing:
            return
        if "usageMetadata" in event:
            if len(self.usage) >= 256:
                raise VoiceError("voice_usage_limit")
            self.usage.append(usage_sample(event["usageMetadata"]))
        if "toolCallCancellation" in event:
            ids = event["toolCallCancellation"].get("ids")
            if (
                not isinstance(ids, list)
                or len(ids) > MAX_CALLS
                or any(not isinstance(i, str) or len(i) > 160 for i in ids)
            ):
                raise VoiceError("voice_cancellation_invalid")
            cancelled = []
            for identity in ids:
                if identity == self.tool_wire_id:
                    continue  # Already in socket IO; let the bounded receipt settle.
                task = self.pending.pop(identity, None)
                if task is not None:
                    task.cancel()
                    cancelled.append(task)
            if cancelled:
                await asyncio.gather(*cancelled, return_exceptions=True)
            if self.closing:
                return
            await self.store.event("voice.tools_cancelled", {"ids": ids})
        if "toolCall" in event:
            if self.closing:
                return
            calls = event["toolCall"].get("functionCalls")
            if not isinstance(calls, list) or not calls or len(calls) > MAX_PENDING:
                raise VoiceError("voice_tool_limit")
            for call in calls:
                identity, wire, arguments = tool_request(call)
                if identity in self.seen:
                    continue  # At most one execution/response per provider ID.
                if len(self.seen) >= MAX_CALLS or len(self.pending) >= MAX_PENDING:
                    raise VoiceError("voice_tool_limit")
                self.seen.add(identity)
                self.pending[identity] = asyncio.create_task(
                    self.execute_tool(identity, wire, arguments)
                )
        content = event.get("serverContent")
        if content is not None:
            if not isinstance(content, dict):
                raise VoiceError("voice_provider_content_invalid")
            interrupted = content.get("interrupted") is True
            if interrupted and not self.interrupted_tail:
                # Clearing queued audio must not wait for Calendar or its receipt.
                await self.notify({"type": "interrupted"})
            # A provider can start responding before its tool send returns.
            # Expose none of that response until the encrypted receipt commits.
            after_tool = self.tool_wire_id is not None
            if after_tool:
                async with self.send_lock:
                    pass
            if self.closing:
                return
            if self.exposed_calendar and (
                after_tool
                or (
                    not self.output_started
                    and ("modelTurn" in content or "outputTranscription" in content)
                )
                or content.get("turnComplete") is True
                or interrupted
            ):
                await self.store.check(self.exposed_calendar.copy())
                if self.closing:
                    return
            if interrupted and not self.interrupted_tail:
                await self.store.event("voice.interrupted", {"turn": self.turn})
            parts = content.get("modelTurn", {}).get("parts", [])
            if not isinstance(parts, list) or len(parts) > 64:
                raise VoiceError("voice_provider_parts_invalid")
            for part in parts:
                if not isinstance(part, dict):
                    raise VoiceError("voice_provider_parts_invalid")
                data = pcm(part)
                if data is not None:
                    self.output_bytes += len(data)
                    if self.output_bytes > MAX_OUTPUT_BYTES:
                        raise VoiceError("voice_output_limit")
                    if not interrupted and not self.interrupted_tail:
                        self.output_started = True
                        async with self.browser_lock:
                            if self.closing:
                                return
                            async with asyncio.timeout(5):
                                await self.browser.send_bytes(data)
            if self.closing:
                return
            if not self.interrupted_tail and "outputTranscription" in content:
                await self.caption(content["outputTranscription"], "output_text", "assistant")
                self.output_started = True
            if interrupted and not self.interrupted_tail:
                await self.flush(partial=True)
                self.input_text, self.overlap_input = self.overlap_input, ""
                self.output_started = False
                self.interrupted_tail = True
            if "inputTranscription" in content:
                # Google gives input fragments no turn ID. Preserve overlap
                # with the correction on an observed interruption. Otherwise
                # retain late input, without asserting provider-level pairing.
                attribute = "overlap_input" if self.output_started else "input_text"
                await self.caption(content["inputTranscription"], attribute, "user")
            if content.get("turnComplete") is True:
                if not self.interrupted_tail:
                    self.merge_late_input()
                    await self.flush(partial=False)
                    self.completed_turns += int(self.output_started)
                await self.notify({"type": "turn_complete", "interrupted": self.interrupted_tail})
                self.interrupted_tail = self.output_started = False
            # generationComplete is deliberately not a playback-completed signal.
        if "goAway" in event:
            raise VoiceError("voice_provider_session_ending")  # No automatic reconnect.

    def merge_late_input(self):
        self.input_text += self.overlap_input
        self.overlap_input = ""
        if len(self.input_text.encode()) > MAX_TRANSCRIPT_BYTES:
            raise VoiceError("voice_transcript_limit")

    async def caption(self, value, attribute, role):
        if not isinstance(value, dict) or not isinstance(value.get("text", ""), str):
            raise VoiceError("voice_provider_transcript_invalid")
        combined = getattr(self, attribute) + value.get("text", "")
        if len(combined.encode()) > MAX_TRANSCRIPT_BYTES:
            raise VoiceError("voice_transcript_limit")
        setattr(self, attribute, combined)
        await self.notify({"type": "transcript", "role": role, "text": combined})

    async def provider_loop(self):
        while True:
            await self.process(server_event(await self.provider.recv()))

    async def browser_loop(self):
        try:
            return await self.receive_browser()
        finally:
            self.stop_admission()

    async def receive_browser(self):
        while True:
            event = await self.browser.receive()
            if event["type"] == "websocket.disconnect":
                raise VoiceError("voice_disconnected")
            data = event.get("bytes")
            if data is not None:
                if not self.ready:
                    raise VoiceError("voice_audio_before_setup")
                if not data or len(data) % 2 or len(data) > MAX_CHUNK_BYTES:
                    raise VoiceError("voice_audio_chunk_limit")
                if not self.muted:
                    self.input_bytes += len(data)
                    elapsed = time.monotonic() - self.started
                    if (
                        self.input_bytes > self.store.settings.mimi_voice_max_seconds * 32_000
                        or self.input_bytes > (elapsed + 2) * 32_000
                    ):
                        raise VoiceError("voice_input_limit")
                    await self.send(
                        {
                            "realtimeInput": {
                                "audio": {
                                    "mimeType": "audio/pcm;rate=16000",
                                    "data": base64.b64encode(data).decode("ascii"),
                                }
                            }
                        }
                    )
                continue
            raw = event.get("text")
            if not isinstance(raw, str) or len(raw) > 256:
                raise VoiceError("voice_browser_message_invalid")
            try:
                control = json.loads(raw)
            except ValueError:
                raise VoiceError("voice_browser_message_invalid") from None
            if control == {"type": "stop"}:
                return "voice_stopped"
            if (
                self.ready
                and isinstance(control, dict)
                and set(control) == {"type", "muted"}
                and (control["type"] == "mute" and type(control["muted"]) is bool)
            ):
                self.muted = control["muted"]
                if self.muted:
                    await self.send({"realtimeInput": {"audioStreamEnd": True}})
                await self.notify({"type": "muted", "muted": self.muted})
            else:
                raise VoiceError("voice_browser_message_forbidden")

    async def watchdog(self):
        try:
            while True:
                await asyncio.sleep(2)
                if self.tool_error:
                    raise VoiceError(self.tool_error)
                await self.store.check(self.exposed_calendar.copy())
        finally:
            self.stop_admission()

    async def end_tasks(self, tasks):
        self.stop_admission()
        all_tasks = [*tasks, *self.pending.values()]
        for task in tasks:
            task.cancel()
        if all_tasks:
            # A cancelled upstream waiter must not cancel tool cleanup again.
            await asyncio.wait(all_tasks)
            await asyncio.gather(*all_tasks, return_exceptions=True)

    async def upstream(self, config, seed):
        async with connect_provider(self.store.settings, run_id=self.store.run_id) as provider:
            self.provider = provider
            try:
                await self.store.check()
                await self.send(config)
                event = server_event(await asyncio.wait_for(provider.recv(), timeout=10))
                if not isinstance(event.get("setupComplete"), dict):
                    raise VoiceError("voice_provider_setup_rejected")
                self.connected = True
                await self.process(event)
                await self.store.check()
                if seed is not None:
                    await self.send(seed)
                await self.store.event("voice.connected", {"transport": "google_live"})
                self.ready = True
                await self.notify({"type": "ready", "run_id": str(self.store.run_id)})
                await self.provider_loop()
            finally:
                self.ready = False
                await self.end_tasks([])  # Fence pending reads before closing upstream.

    async def run(self, config, seed, deadline):
        reason, tasks = "voice_disconnected", []
        try:
            await self.store.dispatched()  # Persist uncertainty before the external connection.
            remaining = (deadline - datetime.now(UTC)).total_seconds()
            async with asyncio.timeout(remaining):
                tasks = [
                    asyncio.create_task(work)
                    for work in (
                        self.browser_loop(),
                        self.upstream(config, seed),
                        self.watchdog(),
                    )
                ]
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in tasks:
                    if task.done() and (value := task.result()):
                        reason = value
                        break
        except VoiceError as error:
            reason = str(error)
        except TimeoutError:
            reason = "voice_time_limit"
        except WebSocketDisconnect, asyncio.CancelledError:
            reason = "voice_disconnected"
        except Exception:
            reason = "voice_connection_failed"  # No raw exceptions, wire, socket repr or key.
        finally:
            await self.end_tasks(tasks)
            incomplete = (
                self.output_started
                or self.abandoned_tool
                or self.interrupted_tail
                or self.send_uncertain
            )
            if any(t.strip() for t in (self.input_text, self.overlap_input, self.output_text)):
                with suppress(Exception), asyncio.timeout(5):
                    self.merge_late_input()
                    await self.flush(partial=True)
                incomplete = True
            if incomplete and reason == "voice_stopped":
                reason = "voice_interrupted_on_stop"
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
                        "provider_send_may_have_been_in_flight": self.send_uncertain,
                    },
                )
            with suppress(Exception):
                await self.notify({"type": "ended", "reason": reason}, terminal=True)
        return reason
