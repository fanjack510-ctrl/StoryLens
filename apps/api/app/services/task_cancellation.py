"""CHG-20260729-006 — cooperative AnalysisRun cancellation (no process kill)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, ReaderJourneyRun
from app.services.budget_reservation import release_run_reservation

REASON_USER_REQUESTED = "user_requested"

STATUS_CANCELLATION_REQUESTED = "cancellation_requested"
STATUS_STOPPING = "stopping"
STATUS_CANCELLED = "cancelled"

TERMINAL_SUCCESS = frozenset({"succeeded", "completed"})
TERMINAL_FAILED = frozenset(
    {
        "failed",
        "failed_provider",
        "failed_structural",
    }
)
TERMINAL_CANCELLED = frozenset({"cancelled", "review_cancelled", "review_expired"})
CANCEL_IN_PROGRESS = frozenset({STATUS_CANCELLATION_REQUESTED, STATUS_STOPPING})

CANCELABLE_STATUSES = frozenset(
    {
        "queued",
        "pending",
        "preparing",
        "running",
        "analyzing",
        "materializing",
        "synthesizing",
        "paused",
        "boundary_candidates_running",
        "boundary_confirmed",
        "boundary_confirmed_budget_blocked",
        "scene_analysis_running",
        "scene_analysis_partial",
        "boundary_candidates_partial",
        "reader_journey_processing",
        "reader_journey_running",
        "reader_journey_scene_profiles_running",
        "reader_journey_chapter_running",
        "awaiting_provider_recovery",
        "awaiting_boundary_review",
        "aborted_by_limit",
        "retrying",
    }
)

# No in-process worker advancing these — finalize cancel immediately.
IMMEDIATE_CANCEL_STATUSES = frozenset(
    {
        "queued",
        "pending",
        "paused",
        "awaiting_provider_recovery",
        "awaiting_boundary_review",
        "boundary_confirmed_budget_blocked",
        "aborted_by_limit",
        "scene_analysis_partial",
        "boundary_candidates_partial",
        "boundary_confirmed",
    }
)


class AnalysisCancellationRequested(Exception):
    """Raised inside workers when a persisted cancel request is observed."""

    def __init__(self, run_id: int):
        super().__init__(f"analysis_run_cancelled:{run_id}")
        self.run_id = run_id


@dataclass
class CancelResult:
    task_id: int
    previous_status: str
    current_status: str
    cancellation_requested_at: datetime | None
    cancelled_at: datetime | None
    message: str
    already_requested: bool
    already_cancelled: bool
    already_completed: bool
    cannot_cancel: bool
    can_restart_as_new_task: bool
    status_version: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_cancel_requested(run: AnalysisRun | None) -> bool:
    if run is None:
        return False
    if run.status in CANCEL_IN_PROGRESS or run.status == STATUS_CANCELLED:
        return True
    return run.cancellation_requested_at is not None and run.status not in TERMINAL_SUCCESS


def raise_if_cancel_requested(session: Session, run_id: int) -> None:
    """Raise when a cooperative cancel request is visible.

    Flush pending ORM mutations before refresh so local progress / stage updates
    are not discarded when reloading cancel flags from the database.
    """
    run = session.get(AnalysisRun, run_id)
    if run is None:
        return
    session.flush()
    session.refresh(run)
    if run.status in TERMINAL_SUCCESS | TERMINAL_FAILED:
        return
    if is_cancel_requested(run):
        raise AnalysisCancellationRequested(run_id)


def _cancel_open_journeys(session: Session, analysis_run_id: int) -> None:
    journeys = list(
        session.scalars(
            select(ReaderJourneyRun).where(ReaderJourneyRun.analysis_run_id == analysis_run_id)
        )
    )
    now = _now()
    for journey in journeys:
        if journey.status in {"succeeded", "cancelled"}:
            # Do not rewrite a prior succeeded journey as cancelled.
            if journey.status == "succeeded":
                if journey.result_status == "current":
                    # Partial cancel of parent must not leave a false "current complete" if incomplete.
                    # Keep succeeded journeys as-is; only cancel non-terminal ones.
                    continue
            continue
        journey.status = STATUS_CANCELLED
        journey.completed_at = now
        journey.retryable = False
        journey.root_error_code = "USER_CANCELLED"
        journey.root_error_message = "用户主动停止分析"
        # Never present cancelled journey as the current succeeded chapter result.
        if journey.result_status == "current":
            journey.result_status = "cancelled_partial"


def finalize_cancelled(session: Session, run: AnalysisRun, *, commit: bool = True) -> AnalysisRun:
    """Idempotently move run to cancelled, release reservations, cancel open journeys."""
    if run.status == STATUS_CANCELLED and run.cancelled_at is not None:
        return run
    now = _now()
    if run.status != STATUS_CANCELLED:
        if run.status not in CANCEL_IN_PROGRESS:
            run.status = STATUS_STOPPING
            session.flush()
        run.status = STATUS_CANCELLED
    if run.cancellation_requested_at is None:
        run.cancellation_requested_at = now
    if run.cancellation_reason is None:
        run.cancellation_reason = REASON_USER_REQUESTED
    if run.cancelled_by is None:
        run.cancelled_by = "user"
    run.cancelled_at = run.cancelled_at or now
    run.completed_at = run.completed_at or now
    run.retryable = False
    run.error_code = run.error_code or "USER_CANCELLED"
    run.error_message = run.error_message or "用户主动停止分析"
    run.status_version = int(run.status_version or 0) + 1
    session.flush()
    # Release all active reservations for this run (all stages).
    release_run_reservation(session, run.id, stage=None)
    _cancel_open_journeys(session, run.id)
    if commit:
        session.commit()
        session.refresh(run)
    return run


def request_cancel(
    session: Session,
    run_id: int,
    *,
    reason: str = REASON_USER_REQUESTED,
    expected_version: int | None = None,
    client_request_id: str | None = None,  # noqa: ARG001 — reserved for audit / future dedupe
) -> CancelResult:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise LookupError("ANALYSIS_RUN_NOT_FOUND")

    previous = run.status
    version = int(run.status_version or 0)
    if expected_version is not None and version != int(expected_version):
        raise ValueError("ANALYSIS_RUN_VERSION_CONFLICT")

    if run.status in TERMINAL_SUCCESS:
        return CancelResult(
            task_id=run.id,
            previous_status=previous,
            current_status=run.status,
            cancellation_requested_at=run.cancellation_requested_at,
            cancelled_at=run.cancelled_at,
            message="任务已完成，无法停止",
            already_requested=False,
            already_cancelled=False,
            already_completed=True,
            cannot_cancel=True,
            can_restart_as_new_task=True,
            status_version=version,
        )
    if run.status in TERMINAL_FAILED:
        return CancelResult(
            task_id=run.id,
            previous_status=previous,
            current_status=run.status,
            cancellation_requested_at=run.cancellation_requested_at,
            cancelled_at=run.cancelled_at,
            message="任务已失败，无法停止",
            already_requested=False,
            already_cancelled=False,
            already_completed=False,
            cannot_cancel=True,
            can_restart_as_new_task=True,
            status_version=version,
        )
    if run.status in TERMINAL_CANCELLED:
        return CancelResult(
            task_id=run.id,
            previous_status=previous,
            current_status=run.status,
            cancellation_requested_at=run.cancellation_requested_at,
            cancelled_at=run.cancelled_at,
            message="任务已停止",
            already_requested=True,
            already_cancelled=True,
            already_completed=False,
            cannot_cancel=False,
            can_restart_as_new_task=True,
            status_version=version,
        )
    if run.status in CANCEL_IN_PROGRESS or run.cancellation_requested_at is not None:
        # Idempotent re-request while stopping.
        if run.status != STATUS_CANCELLED:
            # Ensure request fields exist.
            run.cancellation_reason = run.cancellation_reason or reason
            session.commit()
        return CancelResult(
            task_id=run.id,
            previous_status=previous,
            current_status=run.status,
            cancellation_requested_at=run.cancellation_requested_at,
            cancelled_at=run.cancelled_at,
            message="正在停止" if run.status != STATUS_CANCELLED else "任务已停止",
            already_requested=True,
            already_cancelled=run.status == STATUS_CANCELLED,
            already_completed=False,
            cannot_cancel=False,
            can_restart_as_new_task=True,
            status_version=int(run.status_version or 0),
        )

    if run.status not in CANCELABLE_STATUSES:
        return CancelResult(
            task_id=run.id,
            previous_status=previous,
            current_status=run.status,
            cancellation_requested_at=None,
            cancelled_at=None,
            message="当前状态不可停止",
            already_requested=False,
            already_cancelled=False,
            already_completed=False,
            cannot_cancel=True,
            can_restart_as_new_task=True,
            status_version=version,
        )

    now = _now()
    run.cancellation_requested_at = now
    run.cancellation_reason = reason or REASON_USER_REQUESTED
    run.cancelled_by = "user"
    run.status_version = version + 1

    # Idle / paused / never-started: finalize immediately (no worker to observe).
    if run.status in IMMEDIATE_CANCEL_STATUSES or run.started_at is None:
        finalize_cancelled(session, run, commit=True)
        return CancelResult(
            task_id=run.id,
            previous_status=previous,
            current_status=run.status,
            cancellation_requested_at=run.cancellation_requested_at,
            cancelled_at=run.cancelled_at,
            message="任务已停止",
            already_requested=False,
            already_cancelled=True,
            already_completed=False,
            cannot_cancel=False,
            can_restart_as_new_task=True,
            status_version=int(run.status_version or 0),
        )

    # Active worker path: persist request; worker finalizes at next checkpoint.
    run.status = STATUS_CANCELLATION_REQUESTED
    session.commit()
    session.refresh(run)
    return CancelResult(
        task_id=run.id,
        previous_status=previous,
        current_status=run.status,
        cancellation_requested_at=run.cancellation_requested_at,
        cancelled_at=run.cancelled_at,
        message="正在停止分析",
        already_requested=False,
        already_cancelled=False,
        already_completed=False,
        cannot_cancel=False,
        can_restart_as_new_task=True,
        status_version=int(run.status_version or 0),
    )


def try_finalize_if_cancel_requested(session: Session, run_id: int) -> bool:
    """If cancel requested, finalize and return True (caller must stop work)."""
    run = session.get(AnalysisRun, run_id)
    if run is None:
        return False
    if run.status in TERMINAL_SUCCESS:
        return False
    if not is_cancel_requested(run):
        return False
    finalize_cancelled(session, run, commit=True)
    return True
