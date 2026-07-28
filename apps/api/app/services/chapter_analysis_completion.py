"""Chapter analysis completeness: scenes + reader journey as one pipeline.

Scene-pipeline ``succeeded`` historically meant “scenes certified”. Product completion
requires a succeeded ReaderJourneyRun as well. This module:

- detects partial (scenes done, journey missing);
- auto-enqueues journey on the same analysis_run_id;
- finalizes AnalysisRun.completed_at only when the chapter is fully complete;
- never deletes scene artifacts.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AnalysisRun, BoundaryRevision, Chapter, ReaderJourneyRun, Scene
from app.services.reader_journey_batch_planner import PLANNER_VERSION
from app.services.reader_journey_progress import (
    find_recoverable_journey_run,
    load_revision_scenes,
    require_completed_scene_analysis,
    sync_journey_run_counts,
)
from app.services.reader_journey_version import new_journey_version_fields
from app.services.scene_analysis_progress import scene_analysis_progress

logger = logging.getLogger(__name__)

AUTO_JOURNEY_CLIENT_PREFIX = "auto-chapter-journey:"
STATUS_SCENES_SUCCEEDED = "succeeded"
STATUS_JOURNEY_RUNNING = "reader_journey_running"
STATUS_JOURNEY_PENDING = "reader_journey_pending"
STATUS_JOURNEY_FAILED = "reader_journey_failed"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _marker(run: AnalysisRun) -> dict[str, Any]:
    try:
        raw = json.loads(run.raw_output or "{}")
        return raw if isinstance(raw, dict) else {}
    except json.JSONDecodeError:
        return {}


def _store_marker(run: AnalysisRun, **fields: Any) -> None:
    payload = _marker(run)
    payload.update(fields)
    payload["kind"] = payload.get("kind") or "chapter_pipeline"
    run.raw_output = json.dumps(payload, ensure_ascii=False, sort_keys=True)


def latest_journey(session: Session, run_id: int) -> ReaderJourneyRun | None:
    return session.scalar(
        select(ReaderJourneyRun)
        .where(ReaderJourneyRun.analysis_run_id == run_id)
        .order_by(ReaderJourneyRun.id.desc())
    )


def is_scene_pipeline_complete(session: Session, run: AnalysisRun) -> bool:
    progress = scene_analysis_progress(session, run)
    return progress.total_scene_count > 0 and progress.remaining_scene_count == 0


def is_chapter_analysis_complete(session: Session, run: AnalysisRun) -> bool:
    if not is_scene_pipeline_complete(session, run):
        return False
    journey = latest_journey(session, run.id)
    return bool(journey is not None and journey.status == "succeeded")


def effective_chapter_status(session: Session, run: AnalysisRun) -> str:
    """Derived product status for UI / tasks (does not rewrite legacy rows)."""
    journey = latest_journey(session, run.id)
    scenes_done = is_scene_pipeline_complete(session, run)

    if run.status in {
        "failed",
        "failed_provider",
        "failed_structural",
        "cancelled",
        "review_cancelled",
    }:
        return run.status
    if run.status in {"scene_analysis_partial", "boundary_candidates_partial"}:
        return run.status
    if run.status in {"awaiting_boundary_review", "boundary_review_required"}:
        return "awaiting_boundary_confirmation"
    marker = _marker(run)
    if marker.get("chapter_pipeline") == "awaiting_scene_boundary_confirmation":
        return "awaiting_scene_boundary_confirmation"
    if run.status in {"scene_analysis_running", "awaiting_provider_recovery"}:
        return "scene_analysis"
    if journey is not None and journey.status in {
        "queued",
        "running",
        "scene_profiles_running",
        "chapter_synthesis_running",
    }:
        return "journey_running"
    if journey is not None and journey.status in {
        "failed",
        "scene_profiles_partial",
        "budget_blocked",
        "aborted_by_limit",
    }:
        return "journey_failed"
    if scenes_done and (journey is None or journey.status != "succeeded"):
        marker = _marker(run)
        if marker.get("chapter_pipeline") == "awaiting_scene_boundary_confirmation":
            return "awaiting_scene_boundary_confirmation"
        return "partial_complete"
    if is_chapter_analysis_complete(session, run):
        return "completed"
    if run.status == STATUS_JOURNEY_PENDING:
        return "partial_complete"
    if run.status == STATUS_JOURNEY_RUNNING:
        return "journey_running"
    if run.status == STATUS_JOURNEY_FAILED:
        return "journey_failed"
    return run.status or "running"


def checkpoint_stage(session: Session, run: AnalysisRun) -> str:
    eff = effective_chapter_status(session, run)
    mapping = {
        "awaiting_boundary_confirmation": "awaiting_boundary_confirmation",
        "awaiting_scene_boundary_confirmation": "scene_boundary_confirmation",
        "scene_analysis": "scene_analysis",
        "partial_complete": "reader_journey_generation",
        "journey_running": "reader_journey_generation",
        "journey_failed": "reader_journey_generation",
        "completed": "completed",
        "scene_analysis_partial": "scene_analysis",
    }
    return mapping.get(eff, "preparing")


def mark_scenes_complete_awaiting_boundary_confirmation(session: Session, run: AnalysisRun) -> None:
    """Scenes certified — hold for manual boundary confirmation before journey."""
    run.status = STATUS_SCENES_SUCCEEDED
    run.completed_at = None
    run.error_code = None
    run.error_message = None
    _store_marker(
        run,
        chapter_pipeline="awaiting_scene_boundary_confirmation",
        checkpoint_stage="scene_boundary_confirmation",
        scenes_completed_at=_now().isoformat(),
    )


def mark_scenes_complete_awaiting_journey(session: Session, run: AnalysisRun) -> None:
    """Scenes certified — do not freeze chapter completed_at yet."""
    run.status = STATUS_SCENES_SUCCEEDED
    run.completed_at = None
    run.error_code = None
    run.error_message = None
    _store_marker(
        run,
        chapter_pipeline="awaiting_reader_journey",
        checkpoint_stage="reader_journey_generation",
        scenes_completed_at=_now().isoformat(),
    )


def finalize_chapter_analysis(session: Session, run: AnalysisRun) -> None:
    run.status = STATUS_SCENES_SUCCEEDED
    run.completed_at = _now()
    _store_marker(
        run,
        chapter_pipeline="completed",
        checkpoint_stage="completed",
        chapter_completed_at=run.completed_at.isoformat(),
    )


def mark_journey_failed_on_run(session: Session, run: AnalysisRun) -> None:
    # Keep scenes; expose resume via effective status.
    run.completed_at = None
    _store_marker(
        run,
        chapter_pipeline="journey_failed",
        checkpoint_stage="reader_journey_generation",
    )


def auto_journey_client_request_id(run_id: int, scene_revision_id: int | None = None) -> str:
    if scene_revision_id is not None:
        return f"{AUTO_JOURNEY_CLIENT_PREFIX}{run_id}:rev:{scene_revision_id}"
    return f"{AUTO_JOURNEY_CLIENT_PREFIX}{run_id}"


def ensure_auto_reader_journey_row(
    session: Session,
    run: AnalysisRun,
    *,
    cloud_consent: bool | None = None,
    scene_revision_id: int | None = None,
) -> ReaderJourneyRun | None:
    """Idempotently create/reuse a journey row for this analysis run. No model call."""
    # Confirmed revision bind may rematerialize scenes; skip global pipeline gate.
    if scene_revision_id is None and not is_scene_pipeline_complete(session, run):
        return None

    from app.services.scene_boundary_manual_review import (
        bind_journey_to_revision,
        revision_scenes,
    )

    client_request_id = auto_journey_client_request_id(run.id, scene_revision_id)
    existing = session.scalar(
        select(ReaderJourneyRun).where(
            ReaderJourneyRun.analysis_run_id == run.id,
            ReaderJourneyRun.client_request_id == client_request_id,
        )
    )
    if existing is not None:
        if scene_revision_id is not None:
            revision = session.get(BoundaryRevision, scene_revision_id)
            if revision is not None:
                scenes = revision_scenes(session, revision.id)
                bind_journey_to_revision(session, existing, revision, scenes)
        elif existing.scene_revision_id is None and scene_revision_id is not None:
            revision = session.get(BoundaryRevision, scene_revision_id)
            if revision is not None:
                scenes = revision_scenes(session, revision.id)
                bind_journey_to_revision(session, existing, revision, scenes)
        return existing

    # Legacy auto path (no revision bind): may reuse a current succeeded journey.
    # Explicit revision bind must create/reuse only via client_request_id above —
    # never steal an older fixture/manual succeeded row for the same or other revision.
    if scene_revision_id is None:
        succeeded = session.scalar(
            select(ReaderJourneyRun)
            .where(
                ReaderJourneyRun.analysis_run_id == run.id,
                ReaderJourneyRun.status == "succeeded",
                ReaderJourneyRun.result_status == "current",
            )
            .order_by(ReaderJourneyRun.id.desc())
        )
        if succeeded is not None:
            return succeeded
        recoverable = find_recoverable_journey_run(session, run.id)
        if recoverable is not None:
            return recoverable

    if scene_revision_id is not None:
        revision = session.get(BoundaryRevision, scene_revision_id)
        if revision is not None and revision.status == "confirmed":
            scenes = revision_scenes(session, revision.id)
            included = [s for s in scenes if bool(getattr(s, "included_in_journey", True))]
            chapter = session.get(Chapter, int(run.subject_id))
            version_fields = new_journey_version_fields()
            for other in session.scalars(
                select(ReaderJourneyRun).where(
                    ReaderJourneyRun.chapter_id == int(run.subject_id),
                    ReaderJourneyRun.result_status == "current",
                )
            ):
                other.result_status = "superseded"
            journey_run = ReaderJourneyRun(
                analysis_run_id=run.id,
                book_id=chapter.book_id if chapter else 0,
                chapter_id=int(run.subject_id),
                status="queued",
                current_stage=None,
                provider_name=run.provider,
                model_name=run.model,
                scene_prompt_version=version_fields["scene_prompt_version"],
                chapter_prompt_version=version_fields["chapter_prompt_version"],
                scene_contract_version=version_fields["scene_contract_version"],
                chapter_contract_version=version_fields["chapter_contract_version"],
                planner_version=PLANNER_VERSION,
                formula_version=version_fields["formula_version"],
                genre=version_fields["genre"],
                total_scene_count=len(included),
                completed_scene_count=0,
                remaining_scene_count=len(included),
                completed_scene_ids_json="[]",
                remaining_scene_ids_json=json.dumps([s.id for s in included]),
                cloud_consent=bool(cloud_consent if cloud_consent is not None else run.cloud_consent),
                client_request_id=client_request_id,
                failure_details_json=version_fields["failure_details_json"],
            )
            session.add(journey_run)
            session.flush()
            bind_journey_to_revision(session, journey_run, revision, scenes)
            _store_marker(
                run,
                chapter_pipeline="reader_journey_queued",
                checkpoint_stage="reader_journey_generation",
                auto_journey_run_id=journey_run.id,
            )
            return journey_run

    recoverable = find_recoverable_journey_run(session, run.id)
    if recoverable is not None:
        return recoverable

    _revision, scenes = load_revision_scenes(session, run.id)
    if not scenes:
        from app.services.scene_boundary_manual_review import run_scenes

        scenes = run_scenes(session, run.id)
    require_completed_scene_analysis(session, run, scenes)
    chapter = session.get(Chapter, int(run.subject_id))
    version_fields = new_journey_version_fields()
    journey_run = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=chapter.book_id if chapter else 0,
        chapter_id=int(run.subject_id),
        status="queued",
        current_stage=None,
        provider_name=run.provider,
        model_name=run.model,
        scene_prompt_version=version_fields["scene_prompt_version"],
        chapter_prompt_version=version_fields["chapter_prompt_version"],
        scene_contract_version=version_fields["scene_contract_version"],
        chapter_contract_version=version_fields["chapter_contract_version"],
        planner_version=PLANNER_VERSION,
        formula_version=version_fields["formula_version"],
        genre=version_fields["genre"],
        total_scene_count=len(scenes),
        completed_scene_count=0,
        remaining_scene_count=len(scenes),
        completed_scene_ids_json="[]",
        remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
        cloud_consent=bool(cloud_consent if cloud_consent is not None else run.cloud_consent),
        client_request_id=client_request_id,
        failure_details_json=version_fields["failure_details_json"],
    )
    session.add(journey_run)
    session.flush()
    if scene_revision_id is not None:
        revision = session.get(BoundaryRevision, scene_revision_id)
        if revision is not None:
            bound_scenes = revision_scenes(session, revision.id)
            bind_journey_to_revision(session, journey_run, revision, bound_scenes)
    _store_marker(
        run,
        chapter_pipeline="reader_journey_queued",
        checkpoint_stage="reader_journey_generation",
        auto_journey_run_id=journey_run.id,
    )
    return journey_run


async def continue_chapter_after_scenes(
    session_factory: sessionmaker[Session],
    gateway: Any,
    run_id: int,
) -> None:
    """After all scenes succeed: ensure model revision and await manual boundary confirmation."""
    from app.services.scene_boundary_manual_review import ensure_ai_model_revision_after_scenes_v1

    with session_factory() as session:
        run = session.get(AnalysisRun, run_id)
        if run is None:
            return
        if not is_scene_pipeline_complete(session, run):
            return
        if is_chapter_analysis_complete(session, run):
            finalize_chapter_analysis(session, run)
            session.commit()
            return

        ensure_ai_model_revision_after_scenes_v1(session, run)
        mark_scenes_complete_awaiting_boundary_confirmation(session, run)
        session.commit()


def _journey_result_available(session: Session, journey: ReaderJourneyRun | None) -> bool:
    if journey is None or journey.status != "succeeded":
        return False
    from app.db.models import ChapterReaderJourneySummary

    summary = session.scalar(
        select(ChapterReaderJourneySummary).where(
            ChapterReaderJourneySummary.reader_journey_run_id == journey.id
        )
    )
    return summary is not None


def _journey_primary_action(
    *,
    effective: str,
    journey: ReaderJourneyRun | None,
    result_available: bool,
) -> str | None:
    if journey is None:
        return None
    if effective == "journey_running":
        return "view_progress"
    if effective == "journey_failed":
        return "view_detail"
    if effective == "completed" and result_available:
        return "view_result"
    if journey.status == "succeeded" and not result_available:
        return "view_detail"
    return None


def chapter_completion_payload(session: Session, run: AnalysisRun) -> dict[str, Any]:
    progress = scene_analysis_progress(session, run)
    journey = latest_journey(session, run.id)
    complete = is_chapter_analysis_complete(session, run)
    effective = effective_chapter_status(session, run)
    result_available = _journey_result_available(session, journey)
    return {
        "chapter_complete": complete,
        "effective_status": effective,
        "checkpoint_stage": checkpoint_stage(session, run),
        "scene_pipeline_complete": is_scene_pipeline_complete(session, run),
        "total_scene_count": progress.total_scene_count,
        "completed_scene_count": progress.completed_scene_count,
        "journey_run_id": journey.id if journey else None,
        "journey_status": journey.status if journey else None,
        "journey_completed_scene_count": (
            int(journey.completed_scene_count) if journey is not None else None
        ),
        "journey_total_scene_count": (
            int(journey.total_scene_count) if journey is not None else None
        ),
        "journey_retryable": bool(journey.retryable) if journey is not None else None,
        "journey_result_available": result_available,
        "journey_error_code": journey.root_error_code if journey is not None else None,
        "primary_action": _journey_primary_action(
            effective=effective, journey=journey, result_available=result_available
        ),
        "resume_stage": (
            None
            if complete
            else (
                "reader_journey_generation"
                if is_scene_pipeline_complete(session, run)
                else None
            )
        ),
    }
