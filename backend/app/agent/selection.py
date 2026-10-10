"""Server-bound semantic selection from actual encrypted tool receipts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid7

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import crypto
from app.agent.models import MimiEvent, MimiRun
from app.agent.task_collection import canonical, digest

SELECTION_TOOL = "task.freeze_selection.v1"


class SelectionMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    classification: Literal["included", "excluded", "uncertain"]
    reason: str = Field(min_length=1, max_length=500)


class SelectionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    intent: str = Field(min_length=1, max_length=1000)
    variants_considered: tuple[str, ...] = Field(min_length=1, max_length=32)
    variants_pending: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    members: tuple[SelectionMember, ...] = Field(min_length=1, max_length=1000)
    explicitly_named_subset: bool = False

    @model_validator(mode="after")
    def unique_members(self):
        if len({m.id for m in self.members}) != len(self.members):
            raise ValueError("selection_duplicate_member")
        if any(
            not v.strip() or len(v) > 120
            for v in (*self.variants_considered, *self.variants_pending)
        ):
            raise ValueError("selection_variant_invalid")
        return self


async def read_receipts(
    db: AsyncSession, conversation_id: UUID, dek: bytes, run_id: UUID
) -> list[dict]:
    events = (
        await db.scalars(
            select(MimiEvent)
            .join(MimiRun, MimiEvent.run_id == MimiRun.id)
            .where(
                MimiRun.conversation_id == conversation_id,
                MimiRun.id == run_id,
                MimiEvent.kind == "tool.read_result",
            )
            .order_by(MimiEvent.created_at, MimiEvent.sequence)
            .limit(1001)
        )
    ).all()
    if len(events) > 1000:
        raise ValueError("selection_receipt_range_exceeded")
    receipts = []
    for event in events:
        ciphertext = event.payload.get("body_ciphertext")
        if not isinstance(ciphertext, str):
            continue
        body = json.loads(
            crypto.open_content(
                dek,
                ciphertext,
                aad=crypto.event_content_aad(event.run_id, event.sequence, event.kind),
            )
        )
        if digest(body["result"]) != event.payload.get("result_sha256"):
            raise ValueError("selection_read_receipt_hash_invalid")
        receipts.append(
            {
                "event_id": str(event.id),
                "run_id": str(event.run_id),
                "tool": event.payload["tool"],
                **body,
            }
        )
    return receipts


def bind_selection(candidate: SelectionCandidate, receipts: list[dict]) -> dict[str, Any]:
    observed = {}
    queries = {}
    content_reads = {}
    version_conflicts = set()
    for receipt in receipts:
        result = receipt["result"]
        for row in result.get("rows", []):
            if not isinstance(row, dict) or "collection_version" not in row:
                continue
            prior = observed.get(row["id"])
            if prior and (
                prior["collection_version"] != row["collection_version"]
                or prior["source_version"] != row["source_version"]
            ):
                version_conflicts.add(row["id"])
            observed[row["id"]] = {
                "collection_version": row["collection_version"],
                "source_version": row["source_version"],
                "data_as_of": result.get("data_as_of"),
                "receipt_event_id": receipt["event_id"],
            }
        if receipt["tool"] == "task.query.v1":
            args = receipt["arguments"]
            key = digest({k: v for k, v in args.items() if k != "cursor"})
            q = queries.setdefault(
                key,
                {
                    "filter": args.get("filter", {}),
                    "pages": [],
                    "open_cursors": set(),
                    "first_page": False,
                },
            )
            cursor = args.get("cursor")
            q["first_page"] |= cursor is None
            q["open_cursors"].discard(cursor)
            next_cursor = result.get("next_cursor")
            if next_cursor:
                q["open_cursors"].add(next_cursor)
            q["pages"].append(receipt["event_id"])
        if receipt["tool"] == "task.read_content.v1":
            for row in result.get("rows", []):
                item = content_reads.setdefault(
                    row["id"],
                    {
                        "body_total": row.get("body_total_chars", 0),
                        "body_ranges": [],
                        "item_pages": [],
                        "items": {},
                        "event_ids": [],
                    },
                )
                item["event_ids"].append(receipt["event_id"])
                item["body_ranges"].append(row.get("body_range", [0, 0]))
                item["item_pages"].append(
                    (
                        row.get("items_offset", 0),
                        row.get("items_offset", 0) + len(row.get("items", [])),
                        result.get("next_items_offset") is None,
                    )
                )
                for child in row.get("items", []):
                    c = item["items"].setdefault(
                        child["id"], {"total": child["content_total_chars"], "ranges": []}
                    )
                    c["ranges"].append(child["content_range"])
    if version_conflicts:
        raise ValueError("selection_source_version_changed_between_reads")

    def covered(ranges, total):
        end = 0
        for start, stop in sorted(ranges):
            if start > end:
                return False
            end = max(end, stop)
        return end >= total

    content_obligations = []
    for tid, item in content_reads.items():
        terminal = [stop for start, stop, last in item["item_pages"] if last]
        obligations = []
        if not covered(item["body_ranges"], item["body_total"]):
            obligations.append("body_md.outside_read_union")
        if not terminal or not covered([(a, b) for a, b, _ in item["item_pages"]], max(terminal)):
            obligations.append("items.outside_read_union")
        if any(not covered(c["ranges"], c["total"]) for c in item["items"].values()):
            obligations.append("items.content.outside_read_union")
        if obligations:
            content_obligations.append(
                {"id": tid, "event_ids": item["event_ids"], "omitted_fields": obligations}
            )
    members = []
    for member in candidate.members:
        version = observed.get(str(member.id))
        if version is None or not isinstance(version["collection_version"], int):
            raise ValueError("selection_member_has_no_actual_versioned_receipt")
        members.append({**member.model_dump(mode="json"), **version})
    query_records = [{**q, "open_cursors": sorted(q["open_cursors"])} for q in queries.values()]
    query_complete = bool(query_records) and all(
        q["first_page"] and not q["open_cursors"] for q in query_records
    )
    uncertain = sum(m.classification == "uncertain" for m in candidate.members)
    # Every observed corpus row needs classification for an all-scope statement.
    missing_members = sorted(set(observed) - {str(m.id) for m in candidate.members})
    scanned_variants = {
        str(q["filter"].get("title_contains", "")).casefold().strip() for q in query_records
    }
    full_corpus = any(
        q["first_page"]
        and not q["open_cursors"]
        and not any(v for k, v in q["filter"].items() if k != "lifecycle")
        for q in query_records
    )
    unproved_variants = [
        v
        for v in candidate.variants_considered
        if v.casefold().strip() not in scanned_variants and not full_corpus
    ]
    semantic_complete = (
        query_complete
        and not candidate.variants_pending
        and not uncertain
        and not missing_members
        and not content_obligations
        and not unproved_variants
    )
    if not semantic_complete and not candidate.explicitly_named_subset:
        raise ValueError("selection_all_scope_has_unresolved_obligations")
    included = [m for m in members if m["classification"] == "included"]
    if not included or len(included) > 200:
        raise ValueError("selection_included_target_bound")
    return {
        "schema_version": "mimi.selection.v1",
        "selection_id": str(uuid7()),
        "intent": candidate.intent,
        "variants_considered": candidate.variants_considered,
        "variants_pending": candidate.variants_pending,
        "unproved_variants": unproved_variants,
        "queries": query_records,
        "members": members,
        "missing_classifications": missing_members,
        "content_obligations": content_obligations,
        "query_complete": query_complete,
        "semantic_complete": semantic_complete,
        "explicitly_named_subset": candidate.explicitly_named_subset,
        "as_of": datetime.now(UTC).isoformat(),
    }


async def persist_selection(
    db: AsyncSession,
    conversation_id: UUID,
    run_id: UUID,
    dek: bytes,
    arguments: dict,
    append_event,
) -> dict:
    candidate = SelectionCandidate.model_validate(arguments)
    selection = bind_selection(candidate, await read_receipts(db, conversation_id, dek, run_id))
    sequence = await append_event(
        db,
        run_id,
        "selection.frozen",
        {"selection_id": selection["selection_id"], "sha256": digest(selection)},
    )
    event = (
        await db.scalars(
            select(MimiEvent).where(MimiEvent.run_id == run_id, MimiEvent.sequence == sequence)
        )
    ).one()
    event.payload = {
        **event.payload,
        "body_ciphertext": crypto.seal_content(
            dek, canonical(selection), aad=crypto.event_content_aad(run_id, sequence, event.kind)
        ),
    }
    await db.flush()
    return selection


async def load_selection(
    db: AsyncSession, conversation_id: UUID, selection_id: UUID, dek: bytes
) -> dict:
    events = (
        await db.scalars(
            select(MimiEvent)
            .join(MimiRun, MimiEvent.run_id == MimiRun.id)
            .where(
                MimiRun.conversation_id == conversation_id,
                MimiEvent.kind == "selection.frozen",
                MimiEvent.payload["selection_id"].astext == str(selection_id),
            )
            .limit(2)
        )
    ).all()
    if len(events) != 1:
        raise HTTPException(409, "selection_not_found_or_wrong_conversation")
    event = events[0]
    body = json.loads(
        crypto.open_content(
            dek,
            event.payload["body_ciphertext"],
            aad=crypto.event_content_aad(event.run_id, event.sequence, event.kind),
        )
    )
    if digest(body) != event.payload["sha256"]:
        raise HTTPException(409, "selection_hash_invalid")
    return body


def covered_versions(selection: dict, target_ids: list[UUID]) -> dict[UUID, int]:
    included = {
        UUID(m["id"]): m["collection_version"]
        for m in selection["members"]
        if m["classification"] == "included"
    }
    if set(target_ids) != set(included):
        raise HTTPException(409, "collection_must_match_exact_frozen_selection")
    return included


async def latest_selection(db, conversation_id, dek):
    event = (
        await db.scalars(
            select(MimiEvent)
            .join(MimiRun)
            .where(MimiRun.conversation_id == conversation_id, MimiEvent.kind == "selection.frozen")
            .order_by(MimiEvent.created_at.desc(), MimiEvent.id.desc())
            .limit(1)
        )
    ).first()
    if event is None:
        return None
    body = json.loads(
        crypto.open_content(
            dek,
            event.payload["body_ciphertext"],
            aad=crypto.event_content_aad(event.run_id, event.sequence, event.kind),
        )
    )
    if digest(body) != event.payload["sha256"]:
        raise HTTPException(409, "selection_hash_invalid")
    return {"event_id": str(event.id), "run_id": str(event.run_id), "snapshot": body}
