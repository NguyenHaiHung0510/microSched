"""R1 090 task-owned namespace over the existing sandbox driver. Never reuse legacy volumes."""

import argparse
import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

TASK = "r1-090-20261022"
LANES = {"microsched"}
SOURCES = {
    "microsched": Path(
        "C:/Users/os/Desktop/ai_eng_path/microsched/worktrees/090-group-heatmap"
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
            "Volume has no exact R1 ownership label; retain it, do not reuse/reset/delete"
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
        ["docker", "volume", "inspect", name], capture_output=True, text=True
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
    sys.path.insert(0, str(source / "backend"))
    d = importlib.import_module("scripts.mimi_sandbox")
    identity = f"{TASK}-{lane}"
    d.TASK_ID = identity
    d.ENVIRONMENT_ID = identity + "-local"
    d.CONTAINER = identity
    d.VOLUME = identity + "-db"
    d.CONTAINER_LABEL = "microsched.synthetic=" + identity
    d.DATABASE = "microsched_r1_090"
    d.POSTGRES_PORT = 55490
    # Vite's inspected proxy targets 8000, so app ports are used sequentially, not changed silently.
    d.BACKEND_PORT = 8000
    d.FRONTEND_PORT = 5173
    d.LOCAL_ROOT = source / ".local/r1-090" / lane
    d.STATE_PATH = d.LOCAL_ROOT / "runtime.json"
    d.DOMAIN_RECEIPT = d.LOCAL_ROOT / "domain/seed-receipt.json"
    d.REVIEW_ROOT = d.LOCAL_ROOT / "review"
    original_env = d._runtime_env

    def synthetic_env(state):
        e = original_env(state)
        e.update(
            {
                "MIMI_PUBLIC_ORIGIN": "http://127.0.0.1:5173",
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
            )
            if p.returncode:
                raise Refusal("Owned volume creation failed")
            payload = inspect_volume(d.VOLUME)
        validate_volume(payload, d.VOLUME, identity)
        image = subprocess.run(
            ["docker", "image", "inspect", "pgvector/pgvector:pg18"],
            capture_output=True,
            text=True,
        )
        if image.returncode:
            raise Refusal("Required cached image missing; no implicit pull")
        original_ensure(state)

    d._ensure_postgres = ensure
    return d, identity


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True)
    p.add_argument("--binding", required=True)
    p.add_argument("--lane", choices=sorted(LANES), required=True)
    p.add_argument("action", choices=["start", "start-db", "status", "verify", "stop"])
    a = p.parse_args()
    source = Path(a.source).resolve()
    d, identity = configure(source, a.lane, a.binding)
    volume = inspect_volume(d.VOLUME)
    if volume is not None:
        validate_volume(volume, d.VOLUME, identity)
    # Original driver checks state marker, exact labeled container, image/mount/loopback port and PID owners.
    if a.action in {"start", "start-db"}:
        result = d.start(with_app=a.action == "start", install=False)
    elif a.action == "status":
        result = d.status()
    elif a.action == "verify":
        state = d._load_state()
        d._activate_synthetic_settings(state)
        import asyncio

        result = asyncio.run(d.verify(state))
        validate_fixture(result)
    else:
        result = d.stop()
    print(json.dumps(result, default=str, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Refusal as e:
        print("REFUSED: " + str(e), file=sys.stderr)
        sys.exit(2)
