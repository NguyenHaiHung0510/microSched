"""Finite synthetic collection selection, fanout and endpoint-policy oracles."""

import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.agent.context import AssistantText, ToolRequest, ToolRequests
from app.agent.loop import LoopLimits, messages_final_only, run_read_loop
from app.agent.openrouter import AgentCompletion, RouteContractError, build_request
from app.agent.route_config import bind_configuration, default_configuration, profiles_for_ui
from app.agent.route_pool import ADMITTED_MODEL, CatalogCache, NoEligibleEndpoint, eligible_pool
from app.agent.selection import SelectionCandidate, bind_selection, covered_versions
from app.agent.task_collection import CollectionCandidate, TaskCommand
from app.core.settings import Settings


def settings(**extra):
    fields = dict(
        app_env="local",
        oauth_state_secret="synthetic-collection-test",
        mimi_collection_enabled=True,
        mimi_real_chat_enabled=True,
        mimi_standard_api_key="synthetic-not-sent",
        mimi_context_v1_enabled=True,
        mimi_live_provider_enabled=True,
        mimi_route_model=ADMITTED_MODEL,
        mimi_route_provider="deepinfra",
        mimi_route_quantization="fp8",
        mimi_route_reasoning_effort="high",
        mimi_route_max_input_price=0.2,
        mimi_route_max_output_price=0.6,
        mimi_route_allowed_quantizations="fp8",
        mimi_route_forced_tool_choice="function",
    )
    return Settings(_env_file=None, **(fields | extra))


def catalog(*rows):
    row = dict(
        tag="deepinfra/fp8",
        uptime_last_1d=99.7,
        uptime_last_30m=99.1,
        quantization="fp8",
        supported_parameters=["tools", "tool_choice", "reasoning"],
        pricing={"prompt": "0.0000002", "completion": "0.0000006"},
    )
    return {"data": {"id": ADMITTED_MODEL, "endpoints": [row | r for r in (rows or ({},))]}}


def row(tid):
    return {"id": str(tid), "collection_version": 1, "source_version": "2026-10-09T00:00:00+07:00"}


def read(rows, *, query=None, cursor=None, next_cursor=None, event_id=None):
    return {
        "event_id": str(event_id or uuid4()),
        "tool": "task.query.v1",
        "arguments": {"filter": query or {}, "limit": 50, "cursor": cursor},
        "result": {
            "rows": rows,
            "next_cursor": next_cursor,
            "data_as_of": "2026-10-09T00:00:00+07:00",
        },
    }


def selection(ids, *, subset=False, pending=()):
    return SelectionCandidate(
        intent="Đổi ưu tiên các buổi tập",
        variants_considered=("tập luyện", "the duc", "luyện tập", "tap luyen"),
        variants_pending=pending,
        explicitly_named_subset=subset,
        members=tuple(
            {"id": tid, "classification": "included", "reason": "Buổi tập thực sự"} for tid in ids
        ),
    )


def test_training49_frozen_classifications_are_not_query_completion():
    ids = [uuid4() for _ in range(49)]
    candidate = selection(ids)
    members = list(candidate.members)
    members[-1] = members[-1].model_copy(
        update={"classification": "excluded", "reason": "Bài viết chỉ nhắc tập luyện"}
    )
    candidate = candidate.model_copy(update={"members": tuple(members)})
    result = bind_selection(candidate, [read([row(tid) for tid in ids])])
    assert result["semantic_complete"] and result["query_complete"]
    assert len(covered_versions(result, ids[:48])) == 48
    with pytest.raises(Exception, match="exact_frozen_selection"):
        covered_versions(result, ids)
    incomplete = [read([row(tid) for tid in ids], query={"title_contains": "tập luyện"})]
    with pytest.raises(ValueError, match="unresolved_obligations"):
        bind_selection(candidate, incomplete)
    subset = bind_selection(
        candidate.model_copy(update={"explicitly_named_subset": True}), incomplete
    )
    assert subset["query_complete"] and not subset["semantic_complete"]
    assert set(subset["unproved_variants"]) == {"the duc", "luyện tập", "tap luyen"}


def test_four_pages_union_cursor_version_and_subset_obligations():
    ids = [uuid4() for _ in range(200)]
    pages = [
        read(
            [row(t) for t in ids[i : i + 50]],
            cursor=f"c{i}" if i else None,
            next_cursor=f"c{i + 50}" if i < 150 else None,
        )
        for i in range(0, 200, 50)
    ]
    frozen = bind_selection(selection(ids), pages)
    assert frozen["semantic_complete"] and len(frozen["members"]) == 200
    assert len(frozen["queries"][0]["pages"]) == 4
    with pytest.raises(ValueError, match="unresolved_obligations"):
        bind_selection(selection(ids[50:]), pages[1:])
    partial = bind_selection(selection(ids[:50], subset=True), pages[:1])
    assert partial["queries"][0]["open_cursors"] == ["c50"] and not partial["semantic_complete"]
    changed = copy.deepcopy(pages)
    changed.append(read([row(ids[0]) | {"collection_version": 2}]))
    with pytest.raises(ValueError, match="version_changed"):
        bind_selection(selection(ids), changed)


def test_collection_bounds_and_ungranted_fields_fail_before_execution():
    entry = TaskCommand(action="create", fields={"title": "Synthetic", "pinned": True})
    assert len(CollectionCandidate(entries=(entry,) * 200).entries) == 200
    for entries in ((), (entry,) * 201):
        with pytest.raises(ValidationError):
            CollectionCandidate(entries=entries)
    for fields in (
        {"title": "Synthetic", "is_private": True},
        {"title": "Synthetic", "due_at": "2026-10-10T10:00:00Z"},
    ):
        with pytest.raises(ValidationError):
            TaskCommand(action="create", fields=fields)


@pytest.mark.parametrize("bad", ["unknown_tool", "malformed"])
def test_whole_fanout_validates_before_first_read(bad):
    async def scenario():
        reads = []
        reqs = [
            ToolRequest(call_id=f"r{i}", name="task.query.v1", arguments={"limit": i + 1})
            for i in range(8)
        ]
        reqs[-1] = ToolRequest(
            call_id="bad",
            name="shell" if bad == "unknown_tool" else "task.query.v1",
            arguments={} if bad == "unknown_tool" else {"limit": 51},
        )

        async def invoke(*_):
            return AgentCompletion(
                outcome=ToolRequests(requests=tuple(reqs)),
                response_id="synthetic",
                usage={},
                model=ADMITTED_MODEL,
                provider="synthetic",
            )

        async def execute(*args):
            reads.append(args)

        with pytest.raises(RouteContractError):
            await run_read_loop(
                [],
                limits=LoopLimits(32, 64, 200000, datetime.now(UTC) + timedelta(seconds=5)),
                invoke_model=invoke,
                execute_read=execute,
            )
        assert reads == []

    asyncio.run(scenario())


def test_fanout8_remaining3_final_wire_omits_tools_and_preserves_obligations():
    async def scenario():
        reads, wires = [], []

        async def invoke(messages, turn):
            final = messages_final_only(messages)
            wires.append(
                build_request(
                    messages, settings=settings(), agent_contract=True, final_answer_only=final
                )
            )
            if final:
                return AgentCompletion(
                    outcome=AssistantText(text="Đã đọc3, còn5 chưa đọc."),
                    response_id="synthetic",
                    usage={},
                    provider="synthetic",
                    model=ADMITTED_MODEL,
                )
            return AgentCompletion(
                outcome=ToolRequests(
                    requests=tuple(
                        ToolRequest(
                            call_id=f"r{i}", name="task.query.v1", arguments={"limit": i + 1}
                        )
                        for i in range(8)
                    )
                ),
                response_id="synthetic",
                usage={},
                provider="synthetic",
                model=ADMITTED_MODEL,
            )

        async def execute(name, args):
            reads.append(args)
            return {
                "coverage": "partial",
                "next_cursor": "opaque-cursor",
                "alias_pending": ["the duc"],
            }

        result = await run_read_loop(
            [],
            limits=LoopLimits(32, 3, 200000, datetime.now(UTC) + timedelta(seconds=5)),
            invoke_model=invoke,
            execute_read=execute,
        )
        assert result.turns == 2 and result.tool_calls == 3 and len(reads) == 3
        assert "tools" not in wires[-1] and wires[-1]["tool_choice"] == "none"
        assert "opaque-cursor" in json.dumps(wires[-1]) and "the duc" in json.dumps(wires[-1])
        omitted = json.loads(
            next(
                m["content"]
                for m in result.messages
                if "not_run_reads" in m.get("content", "")
                and not m["content"].startswith("MIMI_SERVER")
            )
        )
        assert len(omitted["not_run_reads"]) == 5

    asyncio.run(scenario())


@pytest.mark.parametrize("effort", ["low", "high", "max"])
def test_pool_native_exact_model_effort_privacy_price_and_variant_boundary(effort):
    pool = eligible_pool(catalog(), model=ADMITTED_MODEL, effort=effort)
    wire = build_request(
        [],
        settings=settings(
            mimi_route_mode="adaptive",
            mimi_route_reasoning_effort=effort,
            mimi_route_allowed_providers=",".join(pool.tags),
        ),
        agent_contract=True,
    )
    assert wire["model"] == ADMITTED_MODEL and wire["reasoning"]["effort"] == effort
    assert pool.effort == effort
    assert wire["provider"]["only"] == ["deepinfra/fp8"]
    assert wire["provider"]["zdr"] is True and wire["provider"]["data_collection"] == "deny"
    assert wire["provider"]["require_parameters"] is True and "order" not in wire["provider"]
    assert wire["provider"]["max_price"] == {"prompt": 0.2, "completion": 0.6}
    with pytest.raises(NoEligibleEndpoint):
        eligible_pool(
            catalog({"tag": "deepinfra"}, {"tag": "deepinfra/fp8", "uptime_last_1d": 95}),
            model=ADMITTED_MODEL,
            effort=effort,
        )
    for override in (
        {"quantization": "fp4"},
        {"zdr": False},
        {"data_collection": "allow"},
        {"supported_parameters": ["reasoning"]},
        {"pricing": {"prompt": "NaN", "completion": ".0000006"}},
        {"supported_reasoning_efforts": ["high"] if effort == "low" else ["low"]},
    ):
        with pytest.raises(NoEligibleEndpoint):
            eligible_pool(catalog(override), model=ADMITTED_MODEL, effort=effort)
    for model, unsupported in (("xiaomi/mimo-v2.6-pro", effort), (ADMITTED_MODEL, "medium")):
        with pytest.raises(NoEligibleEndpoint):
            eligible_pool(catalog(), model=model, effort=unsupported)
    assert [p["id"] for p in profiles_for_ui(settings()) if p["available"]] == ["deepseek"]
    with pytest.raises(HTTPException):
        default_configuration(settings(mimi_route_model="unselected/unknown"))


@pytest.mark.parametrize("uptime", [95, None, float("nan"), float("inf"), True])
def test_strict_uptime_missing_and_nonfinite_excluded(uptime):
    with pytest.raises(NoEligibleEndpoint):
        eligible_pool(catalog({"uptime_last_1d": uptime}), model=ADMITTED_MODEL, effort="high")
    assert (
        eligible_pool(
            catalog({"uptime_last_1d": 95.01}), model=ADMITTED_MODEL, effort="high"
        ).threshold
        == 95
    )
    pool = eligible_pool(
        catalog({"uptime_last_30m": 97}),
        model=ADMITTED_MODEL,
        effort="high",
        threshold=96,
        window="30m",
    )
    assert pool.threshold == 96 and pool.window == "30m"


def test_catalog_singleflight_ttl_cooldown_size_timeout_and_fail_closed(monkeypatch):
    async def scenario():
        cache = CatalogCache()
        requests = []

        async def handler(request):
            requests.append(request)
            assert "authorization" not in request.headers
            return httpx.Response(200, json=catalog())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            a, b = await asyncio.gather(
                cache.refresh(settings(), client=client), cache.refresh(settings(), client=client)
            )
            assert a == b and len(requests) == 1
            await cache.refresh(settings(), client=client, manual=True)
            assert len(requests) == 2
            with pytest.raises(NoEligibleEndpoint, match="cooldown"):
                await cache.refresh(settings(), client=client, manual=True)

        async def unavailable(request):
            raise httpx.ReadTimeout("synthetic catalog timeout")

        async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
            with pytest.raises(NoEligibleEndpoint):
                await CatalogCache().refresh(settings(), client=client)

        async def huge(request):
            return httpx.Response(200, content=b"x" * 2097153)

        async with httpx.AsyncClient(transport=httpx.MockTransport(huge)) as client:
            with pytest.raises(NoEligibleEndpoint):
                await CatalogCache().refresh(settings(), client=client)

    asyncio.run(scenario())


def test_feature_off_and_forced_collection_revision_preserve_exact_tool():
    off = build_request([], settings=settings(mimi_collection_enabled=False), agent_contract=True)
    assert "task.collection_candidate.v1" not in {t["function"]["name"] for t in off["tools"]}
    on = build_request(
        [],
        settings=settings(mimi_revision_collection=True),
        agent_contract=True,
        force_task_tool=True,
    )
    assert on["tool_choice"]["function"]["name"] == "task.collection_candidate.v1"
    configured = bind_configuration(
        settings(),
        {
            "profile_id": "deepseek",
            "effort": "high",
            "input_tokens": 100000,
            "min_uptime_percent": 96,
            "uptime_window": "30m",
        },
    )
    assert (
        configured.mimi_route_mode == "adaptive" and configured.mimi_route_min_uptime_percent == 96
    )
