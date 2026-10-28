"""Server-bound ordinary followups: no forced revision or NL routing."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import cleanup, prepare
from test_mimi_night_egress_pg import completion, configure
from test_mimi_sync_failure_pg import local_sync_contract  # noqa: F401

from app.agent import service
from app.agent.context import (
    AssistantText,
    Clarification,
    PreviewCandidate,
    ToolRequest,
    ToolRequests,
)
from app.agent.models import MimiChangeSet, MimiConversation
from app.agent.openrouter import (
    CandidateContractError,
    ProviderDispatchError,
    parse_agent_completion,
)
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL
from app.core.database_urls import async_postgres_url
from app.core.qa_event_loop import selector_loop_factory
from app.domain.models import Task

pytestmark = [pytest.mark.pg, pytest.mark.usefixtures("local_sync_contract")]


@pytest.mark.parametrize(
    "mode", ["valid", "text", "clarification", "read", "invalid", "failure", "reject", "expiry"]
)
def test_auto_keeps_or_replaces_only_exact_observed_pending_after_io(pg_dsn, monkeypatch, mode):
    from test_mimi_owner296 import call, payload

    configure(monkeypatch)

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        actor, cid, _, ids, old_id, decision = await prepare(maker, 2)
        attempts = []

        async def provider(messages, **kwargs):
            attempts.append(True)
            assert not kwargs.get("force_task_tool")
            if mode == "text" or (mode in {"read", "invalid"} and len(attempts) > 1):
                return completion(AssistantText(text="Chỉ trò chuyện; giữ phương án đang chờ."))
            if mode == "clarification":
                return completion(Clarification(question="Bạn muốn thảo luận thêm phần nào?"))
            if mode == "read":
                return completion(
                    ToolRequests(
                        requests=(
                            ToolRequest(
                                call_id="current-read",
                                name="task.inspect_batch.v1",
                                arguments={"ids": [str(ids[0])]},
                            ),
                        )
                    )
                )
            if mode == "failure":
                raise ProviderDispatchError("failed", 400)
            if mode == "invalid":
                try:
                    parse_agent_completion(
                        payload(
                            [
                                call(
                                    COLLECTION_CANDIDATE_TOOL,
                                    {
                                        "entries": [
                                            {
                                                "action": "create",
                                                "fields": {"title": "Synthetic B", "pinned": None},
                                            }
                                        ]
                                    },
                                )
                            ]
                        )
                    )
                except CandidateContractError as error:
                    error.terminal_receipt = {
                        "id": "synthetic-invalid",
                        "usage": {"cost": 0},
                        "model": kwargs["settings"].mimi_route_model,
                        "provider": "Synthetic",
                    }
                    raise
            if mode in {"reject", "expiry"}:
                async with maker() as db:
                    if mode == "reject":
                        await service.confirm_change_set(
                            db,
                            actor,
                            old_id,
                            service.ConfirmationDecision(
                                digest=decision.digest, nonce=decision.nonce, decision="reject"
                            ),
                            "other-tab-reject",
                        )
                    else:
                        (await db.get(MimiChangeSet, old_id)).expires_at = datetime.now(
                            UTC
                        ) - timedelta(seconds=1)
                    await db.commit()
            return completion(
                PreviewCandidate(
                    tool=COLLECTION_CANDIDATE_TOOL,
                    arguments={
                        "entries": [{"action": "create", "fields": {"title": "Synthetic B"}}],
                    },
                )
            )

        monkeypatch.setattr(service, "openrouter_complete", provider)
        try:
            async with maker() as db:
                before = [(await db.get(Task, tid)).model_dump() for tid in ids]
                old = await db.get(MimiChangeSet, old_id)
                binding = (old.digest_sha256, old.nonce, old.operation_ciphertext)
                conv = await db.get(MimiConversation, cid)
                result = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="natural-followup",
                        content="Tiếp tục theo yêu cầu mới của tôi.",
                        expected_generation=conv.generation,
                    ),
                )
                await db.commit()
                changes = result["change_sets"]
                original = next(c for c in changes if str(c["id"]) == str(old_id))
                if mode == "valid":
                    assert original["state"] == "stale" and len(changes) == 2
                    assert sum(c["state"] == "pending" for c in changes) == 1
                elif mode in {"reject", "expiry"}:
                    assert len(changes) == 1
                    assert result["runs"][-1]["error_code"] == "preview_frontier_changed"
                else:
                    assert len(changes) == 1 and original["state"] == "pending"
                await db.refresh(old)
                assert (old.digest_sha256, old.nonce, old.operation_ciphertext) == binding
                assert result["receipts"] == []
                assert [(await db.get(Task, tid)).model_dump() for tid in ids] == before
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)
