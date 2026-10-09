"""Actual service regressions for current-run selection and bound preview kind."""

import asyncio
import json
from uuid import UUID, uuid7

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import auth, cleanup, local_contract, prepare  # noqa: F401

from app.agent import crypto, service
from app.agent.context import PreviewCandidate, ToolRequest, ToolRequests
from app.agent.models import MimiChangeSet, MimiConversation, MimiEvent, MimiRun
from app.agent.openrouter import AgentCompletion, build_request, validate_task_candidate
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import Task

pytestmark = pytest.mark.pg


@pytest.fixture
def live_double(monkeypatch):
    for key, value in {
        "MIMI_LIVE_PROVIDER_ENABLED": "1",
        "MIMI_CONTEXT_V1_ENABLED": "1",
        "MIMI_STANDARD_API_KEY": "synthetic-never-sent",
        "MIMI_ROUTE_MODEL": "deepseek/deepseek-v4.1-flash",
        "MIMI_ROUTE_PROVIDER": "deepinfra",
        "MIMI_ROUTE_QUANTIZATION": "fp8",
        "MIMI_ROUTE_MAX_INPUT_PRICE": "0.2",
        "MIMI_ROUTE_MAX_OUTPUT_PRICE": "0.6",
        "MIMI_ROUTE_MODE": "exact",
        "MIMI_ROUTE_FORCED_TOOL_CHOICE": "function",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def route():
    return {
        "profile_id": "deepseek",
        "effort": "high",
        "input_tokens": 100000,
        "routing_mode": "exact",
    }


async def operation(db, cid, change):
    dek = crypto.unwrap_dek((await db.get(MimiConversation, cid)).dek_wrapped)
    return json.loads(
        crypto.open_content(
            dek, change.operation_ciphertext, aad=crypto.change_set_aad(cid, change.id)
        )
    )


@pytest.mark.parametrize("attack_reads", ["none", "current_ids", "unrelated_read"])
def test_prior_run_selection_cannot_authorize_revision_even_with_current_reads(
    pg_dsn, monkeypatch, live_double, attack_reads
):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, _, ids, initial_id, decision = await prepare(maker, 4)
        targets = list(ids)
        async with maker() as db:
            unrelated = Task(title="Synthetic unrelated owner118")
            db.add(unrelated)
            await db.flush()
            unrelated_id = unrelated.id
            ids.append(unrelated_id)
            await db.commit()
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        phase, step, old_selection = "seed", 0, None
        wires = []

        async def fake(messages, **kwargs):
            nonlocal step
            wire = build_request(
                messages,
                kwargs["settings"],
                agent_contract=True,
                force_task_tool=kwargs["force_task_tool"],
                final_answer_only=kwargs.get("final_answer_only", False),
            )
            wires.append(wire)
            assert wire["tool_choice"] == "auto"
            if (
                phase == "seed"
                and step == 0
                or phase == "attack"
                and step == 0
                and attack_reads == "current_ids"
            ):
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id=f"inspect-{phase}",
                            name="task.inspect_batch.v1",
                            arguments={
                                "ids": [str(i) for i in targets],
                                "projection": ["id", "title"],
                            },
                        ),
                    )
                )
            elif phase == "seed" and step == 1:
                rows = json.loads(messages[-1]["content"])["rows"]
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id="fresh-seed-selection",
                            name="task.freeze_selection.v1",
                            arguments={
                                "intent": "Synthetic full set",
                                "variants_considered": ["Explicit synthetic IDs"],
                                "explicitly_named_subset": True,
                                "members": [
                                    {
                                        "id": r["id"],
                                        "classification": "included",
                                        "reason": "Explicit set",
                                    }
                                    for r in rows
                                ],
                            },
                        ),
                    )
                )
            elif phase == "attack" and step == 0 and attack_reads == "unrelated_read":
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id="unrelated-count",
                            name="task.inspect_batch.v1",
                            arguments={"ids": [str(unrelated_id)], "projection": ["id", "title"]},
                        ),
                    )
                )
            else:
                selection = (
                    json.loads(messages[-1]["content"])["selection"]
                    if phase == "seed"
                    else old_selection
                )
                outcome = PreviewCandidate(
                    tool="task.collection_candidate.v1",
                    arguments={
                        "selection_id": selection["selection_id"],
                        "entries": [
                            {
                                "action": "edit",
                                "id": m["id"],
                                "expected_collection_version": m["collection_version"],
                                "fields": {"priority": "p1"},
                            }
                            for m in selection["members"]
                        ],
                    },
                )
            step += 1
            return AgentCompletion(
                outcome=outcome,
                response_id=f"synthetic-{phase}-{step}",
                usage={},
                provider="Synthetic",
                model="deepseek/deepseek-v4.1-flash",
            )

        monkeypatch.setattr(service, "openrouter_complete", fake)
        try:
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                conv.route_config = route()
                await db.commit()
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="seed-current-selection",
                        content="Lập lại preview toàn bộ nhóm",
                        intent="revise_pending_preview",
                        expected_generation=conv.generation,
                        expected_change_set_id=initial_id,
                        expected_change_set_digest=decision.digest,
                    ),
                )
                await db.commit()
                assert view["runs"][-1]["state"] == "waiting_confirmation" and len(wires) == 3
                old = next(
                    c
                    for c in (
                        await db.scalars(
                            select(MimiChangeSet)
                            .join(MimiRun)
                            .where(MimiRun.conversation_id == cid)
                        )
                    ).all()
                    if c.state == "pending"
                )
                old_id, old_digest = old.id, old.digest_sha256
                preserved = (old.digest_sha256, old.nonce, old.expires_at, old.operation_ciphertext)
                old_op = await operation(db, cid, old)
                # Authentic prior-run selection with encrypted versioned read receipts.
                event = (
                    await db.scalars(
                        select(MimiEvent).where(
                            MimiEvent.run_id == old.run_id, MimiEvent.kind == "selection.frozen"
                        )
                    )
                ).one()
                dek = crypto.unwrap_dek((await db.get(MimiConversation, cid)).dek_wrapped)
                old_selection = json.loads(
                    crypto.open_content(
                        dek,
                        event.payload["body_ciphertext"],
                        aad=crypto.event_content_aad(event.run_id, event.sequence, event.kind),
                    )
                )
                assert old_selection["selection_id"] == old_op["args"]["selection_id"]
            phase, step = "attack", 0
            async with maker() as db:
                generation = (await db.get(MimiConversation, cid)).generation
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id=f"attack-old-selection-{attack_reads}",
                        content="Giữ cùng nhóm và ưu tiên",
                        intent="revise_pending_preview",
                        expected_generation=generation,
                        expected_change_set_id=old_id,
                        expected_change_set_digest=old_digest,
                    ),
                )
                await db.commit()
            async with maker() as db:
                old = await db.get(MimiChangeSet, old_id)
                assert old.state == "pending", "OWNER118_CURRENT_RUN_SELECTION_REQUIRED"
                assert (
                    old.digest_sha256,
                    old.nonce,
                    old.expires_at,
                    old.operation_ciphertext,
                ) == preserved
                run = await db.get(MimiRun, UUID(str(view["runs"][-1]["id"])))
                assert (
                    run.state == "halted"
                    and run.error_code
                    == "provider_contract_provider_revision_requires_current_run_selection"
                )
                assert (
                    await db.scalars(
                        select(MimiEvent).where(
                            MimiEvent.run_id == run.id, MimiEvent.kind == "selection.frozen"
                        )
                    )
                ).all() == []
                reads = (
                    await db.scalars(
                        select(MimiEvent).where(
                            MimiEvent.run_id == run.id, MimiEvent.kind == "tool.read_result"
                        )
                    )
                ).all()
                assert len(reads) == (0 if attack_reads == "none" else 1)
                assert all(
                    t.priority is None and t.collection_version == 1
                    for t in (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                )
                assert len(wires) == (4 if attack_reads == "none" else 5)
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_single_create_revision_rejects_collection_terminal_at_service_gate(
    pg_dsn, monkeypatch, live_double
):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor = auth()
        cid = None
        calls = []
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)

        async def fake(messages, **kwargs):
            wire = build_request(
                messages,
                kwargs["settings"],
                agent_contract=True,
                force_task_tool=kwargs["force_task_tool"],
            )
            calls.append(wire)
            if len(calls) == 1:
                candidate = {"title": "Synthetic create only"}
                validate_task_candidate(candidate, require_id=False)
                outcome = PreviewCandidate(tool=CREATE_CANDIDATE_TOOL, arguments=candidate)
            else:
                assert kwargs["force_task_tool"] and not kwargs["settings"].mimi_revision_collection
                assert wire["tool_choice"]["function"]["name"] == CREATE_CANDIDATE_TOOL
                outcome = PreviewCandidate(
                    tool="task.collection_candidate.v1",
                    arguments={
                        "selection_id": str(uuid7()),
                        "entries": [
                            {
                                "action": "create",
                                "fields": {"title": "Synthetic wrong replacement kind"},
                            }
                        ],
                    },
                )
            return AgentCompletion(
                outcome=outcome,
                response_id=f"synthetic-single-{len(calls)}",
                usage={},
                provider="Synthetic",
                model="deepseek/deepseek-v4.1-flash",
            )

        monkeypatch.setattr(service, "openrouter_complete", fake)
        try:
            async with maker() as db:
                cid = (await service.create_conversation(db, actor, service.ConversationCreate()))[
                    "id"
                ]
                conv = await db.get(MimiConversation, cid)
                conv.route_config = route()
                await db.commit()
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="single-original",
                        content="Tạo Synthetic create only",
                        expected_generation=conv.generation,
                    ),
                )
                await db.commit()
                assert view["runs"][-1]["state"] == "waiting_confirmation"
                original = await db.get(MimiChangeSet, UUID(str(view["change_sets"][-1]["id"])))
                assert (await operation(db, cid, original))["tool"] == "task.create.v1"
                preserved = (
                    original.digest_sha256,
                    original.nonce,
                    original.expires_at,
                    original.operation_ciphertext,
                )
                oid = original.id
                generation = (await db.get(MimiConversation, cid)).generation
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="single-wrong-collection",
                        content="Sửa preview",
                        intent="revise_pending_preview",
                        expected_generation=generation,
                        expected_change_set_id=oid,
                        expected_change_set_digest=original.digest_sha256,
                    ),
                )
                await db.commit()
                original = await db.get(MimiChangeSet, oid)
                assert original.state == "pending", "OWNER118_BOUND_PREVIEW_KIND_REQUIRED"
                assert (
                    original.digest_sha256,
                    original.nonce,
                    original.expires_at,
                    original.operation_ciphertext,
                ) == preserved
                assert (
                    view["runs"][-1]["error_code"]
                    == "provider_contract_provider_revision_must_return_task_tool"
                )
                assert len(calls) == 2
        finally:
            if cid:
                await cleanup(maker, cid, [])
            await engine.dispose()

    asyncio.run(scenario())
