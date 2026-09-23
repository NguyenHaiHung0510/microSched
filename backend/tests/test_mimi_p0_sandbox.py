"""Static safety contracts for the guarded local sandbox runner."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts import mimi_sandbox


def test_runtime_urls_are_exact_loopback_synthetic_targets() -> None:
    state = mimi_sandbox._new_state()
    assert state["volume"] == mimi_sandbox.VOLUME
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
    assert "reset refuses unowned rows" in reset_source


def test_runtime_environment_drops_host_credentials_and_disables_dotenv(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "must-not-propagate")
    monkeypatch.setenv("NEON_OWNER_URL", "must-not-propagate")
    monkeypatch.setattr(mimi_sandbox, "_git_sha", lambda: "candidate-sha")
    environment = mimi_sandbox._runtime_env(mimi_sandbox._new_state())
    assert "GOOGLE_CLIENT_SECRET" not in environment
    assert "NEON_OWNER_URL" not in environment
    assert environment["MIMI_P0_DISABLE_DOTENV"] == "1"
    assert environment["ENABLE_INPROCESS_CRON"] == "false"
    assert environment["DATABASE_URL"].startswith("postgresql://microsched_app:")


def test_local_runtime_state_is_excluded_from_docker_context() -> None:
    patterns = (mimi_sandbox.REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert ".local" in patterns


def test_recorded_pid_must_still_own_expected_listener(monkeypatch) -> None:
    monkeypatch.setattr(mimi_sandbox, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(mimi_sandbox, "_listener_pid", lambda port: 902)
    monkeypatch.setattr(mimi_sandbox.os, "name", "nt")
    with pytest.raises(mimi_sandbox.SandboxRefusal, match="does not own"):
        mimi_sandbox._owned_listener_or_refuse(901, mimi_sandbox.BACKEND_PORT, "backend")


def _inspect_result(*, host_port="55455", volume="microsched-mimi-p0-055-db"):
    payload = [
        {
            "Config": {
                "Image": "pgvector/pgvector:pg18",
                "Labels": {"microsched.synthetic": "mimi-p0-055"},
            },
            "HostConfig": {
                "PortBindings": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": host_port}]}
            },
            "Mounts": [
                {
                    "Type": "volume",
                    "Name": volume,
                    "Destination": "/var/lib/postgresql",
                }
            ],
            "State": {"Running": True},
        }
    ]
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (_inspect_result(host_port="55456"), "loopback port"),
        (_inspect_result(volume="somebody-elses-volume"), "sandbox volume"),
    ],
)
def test_container_identity_requires_exact_binding_and_volume(monkeypatch, result, message) -> None:
    monkeypatch.setattr(mimi_sandbox.subprocess, "run", lambda *args, **kwargs: result)
    with pytest.raises(mimi_sandbox.SandboxRefusal, match=message):
        mimi_sandbox._docker_inspect()


def test_occupied_port_without_recorded_owner_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(mimi_sandbox, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(mimi_sandbox, "_port_bound", lambda port: port == mimi_sandbox.BACKEND_PORT)
    with pytest.raises(mimi_sandbox.SandboxRefusal, match="unrecorded process"):
        mimi_sandbox._assert_app_ports_owned(mimi_sandbox._new_state())


def test_stop_timeout_still_stops_exact_container(monkeypatch) -> None:
    calls = []
    ticks = iter((0.0, 11.0))
    monkeypatch.setattr(mimi_sandbox, "_load_state", lambda: mimi_sandbox._new_state())
    monkeypatch.setattr(mimi_sandbox, "_owned_listener_or_refuse", lambda *args: 901)
    monkeypatch.setattr(mimi_sandbox, "_stop_pid", lambda pid: None)
    monkeypatch.setattr(mimi_sandbox, "_port_bound", lambda port: True)
    monkeypatch.setattr(mimi_sandbox.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(mimi_sandbox.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(mimi_sandbox, "_docker_inspect", lambda: {"State": {"Running": True}})
    monkeypatch.setattr(mimi_sandbox, "_run", lambda args, **kwargs: calls.append(args))

    with pytest.raises(RuntimeError, match="did not stop"):
        mimi_sandbox.stop()
    assert calls == [["docker", "stop", mimi_sandbox.CONTAINER]]


@pytest.mark.skipif(
    os.environ.get("MIMI_P0_INTEGRATION") != "1", reason="requires exact local Mimi P0 Postgres"
)
def test_reset_refuses_unowned_tracker_dependents_then_recovers() -> None:
    import asyncio
    from uuid import UUID

    import asyncpg

    from app.core.database_urls import asyncpg_dsn

    state = mimi_sandbox._load_state()
    _, _, app_url = mimi_sandbox._validated_urls(state)
    unowned_id = UUID("70000000-0000-7000-8000-000000000001")
    tracker_id = UUID("41000000-0000-7000-8000-000000000001")

    async def exercise() -> None:
        connection = await asyncpg.connect(asyncpg_dsn(app_url), timeout=20)
        try:
            await connection.execute(
                "INSERT INTO microsched.entry "
                "(id,tracker_id,amount,occurred_at,note_md,deleted_at) "
                "VALUES ($1,$2,NULL,'2030-01-15T00:00:00Z',NULL,NULL) "
                "ON CONFLICT (id) DO NOTHING",
                unowned_id,
                tracker_id,
            )
            with pytest.raises(mimi_sandbox.SandboxRefusal, match="entry=1"):
                await mimi_sandbox.reset(state)
        finally:
            await connection.execute("DELETE FROM microsched.entry WHERE id=$1", unowned_id)
            await connection.close()
        result = await mimi_sandbox.reset(state)
        assert result["entries"] == 5

    asyncio.run(exercise())
