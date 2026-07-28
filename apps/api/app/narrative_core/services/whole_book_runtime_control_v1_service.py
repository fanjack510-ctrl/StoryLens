"""Whole-book runtime control — pause/resume/cancel soft semantics (WB-1.8)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    WholeBookConsent,
    WholeBookProviderAttempt,
    WholeBookProviderUnit,
    WholeBookRun,
    WholeBookRunStageRow,
    WholeBookWindow,
    utc_now,
)
from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus, WholeBookStageStatus
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_run_v1_service import (
    _TERMINAL_STATUSES,
    _transition_run,
    get_run,
)

_RUNNING_UNIT_STATUSES = frozenset({"pending", "running"})


def is_pause_requested(run: WholeBookRun) -> bool:
    return run.pause_requested_at is not None


def is_cancel_requested(run: WholeBookRun) -> bool:
    return run.cancel_requested_at is not None


def _has_in_flight_provider_unit(session: Session, run_id: int) -> bool:
    row = session.scalar(
        select(WholeBookProviderUnit.id).where(
            WholeBookProviderUnit.run_id == run_id,
            WholeBookProviderUnit.status == "running",
        )
    )
    return row is not None


def _touch_heartbeat(run: WholeBookRun) -> None:
    run.last_heartbeat_at = utc_now()


def _pause_current_stage(session: Session, run: WholeBookRun) -> None:
    if not run.current_stage_code:
        return
    stage = session.scalar(
        select(WholeBookRunStageRow).where(
            WholeBookRunStageRow.run_id == run.id,
            WholeBookRunStageRow.stage_code == run.current_stage_code,
        )
    )
    if stage is not None and stage.status == WholeBookStageStatus.running.value:
        stage.status = WholeBookStageStatus.paused.value
        session.flush()


def complete_soft_pause_if_requested(session: Session, run_id: int) -> bool:
    run = get_run(session, run_id)
    session.refresh(run)
    if not is_pause_requested(run):
        return False
    if run.status != WholeBookRunStatus.running.value:
        return False
    if _has_in_flight_provider_unit(session, run_id):
        return False
    _transition_run(session, run, WholeBookRunStatus.paused.value)
    _pause_current_stage(session, run)
    _touch_heartbeat(run)
    session.flush()
    return True


def complete_soft_cancel_if_requested(session: Session, run_id: int) -> bool:
    run = get_run(session, run_id)
    session.refresh(run)
    if not is_cancel_requested(run):
        return False
    if run.status in _TERMINAL_STATUSES:
        return False
    if _has_in_flight_provider_unit(session, run_id):
        return False
    _transition_run(session, run, WholeBookRunStatus.cancelled.value)
    session.flush()
    return True


def should_stop_claiming_units(session: Session, run_id: int) -> bool:
    run = get_run(session, run_id)
    session.refresh(run)
    if run.status in _TERMINAL_STATUSES:
        return True
    if is_cancel_requested(run):
        complete_soft_cancel_if_requested(session, run_id)
        return True
    if is_pause_requested(run):
        complete_soft_pause_if_requested(session, run_id)
        return True
    return False


def request_pause_whole_book_run_v1(session: Session, run_id: int) -> WholeBookRun:
    run = get_run(session, run_id)
    if run.status != WholeBookRunStatus.running.value:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
            f"run {run_id} must be running to pause (status={run.status})",
        )
    run.pause_requested_at = utc_now()
    _touch_heartbeat(run)
    session.flush()
    if not _has_in_flight_provider_unit(session, run_id):
        complete_soft_pause_if_requested(session, run_id)
        session.refresh(run)
    return run


def request_cancel_whole_book_run_v1(session: Session, run_id: int) -> WholeBookRun:
    run = get_run(session, run_id)
    if run.status in _TERMINAL_STATUSES:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_TERMINAL,
            f"run {run_id} is terminal ({run.status})",
        )
    run.cancel_requested_at = utc_now()
    _touch_heartbeat(run)
    session.flush()
    if not _has_in_flight_provider_unit(session, run_id):
        complete_soft_cancel_if_requested(session, run_id)
        session.refresh(run)
    return run


def resume_whole_book_run_v1(session: Session, run_id: int) -> WholeBookRun:
    run = get_run(session, run_id)
    if run.status not in {
        WholeBookRunStatus.paused.value,
        WholeBookRunStatus.recoverable.value,
    }:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
            f"run {run_id} cannot resume from {run.status}",
        )
    if run.cancel_requested_at is not None or run.status == WholeBookRunStatus.cancelled.value:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
            f"run {run_id} was cancelled and cannot resume",
        )
    run.pause_requested_at = None
    run.resume_count = int(run.resume_count or 0) + 1
    run.resumed_at = utc_now()
    _touch_heartbeat(run)
    _transition_run(session, run, WholeBookRunStatus.pending.value)
    if run.current_stage_code:
        stage = session.scalar(
            select(WholeBookRunStageRow).where(
                WholeBookRunStageRow.run_id == run.id,
                WholeBookRunStageRow.stage_code == run.current_stage_code,
            )
        )
        if stage is not None and stage.status == WholeBookStageStatus.paused.value:
            stage.status = WholeBookStageStatus.running.value
            stage.started_at = stage.started_at or utc_now()
    session.flush()
    return run


def _consent_limits(session: Session, run: WholeBookRun) -> tuple[int | None, int | None, int | None, str | None]:
    if run.consent_id is None:
        return None, None, None, None
    consent = session.get(WholeBookConsent, run.consent_id)
    if consent is None:
        return None, None, None, None
    return (
        int(consent.max_provider_calls or 0) or None,
        int(consent.max_input_tokens or 0) or None,
        int(consent.max_output_tokens or 0) or None,
        str(consent.user_budget_limit_cny) if consent.user_budget_limit_cny is not None else None,
    )


def aggregate_run_progress_v1(session: Session, run_id: int) -> dict[str, Any]:
    run = get_run(session, run_id)
    windows = list(
        session.scalars(select(WholeBookWindow).where(WholeBookWindow.run_id == run_id)).all()
    )
    total_windows = len(windows)
    completed_windows = sum(1 for w in windows if w.status == "completed")

    units = list(
        session.scalars(select(WholeBookProviderUnit).where(WholeBookProviderUnit.run_id == run_id)).all()
    )
    total_units = len(units)
    completed_units = sum(1 for u in units if u.status == "completed")

    attempt_rows = session.execute(
        select(
            func.count(WholeBookProviderAttempt.id),
            func.coalesce(func.sum(WholeBookProviderAttempt.input_tokens), 0),
            func.coalesce(func.sum(WholeBookProviderAttempt.output_tokens), 0),
            func.coalesce(func.sum(WholeBookProviderAttempt.cost_cny), 0),
        )
        .join(WholeBookProviderUnit, WholeBookProviderAttempt.provider_unit_id == WholeBookProviderUnit.id)
        .where(
            WholeBookProviderUnit.run_id == run_id,
            WholeBookProviderAttempt.status == "completed",
        )
    ).one()
    provider_calls_used = int(attempt_rows[0] or 0)
    input_tokens_used = int(attempt_rows[1] or 0)
    output_tokens_used = int(attempt_rows[2] or 0)
    cost_used = attempt_rows[3] or Decimal("0")

    stages = list(
        session.scalars(
            select(WholeBookRunStageRow)
            .where(WholeBookRunStageRow.run_id == run_id)
            .order_by(WholeBookRunStageRow.sequence.asc())
        ).all()
    )
    stage_progress_parts: list[float] = []
    for stage in stages:
        if stage.progress_total > 0:
            stage_progress_parts.append(min(1.0, stage.progress_current / stage.progress_total))
        elif stage.status == WholeBookStageStatus.completed.value:
            stage_progress_parts.append(1.0)
        elif stage.status in {WholeBookStageStatus.running.value, WholeBookStageStatus.paused.value}:
            stage_progress_parts.append(0.0)
    overall_progress = sum(stage_progress_parts) / len(stage_progress_parts) if stage_progress_parts else 0.0

    calls_limit, _input_limit, _output_limit, _budget = _consent_limits(session, run)

    can_pause = run.status == WholeBookRunStatus.running.value and not is_cancel_requested(run)
    can_resume = run.status in {
        WholeBookRunStatus.paused.value,
        WholeBookRunStatus.recoverable.value,
    } and not is_cancel_requested(run)
    can_cancel = run.status not in _TERMINAL_STATUSES

    return {
        "run_id": run_id,
        "status": run.status,
        "overall_progress": round(overall_progress, 4),
        "current_stage": run.current_stage_code,
        "completed_windows": completed_windows,
        "total_windows": total_windows,
        "completed_provider_units": completed_units,
        "total_provider_units": total_units,
        "provider_calls_used": provider_calls_used,
        "provider_calls_limit": calls_limit,
        "input_tokens_used": input_tokens_used,
        "output_tokens_used": output_tokens_used,
        "cost_used_cny": str(cost_used),
        "pause_requested": is_pause_requested(run),
        "cancel_requested": is_cancel_requested(run),
        "can_pause": can_pause,
        "can_resume": can_resume,
        "can_cancel": can_cancel,
        "resume_count": int(run.resume_count or 0),
        "stages": [
            {
                "stage_code": stage.stage_code,
                "status": stage.status,
                "progress_current": stage.progress_current,
                "progress_total": stage.progress_total,
            }
            for stage in stages
        ],
    }
