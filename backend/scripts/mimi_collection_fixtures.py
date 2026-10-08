"""Deterministic STANDARD synthetic fixture manifest/seed for Task086 QA."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

import asyncpg
from sqlalchemy.engine import make_url

from app.core.database_urls import asyncpg_dsn

CLOCK = "2026-10-09T00:00:00+07:00"
STAMP = 1791482400000


def stable_id(counter):
    return str(UUID(int=(STAMP << 80) | (7 << 76) | (0x86 << 64) | (2 << 62) | counter))


def manifest():
    groups = {}
    serial = 1
    for name, count in (("training49", 49), ("bulk50", 50), ("bulk100", 100), ("bulk200", 200)):
        tasks = []
        for i in range(count):
            tid = stable_id(serial)
            serial += 1
            title = f"{name} · Công việc tổng hợp {i + 1}"
            included = True
            if name == "training49":
                aliases = ("tập luyện", "the duc", "luyện tập", "tap luyen")
                title = (
                    f"Buổi {aliases[i % 4]} {i + 1}"
                    if i < 48
                    else "Đọc bài viết nhắc đến tập luyện"
                )
                included = i < 48
            items = []
            for j in range(25 if i == 0 else 2):
                items.append(
                    {
                        "id": stable_id(serial),
                        "position": j,
                        "content": "í" * 1200 if j == 0 and i == 0 else f"Bước {j + 1} · {name}",
                        "is_completed": j == 1,
                        "deleted_at": None,
                    }
                )
                serial += 1
            tasks.append(
                {
                    "id": tid,
                    "title": title,
                    "body_md": "ế" * 12000 if i == 0 else "Nội dung chuẩn bị 🏃",
                    "status": "open",
                    "priority": None,
                    "pinned": False,
                    "due_precision": "none",
                    "due_on": None,
                    "due_at": None,
                    "is_private": False,
                    "collection_version": 1 + len(items),
                    "classification": "included" if included else "excluded",
                    "classification_reason": "Buổi tập thực sự"
                    if included
                    else "Bài viết nhắc hoạt động, không phải buổi tập",
                    "items": items,
                }
            )
        groups[name] = {
            "count": count,
            "included_ids": [t["id"] for t in tasks if t["classification"] == "included"],
            "tasks": tasks,
        }
    result = {
        "schema_version": "mimi086.synthetic-fixture.v1",
        "seed": "086",
        "clock": CLOCK,
        "scope": "STANDARD_ONLY",
        "groups": groups,
        "private_sentinel_id": stable_id(serial),
        "reminder_variants": [
            "future_absolute",
            "future_relative_date_anchor",
            "future_relative_datetime",
            "sent",
            "sending",
            "needs_reschedule",
            "cancelled",
        ],
        "reminder_note": (
            "Executable tests create each variant per case and use actual "
            "clock+future offsets; manifest group seed has no dispatchable reminders."
        ),
        "domain_total": 399,
        "training_actual_sessions": 48,
        "training_incidental": 1,
    }
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result["content_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return result


async def seed_manifest(data, url):
    parsed = make_url(url)
    if (parsed.host, parsed.port, parsed.database) not in {
        ("127.0.0.1", 21886, "microsched_mimi086"),
        ("127.0.0.1", 21886, "microsched_mimi086_ci2"),
        ("localhost", 21886, "microsched_mimi086"),
        ("127.0.0.1", 21887, "mimi086_qa"),
        ("localhost", 21887, "mimi086_qa"),
    }:
        raise SystemExit("fixture seed refuses undeclared/nonlocal database")
    conn = await asyncpg.connect(asyncpg_dsn(url))
    try:
        assert await conn.fetchval("SELECT version_num FROM microsched.alembic_version") == "0017"
        tids = [UUID(t["id"]) for g in data["groups"].values() for t in g["tasks"]]
        if await conn.fetchval(
            "SELECT count(*) FROM microsched.task WHERE id=ANY($1::uuid[])", tids
        ):
            raise SystemExit("fixture already exists: inspect/reuse; no blind reseed/reset")
        async with conn.transaction():
            for group in data["groups"].values():
                for task in group["tasks"]:
                    await conn.execute(
                        "INSERT INTO microsched.task"
                        "(id,title,body_md,status,due_precision,is_private) "
                        "VALUES($1,$2,$3,'open','none',false)",
                        UUID(task["id"]),
                        task["title"],
                        task["body_md"],
                    )
                    for item in task["items"]:
                        await conn.execute(
                            "INSERT INTO microsched.task_item"
                            "(id,task_id,content,position,is_completed) "
                            "VALUES($1,$2,$3,$4,$5)",
                            UUID(item["id"]),
                            UUID(task["id"]),
                            item["content"],
                            item["position"],
                            item["is_completed"],
                        )
            # Negative synthetic ciphertext sentinel; never decrypt/send it.
            await conn.execute(
                "INSERT INTO microsched.task(id,title,body_md,is_private,due_precision) "
                "VALUES($1,'enc:v1:synthetic-private-sentinel',"
                "'enc:v1:synthetic-body',true,'none')",
                UUID(data["private_sentinel_id"]),
            )
        rows = await conn.fetch(
            "SELECT id,collection_version,updated_at FROM microsched.task WHERE id=ANY($1::uuid[])",
            tids,
        )
        return {
            "status": "PASS_SEED",
            "fixture_sha256": data["content_sha256"],
            "count": len(rows),
            "private_sentinel": "EXCLUDED_FROM_PROVIDER",
            "schema": "0017",
            "actual_versions": [
                {
                    "id": str(r["id"]),
                    "collection_version": r["collection_version"],
                    "source_version": r["updated_at"].isoformat(),
                }
                for r in rows
            ],
        }
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    data = manifest()
    if args.manifest_output:
        args.manifest_output.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if args.seed:
        if not args.receipt:
            raise SystemExit("--receipt required")
        result = asyncio.run(seed_manifest(data, os.environ["NEON_MIGRATOR_URL"]))
        args.receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("synthetic_fixture_count=" + str(result["count"]))
    else:
        print("fixture_manifest_sha256=" + data["content_sha256"])


if __name__ == "__main__":
    main()
