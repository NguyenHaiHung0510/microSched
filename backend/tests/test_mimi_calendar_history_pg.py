"""Calendar prose never becomes historical provider evidence; original UI chat remains."""

import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import uuid7

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import auth, local_contract  # noqa: F401
from test_mimi_p3_working_pg import observed_trigger

from app.agent import config_policy, crypto, service
from app.agent.compaction import (
    CALENDAR_HISTORY_MARKER,
    CheckpointSource,
    make_checkpoint,
    validate_checkpoint,
)
from app.agent.context import AssistantText
from app.agent.models import MimiConversation, MimiEvent, MimiMessage, MimiRun
from app.agent.openrouter import AgentCompletion
from app.agent.tools.calendar_reads import (
    CALENDAR_INSPECT_TOOL,
    CALENDAR_READ_TOOL,
    execute_calendar_tool,
)
from app.agent.working_context import load_history
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AppSetting, CalendarEvent, CalendarSource, DayAnnotation

pytestmark = pytest.mark.pg


@pytest.mark.parametrize("scenario_name", ["read_hidden", "inspect_edited", "empty_read"])
@pytest.mark.parametrize("enabled", [True, False], ids=["flag_on", "flag_off"])
@pytest.mark.parametrize("mode", ["suffix", "deterministic", "semantic", "legacy"])
def test_calendar_prose_egress_and_checkpoint_integrity(
    pg_dsn, monkeypatch, scenario_name, enabled, mode
):
    monkeypatch.delenv("MIMI_LOCAL_BUDGET_LEDGER", raising=False)
    for key, value in {
        "MIMI_CONTEXT_V1_ENABLED": "1",
        "MIMI_LIVE_PROVIDER_ENABLED": "1",
        "MIMI_STANDARD_API_KEY": "synthetic-never-sent",
        "MIMI_ROUTE_MODEL": "deepseek/deepseek-v4.1-flash-1017",
        "MIMI_ROUTE_REASONING_EFFORT": "none",
        "MIMI_ROUTE_MODE": "native",
        "MIMI_ROUTE_MAX_INPUT_PRICE": "0.36",
        "MIMI_ROUTE_MAX_OUTPUT_PRICE": "1.44",
        "MIMI_CALENDAR_READ_ENABLED": "1",
        "MIMI_NOTIFICATIONS_ENABLED": "0",
    }.items():
        monkeypatch.setenv(key, value)
    policy_key = f"mimi.calendar.history.{uuid7()}"
    monkeypatch.setattr(config_policy, "POLICY_KEY", policy_key)
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        cid, source_id, event_id = None, uuid7(), uuid7()
        marker_id, helper_calls = uuid7(), []
        old = "Synthetic OLD-CALENDAR-PROSE: hidden meeting detail; the day was empty."
        general_user = "General user preference: concise explanations."
        general_assistant = "General assistant explanation retained."
        day = date(2093, 5, 6)

        async def helper(messages, **kwargs):
            assert kwargs["summary_mode"] is True
            wire = json.dumps(messages)
            assert old not in wire
            assert CALENDAR_HISTORY_MARKER in wire
            assert general_user in wire and general_assistant in wire
            helper_calls.append(messages)
            return AgentCompletion(
                outcome=AssistantText(
                    text=json.dumps(
                        {
                            "summary": "General preference retained; Calendar needs a fresh read.",
                            "constraints": [],
                            "supersessions": [],
                            "resolutions": [],
                        }
                    )
                ),
                usage={"cost": 0},
                response_id="synthetic-history-summary",
                model=kwargs["settings"].mimi_route_model,
                provider="Synthetic",
            )

        monkeypatch.setattr(service, "openrouter_complete", helper)
        try:
            async with maker() as db:
                actor = auth()
                cid = (await service.create_conversation(db, actor, service.ConversationCreate()))[
                    "id"
                ]
                conv = await db.get(MimiConversation, cid)
                dek = crypto.unwrap_dek(conv.dek_wrapped)
                runs = [
                    MimiRun(
                        id=uuid7(),
                        conversation_id=cid,
                        generation=i,
                        state="completed" if i < 4 else "building",
                        deadline=datetime.now(UTC) + timedelta(minutes=5),
                    )
                    for i in range(1, 5)
                ]
                db.add_all(runs)
                db.add(CalendarSource(id=source_id, name=f"Synthetic {source_id}", kind="ics"))
                await db.flush()
                event = CalendarEvent(
                    id=event_id,
                    source_id=source_id,
                    title="Original synthetic title",
                    description_md="Original synthetic inspect detail",
                    starts_at=datetime(2093, 5, 6, 1, tzinfo=UTC),
                    ends_at=datetime(2093, 5, 6, 2, tzinfo=UTC),
                )
                db.add(event)
                await db.flush()
                tool = (
                    CALENDAR_INSPECT_TOOL
                    if scenario_name == "inspect_edited"
                    else CALENDAR_READ_TOOL
                )
                args = (
                    {"kind": "event", "id": str(event_id)}
                    if tool == CALENDAR_INSPECT_TOOL
                    else {
                        "date": str(day),
                        "kinds": ["annotation"] if scenario_name == "empty_read" else ["event"],
                    }
                )
                result = await execute_calendar_tool(db, tool, args, settings=get_settings())
                assert len(result["rows"]) == (0 if scenario_name == "empty_read" else 1)
                # Provenance uses this allowlisted metadata, not a decrypted receipt.
                db.add(
                    MimiEvent(
                        run_id=runs[1].id,
                        sequence=1,
                        kind="tool.read_result",
                        payload={"tool": tool, "body_ciphertext": "intentionally-not-decryptable"},
                    )
                )
                # A similarly named, nonallowlisted tool must not taint general history.
                db.add(
                    MimiEvent(
                        run_id=runs[0].id,
                        sequence=1,
                        kind="tool.read_result",
                        payload={
                            "tool": "calendar.untrusted",
                            "body_ciphertext": "not-decryptable",
                        },
                    )
                )
                texts = [
                    ("user", general_user, runs[0]),
                    ("assistant", general_assistant, runs[0]),
                    ("user", "Read the saved Calendar.", runs[1]),
                    ("assistant", old, runs[1]),
                ]
                if mode in {"deterministic", "semantic"}:
                    texts += [("user", f"General suffix {i}", runs[2]) for i in range(12)]
                elif mode == "legacy":
                    texts.append(("user", "General legacy suffix retained in UI.", runs[2]))
                rows = []
                for sequence, (role, text, run) in enumerate(texts, 1):
                    row = MimiMessage(
                        id=uuid7(),
                        conversation_id=cid,
                        run_id=run.id,
                        role=role,
                        sequence=sequence,
                        content_ciphertext=crypto.seal_content(
                            dek, text, aad=crypto.message_aad(cid, sequence, role)
                        ),
                        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                        content_bytes=len(text.encode()),
                    )
                    rows.append(row)
                db.add_all(rows)
                conv.next_message_sequence = len(rows) + 1
                conv.generation = 4
                await db.flush()
                if scenario_name == "read_hidden":
                    source = await db.get(CalendarSource, source_id)
                    source.is_visible = False
                elif scenario_name == "inspect_edited":
                    event.description_md = "Edited synthetic inspect detail"
                else:
                    db.add(
                        DayAnnotation(
                            id=marker_id, starts_on=day, ends_on=day, label="Newly present"
                        )
                    )
                monkeypatch.setenv("MIMI_CALENDAR_READ_ENABLED", "1" if enabled else "0")
                get_settings.cache_clear()
                settings = get_settings()
                # Both direct and shared working projection must independently redact.
                await db.flush()
                original_ui = [service._message_read(row, dek) for row in rows]
                direct = await service._provider_history(db, conv, dek)
                assert old not in json.dumps(direct)
                assert general_user in json.dumps(direct) and general_assistant in json.dumps(
                    direct
                )
                for projection_enabled in (True, False):
                    working = await load_history(
                        db,
                        conv,
                        dek,
                        rows,
                        settings.model_copy(
                            update={"mimi_working_projection_enabled": projection_enabled}
                        ),
                    )
                    projected = working.messages(
                        rows, [{"role": m["role"], "content": m["content"]} for m in original_ui]
                    )
                    assert old not in json.dumps(projected)
                    assert CALENDAR_HISTORY_MARKER in json.dumps(projected)
                    assert working.source(4) is None
                    assert "calendar_history_requires_fresh_read" in working.metadata(0)["gaps"]
                    assert general_assistant in json.dumps(projected)
                sources = [
                    CheckpointSource(
                        id=row.id,
                        sequence=row.sequence,
                        role=row.role,
                        content_sha256=row.content_sha256,
                        content=texts[i][1],
                        calendar_derived=row.sequence == 4,
                    )
                    for i, row in enumerate(rows)
                ]
                if mode == "legacy":
                    ancestor = make_checkpoint(
                        sources=[replace(s, calendar_derived=False) for s in sources[:4]],
                        prior=None,
                        policy_sha256="b" * 64,  # Pre-guard policy may be unsupported now.
                        pending_preview=None,
                        pending_draft=None,
                    )
                    del ancestor["calendar_history_policy"]
                    legacy = make_checkpoint(
                        sources=sources[4:],
                        prior=ancestor,
                        policy_sha256="b" * 64,
                        pending_preview=None,
                        pending_draft=None,
                    )
                    del legacy["calendar_history_policy"]  # An authentic pre-guard shape.
                    assert all(ref["id"] != str(rows[3].id) for ref in legacy["source_refs"])
                    assert legacy["prior_checkpoint_sha256"] == service._canonical_digest(ancestor)
                    assert old in json.dumps(legacy)
                    seq = await service._append_event(
                        db, runs[1].id, "context.checkpoint.activated", {}
                    )
                    cp_event = await db.scalar(
                        select(MimiEvent).where(
                            MimiEvent.run_id == runs[1].id, MimiEvent.sequence == seq
                        )
                    )
                    cp_event.payload = {
                        "frontier": legacy["frontier"],
                        "content_sha256": service._canonical_digest(legacy),
                        "content_ciphertext": crypto.seal_content(
                            dek,
                            json.dumps(legacy),
                            aad=crypto.event_content_aad(runs[1].id, seq, cp_event.kind),
                        ),
                    }
                    conv.context_frontier_sequence = legacy["frontier"]
                    await db.commit()
                    with pytest.raises(HTTPException) as caught:
                        await service._load_active_checkpoint(db, conv, dek)
                    assert "requires_new_conversation" in caught.value.detail
                    assert "cuộc trò chuyện mới" in caught.value.detail
                    assert service._canonical_digest(legacy) == cp_event.payload["content_sha256"]
                    assert conv.context_frontier_sequence == 5
                    assert helper_calls == []
                else:
                    if mode == "semantic":
                        await db.commit()
                        await observed_trigger(db, conv, runs[-1].id, settings)
                    elif mode == "deterministic":
                        settings = settings.model_copy(
                            update={"mimi_route_model": "synthetic/offline"}
                        )
                    suffix, _, checkpoint, checkpoint_id = await service._prepare_context_history(
                        db,
                        conv,
                        dek,
                        runs[-1].id,
                        conv.next_message_sequence,
                        None,
                        None,
                        settings=settings,
                    )
                    assert old not in json.dumps([suffix, checkpoint])
                    if mode == "suffix":
                        assert checkpoint is None
                        assert general_user in json.dumps(
                            suffix
                        ) and general_assistant in json.dumps(suffix)
                    else:
                        assert checkpoint["calendar_history_policy"] == 1
                        count = 4 if mode == "deterministic" else 12
                        assert checkpoint["frontier"] == conv.context_frontier_sequence == count
                        assert checkpoint["source_refs"][3]["sha256"] == rows[3].content_sha256
                        assert (
                            checkpoint["source_refs"][3]["sha256"]
                            != hashlib.sha256(CALENDAR_HISTORY_MARKER.encode()).hexdigest()
                        )
                        validate_checkpoint(
                            checkpoint, expected_sources=sources[:count], prior=None
                        )
                        await db.commit()
                        loaded, loaded_id = await service._load_active_checkpoint(db, conv, dek)
                        assert loaded == checkpoint and loaded_id == checkpoint_id
                        again = await service._prepare_context_history(
                            db,
                            conv,
                            dek,
                            runs[-1].id,
                            conv.next_message_sequence,
                            None,
                            None,
                            settings=settings,
                        )
                        assert old not in json.dumps(again, default=str)
                        assert again[-1] == checkpoint_id
                        assert len(helper_calls) == (1 if mode == "semantic" else 0)
                # Original encrypted messages and hashes remain exactly as stored.
                assert [service._message_read(row, dek) for row in rows] == original_ui
                assert original_ui[3]["content"] == old
                await db.commit()
        finally:
            try:
                async with maker() as db:
                    if cid is not None:
                        await db.execute(delete(MimiConversation).where(MimiConversation.id == cid))
                    await db.execute(delete(CalendarEvent).where(CalendarEvent.id == event_id))
                    await db.execute(delete(CalendarSource).where(CalendarSource.id == source_id))
                    await db.execute(delete(DayAnnotation).where(DayAnnotation.id == marker_id))
                    await db.execute(delete(AppSetting).where(AppSetting.key == policy_key))
                    await db.commit()
            finally:
                await engine.dispose()

    asyncio.run(scenario())
