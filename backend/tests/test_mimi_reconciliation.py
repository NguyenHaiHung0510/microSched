"""Generation metadata must not manufacture a successful completion."""

import pytest

from app.agent import service


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"id": "gen-synthetic"}, "unknown"),
        ({"finish_reason": None, "cancelled": False}, "unknown"),
        ({"finish_reason": "stop", "cancelled": False}, "succeeded"),
        ({"finish_reason": "tool_calls", "cancelled": False}, "succeeded"),
        ({"finish_reason": "stop", "cancelled": True}, "failed"),
        ({"finish_reason": "length", "cancelled": False}, "failed"),
        ({"finish_reason": "error", "cancelled": False}, "failed"),
        ({"finish_reason": "content_filter", "cancelled": False}, "failed"),
        ({"finish_reason": "future_reason"}, "unknown"),
        ({"finish_reason": "stop", "cancelled": "false"}, "unknown"),
    ],
)
def test_generation_outcome_requires_explicit_usable_terminal(metadata, expected):
    assert service._generation_metadata_outcome(metadata) == expected
