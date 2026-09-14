"""Static safety contracts for the guarded local sandbox runner."""

import json
from pathlib import Path

import pytest

from scripts import mimi_sandbox


def test_runtime_urls_are_exact_loopback_synthetic_targets() -> None:
    state = mimi_sandbox._new_state()
    urls = mimi_sandbox._validated_urls(state)
    assert all("127.0.0.1:55455/microsched_mimi_p0_055" in value for value in urls)
    assert all("neon.tech" not in value and "fly.dev" not in value for value in urls)


def test_changed_runtime_marker_fails_closed(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "runtime.json"
    state = mimi_sandbox._new_state()
    state["environment_id"] = "not-the-authorized-sandbox"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(mimi_sandbox, "STATE_PATH", state_path)
    with pytest.raises(mimi_sandbox.SandboxRefusal, match="marker"):
        mimi_sandbox._load_state()


def test_fixture_digest_is_stable_and_manifest_scoped() -> None:
    first = mimi_sandbox.fixture_digest()
    second = mimi_sandbox.fixture_digest()
    assert first == second
    assert len(first) == 64


def test_reset_uses_exact_manifest_ids_not_truncate_or_broad_delete() -> None:
    source = Path(mimi_sandbox.__file__).read_text(encoding="utf-8")
    assert "TRUNCATE" not in source.upper()
    assert "DROP DATABASE" not in source.upper()
    assert "WHERE id = ANY($1::uuid[])" in source
    reset_source = source[source.index("async def reset") : source.index("async def verify")]
    assert "review" not in reset_source
