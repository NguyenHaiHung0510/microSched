"""Grant71 B1 regressions: synthetic transport only; no Google dispatch."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from test_mimi_voice_v2 import PCM, Browser, Live, Store, audio, proposal

from app.agent import voice_bridge
from app.agent.voice_v2_bridge import VoiceV2Bridge
from app.agent.voice_v2_intent import SpeechWindow
from app.agent.voice_v2_protocol import setup_v2


def test_caption_free_vad_binds_one_structured_turn():
    window = SpeechWindow()
    window.activity({"type": "ACTIVITY_START", "audioOffset": "0.01s"}, 200)
    window.activity({"type": "ACTIVITY_END", "audioOffset": "0.15s"}, 200)
    binding = window.bind(2, 3, ["fresh"])
    assert binding.matches(3, 2, 1)
    assert not binding.matches(3, 1, 1)
    assert not binding.matches(4, 2, 1)


def test_interim_final_or_repeated_caption_does_not_change_write_binding():
    bridge = VoiceV2Bridge(Browser(), Store())
    bridge.forwarded_ms = 200
    bridge.speech.activity({"type": "ACTIVITY_START", "audioOffset": "0.01s"}, 200)
    bridge.speech.activity({"type": "ACTIVITY_END", "audioOffset": "0.15s"}, 200)
    binding = bridge.speech.bind(1, 1, ["one"])
    for item in ({"text": "A", "finished": False}, {"text": "B"}, {"text": "B"}):
        bridge._track_input_final(item)
        assert bridge.speech.bind(1, 1, ["one"]) == binding


def test_blocking_tool_gets_one_actual_result_only_after_delayed_final(monkeypatch):
    async def run():
        browser, store, live = Browser(), Store(), Live()

        @asynccontextmanager
        async def connect(_settings, *, run_id):
            yield live

        monkeypatch.setattr(voice_bridge, "connect_provider", connect)
        bridge = VoiceV2Bridge(browser, store)
        runner = asyncio.create_task(
            bridge.run(
                setup_v2(datetime.now(UTC), store.settings),
                None,
                datetime.now(UTC) + timedelta(seconds=5),
            )
        )
        try:
            await browser.until("ready")
            await live.sent.get()
            await audio(browser, live)
            live.emit(
                {"voiceActivity": {"type": "ACTIVITY_START", "audioOffset": "0.01s"}},
                proposal("one", ["A"]),
                {"serverContent": {"interimInputTranscription": {"text": "Tạo việc B."}}},
                {"voiceActivity": {"type": "ACTIVITY_END", "audioOffset": "0.15s"}},
            )
            await asyncio.sleep(0.02)
            assert not store.actions
            assert not any("toolResponse" in f for f in live.frames)
            live.emit({"serverContent": {"inputTranscription": {"text": "Tạo việc A."}}})
            event = await browser.until("action_updated")
            assert event["status"] == "applied"
            while True:
                result = await live.sent.get()
                if "toolResponse" in result:
                    break
            response = result["toolResponse"]["functionResponses"][0]
            assert response["id"] == "one"
            assert response["response"]["result"]["final"] is True
            assert response["response"]["result"]["status"] == "applied"
            live.emit(
                {
                    "serverContent": {
                        "outputTranscription": {"text": "Đã áp dụng."},
                        "generationComplete": True,
                        "turnComplete": True,
                    }
                },
                proposal("one", ["A"]),
            )
            await asyncio.sleep(0.02)
            assert len(store.actions) == 1
            assert len([f for f in live.frames if "toolResponse" in f]) == 1
        finally:
            await browser.inbound.put({"type": "websocket.disconnect"})
            assert await runner == "voice_browser_disconnected"

    asyncio.run(run())


def test_read_audio_after_native_resume_needs_no_write_authority():
    async def run():
        browser, store = Browser(), Store()
        bridge = VoiceV2Bridge(browser, store)
        bridge.deadline = datetime.now(UTC) + timedelta(seconds=5)
        bridge.native = True
        bridge.speech.floor_ms = 200
        await bridge._server_content(
            None,
            {
                "outputTranscription": {"text": "Cần đọc lại lịch hiện tại."},
                "generationComplete": True,
            },
            new_audio=True,
        )
        assert any(f.get("role") == "assistant" for f in browser.sent)
        assert not store.actions

    asyncio.run(run())


def test_setup_and_history_have_independent_bounds_with_b2_memory():
    from app.agent.voice_context import bound_voice_history
    from app.agent.voice_protocol import encoded

    config = setup_v2(datetime.now(UTC), Store().settings)
    config["setup"]["systemInstruction"]["parts"].append({"text": "x" * 8192})
    config, seed, included, limited = bound_voice_history(
        config,
        [{"role": "user", "parts": [{"text": "Giữ quyết định A."}]}],
    )
    assert included == 1 and seed is not None and not limited
    assert len(encoded(config).encode()) <= 65536
    assert len(encoded(seed).encode()) <= 32768
    with pytest.raises(Exception, match="voice_setup_limit"):
        oversized = {"setup": {"systemInstruction": {"parts": [{"text": "x" * 70000}]}}}
        bound_voice_history(oversized, [])


def test_titles_are_model_content_and_never_a_voice_permission_comparison():
    from test_mimi_voice_v2 import _plan

    from app.agent.voice_v2_store import automatic_plan

    for title in ("[TRAINING] alpha", "Training: alpha", '"A literal title"'):
        assert automatic_plan(_plan([(title, None)]))


def test_actual_setup_blocks_actions_and_scalar_notices_never_interrupt():
    from app.agent.voice_context import configure_voice_setup
    from app.agent.voice_v2_outcome import committed
    from app.agent.voice_v2_protocol import ACTION_TOOLS

    config = configure_voice_setup(setup_v2(datetime.now(UTC), Store().settings))
    declarations = config["setup"]["tools"][0]["functionDeclarations"]
    action_names = {name.replace(".", "_") for name in ACTION_TOOLS}
    assert all(d.get("behavior") == "BLOCKING" for d in declarations if d["name"] in action_names)

    async def run():
        bridge = VoiceV2Bridge(Browser(), Store())
        bridge.deadline = datetime.now(UTC) + timedelta(seconds=5)
        live = Live()
        bridge.pending_notice = committed("applied")
        await bridge._send_action_context(live, revision=bridge.output_revision)
        (note,) = live.frames
        assert note["clientContent"]["turnComplete"] is False
        assert "voice_action_committed" in str(note)
        assert "State this outcome" not in str(note)

    asyncio.run(run())


@pytest.mark.parametrize("event_kind", ["new_speech", "cancel", "disconnect"])
def test_receiving_new_input_during_commit_revokes_previous_action(monkeypatch, event_kind):
    from app.agent.voice_v2_outcome import VoiceActionOutcome

    async def run():
        browser, store, live = Browser(), Store(), Live()
        entered, release = asyncio.Event(), asyncio.Event()
        allowed = []
        bridge = VoiceV2Bridge(browser, store)
        bridge.deadline = datetime.now(UTC) + timedelta(seconds=5)
        bridge.forwarded_ms = 200
        bridge.signal.record(PCM)
        bridge.input_text = "Tạo việc A."
        bridge.speech.activity({"type": "ACTIVITY_START", "audioOffset": "0.01s"}, 200)
        bridge.speech.activity({"type": "ACTIVITY_END", "audioOffset": "0.15s"}, 200)
        bridge.epoch = 1
        bridge.actions = {"action": ("task.collection_candidate.v1", {"entries": []})}
        bridge.action_wires = {"action": "task_collection_candidate_v1"}

        async def delayed(*args):
            is_active = args[-1]
            entered.set()
            await release.wait()
            allowed.append(is_active())
            return VoiceActionOutcome("rejected", "voice_turn_expired")

        store.act = delayed
        await live.events.get()  # setup was already observed by the transport
        completing = asyncio.create_task(bridge._complete_with_live_events(live))
        await entered.wait()
        if event_kind == "new_speech":
            live.emit({"voiceActivity": {"type": "ACTIVITY_START", "audioOffset": "0.21s"}})
        elif event_kind == "cancel":
            live.emit({"toolCallCancellation": {"ids": ["action"]}})
        else:
            live.emit(OSError("synthetic upstream close"))
        for _ in range(30):
            if bridge.action_cancelled:
                break
            await asyncio.sleep(0)
        assert bridge.action_cancelled
        release.set()
        if event_kind == "disconnect":
            from app.agent.voice_v2_bridge import _UpstreamDrop

            with pytest.raises(_UpstreamDrop):
                await completing
        else:
            await completing
            assert bridge.deferred_events
        assert allowed == [False]
        if event_kind == "cancel":
            assert not any("toolResponse" in frame for frame in live.frames)

    asyncio.run(run())


def test_ambiguous_commit_never_sends_applied_false_or_success_response():
    from app.agent.voice_protocol import VoiceError
    from app.agent.voice_v2_outcome import VoiceActionOutcome

    async def run():
        bridge = VoiceV2Bridge(Browser(), Store())
        bridge.deadline = datetime.now(UTC) + timedelta(seconds=5)
        bridge.input_text = "Tạo việc A."
        bridge.epoch = 1
        bridge.forwarded_ms = 200
        bridge.signal.record(PCM)
        bridge.speech.activity({"type": "ACTIVITY_START", "audioOffset": "0.01s"}, 200)
        bridge.speech.activity({"type": "ACTIVITY_END", "audioOffset": "0.15s"}, 200)
        bridge.actions = {"uncertain": ("task.collection_candidate.v1", {})}
        bridge.action_wires = {"uncertain": "task_collection_candidate_v1"}
        bridge.provider_turn_complete = True

        async def unknown(*args):
            return VoiceActionOutcome("unknown", "voice_result_ambiguous")

        bridge.store.act = unknown
        live = Live()
        with pytest.raises(VoiceError, match="voice_action_outcome_unknown"):
            await bridge._complete_turn(live)
        assert not any("toolResponse" in frame for frame in live.frames)
        assert not any(f["type"] == "action_updated" for f in bridge.browser.sent)
        assert bridge.action_outcomes["voice_result_ambiguous"] == 1

    asyncio.run(run())
