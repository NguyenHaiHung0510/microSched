"""All control-changing transactions lock the one logical Zone first."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.migarden.models import ConfigRecord, ZoneState
from app.domain.migarden.wire import ZONE, ConfigurationBundle


class Rejected(Exception):
    def __init__(self, code: str, status: int = 409):
        self.code = code
        self.status = status
        super().__init__(code)


async def read_zone(db: AsyncSession) -> ZoneState | None:
    return await db.scalar(select(ZoneState).where(ZoneState.zone_id == ZONE))


async def lock_zone(db: AsyncSession, *, create: bool = False) -> ZoneState:
    if create:
        await db.execute(insert(ZoneState).values(zone_id=ZONE).on_conflict_do_nothing())
    zone = await db.scalar(
        select(ZoneState)
        .where(ZoneState.zone_id == ZONE)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if zone is None:
        raise Rejected("controller_not_provisioned")
    return zone


async def config_record(db: AsyncSession, ref: str | None) -> ConfigRecord | None:
    if ref is None:
        return None
    return await db.scalar(select(ConfigRecord).where(ConfigRecord.config_ref == ref))


async def get_config(db: AsyncSession, ref: str | None) -> ConfigurationBundle | None:
    row = await config_record(db, ref)
    return ConfigurationBundle.model_validate(row.bundle) if row else None
