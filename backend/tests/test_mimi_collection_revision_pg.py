"""Bound collection revisions through the real service and wire builder, synthetic only."""

import asyncio
import json
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import cleanup, local_contract, prepare  # noqa: F401

from app.agent import crypto, service
from app.agent.context import (
    AssistantText,
    Blocked,
    Clarification,
    Draft,
    PreviewCandidate,
    ToolRequest,
    ToolRequests,
)
from app.agent.models import MimiChangeSet, MimiConversation, MimiEvent
from app.agent.openrouter import AgentCompletion, ProviderDispatchError, build_request
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import Task

pytestmark = pytest.mark.pg


@pytest.mark.parametrize(
    "mode",
    [
        "full_subset_full",
        "text",
        "clarification",
        "draft",
        "blocked",
        "single_create",
        "failure",
        "partial",
        "missing_current_read",
        "selection_mismatch",
    ],
)
def test_revision_read_phase_exact_selection_and_nonreplacement_retention(
    pg_dsn, monkeypatch, mode
):
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
    if mode == "partial":
        monkeypatch.setenv("MIMI_RUN_MAX_TURNS", "1")
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, old_run, ids, old_id, old_decision = await prepare(maker, 4)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        wires = []
        step = 0
        target = ids[:3]

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
            assert kwargs["settings"].mimi_revision_collection
            assert wire["tool_choice"] == ("none" if mode == "partial" else "auto")
            if mode == "failure":
                raise ProviderDispatchError("failed", 400)
            terminals = {
                "text": AssistantText(text="Preview đã đổi (synthetic invalid claim)"),
                "clarification": Clarification(question="Chọn nhóm nào?"),
                "draft": Draft(text="Kế hoạch thay đổi"),
                "blocked": Blocked(reason="Thiếu dữ liệu"),
                "partial": AssistantText(text="Chưa đủ bằng chứng để sửa preview."),
            }
            if mode in terminals:
                outcome = terminals[mode]
            elif mode == "single_create":
                outcome = PreviewCandidate(
                    tool="task.create_candidate.v1", arguments={"title": "Synthetic wrong terminal"}
                )
            elif mode == "missing_current_read":
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id="without-current-read",
                            name="task.freeze_selection.v1",
                            arguments={
                                "intent": "Sửa phạm vi",
                                "variants_considered": ["Synthetic exact IDs"],
                                "explicitly_named_subset": True,
                                "members": [
                                    {
                                        "id": str(i),
                                        "classification": "included",
                                        "reason": "Synthetic",
                                    }
                                    for i in target
                                ],
                            },
                        ),
                    )
                )
            elif step % 3 == 0:
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id=f"inspect-{step}",
                            name="task.inspect_batch.v1",
                            arguments={
                                "ids": [str(i) for i in target],
                                "projection": ["id", "title"],
                            },
                        ),
                    )
                )
            elif step % 3 == 1:
                rows = json.loads(messages[-1]["content"])["rows"]
                assert {r["id"] for r in rows} == {str(i) for i in target}
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id=f"freeze-{step}",
                            name="task.freeze_selection.v1",
                            arguments={
                                "intent": "Sửa phạm vi",
                                "variants_considered": ["Synthetic exact IDs"],
                                "explicitly_named_subset": True,
                                "members": [
                                    {
                                        "id": r["id"],
                                        "classification": "included",
                                        "reason": "Đúng phạm vi",
                                    }
                                    for r in rows
                                ],
                            },
                        ),
                    )
                )
            else:
                selection = json.loads(messages[-1]["content"])["selection"]
                members = selection["members"]
                if mode == "selection_mismatch":
                    members = members[:-1]
                outcome = PreviewCandidate(
                    tool="task.collection_candidate.v1",
                    arguments={
                        "selection_id": selection["selection_id"],
                        "entries": [
                            {
                                "action": "edit",
                                "id": r["id"],
                                "expected_collection_version": r["collection_version"],
                                "fields": {"priority": "p1"},
                            }
                            for r in members
                        ],
                    },
                )
            step += 1
            return AgentCompletion(
                outcome=outcome,
                response_id=f"synthetic-revision-{step}",
                usage={},
                provider="Synthetic",
                model="deepseek/deepseek-v4.1-flash",
            )

        monkeypatch.setattr(service, "openrouter_complete", fake)
        try:
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                conv.route_config = {
                    "profile_id": "deepseek",
                    "effort": "high",
                    "input_tokens": 100000,
                    "routing_mode": "exact",
                }
                await db.commit()
                old = await db.get(MimiChangeSet, old_id)
                preserved = (old.digest_sha256, old.nonce, old.expires_at, old.operation_ciphertext)
            current_id, current_digest = old_id, old_decision.digest
            for turn in range(2 if mode == "full_subset_full" else 1):
                target = ids[:3] if turn == 0 else ids
                async with maker() as db:
                    generation = (await db.get(MimiConversation, cid)).generation
                    started = datetime.now(UTC)
                    if mode == "selection_mismatch":
                        with pytest.raises(HTTPException) as rejected:
                            await service.send_message(
                                db,
                                actor,
                                cid,
                                service.MessageCreate(
                                    client_id=f"revision-{mode}-{turn}",
                                    content="Chỉ ba Task đã chọn"
                                    if turn == 0
                                    else "Lấy lại toàn bộ nhóm",
                                    intent="revise_pending_preview",
                                    expected_generation=generation,
                                    expected_change_set_id=current_id,
                                    expected_change_set_digest=current_digest,
                                ),
                            )
                        assert rejected.value.status_code == 409
                        assert (
                            rejected.value.detail == "collection_must_match_exact_frozen_selection"
                        )
                        await db.rollback()
                        view = await service.conversation_view(db, actor, cid)
                    else:
                        view = await service.send_message(
                            db,
                            actor,
                            cid,
                            service.MessageCreate(
                                client_id=f"revision-{mode}-{turn}",
                                content="Chỉ ba Task đã chọn"
                                if turn == 0
                                else "Lấy lại toàn bộ nhóm",
                                intent="revise_pending_preview",
                                expected_generation=generation,
                                expected_change_set_id=current_id,
                                expected_change_set_digest=current_digest,
                            ),
                        )
                    await db.commit()
                async with maker() as db:
                    old = await db.get(MimiChangeSet, old_id)
                    assert (
                        old.digest_sha256,
                        old.nonce,
                        old.expires_at,
                        old.operation_ciphertext,
                    ) == preserved
                    tasks = (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                    assert all(t.priority is None and t.collection_version == 1 for t in tasks)
                    changes = (
                        await db.scalars(
                            select(MimiChangeSet)
                            .join(service.MimiRun, MimiChangeSet.run_id == service.MimiRun.id)
                            .where(service.MimiRun.conversation_id == cid)
                        )
                    ).all()
                    if mode == "full_subset_full":
                        assert old.state == "stale"
                        new = next(c for c in changes if c.state == "pending")
                        dek = crypto.unwrap_dek((await db.get(MimiConversation, cid)).dek_wrapped)
                        operation = json.loads(
                            crypto.open_content(
                                dek,
                                new.operation_ciphertext,
                                aad=crypto.change_set_aad(cid, new.id),
                            )
                        )
                        assert {e["id"] for e in operation["args"]["entries"]} == {
                            str(i) for i in target
                        }
                        assert 179 * 60 < (new.expires_at - started).total_seconds() < 181 * 60
                        current_id, current_digest = new.id, new.digest_sha256
                        events = (
                            await db.scalars(
                                select(MimiEvent).where(
                                    MimiEvent.run_id == new.run_id,
                                    MimiEvent.kind == "tool.read_result",
                                )
                            )
                        ).all()
                        assert events
                        with pytest.raises(HTTPException):
                            await service.confirm_change_set(
                                db, actor, old_id, old_decision, f"superseded-old-{cid}"
                            )
                        await db.rollback()
                    else:
                        assert len(changes) == 1 and old.state == "pending"
                        assert view["runs"][-1]["state"] != "waiting_confirmation"
                        # Retained bytes do not rebase the old generation/nonce authority.
                        with pytest.raises(HTTPException):
                            await service.confirm_change_set(
                                db, actor, old_id, old_decision, f"retained-old-frontier-{cid}"
                            )
                        await db.rollback()
            assert len(wires) == (
                6 if mode == "full_subset_full" else 3 if mode == "selection_mismatch" else 1
            )
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())
