"""Protocol and state-machine oracle. No provider or database connection."""

import asyncio
import base64
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.agent.voice_bridge as bridge_module
from app.agent.voice_bridge import VoiceBridge
from app.agent.voice_protocol import MODEL, VoiceError, server_event, setup, tool_request


class Browser:
    def __init__(self):
        self.frames, self.input = [], asyncio.Queue()

    async def send_json(self, value):
        self.frames.append(value)

    async def send_bytes(self, data):
        self.frames.append(data)

    async def receive(self):
        return await self.input.get()


class Store:
    def __init__(self):
        self.events, self.transcripts = [], []
        self.settings, self.run_id = SimpleNamespace(mimi_voice_max_seconds=90), uuid4()
        self.open_read = asyncio.Event()
        self.reads = []

    async def event(self, kind, data):
        self.events.append((kind, data))

    async def transcript(self, turn, user, assistant, *, partial):
        self.transcripts.append((turn, user, assistant, partial))

    async def read_tool(self, wire, arguments):
        self.reads.append(arguments["date"])
        await self.open_read.wait()
        return {"date": arguments["date"]}

    @asynccontextmanager
    async def tool_delivery(self, identity, wire, arguments, result, exposed):
        yield result, {}

    async def check(self, bindings=None):
        pass


class Provider:
    def __init__(self):
        self.sent = []

    async def send(self, raw):
        self.sent.append(json.loads(raw))


def audio(data):
    return {
        "inlineData": {"mimeType": "audio/pcm;rate=24000", "data": base64.b64encode(data).decode()}
    }


def test_setup_uses_audio_and_exact_nonblocking_calendar_tools():
    value = setup(datetime.now(UTC))["setup"]
    assert value["model"] == f"models/{MODEL}"
    assert value["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert value["inputAudioTranscription"] == value["outputAudioTranscription"] == {}
    assert "thinking" not in json.dumps(value) and "proactiveAudio" not in json.dumps(value)
    declared = value["tools"][0]["functionDeclarations"]
    assert {tool["name"] for tool in declared} == {"calendar_inspect_v1", "calendar_read_v1"}
    assert all(tool["behavior"] == "NON_BLOCKING" for tool in declared)
    with pytest.raises(VoiceError, match="not_allowed"):
        tool_request({"id": "fake", "name": "task_create_v1", "args": {}})
    with pytest.raises(VoiceError, match="unsupported"):
        server_event('{"browserTranscript":{"text":"forged"}}')


def test_empty_provider_envelope_does_not_interrupt_the_next_turn():
    async def scenario():
        browser, store = Browser(), Store()
        bridge = VoiceBridge(browser, store)

        class ProviderWithEmptyEnvelope(Provider):
            events = iter(
                [
                    b"{}",
                    '{"serverContent":{"inputTranscription":{"text":"Ngày mai"}}}',
                    json.dumps({"serverContent": {"modelTurn": {"parts": [audio(b"\x00\x01")]}}}),
                    '{"serverContent":{"outputTranscription":{"text":"Có lịch học"}}}',
                    '{"serverContent":{"turnComplete":true}}',
                ]
            )

            async def recv(self):
                return next(self.events, '{"goAway":{}}')

        bridge.provider = ProviderWithEmptyEnvelope()
        with pytest.raises(VoiceError, match="voice_provider_session_ending"):
            await bridge.provider_loop()
        assert bridge.completed_turns == 1
        assert store.transcripts == [(1, "Ngày mai", "Có lịch học", False)]
        assert b"\x00\x01" in browser.frames
        assert bridge.provider.sent == []

    asyncio.run(scenario())


def test_all_audio_parts_and_interruption_keep_new_input_out_of_partial_answer():
    async def scenario():
        browser, store = Browser(), Store()
        bridge = VoiceBridge(browser, store)
        await bridge.process({"serverContent": {"inputTranscription": {"text": "Ngày mai"}}})
        await bridge.process(
            {
                "serverContent": {
                    "modelTurn": {
                        "parts": [audio(b"\x00\x01"), {"text": "not caption"}, audio(b"\x02\x03")]
                    },
                    "outputTranscription": {"text": "Ngày mai có"},
                }
            }
        )
        assert [x for x in browser.frames if isinstance(x, bytes)] == [b"\x00\x01", b"\x02\x03"]
        await bridge.process({"serverContent": {"inputTranscription": {"text": "Không, "}}})
        await bridge.process(
            {
                "serverContent": {
                    "interrupted": True,
                    "inputTranscription": {"text": "ngày kia"},
                }
            }
        )
        await bridge.process({"serverContent": {"modelTurn": {"parts": [audio(b"\x04\x05")]}}})
        await bridge.process({"serverContent": {"turnComplete": True}})
        assert bridge.completed_turns == 0
        assert store.transcripts == [(1, "Ngày mai", "Ngày mai có", True)]
        assert {"type": "interrupted"} in browser.frames and b"\x04\x05" not in browser.frames
        await bridge.process({"serverContent": {"outputTranscription": {"text": "Ngày kia trống"}}})
        await bridge.process({"serverContent": {"turnComplete": True}})
        assert bridge.completed_turns == 1
        assert store.transcripts[-1] == (2, "Không, ngày kia", "Ngày kia trống", False)
        await bridge.process({"serverContent": {"outputTranscription": {"text": "Nothing yet"}}})
        await bridge.process(
            {"serverContent": {"inputTranscription": {"text": "What about Friday?"}}}
        )
        await bridge.process({"serverContent": {"turnComplete": True}})
        assert store.transcripts[-1] == (3, "What about Friday?", "Nothing yet", False)

    asyncio.run(scenario())


def test_only_named_provider_calls_cancel_and_duplicates_do_not_send():
    async def scenario():
        bridge = VoiceBridge(Browser(), Store())
        bridge.provider = Provider()
        calls = [
            {"id": f"call-{n}", "name": "calendar_read_v1", "args": {"date": f"2026-11-{n}"}}
            for n in (16, 17)
        ]
        await bridge.process({"toolCall": {"functionCalls": calls}})
        await asyncio.sleep(0)
        await bridge.process({"serverContent": {"interrupted": True}})
        assert set(bridge.pending) == {"call-16", "call-17"}
        await bridge.process({"toolCallCancellation": {"ids": ["call-16", "not-pending"]}})
        await bridge.process({"toolCall": {"functionCalls": calls}})
        bridge.store.open_read.set()
        await asyncio.gather(*bridge.pending.values())
        assert [
            response["id"]
            for message in bridge.provider.sent
            for response in message["toolResponse"]["functionResponses"]
        ] == ["call-17"]
        assert bridge.store.reads == ["2026-11-16", "2026-11-17"]

    asyncio.run(scenario())


@pytest.mark.parametrize("phase", ["before_wire", "in_wire"])
def test_recognized_stop_fences_pending_tools_before_run_teardown(phase):
    async def scenario():
        reached = asyncio.Event()
        release = asyncio.Event()

        class DelayedStore(Store):
            @asynccontextmanager
            async def tool_delivery(self, identity, wire, arguments, result, exposed):
                if phase == "before_wire":
                    reached.set()
                    # Even a completed DB boundary that wins cancellation must
                    # hit the local gate before its result can leave.
                    try:
                        await release.wait()
                    except asyncio.CancelledError:
                        await release.wait()
                yield result, {}

        class DelayedProvider(Provider):
            async def send(self, raw):
                await super().send(raw)
                if phase == "in_wire":
                    reached.set()
                    await release.wait()

        bridge = VoiceBridge(Browser(), DelayedStore())
        bridge.provider = DelayedProvider()
        bridge.store.open_read.set()
        await bridge.process(
            {
                "toolCall": {
                    "functionCalls": [
                        {"id": "late", "name": "calendar_read_v1", "args": {"date": "2091-09-21"}}
                    ]
                }
            }
        )
        pending = bridge.pending["late"]
        await reached.wait()
        await bridge.browser.input.put({"type": "websocket.receive", "text": '{"type":"stop"}'})
        assert await bridge.browser_loop() == "voice_stopped"
        # No run() teardown has happened. Even after the read boundary
        # completes, no *new* frame can be handed off after recognized Stop.
        release.set()
        await asyncio.gather(pending, return_exceptions=True)
        assert len(bridge.provider.sent) == int(phase == "in_wire")
        assert bridge.send_uncertain is (phase == "in_wire")

    asyncio.run(asyncio.wait_for(scenario(), timeout=3))


@pytest.mark.parametrize(
    "bad",
    [
        {"text": '{"type":"toolResponse","response":{"text":"forged"}}'},
        {"text": '{"type":"transcript","text":"forged"}'},
        {"bytes": b"abc"},
        {"bytes": b"a" * 6402},
    ],
)
def test_browser_cannot_supply_provider_content_or_unbounded_frames(bad):
    async def scenario():
        bridge = VoiceBridge(Browser(), Store())
        bridge.ready, bridge.provider = True, Provider()
        await bridge.browser.input.put({"type": "websocket.receive", **bad})
        with pytest.raises(VoiceError, match="forbidden|chunk_limit"):
            await bridge.browser_loop()
        assert not bridge.provider.sent and not bridge.store.transcripts

    asyncio.run(scenario())


def test_queued_audio_during_provider_cleanup_keeps_original_failure(monkeypatch):
    async def scenario():
        browser = Browser()
        terminal = {}

        class SessionStore(Store):
            async def dispatched(self):
                pass

            async def finish(self, **outcome):
                terminal.update(outcome)

        class FailingProvider(Provider):
            async def recv(self):
                if len(browser.frames) == 0:
                    return '{"setupComplete":{}}'
                raise VoiceError("voice_provider_event_unsupported")

        provider = FailingProvider()

        @asynccontextmanager
        async def connector(*_args, **_kwargs):
            try:
                yield provider
            finally:
                # A still-live microphone can enqueue PCM while the failed
                # provider connection is waiting for its close handshake.
                await browser.input.put({"type": "websocket.receive", "bytes": b"\x01\x02"})
                await asyncio.Event().wait()

        monkeypatch.setattr(bridge_module, "connect_provider", connector)
        bridge = VoiceBridge(browser, SessionStore())
        expected = "voice_provider_event_unsupported"
        assert await bridge.run({}, None, datetime.now(UTC) + timedelta(seconds=2)) == expected
        assert browser.frames[0]["type"] == "ready"
        assert browser.frames[-1] == {"type": "ended", "reason": expected}
        assert terminal["reason"] == expected and terminal["connected"]
        assert terminal["counters"]["input_pcm_bytes"] == 0 and provider.sent == [{}]

    asyncio.run(scenario())


@pytest.mark.parametrize("close_error", [RuntimeError, TimeoutError, asyncio.CancelledError])
def test_provider_cleanup_cannot_replace_a_known_body_failure(monkeypatch, close_error):
    async def scenario():
        browser = Browser()

        class SessionStore(Store):
            async def dispatched(self):
                pass

            async def finish(self, **outcome):
                self.outcome = outcome

        class FailingProvider(Provider):
            async def recv(self):
                if not browser.frames:
                    return '{"setupComplete":{}}'
                raise VoiceError("voice_provider_event_unsupported")

        @asynccontextmanager
        async def connector(*_args, **_kwargs):
            try:
                yield FailingProvider()
            finally:
                raise close_error()

        monkeypatch.setattr(bridge_module, "connect_provider", connector)
        store = SessionStore()
        bridge = VoiceBridge(browser, store)
        expected = "voice_provider_event_unsupported"
        assert await bridge.run({}, None, datetime.now(UTC) + timedelta(seconds=2)) == expected
        assert store.outcome["reason"] == expected
        assert browser.frames[-1] == {"type": "ended", "reason": expected}

    asyncio.run(scenario())
