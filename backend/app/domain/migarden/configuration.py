"""Coherent desired/applied configuration with an immutable history of content."""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.migarden.models import ConfigRecord, ReportRecord, ZoneState
from app.domain.migarden.schedule import Forecast, forecast
from app.domain.migarden.storage import Rejected, config_record, get_config, lock_zone
from app.domain.migarden.wire import BundleContent, ConfigurationBundle, Identity, WireModel


class SaveConfig(BundleContent):
    expected_config_ref: Identity | None


class ScheduleProjection(WireModel):
    saved: Forecast
    last_confirmed: Forecast
    application_status: Literal["not_saved", "pending", "applied", "rejected"]
    possible_previous_run: bool


class ConfigView(WireModel):
    desired: ConfigurationBundle | None = None
    desired_saved_at: datetime | None = None
    applied: ConfigurationBundle | None = None
    applied_confirmed_at: datetime | None = None
    application_status: Literal["not_saved", "pending", "applied", "rejected"] = "not_saved"
    reason: str | None = None
    schedule_projection: ScheduleProjection | None = None


async def read_config(
    db: AsyncSession, zone: ZoneState | None, now: datetime | None = None
) -> ConfigView:
    view = await _read_config(db, zone)
    now = now or datetime.now(UTC)
    saved, confirmed = forecast(view.desired, now), forecast(view.applied, now)
    projection = ScheduleProjection(
        saved=saved,
        last_confirmed=confirmed,
        application_status=view.application_status,
        possible_previous_run=bool(
            view.desired
            and view.applied
            and view.desired.schedule != view.applied.schedule
            and view.application_status != "applied"
            and confirmed.status == "scheduled"
        ),
    )
    return view.model_copy(update={"schedule_projection": projection})


async def _read_config(db: AsyncSession, zone: ZoneState | None) -> ConfigView:
    if zone is None:
        return ConfigView()
    applied = await get_config(db, zone.applied_ref)
    saved = await config_record(db, zone.desired_ref)
    if saved is None:
        return ConfigView(applied=applied, applied_confirmed_at=zone.applied_confirmed_at)
    desired = ConfigurationBundle.model_validate(saved.bundle)
    status, reason = "pending", None
    if applied and desired.config_ref == applied.config_ref:
        status = "applied"
    elif zone.boot_id is not None:
        rejected = await db.scalar(
            select(ReportRecord)
            .where(
                ReportRecord.kind == "config_rejected",
                ReportRecord.config_ref == desired.config_ref,
                ReportRecord.boot_id == zone.boot_id,
            )
            .order_by(ReportRecord.sequence.desc())
            .limit(1)
        )
        if rejected is not None:
            status, reason = "rejected", rejected.body["payload"].get("reason")
    return ConfigView(
        desired=desired,
        desired_saved_at=saved.saved_at,
        applied=applied,
        applied_confirmed_at=zone.applied_confirmed_at,
        application_status=status,
        reason=reason,
    )


async def save_config(db: AsyncSession, form: SaveConfig, now: datetime) -> ConfigView:
    zone = await lock_zone(db, create=True)
    if form.expected_config_ref != zone.desired_ref:
        raise Rejected("config_conflict")
    current = await get_config(db, zone.desired_ref)
    if current is None or current.policy != form.policy or current.schedule != form.schedule:
        ref = str(uuid4())
        bundle = ConfigurationBundle(config_ref=ref, policy=form.policy, schedule=form.schedule)
        row = ConfigRecord(config_ref=ref, saved_at=now, bundle=bundle.model_dump(mode="json"))
        db.add(row)
        await db.flush()
        zone.desired_ref = ref
    return await read_config(db, zone, now)
