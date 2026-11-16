"""Small guards around the full-store grouped-repair witnesses."""

import pytest
from test_mimi_voice_v2 import Browser, Store

from app.agent.voice_v2_bridge import VoiceV2Bridge


@pytest.mark.parametrize("new_pcm", [False, True])
def test_prior_final_can_only_settle_without_competing_new_pcm(new_pcm):
    bridge = VoiceV2Bridge(Browser(), Store())
    bridge.speech.floor_ms = 150
    bridge.unsettled_speech = [(10, 150)]
    bridge.retired_audio_ms = 200
    bridge.forwarded_ms = 400 if new_pcm else 200
    assert not bridge._track_input_final({"text": "Tạo việc A."})
    assert bool(bridge.unsettled_speech) == new_pcm
    bridge.forwarded_ms = 400
    bridge.speech.activity({"type": "ACTIVITY_START", "audioOffset": "0.210s"}, 400)
    assert bridge._track_input_final({"text": "Tạo việc B."})
    assert bridge.speech.final_ambiguous == new_pcm


def test_only_exact_timed_old_window_retires_its_outstanding_final():
    bridge = VoiceV2Bridge(Browser(), Store())
    bridge.speech.floor_ms = 200
    bridge.forwarded_ms = 400
    bridge.unsettled_speech = [(10, 150)]
    assert not bridge._track_input_final(
        {
            "text": "Tạo việc A.",
            "startOffset": "0.020s",
            "endOffset": "0.160s",
        }
    )
    assert bridge.unsettled_speech == [(10, 150)]
    assert not bridge._track_input_final(
        {
            "text": "Tạo việc A.",
            "startOffset": "0.010s",
            "endOffset": "0.150s",
        }
    )
    assert bridge.unsettled_speech == []
