"""Whole-Book Run v1 state machine (WB-1.1) — no Provider calls."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Book, BookSnapshot, WholeBookRun, WholeBookRunStageRow, utc_now
from app.narrative_core.contracts.whole_book_contract_v1 import (
    WHOLE_BOOK_CONTRACT_VERSION,
    WHOLE_BOOK_STAGE_CODES_V1,
    ResultOrigin,
    WholeBookMode,
    WholeBookRunStatus,
    WholeBookStageStatus,
)
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)

DIAGNOSTIC_ENGINE_ID = "diagnostic_contract_engine"
DIAGNOSTIC_ENGINE_VERSION = "1"

_TERMINAL_STATUSES = frozenset(
    {
        WholeBookRunStatus.completed.value,
        WholeBookRunStatus.failed.value,
        WholeBookRunStatus.cancelled.value,
    }
)

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    WholeBookRunStatus.pending.value: frozenset(
        {
            WholeBookRunStatus.running.value,
            WholeBookRunStatus.cancelled.value,
        }
    ),
    WholeBookRunStatus.running.value: frozenset(
        {
            WholeBookRunStatus.paused.value,
            WholeBookRunStatus.recoverable.value,
            WholeBookRunStatus.failed.value,
            WholeBookRunStatus.completed.value,
            WholeBookRunStatus.cancelled.value,
        }
    ),
    WholeBookRunStatus.paused.value: frozenset(
        {
            WholeBookRunStatus.pending.value,
            WholeBookRunStatus.cancelled.value,
        }
    ),
    WholeBookRunStatus.recoverable.value: frozenset(
        {
            WholeBookRunStatus.pending.value,
            WholeBookRunStatus.failed.value,
            WholeBookRunStatus.cancelled.value,
            WholeBookRunStatus.running.value,
        }
    ),
}


def _run_idempotency_key(
    *,
    book_id: int,
    snapshot_id: int,
    mode: str,
    client_request_id: str,
) -> str:
    payload = (
        f"{book_id}|{snapshot_id}|{mode}|{client_request_id}|{WHOLE_BOOK_CONTRACT_VERSION}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_snapshot_for_run(session: Session, book_id: int, snapshot_id: int) -> BookSnapshot:
    snapshot = session.get(BookSnapshot, snapshot_id)
    if snapshot is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"snapshot not found: {snapshot_id}",
        )
    if snapshot.book_id != book_id:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_BOOK_MISMATCH,
            f"snapshot {snapshot_id} belongs to book {snapshot.book_id}, not {book_id}",
        )
    if snapshot.snapshot_status != "completed":
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_COMPLETED,
            f"snapshot {snapshot_id} status={snapshot.snapshot_status}",
        )
    return snapshot


def _validate_mode(mode: str) -> None:
    WholeBookMode(mode)


def _init_stages(session: Session, run_id: int, *, now: datetime) -> None:
    for sequence, stage_code in enumerate(WHOLE_BOOK_STAGE_CODES_V1):
        if stage_code == "snapshot":
            status = WholeBookStageStatus.completed.value
            progress_current = 1
            progress_total = 1
            completed_at = now
            started_at = now
        else:
            status = WholeBookStageStatus.pending.value
            progress_current = 0
            progress_total = 0
            completed_at = None
            started_at = None
        session.add(
            WholeBookRunStageRow(
                run_id=run_id,
                stage_code=stage_code,
                sequence=sequence,
                status=status,
                progress_current=progress_current,
                progress_total=progress_total,
                started_at=started_at,
                completed_at=completed_at,
            )
        )
    session.flush()


def create_whole_book_run_v1(
    session: Session,
    book_id: int,
    snapshot_id: int,
    mode: str,
    client_request_id: str,
    result_origin: str,
) -> WholeBookRun:
    if session.get(Book, book_id) is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_CHANGED,
            f"book not found: {book_id}",
        )
    _validate_mode(mode)
    _validate_snapshot_for_run(session, book_id, snapshot_id)

    idem = _run_idempotency_key(
        book_id=book_id,
        snapshot_id=snapshot_id,
        mode=mode,
        client_request_id=client_request_id,
    )
    existing = session.scalar(
        select(WholeBookRun).where(WholeBookRun.idempotency_key == idem)
    )
    if existing is not None:
        return existing

    origin = ResultOrigin(result_origin)
    now = utc_now()
    run = WholeBookRun(
        book_id=book_id,
        snapshot_id=snapshot_id,
        mode=mode,
        status=WholeBookRunStatus.pending.value,
        current_stage_code="windowing",
        idempotency_key=idem,
        engine_id=DIAGNOSTIC_ENGINE_ID,
        engine_version=DIAGNOSTIC_ENGINE_VERSION,
        contract_version=WHOLE_BOOK_CONTRACT_VERSION,
        prompt_version=None,
        result_origin=origin.value,
        consent_id=None,
        cost_policy_id=None,
        created_at=now,
    )
    session.add(run)
    session.flush()
    _init_stages(session, run.id, now=now)
    return run


def get_run(session: Session, run_id: int) -> WholeBookRun:
    run = session.get(WholeBookRun, run_id)
    if run is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_NOT_FOUND,
            f"run not found: {run_id}",
        )
    return run


def list_runs_for_book(session: Session, book_id: int) -> list[WholeBookRun]:
    return list(
        session.scalars(
            select(WholeBookRun)
            .where(WholeBookRun.book_id == book_id)
            .order_by(WholeBookRun.id.desc())
        ).all()
    )


def list_stages(session: Session, run_id: int) -> list[WholeBookRunStageRow]:
    get_run(session, run_id)
    return list(
        session.scalars(
            select(WholeBookRunStageRow)
            .where(WholeBookRunStageRow.run_id == run_id)
            .order_by(WholeBookRunStageRow.sequence.asc())
        ).all()
    )


def _transition_run(session: Session, run: WholeBookRun, target: str) -> WholeBookRun:
    current = run.status
    if current in _TERMINAL_STATUSES:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_TERMINAL,
            f"run {run.id} is terminal ({current})",
        )
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
            f"cannot transition run {run.id} from {current} to {target}",
        )
    now = datetime.now(timezone.utc)
    run.status = target
    if target == WholeBookRunStatus.running.value:
        run.started_at = run.started_at or now
        run.paused_at = None
    elif target == WholeBookRunStatus.paused.value:
        run.paused_at = now
    elif target == WholeBookRunStatus.pending.value:
        run.paused_at = None
    elif target == WholeBookRunStatus.cancelled.value:
        run.cancelled_at = now
    elif target == WholeBookRunStatus.completed.value:
        run.completed_at = now
    elif target == WholeBookRunStatus.failed.value:
        run.failed_at = now
    session.flush()
    return run


def start_whole_book_run_v1(session: Session, run_id: int) -> WholeBookRun:
    run = get_run(session, run_id)
    return _transition_run(session, run, WholeBookRunStatus.running.value)


def pause_whole_book_run_v1(session: Session, run_id: int) -> WholeBookRun:
    from app.narrative_core.services.whole_book_runtime_control_v1_service import (
        request_pause_whole_book_run_v1,
    )

    return request_pause_whole_book_run_v1(session, run_id)


def resume_whole_book_run_v1(session: Session, run_id: int) -> WholeBookRun:
    from app.narrative_core.services.whole_book_runtime_control_v1_service import (
        resume_whole_book_run_v1 as runtime_resume,
    )

    return runtime_resume(session, run_id)


def cancel_whole_book_run_v1(session: Session, run_id: int) -> WholeBookRun:
    from app.narrative_core.services.whole_book_runtime_control_v1_service import (
        request_cancel_whole_book_run_v1,
    )

    return request_cancel_whole_book_run_v1(session, run_id)


def run_to_dict(run: WholeBookRun) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "book_id": run.book_id,
        "snapshot_id": run.snapshot_id,
        "mode": run.mode,
        "status": run.status,
        "current_stage_code": run.current_stage_code,
        "idempotency_key": run.idempotency_key,
        "engine_id": run.engine_id,
        "engine_version": run.engine_version,
        "contract_version": run.contract_version,
        "prompt_version": run.prompt_version,
        "result_origin": run.result_origin,
        "input_usage": {
            "full_text_snapshot_used": True,
            "chapter_analysis_asset_count": 0,
            "reader_journey_asset_count": 0,
            "confirmed_whole_book_asset_count": 0,
        },
        "consent_id": run.consent_id,
        "cost_policy_id": run.cost_policy_id,
        "provider_name": getattr(run, "provider_name", "") or "",
        "model_name": getattr(run, "model_name", "") or "",
        "estimated_actual_cost_cny": getattr(run, "estimated_actual_cost_cny", None),
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "paused_at": run.paused_at.isoformat() if run.paused_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "failed_at": run.failed_at.isoformat() if run.failed_at else None,
        "cancelled_at": run.cancelled_at.isoformat() if run.cancelled_at else None,
        "failure_code": run.failure_code,
        "failure_message_safe": run.failure_message_safe,
        "pause_requested_at": run.pause_requested_at.isoformat() if run.pause_requested_at else None,
        "cancel_requested_at": run.cancel_requested_at.isoformat() if run.cancel_requested_at else None,
        "last_heartbeat_at": run.last_heartbeat_at.isoformat() if run.last_heartbeat_at else None,
        "resumed_at": run.resumed_at.isoformat() if run.resumed_at else None,
        "resume_count": int(run.resume_count or 0),
    }


def stage_to_dict(stage: WholeBookRunStageRow) -> dict[str, Any]:
    return {
        "stage_id": stage.id,
        "run_id": stage.run_id,
        "stage_code": stage.stage_code,
        "sequence": stage.sequence,
        "status": stage.status,
        "progress_current": stage.progress_current,
        "progress_total": stage.progress_total,
        "started_at": stage.started_at.isoformat() if stage.started_at else None,
        "completed_at": stage.completed_at.isoformat() if stage.completed_at else None,
        "last_error_code": stage.last_error_code,
        "last_error_message_safe": stage.last_error_message_safe,
    }
