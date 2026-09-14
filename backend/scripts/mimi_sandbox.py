"""Guarded local synthetic Mimi P0 sandbox: start/status/seed/reset/stop/verify."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
from sqlalchemy import URL
from sqlalchemy.engine import make_url

from app.core.database_urls import asyncpg_dsn

TASK_ID = "mimi-p0-055"
ENVIRONMENT_ID = "mimi-p0-local-055"
CONTAINER = "microsched-mimi-p0-055"
VOLUME = "microsched-mimi-p0-055-db"
CONTAINER_LABEL = "microsched.synthetic=mimi-p0-055"
DATABASE = "microsched_mimi_p0_055"
POSTGRES_PORT = 55455
BACKEND_PORT = 8000
FRONTEND_PORT = 5173
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend"
FIXTURE_ROOT = BACKEND_ROOT / "tests" / "fixtures" / "mimi_p0" / "v1"
LOCAL_ROOT = REPO_ROOT / ".local" / "mimi-p0"
STATE_PATH = LOCAL_ROOT / "runtime.json"
DOMAIN_RECEIPT = LOCAL_ROOT / "domain" / "seed-receipt.json"
REVIEW_ROOT = LOCAL_ROOT / "review"
REVIEW_BUNDLE_ID = UUID("50000000-0000-7000-8000-000000000001")
REVIEW_FEEDBACK_ID = UUID("50000000-0000-7000-8000-000000000002")


class SandboxRefusal(RuntimeError):
    """The requested target cannot be proven to be the dedicated local sandbox."""


def _new_state() -> dict[str, Any]:
    password = secrets.token_urlsafe(24)
    return {
        "schema_version": "mimi.sandbox-runtime.v1",
        "task_id": TASK_ID,
        "environment_id": ENVIRONMENT_ID,
        "container": CONTAINER,
        "database": DATABASE,
        "postgres_password": password,
        "migrator_password": secrets.token_urlsafe(24),
        "app_password": secrets.token_urlsafe(24),
        "encryption_master_key": base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
        "oauth_state_secret": secrets.token_urlsafe(32),
        "backend_pid": None,
        "frontend_pid": None,
    }


def _load_state(*, create: bool = False) -> dict[str, Any]:
    if not STATE_PATH.exists():
        if not create:
            raise SandboxRefusal(f"sandbox state missing: {STATE_PATH}")
        LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
        state = _new_state()
        _atomic_json(STATE_PATH, state)
    else:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if (
        state.get("task_id") != TASK_ID
        or state.get("environment_id") != ENVIRONMENT_ID
        or state.get("container") != CONTAINER
        or state.get("database") != DATABASE
    ):
        raise SandboxRefusal("runtime marker does not match the exact Mimi P0 sandbox")
    _validated_urls(state)
    return state


def _urls(state: dict[str, Any]) -> tuple[str, str, str]:
    common = {"host": "127.0.0.1", "port": POSTGRES_PORT, "database": DATABASE}
    owner = URL.create(
        "postgresql", username="postgres", password=state["postgres_password"], **common
    )
    migrator = URL.create(
        "postgresql",
        username="microsched_migrator",
        password=state["migrator_password"],
        **common,
    )
    app = URL.create(
        "postgresql", username="microsched_app", password=state["app_password"], **common
    )
    return tuple(url.render_as_string(hide_password=False) for url in (owner, migrator, app))


def _validated_urls(state: dict[str, Any]) -> tuple[str, str, str]:
    urls = _urls(state)
    for value in urls:
        parsed = make_url(value)
        if parsed.host not in {"127.0.0.1", "localhost", "::1"}:
            raise SandboxRefusal("sandbox database must use a loopback host")
        if parsed.port != POSTGRES_PORT or parsed.database != DATABASE:
            raise SandboxRefusal("sandbox database target does not match the exact port/name")
    return urls


def fixture_digest() -> str:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    for name in sorted(manifest["files"]):
        path = (FIXTURE_ROOT / name).resolve()
        if path.parent != FIXTURE_ROOT.resolve():
            raise SandboxRefusal("fixture manifest may not escape its version directory")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _runtime_env(state: dict[str, Any]) -> dict[str, str]:
    _, migrator, app = _validated_urls(state)
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "local",
            "ALLOW_PROD_DB_IN_LOCAL": "false",
            "DATABASE_URL": app,
            "NEON_MIGRATOR_URL": migrator,
            "ENCRYPTION_MASTER_KEY": state["encryption_master_key"],
            "OAUTH_STATE_SECRET": state["oauth_state_secret"],
            "ALLOWED_EMAILS": "owner@test.local",
            "ENABLE_INPROCESS_CRON": "false",
            "GIT_SHA": _git_sha(),
        }
    )
    return env


def _git_sha() -> str:
    result = _run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture=True)
    return result.stdout.strip()


def _run(
    args: list[str], *, cwd: Path = REPO_ROOT, env: dict[str, str] | None = None, capture=False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=capture,
    )


def _docker_inspect() -> dict[str, Any] | None:
    result = subprocess.run(
        ["docker", "inspect", CONTAINER], text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        return None
    payload = json.loads(result.stdout)[0]
    if payload.get("Config", {}).get("Labels", {}).get("microsched.synthetic") != TASK_ID:
        raise SandboxRefusal(f"container {CONTAINER!r} exists without the required task label")
    return payload


def _ensure_postgres(state: dict[str, Any]) -> None:
    inspected = _docker_inspect()
    if inspected is None:
        child_env = os.environ.copy()
        child_env["POSTGRES_PASSWORD"] = state["postgres_password"]
        child_env["POSTGRES_DB"] = DATABASE
        _run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                CONTAINER,
                "--label",
                CONTAINER_LABEL,
                "--env",
                "POSTGRES_PASSWORD",
                "--env",
                "POSTGRES_DB",
                "--publish",
                f"127.0.0.1:{POSTGRES_PORT}:5432",
                "--volume",
                f"{VOLUME}:/var/lib/postgresql",
                "pgvector/pgvector:pg18",
            ],
            env=child_env,
            capture=True,
        )
    elif not inspected.get("State", {}).get("Running"):
        _run(["docker", "start", CONTAINER], capture=True)

    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        ready = subprocess.run(
            ["docker", "exec", CONTAINER, "pg_isready", "-U", "postgres", "-d", DATABASE],
            text=True,
            capture_output=True,
            check=False,
        )
        if ready.returncode == 0:
            return
        time.sleep(0.5)
    raise RuntimeError("synthetic Postgres did not become ready within 45 seconds")


async def _bootstrap(state: dict[str, Any]) -> None:
    from scripts.prepare_ci_database import prepare

    owner, _, _ = _validated_urls(state)
    await prepare(
        bootstrap_url=owner,
        migrator_password=state["migrator_password"],
        app_password=state["app_password"],
    )


def _migrate(state: dict[str, Any]) -> None:
    _run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=_runtime_env(state),
    )


def _load_domain_fixture() -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / "domain.json").read_text(encoding="utf-8"))


def _encrypted(value: str) -> str:
    from app.core import crypto

    return crypto.encrypt(value)


async def seed(state: dict[str, Any]) -> dict[str, int]:
    os.environ.update(_runtime_env(state))
    from app.core import crypto
    from app.core.settings import get_settings

    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    fixture = _load_domain_fixture()
    _, _, app_url = _validated_urls(state)
    connection = await asyncpg.connect(asyncpg_dsn(app_url), timeout=20)
    try:
        async with connection.transaction():
            for row in fixture["tasks"]:
                title = _encrypted(row["title"]) if row["is_private"] else row["title"]
                body = _encrypted(row["body_md"]) if row["is_private"] else row["body_md"]
                await connection.execute(
                    """
                    INSERT INTO microsched.task
                        (id,title,body_md,status,priority,due_precision,due_on,due_at,is_private,pinned)
                    VALUES ($1,$2,$3,'open',$4,$5,$6,$7,$8,false)
                    ON CONFLICT (id) DO UPDATE SET
                        title=EXCLUDED.title, body_md=EXCLUDED.body_md, priority=EXCLUDED.priority,
                        due_precision=EXCLUDED.due_precision, due_on=EXCLUDED.due_on,
                        due_at=EXCLUDED.due_at, is_private=EXCLUDED.is_private, deleted_at=NULL
                    """,
                    UUID(row["id"]),
                    title,
                    body,
                    row["priority"],
                    row["due_precision"],
                    _date(row.get("due_on")),
                    _datetime(row.get("due_at")),
                    row["is_private"],
                )
            for row in fixture["notes"]:
                title = _encrypted(row["title"]) if row["is_private"] else row["title"]
                body = _encrypted(row["body_md"]) if row["is_private"] else row["body_md"]
                await connection.execute(
                    """INSERT INTO microsched.note
                    (id,title,body_md,pinned,priority,is_private)
                    VALUES ($1,$2,$3,false,$4,$5)
                    ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title,body_md=EXCLUDED.body_md,
                    priority=EXCLUDED.priority,is_private=EXCLUDED.is_private,embedding=NULL,deleted_at=NULL""",
                    UUID(row["id"]),
                    title,
                    body,
                    row["priority"],
                    row["is_private"],
                )
            for row in fixture["calendar_sources"]:
                await connection.execute(
                    """INSERT INTO microsched.calendar_source (id,name,kind,color,is_visible)
                    VALUES ($1,$2,$3,$4,true) ON CONFLICT (id) DO UPDATE SET
                    name=EXCLUDED.name,kind=EXCLUDED.kind,color=EXCLUDED.color,is_visible=true""",
                    UUID(row["id"]),
                    row["name"],
                    row["kind"],
                    row["color"],
                )
            for row in fixture["calendar_events"]:
                await connection.execute(
                    """INSERT INTO microsched.calendar_event
                    (id,source_id,title,starts_at,ends_at,description_md,all_day,is_hidden)
                    VALUES ($1,$2,$3,$4,$5,$6,false,false) ON CONFLICT (id) DO UPDATE SET
                    source_id=EXCLUDED.source_id,title=EXCLUDED.title,starts_at=EXCLUDED.starts_at,
                    ends_at=EXCLUDED.ends_at,description_md=EXCLUDED.description_md,is_hidden=false""",
                    UUID(row["id"]),
                    UUID(row["source_id"]),
                    row["title"],
                    _datetime(row["starts_at"]),
                    _datetime(row["ends_at"]),
                    row["description_md"],
                )
            for row in fixture["day_annotations"]:
                await connection.execute(
                    """INSERT INTO microsched.day_annotation
                    (id,starts_on,ends_on,label,note_md,is_private)
                    VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (id) DO UPDATE SET
                    starts_on=EXCLUDED.starts_on,ends_on=EXCLUDED.ends_on,label=EXCLUDED.label,
                    note_md=EXCLUDED.note_md,is_private=EXCLUDED.is_private""",
                    UUID(row["id"]),
                    _date(row["starts_on"]),
                    _date(row["ends_on"]),
                    _encrypted(row["label"]),
                    _encrypted(row["note_md"]),
                    row["is_private"],
                )
            for row in fixture["tracker_groups"]:
                await connection.execute(
                    """INSERT INTO microsched.tracker_group (id,name,kind,position)
                    VALUES ($1,$2,$3,$4) ON CONFLICT (id) DO UPDATE SET
                    name=EXCLUDED.name,kind=EXCLUDED.kind,position=EXCLUDED.position""",
                    UUID(row["id"]),
                    row["name"],
                    row["kind"],
                    row["position"],
                )
            for row in fixture["trackers"]:
                await connection.execute(
                    """INSERT INTO microsched.tracker
                    (id,name,kind,direction,input_mode,group_id,is_private)
                    VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (id) DO UPDATE SET
                    name=EXCLUDED.name,kind=EXCLUDED.kind,direction=EXCLUDED.direction,
                    input_mode=EXCLUDED.input_mode,group_id=EXCLUDED.group_id,
                    is_private=EXCLUDED.is_private,deleted_at=NULL""",
                    UUID(row["id"]),
                    _encrypted(row["name"]),
                    row["kind"],
                    row["direction"],
                    row["input_mode"],
                    UUID(row["group_id"]),
                    row["is_private"],
                )
            for row in fixture["subscriptions"]:
                await connection.execute(
                    """INSERT INTO microsched.subscription
                    (id,name,tracker_id,amount,period_count,period_unit,started_on,expires_on,auto_renew)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT (id) DO UPDATE SET
                    name=EXCLUDED.name,tracker_id=EXCLUDED.tracker_id,amount=EXCLUDED.amount,
                    period_count=EXCLUDED.period_count,period_unit=EXCLUDED.period_unit,
                    started_on=EXCLUDED.started_on,expires_on=EXCLUDED.expires_on,
                    auto_renew=EXCLUDED.auto_renew,deleted_at=NULL""",
                    UUID(row["id"]),
                    _encrypted(row["name"]),
                    UUID(row["tracker_id"]),
                    _encrypted(row["amount"]),
                    row["period_count"],
                    row["period_unit"],
                    _date(row["started_on"]),
                    _date(row["expires_on"]),
                    row["auto_renew"],
                )
            for row in fixture["entries"]:
                await connection.execute(
                    """INSERT INTO microsched.entry
                    (id,tracker_id,amount,occurred_at,note_md,deleted_at)
                    VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (id) DO UPDATE SET
                    tracker_id=EXCLUDED.tracker_id,amount=EXCLUDED.amount,
                    occurred_at=EXCLUDED.occurred_at,note_md=EXCLUDED.note_md,
                    deleted_at=EXCLUDED.deleted_at""",
                    UUID(row["id"]),
                    UUID(row["tracker_id"]),
                    _encrypted(row["amount"]) if row.get("amount") is not None else None,
                    _datetime(row["occurred_at"]),
                    _encrypted(row["note_md"]),
                    datetime(2030, 1, 13, tzinfo=UTC) if row.get("deleted") else None,
                )
    finally:
        await connection.close()
    counts = {key: len(value) for key, value in fixture.items()}
    receipt = {
        "schema_version": "mimi.seed-receipt.v1",
        "environment_id": ENVIRONMENT_ID,
        "fixture_version": "mimi-p0.v1",
        "fixture_sha256": fixture_digest(),
        "counts": counts,
        "seeded_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
    }
    DOMAIN_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(DOMAIN_RECEIPT, receipt)
    return counts


async def reset(state: dict[str, Any]) -> dict[str, int]:
    fixture = _load_domain_fixture()
    _, _, app_url = _validated_urls(state)
    connection = await asyncpg.connect(asyncpg_dsn(app_url), timeout=20)
    deletion_order = (
        ("entry", "entries"),
        ("subscription", "subscriptions"),
        ("tracker", "trackers"),
        ("tracker_group", "tracker_groups"),
        ("day_annotation", "day_annotations"),
        ("calendar_event", "calendar_events"),
        ("calendar_source", "calendar_sources"),
        ("note", "notes"),
        ("task", "tasks"),
    )
    try:
        async with connection.transaction():
            for table, key in deletion_order:
                ids = [UUID(row["id"]) for row in fixture[key]]
                await connection.execute(
                    f"DELETE FROM microsched.{table} WHERE id = ANY($1::uuid[])", ids
                )
    finally:
        await connection.close()
    return await seed(state)


async def verify(state: dict[str, Any]) -> dict[str, Any]:
    fixture = _load_domain_fixture()
    _, _, app_url = _validated_urls(state)
    connection = await asyncpg.connect(asyncpg_dsn(app_url), timeout=20)
    observed: dict[str, int] = {}
    mapping = {
        "tasks": "task",
        "notes": "note",
        "calendar_sources": "calendar_source",
        "calendar_events": "calendar_event",
        "day_annotations": "day_annotation",
        "tracker_groups": "tracker_group",
        "trackers": "tracker",
        "subscriptions": "subscription",
        "entries": "entry",
    }
    try:
        for key, table in mapping.items():
            ids = [UUID(row["id"]) for row in fixture[key]]
            observed[key] = await connection.fetchval(
                f"SELECT count(*) FROM microsched.{table} WHERE id = ANY($1::uuid[])", ids
            )
    finally:
        await connection.close()
    expected = {key: len(fixture[key]) for key in mapping}
    os.environ.update(_runtime_env(state))
    from app.agent.feedback_store import EncryptedReviewStore
    from app.core import crypto
    from app.core.settings import get_settings

    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    review_store = EncryptedReviewStore(REVIEW_ROOT)
    review_bundle = review_store.load_bundle(REVIEW_BUNDLE_ID)
    review_feedback = review_store.load_feedback(REVIEW_FEEDBACK_ID)
    return {
        "environment_id": ENVIRONMENT_ID,
        "fixture_version": "mimi-p0.v1",
        "fixture_sha256": fixture_digest(),
        "counts_expected": expected,
        "counts_observed": observed,
        "counts_match": observed == expected,
        "review_store_preserved": (REVIEW_ROOT / "STORE-MARKER.json").exists(),
        "review_bundle_roundtrip": (
            review_bundle.payload.assembled_prompt == "Synthetic assembled prompt for J05"
            and review_bundle.completeness.status.value == "complete"
        ),
        "feedback_acknowledged": review_feedback.state.value == "acknowledged",
        "feedback_unresolved": review_feedback.unresolved,
    }


def seed_review_fixture(state: dict[str, Any]) -> None:
    from app.agent.contracts import (
        CaptureStatus,
        CompletenessManifest,
        EvidenceBundle,
        EvidencePayload,
        FeedbackRecord,
        Sensitivity,
        ToolExchange,
    )
    from app.agent.feedback_store import EncryptedReviewStore

    expected_parts = ("prompt", "request", "response", "tools", "route", "config", "usage")
    bundle = EvidenceBundle(
        bundle_id=REVIEW_BUNDLE_ID,
        client_id="mimi-p0-review-bundle-001",
        run_id=UUID("50000000-0000-7000-8000-000000000003"),
        turn_id=UUID("50000000-0000-7000-8000-000000000004"),
        call_id="mimi-p0-synthetic-call-001",
        sensitivity=Sensitivity.PRIVATE,
        environment_id=ENVIRONMENT_ID,
        fixture_version="mimi-p0.v1",
        source_versions={
            "fixture": f"sha256:{fixture_digest()}",
            "task": "task-v2-before-owner-edit",
        },
        created_at=datetime(2030, 1, 15, tzinfo=UTC),
        completeness=CompletenessManifest(
            status=CaptureStatus.COMPLETE,
            expected_parts=expected_parts,
            captured_parts=expected_parts,
        ),
        payload=EvidencePayload(
            assembled_prompt="Synthetic assembled prompt for J05",
            request={"model": "fake-provider", "input": "Synthetic revise request"},
            response={"output": "Synthetic preview v2"},
            tool_exchanges=(
                ToolExchange(
                    call_id="mimi-p0-tool-call-001",
                    tool_name="task.read",
                    arguments={"task_id": "10000000-0000-7000-8000-000000000001"},
                    result={"version": "task-v2-before-owner-edit"},
                    outcome="succeeded",
                ),
            ),
            route={"provider": "fake", "model": "scripted-v1"},
            config={"temperature": 0},
            usage={"input_tokens": 24, "output_tokens": 8},
        ),
    )
    feedback = FeedbackRecord(
        feedback_id=REVIEW_FEEDBACK_ID,
        client_id="mimi-p0-feedback-001",
        target_type="turn",
        target_id=str(bundle.turn_id),
        comment="Synthetic feedback: preview used the stale task version.",
        expected="Require a fresh preview after the Owner edit.",
        evidence_bundle_ids=(bundle.bundle_id,),
        sensitivity=Sensitivity.PRIVATE,
        created_at=datetime(2030, 1, 15, tzinfo=UTC),
    )
    store = EncryptedReviewStore(REVIEW_ROOT)
    store.save_bundle(bundle)
    receipt = store.save_feedback(feedback)
    if receipt.created:
        store.acknowledge_feedback(
            feedback.feedback_id, acknowledged_at=datetime(2030, 1, 15, 0, 5, tzinfo=UTC)
        )


def _date(value: str | None):
    return datetime.fromisoformat(value).date() if value else None


def _datetime(value: str | None):
    return datetime.fromisoformat(value) if value else None


def _start_processes(state: dict[str, Any], *, install: bool) -> None:
    env = _runtime_env(state)
    if install:
        _run([_npm_command(), "ci"], cwd=FRONTEND_ROOT, env=env)
    vite = FRONTEND_ROOT / "node_modules" / ".bin" / "vite.cmd"
    if not vite.exists():
        raise RuntimeError("frontend dependencies missing; rerun start with --install")
    logs = LOCAL_ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
        subprocess, "CREATE_NO_WINDOW", 0
    )
    if _http_ok(f"http://127.0.0.1:{BACKEND_PORT}/api/healthz") and not _pid_alive(
        state.get("backend_pid")
    ):
        raise SandboxRefusal("backend port 8000 is owned by an unrecorded process")
    if _http_ok(f"http://127.0.0.1:{FRONTEND_PORT}/") and not _pid_alive(state.get("frontend_pid")):
        raise SandboxRefusal("frontend port 5173 is owned by an unrecorded process")
    if not _pid_alive(state.get("backend_pid")):
        backend_log = (logs / "backend.log").open("ab")
        backend = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(BACKEND_PORT),
            ],
            cwd=BACKEND_ROOT,
            env=env,
            stdout=backend_log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
        state["backend_pid"] = backend.pid
    if not _pid_alive(state.get("frontend_pid")):
        frontend_log = (logs / "frontend.log").open("ab")
        frontend = subprocess.Popen(
            [
                _npm_command(),
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(FRONTEND_PORT),
            ],
            cwd=FRONTEND_ROOT,
            env=env,
            stdout=frontend_log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
        state["frontend_pid"] = frontend.pid
    _atomic_json(STATE_PATH, state)
    if not _wait_backend_ready(30):
        raise RuntimeError(f"backend readiness failed; inspect {logs / 'backend.log'}")
    if not _wait_http(f"http://127.0.0.1:{FRONTEND_PORT}/", 30):
        raise RuntimeError(f"frontend readiness failed; inspect {logs / 'frontend.log'}")
    # Windows venv/npm launchers may exit after spawning the actual listener.
    # Persist the owning listeners, not transient wrapper PIDs, so stop remains exact.
    if os.name == "nt":
        backend_listener = _listener_pid(BACKEND_PORT)
        frontend_listener = _listener_pid(FRONTEND_PORT)
        if backend_listener is None or frontend_listener is None:
            raise RuntimeError("could not resolve exact local listener PIDs after readiness")
        state["backend_pid"] = backend_listener
        state["frontend_pid"] = frontend_listener
        _atomic_json(STATE_PATH, state)


def _wait_http(url: str, seconds: int) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _http_ok(url):
            return True
        time.sleep(0.25)
    return False


def _wait_backend_ready(seconds: int) -> bool:
    deadline = time.monotonic() + seconds
    expected_commit = _git_sha()
    while time.monotonic() < deadline:
        body = _http_json(f"http://127.0.0.1:{BACKEND_PORT}/api/readyz")
        if body and body.get("db") == "up" and body.get("commit") == expected_commit:
            return True
        time.sleep(0.25)
    return False


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= response.status < 400
    except OSError, urllib.error.URLError:
        return False


def _http_json(url: str) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if not 200 <= response.status < 400:
                return None
            return json.loads(response.read())
    except OSError, ValueError, urllib.error.URLError:
        return None


def _npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _listener_pid(port: int) -> int | None:
    if os.name != "nt":
        return None
    command = (
        "$row = Get-NetTCPConnection -State Listen -LocalPort "
        f"{port} -ErrorAction SilentlyContinue | "
        "Where-Object { $_.LocalAddress -in '127.0.0.1','::1' } | "
        "Select-Object -First 1 -ExpandProperty OwningProcess; if ($row) { $row }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        text=True,
        capture_output=True,
        check=False,
    )
    value = result.stdout.strip()
    return int(value) if result.returncode == 0 and value.isdigit() else None


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"if (Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue) "
                "{ exit 0 } else { exit 1 }",
            ],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _stop_pid(pid: int | None) -> None:
    if not _pid_alive(pid):
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T"], check=False, capture_output=True)
        deadline = time.monotonic() + 5
        while _pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        if _pid_alive(pid):
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
            )
    else:
        os.kill(pid, signal.SIGTERM)


def status() -> dict[str, Any]:
    state = _load_state() if STATE_PATH.exists() else None
    inspected = _docker_inspect()
    readiness = _http_json(f"http://127.0.0.1:{BACKEND_PORT}/api/readyz")
    expected_commit = _git_sha()
    return {
        "task_id": TASK_ID,
        "environment_id": ENVIRONMENT_ID,
        "state_present": state is not None,
        "container_present": inspected is not None,
        "postgres_running": bool(inspected and inspected.get("State", {}).get("Running")),
        "backend_running": bool(state and _pid_alive(state.get("backend_pid"))),
        "backend_ready": bool(
            readiness and readiness.get("db") == "up" and readiness.get("commit") == expected_commit
        ),
        "backend_commit": readiness.get("commit") if readiness else None,
        "backend_db": readiness.get("db") if readiness else None,
        "frontend_running": bool(state and _pid_alive(state.get("frontend_pid"))),
        "frontend_ready": _http_ok(f"http://127.0.0.1:{FRONTEND_PORT}/"),
        "fixture_version": "mimi-p0.v1",
        "fixture_sha256": fixture_digest(),
        "review_store_present": (REVIEW_ROOT / "STORE-MARKER.json").exists(),
    }


def start(*, with_app: bool, install: bool) -> dict[str, Any]:
    state = _load_state(create=True)
    _ensure_postgres(state)
    asyncio.run(_bootstrap(state))
    _migrate(state)
    os.environ.update(_runtime_env(state))
    from app.core import crypto
    from app.core.settings import get_settings

    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    seed_review_fixture(state)
    asyncio.run(seed(state))
    if with_app:
        _start_processes(state, install=install)
    return status()


def stop() -> dict[str, Any]:
    state = _load_state()
    _stop_pid(state.get("frontend_pid"))
    _stop_pid(state.get("backend_pid"))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        backend_down = not _http_ok(f"http://127.0.0.1:{BACKEND_PORT}/api/healthz")
        frontend_down = not _http_ok(f"http://127.0.0.1:{FRONTEND_PORT}/")
        if backend_down and frontend_down:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("recorded local app process tree did not stop within 10 seconds")
    state["frontend_pid"] = None
    state["backend_pid"] = None
    _atomic_json(STATE_PATH, state)
    inspected = _docker_inspect()
    if inspected and inspected.get("State", {}).get("Running"):
        _run(["docker", "stop", CONTAINER], capture=True)
    return status()


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True), encoding="utf-8", newline="\n"
    )
    os.replace(temporary, path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start_parser = sub.add_parser("start", help="start exact local Postgres, seed, and app")
    start_parser.add_argument("--db-only", action="store_true", help="skip backend/frontend")
    start_parser.add_argument("--install", action="store_true", help="run npm ci before app start")
    sub.add_parser("status", help="show non-secret health and ownership state")
    sub.add_parser("seed", help="idempotently upsert manifest-owned synthetic rows")
    sub.add_parser("reset", help="delete only manifest-owned IDs, reseed, preserve review store")
    sub.add_parser("verify", help="compare exact owned IDs/counts and fixture digest")
    sub.add_parser("stop", help="stop exact recorded processes/container; delete nothing")
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "start":
        result = start(with_app=not args.db_only, install=args.install)
    elif args.command == "status":
        result = status()
    elif args.command == "seed":
        result = asyncio.run(seed(_load_state()))
    elif args.command == "reset":
        result = asyncio.run(reset(_load_state()))
    elif args.command == "verify":
        result = asyncio.run(verify(_load_state()))
    else:
        result = stop()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
