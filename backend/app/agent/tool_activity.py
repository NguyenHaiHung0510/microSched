"""Authenticated, bounded display projection of existing encrypted tool receipts."""

from __future__ import annotations

import json
from binascii import Error as Base64Error
from typing import Any

from cryptography.exceptions import InvalidTag

from app.agent import crypto
from app.agent.tools.task_reads import TaskQuery

TOOLS = {
    "task.query.v1": "Đọc Task",
    "task.aggregate.v1": "Thống kê Task",
    "task.inspect_batch.v1": "Đối chiếu Task",
    "task.read_content.v1": "Đọc nội dung Task",
    "task.freeze_selection.v1": "Chốt tập Task",
    "task.create_candidate.v2": "Đề xuất Task mới",
    "task.collection_candidate.v1": "Đề xuất thay đổi Task",
}


def tool_activity(row: Any, dek: bytes) -> dict[str, Any]:
    tool = row.payload.get("tool")
    activity: dict[str, Any] = {
        "label": TOOLS.get(tool, "Công cụ Task"),
        "state": "unavailable",
        "query": None,
    }
    ciphertext = row.payload.get("body_ciphertext")
    if not isinstance(ciphertext, str) or len(ciphertext) > 256_000:
        return activity
    try:
        body = json.loads(
            crypto.open_content(
                dek,
                ciphertext,
                aad=crypto.event_content_aad(row.run_id, row.sequence, row.kind),
            )
        )
        result = body["result"]
        if not isinstance(result, dict):
            return activity
        error = result.get("error")
        failed = isinstance(error, dict)
        if tool != "task.query.v1":
            activity["state"] = "error" if failed else "recorded"
            return activity
        request = TaskQuery.model_validate(body["arguments"])
        count = result.get("count")
        count = count if not failed and type(count) is int and 0 <= count <= 50 else None
        coverage = result.get("coverage")
        coverage = coverage if coverage in {"complete", "partial", "unavailable"} else "unavailable"
        as_of = result.get("data_as_of")
        # The values are known server-produced dates; never pass arbitrary text.
        from datetime import datetime

        if isinstance(as_of, str):
            as_of = datetime.fromisoformat(as_of).isoformat()
        else:
            as_of = None
        activity.update(
            state="error" if failed else "recorded",
            query={
                "filter": request.filter.model_dump(mode="json"),
                "sort": request.sort,
                "limit": request.limit,
                "projection": list(request.projection),
                "cursor_present": bool(request.cursor),
                "count": count,
                "coverage": coverage,
                "as_of": as_of,
                "has_next_page": bool(result.get("next_cursor")),
                "error": "invalid_task_query_cursor"
                if failed and error.get("code") == "invalid_task_query_cursor"
                else "tool_error"
                if failed
                else None,
                # Mandatory source provenance, not requested selected fields or entity IDs.
                "intrinsic_provenance": ["source_version", "collection_version"],
            },
        )
    except ValueError, TypeError, KeyError, InvalidTag, Base64Error:
        pass  # Malformed/old receipts stay explicitly unavailable, never zero matches.
    return activity
