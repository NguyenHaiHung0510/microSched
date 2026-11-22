"""Optional bounded telemetry; never an input to the control/safety arbiter."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.migarden.models import BootRecord, HealthRecord, ZoneState
from app.domain.migarden.wire import ExchangeEnvelope, Identity, UTCDateTime, WireModel

Counter = Annotated[int, Field(strict=True, ge=0, le=2**63 - 1)]


class HealthSample(WireModel):
    build_id: Identity
    boot_id: Identity
    sampled_at: UTCDateTime | None
    time_quality: Literal["synced", "holdover", "unknown"]
    uptime_seconds: Counter
    reset_reason: Annotated[int, Field(strict=True, ge=0, le=255)] | None = None
    free_heap: Counter
    minimum_heap: Counter
    wifi_phase: Literal["READY", "TRYING", "CONNECTED", "BACKOFF"]
    sync_status: Literal["OK", "RETRY", "WIFI_PENDING", "CLOCK_PENDING", "SENDING", "UNKNOWN"]
    pending_reports: Annotated[int, Field(strict=True, ge=0, le=512)]
    evidence_gaps: Counter


async def ingest_health(
    db: AsyncSession, packet: ExchangeEnvelope, zone: ZoneState, now: datetime
) -> None:
    if packet.health is None or packet.boot_id != zone.boot_id:
        return
    try:
        sample = HealthSample.model_validate(packet.health)
    except ValidationError:
        return
    if sample.boot_id != packet.boot_id:
        return
    # Server UTC hour is the rate boundary, including replay/offline uploads.
    bucket = now.replace(minute=0, second=0, microsecond=0)
    try:
        async with db.begin_nested():
            await db.execute(
                insert(HealthRecord)
                .values(
                    zone_id="zone-a",
                    hour_start=bucket,
                    received_at=now,
                    boot_id=sample.boot_id,
                    sample=sample.model_dump(mode="json"),
                )
                .on_conflict_do_nothing(index_elements=["zone_id", "hour_start"])
            )
    except SQLAlchemyError:
        # Optional relation/row faults roll back only this savepoint. A lost outer
        # transaction still fails its commit, so no ACK can escape that failure.
        pass


async def latest_health(db: AsyncSession) -> dict | None:
    row = await db.scalar(select(HealthRecord).order_by(HealthRecord.hour_start.desc()).limit(1))
    if row is None:
        return None
    return {"received_at": row.received_at, "sample": row.sample}


async def health_history(db: AsyncSession, criteria) -> dict:
    from app.domain.migarden.queries import (
        bound_history,
        decode_cursor,
        encode_cursor,
        validate_history_dates,
    )

    validate_history_dates(criteria)
    cursor = decode_cursor(criteria.cursor, ("h",)) if criteria.cursor else None
    rows = (
        await db.scalars(
            bound_history(
                select(HealthRecord),
                criteria,
                cursor,
                group="h",
                key=HealthRecord.boot_id,
                ordered_at=HealthRecord.received_at,
                event_at=HealthRecord.received_at,
            )
        )
    ).all()
    page = rows[: criteria.limit]
    boots = select(BootRecord).order_by(BootRecord.first_seen_at.desc()).limit(criteria.limit)
    from app.domain.migarden.schedule import ONE_DAY, day_start

    if criteria.from_day:
        boots = boots.where(BootRecord.first_seen_at >= day_start(criteria.from_day))
    if criteria.to_day:
        boots = boots.where(BootRecord.first_seen_at < day_start(criteria.to_day + ONE_DAY))
    return {
        "items": [{"received_at": row.received_at, "sample": row.sample} for row in page],
        "next_cursor": encode_cursor((page[-1].received_at, "h", page[-1].boot_id))
        if len(rows) > len(page)
        else None,
        "boots": [
            {"boot_id": row.boot_id, "first_seen_at": row.first_seen_at}
            for row in (await db.scalars(boots)).all()
        ],
        "coverage": "partial",
        "time_basis": "server_received",
    }
