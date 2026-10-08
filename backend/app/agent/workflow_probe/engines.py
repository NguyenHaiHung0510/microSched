"""Two schedulers, identical workflow handlers and PostgreSQL authority."""

from __future__ import annotations

import asyncio
import hashlib
from typing import TypedDict

from app.agent.workflow_probe.contracts import ProbeBlocked
from app.agent.workflow_probe.store import checkpoint_thread
from app.agent.workflow_probe.workflow import STAGES, STOPPED, Workflow


async def run_control(workflow: Workflow) -> dict[str, object]:
    remaining = await workflow.enter()
    if remaining:
        try:
            async with asyncio.timeout(remaining):
                for _ in range(32):
                    frame, _ = await workflow.load()
                    if frame.phase in STOPPED:
                        break
                    if frame.phase in {
                        "direction",
                        "confirmation",
                    } and not await workflow.has_input(frame.phase):
                        break
                    await workflow.step(frame.phase)
                else:
                    raise ProbeBlocked("control_transition_budget_exceeded")
        finally:
            await workflow.leave()
    return await workflow.status()


class GraphRefs(TypedDict):
    run_id: str
    generation: int
    state_schema_version: int
    policy_hash: str
    contract_hash: str
    cursor: str


def validate_refs(values: dict, expected: GraphRefs) -> None:
    if set(values) != set(expected):
        raise ProbeBlocked("graph_reference_shape_invalid")
    for key in ("run_id", "generation", "policy_hash", "contract_hash"):
        if values[key] != expected[key] or type(values[key]) is not type(expected[key]):
            raise ProbeBlocked("graph_reference_identity_invalid")
    if type(values["state_schema_version"]) is not int or values["state_schema_version"] not in {
        1,
        expected["state_schema_version"],
    }:
        raise ProbeBlocked("graph_reference_version_invalid")
    if values["cursor"] not in set(STAGES) | STOPPED:
        raise ProbeBlocked("graph_reference_cursor_invalid")


async def run_graph(workflow: Workflow) -> dict[str, object]:
    # Optional libraries are imported only by this local experimental entry point.
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt

    frame, _ = await workflow.load()
    if frame.phase in STOPPED:
        return await workflow.status()
    refs: GraphRefs = {
        "run_id": str(frame.run_id),
        "generation": frame.generation,
        "state_schema_version": workflow.version,
        "policy_hash": hashlib.sha256(workflow.policy.encode()).hexdigest(),
        "contract_hash": workflow.contract_hash,
        "cursor": frame.phase,
    }
    graph = StateGraph(GraphRefs)

    def node_for(stage):
        async def node(state):
            validate_refs(state, refs)
            current, _ = await workflow.load()
            if current.phase == stage and stage in {"direction", "confirmation"}:
                # Only a reference/control signal is persisted, never draft or user input.
                signal = interrupt({"run_id": str(current.run_id), "kind": stage})
                if signal != "input_ready":
                    raise ProbeBlocked("graph_resume_signal_invalid")
            cursor = await workflow.step(stage)
            return {"cursor": cursor, "state_schema_version": workflow.version}

        return node

    route = {stage: stage for stage in STAGES} | {phase: END for phase in STOPPED}
    for stage in STAGES:
        graph.add_node(stage, node_for(stage))
        graph.add_conditional_edges(stage, lambda state: state["cursor"], route)
    graph.add_conditional_edges(START, lambda state: state["cursor"], route)
    config = {
        "configurable": {"thread_id": checkpoint_thread(frame.run_id, frame.generation)},
        "recursion_limit": 32,
    }
    remaining = await workflow.enter()
    if not remaining:
        return await workflow.status()
    try:
        async with asyncio.timeout(remaining):
            async with AsyncPostgresSaver.from_conn_string(workflow.store._dsn) as saver:
                compiled = graph.compile(checkpointer=saver)
                snapshot = await compiled.aget_state(config)
                if snapshot.values:
                    validate_refs(snapshot.values, refs)
                    if snapshot.values["state_schema_version"] != workflow.version:
                        await compiled.aupdate_state(
                            config, {"state_schema_version": workflow.version}
                        )
                    pending = any(task.interrupts for task in snapshot.tasks)
                    if pending:
                        current, _ = await workflow.load()
                        if not await workflow.has_input(current.phase):
                            return await workflow.status()
                        value = Command(resume="input_ready")
                    else:
                        value = None
                else:
                    value = refs
                result = await compiled.ainvoke(value, config)
                # A crash before the first gate checkpoint may leave approved PG input
                # waiting when the replay reaches interrupt. At most one such resume.
                if result.get("__interrupt__"):
                    current, _ = await workflow.load()
                    if await workflow.has_input(current.phase):
                        await compiled.ainvoke(Command(resume="input_ready"), config)
    finally:
        await workflow.leave()
    return await workflow.status()
