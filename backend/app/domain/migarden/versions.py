"""Read-only immutable configuration evidence and schedule-change timeline."""

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.migarden.models import ConfigRecord, ReportRecord
from app.domain.migarden.queries import (
    Cursor,
    HistoryFilter,
    HistoryItem,
    bound_history,
    decode_cursor,
    encode_cursor,
    validate_history_dates,
)
from app.domain.migarden.storage import Rejected, config_record, read_zone


def schedule_versions():
    order = (ConfigRecord.saved_at, ConfigRecord.id)
    return select(
        ConfigRecord.config_ref,
        ConfigRecord.saved_at,
        ConfigRecord.bundle["schedule"].label("schedule"),
        func.lag(ConfigRecord.bundle["schedule"]).over(order_by=order).label("previous"),
    ).cte("schedule_versions")


def changed_refs():
    versions = schedule_versions()
    return select(versions.c.config_ref).where(
        versions.c.schedule.is_distinct_from(versions.c.previous)
    )


async def version_detail(db: AsyncSession, ref: str) -> dict:
    row = await config_record(db, ref)
    if row is None:
        raise Rejected("config_not_found", 404)
    previous = await db.scalar(
        select(ConfigRecord)
        .where(
            or_(
                ConfigRecord.saved_at < row.saved_at,
                and_(ConfigRecord.saved_at == row.saved_at, ConfigRecord.id < row.id),
            )
        )
        .order_by(ConfigRecord.saved_at.desc(), ConfigRecord.id.desc())
        .limit(1)
    )
    reports = (
        await db.scalars(
            select(ReportRecord)
            .where(
                ReportRecord.config_ref == ref,
                ReportRecord.kind.in_(("config_applied", "config_rejected")),
            )
            .order_by(ReportRecord.received_at.desc(), ReportRecord.event_id.desc())
            .limit(50)
        )
    ).all()
    zone = await read_zone(db)
    return {
        "config_ref": ref,
        "saved_at": row.saved_at,
        "bundle": row.bundle,
        "previous_ref": previous.config_ref if previous else None,
        "previous_bundle": previous.bundle if previous else None,
        "schedule_changed": previous is None
        or row.bundle["schedule"] != previous.bundle["schedule"],
        "last_confirmed_ref": zone.applied_ref if zone else None,
        "evidence": [
            {
                "event_id": report.event_id,
                "kind": report.kind,
                "boot_id": report.boot_id,
                "sequence": report.sequence,
                "applied_at": report.occurred_at
                if report.kind == "config_applied" and report.body["time_quality"] != "unknown"
                else None,
                "occurred_at": report.occurred_at,
                "received_at": report.received_at,
                "time_quality": report.body["time_quality"],
                "reason": report.body["payload"].get("reason"),
            }
            for report in reports
        ],
        "evidence_limit": 50,
    }


async def version_list(db: AsyncSession, criteria: HistoryFilter) -> dict:
    validate_history_dates(criteria)
    cursor = decode_cursor(criteria.cursor, ("v",)) if criteria.cursor else None
    rows = (
        await db.scalars(
            bound_history(
                select(ConfigRecord).where(ConfigRecord.config_ref.in_(changed_refs())),
                criteria,
                cursor,
                group="v",
                key=ConfigRecord.config_ref,
                ordered_at=ConfigRecord.saved_at,
                event_at=ConfigRecord.saved_at,
            )
        )
    ).all()
    page = rows[: criteria.limit]
    zone = await read_zone(db)
    return {
        "items": [
            {
                "config_ref": row.config_ref,
                "saved_at": row.saved_at,
                "bundle": row.bundle,
                "is_saved": bool(zone and zone.desired_ref == row.config_ref),
                "is_last_confirmed": bool(zone and zone.applied_ref == row.config_ref),
            }
            for row in page
        ],
        "next_cursor": encode_cursor((page[-1].saved_at, "v", page[-1].config_ref))
        if len(rows) > len(page)
        else None,
    }


async def config_events(
    db: AsyncSession, criteria: HistoryFilter, cursor: Cursor | None
) -> list[tuple[Cursor, HistoryItem]]:
    if criteria.source or criteria.category == "watering":
        return []
    result = []
    if criteria.result is None:
        versions = schedule_versions()
        query = (
            select(ConfigRecord, versions.c.previous)
            .join(versions, versions.c.config_ref == ConfigRecord.config_ref)
            .where(versions.c.schedule.is_distinct_from(versions.c.previous))
        )
        for row, previous in (
            await db.execute(
                bound_history(
                    query,
                    criteria,
                    cursor,
                    group="v",
                    key=ConfigRecord.config_ref,
                    ordered_at=ConfigRecord.saved_at,
                    event_at=ConfigRecord.saved_at,
                )
            )
        ).all():
            schedule = row.bundle["schedule"]
            kind = (
                "schedule_saved"
                if previous is None
                else (
                    "schedule_paused"
                    if previous["enabled"] and not schedule["enabled"]
                    else "schedule_resumed"
                    if not previous["enabled"] and schedule["enabled"]
                    else "schedule_changed"
                )
            )
            result.append(
                (
                    (row.saved_at, "v", row.config_ref),
                    HistoryItem(
                        id="v:" + row.config_ref,
                        kind=kind,
                        source=None,
                        result=None,
                        occurred_at=row.saved_at,
                        received_at=None,
                        time_quality="server",
                        config_ref=row.config_ref,
                        config_known=True,
                    ),
                )
            )
    query = select(ReportRecord).where(
        ReportRecord.kind.in_(("config_applied", "config_rejected")),
        ReportRecord.config_ref.in_(changed_refs()),
    )
    if criteria.result:
        if criteria.result != "rejected":
            return result
        query = query.where(ReportRecord.kind == "config_rejected")
    for row in (
        await db.scalars(
            bound_history(
                query,
                criteria,
                cursor,
                group="a",
                key=ReportRecord.event_id,
                ordered_at=ReportRecord.sort_at,
                event_at=ReportRecord.occurred_at,
                trusted_time=ReportRecord.body["time_quality"].as_string() != "unknown",
            )
        )
    ).all():
        result.append(
            (
                (row.sort_at, "a", row.event_id),
                HistoryItem(
                    id="a:" + row.event_id,
                    kind=row.kind,
                    source=None,
                    result="rejected" if row.kind == "config_rejected" else "applied",
                    reason=row.body["payload"].get("reason"),
                    occurred_at=row.occurred_at,
                    received_at=row.received_at,
                    time_quality=row.body["time_quality"],
                    config_ref=row.config_ref,
                    config_known=True,
                ),
            )
        )
    return result
