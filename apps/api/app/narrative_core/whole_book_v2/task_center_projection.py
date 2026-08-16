"""Minimal Task Center projection for WholeBookRun (CHG-084)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, WholeBookRun
from app.narrative_core.whole_book_v2.usage_ledger import (
    TASK_TYPE,
    ensure_task_projection,
    projection_client_request_id,
)
from app.schemas.scene import AnalysisRunResponse


def _map_wb_status(status: str) -> str:
    return {
        "pending": "queued",
        "running": "running",
        "paused": "paused",
        "recoverable": "failed",
        "completed": "succeeded",
        "failed": "failed",
        "cancelled": "cancelled",
        "canceled": "cancelled",
    }.get(str(status), str(status))


def project_whole_book_run(session: Session, wb: WholeBookRun) -> AnalysisRunResponse:
    """Ensure shadow AnalysisRun exists and serialize it for TasksPage."""
    run = ensure_task_projection(session, wb)
    base = AnalysisRunResponse.model_validate(run)
    return base.model_copy(
        update={
            "task_type": TASK_TYPE,
            "subject_type": "book",
            "subject_id": str(int(wb.book_id)),
            "analysis_type": "whole_book_v2",
            "scope_type": "whole_book",
            "book_id": int(wb.book_id),
            "client_request_id": projection_client_request_id(int(wb.id)),
            "current_stage": wb.current_stage_code,
            "user_action_hint": "全书 V2",
            "whole_book_run_id": int(wb.id),
            "mode_label": "全书 V2",
            "provider": str(wb.provider_name or base.provider),
            "model": str(wb.model_name or base.model),
            "status": _map_wb_status(wb.status),
        }
    )


def merge_whole_book_runs_into_task_list(
    session: Session,
    existing: list[AnalysisRunResponse],
    *,
    status: str | None = None,
    provider: str | None = None,
    book_id: int | None = None,
    limit: int = 50,
) -> list[AnalysisRunResponse]:
    known_keys = {
        str(getattr(r, "client_request_id", "") or "")
        for r in existing
    }
    # Also treat task_type whole_book_v2 rows as already projected.
    known_wb_ids: set[int] = set()
    for r in existing:
        if getattr(r, "task_type", None) == TASK_TYPE:
            key = str(getattr(r, "client_request_id", "") or "")
            if key.startswith("whole_book_v2:"):
                try:
                    known_wb_ids.add(int(key.split(":", 1)[1]))
                except ValueError:
                    pass
            details = getattr(r, "failure_details", None) or {}
            if isinstance(details, dict) and details.get("whole_book_run_id") is not None:
                known_wb_ids.add(int(details["whole_book_run_id"]))

    query = select(WholeBookRun).order_by(desc(WholeBookRun.created_at)).limit(limit)
    if book_id is not None:
        query = query.where(WholeBookRun.book_id == int(book_id))
    if provider:
        query = query.where(WholeBookRun.provider_name == provider)
    wb_rows = list(session.scalars(query))
    extras: list[AnalysisRunResponse] = []
    for wb in wb_rows:
        if int(wb.id) in known_wb_ids:
            continue
        key = projection_client_request_id(int(wb.id))
        if key in known_keys:
            continue
        mapped = _map_wb_status(wb.status)
        if status and mapped != status and wb.status != status:
            continue
        extras.append(project_whole_book_run(session, wb))
    merged = list(existing) + extras
    merged.sort(key=_sort_key, reverse=True)
    return merged[:limit]


def _sort_key(row: AnalysisRunResponse) -> datetime:
    """Sortable timestamp, always timezone-aware.

    The two sources disagree: SQLite hands back naive datetimes for chapter runs while the
    whole-book projection carries aware ones, and Python refuses to order the two. The
    comparison raised TypeError and took the whole task list — and with it 开始分析, which
    polls it — down with a 500 that the browser reported as a CORS failure, because an
    unhandled exception never reaches the CORS middleware that would have labelled it.

    Naive values are read as UTC: that is what the writer meant, and guessing local time
    would silently reorder runs by the offset.
    """
    value = row.created_at
    if value is None:
        return datetime.now(timezone.utc)
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


__all__ = [
    "merge_whole_book_runs_into_task_list",
    "project_whole_book_run",
]
