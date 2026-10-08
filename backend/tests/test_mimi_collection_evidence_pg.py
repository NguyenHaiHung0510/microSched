"""Evidence encryption/causality/completeness and logical expiry contracts."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import cleanup, local_contract, prepare  # noqa: F401

from app.agent import crypto, evidence, service
from app.agent.models import MimiConversation
from app.core.database_urls import async_postgres_url

pytestmark = pytest.mark.pg


def test_bundle_bound_truncation_tamper_expiry_and_cross_run_refs(pg_dsn, monkeypatch):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, ch, decision = await prepare(maker)
        try:
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                dek = crypto.unwrap_dek(conv.dek_wrapped)
                body = "Synthetic long causal message " * 500
                service._add_assistant_message(db, conv, rid, dek, body)
                await db.commit()
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                monkeypatch.setattr(evidence, "MAX_BYTES", 8000)
                bundle = await evidence.capture_feedback(db, conv, "run", str(rid), [])
                assert bundle.capture_status == "incomplete" and bundle.content_bytes <= 8000
                assert "messages" in bundle.metadata_json["omitted_parts"]
                assert body not in json.dumps(bundle.metadata_json)
                result = await evidence.read_evidence(db, conv, bundle.id)
                assert (
                    result["metadata"]["hidden_reasoning"] == "EXCLUDED"
                    and result["metadata"]["provider_raw_response"] == "NOT_CAPTURED"
                )
                original = bundle.content_ciphertext
                wrong_aad = crypto.seal_content(
                    crypto.unwrap_dek(conv.dek_wrapped), "{}", aad="wrong-resource"
                )
                bundle.content_ciphertext = wrong_aad
                with pytest.raises(InvalidTag):
                    await evidence.read_evidence(db, conv, bundle.id)
                bundle.content_ciphertext = original
                bundle.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                with pytest.raises(HTTPException, match="expired"):
                    await evidence.read_evidence(db, conv, bundle.id)
                bundle.expires_at = datetime.now(UTC) + timedelta(days=1)
                bundle.metadata_json = {**bundle.metadata_json, "target_id": str(ch)}
                with pytest.raises(HTTPException, match="causal_binding"):
                    await evidence.capture_feedback(db, conv, "run", str(rid), [bundle.id])
                await db.rollback()
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())
