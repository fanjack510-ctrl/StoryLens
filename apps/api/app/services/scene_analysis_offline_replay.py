"""Offline Scene Analysis replay from stored invocations (zero HTTP)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    ModelInvocation,
    Paragraph,
    Scene,
)
from app.schemas.scene import SceneAnalysisResult
from app.services.scene_analysis_progress import (
    is_scene_analysis_complete,
    load_revision_scenes,
    pending_scenes_for_run,
    resolve_scene_failure_pointers,
    scene_analysis_progress,
    sync_run_partial_display,
)
from app.services.scene_pipeline import (
    evidence_fields,
    normalize_scene_analysis_result,
    validate_scene_analysis,
)

# Max real HTTP invocations per scene across resumes (initial + repair count separately).
SCENE_ANALYSIS_MAX_HTTP_ATTEMPTS = 4


@dataclass(frozen=True)
class OfflineReplayResult:
    run_id: int
    scene_id: int
    artifact_id: int
    invocation_id: int
    status: str
    completed_scene_count: int
    remaining_scene_count: int
    remaining_scene_ids: list[int]
    offline_replay_available: bool
    idempotent_replay: bool
    message: str
    request_id: str | None = None


def _scene_paragraphs(session: Session, scene: Scene) -> list[Paragraph]:
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == scene.chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    by_id = {item.id: item for item in paragraphs}
    if scene.start_paragraph_id not in by_id or scene.end_paragraph_id not in by_id:
        raise ValueError("场景段落范围无效")
    start = next(i for i, p in enumerate(paragraphs) if p.id == scene.start_paragraph_id)
    end = next(i for i, p in enumerate(paragraphs) if p.id == scene.end_paragraph_id)
    return paragraphs[start : end + 1]


def _snapshot_matches_scene(snapshot: dict | None, scene: Scene) -> bool:
    if not isinstance(snapshot, dict):
        return False
    if snapshot.get("scene_id") == scene.scene_key:
        return True
    paragraph_ids = snapshot.get("paragraph_ids")
    if isinstance(paragraph_ids, list) and paragraph_ids:
        return (
            paragraph_ids[0] == scene.start_paragraph_id
            and paragraph_ids[-1] == scene.end_paragraph_id
        )
    paragraphs = snapshot.get("paragraphs")
    if isinstance(paragraphs, list) and paragraphs:
        ids = [item.get("id") for item in paragraphs if isinstance(item, dict)]
        if ids:
            return ids[0] == scene.start_paragraph_id and ids[-1] == scene.end_paragraph_id
    return False


def count_scene_http_attempts(session: Session, run_id: int, scene: Scene) -> int:
    rows = session.scalars(
        select(ModelInvocation).where(
            ModelInvocation.run_id == run_id,
            ModelInvocation.task_type == "scene_analysis",
            ModelInvocation.http_request_sent.is_(True),
        )
    ).all()
    count = 0
    for inv in rows:
        try:
            snap = json.loads(inv.input_snapshot_json or "{}")
        except json.JSONDecodeError:
            continue
        if _snapshot_matches_scene(snap if isinstance(snap, dict) else None, scene):
            count += 1
    return count


def find_replayable_scene_invocation(
    session: Session, run_id: int, scene: Scene, *, invocation_id: int | None = None
) -> tuple[ModelInvocation, SceneAnalysisResult] | None:
    query = select(ModelInvocation).where(
        ModelInvocation.run_id == run_id,
        ModelInvocation.task_type == "scene_analysis",
        ModelInvocation.parsed_response_json.is_not(None),
    )
    if invocation_id is not None:
        query = query.where(ModelInvocation.id == invocation_id)
    rows = session.scalars(query.order_by(ModelInvocation.id.desc())).all()
    included = _scene_paragraphs(session, scene)
    allowed = {item.id for item in included}
    for inv in rows:
        try:
            snap = json.loads(inv.input_snapshot_json or "{}")
        except json.JSONDecodeError:
            snap = {}
        if not _snapshot_matches_scene(snap if isinstance(snap, dict) else None, scene):
            continue
        try:
            payload = json.loads(inv.parsed_response_json or "")
            result = normalize_scene_analysis_result(
                SceneAnalysisResult.model_validate(payload), allowed
            )
            validate_scene_analysis(result, scene.scene_key, allowed, True)
        except Exception:
            continue
        return inv, result
    return None


def persist_scene_analysis_artifact(
    session: Session,
    run: AnalysisRun,
    scene: Scene,
    result: SceneAnalysisResult,
) -> AnalysisArtifact:
    included = _scene_paragraphs(session, scene)
    by_id = {item.id: item for item in included}
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
                paragraph_hash=hashlib.sha256(paragraph.raw_text.encode()).hexdigest(),
            )
        )
    session.commit()
    return artifact


def _failure_pointers(session: Session, run: AnalysisRun):
    progress = scene_analysis_progress(session, run)
    return progress, resolve_scene_failure_pointers(
        session,
        run,
        progress,
        find_replayable=find_replayable_scene_invocation,
        count_http_attempts=count_scene_http_attempts,
    )


def offline_replay_scene_analysis(
    session: Session,
    run: AnalysisRun,
    *,
    scene_id: int | None = None,
    invocation_id: int | None = None,
    client_request_id: str | None = None,
) -> OfflineReplayResult:
    """Commit Artifact from a stored parsed response. Never sends HTTP."""
    del client_request_id  # reserved for future idempotency ledger
    _revision, scenes = load_revision_scenes(session, run)
    if not scenes:
        raise ValueError("RUN_HAS_NO_SCENES")
    target: Scene | None = None
    if scene_id is not None:
        target = next((s for s in scenes if s.id == scene_id), None)
        if target is None:
            raise ValueError("SCENE_NOT_FOUND")
    else:
        _progress, pointers = _failure_pointers(session, run)
        if pointers.offline_replay_scene_id is not None:
            target = session.get(Scene, pointers.offline_replay_scene_id)
        if target is None:
            pending = pending_scenes_for_run(session, run)
            target = pending[0] if pending else None
    if target is None:
        raise ValueError("NO_PENDING_SCENE")
    if is_scene_analysis_complete(session, run.id, target):
        progress = sync_run_partial_display(session, run)
        run = session.get(AnalysisRun, run.id)
        assert run is not None
        pointers = resolve_scene_failure_pointers(
            session,
            run,
            progress,
            find_replayable=find_replayable_scene_invocation,
            count_http_attempts=count_scene_http_attempts,
        )
        art = session.scalar(
            select(AnalysisArtifact)
            .where(
                AnalysisArtifact.run_id == run.id,
                AnalysisArtifact.artifact_type == "scene_analysis",
                AnalysisArtifact.subject_id == str(target.id),
                AnalysisArtifact.validation_status == "valid",
            )
            .order_by(AnalysisArtifact.id.desc())
        )
        return OfflineReplayResult(
            run_id=run.id,
            scene_id=target.id,
            artifact_id=art.id if art else 0,
            invocation_id=invocation_id or 0,
            status=run.status,
            completed_scene_count=progress.completed_scene_count,
            remaining_scene_count=progress.remaining_scene_count,
            remaining_scene_ids=progress.pending_scene_ids,
            offline_replay_available=pointers.offline_replay_available,
            idempotent_replay=True,
            message=f"Scene #{target.id}已离线恢复，未产生云端费用",
        )
    matched = find_replayable_scene_invocation(
        session, run.id, target, invocation_id=invocation_id
    )
    if matched is None:
        if invocation_id is not None:
            raise ValueError("OFFLINE_REPLAY_VALIDATION_FAILED")
        raise ValueError("NO_REPLAYABLE_RESPONSE")
    inv, result = matched
    included = _scene_paragraphs(session, target)
    allowed = {item.id for item in included}
    result = normalize_scene_analysis_result(result, allowed)
    validate_scene_analysis(result, target.scene_key, allowed, True)
    artifact = persist_scene_analysis_artifact(session, run, target, result)
    progress = sync_run_partial_display(session, run)
    run = session.get(AnalysisRun, run.id)
    assert run is not None
    pointers = resolve_scene_failure_pointers(
        session,
        run,
        progress,
        find_replayable=find_replayable_scene_invocation,
        count_http_attempts=count_scene_http_attempts,
    )
    return OfflineReplayResult(
        run_id=run.id,
        scene_id=target.id,
        artifact_id=artifact.id,
        invocation_id=inv.id,
        status=run.status,
        completed_scene_count=progress.completed_scene_count,
        remaining_scene_count=progress.remaining_scene_count,
        remaining_scene_ids=progress.pending_scene_ids,
        offline_replay_available=pointers.offline_replay_available,
        idempotent_replay=False,
        message=f"Scene #{target.id}已离线恢复，未产生云端费用",
        request_id=inv.request_id,
    )
