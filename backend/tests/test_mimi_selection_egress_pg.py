"""Subset A prose can quote unclassified B: real PG + actual serializer controls."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import cleanup
from test_mimi_night_egress_pg import completion, configure, seed, send, trigger_compaction
from test_mimi_selection_egress import MARKER
from test_mimi_sync_failure_pg import local_sync_contract  # noqa: F401

from app.agent import crypto, service
from app.agent.context import AssistantText, PreviewCandidate, ToolRequest, ToolRequests
from app.agent.models import MimiConversation, MimiEvent
from app.agent.selection import load_selection
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL
from app.core.database_urls import async_postgres_url
from app.core.qa_event_loop import selector_loop_factory
from app.domain.models import Task

pytestmark = [pytest.mark.pg, pytest.mark.usefixtures("local_sync_contract")]


@pytest.mark.parametrize("b_state", ["active", "private", "deleted"])
def test_selection_subset_source_closure_opaque_text_and_independent_query_evidence(
    pg_dsn,
    monkeypatch,
    b_state,
):
    configure(monkeypatch)

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        actor, cid, aid, _ = await seed(maker)
        prefix = "subset-" + uuid4().hex
        async with maker() as db:
            (await db.get(Task, aid)).title = prefix + " A"
            other = Task(title=prefix + " " + MARKER)
            db.add(other)
            await db.commit()
            bid = other.id
        stage, positives, final_wires = "query", [], []
        selection_id = None
        receipt_id = None

        async def provider(messages, **kwargs):
            nonlocal selection_id
            current = max(i for i, m in enumerate(messages) if m["role"] == "user")
            tools = [m for m in messages[current + 1 :] if m["role"] == "tool"]
            if stage in {"query", "select"}:
                if not tools:
                    return completion(
                        ToolRequests(
                            requests=(
                                ToolRequest(
                                    call_id=stage + "-AB",
                                    name="task.query.v1",
                                    arguments={
                                        "filter": {"title_contains": prefix},
                                        "projection": ["id", "title"],
                                    },
                                ),
                            )
                        )
                    )
                assert MARKER in json.dumps(messages)
                positives.append(stage)
                if stage == "query":
                    return completion(AssistantText(text="Đã đọc hai nguồn hợp lệ."))
                if len(tools) == 1:
                    rows = json.loads(tools[0]["content"])["rows"]
                    assert {row["id"] for row in rows} == {str(aid), str(bid)}
                    return completion(
                        ToolRequests(
                            requests=(
                                ToolRequest(
                                    call_id="only-A",
                                    name="task.freeze_selection.v1",
                                    arguments={
                                        "intent": "Select A using " + MARKER,
                                        "variants_considered": [prefix],
                                        "explicitly_named_subset": True,
                                        "members": [
                                            {
                                                "id": str(aid),
                                                "classification": "included",
                                                "reason": MARKER,
                                            }
                                        ],
                                    },
                                ),
                            )
                        )
                    )
                snapshot = json.loads(tools[-1]["content"])["selection"]
                selection_id = UUID(snapshot["selection_id"])
                assert snapshot["missing_classifications"] == [str(bid)]
                assert snapshot["members"][0]["reason"] == MARKER
                return completion(
                    PreviewCandidate(
                        tool=COLLECTION_CANDIDATE_TOOL,
                        arguments={
                            "selection_id": str(selection_id),
                            "entries": [
                                {
                                    "action": "edit",
                                    "id": str(aid),
                                    "expected_collection_version": snapshot["members"][0][
                                        "collection_version"
                                    ],
                                    "fields": {"priority": "p1"},
                                }
                            ],
                        },
                    )
                )
            wire = json.dumps(messages)
            final_wires.append("helper" if kwargs.get("summary_mode") else "main")
            assert (MARKER in wire) is (b_state == "active")
            # Active query evidence is allowed independently; opaque selection
            # result segments are never the source of that positive control.
            if kwargs.get("summary_mode"):
                sources = json.loads(messages[-1]["content"])["sources"]
                calls = [
                    call
                    for source in sources
                    if source.get("working_history")
                    for m in source["working_history"].get("messages", [])
                    for call in m.get("tool_calls", [])
                ]
                assert not any(c["function"]["name"] == "task.freeze_selection.v1" for c in calls)
                text = (
                    "Hai nguồn vẫn active: " + MARKER
                    if b_state == "active"
                    else "Nguồn lịch sử không còn đủ eligibility."
                )
                return completion(
                    AssistantText(
                        text=json.dumps(
                            {
                                "summary": text,
                                "constraints": [],
                                "supersessions": [],
                                "resolutions": [],
                            }
                        )
                    )
                )
            data = next(
                json.loads(m["content"].split("\n", 1)[1])
                for m in messages
                if (m.get("content") or "").startswith("SERVER-PROVIDED REFERENCE DATA")
            )
            selection = next(x["selection"] for x in data["domain_evidence"] if "selection" in x)
            assert MARKER not in json.dumps(selection)
            assert selection["selection_id"] == str(selection_id)
            assert selection["members"][0]["id"] == str(aid)
            assert selection["coverage"] == "unavailable"
            authority = next(
                json.loads(m["content"])
                for m in messages
                if m["role"] == "system" and "authority_envelope" in m["content"]
            )
            outcomes = authority["pending_state"]["preview_lifecycle"]["historical_outcomes"]
            assert any(o["receipt_id"] == receipt_id for o in outcomes)
            return completion(AssistantText(text="Chỉ đọc trạng thái; không ghi thêm dữ liệu."))

        monkeypatch.setattr(service, "openrouter_complete", provider)
        try:
            await send(maker, actor, cid, "independent-query")
            stage = "select"
            view = await send(maker, actor, cid, "current-selection")
            change = next(c for c in view["change_sets"] if c["state"] == "pending")
            # Immediate current-run selection and Confirm remain functional.
            async with maker() as db:
                result = await service.confirm_change_set(
                    db,
                    actor,
                    UUID(str(change["id"])),
                    service.ConfirmationDecision(
                        digest=change["digest"], nonce=change["nonce"], decision="confirm"
                    ),
                    "subset-A-confirm",
                )
                receipt_id = str(result["id"])
                await db.commit()
                assert (await db.get(Task, aid)).priority == "p1"
                event = (
                    await db.scalars(
                        select(MimiEvent).where(
                            MimiEvent.kind == "selection.frozen",
                            MimiEvent.run_id == UUID(str(view["runs"][-1]["id"])),
                        )
                    )
                ).one()
                original_ciphertext = event.payload["body_ciphertext"]
                event_id = event.id
            if b_state != "active":
                async with maker() as db:
                    task = await db.get(Task, bid)
                    if b_state == "private":
                        task.title, task.body_md, task.is_private = "enc:v1:synthetic", None, True
                    else:
                        task.deleted_at = service.datetime.now(service.UTC)
                    await db.commit()
            stage = "history"
            async with maker() as db:
                await trigger_compaction(db, await db.get(MimiConversation, cid))
            await send(maker, actor, cid, "historical-subset")
            assert "query" in positives and "select" in positives
            assert "helper" in final_wires and "main" in final_wires
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                canonical = await load_selection(
                    db, cid, selection_id, crypto.unwrap_dek(conv.dek_wrapped)
                )
                assert canonical["members"][0]["reason"] == MARKER
                assert (await db.get(MimiEvent, event_id)).payload[
                    "body_ciphertext"
                ] == original_ciphertext
                a = await db.get(Task, aid)
                assert not a.is_private and a.deleted_at is None and a.priority == "p1"
        finally:
            await cleanup(maker, cid, [aid, bid])
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)
