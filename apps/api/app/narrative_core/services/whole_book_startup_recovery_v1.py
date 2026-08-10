"""Startup recovery for WholeBookRun after sidecar / process exit (CHG-081).

Never auto-resume Provider work. Mark leftover running/pending formal V2 runs as
recoverable so the UI can offer 继续 / 重新分析 / 取消.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import WholeBookRun
from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus

logger = logging.getLogger(__name__)

PROCESS_INTERRUPTED_CODE = "WHOLE_BOOK_PROCESS_INTERRUPTED"
PROCESS_INTERRUPTED_MESSAGE = (
    "分析中断：本地分析服务曾退出。可选择继续、重新分析或取消。不会自动重新调用模型。"
)


def mark_interrupted_whole_book_runs(session: Session) -> dict[str, int]:
    """Mark non-terminal in-flight WholeBookRun rows as recoverable.

    Idempotent. Does not invoke Provider. Does not delete prior completed results.
    """
    now = datetime.now(timezone.utc)
    candidates = session.scalars(
        select(WholeBookRun).where(
            WholeBookRun.status.in_(
                (
                    WholeBookRunStatus.running.value,
                    WholeBookRunStatus.pending.value,
                )
            )
        )
    ).all()
    touched = 0
    for run in candidates:
        # pending without start is rare after CHG-077 (create starts immediately);
        # still treat as interrupted so UI never shows forever-stuck running/pending.
        run.status = WholeBookRunStatus.recoverable.value
        run.failure_code = PROCESS_INTERRUPTED_CODE
        run.failure_message_safe = PROCESS_INTERRUPTED_MESSAGE
        run.paused_at = run.paused_at or now
        touched += 1
    if touched:
        session.commit()
        logger.info("whole_book_startup_recovery recoverable=%s", touched)
    return {"recoverable": touched}


__all__ = [
    "PROCESS_INTERRUPTED_CODE",
    "PROCESS_INTERRUPTED_MESSAGE",
    "mark_interrupted_whole_book_runs",
]
