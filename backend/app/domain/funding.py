"""One optional income Entry reference, gated lookup and actual expense breakdown."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dashboard import REPORT_MONTHS, DashboardService, _periods, _relative_now
from app.domain.models import AuthSession, Entry, Tracker
from app.domain.reading import not_deleted, readable
from app.domain.tracker import EntryInvalid, EntryRead, _amount_in, _clear


async def lock_funding_parents(db: AsyncSession, tracker_id: UUID, source_id: UUID) -> None:
    source_tracker = (
        await db.execute(select(Entry.tracker_id).where(Entry.id == source_id))
    ).scalar_one_or_none()
    ids = sorted({tracker_id, *([source_tracker] if source_tracker else [])}, key=str)
    await db.execute(
        select(Tracker.id).where(Tracker.id.in_(ids)).order_by(Tracker.id).with_for_update()
    )


async def sources(db: AsyncSession, auth: AuthSession, ids: set[UUID]) -> dict[UUID, dict]:
    if not ids:
        return {}
    stmt = (
        select(Entry, Tracker)
        .join(Tracker, Entry.tracker_id == Tracker.id)
        .where(Entry.id.in_(ids), Tracker.direction == "in")
    )
    rows = await db.execute(not_deleted(readable(stmt, Tracker, auth), Entry))
    result = {}
    for entry, tracker in rows:
        try:
            amount = _amount_in(entry.amount)
            name = _clear(tracker.name)
            if amount is not None:
                result[entry.id] = dict(
                    id=str(entry.id),
                    tracker_id=str(tracker.id),
                    tracker_name=name,
                    occurred_at=entry.occurred_at.isoformat(),
                    amount=int(amount),
                    is_private=tracker.is_private,
                )
        except Exception:
            # No ciphertext, amount, name or hidden identity in an unavailable response.
            continue
    return result


async def validate_link(
    db: AsyncSession,
    auth: AuthSession,
    tracker: Tracker,
    amount: Decimal | None,
    entry_id: UUID | None,
    source_id: UUID,
) -> None:
    if source_id == entry_id or tracker.direction != "out" or amount is None:
        raise EntryInvalid("Chỉ khoản chi có số tiền mới gắn được nguồn thu.")
    found = await sources(db, auth, {source_id})
    if source_id not in found:
        raise EntryInvalid("Nguồn thu không còn khả dụng. Chọn lại nguồn hoặc không gắn nguồn.")


async def enrich(db: AsyncSession, auth: AuthSession, reads: list[EntryRead]) -> None:
    if not reads:
        return
    links = dict(
        (
            await db.execute(
                select(Entry.id, Entry.funding_entry_id).where(Entry.id.in_([r.id for r in reads]))
            )
        ).all()
    )
    available = await sources(db, auth, {value for value in links.values() if value})
    for row in reads:
        ref = links.get(row.id)
        row.funding = (
            {"status": "none"}
            if ref is None
            else {"status": "available", "source": available[ref]}
            if ref in available
            else {"status": "unavailable"}
        )


async def candidates(db: AsyncSession, auth: AuthSession, cursor: str | None, limit: int) -> dict:
    stmt = (
        select(Entry)
        .join(Tracker, Entry.tracker_id == Tracker.id)
        .where(Tracker.direction == "in", Entry.amount.is_not(None))
    )
    stmt = not_deleted(readable(stmt, Tracker, auth), Entry)
    if cursor:
        try:
            timestamp, identity = cursor.rsplit("|", 1)
            at, ident = datetime.fromisoformat(timestamp), UUID(identity)
            if at.tzinfo is None:
                raise ValueError
        except (ValueError, TypeError) as error:
            raise ValueError("Cursor nguồn thu không hợp lệ.") from error
        stmt = stmt.where(
            or_(Entry.occurred_at < at, and_(Entry.occurred_at == at, Entry.id < ident))
        )
    rows = list(
        (
            await db.execute(
                stmt.order_by(Entry.occurred_at.desc(), Entry.id.desc()).limit(limit + 1)
            )
        ).scalars()
    )
    page = rows[:limit]
    metadata = await sources(db, auth, {row.id for row in page})
    return {
        "items": [metadata[r.id] for r in page if r.id in metadata],
        "next_cursor": f"{page[-1].occurred_at.isoformat()}|{page[-1].id}"
        if len(rows) > limit and page
        else None,
    }


async def report(db: AsyncSession, auth: AuthSession, month: str, months: int) -> dict:
    if months not in REPORT_MONTHS:
        raise ValueError("Khoảng báo cáo phải là1,3,6hoặc12tháng.")
    period = _periods(month, _relative_now(), months)
    rows = (
        []
        if period.is_future
        else await DashboardService()._fetch_month(db, auth, period.period_start, period.period_end)
    )
    decoded = [(entry, tracker, *DashboardService._safe_amount(entry)) for entry, tracker in rows]
    available = await sources(
        db,
        auth,
        {
            e.funding_entry_id
            for e, t, a, bad in decoded
            if t.direction == "out" and e.funding_entry_id and a is not None and not bad
        },
    )
    buckets, total, income, corrupted = {}, Decimal(0), Decimal(0), 0
    for entry, tracker, amount, bad in decoded:
        corrupted += int(bad)
        if bad or amount is None:
            continue
        if tracker.direction != "out":
            income += amount
            continue
        total += amount
        ref = entry.funding_entry_id
        source = available.get(ref)
        key = str(ref) if source else "unavailable" if ref else "unlinked"
        bucket = buckets.setdefault(
            key,
            {"key": key, "source": source, "total": 0, "count": 0, "trackers": {}, "expenses": []},
        )
        bucket["total"] += int(amount)
        bucket["count"] += 1
        tracker_key = str(tracker.id)
        breakdown = bucket["trackers"].setdefault(
            tracker_key,
            {"tracker_id": tracker_key, "name": _clear(tracker.name), "total": 0, "count": 0},
        )
        breakdown["total"] += int(amount)
        breakdown["count"] += 1
        bucket["expenses"].append(
            {
                "id": str(entry.id),
                "tracker_name": breakdown["name"],
                "occurred_at": entry.occurred_at.isoformat(),
                "amount": int(amount),
            }
        )
    for bucket in buckets.values():
        bucket["trackers"] = sorted(
            bucket["trackers"].values(), key=lambda t: (-t["total"], t["tracker_id"])
        )
        bucket["expenses"].sort(key=lambda e: (e["occurred_at"], e["id"]), reverse=True)
        bucket["has_more"] = len(bucket["expenses"]) > 50
        bucket["expenses"] = bucket["expenses"][:50]
    return {
        "period_start": period.period_start,
        "period_end": period.period_end,
        "expense_total": int(total),
        "income_total": int(income),
        "net": int(income - total),
        "corrupted_entry_count": corrupted,
        "buckets": sorted(buckets.values(), key=lambda b: (-b["total"], b["key"])),
    }
