"""One process-local, finite foreground lease for the singleton Controller."""

from time import monotonic

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.migarden.commands import start_block_reason
from app.domain.migarden.models import ZoneState
from app.domain.migarden.wire import ExchangeEnvelope, ExchangeOut

LEASE_SECONDS = 30


def mark_present(request: Request) -> None:
    request.app.state.migarden_present_until = monotonic() + LEASE_SECONDS


async def hint_idle(
    request: Request,
    db: AsyncSession,
    packet: ExchangeEnvelope,
    result: ExchangeOut,
    zone: ZoneState,
) -> ExchangeOut:
    if (
        monotonic() >= getattr(request.app.state, "migarden_present_until", 0)
        or result.retry_after_seconds is not None
        or packet.reports
        or result.acked_event_ids
        or result.desired_config is not None
        or result.candidates
        or result.grants
        or result.stops
        or zone.report_reconciliation is not None
        or zone.unidentified_execution
        or zone.boot_id != packet.boot_id
        or zone.control_epoch != packet.control_epoch
        or zone.snapshot != packet.snapshot.model_dump(mode="json")
        or packet.snapshot.output != "off"
        or packet.snapshot.active_session is not None
        or not packet.snapshot.ready
    ):
        return result
    if await start_block_reason(db, zone, result.server_time) is None:
        return result.model_copy(update={"retry_after_seconds": 2})
    return result
