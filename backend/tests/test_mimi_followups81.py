"""Owner81 C1-C6: real seams with synthetic clocks, stores and transports only."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from test_mimi_voice_v2 import Browser, Live, Store

from app.agent.tools import calendar_reads
from app.agent.tools.registry import tools_for_settings
from app.agent.voice_v2_bridge import VoiceV2Bridge, _UpstreamDrop
from app.agent.voice_v2_intent import VoiceTurnBinding
from app.agent.voice_v2_outcome import committed
from app.agent.voice_v2_protocol import setup_v2
from app.agent.voice_v2_store import VoiceContextChanged, VoiceV2Store, execute_voice_read
from app.core.settings import Settings
from app.domain.calendar_read import CalendarReadRequest, CalendarReadResult


@pytest.mark.parametrize(
    "day,weekday",
    [
        ("2026-11-18", 3),
        ("2026-11-22", 7),
        ("2026-11-23", 1),
        ("2026-11-30", 1),
        ("2026-12-01", 2),
        ("2026-12-31", 4),
        ("2027-01-01", 5),
        ("2028-02-29", 2),
        ("2028-03-01", 3),
    ],
)
def test_c1_same_typed_calendar_facts_reach_chat_and_voice(monkeypatch, day, weekday):
    async def scenario():
        async def page(*args, **kwargs):
            return (), False

        monkeypatch.setattr(calendar_reads, "read_calendar_page", page)
        settings = Settings(_env_file=None, mimi_calendar_read_enabled=True)
        args = {"date": day, "kinds": ["task"]}
        chat = await calendar_reads.execute_calendar_tool(
            None, "calendar.read.v1", args, settings=settings
        )
        voice = await execute_voice_read(None, "calendar.read.v1", args, settings=settings)
        assert chat["calendar_facts"]["requested"] == voice["calendar_facts"]["requested"]
        (fact,) = chat["calendar_facts"]["requested"]
        assert fact["date"] == day and fact["iso_weekday"] == weekday
        assert (
            fact["weekday_vi"]
            == ("thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật")[
                weekday - 1
            ]
        )
        assert chat["rows"] == [] and chat["coverage"] == "complete"
        assert calendar_reads.calendar_result_bindings("calendar.read.v1", chat) == {}
        assert CalendarReadResult.model_validate(chat).model_dump(mode="json") == chat

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "instant,local_day",
    [
        ("2026-11-17T16:59:59+00:00", "2026-11-17"),
        ("2026-11-17T17:00:00+00:00", "2026-11-18"),
    ],
)
def test_c1_facts_anchor_today_at_vietnam_midnight(instant, local_day):
    result = CalendarReadResult(
        requested_dates=CalendarReadRequest(date="2026-11-18").days(),
        kinds=("task",),
        rows=(),
        count=0,
        coverage="partial",
        has_more=False,
        continued=True,
        next_cursor=None,
        data_as_of=datetime.fromisoformat(instant),
    ).model_dump(mode="json")
    assert result["calendar_facts"]["observed_today"]["date"] == local_day
    assert result["calendar_facts"]["requested"][0]["date"] == "2026-11-18"
    assert result["coverage"] == "partial" and result["continued"] is True


def test_c4_voice_projection_has_no_chat_confirmation_contradiction():
    settings = Settings(_env_file=None, mimi_collection_enabled=True)
    config = setup_v2(datetime.now(UTC), settings)["setup"]
    declarations = config["tools"][0]["functionDeclarations"]
    for tool in declarations:
        if tool.get("behavior") == "BLOCKING":
            assert "Never executes before explicit confirmation" not in tool["description"]
            assert "preview_required" in tool["description"]
    assert "it still needs its own Confirm" not in str(config["systemInstruction"])
    chat = {t["function"]["name"]: t["function"] for t in tools_for_settings(settings)}
    assert (
        "Never executes before explicit confirmation"
        in (chat["task.collection_candidate.v1"]["description"])
    )


@pytest.mark.parametrize(
    "calls,expected",
    [
        (
            [("task.collection_candidate.v1", {"entries": [{"action": "create", "fields": {}}]})],
            "invalid_shape",
        ),
        ([("task.collection_candidate.v1", {})], "insufficient_data"),
        ([("task.collection_candidate.v1", {"entries": []})] * 2, "multiple_proposals"),
    ],
)
def test_c5_plan_reasons_are_scalar_and_never_repair_or_echo(calls, expected):
    async def scenario():
        store = object.__new__(VoiceV2Store)
        store.settings = Settings(_env_file=None, mimi_collection_enabled=True)
        binding = VoiceTurnBinding(1, 1, tuple(str(i) for i in range(len(calls))), 1, 10)
        outcome = await store.act(1, 1, calls, binding, None, lambda: True)
        assert outcome.reason == "voice_plan_invalid"
        assert outcome.model_result()["detail"]["code"] == expected
        assert outcome.model_result()["detail"]["next_step"] != "retry"
        assert outcome.event()["detail"] == outcome.model_result()["detail"]
        assert "entries" not in json.dumps(outcome.model_result())

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "internal,expected",
    [
        ("voice_undo_receipt_missing", "receipt_missing"),
        ("voice_undo_receipt_not_exposed", "receipt_not_exposed"),
        ("undo_post_version_stale", "receipt_stale"),
        ("voice_undo_latest_receipt_not_eligible", "latest_inverse"),
        ("receipt_has_no_durable_inverse", "receipt_unavailable"),
        ("unrecognized-private-payload", "receipt_unavailable"),
    ],
)
def test_c5_undo_reason_uses_known_failure_without_latest_fallback(internal, expected):
    async def scenario():
        store = object.__new__(VoiceV2Store)
        store.settings = Settings(_env_file=None, mimi_collection_enabled=True)
        invoked = []

        async def fail(*args):
            invoked.append(True)
            raise HTTPException(409, internal)

        store._act = fail
        outcome = await store.act(
            1,
            1,
            [("voice.undo_latest.v1", {})],
            VoiceTurnBinding(1, 1, ("id",), 1, 10),
            None,
            lambda: True,
        )
        assert invoked == [True] and outcome.reason == "voice_undo_unavailable"
        assert outcome.model_result()["detail"]["code"] == expected
        assert internal not in json.dumps(outcome.model_result())

    asyncio.run(scenario())


@pytest.mark.parametrize("held", ["source", "browser"])
def test_c2_observed_manual_receipt_fences_render_waiting_on_source_lock(held):
    async def scenario():
        browser, store = Browser(), Store()
        entered, release, observed = asyncio.Event(), asyncio.Event(), asyncio.Event()

        @asynccontextmanager
        async def gate(sources=None, **kwargs):
            if sources is not None:
                entered.set()
                if held == "source":
                    await release.wait()
            yield

        async def status():
            observed.set()
            return committed(
                "applied", receipt_id="synthetic-receipt", receipt_ref="vr_" + "a" * 24
            )

        store.live_gate, store.action_status = gate, status
        bridge = VoiceV2Bridge(browser, store)
        bridge.deadline = datetime.now(UTC) + timedelta(seconds=10)
        bridge.epoch, bridge.online, bridge.awaiting_manual = 1, True, True
        if held == "browser":
            await bridge.browser_lock.acquire()
        sending = asyncio.create_task(
            bridge._render(
                [b"old-pcm", {"type": "transcript", "role": "assistant", "text": "old-output"}],
                first_answer=True,
            )
        )
        await entered.wait()
        if held == "browser":
            checking = asyncio.create_task(bridge._manual_status())
            await observed.wait()
            bridge.browser_lock.release()
            await checking
        else:
            await bridge._manual_status()
        release.set()
        await sending
        frames = list(browser.frames._queue)
        assert b"old-pcm" not in frames
        assert not any(isinstance(f, dict) and f.get("role") == "assistant" for f in frames)
        assert any(f.get("type") == "interrupted" for f in browser.sent)
        assert bridge.pending_notice.receipt_id == "synthetic-receipt"
        assert not store.actions and bridge.refresh_context_history
        await bridge._manual_status()
        assert len([f for f in browser.sent if f["type"] == "action_updated"]) == 1

    asyncio.run(scenario())


def test_c3_notice_a_ack_cannot_clear_newer_notice_b():
    async def scenario():
        bridge = VoiceV2Bridge(Browser(), Store())
        bridge.deadline = datetime.now(UTC) + timedelta(seconds=10)
        first, newer = (
            committed("applied", receipt_ref="vr_" + "a" * 24),
            committed("undone", receipt_ref="vr_" + "b" * 24),
        )
        bridge.pending_notice = first

        class ReplacingLive(Live):
            async def send(self, raw):
                bridge.pending_notice = newer
                await super().send(raw)

        await bridge._send_action_context(ReplacingLive())
        assert bridge.pending_notice is newer

    asyncio.run(scenario())


def test_c3_unknown_status_delivery_keeps_scalar_and_never_replays_action():
    async def scenario():
        bridge = VoiceV2Bridge(Browser(), Store())
        bridge.deadline = datetime.now(UTC) + timedelta(seconds=10)
        notice = committed("applied", receipt_ref="vr_" + "a" * 24)
        bridge.pending_notice = notice

        class LostAcknowledgment(Live):
            async def send(self, raw):
                await super().send(raw)
                raise OSError("synthetic lost status acknowledgment")

        old, fresh = LostAcknowledgment(), Live()
        with pytest.raises(_UpstreamDrop):
            await bridge._send_action_context(old, check_sources=False)
        assert bridge.pending_notice is notice and bridge.send_uncertain
        await bridge._send_action_context(fresh, check_sources=False)
        assert bridge.pending_notice is None and not bridge.store.actions
        assert all("clientContent" in f for f in [*old.frames, *fresh.frames])
        # Transport uncertainty permits repeated scalar status, never a second
        # action. Exactly-once model receipt is not a claim of this protocol.

    asyncio.run(scenario())


def test_c3_no_visible_receipt_or_pending_action_has_no_false_manual_success():
    async def scenario():
        store, browser = Store(), Browser()
        visible = None

        async def status():
            return visible

        store.action_status = status
        bridge = VoiceV2Bridge(browser, store)
        bridge.deadline = datetime.now(UTC) + timedelta(seconds=10)
        bridge.online, bridge.awaiting_manual = True, True
        await bridge._manual_status()
        assert not browser.sent and bridge.awaiting_manual
        visible = committed("applied", receipt_id="synthetic")
        bridge.actions = {"pending": ("task.collection_candidate.v1", {})}
        await bridge._manual_status()
        assert not browser.sent and bridge.awaiting_manual and bridge.actions

    asyncio.run(scenario())


@pytest.mark.parametrize("newer_preview", [False, True])
def test_c3_status_read_cannot_commit_or_mislabel_a_newer_preview(monkeypatch, newer_preview):
    from app.agent import receipt_history

    async def scenario():
        conversation = SimpleNamespace(id=uuid4())
        identity = uuid4()
        parent = SimpleNamespace(
            execution_lease={
                "manual_action_receipt": str(identity),
                "manual_action_status": "applied",
                "last_action_receipt": None if newer_preview else str(identity),
                "last_action_status": "preview" if newer_preview else "applied",
            }
        )
        store = object.__new__(VoiceV2Store)
        store.auth = None

        @asynccontextmanager
        async def factory():
            yield object()  # No write/commit API: status must be a read projection.

        async def boundary(db):
            return conversation, parent

        async def bound(*args):
            assert not newer_preview
            return SimpleNamespace(id=identity), None, None, conversation

        store.factory, store.boundary = factory, boundary
        monkeypatch.setattr(receipt_history, "bound_receipt", bound)
        outcome = await store.action_status()
        if newer_preview:
            assert outcome is None
        else:
            assert outcome.receipt_id == str(identity) and outcome.receipt_ref is None

    asyncio.run(scenario())


def test_c6_interrupted_no_write_turn_resets_only_after_clean_terminal():
    async def scenario():
        bridge = VoiceV2Bridge(Browser(), Store())
        bridge.deadline = datetime.now(UTC) + timedelta(seconds=10)
        bridge.forwarded_ms = 200
        await bridge._server_content(None, {"interrupted": True}, new_audio=True)
        assert bridge.epoch_ambiguous and not bridge.refresh_context_history
        with pytest.raises(VoiceContextChanged):
            await bridge._server_content(None, {"turnComplete": True}, new_audio=True)
        assert bridge.refresh_context_history and not bridge.store.actions

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "state,expected",
    [
        ("tainted_and_no_vad", "activity_tainted_epoch"),
        ("cancelled", "activity_cancelled"),
        ("missing_vad", "activity_timing"),
        ("silence", "activity_signal"),
    ],
)
def test_c5_activity_precedes_plan_interpretation_without_caption_authority(state, expected):
    async def scenario():
        bridge = VoiceV2Bridge(Browser(), Store())
        bridge.deadline = datetime.now(UTC) + timedelta(seconds=10)
        bridge.epoch, bridge.forwarded_ms = 1, 200
        bridge.actions = {"fresh": ("task.collection_candidate.v1", {"entries": []})}
        bridge.action_wires = {"fresh": "task_collection_candidate_v1"}
        if state in {"silence", "cancelled"}:
            bridge.speech.activity({"type": "ACTIVITY_START", "audioOffset": "0.01s"}, 200)
            bridge.speech.activity({"type": "ACTIVITY_END", "audioOffset": "0.15s"}, 200)
        if state == "cancelled":
            bridge.action_cancelled = True
        bridge.epoch_ambiguous = state == "tainted_and_no_vad"
        if bridge.epoch_ambiguous:
            with pytest.raises(VoiceContextChanged):
                await bridge._complete_turn(Live())
        else:
            await bridge._complete_turn(Live())
        (outcome,) = [f for f in bridge.browser.sent if f["type"] == "action_updated"]
        assert outcome["detail"]["code"] == expected
        assert not bridge.store.actions

    asyncio.run(scenario())
