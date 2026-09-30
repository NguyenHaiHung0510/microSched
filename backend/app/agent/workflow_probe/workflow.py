"""Shared typed stages; PostgreSQL owns content, effects and execution authority."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.workflow_probe.contracts import (
    NOTE_ADAPTER,
    TASK_ADAPTER,
    Confirmation,
    Preview,
    ProbeBlocked,
    Record,
    canonical_json,
    freeze_preview,
)
from app.agent.workflow_probe.store import PgFrameStore, StoredFrame

STAGES = ("query", "group", "draft", "direction", "materialize", "confirmation", "execute")
STOPPED = {"succeeded", "expired", "cancelled", "reconcile", "repreview"}
Fault = Callable[[str], Awaitable[None]]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class Source(StrictModel):
    id: str
    version: int = Field(gt=0)
    title: str


class Call(StrictModel):
    step: Literal["group", "draft"]
    status: Literal["dispatched", "terminal"]
    result: str | None = None


class Operation(StrictModel):
    id: str
    title: str


class PreviewContent(StrictModel):
    authority_ref: str
    owner: str
    generation: int = Field(gt=0)
    policy: str
    domain: Literal["task", "note"]
    sources: list[Source] = Field(max_length=16)
    operations: list[Operation] = Field(max_length=16)
    groups: list[list[str]] = Field(min_length=1, max_length=16)

    def preview(self) -> Preview:
        return Preview(
            self.authority_ref,
            self.owner,
            self.generation,
            self.policy,
            self.domain,
            tuple(Record(s.id, s.version, s.title) for s in self.sources),
            tuple((o.id, o.title) for o in self.operations),
            tuple(tuple(group) for group in self.groups),
        )


class ConfirmationContent(StrictModel):
    owner: str
    generation: int = Field(gt=0)
    preview_digest: str

    def confirmation(self) -> Confirmation:
        return Confirmation(self.owner, self.generation, self.preview_digest)


class Content(StrictModel):
    schema_version: Literal[2] = 2
    policy: str
    domain: Literal["task", "note"]
    authority_ref: str
    contract_hash: str
    snapshot: list[Source] = Field(default_factory=list, max_length=16)
    groups: list[list[str]] = Field(default_factory=list, max_length=16)
    draft: str = ""
    direction: Literal["apply_prefix"] | None = None
    preview: PreviewContent | None = None
    confirmation: ConfirmationContent | None = None
    provider_calls: list[Call] = Field(default_factory=list, max_length=8)
    events: list[str] = Field(default_factory=list, max_length=32)
    active_seconds: float = Field(default=0.0, ge=0, le=120)
    active_started_at: str | None = None
    stop_reason: str | None = None
    receipt: dict[str, str | int] | None = None


class Workflow:
    def __init__(
        self,
        store: PgFrameStore,
        run_id: UUID,
        owner: str,
        *,
        policy: str = "probe-v1",
        version: int = 2,
        now: Callable[[], datetime] | None = None,
        fault: Fault | None = None,
    ):
        if version not in {1, 2}:
            raise ProbeBlocked("runner_version_unsupported")
        self.store, self.run_id, self.owner = store, run_id, owner
        self.policy, self.version = policy, version
        self.now = now or (lambda: datetime.now(UTC))
        self.fault = fault
        self.accounted_at = perf_counter()
        self.contract_hash = hashlib.sha256(
            canonical_json(
                {
                    "handler_contract": "synthetic-title-prefix-v1",
                    "stages": STAGES,
                    "task_prefix": TASK_ADAPTER.title_prefix,
                    "note_prefix": NOTE_ADAPTER.title_prefix,
                    "preview_schema": PreviewContent.model_json_schema(),
                    "confirmation_schema": ConfirmationContent.model_json_schema(),
                }
            ).encode()
        ).hexdigest()

    def wire(self, body: Content) -> dict[str, object]:
        value = body.model_dump()
        if self.version == 1:
            value["schema_version"] = 1
            value["draft_text"] = value.pop("draft")
        return value

    async def create(self, domain: str, engine: str, records: tuple[Record, ...]) -> StoredFrame:
        if domain not in {"task", "note"}:
            raise ProbeBlocked("unsupported_synthetic_domain")
        body = Content(
            policy=self.policy,
            domain=domain,
            authority_ref=str(uuid4()),
            contract_hash=self.contract_hash,
        )
        created_at = self.now()
        return await self.store.create(
            self.run_id,
            owner=self.owner,
            generation=1,
            engine=engine,
            content=self.wire(body),
            records=records,
            now=created_at,
            expires_at=created_at + timedelta(hours=24),
        )

    async def load(self) -> tuple[StoredFrame, Content]:
        frame = await self.store.load(self.run_id, owner=self.owner)
        raw = dict(frame.content)
        stored_version = raw.get("schema_version")
        if type(stored_version) is not int or stored_version not in {1, 2}:
            raise ProbeBlocked("state_version_unsupported")
        if stored_version > self.version:
            raise ProbeBlocked("state_version_unsupported")
        if stored_version == 1:
            if "draft" in raw or "draft_text" not in raw:
                raise ProbeBlocked("legacy_state_shape_invalid")
            raw["draft"] = raw.pop("draft_text")
            raw["schema_version"] = 2
        try:
            body = Content.model_validate(raw)
        except ValidationError:
            raise ProbeBlocked("invalid_content_schema") from None
        if stored_version == 1 and self.version == 2 and frame.phase not in STOPPED:
            body.events.append("representation_upgraded_v1_to_v2")
            frame = await self.store.save(frame, phase=frame.phase, content=self.wire(body))
        if frame.phase not in STOPPED:
            if self.now() >= frame.expires_at:
                body.stop_reason = "expired"
                frame = await self.store.save(frame, phase="expired", content=self.wire(body))
            elif body.policy != self.policy or body.contract_hash != self.contract_hash:
                body.confirmation = None
                body.stop_reason = "policy_requires_repreview"
                frame = await self.store.save(frame, phase="repreview", content=self.wire(body))
        return frame, body

    async def hook(self, point: str) -> None:
        if self.fault:
            await self.fault(point)

    async def enter(self) -> float:
        frame, body = await self.load()
        if frame.phase in STOPPED:
            return 0.0
        if body.active_started_at:
            elapsed = (self.now() - datetime.fromisoformat(body.active_started_at)).total_seconds()
            if elapsed < 0:
                raise ProbeBlocked("active_clock_reversed")
            body.active_seconds = min(120.0, body.active_seconds + elapsed)
        body.active_started_at = self.now().isoformat()
        if body.active_seconds >= 120:
            body.active_started_at = None
            body.stop_reason = "active_deadline_exceeded"
            phase = (
                "reconcile"
                if any(c.status == "dispatched" for c in body.provider_calls)
                else ("cancelled")
            )
            await self.store.save(frame, phase=phase, content=self.wire(body))
            return 0.0
        await self.store.save(frame, phase=frame.phase, content=self.wire(body))
        self.accounted_at = perf_counter()
        return 120 - body.active_seconds

    async def leave(self) -> None:
        frame, body = await self.load()
        if frame.phase in {"succeeded", "expired", "cancelled"}:
            return
        if body.active_started_at:
            body.active_seconds = min(
                120.0,
                body.active_seconds
                + max(
                    0, (self.now() - datetime.fromisoformat(body.active_started_at)).total_seconds()
                ),
            )
            body.active_started_at = None
            await self.store.save(frame, phase=frame.phase, content=self.wire(body))

    async def accept(
        self,
        *,
        generation: int,
        direction: str | None = None,
        confirmation: ConfirmationContent | None = None,
    ) -> None:
        frame, body = await self.load()
        if type(generation) is not int or frame.generation != generation:
            raise ProbeBlocked("input_generation_mismatch")
        if frame.phase == "direction" and direction == "apply_prefix" and confirmation is None:
            body.direction = "apply_prefix"
        elif frame.phase == "confirmation" and confirmation is not None and direction is None:
            if body.preview is None:
                raise ProbeBlocked("missing_preview")
            preview = body.preview.preview()
            if (
                confirmation.owner != frame.owner
                or confirmation.generation != frame.generation
                or confirmation.preview_digest != preview.digest
            ):
                raise ProbeBlocked("confirmation_mismatch")
            body.confirmation = confirmation
        else:
            raise ProbeBlocked("input_phase_mismatch")
        await self.store.save(frame, phase=frame.phase, content=self.wire(body))

    async def provider(self, frame: StoredFrame, body: Content, step: str):
        existing = next((call for call in body.provider_calls if call.step == step), None)
        if existing:
            if existing.status != "terminal":
                body.stop_reason = "provider_outcome_unknown"
                frame = await self.store.save(frame, phase="reconcile", content=self.wire(body))
                return frame, body, None
            return frame, body, existing.result
        call = Call(step=step, status="dispatched")
        body.provider_calls.append(call)
        frame = await self.store.save(frame, phase=frame.phase, content=self.wire(body))
        await self.hook("after_intent")
        await self.store.fake_dispatch(frame, step)
        await self.hook("after_dispatch")
        # Author-written deterministic fake; not model or conversation-quality evidence.
        call.status = "terminal"
        call.result = "grouped" if step == "group" else "Đề xuất áp dụng prefix cho nhóm đã chọn."
        frame = await self.store.save(frame, phase=frame.phase, content=self.wire(body))
        await self.hook("after_terminal")
        return frame, body, call.result

    async def step(self, expected: str) -> str:
        try:
            return await self._step(expected)
        except ProbeBlocked:
            raise
        except Exception:
            # Framework error writes must not serialize private provider/frame details.
            raise RuntimeError("probe_stage_failed") from None

    async def _step(self, expected: str) -> str:
        frame, body = await self.load()
        # A completed PG step may replay after a crash before the graph checkpoint.
        if frame.phase != expected:
            if frame.phase in STOPPED or (
                frame.phase in STAGES and STAGES.index(frame.phase) > STAGES.index(expected)
            ):
                return frame.phase
            raise ProbeBlocked("stage_cursor_mismatch")
        elapsed = perf_counter() - self.accounted_at
        if body.active_seconds + elapsed >= 120:
            body.stop_reason = "active_deadline_exceeded"
            await self.store.save(frame, phase="cancelled", content=self.wire(body))
            return "cancelled"
        if expected == "query":
            body.snapshot = [
                Source(id=r.record_id, version=r.version, title=r.title)
                for r in await self.store.records(frame)
            ]
            if not body.snapshot:
                raise ProbeBlocked("empty_selection")
            next_phase = "group"
        elif expected in {"group", "draft"}:
            frame, body, result = await self.provider(frame, body, expected)
            if result is None:
                return frame.phase
            if expected == "group":
                body.groups = [
                    [s.id for s in body.snapshot if s.version % 2 == parity] for parity in (0, 1)
                ]
                body.groups = [group for group in body.groups if group]
                next_phase = "draft"
            else:
                body.draft = result
                next_phase = "direction"
        elif expected == "direction":
            if body.direction is None:
                return expected
            next_phase = "materialize"
        elif expected == "materialize":
            adapter = {"task": TASK_ADAPTER, "note": NOTE_ADAPTER}[body.domain]
            preview = freeze_preview(
                adapter,
                tuple(Record(s.id, s.version, s.title) for s in body.snapshot),
                owner=frame.owner,
                generation=frame.generation,
                policy=body.policy,
                authority_ref=body.authority_ref,
                groups=tuple(tuple(group) for group in body.groups),
            )
            body.preview = PreviewContent.model_validate(preview.content())
            next_phase = "confirmation"
        elif expected == "confirmation":
            if body.confirmation is None:
                return expected
            next_phase = "execute"
        elif expected == "execute":
            if body.preview is None or body.confirmation is None:
                raise ProbeBlocked("missing_execution_authority")
            try:
                result = await self.store.execute(
                    frame,
                    body.preview.preview(),
                    body.confirmation.confirmation(),
                    policy=self.policy,
                    now=self.now(),
                    fault=self.fault,
                )
            except ProbeBlocked as error:
                if str(error) not in {"source_requires_repreview", "policy_requires_repreview"}:
                    raise
                body.confirmation = None
                body.stop_reason = str(error)
                result = await self.store.save(frame, phase="repreview", content=self.wire(body))
            return result.phase
        else:
            raise ProbeBlocked("unsupported_stage")
        body.events.append(expected)
        # Invocation wall-clock is durably accounted by enter/leave, including crashes.
        self.accounted_at = perf_counter()
        await self.store.save(frame, phase=next_phase, content=self.wire(body))
        await self.hook(f"after_{expected}")
        return next_phase

    async def has_input(self, phase: str) -> bool:
        _, body = await self.load()
        return (phase == "direction" and body.direction is not None) or (
            phase == "confirmation" and body.confirmation is not None
        )

    async def status(self) -> dict[str, object]:
        frame, body = await self.load()
        return {
            "run_id": str(frame.run_id),
            "generation": frame.generation,
            "phase": frame.phase,
            "schema_version": frame.content["schema_version"],
            "draft": body.draft,
            "preview": body.preview.model_dump() if body.preview else None,
            "preview_digest": body.preview.preview().digest if body.preview else None,
            "receipt": body.receipt,
            "stop_reason": body.stop_reason,
            "provider_calls": len(body.provider_calls),
            "events": body.events,
        }
