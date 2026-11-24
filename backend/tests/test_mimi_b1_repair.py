"""Caption timing is never a write gate; lifecycle and retired offsets are."""

import pytest
from test_mimi_voice_v2 import Browser, Store

from app.agent.voice_v2_bridge import VoiceV2Bridge


@pytest.mark.parametrize("new_pcm", [False, True])
def test_old_unlabelled_caption_cannot_allocate_fresh_activity(new_pcm):
    bridge = VoiceV2Bridge(Browser(), Store())
    bridge.speech.floor_ms = 150
    bridge.forwarded_ms = 400 if new_pcm else 200
    bridge._track_input_final({"text": "Tạo việc A."})
    assert bridge.speech.bind(1, 2, ["fresh"]) is None
    bridge.speech.activity({"type": "ACTIVITY_START", "audioOffset": "0.210s"}, 400)
    bridge.speech.activity({"type": "ACTIVITY_END", "audioOffset": "0.350s"}, 400)
    first = bridge.speech.bind(1, 2, ["fresh"])
    bridge._track_input_final({"text": "Tạo việc A."})
    assert bridge.speech.bind(1, 2, ["fresh"]) == first


def test_timed_old_caption_is_withheld_and_does_not_change_audio_binding():
    bridge = VoiceV2Bridge(Browser(), Store())
    bridge.speech.floor_ms = 200
    bridge.forwarded_ms = 400
    for start, end in (("0.020s", "0.160s"), ("0.010s", "0.150s")):
        assert not bridge._track_input_final(
            {
                "text": "Tạo việc A.",
                "startOffset": start,
                "endOffset": end,
            }
        )
        assert bridge.speech.bind(1, 2, ["fresh"]) is None
