"""Synthetic Chat Undo contracts; SDK doubles prove plumbing, not model intent quality."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx2
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from test_mimi_openai_sdk import _settings

from app.agent import receipt_history, service
from app.agent.context import AssistantText, PreviewCandidate
from app.agent.openrouter import (
    CandidateContractError,
    RouteContractError,
    build_request,
    complete,
    complete_stream,
    parse_agent_completion,
)
from app.agent.task_collection import COLLECTION_TOOL
from app.agent.tools.registry import UNDO_CANDIDATE_TOOL, UndoCandidate, tools_for_settings
from app.core.settings import Settings


def wire(arguments, *, content=None, sibling=None):
    calls = [
        {
            "id": "synthetic-undo",
            "type": "function",
            "function": {"name": UNDO_CANDIDATE_TOOL, "arguments": json.dumps(arguments)},
        }
    ]
    if sibling:
        calls.append(
            {
                "id": "sibling",
                "type": "function",
                "function": {"name": sibling, "arguments": "{}"},
            }
        )
    return {
        "id": "synthetic-undo-response",
        "object": "chat.completion",
        "created": 1,
        "provider": "synthetic-provider",
        "model": "vendor/model",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": content, "tool_calls": calls},
            }
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11, "cost": 0},
    }


@pytest.mark.parametrize("target", ["latest", "exact"])
def test_native_undo_is_one_typed_preview_and_ignores_untrusted_narration(target):
    arguments = {"target": target, "receipt_id": str(uuid4()) if target == "exact" else None}
    outcome = parse_agent_completion(
        wire(arguments, content="Untrusted claim: already applied")
    ).outcome
    assert isinstance(outcome, PreviewCandidate)
    assert outcome.tool == UNDO_CANDIDATE_TOOL and outcome.arguments == arguments


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"target": "latest"},
        {"target": "latest", "receipt_id": str(uuid4())},
        {"target": "exact", "receipt_id": None},
        {"target": "exact", "receipt_id": "guessed"},
        {"target": "another-chat", "receipt_id": None},
        {"target": "latest", "receipt_id": None, "confirm": True},
    ],
)
def test_invalid_undo_selector_never_enters_candidate_correction(arguments):
    with pytest.raises(ValidationError):
        UndoCandidate.model_validate(arguments)
    with pytest.raises(RouteContractError) as caught:
        parse_agent_completion(wire(arguments))
    assert not isinstance(caught.value, CandidateContractError)


@pytest.mark.parametrize(
    "sibling",
    [
        "task.query.v1",
        "task.create_candidate.v2",
        "task.collection_candidate.v1",
        UNDO_CANDIDATE_TOOL,
    ],
)
def test_undo_cannot_share_a_native_tool_turn(sibling):
    with pytest.raises(RouteContractError, match="candidate_cannot_share_tool_turn") as caught:
        parse_agent_completion(wire({"target": "latest", "receipt_id": None}, sibling=sibling))
    assert not isinstance(caught.value, CandidateContractError)


def test_json_prose_does_not_admit_an_undo_candidate():
    terminal = {
        "kind": "preview_candidate",
        "tool": UNDO_CANDIDATE_TOOL,
        "arguments": {"target": "latest", "receipt_id": None},
    }
    with pytest.raises(RouteContractError, match="undo_requires_native_tool_call"):
        parse_agent_completion({"choices": [{"message": {"content": json.dumps(terminal)}}]})


@pytest.mark.parametrize(
    "text",
    [
        "Hoàn tác là gì?",
        "Đừng hoàn tác nhé.",
        'Ví dụ: "hoàn tác cái vừa làm".',
        "Would undo restore the earlier group?",
    ],
)
def test_undo_words_in_a_model_answer_are_plain_text(text):
    result = parse_agent_completion({"choices": [{"message": {"content": text}}]})
    assert result.outcome == AssistantText(text=text)


@pytest.mark.parametrize("enabled", [False, True])
def test_undo_tool_is_collection_gated_and_never_a_read_tool(enabled):
    from app.agent.tools.registry import READ_TOOLS

    settings = Settings(_env_file=None, mimi_collection_enabled=enabled)
    names = {
        item["function"]["name"] for item in tools_for_settings(settings, include_chat_undo=True)
    }
    assert (UNDO_CANDIDATE_TOOL in names) == enabled
    assert UNDO_CANDIDATE_TOOL not in READ_TOOLS


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("target", ["latest", "exact"])
def test_sdk_native_http_and_sse_normalize_the_same_undo_preview(streaming, target):
    arguments = {"target": target, "receipt_id": str(uuid4()) if target == "exact" else None}
    settings = _settings(mimi_route_mode="native", mimi_text_response_format="natural")
    messages = [{"role": "user", "content": "Synthetic natural request"}]
    expected = build_request(messages, settings, stream=streaming, agent_contract=True)
    payload = wire(arguments)
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        assert request.url.path == "/api/v1/chat/completions"
        if not streaming:
            return httpx2.Response(200, json=payload)
        native = [
            {**call, "index": index}
            for index, call in enumerate(payload["choices"][0]["message"]["tool_calls"])
        ]
        chunk = {key: payload[key] for key in ("id", "created", "model", "provider")}
        chunks = [
            {
                **chunk,
                "object": "chat.completion.chunk",
                "choices": [
                    {"index": 0, "delta": {"tool_calls": native}, "finish_reason": "tool_calls"}
                ],
            },
            {
                **chunk,
                "object": "chat.completion.chunk",
                "choices": [],
                "usage": payload["usage"],
            },
        ]
        body = "".join("data: " + json.dumps(item) + "\n\n" for item in chunks)
        return httpx2.Response(
            200, text=body + "data: [DONE]\n\n", headers={"content-type": "text/event-stream"}
        )

    async def scenario():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as transport:
            method = complete_stream if streaming else complete
            return await method(messages, settings=settings, agent_contract=True, client=transport)

    result = asyncio.run(scenario())
    assert captured == [expected]
    assert result.outcome == PreviewCandidate(tool=UNDO_CANDIDATE_TOOL, arguments=arguments)
    assert result.usage["cost"] == 0
    assert "max_tokens" not in captured[0]


@pytest.fixture
def resolver(monkeypatch):
    conversation = SimpleNamespace(id=uuid4())
    run = SimpleNamespace(
        error_code=None,
        deadline=datetime.now(UTC) + timedelta(minutes=1),
        execution_lease={"capabilities": [UNDO_CANDIDATE_TOOL, COLLECTION_TOOL]},
    )
    latest_id, older_id = uuid4(), uuid4()
    receipts = {
        latest_id: SimpleNamespace(id=latest_id),
        older_id: SimpleNamespace(id=older_id),
    }
    latest = AsyncMock(return_value=latest_id)

    async def bound(db, auth, receipt_id):
        return receipts[receipt_id], object(), object(), conversation

    recovery = {"plan": {"undo_receipt_id": None}}
    inverse = SimpleNamespace(undo_receipt_id=None)
    bound_mock = AsyncMock(side_effect=bound)

    def recovery_mock(*args):
        return recovery

    freeze = AsyncMock(return_value=inverse)
    monkeypatch.setattr(receipt_history, "latest_receipt", latest)
    monkeypatch.setattr(receipt_history, "bound_receipt", bound_mock)
    monkeypatch.setattr(receipt_history, "recovery_for", recovery_mock)
    monkeypatch.setattr(service, "freeze_undo", freeze)
    monkeypatch.setattr(
        service, "get_settings", lambda: SimpleNamespace(mimi_collection_enabled=True)
    )
    lifecycle = {
        "historical_outcomes": [
            {"receipt_id": str(older_id), "count": 3},
            {"receipt_id": str(latest_id), "count": 7},
        ]
    }

    def resolve(target="latest", receipt_id=None, *, pending=False):
        return asyncio.run(
            service._prepare_chat_undo_candidate(
                object(),
                object(),
                conversation,
                run,
                b"synthetic-dek",
                UndoCandidate(target=target, receipt_id=receipt_id),
                lifecycle,
                pending_at_accept=pending,
            )
        )

    return SimpleNamespace(
        conversation=conversation,
        run=run,
        latest_id=latest_id,
        older_id=older_id,
        latest=latest,
        bound=bound_mock,
        recovery=recovery,
        freeze=freeze,
        inverse=inverse,
        lifecycle=lifecycle,
        resolve=resolve,
    )


def test_exact_old_three_never_uses_newest_seven(resolver):
    assert resolver.resolve("exact", resolver.older_id) is resolver.inverse
    resolver.latest.assert_not_awaited()
    assert resolver.bound.await_args.args[2] == resolver.older_id
    assert resolver.freeze.await_args.args[1] == resolver.older_id


def test_latest_uses_the_newest_even_when_older_is_selectable(resolver):
    assert resolver.resolve() is resolver.inverse
    resolver.latest.assert_awaited_once()
    assert resolver.bound.await_args.args[2] == resolver.latest_id


@pytest.mark.parametrize(
    "reason", ["undo_post_version_stale", "task_collection_source_not_eligible"]
)
def test_latest_failure_never_auto_skips_to_an_older_receipt(resolver, reason):
    resolver.freeze.side_effect = HTTPException(409, reason)
    with pytest.raises(HTTPException) as caught:
        resolver.resolve()
    assert caught.value.detail == reason
    resolver.latest.assert_awaited_once()
    resolver.bound.assert_awaited_once()
    assert resolver.bound.await_args.args[2] == resolver.latest_id
    resolver.freeze.assert_awaited_once()


@pytest.mark.parametrize("failure", ["missing", "inverse"])
def test_latest_has_no_fallback_when_absent_or_already_an_inverse(resolver, failure):
    if failure == "missing":
        resolver.latest.return_value = None
    else:
        resolver.recovery["plan"]["undo_receipt_id"] = str(resolver.older_id)
    with pytest.raises(HTTPException):
        resolver.resolve()
    resolver.freeze.assert_not_awaited()
    resolver.latest.assert_awaited_once()


def test_exact_target_requires_a_handle_supplied_in_current_model_context(resolver):
    with pytest.raises(HTTPException, match="receipt_undo_target_not_in_context"):
        resolver.resolve("exact", uuid4())
    resolver.bound.assert_not_awaited()
    resolver.freeze.assert_not_awaited()


def test_even_a_context_handle_cannot_cross_current_conversation(resolver):
    resolver.bound.return_value = (
        SimpleNamespace(id=resolver.older_id),
        object(),
        object(),
        SimpleNamespace(id=uuid4()),
    )
    resolver.bound.side_effect = None
    with pytest.raises(HTTPException, match="receipt_undo_target_not_in_context"):
        resolver.resolve("exact", resolver.older_id)
    resolver.freeze.assert_not_awaited()


@pytest.mark.parametrize("fence", ["pending", "paused", "deadline", "revoked", "unleased"])
def test_pending_or_invalid_run_cannot_materialize_an_undo(resolver, fence):
    if fence == "paused":
        resolver.run.error_code = "pause_requested"
    elif fence == "deadline":
        resolver.run.deadline = datetime.now(UTC) - timedelta(seconds=1)
    elif fence == "revoked":
        resolver.run.execution_lease["revoked_at"] = "synthetic"
    elif fence == "unleased":
        resolver.run.execution_lease["capabilities"] = [COLLECTION_TOOL]
    with pytest.raises(HTTPException):
        resolver.resolve(pending=fence == "pending")
    resolver.latest.assert_not_awaited()
    resolver.bound.assert_not_awaited()
    resolver.freeze.assert_not_awaited()


@pytest.mark.parametrize("text", ["Hoàn tác", "Undo last change", "Hãy trả nhóm trước", "Xin chào"])
def test_undo_text_obeys_the_same_admission_context_guard(monkeypatch, text):
    from app.agent import voice_store

    conversation = SimpleNamespace(id=uuid4(), generation=2, route_config={}, dek_wrapped="fixture")
    settings = _settings(
        mimi_context_v1_enabled=True, mimi_route_model="deepseek/deepseek-v4.1-flash-1017"
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    )
    monkeypatch.setattr(service, "_conversation", AsyncMock(return_value=conversation))
    monkeypatch.setattr(voice_store, "guard_voice_for_text", AsyncMock())
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "read_policy", AsyncMock())
    monkeypatch.setattr(service, "bind_policy", lambda s, p: s)
    monkeypatch.setattr(service, "bind_configuration", lambda s, c: s)
    monkeypatch.setattr(service.mimi_crypto, "unwrap_dek", lambda wrapped: b"synthetic")
    monkeypatch.setattr(service, "_load_active_checkpoint", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(
        service,
        "_context_prompt_observation",
        AsyncMock(return_value={"compaction_blocked": True}),
    )
    with pytest.raises(HTTPException, match="mimi_compaction_required_unactivated"):
        asyncio.run(
            service.ensure_message_admissible(
                db,
                object(),
                conversation.id,
                service.MessageCreate(content=text, client_id="admission", expected_generation=2),
            )
        )


def test_deterministic_local_undo_stays_a_labelled_fixture_response():
    kind, text = service._deterministic_turn("Hoàn tác", uuid4(), awaiting_task_title=False)
    assert kind == "text" and "route local" in text


def test_chat_only_undo_never_expands_voice_registry_or_voice_policy():
    from app.agent.voice_v2_protocol import setup_v2

    settings = Settings(
        _env_file=None, mimi_collection_enabled=True, mimi_calendar_read_enabled=True
    )
    default_names = {t["function"]["name"] for t in tools_for_settings(settings)}
    assert UNDO_CANDIDATE_TOOL not in default_names
    setup = setup_v2(datetime.now(UTC), settings)["setup"]
    assert "task_undo_candidate_v1" not in {
        item["name"] for item in setup["tools"][0]["functionDeclarations"]
    }
    assert "Undo in this Chat" not in setup["systemInstruction"]["parts"][0]["text"]
