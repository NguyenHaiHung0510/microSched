"""Deterministic transport and spoken authority; no provider or database."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agent import voice_bridge, voice_v2_bridge
from app.agent.task_collection import (
    PreparedCollection,
    PreparedEntry,
    TaskCommand,
    proposed_fields,
)
from app.agent.voice_protocol import setup
from app.agent.voice_v2_bridge import VoiceV2Bridge
from app.agent.voice_v2_intent import SpeechWindow, create_scope, exact_plan_match, spoken_undo
from app.agent.voice_v2_outcome import committed
from app.agent.voice_v2_protocol import setup_v2
from app.agent.voice_v2_store import VoiceContextChanged, VoiceSources
from app.core.settings import Settings

PCM = b"\0" * 6400


class Browser:
    def __init__(self):
        self.sent, self.inbound, self.frames = [], asyncio.Queue(), asyncio.Queue()

    async def send_json(self, value):
        self.sent.append(value)
        await self.frames.put(value)

    async def send_bytes(self, value):
        await self.frames.put(value)

    async def receive(self):
        return await self.inbound.get()

    async def until(self, field):
        while True:
            frame = await asyncio.wait_for(self.frames.get(), timeout=2)
            if isinstance(frame, dict) and frame["type"] == field:
                return frame


class Live:
    def __init__(self):
        self.events = asyncio.Queue()
        self.sent = asyncio.Queue()
        self.frames = []
        self.events.put_nowait({"setupComplete": {}})

    async def send(self, raw):
        frame = json.loads(raw)
        self.frames.append(frame)
        await self.sent.put(frame)

    async def recv(self):
        event = await self.events.get()
        if isinstance(event, Exception):
            raise event
        return json.dumps(event)

    def emit(self, *values):
        for value in values:
            self.events.put_nowait(value)


class Store:
    def __init__(self):
        self.settings = Settings(mimi_collection_enabled=True, mimi_calendar_read_enabled=True)
        self.run_id = uuid4()
        self.saved, self.actions, self.events = [], [], []
        self.final = None
        self.invalid = False
        self.gate_blocked, self.release_gate = asyncio.Event(), asyncio.Event()
        self.block = False

    @asynccontextmanager
    async def live_gate(self, sources=None, *, detail=False):
        if self.block:
            self.gate_blocked.set()
            await self.release_gate.wait()
        if self.invalid and detail:
            self.invalid = False
            raise VoiceContextChanged()
        yield

    async def event(self, kind, data):
        self.events.append((kind, data))

    async def dispatched(self):
        pass

    async def transcript(self, turn, user, assistant, *, partial, sources):
        self.saved.append((turn, user, assistant, partial))

    async def act(self, turn, epoch, proposals, proof, transcript, sources, is_active):
        assert is_active()
        self.actions.append((turn, epoch, proposals, proof, transcript))
        return committed("applied" if proof else "preview")

    async def finish(self, **value):
        self.final = value


def speech(text, *, base=0.0, outputs=True):
    start, end = f"{base + 0.01:.3f}s", f"{base + 0.15:.3f}s"
    events = [
        {"voiceActivity": {"type": "ACTIVITY_START", "audioOffset": start}},
        {"voiceActivity": {"type": "ACTIVITY_END", "audioOffset": end}},
        {
            "serverContent": {
                "inputTranscription": {
                    "text": text,
                    "startOffset": start,
                    "endOffset": end,
                }
            }
        },
    ]
    if outputs:
        events.append(
            {
                "serverContent": {
                    "outputTranscription": {"text": "Đã nghe."},
                    "generationComplete": True,
                    "turnComplete": True,
                }
            }
        )
    return events


def proposal(identity, titles):
    return {
        "toolCall": {
            "functionCalls": [
                {
                    "id": identity,
                    "name": "task_collection_candidate_v1",
                    "args": {
                        "entries": [{"action": "create", "fields": {"title": t}} for t in titles]
                    },
                }
            ]
        }
    }


async def audio(browser, provider):
    await browser.inbound.put({"type": "websocket.receive", "bytes": PCM})
    return await asyncio.wait_for(provider.sent.get(), timeout=2)


def test_setup_keeps_v1_wire_and_leases_only_current_v2_capabilities():
    settings = Settings()
    assert not settings.mimi_voice_v2_enabled
    assert settings.mimi_voice_v2_max_seconds == 5400
    now = datetime.now(UTC)
    old = setup(now)["setup"]
    assert "sessionResumption" not in old
    assert {t["name"] for t in old["tools"][0]["functionDeclarations"]} == {
        "calendar_read_v1",
        "calendar_inspect_v1",
    }
    config = setup_v2(now, settings)["setup"]
    assert config["sessionResumption"] == {}
    assert config["inputAudioTranscription"] == {"wordTimestamp": True}
    assert config["contextWindowCompression"] == {
        "triggerTokens": "25000",
        "slidingWindow": {"targetTokens": "8000"},
    }
    assert config["generationConfig"] == old["generationConfig"]
    names = {t["name"] for t in config["tools"][0]["functionDeclarations"]}
    assert names == {
        "task_query_v1",
        "task_aggregate_v1",
        "task_inspect_batch_v1",
        "task_read_content_v1",
        "task_create_candidate_v2",
    }
    settings = Settings(
        mimi_collection_enabled=True,
        mimi_calendar_read_enabled=True,
        mimi_voice_v2_compression_enabled=False,
    )
    config = setup_v2(now, settings)["setup"]
    assert "contextWindowCompression" not in config
    assert {t["name"] for t in config["tools"][0]["functionDeclarations"]} - names == {
        "task_freeze_selection_v1",
        "task_collection_candidate_v1",
        "voice_undo_latest_v1",
        "calendar_read_v1",
        "calendar_inspect_v1",
    }


@pytest.mark.parametrize("drop", [OSError("upstream closed"), {"goAway": {"timeLeft": "1s"}}])
def test_early_live_drop_resumes_same_mic_without_audio_asr_or_actions_replay(monkeypatch, drop):
    async def scenario():
        browser, store = Browser(), Store()
        sockets = [Live(), Live()]
        opened = []

        @asynccontextmanager
        async def connect(_settings, *, run_id):
            assert run_id == store.run_id
            socket = sockets[len(opened)]
            opened.append(socket)
            yield socket

        monkeypatch.setattr(voice_bridge, "connect_provider", connect)
        monkeypatch.setattr(voice_v2_bridge, "BACKOFF", (0.05, 0.05, 0.05))
        bridge = VoiceV2Bridge(browser, store)
        absolute = datetime.now(UTC) + timedelta(minutes=90)
        config = setup_v2(datetime.now(UTC), store.settings)
        runner = asyncio.create_task(bridge.run(config, None, absolute))
        ready = await browser.until("ready")
        await sockets[0].sent.get()  # initial setup
        assert ready["deadline"] == absolute.isoformat()
        for turn in range(3):
            await audio(browser, sockets[0])
            sockets[0].emit(*speech(f"Lượt {turn + 1}", base=turn * 0.2))
            await browser.until("turn_complete")
        sockets[0].emit(
            {"sessionResumptionUpdate": {"newHandle": "only-in-memory", "resumable": True}}, drop
        )
        await browser.until("reconnecting")
        await browser.inbound.put({"type": "websocket.receive", "bytes": b"a\0" * 1600})
        assert (await browser.until("resumed"))["context_retained"]
        resumed_setup = await sockets[1].sent.get()
        assert resumed_setup["setup"]["sessionResumption"] == {"handle": "only-in-memory"}
        assert len(sockets[1].frames) == 1
        await audio(browser, sockets[1])
        sockets[1].emit(proposal("old", ["stale"]), speech("tạo task stale")[2])
        sockets[1].emit(
            *speech("tạo task mới", base=0.6, outputs=False),
            proposal("new", ["mới"]),
            *speech("", outputs=True)[-1:],
        )
        await browser.until("action_updated")
        assert store.actions[0][3] == "tạo task mới"
        await browser.inbound.put({"type": "websocket.receive", "text": '{"type":"stop"}'})
        assert await asyncio.wait_for(runner, timeout=2) == "voice_stopped"
        assert len(store.actions) == 1
        assert len(store.saved) == 4
        assert store.final["counters"]["connection_attempts"] == 2
        assert "only-in-memory" not in repr((store.events, store.final, browser.sent))
        assert bridge.deadline == absolute

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "browser_event,reason",
    [
        ({"type": "websocket.disconnect"}, "voice_browser_disconnected"),
        (
            {"type": "websocket.receive", "text": '{"type":"microphone_lost"}'},
            "voice_microphone_lost",
        ),
    ],
)
def test_browser_terminal_during_backoff_never_dials_again(monkeypatch, browser_event, reason):
    async def scenario():
        browser, store, live = Browser(), Store(), Live()
        dials = []

        @asynccontextmanager
        async def connect(_settings, *, run_id):
            dials.append(run_id)
            yield live

        monkeypatch.setattr(voice_bridge, "connect_provider", connect)
        monkeypatch.setattr(voice_v2_bridge, "BACKOFF", (0.2, 0.2, 0.2))
        task = asyncio.create_task(
            VoiceV2Bridge(browser, store).run(
                setup_v2(datetime.now(UTC), store.settings),
                None,
                datetime.now(UTC) + timedelta(seconds=4),
            )
        )
        await browser.until("ready")
        live.emit({"goAway": {}})
        await browser.until("reconnecting")
        await browser.inbound.put(browser_event)
        assert await task == reason
        assert store.final["reason"] == reason and len(dials) == 1

    asyncio.run(scenario())


def test_expired_deadline_cannot_open_and_stale_handle_uses_fresh_context(monkeypatch):
    async def scenario():
        browser, store = Browser(), Store()
        opened = []

        @asynccontextmanager
        async def connect(_settings, *, run_id):
            live = Live()
            opened.append(live)
            yield live

        monkeypatch.setattr(voice_bridge, "connect_provider", connect)
        monkeypatch.setattr(voice_v2_bridge, "BACKOFF", (0.001, 0.001, 0.001))
        config = setup_v2(datetime.now(UTC), store.settings)
        assert (
            await VoiceV2Bridge(browser, store).run(
                config, None, datetime.now(UTC) - timedelta(milliseconds=1)
            )
            == "voice_time_limit"
        )
        assert not opened
        browser = Browser()
        task = asyncio.create_task(
            VoiceV2Bridge(browser, store).run(
                config,
                None,
                datetime.now(UTC) + timedelta(seconds=4),
            )
        )
        await browser.until("ready")
        store.invalid = True
        opened[0].emit(
            {"sessionResumptionUpdate": {"newHandle": "stale", "resumable": True}},
            {"goAway": {}},
        )
        assert not (await browser.until("resumed"))["context_retained"]
        assert opened[1].frames[0]["setup"]["sessionResumption"] == {}
        await browser.inbound.put({"type": "websocket.disconnect"})
        assert await task == "voice_browser_disconnected"
        assert len(opened) == 2

    asyncio.run(scenario())


def _plan(titles):
    commands = [
        TaskCommand(action="create", fields={"title": name, **(due or {})}) for name, due in titles
    ]
    return PreparedCollection(
        selection_id=None,
        entries=tuple(
            PreparedEntry(
                id=uuid4(),
                command=c,
                before=None,
                after={"fields": proposed_fields(c, None)},
                reminder_effect={"action": "none"},
            )
            for c in commands
        ),
    )


def test_mic_cadence_survives_pending_authority_check_then_fails_closed(monkeypatch):
    async def scenario():
        browser, store, live = Browser(), Store(), Live()

        @asynccontextmanager
        async def connect(_settings, *, run_id):
            yield live

        monkeypatch.setattr(voice_bridge, "connect_provider", connect)
        monkeypatch.setattr(voice_v2_bridge, "WATCHDOG_INTERVAL", 0.005)
        monkeypatch.setattr(voice_v2_bridge, "AUTH_WINDOW", 0.3)
        bridge = VoiceV2Bridge(browser, store)
        task = asyncio.create_task(
            bridge.run(
                setup_v2(datetime.now(UTC), store.settings),
                None,
                datetime.now(UTC) + timedelta(seconds=3),
            )
        )
        await browser.until("ready")
        await live.sent.get()
        store.block = True
        await asyncio.wait_for(store.gate_blocked.wait(), 1)
        for _ in range(6):
            await browser.inbound.put({"type": "websocket.receive", "bytes": PCM[:640]})
            frame = await asyncio.wait_for(live.sent.get(), 0.15)
            assert "audio" in frame["realtimeInput"]
        await asyncio.sleep(0.31)
        await browser.inbound.put({"type": "websocket.receive", "bytes": PCM[:640]})
        assert await asyncio.wait_for(task, 1) == "voice_authority_expired"
        assert live.sent.empty()

    asyncio.run(scenario())


def test_absolute_deadline_keeps_running_during_reconnect_backoff(monkeypatch):
    async def scenario():
        browser, store, live = Browser(), Store(), Live()
        dials = []

        @asynccontextmanager
        async def connect(_settings, *, run_id):
            dials.append(run_id)
            yield live

        monkeypatch.setattr(voice_bridge, "connect_provider", connect)
        monkeypatch.setattr(voice_v2_bridge, "BACKOFF", (1, 1, 1))
        bridge = VoiceV2Bridge(browser, store)
        deadline = datetime.now(UTC) + timedelta(seconds=0.5)
        task = asyncio.create_task(
            bridge.run(setup_v2(datetime.now(UTC), store.settings), None, deadline)
        )
        assert (await browser.until("ready"))["deadline"] == deadline.isoformat()
        live.emit({"goAway": {}})
        await browser.until("reconnecting")
        assert await asyncio.wait_for(task, 2) == "voice_time_limit"
        assert (await browser.until("ended"))["reason"] == "voice_time_limit"
        assert len(dials) == 1

    asyncio.run(scenario())


def test_source_backed_pcm_burst_does_not_recheck_each_envelope_after_slow_validation(monkeypatch):
    async def scenario():
        browser, store = Browser(), Store()
        now = [1.0]
        checks = []
        monkeypatch.setattr(voice_v2_bridge, "time", SimpleNamespace(monotonic=lambda: now[0]))

        @asynccontextmanager
        async def slow_gate(sources):
            checks.append(sources)
            now[0] += voice_v2_bridge.SOURCE_WINDOW + 0.10
            yield

        monkeypatch.setattr(store, "live_gate", slow_gate)
        bridge = VoiceV2Bridge(browser, store)
        bridge.deadline = datetime.now(UTC) + timedelta(seconds=3)
        bridge.authority_until = 10
        bridge.sources = VoiceSources().plus(
            "task.aggregate.v1",
            {"group_by": "status"},
            {"groups": [{"value": "open", "count": 1}], "coverage": "complete"},
        )
        pcm = PCM[:960]
        await bridge._render([pcm], first_answer=True)
        for _ in range(6):
            now[0] += 0.02
            await bridge._render([pcm], first_answer=False)
        assert len(checks) == 1
        assert browser.frames.qsize() == 7

        now[0] += voice_v2_bridge.SOURCE_WINDOW
        await bridge._render([pcm], first_answer=False)
        assert checks == [bridge.sources, bridge.sources]

    asyncio.run(scenario())


def test_whole_speech_never_authorizes_fragments_unspoken_fields_or_six_targets():
    names = "một", "hai", "ba", "bốn", "năm", "sáu"
    sample = lambda n: _plan([(name, None) for name in names[:n]])  # noqa: E731
    utterance = lambda n: f"Tạo các việc: {', '.join(names[:n])}."  # noqa: E731
    # Supported named-list form; check both real counts against the same whole command.
    full = utterance(6).replace("các ", "")
    assert exact_plan_match(utterance(5).replace("các ", ""), sample(5))
    assert not exact_plan_match(full, sample(5))
    assert not exact_plan_match(full, sample(6))
    assert not exact_plan_match("Cho tôi xem năm việc.", sample(5))
    assert not exact_plan_match("Tạo việc một, rồi đừng tạo việc hai.", sample(2))
    assert not exact_plan_match("Tạo việc một và hai?", sample(2))
    plan = _plan([("nộp bài", {"due_precision": "date", "due_on": "2091-02-04", "due_at": None})])
    assert exact_plan_match("Tạo việc nộp bài hạn ngày mai.", plan, today=date(2091, 2, 3))
    assert exact_plan_match("Tạo việc nộp bài hạn 4/2/2091.", plan)
    assert not exact_plan_match("Tạo việc nộp bài.", plan)
    assert spoken_undo("Mimi, hoàn tác cái vừa làm.")
    assert not spoken_undo("Nếu hoàn tác cái vừa làm thì sao?")


def test_vad_asr_offsets_reject_overlap_late_input_and_missing_boundaries():
    parts = speech("Tạo việc A.", outputs=False)
    window = SpeechWindow()
    assert window.prove() is None
    window.activity(parts[0]["voiceActivity"], 200)
    window.activity(parts[1]["voiceActivity"], 200)
    window.transcript(parts[2]["serverContent"]["inputTranscription"], 200)
    assert window.prove() == "Tạo việc A."
    renewed = window.next(200)
    renewed.activity(parts[0]["voiceActivity"], 400)
    renewed.activity(parts[1]["voiceActivity"], 400)
    renewed.transcript(parts[2]["serverContent"]["inputTranscription"], 400)
    assert renewed.prove() is None
    window.transcript(parts[2]["serverContent"]["inputTranscription"], 200)
    assert window.prove() is None


@pytest.mark.parametrize(
    "phrase",
    [
        "Tạo các việc sau: A, B, C, D, E và F.",
        "Tạo sáu việc tên A, B, C, D, E và F.",
        "Tạo 6 công việc gồm A, B, C, D, E và F.",
        "Create six tasks named A, B, C, D, E and F.",
        "Add 6 new tasks: A, B, C, D, E and F.",
    ],
)
def test_numeric_and_natural_plural_whole_speech_keeps_exact_six_targets(phrase):
    result = create_scope(phrase, None)
    assert result.count == 6 and not result.ambiguous
    assert result.names == tuple((name, None) for name in "abcdef")
    assert not exact_plan_match(phrase, _plan([(name, None) for name in "abcde"]))


def test_late_overlapping_asr_denies_proposal_before_commit_and_reports_to_both_sides(monkeypatch):
    async def scenario():
        browser, store, live = Browser(), Store(), Live()

        @asynccontextmanager
        async def connect(_settings, *, run_id):
            yield live

        monkeypatch.setattr(voice_bridge, "connect_provider", connect)
        task = asyncio.create_task(
            VoiceV2Bridge(browser, store).run(
                setup_v2(datetime.now(UTC), store.settings),
                None,
                datetime.now(UTC) + timedelta(seconds=5),
            )
        )
        await browser.until("ready")
        await live.sent.get()
        await audio(browser, live)
        first = speech("Tạo việc misheard.")
        correction = speech("Đừng tạo việc đó.")[2]
        live.emit(*first[:-1], proposal("misheard", ["misheard"]), first[-1], correction)
        result = await browser.until("action_updated")
        assert result["status"] == "needs_clarification"
        assert result["reason"] == "voice_spoken_intent_unproven"
        await browser.until("turn_complete")
        assert not store.actions
        await live.sent.get()  # proposal acknowledgment
        note = (await asyncio.wait_for(live.sent.get(), 1))["clientContent"]
        assert note["turnComplete"] is False
        assert "voice_spoken_intent_unproven" in str(note) and "misheard" not in str(note)
        await audio(browser, live)
        new = speech("Tạo việc đúng.", base=0.2)
        live.emit(*new[:-1], proposal("right", ["đúng"]), new[-1])
        assert (await browser.until("action_updated"))["status"] == "applied"
        assert [a[3] for a in store.actions] == ["Tạo việc đúng."]
        await browser.inbound.put({"type": "websocket.disconnect"})
        assert await task == "voice_browser_disconnected"

    asyncio.run(scenario())
