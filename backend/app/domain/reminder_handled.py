"""Owner-scoped handled state and exact prepared bulk; no source-side acknowledgements."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool, field_validator
from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert

from app.agent.models import MimiConversation, MimiNotificationIntent
from app.agent.service import _owner_id
from app.domain.models import (
    AuthSession,
    CalendarEvent,
    DayAnnotation,
    OneShotReminder,
    ReminderDispatch,
    ReminderHandledBatch,
    ReminderOccurrenceHandled,
    Subscription,
    Task,
    Tracker,
)
from app.domain.reminder_history import HistoryFilter, Origin, _projection, filtered_query

COLUMN = {
    "one_shot": "one_shot_id",
    "tracker_dispatch": "dispatch_id",
    "subscription_dispatch": "dispatch_id",
    "mimi_intent": "mimi_intent_id",
}
RECEIPT = {
    "one_shot": OneShotReminder,
    "tracker_dispatch": ReminderDispatch,
    "subscription_dispatch": ReminderDispatch,
    "mimi_intent": MimiNotificationIntent,
}
SOURCE = {
    "task": Task,
    "event": CalendarEvent,
    "annotation": DayAnnotation,
    "tracker": Tracker,
    "subscription": Subscription,
    "mimi": MimiConversation,
}


class DesiredHandled(BaseModel):
    model_config = ConfigDict(extra="forbid")
    handled: StrictBool

    @field_validator("handled")
    @classmethod
    def desired_true(cls, value):
        if value is not True:
            raise ValueError("Only desired handled=true is supported")
        return value


class OccurrenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: Origin
    id: UUID


class PrepareHandled(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: UUID
    filter: HistoryFilter
    selected_refs: list[OccurrenceRef] | None = None

    @field_validator("batch_id")
    @classmethod
    def uuid_version(cls, value):
        if value.version != 7:
            raise ValueError("UUIDv7 batch identity required")
        return value


async def current_auth(db, auth):
    if auth.id:
        owner = _owner_id(auth)
        live = (
            await db.scalars(
                select(AuthSession)
                .where(AuthSession.id == auth.id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if live is None or live.expires_at <= datetime.now(UTC) or _owner_id(live) != owner:
            raise HTTPException(401, "Not authenticated")
        auth.private_until = live.private_until
    return auth


def ref_key(ref):
    return (ref["origin"], UUID(str(ref["id"])))


async def visible_targets(db, auth, refs, *, lock=False):
    if not refs:
        return []
    keys = sorted(set(ref_key(ref) for ref in refs), key=lambda r: (r[0], str(r[1])))
    now = datetime.now(UTC)
    p = _projection(auth, now, now)
    q = select(p).where(tuple_(p.c.origin, p.c.receipt_id).in_(keys))
    rows = (await db.execute(q)).mappings().all()
    if len(rows) != len(keys):
        return None
    if lock:
        # Global deterministic source-parent order, then receipt order; no lock while user confirms.
        sources = {(row["source_kind"], row["source_id"]) for row in rows}
        for kind, identity in list(sources):
            if kind == "subscription":
                parent = await db.scalar(
                    select(Subscription.tracker_id).where(Subscription.id == identity)
                )
                if parent:
                    sources.add(("tracker", parent))
        for kind, identity in sorted(
            sources, key=lambda r: (r[0] != "tracker", SOURCE[r[0]].__tablename__, str(r[1]))
        ):
            await db.execute(
                select(SOURCE[kind].id).where(SOURCE[kind].id == identity).with_for_update()
            )
        for origin, identity in keys:
            model = RECEIPT[origin]
            await db.execute(select(model.id).where(model.id == identity).with_for_update())
        # Re-run current disclosure gates after locks. A hidden/deleted member aborts the whole set.
        rows = (await db.execute(q)).mappings().all()
        if len(rows) != len(keys):
            return None
    return rows


async def insert_handled(db, owner, refs, at):
    if not refs:
        return 0
    values = [
        {"owner_id": owner, COLUMN[ref["origin"]]: UUID(str(ref["id"])), "handled_at": at}
        for ref in refs
    ]
    # Separate shapes because each typed FK is nullable and exactly one must be populated.
    inserted = 0
    for column in sorted(set(COLUMN[ref["origin"]] for ref in refs)):
        selected = [v for v in values if column in v]
        result = await db.execute(
            insert(ReminderOccurrenceHandled)
            .values(selected)
            .on_conflict_do_nothing()
            .returning(ReminderOccurrenceHandled.id)
        )
        inserted += len(result.all())
    return inserted


async def mark_handled(db, auth, origin: Origin, receipt_id: UUID):
    await current_auth(db, auth)
    refs = [{"origin": origin, "id": str(receipt_id)}]
    if await visible_targets(db, auth, refs, lock=True) is None:
        raise HTTPException(404, "History occurrence unavailable")
    owner = _owner_id(auth)
    await insert_handled(db, owner, refs, datetime.now(UTC))
    model = ReminderOccurrenceHandled
    row = (
        await db.scalars(
            select(model).where(
                model.owner_id == owner, getattr(model, COLUMN[origin]) == receipt_id
            )
        )
    ).one()
    return {"occurrence_ref": refs[0], "handled": True, "handled_at": row.handled_at}


def filter_digest(filters, selected_refs=None):
    normalized = filters.model_dump(mode="json")
    if selected_refs is not None:
        normalized["selected_refs"] = sorted(
            [
                {"origin": origin, "id": str(identity)}
                for origin, identity in {ref_key(ref.model_dump()) for ref in selected_refs}
            ],
            key=lambda ref: (ref["origin"], ref["id"]),
        )
    return normalized, hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def batch_response(db, auth, row):
    authorized = await visible_targets(db, auth, row.target_refs) is not None
    if not authorized:
        if row.committed_at:
            return {
                "id": row.id,
                "committed": True,
                "committed_at": row.committed_at,
                "scope_visible": False,
            }
        raise HTTPException(409, "history_selection_stale")
    return {
        "id": row.id,
        "committed": row.committed_at is not None,
        "committed_at": row.committed_at,
        "scope_visible": True,
        "selected_count": row.selected_count,
        "filter": row.normalized_filter,
        "fingerprint": row.fingerprint,
        "cutoff": row.cutoff,
        "expires_at": row.expires_at,
        "result": row.result,
    }


async def prepare_batch(db, auth, payload: PrepareHandled, *, now=None):
    await current_auth(db, auth)
    owner = _owner_id(auth)
    filters = payload.filter
    if filters.day_from and filters.day_to and filters.day_from > filters.day_to:
        raise HTTPException(422, "history_filter_invalid")
    normalized, fingerprint = filter_digest(filters, payload.selected_refs)
    existing = await db.get(ReminderHandledBatch, payload.batch_id)
    if existing is not None:
        if existing.owner_id != owner:
            raise HTTPException(404, "History batch unavailable")
        if existing.fingerprint != fingerprint:
            raise HTTPException(409, "history_batch_identity_reused")
        return await batch_response(db, auth, existing)
    cutoff = now or datetime.now(UTC)
    projection, query = filtered_query(auth, filters, cutoff, cutoff)
    if payload.selected_refs is not None:
        selected = [ref_key(ref.model_dump()) for ref in payload.selected_refs]
        if await visible_targets(db, auth, normalized["selected_refs"]) is None:
            raise HTTPException(409, "history_selection_stale")
        query = query.where(tuple_(projection.c.origin, projection.c.receipt_id).in_(selected))
    # One SQL statement snapshots ALL authorized unhandled targets, not a loaded page.
    rows = (
        (await db.execute(query.where(ReminderOccurrenceHandled.handled_at.is_(None))))
        .mappings()
        .all()
    )
    refs = sorted(
        [{"origin": r["origin"], "id": str(r["receipt_id"])} for r in rows],
        key=lambda r: (r["origin"], r["id"]),
    )
    values = dict(
        id=payload.batch_id,
        owner_id=owner,
        normalized_filter=normalized,
        fingerprint=fingerprint,
        target_refs=refs,
        selected_count=len(refs),
        cutoff=cutoff,
        expires_at=cutoff + timedelta(minutes=15),
    )
    await db.execute(insert(ReminderHandledBatch).values(**values).on_conflict_do_nothing())
    row = (
        await db.scalars(
            select(ReminderHandledBatch)
            .where(ReminderHandledBatch.id == payload.batch_id)
            .with_for_update()
        )
    ).one()
    if row.owner_id != owner:
        raise HTTPException(404, "History batch unavailable")
    if row.fingerprint != fingerprint:
        raise HTTPException(409, "history_batch_identity_reused")
    return await batch_response(db, auth, row)


async def commit_batch(db, auth, batch_id, *, now=None):
    await current_auth(db, auth)
    row = (
        await db.scalars(
            select(ReminderHandledBatch)
            .where(
                ReminderHandledBatch.id == batch_id,
                ReminderHandledBatch.owner_id == _owner_id(auth),
            )
            .with_for_update()
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "History batch unavailable")
    if row.committed_at:
        return await batch_response(db, auth, row)
    clock = now or datetime.now(UTC)
    if row.expires_at <= clock:
        raise HTTPException(409, "history_batch_expired")
    if await visible_targets(db, auth, row.target_refs, lock=True) is None:
        raise HTTPException(409, "history_selection_stale")
    new = await insert_handled(db, row.owner_id, row.target_refs, clock)
    row.committed_at = clock
    row.result = {
        "selected_count": row.selected_count,
        "new_count": new,
        "already_count": row.selected_count - new,
    }
    db.add(row)
    await db.flush()
    return await batch_response(db, auth, row)
