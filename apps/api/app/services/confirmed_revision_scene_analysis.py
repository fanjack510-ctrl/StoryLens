"""Ensure scene-analysis artifacts exist for a confirmed BoundaryRevision (CHG-015)."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    BoundaryRevision,
    Paragraph,
    Scene,
)
from app.model_gateway.gateway import ModelGateway
from app.schemas.scene import SceneAnalysisResult
from app.services.prompt_service import load_prompt
from app.services.scene_analysis_progress import (
    clear_scene_analysis_error_fields,
    is_scene_analysis_complete,
)
from app.services.scene_pipeline import evidence_fields
from app.services.structured_output import generate_validated

logger = logging.getLogger(__name__)


def revision_scene_analysis_complete(
    session: Session, run_id: int, revision_id: int
) -> bool:
    scenes = list(
        session.scalars(
            select(Scene)
            .where(Scene.boundary_revision_id == revision_id)
            .order_by(Scene.ordinal)
        )
    )
    if not scenes:
        return False
    return all(is_scene_analysis_complete(session, run_id, scene) for scene in scenes)


def mark_awaiting_post_confirm_scene_analysis(session: Session, run: AnalysisRun) -> None:
    """Confirmed partition needs scene analysis — do not advertise scenes as complete."""
    from app.services.chapter_analysis_completion import _store_marker

    run.status = "scene_analysis_running"
    run.completed_at = None
    run.error_code = None
    run.error_message = None
    _store_marker(
        run,
        chapter_pipeline="post_confirm_scene_analysis",
        checkpoint_stage="scene_analysis",
        post_confirm_scene_analysis_at=datetime.now(timezone.utc).isoformat(),
    )


async def ensure_confirmed_revision_scene_analysis(
    session_factory: sessionmaker[Session],
    gateway: ModelGateway,
    revision_id: int,
) -> bool:
    """Analyze missing scenes for a confirmed revision. Returns True when complete."""
    from app.services.boundary_review_service import (
        _paragraphs,
        _validate_and_normalize_scene,
    )
    from app.services.chapter_analysis_completion import mark_scenes_complete_awaiting_journey

    with session_factory() as session:
        revision = session.get(BoundaryRevision, revision_id)
        if revision is None or revision.status != "confirmed":
            return False
        run = session.get(AnalysisRun, revision.analysis_run_id)
        if run is None:
            return False
        if revision_scene_analysis_complete(session, run.id, revision.id):
            mark_scenes_complete_awaiting_journey(session, run)
            session.commit()
            return True

        mark_awaiting_post_confirm_scene_analysis(session, run)
        session.commit()

        prompt = load_prompt("scene_analysis", "v3.2")
        clear_scene_analysis_error_fields(run)
        run.status = "scene_analysis_running"
        session.commit()

        scenes = list(
            session.scalars(
                select(Scene)
                .where(Scene.boundary_revision_id == revision.id)
                .order_by(Scene.ordinal)
            )
        )
        paragraphs = _paragraphs(session, revision.chapter_id)
        by_id = {item.id: item for item in paragraphs}
        position = {item.id: index for index, item in enumerate(paragraphs)}

        for scene in scenes:
            if is_scene_analysis_complete(session, run.id, scene):
                continue
            included = paragraphs[
                position[scene.start_paragraph_id] : position[scene.end_paragraph_id] + 1
            ]
            snapshot = {
                "scene_id": scene.scene_key,
                "paragraphs": [
                    {"id": item.id, "text": item.normalized_text} for item in included
                ],
            }
            result = await generate_validated(
                session=session,
                gateway=gateway,
                run_id=run.id,
                provider_name=run.provider,
                task_type="scene_analysis",
                prompt=prompt,
                schema=SceneAnalysisResult,
                input_snapshot=snapshot,
                user_content=prompt.user_template.format(
                    input_json=json.dumps(snapshot, ensure_ascii=False)
                ),
                business_validator=lambda value, scene=scene, included=included: (
                    _validate_and_normalize_scene(
                        value, scene.scene_key, {item.id for item in included}
                    )
                ),
            )
            artifact = AnalysisArtifact(
                run_id=run.id,
                artifact_type="scene_analysis",
                subject_type="scene",
                subject_id=str(scene.id),
                schema_version="v1",
                prompt_version="v3.2",
                payload_json=result.model_dump_json(),
                confidence=result.confidence,
                validation_status="valid",
            )
            session.add(artifact)
            session.flush()
            for path, paragraph_id in evidence_fields(result):
                paragraph = by_id[paragraph_id]
                session.add(
                    AnalysisEvidence(
                        artifact_id=artifact.id,
                        field_path=path,
                        paragraph_id=paragraph_id,
                        paragraph_hash=hashlib.sha256(
                            paragraph.raw_text.encode()
                        ).hexdigest(),
                    )
                )
            session.commit()

        run = session.get(AnalysisRun, revision.analysis_run_id)
        if run is None:
            return False
        if not revision_scene_analysis_complete(session, run.id, revision.id):
            logger.warning(
                "post_confirm_scene_analysis_incomplete revision_id=%s run_id=%s",
                revision_id,
                run.id,
            )
            return False
        mark_scenes_complete_awaiting_journey(session, run)
        session.commit()
        return True


async def confirm_start_analyze_then_journey(
    session_factory: sessionmaker[Session],
    gateway: ModelGateway,
    *,
    revision_id: int,
    journey_run_id: int,
) -> None:
    """Background: finish rematerialized scene analysis, then run journey."""
    from app.db.models import ReaderJourneyRun
    from app.services.reader_journey_pipeline import execute_reader_journey

    ok = await ensure_confirmed_revision_scene_analysis(
        session_factory, gateway, revision_id
    )
    if not ok:
        logger.error(
            "confirm_start_scene_analysis_failed revision_id=%s journey_run_id=%s",
            revision_id,
            journey_run_id,
        )
        with session_factory() as session:
            journey = session.get(ReaderJourneyRun, journey_run_id)
            if journey is not None and journey.status in {"starting", "queued"}:
                journey.status = "failed"
                journey.root_error_code = "SCENE_ANALYSIS_INCOMPLETE"
                journey.root_error_message = "确认后的场景分析未能完成"
                journey.failed_stage = "scene_analysis"
                journey.retryable = True
                journey.completed_at = datetime.now(timezone.utc)
                session.commit()
        return
    with session_factory() as session:
        journey = session.get(ReaderJourneyRun, journey_run_id)
        if journey is not None and journey.root_error_code == "WAITING_SCENE_ANALYSIS":
            journey.root_error_code = None
            journey.root_error_message = None
            journey.failed_stage = None
            if journey.status not in {
                "starting",
                "queued",
                "running",
                "scene_profiles_running",
                "chapter_synthesis_running",
            }:
                journey.status = "starting"
                journey.current_stage = "starting"
            session.commit()
    await execute_reader_journey(session_factory, gateway, journey_run_id)
