"""Durable STANDARD in-app attention and explicit device Web Push opt-in."""

from __future__ import annotations

import asyncio
import json
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.agent import crypto
from app.agent.models import (
    MimiChangeSet,
    MimiConversation,
    MimiDevicePreference,
    MimiEvent,
    MimiMessage,
    MimiNotificationDelivery,
    MimiNotificationIntent,
    MimiRun,
)
from app.core.settings import get_settings
from app.domain.models import PushSubscription
from app.domain.push import ProviderWorkTracker, send_push_detailed

TTL = timedelta(minutes=45)
BACKOFF = (30, 120, 600)
WAKE = "mimi_attention_wake"
_dispatcher = None


def visible_text(value: str, limit: int) -> str:
    value = re.sub(r"[\x00-\x1f\x7f]", " ", value)
    value = re.sub(r"[`*_>#]", "", value)
    value = " ".join(value.split())
    return value[:limit]


def copy_aad(intent):
    return f"mimi-attention:{intent.conversation_id}:{intent.id}:copy"


async def queue_completion(db: AsyncSession, run_id: UUID, sequence: int, kind: str):
    if not get_settings().mimi_notifications_enabled:
        return
    run = await db.get(MimiRun, run_id)
    conversation = await db.get(MimiConversation, run.conversation_id)
    if conversation.sensitivity != "standard" or conversation.is_private:
        return
    if kind not in {"run.terminal", "change_set.ready"}:
        return
    approval = kind == "change_set.ready"
    if not approval and run.state != "completed":
        return
    dek = crypto.unwrap_dek(conversation.dek_wrapped)
    message = (
        await db.scalars(
            select(MimiMessage)
            .where(MimiMessage.run_id == run_id, MimiMessage.role == "assistant")
            .order_by(MimiMessage.sequence.desc())
            .limit(1)
        )
    ).first()
    if message is None:
        return
    answer = crypto.open_content(
        dek,
        message.content_ciphertext,
        aad=crypto.message_aad(conversation.id, message.sequence, message.role),
    )
    title = (
        crypto.open_content(
            dek, conversation.title_ciphertext, aad=crypto.conversation_title_aad(conversation.id)
        )
        if conversation.title_ciphertext
        else "Mimi"
    )
    expires = datetime.now(UTC) + TTL
    if approval:
        change = (
            await db.scalars(select(MimiChangeSet).where(MimiChangeSet.run_id == run_id))
        ).one_or_none()
        if change is None or change.state != "pending" or change.expires_at <= datetime.now(UTC):
            return
        expires = min(expires, change.expires_at)
        answer = "Chờ bạn duyệt, chưa áp dụng. " + answer
    source = (
        await db.scalars(
            select(MimiEvent).where(MimiEvent.run_id == run_id, MimiEvent.sequence == sequence)
        )
    ).one()
    if await db.scalar(
        select(MimiNotificationIntent.id).where(
            MimiNotificationIntent.event_id == source.id,
            MimiNotificationIntent.kind == ("approval_ready" if approval else "completed"),
        )
    ):
        return
    intent = MimiNotificationIntent(
        id=uuid7(),
        owner_id=conversation.owner_id,
        conversation_id=conversation.id,
        run_id=run_id,
        event_id=source.id,
        kind="approval_ready" if approval else "completed",
        locator=secrets.token_urlsafe(24),
        expires_at=expires,
        copy_ciphertext="mimi:v1:pending",
    )
    intent.copy_ciphertext = crypto.seal_content(
        dek,
        json.dumps(
            {"title": visible_text("Mimi · " + title, 80), "body": visible_text(answer, 240)},
            ensure_ascii=False,
        ),
        aad=copy_aad(intent),
    )
    db.add(intent)
    await db.flush()
    preferences = (
        await db.scalars(
            select(MimiDevicePreference)
            .where(
                MimiDevicePreference.owner_id == conversation.owner_id,
                MimiDevicePreference.enabled.is_(True),
            )
            .order_by(MimiDevicePreference.id)
            .limit(100)
        )
    ).all()
    db.add_all(
        [MimiNotificationDelivery(intent_id=intent.id, preference_id=p.id) for p in preferences]
    )
    db.info[WAKE] = True


@event.listens_for(Session, "after_commit")
def post_commit_wake(session):
    if session.info.pop(WAKE, False) and _dispatcher is not None:
        _dispatcher.wake.set()


@event.listens_for(Session, "after_rollback")
def clear_rollback_wake(session):
    session.info.pop(WAKE, None)


class DevicePreferenceProof(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subscription_id: UUID
    endpoint: str = Field(min_length=1, max_length=4096)
    p256dh: str = Field(min_length=1, max_length=1024)
    auth: str = Field(min_length=1, max_length=1024)


class DevicePreferenceChange(DevicePreferenceProof):
    enabled: bool
    expected_revision: int | None = Field(default=None, ge=1)


async def _proved_subscription(db, payload, *, lock=False):
    query = select(PushSubscription).where(PushSubscription.id == payload.subscription_id)
    if lock:
        query = query.with_for_update()
    sub = (await db.scalars(query)).one_or_none()
    if sub is None or not (
        secrets.compare_digest(sub.endpoint, payload.endpoint)
        and secrets.compare_digest(sub.p256dh, payload.p256dh)
        and secrets.compare_digest(sub.auth, payload.auth)
    ):
        raise HTTPException(404, "Mimi device not found")
    return sub


async def read_preference(db, owner_id, payload: DevicePreferenceProof):
    """Prove the device without creating consent or advancing its revision."""
    sub = await _proved_subscription(db, payload)
    pref = (
        await db.scalars(
            select(MimiDevicePreference).where(MimiDevicePreference.subscription_id == sub.id)
        )
    ).one_or_none()
    if pref is not None and pref.owner_id != owner_id:
        raise HTTPException(404, "Mimi device not found")
    return {
        "subscription_id": str(sub.id),
        "enabled": pref.enabled if pref is not None else False,
        "revision": pref.revision if pref is not None else None,
        "registered": pref is not None,
    }


async def set_preference(db, owner_id, payload):
    sub = await _proved_subscription(db, payload, lock=True)
    pref = (
        await db.scalars(
            select(MimiDevicePreference)
            .where(MimiDevicePreference.subscription_id == sub.id)
            .with_for_update()
        )
    ).one_or_none()
    if pref is None:
        if payload.expected_revision is not None:
            raise HTTPException(409, "mimi_device_preference_stale")
        pref = MimiDevicePreference(
            owner_id=owner_id, subscription_id=sub.id, enabled=payload.enabled
        )
        db.add(pref)
    else:
        if pref.owner_id != owner_id:
            raise HTTPException(404, "Mimi device not found")
        if pref.revision != payload.expected_revision:
            raise HTTPException(409, "mimi_device_preference_stale")
        pref.enabled = payload.enabled
        pref.revision += 1
    await db.flush()
    return {"subscription_id": str(sub.id), "enabled": pref.enabled, "revision": pref.revision}


async def list_attention(db, owner_id):
    rows = (
        await db.scalars(
            select(MimiNotificationIntent)
            .where(MimiNotificationIntent.owner_id == owner_id)
            .order_by(MimiNotificationIntent.created_at.desc())
            .limit(50)
        )
    ).all()
    output = []
    for r in rows:
        conversation = await db.get(MimiConversation, r.conversation_id)
        if (
            conversation is None
            or conversation.owner_id != owner_id
            or conversation.is_private
            or conversation.sensitivity != "standard"
        ):
            continue
        copy = json.loads(
            crypto.open_content(
                crypto.unwrap_dek(conversation.dek_wrapped), r.copy_ciphertext, aad=copy_aad(r)
            )
        )
        output.append(
            {
                **copy,
                "id": r.id,
                "conversation_id": r.conversation_id,
                "run_id": r.run_id,
                "kind": r.kind,
                "unread": r.read_at is None,
                "expires_at": r.expires_at,
            }
        )
    return output


async def acknowledge(db, owner_id, intent_id):
    row = (
        await db.scalars(
            select(MimiNotificationIntent)
            .where(
                MimiNotificationIntent.id == intent_id, MimiNotificationIntent.owner_id == owner_id
            )
            .with_for_update()
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Mimi attention not found")
    row.read_at = datetime.now(UTC)
    await db.flush()
    return {"id": row.id, "unread": False}


async def resolve_locator(db, owner_id, locator):
    row = (
        await db.scalars(
            select(MimiNotificationIntent)
            .join(MimiConversation, MimiNotificationIntent.conversation_id == MimiConversation.id)
            .where(
                MimiNotificationIntent.locator == locator,
                MimiNotificationIntent.owner_id == owner_id,
                MimiConversation.owner_id == owner_id,
                MimiConversation.sensitivity == "standard",
                MimiConversation.is_private.is_(False),
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Mimi attention not found")
    return {
        "conversation_id": str(row.conversation_id),
        "run_id": str(row.run_id),
        "path": "/mimi",
        "kind": row.kind,
        "expired": row.expires_at <= datetime.now(UTC),
    }


async def preview_sources_current(db, conversation, run, change):
    """Read-only suppression; never execute/confirm or invalidate a change set."""
    from app.agent.contracts import ChangeOperation
    from app.agent.task_collection import COLLECTION_TOOL, PreparedCollection, digest, snapshot
    from app.domain.models import OneShotReminder, Task, TaskItem
    from app.domain.one_shot import ACTIVE

    dek = crypto.unwrap_dek(conversation.dek_wrapped)
    try:
        operation = ChangeOperation.model_validate(
            json.loads(
                crypto.open_content(
                    dek,
                    change.operation_ciphertext,
                    aad=crypto.change_set_aad(conversation.id, change.id),
                )
            )
        )
        if operation.tool == COLLECTION_TOOL:
            plan = PreparedCollection.model_validate(operation.args)
            for entry in plan.entries:
                task = (
                    await db.scalars(
                        select(Task)
                        .where(Task.id == entry.id)
                        .execution_options(populate_existing=True)
                    )
                ).one_or_none()
                if entry.before is None:
                    if task is not None:
                        return False
                    continue
                if task is None or task.is_private:
                    return False
                children = (
                    await db.scalars(
                        select(TaskItem)
                        .where(TaskItem.task_id == entry.id)
                        .execution_options(populate_existing=True)
                    )
                ).all()
                reminder = (
                    await db.scalars(
                        select(OneShotReminder)
                        .where(
                            OneShotReminder.task_id == entry.id, OneShotReminder.status.in_(ACTIVE)
                        )
                        .execution_options(populate_existing=True)
                    )
                ).one_or_none()
                if digest(snapshot(task, children, reminder)) != digest(entry.before):
                    return False
                if entry.reminder_effect["action"] == "configure" and (
                    datetime.fromisoformat(entry.reminder_effect["due_at"]) <= datetime.now(UTC)
                ):
                    return False
            return True
        for key, expected in run.source_versions.items():
            if not isinstance(key, str) or not key.startswith("task:"):
                return False
            task = (
                await db.scalars(
                    select(Task)
                    .where(Task.id == UUID(key[5:]))
                    .execution_options(populate_existing=True)
                )
            ).one_or_none()
            if (
                task is None
                or task.is_private
                or task.deleted_at is not None
                or task.updated_at.isoformat() != expected
            ):
                return False
        return True
    except ValueError, KeyError, TypeError:
        return False


async def eligible_delivery(db, intent, pref):
    conversation = await db.get(MimiConversation, intent.conversation_id)
    if (
        not pref.enabled
        or pref.owner_id != intent.owner_id
        or conversation is None
        or conversation.owner_id != intent.owner_id
        or conversation.is_private
        or conversation.sensitivity != "standard"
        or intent.expires_at <= datetime.now(UTC)
    ):
        return False
    run = await db.get(MimiRun, intent.run_id)
    if run is None:
        return False
    if intent.kind == "approval_ready":
        change = (
            await db.scalars(select(MimiChangeSet).where(MimiChangeSet.run_id == run.id))
        ).one_or_none()
        return bool(
            change
            and change.state == "pending"
            and change.expires_at > datetime.now(UTC)
            and conversation.generation == run.generation + 1
            and await preview_sources_current(db, conversation, run, change)
        )
    return bool(run and run.state == "completed")


class NotificationDispatcher:
    def __init__(self, factory, send=send_push_detailed):
        self.factory = factory
        self.send = send
        self.wake = asyncio.Event()
        self.stop_requested = False
        self.tracker = ProviderWorkTracker()
        self.task = None
        self.lock_db = None

    async def start(self):
        global _dispatcher
        self.lock_db = self.factory()
        locked = await self.lock_db.scalar(select(func.pg_try_advisory_lock(7860086001)))
        if not locked:
            await self.lock_db.close()
            self.lock_db = None
            return
        _dispatcher = self
        async with self.factory() as db:
            # Prior process may have sent before crash. Never retry its ambiguous send.
            rows = (
                await db.scalars(
                    select(MimiNotificationDelivery)
                    .where(MimiNotificationDelivery.state == "sending")
                    .limit(1000)
                    .with_for_update()
                )
            ).all()
            for r in rows:
                r.state = "unknown"
                r.last_error = "process_restart_after_dispatch"
            await db.commit()
        self.wake.set()
        self.task = asyncio.create_task(self.run(), name="mimi-attention-dispatcher")

    async def stop(self):
        global _dispatcher
        self.stop_requested = True
        self.wake.set()
        if self.task:
            await self.task
        # Keep advisory ownership until real shielded send threads finish.
        await self.tracker.wait_for_idle(None)
        if self.lock_db:
            await self.lock_db.execute(select(func.pg_advisory_unlock(7860086001)))
            await self.lock_db.close()
        if _dispatcher is self:
            _dispatcher = None

    async def drain_once(self):
        async with self.factory() as db:
            ids = (
                await db.scalars(
                    select(MimiNotificationDelivery.id)
                    .where(
                        MimiNotificationDelivery.state.in_(["pending", "retryable"]),
                        MimiNotificationDelivery.next_at <= datetime.now(UTC),
                    )
                    .order_by(MimiNotificationDelivery.next_at, MimiNotificationDelivery.id)
                    .limit(1000)
                )
            ).all()
        for did in ids:
            if self.stop_requested:
                break
            await self.deliver(did)
        async with self.factory() as db:
            return await db.scalar(
                select(func.min(MimiNotificationDelivery.next_at)).where(
                    MimiNotificationDelivery.state.in_(["pending", "retryable"])
                )
            )

    async def run(self):
        while not self.stop_requested:
            self.wake.clear()
            next_at = await self.drain_once()
            if self.stop_requested:
                break
            delay = max(0, (next_at - datetime.now(UTC)).total_seconds()) if next_at else None
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=delay)
            except TimeoutError:
                pass

    async def deliver(self, did):
        async with self.factory() as db:
            row = (
                await db.scalars(
                    select(MimiNotificationDelivery)
                    .where(MimiNotificationDelivery.id == did)
                    .with_for_update()
                )
            ).one_or_none()
            if row is None or row.state not in {"pending", "retryable"}:
                return
            intent = await db.get(MimiNotificationIntent, row.intent_id)
            pref = await db.get(MimiDevicePreference, row.preference_id)
            if intent is None or pref is None or not await eligible_delivery(db, intent, pref):
                row.state = "suppressed"
                await db.commit()
                return
            sub = await db.get(PushSubscription, pref.subscription_id)
            if sub is None:
                row.state = "suppressed"
                await db.commit()
                return
            conversation = await db.get(MimiConversation, intent.conversation_id)
            copy = json.loads(
                crypto.open_content(
                    crypto.unwrap_dek(conversation.dek_wrapped),
                    intent.copy_ciphertext,
                    aad=copy_aad(intent),
                )
            )
            payload = {
                **copy,
                "url": "/mimi?attention=" + intent.locator,
                "tag": "mimi-" + str(intent.id),
            }
            row.state = "sending"
            row.attempt_count += 1
            attempt = row.attempt_count
            await db.commit()
            try:
                outcome = await self.send(
                    sub,
                    payload,
                    provider_work_tracker=self.tracker,
                    timeout_seconds=20,
                    ttl_seconds=max(
                        1, int((intent.expires_at - datetime.now(UTC)).total_seconds())
                    ),
                )
            except Exception:
                # The send may already have reached the service; never retry it.
                outcome = "unknown"
        async with self.factory() as db:
            row = (
                await db.scalars(
                    select(MimiNotificationDelivery)
                    .where(MimiNotificationDelivery.id == did)
                    .with_for_update()
                )
            ).one_or_none()
            if row is None or row.state != "sending" or row.attempt_count != attempt:
                return
            if outcome == "accepted":
                row.state = "accepted"
            elif outcome == "unknown":
                row.state = "unknown"
            elif outcome == "dead_subscription":
                row.state = "suppressed"
            elif attempt >= 4:
                row.state = "expired"
            else:
                row.state = "retryable"
                row.next_at = datetime.now(UTC) + timedelta(seconds=BACKOFF[attempt - 1])
            await db.commit()
