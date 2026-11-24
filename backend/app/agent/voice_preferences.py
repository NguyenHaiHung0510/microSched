"""Workspace-scoped Voice preference, serialized with the quick-apply decision."""

from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy import func, select

from app.agent.owner_workspace import owner_id
from app.agent.service import _transaction_lock_key
from app.domain.models import AppSetting


class VoicePreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fast_apply: StrictBool


async def voice_preference(db, auth, *, lock=False, change: VoicePreferences | None = None):
    key = f"mimi.voice.fast_apply.v1:{owner_id(auth)}"
    if lock or change is not None:
        # An absent row is the default-on case and must take the same lock.
        await db.execute(select(func.pg_advisory_xact_lock(_transaction_lock_key("setting", key))))
    row = await db.scalar(select(AppSetting).where(AppSetting.key == key))
    if change is not None:
        if row is None:
            db.add(AppSetting(key=key, value=change.model_dump()))
        else:
            row.value = change.model_dump()
        return change
    return VoicePreferences(fast_apply=row is None or row.value.get("fast_apply") is True)
