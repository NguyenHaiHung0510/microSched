"""Read-only occurrence projection. No receipt writes, historical prose or delivery fiction."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    Date,
    DateTime,
    Integer,
    String,
    case,
    cast,
    func,
    literal,
    select,
    tuple_,
    union_all,
)

from app.agent import crypto as mimi_crypto
from app.agent.models import MimiConversation, MimiNotificationDelivery, MimiNotificationIntent
from app.agent.notifications import copy_aad
from app.agent.service import _owner_id
from app.core.settings import get_settings
from app.domain.models import (
    CalendarEvent,
    OneShotReminder,
    ReminderDispatch,
    Subscription,
    Task,
    TaskItem,
    Tracker,
    TrackerReminderBatch,
    TrackerReminderBatchItem,
)
from app.domain.notification_content import public_text
from app.domain.one_shot import SOURCES, VN, source_open, source_title
from app.domain.one_shot_delivery import build_one_shot_payload
from app.domain.reading import can_see_private, readable

Origin = Literal["one_shot", "tracker_dispatch", "subscription_dispatch", "mimi_intent"]
Source = Literal["task", "event", "tracker", "annotation", "subscription", "mimi"]
Status = Literal[
    "pending",
    "sending",
    "sent",
    "missed",
    "needs_reschedule",
    "no_device",
    "failed",
    "cancelled",
    "exhausted",
    "accepted",
    "unknown",
    "retryable",
    "expired",
    "suppressed",
    "not_requested",
]


class HistoryFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: Origin | None = None
    source: Source | None = None
    status: Status | None = None
    handled: Literal["all", "unhandled"] = "all"
    day_from: date | None = None
    day_to: date | None = None


def _mimi_enabled():
    s = get_settings()
    return s.mimi_notifications_enabled and (
        not s.is_production or (s.mimi_real_chat_enabled and s.mimi_live_provider_enabled)
    )


def _fingerprint(auth, filters):
    value = [
        str(_owner_id(auth)),
        can_see_private(auth),
        _mimi_enabled(),
        filters.model_dump(mode="json"),
    ]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _signature(payload):
    s = get_settings()
    key = (s.oauth_state_secret or s.app_name).encode()
    return hmac.new(key, b"reminder-history-v1:" + payload, hashlib.sha256).hexdigest()


def _encode_cursor(row, fingerprint, cutoff):
    value = {
        "v": 1,
        "fp": fingerprint,
        "cutoff": cutoff.isoformat(),
        "last": [
            row["sort_day"].isoformat(),
            row["precision"],
            row["clock"].isoformat(),
            row["rank"],
            str(row["receipt_id"]),
        ],
    }
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=") + "." + _signature(raw)


def _decode_cursor(cursor, fingerprint, now):
    try:
        encoded, signature = cursor.split(".")
        raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        if not hmac.compare_digest(signature, _signature(raw)):
            raise ValueError()
        value = json.loads(raw)
        if set(value) != {"v", "fp", "cutoff", "last"} or value["v"] != 1:
            raise ValueError()
        if value["fp"] != fingerprint:
            raise ValueError()
        cutoff = datetime.fromisoformat(value["cutoff"])
        day, precision, clock, rank, identity = value["last"]
        clock = datetime.fromisoformat(clock)
        if cutoff.tzinfo is None or clock.tzinfo is None or cutoff > now:
            raise ValueError()
        if (
            type(precision) is not int
            or precision not in (0, 1)
            or type(rank) is not int
            or rank not in range(1, 5)
        ):
            raise ValueError()
        return cutoff, (date.fromisoformat(day), precision, clock, rank, UUID(identity))
    except ValueError, TypeError, KeyError, UnicodeError:
        raise HTTPException(422, "history_cursor_invalid_or_view_changed") from None


def _arm(origin, kind, row, source_id, at, on, basis, rank, *, state=None, accepted=None):
    # NULL sentinels are sort keys only, never fabricated occurrence timestamps in DTOs.
    instant = cast(at, DateTime(timezone=True))
    day = cast(on, Date)
    return select(
        literal(origin).label("origin"),
        literal(kind).label("source_kind"),
        row.id.label("receipt_id"),
        source_id.label("source_id"),
        instant.label("occurrence_at"),
        day.label("occurrence_on"),
        cast(basis, String).label("time_basis"),
        (state if state is not None else row.status).label("status"),
        row.created_at.label("recorded_at"),
        cast(accepted, DateTime(timezone=True)).label("accepted_at"),
        func.coalesce(day, date.min).label("sort_day"),
        case((instant.is_not(None), 1), else_=0).label("precision"),
        func.coalesce(instant, datetime(1970, 1, 1, tzinfo=UTC)).label("clock"),
        cast(literal(rank), Integer).label("rank"),
    )


def _projection(auth, now, cutoff):
    arms = []
    r = OneShotReminder
    at = case(((r.status == "cancelled") & (r.due_at > now), r.created_at), else_=r.due_at)
    basis = case(((r.status == "cancelled") & (r.due_at > now), "recorded_only"), else_="scheduled")
    for kind, (model, column) in SOURCES.items():
        q = _arm(
            "one_shot",
            kind,
            r,
            model.id,
            at,
            cast(func.timezone("Asia/Ho_Chi_Minh", at), Date),
            basis,
            1,
            accepted=r.sent_at,
        )
        q = readable(q.join(model, getattr(r, column) == model.id), model, auth)
        if kind == "event":
            q = q.where(CalendarEvent.is_hidden.is_(False))
        arms.append(
            q.where(
                r.created_at <= cutoff,
                (r.due_at <= now) | (r.attempt_count > 0) | r.status.not_in(("pending", "sending")),
            )
        )
    d, item, batch = ReminderDispatch, TrackerReminderBatchItem, TrackerReminderBatch
    batch_at = func.timezone("Asia/Ho_Chi_Minh", batch.occurrence_on + batch.reminder_time)
    q = _arm(
        "tracker_dispatch",
        "tracker",
        d,
        Tracker.id,
        batch_at,
        func.coalesce(batch.occurrence_on, d.dispatched_on),
        case((batch.id.is_not(None), "batch_schedule"), else_="dispatch_day"),
        2,
    )
    q = (
        q.join(Tracker, (d.subject_type == "tracker") & (d.subject_id == Tracker.id))
        .outerjoin(item, item.dispatch_id == d.id)
        .outerjoin(batch, batch.id == item.batch_id)
    )
    q = readable(q, Tracker, auth)
    arms.append(
        q.where(
            d.created_at <= cutoff,
            (
                (batch.id.is_(None) & (d.dispatched_on <= now.astimezone(VN).date()))
                | (batch_at <= now)
            )
            | (d.attempt_count > 0)
            | (d.status != "pending"),
        )
    )
    q = _arm(
        "subscription_dispatch",
        "subscription",
        d,
        Subscription.id,
        None,
        d.dispatched_on,
        literal("dispatch_day"),
        3,
    )
    q = q.join(
        Subscription, (d.subject_type == "subscription") & (d.subject_id == Subscription.id)
    ).join(Tracker, Subscription.tracker_id == Tracker.id)
    q = readable(q, Tracker, auth).where(Subscription.deleted_at.is_(None))
    arms.append(
        q.where(
            d.created_at <= cutoff,
            (d.dispatched_on <= now.astimezone(VN).date())
            | (d.attempt_count > 0)
            | (d.status != "pending"),
        )
    )
    if _mimi_enabled():
        i, c, delivery = MimiNotificationIntent, MimiConversation, MimiNotificationDelivery
        # A single scalar aggregate per intent; endpoints never multiply occurrences.
        priority = case(
            (delivery.state == "accepted", 7),
            (delivery.state == "unknown", 6),
            (delivery.state == "sending", 5),
            (delivery.state == "retryable", 4),
            (delivery.state == "pending", 3),
            (delivery.state == "expired", 2),
            else_=1,
        )
        states = (
            select(delivery.intent_id, func.max(priority).label("priority"))
            .group_by(delivery.intent_id)
            .subquery()
        )
        state = case(
            *[
                (states.c.priority == k, v)
                for k, v in [
                    (7, "accepted"),
                    (6, "unknown"),
                    (5, "sending"),
                    (4, "retryable"),
                    (3, "pending"),
                    (2, "expired"),
                    (1, "suppressed"),
                ]
            ],
            else_="not_requested",
        )
        q = _arm(
            "mimi_intent",
            "mimi",
            i,
            c.id,
            i.created_at,
            cast(func.timezone("Asia/Ho_Chi_Minh", i.created_at), Date),
            literal("intent_created"),
            4,
            state=state,
        )
        q = q.join(c, i.conversation_id == c.id).outerjoin(states, states.c.intent_id == i.id)
        arms.append(
            q.where(
                i.owner_id == _owner_id(auth),
                c.owner_id == _owner_id(auth),
                c.is_private.is_(False),
                c.sensitivity == "standard",
                i.created_at <= cutoff,
            )
        )
    return union_all(*arms).subquery("occurrences")


async def _hydrate(db, auth, rows):
    sources = {}
    private_sources = {}
    for kind, model in [(k, v[0]) for k, v in SOURCES.items()] + [("subscription", Subscription)]:
        ids = [r["source_id"] for r in rows if r["source_kind"] == kind]
        if not ids:
            continue
        q = select(model).where(model.id.in_(ids))
        if kind == "subscription":
            q = select(Subscription, Tracker.is_private).where(Subscription.id.in_(ids))
            q = readable(
                q.join(Tracker, Subscription.tracker_id == Tracker.id), Tracker, auth
            ).where(Subscription.deleted_at.is_(None))
        else:
            q = readable(q, model, auth)
            if kind == "event":
                q = q.where(model.is_hidden.is_(False))
        if kind == "subscription":
            for source, private in (await db.execute(q)).all():
                sources[(kind, source.id)] = source
                private_sources[(kind, source.id)] = private
        else:
            sources.update({(kind, s.id): s for s in (await db.scalars(q)).all()})
    task_ids = [sid for kind, sid in sources if kind == "task"]
    checklist = {}
    if task_ids:
        children = readable(
            select(TaskItem)
            .join(Task, TaskItem.task_id == Task.id)
            .where(TaskItem.task_id.in_(task_ids), TaskItem.deleted_at.is_(None)),
            Task,
            auth,
        ).order_by(TaskItem.position, TaskItem.id)
        for child in (await db.scalars(children)).all():
            checklist.setdefault(child.task_id, []).append(
                ("☑ " if child.is_completed else "☐ ") + public_text(child.content)
            )
    shot_ids = [r["receipt_id"] for r in rows if r["origin"] == "one_shot"]
    shots = (
        {
            s.id: s
            for s in (
                await db.scalars(select(OneShotReminder).where(OneShotReminder.id.in_(shot_ids)))
            ).all()
        }
        if shot_ids
        else {}
    )
    dispatch_ids = [
        r["receipt_id"]
        for r in rows
        if r["origin"] in ("tracker_dispatch", "subscription_dispatch")
    ]
    dispatches = (
        {
            s.id: s
            for s in (
                await db.scalars(
                    select(ReminderDispatch).where(ReminderDispatch.id.in_(dispatch_ids))
                )
            ).all()
        }
        if dispatch_ids
        else {}
    )
    mimi_ids = [r["receipt_id"] for r in rows if r["origin"] == "mimi_intent"]
    mimi = {}
    mimi_attempts = {}
    if mimi_ids:
        q = (
            select(MimiNotificationIntent, MimiConversation)
            .join(MimiConversation)
            .where(
                MimiNotificationIntent.id.in_(mimi_ids),
                MimiNotificationIntent.owner_id == _owner_id(auth),
                MimiConversation.owner_id == _owner_id(auth),
                MimiConversation.is_private.is_(False),
                MimiConversation.sensitivity == "standard",
            )
        )
        mimi = {i.id: (i, c) for i, c in (await db.execute(q)).all()}
        q = (
            select(
                MimiNotificationDelivery.intent_id, func.max(MimiNotificationDelivery.attempt_count)
            )
            .where(MimiNotificationDelivery.intent_id.in_(mimi_ids))
            .group_by(MimiNotificationDelivery.intent_id)
        )
        mimi_attempts = dict((await db.execute(q)).all())
    output = []
    for row in rows:
        kind, rid = row["source_kind"], row["receipt_id"]
        record = {
            k: row[k]
            for k in (
                "origin",
                "source_kind",
                "occurrence_at",
                "occurrence_on",
                "time_basis",
                "status",
                "recorded_at",
                "accepted_at",
            )
        }
        record.update(
            occurrence_ref={"origin": row["origin"], "id": rid},
            source_ref={"kind": kind, "id": row["source_id"]},
            can_open=True,
            can_handle=False,
            handled_at=None,
            is_private=False,
            scheduled_at=None,
            last_attempt_at=None,
            attempt_count=0,
            time_precision="instant"
            if row["occurrence_at"] is not None
            else ("day" if row["occurrence_on"] is not None else "unknown"),
        )
        if kind == "mimi":
            if rid not in mimi:
                raise HTTPException(409, "history_view_changed")
            intent, conversation = mimi[rid]
            copy = json.loads(
                mimi_crypto.open_content(
                    mimi_crypto.unwrap_dek(conversation.dek_wrapped),
                    intent.copy_ciphertext,
                    aad=copy_aad(intent),
                )
            )
            record.update(
                title=copy["title"],
                body=copy["body"],
                content_basis="intent_snapshot",
                attention_kind=intent.kind,
                read_at=intent.read_at,
                attempt_count=mimi_attempts.get(rid, 0),
                attempt_basis="maximum_per_device_receipt",
                delivery_basis="at_least_one_provider_accepted;other_targets_may_differ"
                if row["status"] == "accepted"
                else "aggregate_device_receipt_states",
                expires_at=intent.expires_at,
            )
        else:
            source = sources.get((kind, row["source_id"]))
            if source is None:
                raise HTTPException(409, "history_view_changed")
            record["can_open"] = source_open(source) if kind in SOURCES else True
            record["is_private"] = private_sources.get(
                (kind, source.id), getattr(source, "is_private", False)
            )
            if row["origin"] == "one_shot":
                receipt = shots.get(rid)
                if receipt is None:
                    raise HTTPException(409, "history_view_changed")
                copy = build_one_shot_payload(receipt, source, checklist.get(source.id, ()))
                record.update(
                    title=source_title(source), body=copy["body"], scheduled_at=receipt.due_at
                )
                # Push abstracts private; unlocked history instead uses current live prose.
                if record["is_private"]:
                    prose = public_text(
                        getattr(source, "body_md", None)
                        or getattr(source, "note_md", None)
                        or getattr(source, "reminder_text", None)
                    )
                    record["body"] = "\n".join(
                        part for part in [prose, *checklist.get(source.id, ())] if part
                    )
            else:
                receipt = dispatches.get(rid)
                if receipt is None:
                    raise HTTPException(409, "history_view_changed")
                record.update(
                    title=public_text(source.name),
                    body=public_text(
                        source.note_md if kind == "subscription" else source.reminder_text
                    ),
                    scheduled_at=row["occurrence_at"]
                    if row["time_basis"] == "batch_schedule"
                    else None,
                )
            record.update(
                attempt_count=receipt.attempt_count,
                last_attempt_at=receipt.last_attempt_at,
                content_basis="current_source",
            )
        output.append(record)
    return output


async def list_history(db, auth, filters: HistoryFilter, *, limit=50, cursor=None, now=None):
    now = now or datetime.now(UTC)
    if not 1 <= limit <= 100 or (
        filters.day_from and filters.day_to and filters.day_from > filters.day_to
    ):
        raise HTTPException(422, "history_filter_invalid")
    fingerprint = _fingerprint(auth, filters)
    cutoff, last = _decode_cursor(cursor, fingerprint, now) if cursor else (now, None)
    p = _projection(auth, now, cutoff)
    keys = [p.c.sort_day, p.c.precision, p.c.clock, p.c.rank, p.c.receipt_id]
    q = select(p)
    for name, value in [
        ("origin", filters.origin),
        ("source_kind", filters.source),
        ("status", filters.status),
    ]:
        if value is not None:
            q = q.where(p.c[name] == value)
    if filters.day_from:
        q = q.where(p.c.occurrence_on >= filters.day_from)
    if filters.day_to:
        q = q.where(p.c.occurrence_on <= filters.day_to)
    if last:
        q = q.where(tuple_(*keys) < tuple_(*last))
    rows = (
        (await db.execute(q.order_by(*(k.desc() for k in keys)).limit(limit + 1))).mappings().all()
    )
    page = rows[:limit]
    items = await _hydrate(db, auth, page)
    if fingerprint != _fingerprint(auth, filters):
        raise HTTPException(409, "history_view_changed")
    has_more = len(rows) > limit
    return {
        "items": items,
        "has_more": has_more,
        "next_cursor": _encode_cursor(page[-1], fingerprint, cutoff) if has_more else None,
        "view_opened_at": cutoff,
        "total": None,
        "private_notice": None
        if can_see_private(auth)
        else {"title": "Nhắc việc riêng tư", "body": "Nội dung được ẩn"},
        "coverage": {
            "history": "existing_durable_receipts_only",
            "content": "current_source_except_mimi_intent_snapshot",
            "time": "occurrence_not_device_delivery;legacy_dispatch_day_only",
            "private": "locked_rows_omitted;constant_notice_not_inventory",
            "unavailable": "hidden_deleted_or_orphan_sources_omitted",
            "handled": "not_implemented",
            "pagination": "keyset_browsing_bookmark_not_transaction_snapshot",
            "supported_sources": ["task", "event", "tracker", "annotation", "subscription", "mimi"],
        },
    }
