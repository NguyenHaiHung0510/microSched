"""Synthetic-only CLI dogfood / fresh-process lifecycle entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import selectors
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.agent.workflow_probe.contracts import Record
from app.agent.workflow_probe.engines import run_control, run_graph
from app.agent.workflow_probe.store import PgFrameStore
from app.agent.workflow_probe.workflow import ConfirmationContent, Workflow
from app.core import crypto


def synthetic_cipher() -> None:
    # No .env/settings invocation and no inherited provider/encryption credential use.
    # This public deterministic key is deliberately unsuitable for any real data.
    crypto._cipher = lambda: AESGCM(b"s" * 32)


async def main(args):
    synthetic_cipher()
    url = os.environ.get("MIMI_WORKFLOW_PROBE_APP_URL")
    if not url:
        raise SystemExit("MIMI_WORKFLOW_PROBE_APP_URL required: dedicated local 068 app database")
    store = PgFrameStore(url)

    async def fault(point):
        if point == args.fault:
            print(json.dumps({"fault_ready": point, "pid": os.getpid()}), flush=True)
            # Finite wall time; parent must terminate this exact PID for crash evidence.
            await asyncio.wait_for(asyncio.Event().wait(), 60)

    def clock():
        return datetime.now(UTC) + timedelta(seconds=args.clock_offset)

    workflow = Workflow(
        store,
        UUID(args.run_id) if args.run_id else uuid4(),
        args.owner,
        version=args.version,
        policy=args.policy,
        now=clock,
        fault=fault,
    )
    if args.command == "create":
        await store.cleanup(now=clock())
        await workflow.create(
            args.domain,
            args.engine,
            (
                Record("a", 1, "Synthetic alpha"),
                Record("b", 2, "Synthetic beta"),
            ),
        )
        result = await workflow.status()
    elif args.command == "status":
        result = await workflow.status()
    elif args.command == "cleanup":
        result = await store.cleanup(now=clock())
    else:
        frame, _ = await workflow.load()
        if args.direction:
            await workflow.accept(generation=args.generation, direction=args.direction)
        if args.confirm:
            await workflow.accept(
                generation=args.generation,
                confirmation=ConfirmationContent(
                    owner=args.owner,
                    generation=args.generation,
                    preview_digest=args.confirm,
                ),
            )
        result = await {"control": run_control, "graph": run_graph}[frame.engine](workflow)
        await store.cleanup(now=clock())
    if result.get("phase") in {"direction", "confirmation"}:
        await fault("after_pause")
    print(json.dumps({"pid": os.getpid(), **result}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["create", "run", "status", "cleanup"])
    parser.add_argument("--run-id")
    parser.add_argument("--owner", default="synthetic-owner")
    parser.add_argument("--engine", choices=["control", "graph"], default="control")
    parser.add_argument("--domain", choices=["task", "note"], default="task")
    parser.add_argument("--version", type=int, choices=[1, 2], default=2)
    parser.add_argument("--policy", default="probe-v1")
    parser.add_argument("--generation", type=int, default=1)
    parser.add_argument("--direction", choices=["apply_prefix"])
    parser.add_argument("--confirm")
    parser.add_argument("--fault")
    parser.add_argument("--clock-offset", type=float, default=0)
    args = parser.parse_args()
    if args.command in {"run", "status"} and not args.run_id:
        parser.error("--run-id is required")
    asyncio.run(
        main(args), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
    )
