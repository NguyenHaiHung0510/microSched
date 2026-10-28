"""Prepared native CAS/dispatch policy proof. Requires an explicitly leased PG lane."""

import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import config_policy as policy
from app.core.database_urls import async_postgres_url
from app.core.settings import Settings
from app.domain.models import AppSetting

pytestmark = pytest.mark.pg


def test_durable_policy_CAS_and_save_send_ordering(pg_dsn, monkeypatch):
    # Fresh exact synthetic key; no resetting a retained/global setting row.
    setting_name = "mimi.owner172.test." + uuid4().hex
    monkeypatch.setattr(policy, "POLICY_KEY", setting_name)
    monkeypatch.setattr(policy, "POLICY_LOCK", int(uuid4().hex[:14], 16))

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        selected = Settings(_env_file=None, mimi_route_model="deepseek/deepseek-v4.1-flash-1017")
        initial = policy.bootstrap_policy(selected)
        prices = initial.model_dump(mode="json")["prices"]
        prices[selected.mimi_route_model] = {"prompt": ".05", "completion": ".10"}
        change = policy.PolicyChange(expected_revision=0, input_codepoints=50_000, prices=prices)
        pending = None
        try:
            async with maker() as dispatch_db:
                admitted = await policy.bind_wire_policy(dispatch_db, selected)
                assert admitted.mimi_operating_policy_revision == 0

                async def save():
                    async with maker() as save_db:
                        updated = await policy.save_policy(save_db, selected, change)
                        await save_db.commit()
                        return updated

                pending = asyncio.create_task(save())
                # Explicit event boundary: save waits while the unsent admission
                # holds its policy transaction; no paid call or sleep/retry loop.
                await asyncio.sleep(0)
                assert not pending.done()
                await dispatch_db.commit()
            updated = await pending
            assert updated.revision == 1
            async with maker() as next_db:
                following = await policy.bind_wire_policy(next_db, selected)
                assert following.mimi_route_max_input_price == policy.Decimal(".05")
                assert admitted.mimi_route_max_input_price == policy.Decimal(".36")
                await next_db.commit()

            async def stale_save():
                async with maker() as db:
                    with pytest.raises(HTTPException, match="policy_stale"):
                        await policy.save_policy(db, selected, change)
                    await db.rollback()

            await asyncio.gather(stale_save(), stale_save())
            async with maker() as read_db:
                assert (await policy.read_policy(read_db, selected)).revision == 1
        finally:
            if pending is not None and not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            async with maker() as db:
                await db.execute(delete(AppSetting).where(AppSetting.key == setting_name))
                await db.commit()
            await engine.dispose()

    asyncio.run(scenario())
