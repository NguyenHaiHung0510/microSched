"""Batch 74: the provider event boundary, independent of caption content."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from test_mimi_voice_v2 import Browser, Live, Store, audio, proposal, speech

from app.agent import voice_bridge
from app.agent.voice_v2_bridge import VoiceV2Bridge
from app.agent.voice_v2_intent import VoiceTurnBinding
from app.agent.voice_v2_protocol import UNDO_TOOL, setup_v2
from app.agent.voice_v2_store import voice_candidate


@asynccontextmanager
async def voice(monkeypatch):
    browser, store, live = Browser(), Store(), Live()

    @asynccontextmanager
    async def connect(_settings, *, run_id):
        assert run_id == store.run_id
        yield live

    monkeypatch.setattr(voice_bridge, "connect_provider", connect)
    now = datetime.now(UTC)
    task = asyncio.create_task(
        VoiceV2Bridge(browser, store).run(
            setup_v2(now, store.settings), None, now + timedelta(seconds=10)
        )
    )
    try:
        await browser.until("ready")
        await live.sent.get()
        yield browser, store, live
    finally:
        await browser.inbound.put({"type": "websocket.disconnect"})
        assert await task == "voice_browser_disconnected"


def test_voice_does_not_need_caption_to_offer_one_live_action(monkeypatch):
    async def scenario():
        async with voice(monkeypatch) as (browser, store, live):
            await audio(browser, live)
            start, end, _, complete = speech("Caption not received.")
            live.emit(start, end, proposal("fresh", ["New task"]), complete)
            assert (await browser.until("action_updated"))["status"] == "applied"
            assert len(store.actions) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("split_frames", [False, True])
def test_voice_mixed_replay_cannot_apply_surviving_fragment(monkeypatch, split_frames):
    async def scenario():
        async with voice(monkeypatch) as (browser, store, live):
            await audio(browser, live)
            start, end, caption, complete = speech("Tạo việc A.")
            live.emit(start, end, caption, proposal("previous", ["A"]), complete)
            assert (await browser.until("action_updated"))["status"] == "applied"
            await browser.until("turn_complete")
            await live.sent.get()  # Exact final result for the first proposal.

            await audio(browser, live)
            start, end, caption, complete = speech("Tạo việc B.", base=0.2)
            replay = proposal("previous", ["A"])
            call = proposal("fragment", ["B"])
            if split_frames:
                live.emit(start, end, caption, replay, call, complete)
            else:
                call["toolCall"]["functionCalls"][:0] = replay["toolCall"]["functionCalls"]
                live.emit(start, end, caption, call, complete)
            assert (await browser.until("action_updated"))["status"] == "needs_clarification"
            assert len(store.actions) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["no_caption", "repeated", "late_caption"])
def test_caption_content_never_limits_a_current_bound_proposal(monkeypatch, mode):
    async def scenario():
        async with voice(monkeypatch) as (browser, store, live):
            for index in range(2):
                await audio(browser, live)
                start, end, caption, complete = speech("Same words.", base=index * 0.2)
                events = [start, end, proposal(f"tool-{index}", [f"Task {index}"])]
                if mode != "no_caption":
                    if mode == "late_caption":
                        caption["serverContent"]["inputTranscription"]["startOffset"] = "0.010s"
                        caption["serverContent"]["inputTranscription"]["endOffset"] = "0.150s"
                    events.append(caption)
                live.emit(*events, complete)
                assert (await browser.until("action_updated"))["status"] == "applied"
                await browser.until("turn_complete")
                await live.sent.get()
            assert [a[3].call_ids for a in store.actions] == [("tool-0",), ("tool-1",)]

    asyncio.run(scenario())


def test_duplicate_completed_tool_is_inert_even_with_new_audio(monkeypatch):
    async def scenario():
        async with voice(monkeypatch) as (browser, store, live):
            for index in range(2):
                await audio(browser, live)
                start, end, caption, complete = speech("Repeat.", base=index * 0.2)
                live.emit(start, end, caption, proposal("exact-id", ["Task"]), complete)
                if index == 0:
                    await browser.until("action_updated")
                await browser.until("turn_complete")
            assert len(store.actions) == 1
            responses = [f for f in live.frames if "toolResponse" in f]
            assert len(responses) == 1

    asyncio.run(scenario())


def test_cancelled_id_remains_retired_across_turns(monkeypatch):
    async def scenario():
        async with voice(monkeypatch) as (browser, store, live):
            await audio(browser, live)
            live.emit(
                {"toolCallCancellation": {"ids": ["retired-before-call"]}},
                *speech("First read-only turn."),
            )
            await browser.until("turn_complete")
            await audio(browser, live)
            start, end, caption, complete = speech("Another turn.", base=0.2)
            live.emit(start, end, caption, proposal("retired-before-call", ["Task"]), complete)
            await browser.until("turn_complete")
            assert not store.actions

    asyncio.run(scenario())


@pytest.mark.parametrize("order", ["before", "after", "split"])
def test_multiple_or_duplicate_action_proposals_are_not_coalesced(monkeypatch, order):
    async def scenario():
        async with voice(monkeypatch) as (browser, store, live):
            await audio(browser, live)
            start, end, caption, complete = speech("One complete request.")
            first, second = proposal("first", ["Task A"]), proposal("second", ["Task B"])
            duplicate = proposal("first", ["Task A"])
            calls = [first, duplicate] if order != "split" else [first, second]
            if order == "after":
                calls.reverse()
            live.emit(start, end, caption, *calls, complete)
            result = await browser.until("action_updated")
            if order == "split":
                # Real store rejects two candidates; this double records the exact
                # whole input so the coalescing contract is checked below.
                assert len(store.actions[0][2]) == 2
            else:
                assert result["status"] == "needs_clarification"
                assert not store.actions

    asyncio.run(scenario())


def test_one_typed_plan_and_strict_undo_selectors():
    create = (
        "task.collection_candidate.v1",
        {
            "entries": [
                {"action": "create", "fields": {"title": "A"}},
            ]
        },
    )
    with pytest.raises(ValueError, match="single_proposal"):
        voice_candidate([create, create], collection_enabled=True)
    assert voice_candidate([(UNDO_TOOL, {})], collection_enabled=True) == (
        UNDO_TOOL,
        {"target": "latest"},
    )
    assert voice_candidate([(UNDO_TOOL, {"target": "latest"})], collection_enabled=True)[1] == {
        "target": "latest"
    }
    for arguments in (
        {"target": "receipt"},
        {"target": "latest", "receipt_ref": "vr_" + "a" * 24},
        {"target": "receipt", "receipt_ref": "vr_" + "x" * 24},
        {"receipt_id": "synthetic-unexposed-id"},
    ):
        with pytest.raises(ValueError):
            voice_candidate([(UNDO_TOOL, arguments)], collection_enabled=True)
    binding = VoiceTurnBinding(2, 3, ("id",), 10, 150)
    assert binding.matches(3, 2, 1)
    assert not binding.matches(3, 1, 1)


@pytest.mark.parametrize("enabled", [False, True])
def test_vi_en_hint_is_v2_opt_in_and_v1_setup_stays_identical(monkeypatch, enabled):
    from app.agent.voice_protocol import setup

    now = datetime.now(UTC)
    original = setup(now)
    monkeypatch.setenv("MIMI_VOICE_V2_INPUT_LANGUAGE_HINTS", str(enabled).lower())
    configured = setup_v2(now, Store().settings)
    assert setup(now) == original
    assert configured["setup"]["inputAudioTranscription"] == (
        {"languageCodes": ["vi-VN", "en-US"]} if enabled else {}
    )
    assert configured["setup"]["generationConfig"] == original["setup"]["generationConfig"]
    prompt = str(configured["setup"]["systemInstruction"])
    assert "Vietnamese or English" in prompt
    assert "Never ask for a magic phrase" in prompt
    assert "preview_required" in prompt
