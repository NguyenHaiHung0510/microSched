"""Authenticated local-only workflow pilot; existing Mimi CSRF rules apply."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent import workflow_pilot as pilot
from app.agent.service import _owner_id
from app.agent.workflow_probe.contracts import ProbeBlocked
from app.core.settings import get_settings
from app.domain.models import AuthSession
from app.web.deps import require_session
from app.web.mimi_csrf import require_mimi_csrf


def require_pilot():
    if not pilot.pilot_available(get_settings()):
        raise HTTPException(404, "Not Found")


router = APIRouter(
    prefix="/mimi/workflow-pilot", tags=["mimi-pilot"], dependencies=[Depends(require_pilot)]
)
Session = Annotated[AuthSession, Depends(require_session)]


class CreateRun(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    run_id: UUID
    task_ids: list[UUID] = Field(min_length=1, max_length=16)
    engine: Literal["graph", "control"] = "graph"

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.task_ids)) != len(self.task_ids):
            raise ValueError("duplicate_selection")
        return self


class AdvanceRun(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    generation: int = Field(ge=1, strict=True)
    direction: Literal["apply_prefix"] | None = None
    preview_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    cancel: bool = Field(default=False, strict=True)
    resume: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def one_action(self):
        if (
            sum(
                (
                    self.direction is not None,
                    self.preview_digest is not None,
                    self.cancel,
                    self.resume,
                )
            )
            != 1
        ):
            raise ValueError("one_action_required")
        return self


def store(request: Request):
    return pilot.TaskFrameStore(
        get_settings().database_url,
        provider=getattr(request.app.state, "workflow_pilot_provider", None),
    )


async def guarded(coroutine):
    try:
        return await coroutine
    except ProbeBlocked as error:
        raise HTTPException(409, str(error)) from None


@router.get("/tasks")
async def tasks(request: Request, _session: Session):
    return {"items": await store(request).choices()}


@router.get("/runs")
async def runs(request: Request, session: Session):
    owner = str(_owner_id(session))
    current = store(request)
    return {
        "items": [
            await pilot.status_view(
                pilot.PilotWorkflow(current, run_id, owner, policy=pilot.POLICY)
            )
            for run_id in await current.owned_runs(owner)
        ]
    }


@router.post("/runs", dependencies=[Depends(require_mimi_csrf)])
async def create_run(request: Request, payload: CreateRun, session: Session):
    async def invoke():
        current = store(request)
        async with current.invocation(payload.run_id):
            return await pilot.create(
                current, payload.run_id, str(_owner_id(session)), payload.engine, payload.task_ids
            )

    return await guarded(invoke())


@router.get("/runs/{run_id}")
async def get_run(request: Request, run_id: UUID, session: Session):
    return await guarded(
        pilot.status_view(
            pilot.PilotWorkflow(
                store(request), run_id, str(_owner_id(session)), policy=pilot.POLICY
            )
        )
    )


@router.post("/runs/{run_id}/advance", dependencies=[Depends(require_mimi_csrf)])
async def advance_run(request: Request, run_id: UUID, payload: AdvanceRun, session: Session):
    async def invoke():
        current = store(request)
        workflow = pilot.PilotWorkflow(
            current, run_id, str(_owner_id(session)), policy=pilot.POLICY
        )
        await current.load(run_id, owner=workflow.owner)
        async with current.invocation(run_id):
            return await pilot.advance(
                workflow,
                generation=payload.generation,
                direction=payload.direction,
                digest=payload.preview_digest,
                cancel=payload.cancel,
                resume=payload.resume,
            )

    return await guarded(invoke())
