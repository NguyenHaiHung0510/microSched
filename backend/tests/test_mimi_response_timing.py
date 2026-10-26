"""Deterministic browser timing contracts; no app provider or real data."""

import asyncio
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.agent import response_timing as timing


def run(**patch):
    return NS(id=uuid4(), state="completed", provider_outcome="succeeded", error_code=None, **patch)


def message(r, role="assistant", **patch):
    return NS(id=uuid4(), run_id=r.id, role=role, client_id=None, **patch)


def payload(r, target, **patch):
    values = dict(
        client_id="timing-fixture",
        run_id=r.id,
        target_id=target,
        phase="send",
        source_id="submit-fixture",
        observation="visible_paint",
        elapsed_ms=2000,
    )
    return timing.ResponseTimingCreate(**(values | patch))


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), True, "2000", 86_400_001])
def test_invalid_clock_cannot_become_a_measurement(value):
    with pytest.raises(ValidationError):
        payload(run(), uuid4(), elapsed_ms=value)


def test_only_visible_paint_has_a_measurement_and_extra_authority_is_rejected():
    r = run()
    assert payload(r, uuid4(), elapsed_ms=0).elapsed_ms == 0
    for patch in [dict(observation="hidden"), dict(elapsed_ms=None), dict(outcome="succeeded")]:
        with pytest.raises(ValidationError):
            payload(r, uuid4(), **patch)
    assert payload(r, uuid4(), observation="offscreen", elapsed_ms=None).elapsed_ms is None


def test_two_eight_missing_hidden_fail_cancel_pending_and_duplicate_receipts():
    rows, events = [], []
    r = run()
    for duration, outcome in [
        (2000, "succeeded"),
        (8000, "succeeded"),
        (None, "succeeded"),
        (9000, "failed"),
        (1000, "cancelled"),
        (None, "pending"),
    ]:
        mid = uuid4()
        rows.append(
            dict(
                run_id=str(r.id),
                target_id=str(mid),
                phase="send",
                source_id="submit-fixture",
                outcome=outcome,
                elapsed_ms=None,
                observation="missing",
            )
        )
        if duration is not None:
            events.append(NS(payload=payload(r, mid, elapsed_ms=duration).model_dump(mode="json")))
    summary = timing.summarize_segments(rows, events)
    assert (summary["min_ms"], summary["avg_ms"], summary["max_ms"]) == (2000, 5000, 8000)
    assert (summary["observed"], summary["eligible"], summary["missing"]) == (2, 3, 1)
    assert (summary["failed"], summary["cancelled"], summary["pending"]) == (1, 1, 1)
    # Corrupt duplicate persisted events abstain rather than increase sample n.
    duplicated = timing.summarize_segments(rows, events + events[:1])
    assert duplicated["observed"] == 1 and duplicated["eligible"] == 3
    assert duplicated["responses"][0]["observation"] == "conflicting_receipts"
    empty = timing.summarize_segments([], [])
    assert empty["min_ms"] is empty["avg_ms"] is empty["max_ms"] is None


def test_preview_and_confirm_keep_phase_identity_after_run_state_changes():
    r = run()
    user = message(r, role="user")
    user.client_id = "submit-fixture"
    preview, committed = message(r), message(r)
    change = NS(id=uuid4(), run_id=r.id, state="executed")
    receipt = NS(change_set_id=change.id)
    proofs = {
        preview.id: {"producer_code": "preview_prepared", "origin": "server_notice"},
        committed.id: {"producer_code": "operation_committed", "origin": "server_notice"},
    }
    rows = timing.response_segments(
        [r], [user, preview, committed], proofs, [change], [receipt], []
    )
    assert len(rows) == 2
    assert [(r["phase"], r["response_kind"], r["outcome"]) for r in rows] == [
        ("send", "preview", "succeeded"),
        ("confirmation", "receipt", "succeeded"),
    ]
    assert rows[0]["source_id"] == user.client_id
    assert rows[1]["source_id"] == str(change.id)


def test_resume_retains_parent_and_refusal_does_not_become_success():
    parent, child = run(), run()
    parent.state = "halted"
    parent.error_code = f"resumed_by:{child.id}"
    failed, answer = message(parent), message(child)
    proofs = {
        failed.id: {"producer_code": "provider_terminal", "origin": "server_notice"},
        answer.id: {"producer_code": "provider_text", "origin": "model_answer"},
    }
    rows = timing.response_segments([parent, child], [failed, answer], proofs, [], [], [])
    assert rows[0]["outcome"] == "failed"
    assert rows[1]["phase"] == "resume" and rows[1]["source_id"] == str(parent.id)


def test_no_answer_is_not_a_success_sample_and_unknown_notice_stays_unknown():
    completed = run()
    rows = timing.response_segments([completed], [], {}, [], [], [])
    assert rows[0]["outcome"] == "unknown"
    assert timing.summarize_segments(rows, [])["eligible"] == 0
    uncertain = run()
    uncertain.state, uncertain.provider_outcome = "outcome_unknown", "unknown"
    notice = message(uncertain)
    rows = timing.response_segments(
        [uncertain],
        [notice],
        {notice.id: {"producer_code": "provider_terminal", "origin": "server_notice"}},
        [],
        [],
        [],
    )
    assert rows[0]["outcome"] == "unknown"


def test_hidden_receipt_remains_missing_in_success_denominator():
    r, mid = run(), uuid4()
    rows = [
        dict(
            run_id=str(r.id),
            target_id=str(mid),
            phase="send",
            source_id="submit-fixture",
            outcome="succeeded",
        )
    ]
    receipt = payload(r, mid, observation="hidden", elapsed_ms=None)
    result = timing.summarize_segments(rows, [NS(payload=receipt.model_dump(mode="json"))])
    assert (result["observed"], result["eligible"], result["missing"]) == (0, 1, 1)
    assert result["avg_ms"] is None and result["responses"][0]["observation"] == "hidden"


def test_retained_aggregation_does_not_use_public_event_window():
    r = run()
    rows, events = [], []
    for _ in range(1100):
        target = uuid4()
        rows.append(
            dict(
                run_id=str(r.id),
                target_id=str(target),
                phase="send",
                source_id="submit-fixture",
                outcome="succeeded",
            )
        )
        events.append(NS(payload=payload(r, target).model_dump(mode="json")))
    result = timing.summarize_segments(rows, events)
    assert result["observed"] == result["eligible"] == 1100
    assert result["avg_ms"] == 2000


def test_endpoint_binding_replay_conflict_and_no_pending_writes(monkeypatch):
    cid, r, target = uuid4(), run(), uuid4()
    r.conversation_id = cid
    conversation = NS(id=cid)
    descriptor = dict(
        run_id=str(r.id),
        target_id=str(target),
        phase="send",
        source_id="submit-fixture",
        outcome="succeeded",
    )
    events = []

    async def owned(*args, **kwargs):
        assert kwargs["lock"] is True
        return conversation

    async def retained(*args):
        return {"responses": [descriptor]}

    async def append(db, rid, kind, body):
        assert rid == r.id and kind == timing.KIND
        events.append(NS(payload=body))

    class DB:
        async def scalars(self, statement):
            sql = str(statement)
            if "mimi_event" in sql:
                values = events
            elif "mimi_provider_call" in sql:
                values = []
            else:
                compiled = statement.compile(dialect=postgresql.dialect())
                assert cid in compiled.params.values()
                values = [r]
            return NS(one_or_none=lambda: values[0] if values else None, all=lambda: values)

        async def execute(self, statement):
            return NS(all=lambda: [])

    monkeypatch.setattr("app.agent.service._conversation", owned)
    monkeypatch.setattr("app.agent.service._append_event", append)
    monkeypatch.setattr(timing, "retained_response_timings", retained)
    body = payload(r, target)

    async def scenario():
        db = DB()
        one = await timing.save_response_timing(db, NS(), cid, body)
        assert await timing.save_response_timing(db, NS(), cid, body) == one
        assert len(events) == 1
        for changed in [
            body.model_copy(update={"elapsed_ms": 3000}),
            body.model_copy(update={"client_id": "another-key"}),
        ]:
            with pytest.raises(HTTPException) as error:
                await timing.save_response_timing(db, NS(), cid, changed)
            assert error.value.status_code == 409
        with pytest.raises(HTTPException) as error:
            await timing.save_response_timing(
                db, NS(), cid, body.model_copy(update={"source_id": "wrong"})
            )
        assert error.value.status_code == 404
        descriptor["outcome"] = "pending"
        with pytest.raises(HTTPException) as error:
            await timing.save_response_timing(db, NS(), cid, body)
        assert error.value.status_code == 409 and len(events) == 1

    asyncio.run(scenario())
