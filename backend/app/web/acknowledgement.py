"""Explicit durable ACK boundary for the six admitted batch handlers only."""

import logging
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
AckOperation = Literal[
    "mimi_response_timing",
    "mimi_feedback",
    "note_move_to_top",
    "history_handled",
    "history_batch_prepare",
    "history_batch_commit",
]


async def commit_before_ack(db: AsyncSession, operation: AckOperation) -> None:
    """A failed commit is ambiguous: retain the original client intent for replay.

    This opt-in boundary does not replace request cleanup or own auth/cron state.
    Do not log exception messages: database drivers may include private parameters.
    """
    try:
        await db.commit()
    except Exception as error:
        logger.error(
            "ack_commit_unknown operation=%s error_type=%s", operation, type(error).__name__
        )
        try:
            await db.rollback()
        except Exception as rollback_error:
            logger.error(
                "ack_rollback_unknown operation=%s error_type=%s",
                operation,
                type(rollback_error).__name__,
            )
        raise HTTPException(
            status_code=503,
            detail=(
                f"{operation}_unknown"
                if operation == "history_batch_commit"
                else f"{operation}_commit_unknown"
            ),
            headers={"Cache-Control": "no-store"},
        ) from None
