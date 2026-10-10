"""Loopback-only real app with finite synthetic transport for Task086 Chrome QA.

Provider mocks exercise lifecycle, never conversation quality. No credential load.
"""

from __future__ import annotations

import base64
import json
import os

from sqlalchemy.engine import make_url

raw = os.environ.pop("MIMI086_QA_DATABASE_URL", None)
if not raw:
    raise RuntimeError("MIMI086_QA_DATABASE_URL required")
url = make_url(raw)
if (url.host, url.port, url.database, url.username) not in {
    ("127.0.0.1", 21886, "microsched_mimi086", "microsched_app"),
    ("127.0.0.1", 21886, "microsched_mimi086_ci2", "microsched_app"),
    ("127.0.0.1", 21887, "mimi086_qa", "microsched_app"),
}:
    raise RuntimeError("Task086 browser QA refuses undeclared/nonlocal DB")
for key in tuple(os.environ):
    if (
        key.startswith(("MIMI_", "NEON_"))
        or key.endswith(("_API_KEY", "_TOKEN", "_SECRET"))
        or key
        in {
            "DATABASE_URL",
            "ENCRYPTION_MASTER_KEY",
            "VAPID_PRIVATE_KEY",
            "VAPID_CLAIMS_SUB",
            "GOOGLE_CLIENT_ID",
        }
    ):
        os.environ.pop(key, None)
os.environ.update(
    {
        "MIMI_P0_DISABLE_DOTENV": "1",
        "APP_ENV": "local",
        "DATABASE_URL": raw,
        "OAUTH_STATE_SECRET": "synthetic-mimi086-browser-only",
        "ENCRYPTION_MASTER_KEY": base64.urlsafe_b64encode(b"QA86" * 8).decode(),
        "ALLOWED_EMAILS": "owner@test.local",
        "SESSION_COOKIE_SECURE": "false",
        "ENABLE_INPROCESS_CRON": "false",
        "MIMI_REAL_CHAT_ENABLED": "true",
        "MIMI_LIVE_PROVIDER_ENABLED": "true",
        "MIMI_CONTEXT_V1_ENABLED": "true",
        "MIMI_COLLECTION_ENABLED": "true",
        "MIMI_NOTIFICATIONS_ENABLED": "true",
        "MIMI_STANDARD_API_KEY": "synthetic-never-sent",
        "MIMI_ROUTE_MODE": "exact",
        "MIMI_ROUTE_MODEL": "deepseek/deepseek-v4.1-flash",
        "MIMI_ROUTE_PROVIDER": "deepinfra",
        "MIMI_ROUTE_QUANTIZATION": "fp8",
        "MIMI_ROUTE_MAX_INPUT_PRICE": "0.2",
        "MIMI_ROUTE_MAX_OUTPUT_PRICE": "0.6",
        "MIMI_RUN_DEADLINE_SECONDS": "90",
    }
)
from fastapi import Request  # noqa: E402
from starlette.responses import PlainTextResponse  # noqa: E402

from app.agent import service  # noqa: E402
from app.agent.context import (  # noqa: E402
    AssistantText,
    PreviewCandidate,
    ToolRequest,
    ToolRequests,
)
from app.agent.openrouter import AgentCompletion, RouteContractError  # noqa: E402
from app.main import create_app  # noqa: E402
from scripts.mimi_collection_fixtures import manifest  # noqa: E402

FIXTURE = manifest()


async def fake_completion(messages, **kwargs):
    prompt = next(
        (
            m.get("content", "")
            for m in reversed(messages)
            if m.get("role") == "user"
            and isinstance(m.get("content"), str)
            and m["content"].startswith("QA086:")
        ),
        "",
    )
    if not prompt:
        raise RouteContractError("synthetic086_undeclared_prompt")
    mode = prompt.split(":", 1)[1].strip()
    response = "synthetic086-" + str(len(messages))
    if mode in {"greeting", "answer"}:
        outcome = AssistantText(
            text="Chào bạn! Mình có thể cùng bạn xem và chuẩn bị thay đổi Task."
        )
    elif mode in {"fields", "reminder-relative", "reminder-absolute", "reminder-change-due"}:
        from datetime import UTC, datetime, timedelta

        tid = FIXTURE["groups"]["bulk50"]["tasks"][1]["id"]
        last = messages[-1]
        result = json.loads(last["content"]) if last.get("role") == "tool" else None
        if result and "selection" in result:
            selection = result["selection"]
            member = next(m for m in selection["members"] if m["id"] == tid)
            due = (datetime.now(UTC) + timedelta(days=2)).isoformat()
            entry = {
                "action": "edit",
                "id": tid,
                "expected_collection_version": member["collection_version"],
            }
            if mode == "fields":
                child = FIXTURE["groups"]["bulk50"]["tasks"][1]["items"][0]["id"]
                entry.update(
                    fields={
                        "title": "Task đầy đủ tổng hợp",
                        "body_md": "Đủ nội dung 🏃 " * 300,
                        "status": "open",
                        "priority": "p2",
                        "pinned": True,
                        "due_precision": "datetime",
                        "due_on": None,
                        "due_at": due,
                    },
                    children=[
                        {
                            "action": "patch",
                            "id": child,
                            "fields": {"content": "Checklist đã sửa đủ", "is_completed": True},
                        },
                        {"action": "append", "fields": {"content": "Checklist mới"}},
                    ],
                )
            else:
                entry["fields"] = {"due_precision": "datetime", "due_on": None, "due_at": due}
                if mode != "reminder-change-due":
                    entry["reminder"] = {
                        "action": "configure",
                        "configuration": {"mode": "relative", "offset_minutes": -30}
                        if mode == "reminder-relative"
                        else {"mode": "absolute", "due_at": due},
                    }
            outcome = PreviewCandidate(
                tool="task.collection_candidate.v1",
                arguments={"selection_id": selection["selection_id"], "entries": [entry]},
            )
        elif result:
            outcome = ToolRequests(
                requests=(
                    ToolRequest(
                        call_id=response,
                        name="task.freeze_selection.v1",
                        arguments={
                            "intent": "Chỉnh đúng Task tổng hợp theo ID",
                            "variants_considered": [tid],
                            "explicitly_named_subset": True,
                            "members": [
                                {
                                    "id": tid,
                                    "classification": "included",
                                    "reason": "Exact named synthetic subset",
                                }
                            ],
                        },
                    ),
                )
            )
        else:
            outcome = ToolRequests(
                requests=(
                    ToolRequest(
                        call_id=response, name="task.read_content.v1", arguments={"id": tid}
                    ),
                )
            )
    elif mode.startswith("collection "):
        group = mode.split(" ", 1)[1]
        if group not in FIXTURE["groups"]:
            raise RouteContractError("synthetic086_unknown_group")
        ids = {t["id"] for t in FIXTURE["groups"][group]["tasks"]}
        last = messages[-1]
        result = json.loads(last["content"]) if last.get("role") == "tool" else None
        if result and "selection" in result:
            selection = result["selection"]
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
                        if m["classification"] == "included"
                    ],
                },
            )
        elif result and result.get("next_cursor"):
            outcome = ToolRequests(
                requests=(
                    ToolRequest(
                        call_id=response,
                        name="task.query.v1",
                        arguments={
                            "filter": {} if group == "training49" else {"title_contains": group},
                            "projection": ["id", "title"],
                            "limit": 50,
                            "cursor": result["next_cursor"],
                        },
                    ),
                )
            )
        elif result:
            observed = {}
            for message in messages:
                if message.get("role") == "tool":
                    body = json.loads(message["content"])
                    observed.update({r["id"]: r for r in body.get("rows", [])})
            if not ids <= set(observed):
                raise RouteContractError("synthetic086_fixture_missing_query_rows")
            outcome = ToolRequests(
                requests=(
                    ToolRequest(
                        call_id=response,
                        name="task.freeze_selection.v1",
                        arguments={
                            "intent": "Đổi độ ưu tiên của nhóm tổng hợp " + group,
                            "variants_considered": [
                                "tập luyện",
                                "the duc",
                                "luyện tập",
                                "tap luyen",
                            ]
                            if group == "training49"
                            else [group],
                            "members": [
                                {
                                    "id": t["id"],
                                    "classification": t["classification"],
                                    "reason": t["classification_reason"],
                                }
                                for t in FIXTURE["groups"][group]["tasks"]
                            ]
                            + [
                                {
                                    "id": tid,
                                    "classification": "excluded",
                                    "reason": "Outside the explicit synthetic group",
                                }
                                for tid in observed
                                if tid not in ids
                            ],
                        },
                    ),
                )
            )
        else:
            outcome = ToolRequests(
                requests=(
                    ToolRequest(
                        call_id=response,
                        name="task.query.v1",
                        arguments={
                            "filter": {} if group == "training49" else {"title_contains": group},
                            "projection": ["id", "title"],
                            "limit": 50,
                        },
                    ),
                )
            )
    else:
        raise RouteContractError("synthetic086_undeclared_mode")
    return AgentCompletion(
        outcome=outcome,
        response_id=response,
        usage={"cost": 0},
        provider="Synthetic",
        model="deepseek/deepseek-v4.1-flash",
    )


async def fake_stream(messages, **kwargs):
    on_event = kwargs.pop("on_event")
    await on_event("provider.connected", {"status": 200})
    result = await fake_completion(messages, **kwargs)
    await on_event("provider.response_identity", {"response_id": result.response_id})
    return result


service.openrouter_complete = fake_completion
service.openrouter_complete_stream = fake_stream
app = create_app()


@app.middleware("http")
async def loopback_only(request: Request, call_next):
    if (
        request.client is None
        or request.client.host not in {"127.0.0.1", "::1"}
        or request.url.hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        return PlainTextResponse("Task086 QA is loopback-only", status_code=403)
    return await call_next(request)


def main():
    import uvicorn

    port = int(os.environ.get("MIMI086_QA_PORT", "18886"))
    if port not in {18886, 18887}:
        raise RuntimeError("undeclared QA API port")
    uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=port, loop="app.core.qa_event_loop:selector_loop_factory"
        )
    ).run()


if __name__ == "__main__":
    main()
