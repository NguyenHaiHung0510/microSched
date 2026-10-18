"""Durable intent is not a paid dispatch; actual unknown wires remain unknown."""

import asyncio
from uuid import uuid7

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import auth, local_contract  # noqa: F401

from app.agent import config_policy, local_budget, service
from app.agent.context import ToolRequest, ToolRequests
from app.agent.models import MimiConversation, MimiProviderCall
from app.agent.openrouter import AgentCompletion, ProviderDispatchError, RouteContractError
from app.core.database_urls import async_postgres_url
from app.core.qa_event_loop import selector_loop_factory
from app.core.settings import get_settings
from app.domain.models import AppSetting

pytestmark = pytest.mark.pg


@pytest.mark.parametrize(
    "mode", ["langgraph_guard", "reservation", "read_reservation", "unknown", "failed_wire"]
)
def test_paid_statistics_follow_transport_handoff_not_dispatched_state(pg_dsn, monkeypatch, mode):
    for key, value in {
        "MIMI_LIVE_PROVIDER_ENABLED": "1",
        "MIMI_CONTEXT_V1_ENABLED": "1",
        "MIMI_STANDARD_API_KEY": "synthetic-never-sent",
        "MIMI_ROUTE_MODE": "native",
        "MIMI_ROUTE_MODEL": "deepseek/deepseek-v4.1-flash-1017",
        "MIMI_ROUTE_MAX_INPUT_PRICE": ".2",
        "MIMI_ROUTE_MAX_OUTPUT_PRICE": ".6",
        "MIMI_RUNNER": "langgraph" if mode == "langgraph_guard" else "current",
        # Deliberately unapproved tuple; no connection to this name is ever permitted.
        "DATABASE_URL": "postgresql://synthetic:synthetic@127.0.0.1:21887/mimi234_guard_only",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("MIMI_LOCAL_BUDGET_LEDGER", raising=False)
    policy_key = "mimi.owner234." + uuid7().hex
    monkeypatch.setattr(config_policy, "POLICY_KEY", policy_key)
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        actor, cid = auth(), None
        transports, reservations = [], []

        def reserve(*args, **kwargs):
            reservations.append(1)
            if mode == "reservation" or mode == "read_reservation" and len(reservations) == 2:
                raise RouteContractError("synthetic_reservation_refused")
            return None

        async def transport(*args, **kwargs):
            transports.append(1)
            if mode in {"unknown", "failed_wire"}:
                raise ProviderDispatchError("unknown" if mode == "unknown" else "failed", None)
            assert mode == "read_reservation" and len(transports) == 1
            return AgentCompletion(
                outcome=ToolRequests(
                    requests=(
                        ToolRequest(call_id="read", name="task.query.v1", arguments={"limit": 1}),
                    )
                ),
                response_id="synthetic-observed-read",
                usage={"prompt_tokens": 8, "cost": 0.001},
                provider="Synthetic",
                model="deepseek/deepseek-v4.1-flash-1017",
            )

        monkeypatch.setattr(local_budget, "reserve", reserve)
        monkeypatch.setattr(service, "openrouter_complete", transport)
        if mode == "langgraph_guard":
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            def forbidden_connection(*args, **kwargs):
                pytest.fail("unauthorized LangGraph tuple must refuse before any DB connection")

            monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", forbidden_connection)
        try:
            async with maker() as db:
                view = await service.create_conversation(db, actor, service.ConversationCreate())
                cid = view["id"]
                await db.commit()
                view = await service.send_message(
                    db, actor, cid, service.MessageCreate(client_id="owner234", content="Xin chào")
                )
                await db.commit()
            async with maker() as db:
                view = await service.conversation_view(db, actor, cid)
                run = view["runs"][-1]
                calls = (
                    await db.scalars(
                        select(MimiProviderCall).where(MimiProviderCall.run_id == run["id"])
                    )
                ).all()
                stats = view["run_observations"][str(run["id"])]
                expected_paid = int(mode in {"read_reservation", "unknown", "failed_wire"})
                assert len(transports) == expected_paid
                assert len(reservations) == (
                    0 if mode == "langgraph_guard" else 2 if mode == "read_reservation" else 1
                )
                assert stats["main_calls"] == expected_paid
                assert stats["helper_calls"] == stats["reused_calls"] == 0
                assert stats["unknown_cost_calls"] == int(mode in {"unknown", "failed_wire"})
                assert stats["known_cost_usd"] == (0.001 if mode == "read_reservation" else 0)
                if mode in {"langgraph_guard", "reservation", "read_reservation"}:
                    refused = max(calls, key=lambda row: row.attempt)
                    assert refused.state == "failed" and refused.usage is None
                    assert refused.route["dispatch_not_started"] is True
                    visible = next(row for row in view["provider_calls"] if row["id"] == refused.id)
                    assert visible["dispatch_not_started"] is True
                    assert visible["paid_dispatch"] is False and visible["usage"] == {}
                    if mode == "langgraph_guard":
                        assert (
                            run["error_code"]
                            == "provider_contract_mimi_langgraph_requires_authorized_app_database"
                        )
                else:
                    assert calls[0].route.get("dispatch_not_started") is not True
                if mode == "unknown":
                    assert run["state"] == "outcome_unknown"
                    with pytest.raises(HTTPException, match="reconciliation_required"):
                        await service.prepare_run_resume(db, actor, run["id"])
                    assert len(transports) == 1
        finally:
            async with maker() as db:
                if cid is not None:
                    await db.execute(delete(MimiConversation).where(MimiConversation.id == cid))
                await db.execute(delete(AppSetting).where(AppSetting.key == policy_key))
                await db.commit()
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)
