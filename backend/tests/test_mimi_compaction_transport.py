"""Truncated semantic output must retain billing metadata, never activate."""

import pytest

from app.agent.openrouter import RouteContractError, parse_compaction_completion


@pytest.mark.parametrize(
    "reason,content,code",
    [
        ("length", '{"summary":"cut', "compaction_summary_output_truncated"),
        ("stop", '{"summary":"cut', "compaction_summary_payload_invalid"),
        (
            "length",
            '{"summary":"ok","constraints":[],"supersessions":[],"resolutions":[]}',
            "compaction_summary_output_truncated",
        ),
    ],
)
def test_invalid_summary_preserves_usage_without_provider_content(reason, content, code):
    payload = {
        "id": "synthetic-summary-1",
        "model": "synthetic-model",
        "provider": "synthetic-provider",
        "usage": {"cost": 0.00012, "prompt_tokens": 10, "completion_tokens": 2048},
        "choices": [{"finish_reason": reason, "message": {"content": content}}],
    }
    with pytest.raises(RouteContractError) as caught:
        parse_compaction_completion(payload)
    error = caught.value
    assert str(error) == code
    assert error.response_id == "synthetic-summary-1"
    assert error.usage == payload["usage"]
    assert error.provider == "synthetic-provider"
    assert error.model == "synthetic-model"
    assert content not in str(error)
