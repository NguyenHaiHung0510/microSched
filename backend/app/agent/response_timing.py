"""Client-observed response segments. Never authority, billing, or provider latency."""

from __future__ import annotations

from collections import Counter
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from app.agent import crypto, message_provenance
from app.agent.models import (
    MimiChangeSet,
    MimiEvent,
    MimiExecutionReceipt,
    MimiMessage,
    MimiProviderCall,
    MimiRun,
)

KIND = "response.timing.v1"
ACTIVE = {"accepted", "building", "running", "executing"}
MAX_ELAPSED_MS = 86_400_000  # A new document never inherits a monotonic start.


class ResponseTimingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    client_id: str = Field(min_length=1, max_length=160)
    run_id: UUID
    target_id: UUID
    phase: Literal["send", "resume", "confirmation"]
    source_id: str = Field(min_length=1, max_length=160)
    observation: Literal["visible_paint", "hidden", "offscreen"]
    elapsed_ms: float | None = Field(default=None, ge=0, le=MAX_ELAPSED_MS, allow_inf_nan=False)

    @field_validator("elapsed_ms", mode="before")
    @classmethod
    def numeric_clock(cls, value):
        if value is not None and type(value) not in {int, float}:
            raise ValueError("elapsed_ms must be a finite browser duration")
        return value

    @model_validator(mode="after")
    def paint_requires_clock(self):
        if (self.observation == "visible_paint") != (self.elapsed_ms is not None):
            raise ValueError("only a visible paint has an elapsed measurement")
        return self


def stopped_outcome(run):
    if run.state in ACTIVE:
        return "pending"
    if run.state == "cancelled":
        return "cancelled"
    if run.state in {"completed", "waiting_confirmation"}:
        return "succeeded"
    return "unknown" if run.provider_outcome == "unknown" else "failed"


def response_segments(runs, messages, proofs, changes, receipts, calls):
    """One row per response/decision, including legacy missing observations."""
    by_run = {str(r.id): r for r in runs}
    parents = {
        r.error_code.removeprefix("resumed_by:"): str(r.id)
        for r in runs
        if r.error_code and r.error_code.startswith("resumed_by:")
    }
    for call in calls:
        parent = (call.route or {}).get("parent_run_id")
        if parent:
            parents[str(call.run_id)] = str(parent)
    sources = {str(m.run_id): m.client_id for m in messages if m.role == "user" and m.client_id}
    change_by_run = {str(c.run_id): c for c in changes}
    receipt_by_change = {str(r.change_set_id): r for r in receipts}
    rows = []
    answered = set()
    confirmed = set()

    def row(run, target, phase, source, kind, outcome):
        return {
            "run_id": str(run.id),
            "target_id": str(target),
            "phase": phase,
            "source_id": source,
            "response_kind": kind,
            "outcome": outcome,
            "parent_run_id": parents.get(str(run.id)),
            "elapsed_ms": None,
            "observation": "missing",
            "provenance": "client_observed_browser_monotonic_to_paint_opportunity",
        }

    for message in messages:
        rid = str(message.run_id)
        if message.role != "assistant" or rid not in by_run:
            continue
        run = by_run[rid]
        proof = proofs.get(message.id, {})
        producer = proof.get("producer_code")
        phase = "resume" if rid in parents else "send"
        source = parents.get(rid) or sources.get(rid)
        kind = "answer" if proof.get("origin") == "model_answer" else "notice"
        outcome = stopped_outcome(run)
        if producer in {"preview_prepared", "undo_prepared"}:
            kind, outcome = "preview", "succeeded"
        elif producer in {"operation_committed", "collection_committed"}:
            change = change_by_run.get(rid)
            if change is not None and str(change.id) in receipt_by_change:
                phase, source = "confirmation", str(change.id)
                kind, outcome = "receipt", "succeeded"
                confirmed.add(rid)
        elif proof.get("origin") == "model_answer":
            outcome = "succeeded"
        elif producer and producer != "local_deterministic_result":
            # A server refusal is not turned into a successful answer by a later
            # confirmation/resume or by a successful provider call.
            outcome = (
                "cancelled"
                if run.state == "cancelled"
                else "unknown"
                if run.provider_outcome == "unknown"
                else "failed"
            )
        rows.append(row(run, message.id, phase, source, kind, outcome))
        if phase != "confirmation":
            answered.add(rid)

    for run in runs:
        rid = str(run.id)
        if rid not in answered:
            phase = "resume" if rid in parents else "send"
            outcome = stopped_outcome(run)
            if outcome == "succeeded":
                outcome = "unknown"  # A completed run is not proof of an answer.
            rows.append(
                row(
                    run,
                    run.id,
                    phase,
                    parents.get(rid) or sources.get(rid),
                    "status",
                    outcome,
                )
            )
        change = change_by_run.get(rid)
        if change is not None and rid not in confirmed:
            receipt = receipt_by_change.get(str(change.id))
            outcome = (
                "succeeded"
                if receipt
                else "pending"
                if change.state == "pending"
                else "cancelled"
                if change.state == "rejected"
                else "failed"
            )
            rows.append(row(run, change.id, "confirmation", str(change.id), "decision", outcome))
    return rows


def summarize_segments(rows, events):
    recorded = {}
    for event in events:
        payload = event.payload
        key = (payload.get("target_id"), payload.get("phase"))
        recorded.setdefault(key, []).append(payload)
    responses = []
    for row in rows:
        receipts = recorded.get((row["target_id"], row["phase"]), [])
        result = dict(row)
        if len(receipts) == 1:
            receipt = receipts[0]
            try:
                valid = ResponseTimingCreate.model_validate(
                    {k: receipt[k] for k in ResponseTimingCreate.model_fields}
                )
            except ValueError, KeyError, TypeError:
                valid = None
            if valid and str(valid.run_id) == row["run_id"] and valid.source_id == row["source_id"]:
                result.update(elapsed_ms=valid.elapsed_ms, observation=valid.observation)
        elif receipts:
            result["observation"] = "conflicting_receipts"
        responses.append(result)
    successful = [r for r in responses if r["outcome"] == "succeeded"]
    values = [r["elapsed_ms"] for r in successful if r["elapsed_ms"] is not None]
    outcomes = Counter(r["outcome"] for r in responses)
    return {
        "version": 1,
        "scope": "all_retained_response_segments",
        "provenance": "client_observed_not_provider_latency",
        "min_ms": min(values) if values else None,
        "avg_ms": sum(values) / len(values) if values else None,
        "max_ms": max(values) if values else None,
        "observed": len(values),
        "eligible": len(successful),
        "missing": len(successful) - len(values),
        "pending": outcomes["pending"],
        "failed": outcomes["failed"],
        "cancelled": outcomes["cancelled"],
        "unknown": outcomes["unknown"],
        "responses": responses,
    }


async def retained_response_timings(db, conversation, runs, messages, calls):
    """Queries are independent of the public last-events/messages window."""
    dek = crypto.unwrap_dek(conversation.dek_wrapped)
    assistants = [m for m in messages if m.role == "assistant"]
    proofs = {}
    for start in range(0, len(assistants), message_provenance.MAX_MESSAGES):
        proofs.update(
            await message_provenance.read_message_provenance(
                db, conversation, assistants[start : start + message_provenance.MAX_MESSAGES], dek
            )
        )
    changes = (
        await db.scalars(
            select(MimiChangeSet).join(MimiRun).where(MimiRun.conversation_id == conversation.id)
        )
    ).all()
    receipts = (
        await db.scalars(
            select(MimiExecutionReceipt)
            .join(MimiChangeSet)
            .join(MimiRun)
            .where(MimiRun.conversation_id == conversation.id)
        )
    ).all()
    events = (
        await db.scalars(
            select(MimiEvent)
            .join(MimiRun)
            .where(MimiRun.conversation_id == conversation.id, MimiEvent.kind == KIND)
            .order_by(MimiEvent.sequence)
        )
    ).all()
    rows = response_segments(runs, messages, proofs, changes, receipts, calls)
    return summarize_segments(rows, events)


async def save_response_timing(db, auth, conversation_id, payload):
    # Import at the boundary to reuse exactly the app's ownership and append
    # fences; this observational module cannot execute a model or domain tool.
    from app.agent.service import _append_event, _conversation

    conversation = await _conversation(db, auth, conversation_id, lock=True)
    run = (
        await db.scalars(
            select(MimiRun)
            .where(MimiRun.id == payload.run_id, MimiRun.conversation_id == conversation.id)
            .with_for_update()
        )
    ).one_or_none()
    if run is None:
        raise HTTPException(404, "Mimi response not found")
    runs = (
        await db.scalars(select(MimiRun).where(MimiRun.conversation_id == conversation.id))
    ).all()
    messages = (
        await db.execute(
            select(
                MimiMessage.id,
                MimiMessage.run_id,
                MimiMessage.role,
                MimiMessage.sequence,
                MimiMessage.conversation_id,
                MimiMessage.client_id,
            )
            .where(MimiMessage.conversation_id == conversation.id)
            .order_by(MimiMessage.sequence)
        )
    ).all()
    calls = (
        await db.scalars(
            select(MimiProviderCall).join(MimiRun).where(MimiRun.conversation_id == conversation.id)
        )
    ).all()
    view = await retained_response_timings(db, conversation, runs, messages, calls)
    segment = next(
        (
            r
            for r in view["responses"]
            if r["target_id"] == str(payload.target_id)
            and r["run_id"] == str(payload.run_id)
            and r["phase"] == payload.phase
        ),
        None,
    )
    if segment is None or segment["source_id"] != payload.source_id:
        raise HTTPException(404, "Mimi response binding mismatch")
    if segment["outcome"] == "pending":
        raise HTTPException(409, "Mimi response is not complete")
    body = payload.model_dump(mode="json")
    existing = (
        await db.scalars(
            select(MimiEvent)
            .join(MimiRun)
            .where(
                MimiRun.conversation_id == conversation.id,
                MimiEvent.kind == KIND,
            )
        )
    ).all()
    for event in existing:
        prior = event.payload
        if prior.get("client_id") == payload.client_id or (
            prior.get("target_id") == str(payload.target_id) and prior.get("phase") == payload.phase
        ):
            if any(prior.get(key) != value for key, value in body.items()):
                raise HTTPException(409, "Mimi response timing conflicts with existing receipt")
            return prior
    await _append_event(db, run.id, KIND, body)
    return body
