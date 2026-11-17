"""Owner81 C2/C3: actual manual Confirm, socket epochs and durable six-task receipt."""

import base64
import json
from concurrent.futures import Future
from contextlib import asynccontextmanager

import pytest
import test_mimi_voice_v2_pg as fixtures
from test_mimi_voice_pg import HEADERS, endpoint
from test_mimi_voice_v2 import Live, proposal
from test_mimi_voice_v2_pg import confirm, receive_to, rows, say, snapshot, start, turn

from app.agent import voice_bridge, voice_v2_bridge

pytestmark = pytest.mark.pg
v2_runtime = fixtures.v2_runtime


def test_c2_confirm_six_wakes_fences_old_socket_and_seeds_only_committed_scalar(
    v2_runtime, monkeypatch
):
    rt = v2_runtime
    names = [f"{rt.stem} manual81 {i}" for i in range(6)]
    cid, issued, _ = start(rt, monkeypatch)
    sockets, batches = [], iter([turn("Prepare the whole group.", proposal("six", names))])
    scalar = Future()
    # Prove the post-commit wake, rather than waiting for the fallback poll.
    monkeypatch.setattr(voice_v2_bridge, "WATCHDOG_INTERVAL", 10)
    monkeypatch.setattr(voice_v2_bridge, "AUTH_WINDOW", 15)

    class Socket(Live):
        async def send(self, raw):
            value = json.loads(raw)
            await super().send(raw)
            if "audio" in value.get("realtimeInput", {}):
                self.emit(*next(batches, ()))
            content = value.get("clientContent", {})
            if content.get("turnComplete") is False and not scalar.done():
                scalar.set_result(content)

    @asynccontextmanager
    async def connect(settings, *, run_id):
        assert str(run_id) == issued["run_id"]
        socket = Socket()
        sockets.append(socket)
        yield socket

    monkeypatch.setattr(voice_bridge, "connect_provider", connect)
    with rt.client.websocket_connect(endpoint(cid, issued), headers=HEADERS) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == ["preview"]
        state = snapshot(rt, cid)
        (pending,) = [c for c in state["change_sets"] if c["state"] == "pending"]
        assert len(pending["operation"]["args"]["entries"]) == 6
        assert not state["receipts"] and not rows(rt)
        result = confirm(rt, pending)
        assert result.is_success, result.text
        observed = receive_to(ws, "action_updated")
        assert any(f["type"] == "interrupted" for f in observed)
        assert observed[-1]["receipt_id"] == result.json()["id"]
        # This event comes from the obsolete model AFTER receipt observation.
        sockets[0].emit(
            {
                "serverContent": {
                    "outputTranscription": {"text": "Obsolete preview output"},
                    "modelTurn": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "audio/pcm;rate=24000",
                                    "data": base64.b64encode(b"\x01\x00").decode(),
                                }
                            }
                        ]
                    },
                    "turnComplete": True,
                }
            }
        )
        resumed = receive_to(ws, "resumed")
        assert not any(f.get("role") == "assistant" for f in resumed)
        assert resumed[-1]["context_retained"] is False and len(sockets) == 2
        note = scalar.result(timeout=2)
        text = note["turns"][0]["parts"][0]["text"]
        status = json.loads(text.split(": ", 1)[1])
        assert status["status"] == "applied" and status["applied"] is True
        assert "receipt_ref" in status and result.json()["id"] not in text
        assert not any("realtimeInput" in f or "toolResponse" in f for f in sockets[1].frames)
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
    state = snapshot(rt, cid)
    (receipt,) = state["receipts"]
    assert receipt["result"]["count"] == 6 and len(rows(rt)) == 6
    assert len([m for m in state["messages"] if m["applied_receipt_id"] == receipt["id"]]) == 1


def test_c3_failed_confirmation_never_wakes_or_exposes_manual_success(v2_runtime, monkeypatch):
    rt = v2_runtime
    cid, issued, _ = start(
        rt, monkeypatch, turn("Prepare six.", proposal("six", [f"{rt.stem} {i}" for i in range(6)]))
    )
    wakes = []
    monkeypatch.setattr(voice_v2_bridge, "signal_voice_manual_confirm", wakes.append)
    with rt.client.websocket_connect(endpoint(cid, issued), headers=HEADERS) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == ["preview"]
        (pending,) = snapshot(rt, cid)["change_sets"]
        pending = {**pending, "digest": "0" * 64}
        result = confirm(rt, pending)
        assert not result.is_success and not wakes
        assert not snapshot(rt, cid)["receipts"] and not rows(rt)
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
