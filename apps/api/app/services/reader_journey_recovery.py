"""Startup / orphan recovery for ReaderJourneyRun (CHG-20260727-019).

Sidecar process exit leaves journey rows in worker-bound statuses with no live
worker. Startup recovery marks them interrupted (retryable) without enqueueing
Provider work. Resume may reclaim a stale fake-running row first.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AnalysisRun, ModelInvocation, ReaderJourneyRun

logger = logging.getLogger(__name__)

JOURNEY_INTERRUPTED = "JOURNEY_INTERRUPTED"

# Worker-bound statuses: no live BackgroundTask survives process exit.
JOURNEY_ACTIVE_WORKER_STATUSES = frozenset(
    {
        "queued",
        "running",
        "scene_profiles_running",
        "chapter_synthesis_running",
        "summary_running",
        "phase_analysis_running",
    }
)

# Mid-process orphan check: updated_at older than this ⇒ assume worker gone.
JOURNEY_STALE_THRESHOLD = timedelta(seconds=120)

_SAFE_ERROR_MESSAGE = "应用重启或后台任务中断，阅读旅程未完成；可从已完成检查点恢复"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def journey_has_unfinished_invocation(session: Session, analysis_run_id: int) -> bool:
    """True when a journey-related invocation is still marked in-flight."""
    row = session.scalar(
        select(ModelInvocation.id)
        .where(
            ModelInvocation.run_id == analysis_run_id,
            ModelInvocation.task_type.like("%reader_journey%"),
            ModelInvocation.status.in_(("running", "started", "pending")),
        )
        .limit(1)
    )
    return row is not None


def is_journey_worker_stale(
    session: Session,
    journey: ReaderJourneyRun,
    *,
    now: datetime | None = None,
    stale_after: timedelta = JOURNEY_STALE_THRESHOLD,
) -> bool:
    """True when a running-like journey has no recent progress / open invocation."""
    if journey.status not in JOURNEY_ACTIVE_WORKER_STATUSES:
        return False
    if journey_has_unfinished_invocation(session, int(journey.analysis_run_id)):
        return False
    clock = now or _now()
    stamp = _as_aware(journey.updated_at) or _as_aware(journey.started_at) or _as_aware(
        journey.created_at
    )
    if stamp is None:
        return True
    return clock - stamp >= stale_after


def mark_journey_interrupted(
    session: Session,
    journey: ReaderJourneyRun,
    *,
    now: datetime | None = None,
) -> bool:
    """Persist recoverable interrupt. Returns True if status changed."""
    if journey.status not in JOURNEY_ACTIVE_WORKER_STATUSES:
        return False
    clock = now or _now()
    previous = journey.status
    # Prefer existing partial status when some profiles already landed.
    if int(journey.completed_scene_count or 0) > 0 and int(
        journey.remaining_scene_count or 0
    ) > 0:
        journey.status = "scene_profiles_partial"
    else:
        journey.status = "failed"
    journey.root_error_code = JOURNEY_INTERRUPTED
    journey.root_error_message = _SAFE_ERROR_MESSAGE
    journey.retryable = True
    journey.failed_stage = journey.current_stage or "reader_journey_scene_profiles"
    journey.completed_at = clock
    journey.updated_at = clock
    details: dict[str, Any] = {}
    try:
        details = json.loads(journey.failure_details_json or "{}")
        if not isinstance(details, dict):
            details = {}
    except json.JSONDecodeError:
        details = {}
    details["interrupt"] = {
        "code": JOURNEY_INTERRUPTED,
        "previous_status": previous,
        "recovered_at": clock.isoformat(),
        "auto_enqueued": False,
    }
    journey.failure_details_json = json.dumps(details, ensure_ascii=False)
    return True


def recover_orphaned_reader_journeys(
    session: Session,
    *,
    force_startup: bool = True,
    stale_after: timedelta = JOURNEY_STALE_THRESHOLD,
) -> dict[str, int]:
    """Mark orphan worker-bound journeys interrupted. Never enqueues Provider work.

    force_startup=True (Sidecar boot): all active worker statuses are orphans.
    force_startup=False: only stale rows (no unfinished invocation + aged stamp).
    Idempotent: already-terminal interrupted rows are skipped.
    """
    from app.services.budget_reservation import release_run_reservation
    from app.services.chapter_analysis_completion import mark_journey_failed_on_run

    now = _now()
    candidates = list(
        session.scalars(
            select(ReaderJourneyRun).where(
                ReaderJourneyRun.status.in_(tuple(JOURNEY_ACTIVE_WORKER_STATUSES))
            )
        )
    )
    touched: list[int] = []
    for journey in candidates:
        if not force_startup and not is_journey_worker_stale(
            session, journey, now=now, stale_after=stale_after
        ):
            continue
        if not mark_journey_interrupted(session, journey, now=now):
            continue
        analysis_run = session.get(AnalysisRun, journey.analysis_run_id)
        if analysis_run is not None:
            mark_journey_failed_on_run(session, analysis_run)
            try:
                release_run_reservation(session, analysis_run.id)
            except Exception:  # noqa: BLE001 — never block recovery
                logger.exception(
                    "journey_interrupt_release_reservation_failed analysis_run_id=%s",
                    analysis_run.id,
                )
        touched.append(int(journey.id))
        logger.info(
            "reader_journey_orphaned_recovered journey_run_id=%s status=%s code=%s",
            journey.id,
            journey.status,
            JOURNEY_INTERRUPTED,
        )

    if touched:
        session.commit()
    return {
        "interrupted_journeys": len(touched),
        "journey_ids": len(touched),
    }


def reclaim_stale_journey_if_needed(
    session: Session,
    journey: ReaderJourneyRun,
    *,
    stale_after: timedelta = JOURNEY_STALE_THRESHOLD,
) -> bool:
    """Resume-entry orphan detect: stale running → recoverable. No Provider call."""
    if journey.status not in JOURNEY_ACTIVE_WORKER_STATUSES:
        return False
    if not is_journey_worker_stale(session, journey, stale_after=stale_after):
        return False
    changed = mark_journey_interrupted(session, journey)
    if changed:
        from app.services.budget_reservation import release_run_reservation
        from app.services.chapter_analysis_completion import mark_journey_failed_on_run

        analysis_run = session.get(AnalysisRun, journey.analysis_run_id)
        if analysis_run is not None:
            mark_journey_failed_on_run(session, analysis_run)
            try:
                release_run_reservation(session, analysis_run.id)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "journey_reclaim_release_reservation_failed analysis_run_id=%s",
                    analysis_run.id,
                )
        session.commit()
    return changed


def persist_journey_worker_failure(
    session_factory: sessionmaker[Session],
    journey_run_id: int,
    exc: BaseException,
) -> None:
    """Short independent transaction so failure survives rolled-back work sessions."""
    from app.services.budget_reservation import release_run_reservation
    from app.services.chapter_analysis_completion import mark_journey_failed_on_run
    from app.services.reader_journey_pipeline import _classify_journey_error

    try:
        root_code, stage, retryable, hint = _classify_journey_error(exc)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        root_code, stage, retryable, hint = (
            "JOURNEY_WORKER_EXCEPTION",
            "reader_journey",
            True,
            "后台任务异常已隔离",
        )

    with session_factory() as session:
        journey = session.get(ReaderJourneyRun, journey_run_id)
        if journey is None:
            return
        if journey.status in {"succeeded", "cancelled"}:
            return
        # Already terminal failure — keep first error unless still worker-bound.
        if journey.status not in JOURNEY_ACTIVE_WORKER_STATUSES and journey.status in {
            "failed",
            "scene_profiles_partial",
            "budget_blocked",
            "aborted_by_limit",
        }:
            return
        analysis_run = session.get(AnalysisRun, journey.analysis_run_id)
        if analysis_run is not None:
            mark_journey_failed_on_run(session, analysis_run)
            try:
                release_run_reservation(session, analysis_run.id)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "journey_failure_release_reservation_failed journey_run_id=%s",
                    journey_run_id,
                )
        if (
            int(journey.completed_scene_count or 0) > 0
            and int(journey.remaining_scene_count or 0) > 0
        ):
            journey.status = "scene_profiles_partial"
        else:
            journey.status = "failed"
        journey.root_error_code = root_code
        journey.root_error_message = str(exc)[:500]
        journey.failed_stage = journey.current_stage or stage
        journey.retryable = bool(retryable)
        journey.completed_at = _now()
        journey.updated_at = _now()
        details: dict[str, Any] = {}
        try:
            details = json.loads(journey.failure_details_json or "{}")
            if not isinstance(details, dict):
                details = {}
        except json.JSONDecodeError:
            details = {}
        details["hint"] = hint
        details["worker_boundary"] = True
        journey.failure_details_json = json.dumps(details, ensure_ascii=False)
        session.commit()
        logger.error(
            "reader_journey_worker_failure_persisted journey_run_id=%s code=%s",
            journey_run_id,
            root_code,
        )
