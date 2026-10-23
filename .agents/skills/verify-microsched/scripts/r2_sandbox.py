"""R2 091 task-owned namespace over the existing sandbox driver. Never reuse legacy volumes."""

import argparse
import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

TASK = "r2-091-20261023"
LANES = {"microsched"}
SOURCES = {
    "microsched": Path(
        "C:/Users/os/Desktop/ai_eng_path/microsched/worktrees/091-offline-outbox-core"
    )
}


class Refusal(RuntimeError):
    pass


def validate_volume(payload, name, identity):
    if (
        payload.get("Name") != name
        or (payload.get("Labels") or {}).get("harness.task") != identity
    ):
        raise Refusal(
            "Volume has no exact R2 ownership label; retain it, do not reuse/reset/delete"
        )


def validate_fixture(payload):
    for key in [
        "counts_match",
        "review_store_preserved",
        "review_bundle_roundtrip",
        "feedback_acknowledged",
    ]:
        if payload.get(key) is not True:
            raise Refusal("Synthetic fixture oracle failed: " + key)


def inspect_volume(name):
    p = subprocess.run(
        ["docker", "volume", "inspect", name], capture_output=True, text=True, check=False
    )
    if p.returncode:
        if "no such volume" in p.stderr.lower():
            return None
        raise Refusal("Volume ownership unavailable; Docker error retained")
    return json.loads(p.stdout)[0]


def check_binding(source, binding, lane):
    p = json.loads(Path(binding).read_text(encoding="utf-8-sig"))
    source = Path(source).resolve()
    if lane not in SOURCES:
        raise Refusal("Unknown lane")
    if p.get("lane") != lane:
        raise Refusal("Binding lane mismatch")
    if source != SOURCES[lane].resolve():
        raise Refusal("Source is not the approved checkout for lane")
    if Path(p["source"]).resolve() != source:
        raise Refusal("Binding checkout mismatch")
    head = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != p["head"]:
        raise Refusal("Candidate head mismatch")
    if not isinstance(p.get("files"), dict) or not p["files"]:
        raise Refusal("Nonempty source closure required")
    for rel, want in p["files"].items():
        parts = PurePosixPath(rel).parts
        if (
            not parts
            or "\\" in rel
            or ":" in rel
            or ".." in parts
            or PurePosixPath(rel).is_absolute()
        ):
            raise Refusal("Unsafe source path")
        raw = source.joinpath(*parts)
        if any(
            q.is_symlink() or q.is_junction()
            for q in [raw, *raw.parents]
            if q != source and q.is_relative_to(source)
        ):
            raise Refusal("Linked source input")
        target = raw.resolve()
        if not target.is_relative_to(source) or any(
            part.startswith(".env") and part != ".env.example" for part in parts
        ):
            raise Refusal("Unsafe source manifest path")
        if (
            not target.is_file()
            or hashlib.sha256(target.read_bytes()).hexdigest() != want
        ):
            raise Refusal("Candidate manifest changed: " + rel)
    return p


def configure(source, lane, binding):
    check_binding(source, binding, lane)
    if lane not in LANES:
        raise Refusal("Unknown lane")
    if (source / "backend/.env").exists() or (source / "frontend/.env").exists():
        raise Refusal("Real dotenv file present in candidate; never read it")
    sys.path.insert(0, str(source / "backend"))
    d = importlib.import_module("scripts.mimi_sandbox")
    identity = f"{TASK}-{lane}"
    d.TASK_ID = identity
    d.ENVIRONMENT_ID = identity + "-local"
    d.CONTAINER = identity
    d.VOLUME = identity + "-db"
    d.CONTAINER_LABEL = "microsched.synthetic=" + identity
    d.DATABASE = "microsched_r2_091"
    d.POSTGRES_PORT = 55491
    # Vite's inspected proxy targets 8001, so app ports are used sequentially, not changed silently.
    d.BACKEND_PORT = 8001
    d.FRONTEND_PORT = 4174
    d.LOCAL_ROOT = source / ".local/r2-091" / lane
    d.STATE_PATH = d.LOCAL_ROOT / "runtime.json"
    d.DOMAIN_RECEIPT = d.LOCAL_ROOT / "domain/seed-receipt.json"
    d.REVIEW_ROOT = d.LOCAL_ROOT / "review"
    if (source / "backend/.env").exists() or (source / "frontend/.env").exists():
        raise Refusal("Real dotenv file present in candidate; never read it")
    original_env = d._runtime_env

    def synthetic_env(state):
        e = original_env(state)
        e.update(
            {
                "MIMI_PUBLIC_ORIGIN": "http://127.0.0.1:4174",
                "VITE_BACKEND_ORIGIN": "http://127.0.0.1:8001",
                "PRIVATE_PIN_BOOTSTRAP": "091091",
                "MIMI_REAL_CHAT_ENABLED": "false",
                "MIMI_LIVE_PROVIDER_ENABLED": "false",
                "MIMI_CONTEXT_V1_ENABLED": "false",
                "MIMI_WORKFLOW_PILOT_ENABLED": "false",
                "MIMI_COLLECTION_ENABLED": "false",
                "MIMI_NOTIFICATIONS_ENABLED": "false",
            }
        )
        return e

    d._runtime_env = synthetic_env
    original_ensure = d._ensure_postgres

    def ensure(state):
        if d._docker_inspect() is None and d._port_bound(d.POSTGRES_PORT):
            raise Refusal('Postgres port is owned by another process')
        payload = inspect_volume(d.VOLUME)
        if payload is None:
            if d._docker_inspect() is not None:
                raise Refusal("Container exists but volume binding is missing")
            p = subprocess.run(
                [
                    "docker",
                    "volume",
                    "create",
                    "--label",
                    "harness.task=" + identity,
                    d.VOLUME,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if p.returncode:
                raise Refusal("Owned volume creation failed")
            payload = inspect_volume(d.VOLUME)
        validate_volume(payload, d.VOLUME, identity)
        image = subprocess.run(
            ["docker", "image", "inspect", "pgvector/pgvector:pg18"],
            capture_output=True,
            text=True,
            check=False,
        )
        if image.returncode:
            raise Refusal("Required cached image missing; no implicit pull")
        original_ensure(state)

    original_run = d._run

    def no_pull(command, **kwargs):
        if command[:2] == ["docker", "run"]:
            command = [*command[:2], "--pull=never", *command[2:]]
        return original_run(command, **kwargs)

    d._run = no_pull
    d._ensure_postgres = ensure
    return d, identity


def init_db(d):
    """Create only the new owned isolated databases; never reset/reseed existing state."""
    import asyncio

    state = d._load_state(create=True)
    d._ensure_postgres(state)
    marker = d.LOCAL_ROOT / "initialized.json"
    if marker.exists():
        return {"initialized": True, "retained": True, "container": d.CONTAINER}
    asyncio.run(d._bootstrap(state))
    d._migrate(
        state
    )  # Apply unchanged accepted head only inside this new throwaway database.
    d._activate_synthetic_settings(state)
    owner, _, _ = d._validated_urls(state)
    from sqlalchemy.engine import make_url

    test_db = "microsched_r2_091_tests"

    async def prepare_test():
        import asyncpg
        from app.core.database_urls import asyncpg_dsn
        from scripts.prepare_ci_database import prepare

        conn = await asyncpg.connect(asyncpg_dsn(owner))
        try:
            if not await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname=$1", test_db
            ):
                await conn.execute('CREATE DATABASE "' + test_db + '"')
        finally:
            await conn.close()
        test_owner = (
            make_url(owner).set(database=test_db).render_as_string(hide_password=False)
        )
        await prepare(
            bootstrap_url=test_owner,
            migrator_password=state["migrator_password"],
            app_password=state["app_password"],
        )

    asyncio.run(prepare_test())
    env = d._runtime_env(state)
    env["NEON_MIGRATOR_URL"] = (
        make_url(env["NEON_MIGRATOR_URL"])
        .set(database=test_db)
        .render_as_string(hide_password=False)
    )
    env["CI_MIGRATOR_URL"] = env["NEON_MIGRATOR_URL"]
    d._run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=d.BACKEND_ROOT,
        env=env,
    )
    result = asyncio.run(seed_r2(d, state))
    d._atomic_json(marker, result)
    return result


async def seed_r2(d, state):
    from datetime import UTC, datetime, timedelta
    from uuid import UUID

    from app.core.database_urls import async_postgres_url
    from app.domain.models import AuthSession
    from app.domain.tasks import TaskCreate, TaskStore
    from app.domain.tracker import EntryCreate, TrackerCreate, TrackerStore
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    d._activate_synthetic_settings(state)
    from app.core import crypto

    crypto._cipher.cache_clear()
    now = datetime.now(UTC)
    auth = AuthSession(
        token_hash="r2-fixture-only",
        user_email="owner@test.local",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=now + timedelta(hours=1),
    )
    engine = create_async_engine(async_postgres_url(d._validated_urls(state)[2]))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    tasks, trackers, entries = [], [], []

    def identity(kind, index):
        return UUID(f"019a0910-0000-7000-8{kind:03d}-{index:012d}")

    try:
        async with maker() as db:
            ts, rs = TaskStore(), TrackerStore()
            for index in range(40):
                task_id = identity(1, index + 1)
                await ts.create(
                    db,
                    auth,
                    TaskCreate(
                        id=task_id,
                        title=f"R2 fixture Task {index + 1}",
                        due_precision="date",
                        due_on=now.astimezone().date(),
                        is_private=index == 39,
                        items=[f"R2 child {n + 1}" for n in range(4)],
                        item_ids=[identity(2, index * 4 + n + 1) for n in range(4)],
                    ),
                )
                tasks.append(str(task_id))
            for index in range(4):
                tracker_id = identity(3, index + 1)
                await rs.create_tracker(
                    db,
                    auth,
                    TrackerCreate(
                        id=tracker_id,
                        name=f"R2 fixture Tracker {index + 1}",
                        kind="general",
                        direction="out",
                        input_mode="event",
                        is_private=index == 3,
                    ),
                )
                trackers.append(str(tracker_id))
                for n in range(50):
                    entry_id = identity(4, index * 50 + n + 1)
                    await rs.create_entry(
                        db,
                        auth,
                        EntryCreate(
                            id=entry_id,
                            tracker_id=tracker_id,
                            occurred_at=now - timedelta(hours=n + 1),
                        ),
                    )
                    entries.append(str(entry_id))
            await db.commit()
    finally:
        await engine.dispose()
    return {
        "fixture_version": "r2-091-v1",
        "task_ids": tasks,
        "tracker_ids": trackers,
        "entry_ids": entries,
        "counts": {"tasks": 40, "items": 160, "trackers": 4, "entries": 200},
        "private_task_id": tasks[-1],
        "private_tracker_id": trackers[-1],
        "container": d.CONTAINER,
        "database": d.DATABASE,
        "test_database": "microsched_r2_091_tests",
        "provider_calls": 0,
        "mimi": False,
        "cron": False,
        "seeded_at": now.isoformat(),
    }


def start_app(d):
    """Start cached installed API + production preview only, no DB/bootstrap/install/reseed."""
    import os
    import subprocess

    state = d._load_state()
    if not (d.LOCAL_ROOT / "initialized.json").exists():
        raise Refusal("Initialize owned fixture first")
    if not d._docker_inspect().get("State", {}).get("Running"):
        raise Refusal("Owned database is not running")
    d._assert_app_ports_owned(state)
    if not (d.FRONTEND_ROOT / "dist/index.html").is_file():
        raise Refusal("Production build missing")
    logs = d.LOCAL_ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    env = d._runtime_env(state)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    commands = [
        (
            "backend_pid",
            d.BACKEND_ROOT,
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(d.BACKEND_PORT),
            ],
        ),
        (
            "frontend_pid",
            d.FRONTEND_ROOT,
            [
                d._npm_command(),
                "run",
                "preview",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(d.FRONTEND_PORT),
                "--strictPort",
            ],
        ),
    ]
    for key, cwd, command in commands:
        if d._pid_alive(state.get(key)):
            continue
        with (logs / (key + ".log")).open("ab") as log:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )
        state[key] = process.pid
        d._atomic_json(
            d.STATE_PATH, state
        )  # Persist effects immediately before readiness.
    if not d._wait_backend_ready(30) or not d._wait_http(
        f"http://127.0.0.1:{d.FRONTEND_PORT}/", 30
    ):
        raise Refusal(
            "App not ready; inspect recorded process/log effects before retry"
        )
    if os.name == "nt":
        for key, port in [
            ("backend_pid", d.BACKEND_PORT),
            ("frontend_pid", d.FRONTEND_PORT),
        ]:
            pid = d._listener_pid(port)
            if pid is None:
                raise Refusal("Listener PID unavailable; preserve state and inspect")
            state[key] = pid
    d._atomic_json(d.STATE_PATH, state)
    return {
        "backend_pid": state["backend_pid"],
        "frontend_pid": state["frontend_pid"],
        "backend_port": d.BACKEND_PORT,
        "frontend_port": d.FRONTEND_PORT,
        "container": d.CONTAINER,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True)
    p.add_argument("--binding", required=True)
    p.add_argument("--lane", choices=sorted(LANES), default="microsched")
    p.add_argument(
        "action",
        choices=["guard", "init-db", "start-app", "status", "stop-app", "test"],
    )
    p.add_argument("--tests", nargs="*")
    a = p.parse_args()
    source = Path(a.source).resolve()
    if a.action == "guard":
        b = check_binding(source, a.binding, a.lane)
        result = {"source_match": True, "members": len(b["files"])}
    else:
        d, identity = configure(source, a.lane, a.binding)
        volume = inspect_volume(d.VOLUME)
        if volume is not None:
            validate_volume(volume, d.VOLUME, identity)
        if a.action == "init-db":
            result = init_db(d)
        elif a.action == "start-app":
            result = start_app(d)
        elif a.action == "status":
            result = d.status()
        elif a.action == "stop-app":
            state = d._load_state()
            for key, port in [
                ("frontend_pid", d.FRONTEND_PORT),
                ("backend_pid", d.BACKEND_PORT),
            ]:
                pid = d._owned_listener_or_refuse(state.get(key), port, key)
                d._stop_pid(pid)
                state[key] = None
                d._atomic_json(d.STATE_PATH, state)
            result = {"app_stopped": True, "container_retained": d.CONTAINER}
        else:
            state = d._load_state()
            env = d._runtime_env(state)
            from sqlalchemy.engine import make_url

            url = (
                make_url(d._validated_urls(state)[0])
                .set(database="microsched_r2_091_tests")
                .render_as_string(hide_password=False)
            )
            env.update(
                {
                    "NEON_MIGRATOR_URL": url,
                    "CI_MIGRATOR_URL": make_url(env["NEON_MIGRATOR_URL"])
                    .set(database="microsched_r2_091_tests")
                    .render_as_string(hide_password=False),
                }
            )
            tests = a.tests or [
                "tests/test_tasks_api.py",
                "tests/test_tasks_store.py",
                "tests/test_task_idempotent_create.py",
                "tests/test_tracker_api.py",
            ]
            if any(
                not value.startswith("tests/")
                or ".." in value
                or not value.endswith(".py")
                for value in tests
            ):
                raise Refusal("Only explicit existing test files")
            d._run(
                [sys.executable, "-m", "pytest", *tests, "-q"],
                cwd=d.BACKEND_ROOT,
                env=env,
            )
            result = {"tests_complete": tests, "database": "microsched_r2_091_tests"}
    print(json.dumps(result, default=str, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Refusal as error:
        print("REFUSED: " + str(error), file=sys.stderr)
        sys.exit(2)
