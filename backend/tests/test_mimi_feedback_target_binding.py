"""No-Postgres ownership-boundary tests for feedback target queries."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.agent.models import MimiRun
from app.agent.service import FeedbackCreate, _feedback_target_query, save_feedback


def _assert_conversation_bound(query, conversation_id, target_id) -> None:
    compiled = query.compile(dialect=postgresql.dialect())
    assert target_id in compiled.params.values()
    assert conversation_id in compiled.params.values()


def test_feedback_target_query_binds_answer_to_its_conversation() -> None:
    conversation_id = uuid4()
    target_id = uuid4()

    query = _feedback_target_query(conversation_id, "turn", str(target_id))

    assert query is not None
    _assert_conversation_bound(query, conversation_id, target_id)
    assert "role" in str(query.compile(dialect=postgresql.dialect())).lower()


@pytest.mark.parametrize("target_type", ["run", "call", "receipt", "operation"])
def test_each_feedback_target_kind_is_conversation_scoped(target_type: str) -> None:
    conversation_id = uuid4()
    target_id = uuid4()

    query = _feedback_target_query(conversation_id, target_type, str(target_id))

    assert query is not None
    _assert_conversation_bound(query, conversation_id, target_id)


def test_ownership_guard_red_for_unscoped_query_then_green_for_current_query() -> None:
    conversation_id = uuid4()
    target_id = uuid4()
    deliberately_unscoped = select(MimiRun.id).where(MimiRun.id == target_id)

    with pytest.raises(AssertionError):
        _assert_conversation_bound(deliberately_unscoped, conversation_id, target_id)

    scoped = _feedback_target_query(conversation_id, "run", str(target_id))
    assert scoped is not None
    _assert_conversation_bound(scoped, conversation_id, target_id)


def test_feedback_rejects_target_absent_from_selected_conversation(monkeypatch) -> None:
    conversation = SimpleNamespace(id=uuid4(), dek_wrapped="synthetic-wrapped-key")
    foreign_target_id = uuid4()
    foreign_owner_conversation_id = uuid4()

    async def owned_conversation(*_args, **_kwargs):
        return conversation

    class EmptyTargetDb:
        statement = None

        async def execute(self, statement):
            self.statement = statement
            parameters = statement.compile(dialect=postgresql.dialect()).params.values()
            is_foreign_target_query = foreign_target_id in parameters
            if is_foreign_target_query:
                # This synthetic target exists in another conversation. If the
                # ownership predicate is removed, an ID-only lookup finds it.
                value = (
                    foreign_target_id
                    if conversation.id not in parameters
                    or foreign_owner_conversation_id == conversation.id
                    else None
                )
            else:
                value = None
            return SimpleNamespace(scalar_one_or_none=lambda: value)

    monkeypatch.setattr("app.agent.service._conversation", owned_conversation)
    db = EmptyTargetDb()
    payload = FeedbackCreate(
        client_id="synthetic-feedback-client",
        target_type="run",
        target_id=str(foreign_target_id),
        comment="Synthetic wrong-conversation target case",
    )

    async def submit():
        with pytest.raises(HTTPException) as raised:
            await save_feedback(db, SimpleNamespace(), conversation.id, payload)
        assert raised.value.status_code == 404

    asyncio.run(submit())
    compiled = db.statement.compile(dialect=postgresql.dialect())
    assert foreign_target_id in compiled.params.values()
    assert conversation.id in compiled.params.values()
    assert foreign_owner_conversation_id != conversation.id


def test_removed_target_scope_would_accept_foreign_run(monkeypatch) -> None:
    """Deliberate RED mutation: an ID-only query bypasses conversation ownership."""

    conversation = SimpleNamespace(id=uuid4(), dek_wrapped="synthetic-wrapped-key")
    foreign_run_id = uuid4()

    async def owned_conversation(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr("app.agent.service._conversation", owned_conversation)
    monkeypatch.setattr(
        "app.agent.service._feedback_target_query",
        lambda _conversation_id, _kind, _target_id: select(MimiRun.id).where(
            MimiRun.id == foreign_run_id
        ),
    )
    monkeypatch.setattr("app.agent.service.mimi_crypto.unwrap_dek", lambda _wrapped: b"synthetic")
    monkeypatch.setattr(
        "app.agent.service.mimi_crypto.seal_content",
        lambda _dek, value, **_kwargs: f"encrypted:{value}",
    )

    async def isolated_bundle(*_args):
        # Isolate this historical query mutation; real causal-binding tests use PG.
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr("app.agent.evidence.capture_feedback", isolated_bundle)

    class ForeignRunDb:
        def __init__(self):
            self.lookups = 0

        async def execute(self, _statement):
            self.lookups += 1
            value = foreign_run_id if self.lookups == 1 else None
            return SimpleNamespace(scalar_one_or_none=lambda: value)

        def add(self, _record):
            return None

        async def flush(self):
            return None

    payload = FeedbackCreate(
        client_id="synthetic-foreign-run-red",
        target_type="run",
        target_id=str(foreign_run_id),
        comment="Synthetic foreign target mutation",
    )
    result = asyncio.run(save_feedback(ForeignRunDb(), SimpleNamespace(), conversation.id, payload))

    assert result["target_id"] == str(foreign_run_id)


def test_feedback_duplicate_client_id_replays_one_encrypted_record(monkeypatch) -> None:
    conversation = SimpleNamespace(id=uuid4(), dek_wrapped="synthetic-wrapped-key")
    target_id = uuid4()

    async def owned_conversation(*_args, **_kwargs):
        return conversation

    monkeypatch.setattr("app.agent.service._conversation", owned_conversation)
    monkeypatch.setattr(
        "app.agent.service.mimi_crypto.unwrap_dek", lambda _wrapped: b"synthetic-dek"
    )
    monkeypatch.setattr(
        "app.agent.service.mimi_crypto.seal_content",
        lambda _dek, value, **_kwargs: f"encrypted:{value}",
    )
    monkeypatch.setattr(
        "app.agent.service.mimi_crypto.open_content",
        lambda _dek, value, **_kwargs: value.removeprefix("encrypted:"),
    )

    bundles = []

    async def isolated_bundle(*_args):
        bundle = SimpleNamespace(id=uuid4())
        bundles.append(bundle)
        return bundle

    monkeypatch.setattr("app.agent.evidence.capture_feedback", isolated_bundle)

    class IdempotentDb:
        def __init__(self):
            self.calls = 0
            self.record = None

        async def execute(self, _statement):
            self.calls += 1
            is_target_lookup = self.calls % 2 == 1
            value = target_id if is_target_lookup else self.record
            return SimpleNamespace(scalar_one_or_none=lambda: value)

        def add(self, record):
            self.record = record

        async def flush(self):
            return None

    db = IdempotentDb()
    payload = FeedbackCreate(
        client_id="synthetic-idempotency-key",
        target_type="run",
        target_id=str(target_id),
        comment="Synthetic feedback comment",
        expected="Synthetic expected classification",
    )

    async def submit_twice():
        first = await save_feedback(db, SimpleNamespace(), conversation.id, payload)
        second = await save_feedback(db, SimpleNamespace(), conversation.id, payload)
        assert first["id"] == second["id"]
        assert len(bundles) == 1
        assert first["evidence_bundle_ids"] == [str(bundles[0].id)]
        assert db.record.comment_ciphertext == "encrypted:Synthetic feedback comment"
        assert db.record.expected_ciphertext == "encrypted:Synthetic expected classification"
        with pytest.raises(HTTPException) as raised:
            await save_feedback(
                db,
                SimpleNamespace(),
                conversation.id,
                payload.model_copy(update={"comment": "Changed synthetic feedback"}),
            )
        assert raised.value.status_code == 409

    asyncio.run(submit_twice())
