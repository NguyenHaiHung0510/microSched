"""Disposable P1C-A browser-QA app with a deterministic in-process provider.

Run only against a local database named microsched_p1ca*. This module replaces
the provider transport before app startup; it never imports a buyer credential.
It is not a production entry point.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from starlette.responses import PlainTextResponse
from starlette.routing import Mount


def _configure_synthetic_process() -> str:
    raw_url = os.environ.pop("MIMI_QA_DATABASE_URL", None)
    if not raw_url:
        raise RuntimeError("MIMI_QA_DATABASE_URL is required for isolated browser QA")
    parsed = make_url(raw_url)
    if (
        parsed.host not in {"127.0.0.1", "localhost"}
        or parsed.port is None
        or not parsed.database
        or not parsed.database.startswith("microsched_p1ca")
        or parsed.username != "microsched_app"
    ):
        raise RuntimeError("browser QA refuses a non-disposable database URL")
    # The fake lane must not even inherit a live Mimi/OpenRouter/Google key.
    for key in tuple(os.environ):
        if (
            key.startswith(("MIMI_", "NEON_"))
            or key.endswith(("_API_KEY", "_TOKEN", "_SECRET"))
            or key in {"GOOGLE_CLIENT_ID", "DATABASE_URL"}
        ):
            os.environ.pop(key, None)
    os.environ.update(
        {
            "MIMI_P0_DISABLE_DOTENV": "1",
            "APP_ENV": "local",
            "DATABASE_URL": raw_url,
            "ALLOWED_EMAILS": "owner@test.local",
            "OAUTH_STATE_SECRET": "synthetic-mimi-p1ca-browser-qa-only",
            "ENCRYPTION_MASTER_KEY": base64.urlsafe_b64encode(b"P1CA" * 8).decode(),
            "ENABLE_INPROCESS_CRON": "false",
            "MIMI_REAL_CHAT_ENABLED": "true",
            "MIMI_LIVE_PROVIDER_ENABLED": "true",
            "MIMI_CONTEXT_V1_ENABLED": "true",
            "MIMI_RUN_DEADLINE_SECONDS": "30",
            "MIMI_STANDARD_API_KEY": "synthetic-never-sent",
            "MIMI_ROUTE_MODEL": "synthetic/p1ca-browser",
            "MIMI_ROUTE_PROVIDER": "Synthetic",
            "MIMI_ROUTE_QUANTIZATION": "fp16",
            "MIMI_ROUTE_MAX_INPUT_PRICE": "1",
            "MIMI_ROUTE_MAX_OUTPUT_PRICE": "1",
        }
    )
    return parsed.database


QA_DATABASE = _configure_synthetic_process()

from app.agent import service as mimi_service  # noqa: E402
from app.agent.context import (  # noqa: E402
    AssistantText,
    Clarification,
    Draft,
    PreviewCandidate,
    ToolRequest,
    ToolRequests,
)
from app.agent.models import (  # noqa: E402
    MimiChangeSet,
    MimiConversation,
    MimiExecutionReceipt,
    MimiProviderCall,
    MimiRun,
)
from app.agent.openrouter import AgentCompletion, ProviderDispatchError  # noqa: E402
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL  # noqa: E402
from app.core.db import get_sessionmaker  # noqa: E402
from app.domain.models import Task  # noqa: E402
from app.main import create_app  # noqa: E402

_transport_calls = 0
_slow_gate = asyncio.Event()
_slow_waiting = False
_retry_attempts: dict[str, int] = {}


class QaCleanup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID
    task_id: UUID


def _current_qa_prompt(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        content = message.get("content")
        if (
            message.get("role") == "user"
            and isinstance(content, str)
            and content.startswith("QA_P1CA_")
        ):
            return content
    raise RuntimeError("browser QA provider received an undeclared prompt")


async def _fake_complete(
    messages: list[dict[str, Any]],
    *,
    settings: Any,
    session_id: str,
    force_task_tool: bool,
    agent_contract: bool,
    on_event: Any = None,
) -> AgentCompletion:
    if settings.mimi_standard_api_key != "synthetic-never-sent":
        raise RuntimeError("browser QA fake transport refuses a buyer credential")
    if not agent_contract:
        raise RuntimeError("browser QA requires the P1C-A context contract")
    global _transport_calls, _slow_waiting
    _transport_calls += 1
    prompt = _current_qa_prompt(messages)
    if on_event is not None:
        await on_event("provider.connected", {"qa_fake": True})
    if prompt.startswith("QA_P1CA_UNKNOWN"):
        response_id = f"qa-unknown-generation-{_transport_calls}"
        if on_event is not None:
            await on_event("provider.response_identity", {"response_id": response_id})
        raise ProviderDispatchError("unknown", 503, response_id=response_id)
    if prompt.startswith("QA_P1CA_RETRYABLE"):
        retry_key = f"{session_id}:{prompt}"
        _retry_attempts[retry_key] = _retry_attempts.get(retry_key, 0) + 1
        if _retry_attempts[retry_key] == 1:
            raise ProviderDispatchError("retryable", 429)
        outcome = AssistantText(text="Mimi đã tiếp tục sau lỗi chưa gửi generation.")
        return AgentCompletion(
            outcome=outcome,
            response_id=f"qa-generation-{_transport_calls}",
            usage={"prompt_tokens": 12, "completion_tokens": 8},
            provider="Synthetic",
            model="synthetic/p1ca-browser",
        )
    if prompt.startswith("QA_P1CA_READONLY"):
        outcome = AssistantText(text="Mimi có thể trả lời câu hỏi này mà không tạo Task.")
    elif prompt.startswith("QA_P1CA_CLARIFY"):
        outcome = Clarification(question="Bạn muốn chọn ngày nào cho lịch này?")
    elif prompt.startswith("QA_P1CA_DRAFT"):
        outcome = Draft(text="Mình đề xuất rà soát lịch trước, sau đó tạo từng preview cần thiết.")
    elif prompt.startswith(("QA_P1CA_SLOW", "QA_P1CA_DEADLINE")):
        _slow_gate.clear()
        _slow_waiting = True
        try:
            await _slow_gate.wait()
        finally:
            _slow_waiting = False
        outcome = AssistantText(text="Run vẫn tiếp tục sau khi đóng hoặc tải lại giao diện.")
    elif prompt.startswith("QA_P1CA_READ"):
        if not any(
            str(message.get("content", "")).startswith("KẾT QUẢ CÔNG CỤ ĐỌC")
            for message in messages
        ):
            outcome = ToolRequests(
                requests=(
                    ToolRequest(
                        call_id="qa-read-tasks",
                        name="task.query.v1",
                        arguments={
                            "filter": {
                                "status": None,
                                "priority": None,
                                "due_from": None,
                                "due_through": None,
                                "title_contains": "QA_P1CA",
                            },
                            "projection": ["id", "title", "status"],
                            "sort": "updated_desc",
                            "limit": 10,
                            "cursor": None,
                        },
                    ),
                )
            )
        else:
            outcome = AssistantText(text="Mình đã đọc Task STANDARD được cấp trong lượt này.")
    elif prompt.startswith("QA_P1CA_CREATE"):
        authority = json.loads(messages[1]["content"])["authority_envelope"]
        title = prompt.removeprefix("QA_P1CA_CREATE").strip() or "QA_P1CA synthetic Task"
        outcome = PreviewCandidate(
            tool=CREATE_CANDIDATE_TOOL,
            arguments={"id": authority["reserved_task_id"], "title": title},
        )
    else:
        raise RuntimeError("browser QA prompt is outside the frozen fixture")
    if force_task_tool and not isinstance(outcome, PreviewCandidate):
        raise RuntimeError("browser QA forced revision did not produce a preview")
    return AgentCompletion(
        outcome=outcome,
        response_id=f"qa-generation-{_transport_calls}",
        usage={"prompt_tokens": 12, "completion_tokens": 8},
        provider="Synthetic",
        model="synthetic/p1ca-browser",
    )


async def _fake_stream(messages: list[dict[str, Any]], **kwargs: Any) -> AgentCompletion:
    return await _fake_complete(messages, **kwargs)


async def _fake_generation(response_id: str) -> dict[str, Any]:
    if not response_id.startswith("qa-unknown-generation-"):
        raise RuntimeError("browser QA refuses non-synthetic generation lookup")
    return {
        "id": response_id,
        "model": "synthetic/p1ca-browser",
        "provider_name": "Synthetic",
    }


mimi_service.openrouter_complete = _fake_complete
mimi_service.openrouter_complete_stream = _fake_stream
mimi_service.openrouter_get_generation = _fake_generation
app = create_app()


@app.middleware("http")
async def qa_loopback_only(request: Request, call_next: Any) -> Any:
    """Fail closed if this test-only app is accidentally exposed off loopback."""

    client_host = request.client.host if request.client else None
    if client_host not in {"127.0.0.1", "::1"} or request.url.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        return PlainTextResponse("synthetic browser QA is loopback-only", status_code=403)
    return await call_next(request)


@app.get("/__qa/mimi-state")
async def qa_state() -> dict[str, Any]:
    factory = get_sessionmaker()
    if factory is None:
        raise HTTPException(503, "synthetic database unavailable")
    async with factory() as db:
        tasks = (
            await db.execute(
                select(func.count()).select_from(Task).where(Task.title.like("QA_P1CA%"))
            )
        ).scalar_one()
        previews = (await db.execute(select(func.count()).select_from(MimiChangeSet))).scalar_one()
        receipts = (
            await db.execute(select(func.count()).select_from(MimiExecutionReceipt))
        ).scalar_one()
        calls = (await db.execute(select(func.count()).select_from(MimiProviderCall))).scalar_one()
    return {
        "database": QA_DATABASE,
        "synthetic_tasks": tasks,
        "change_sets": previews,
        "receipts": receipts,
        "provider_calls": calls,
        "transport_calls": _transport_calls,
        "slow_waiting": _slow_waiting,
    }


@app.post("/__qa/release-slow")
async def qa_release_slow() -> dict[str, bool]:
    if not _slow_waiting:
        raise HTTPException(409, "no synthetic slow run is waiting")
    _slow_gate.set()
    return {"released": True}


@app.post("/__qa/cleanup")
async def qa_cleanup(payload: QaCleanup) -> dict[str, int]:
    """Delete only the exact synthetic Task and its test-created conversation."""

    factory = get_sessionmaker()
    if factory is None:
        raise HTTPException(503, "synthetic database unavailable")
    async with factory() as db:
        conversation = await db.get(MimiConversation, payload.conversation_id)
        task = await db.get(Task, payload.task_id)
        if (
            conversation is None
            or task is None
            or not task.title.startswith("QA_P1CA synthetic Task ")
        ):
            raise HTTPException(409, "exact synthetic cleanup target missing")
        linked_receipt = (
            await db.execute(
                select(MimiExecutionReceipt.id)
                .join(MimiChangeSet, MimiExecutionReceipt.change_set_id == MimiChangeSet.id)
                .join(MimiRun, MimiChangeSet.run_id == MimiRun.id)
                .where(
                    MimiExecutionReceipt.task_id == payload.task_id,
                    MimiRun.conversation_id == payload.conversation_id,
                )
            )
        ).scalar_one_or_none()
        if linked_receipt is None:
            raise HTTPException(409, "synthetic Task is not a receipt of this conversation")
        await db.delete(conversation)
        await db.flush()
        await db.delete(task)
        await db.commit()
    return {"conversations_deleted": 1, "tasks_deleted": 1}


# create_app mounts its built SPA last. Move every test-only route ahead of
# that catch-all mount or the SPA would swallow it.
_qa_routes = [
    route
    for route in app.router.routes
    if isinstance(route, APIRoute) and route.path.startswith("/__qa/")
]
app.router.routes[:] = [route for route in app.router.routes if route not in _qa_routes]
_spa_index = next(
    index
    for index, route in enumerate(app.router.routes)
    if isinstance(route, Mount) and route.path == ""
)
app.router.routes[_spa_index:_spa_index] = _qa_routes
