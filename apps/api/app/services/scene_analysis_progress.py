"""Scene Analysis completion progress and Stage-2 failure persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    BoundaryRevision,
    BoundaryReviewSession,
    ModelInvocation,
    Scene,
)
from app.model_gateway.base import ProviderRequestError
from app.services.scene_pipeline import classify_pipeline_error
from app.services.structured_output import StructuredOutputError


@dataclass(frozen=True)
class SceneAnalysisProgress:
    total_scene_count: int
    completed_scene_ids: list[int]
    failed_scene_ids: list[int]
    pending_scene_ids: list[int]
    completed_scene_count: int
    remaining_scene_count: int
    boundary_revision_id: int | None
    coverage_rate: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "total_scene_count": self.total_scene_count,
            "completed_scene_ids": list(self.completed_scene_ids),
            "failed_scene_ids": list(self.failed_scene_ids),
            "pending_scene_ids": list(self.pending_scene_ids),
            "completed_scene_count": self.completed_scene_count,
            "remaining_scene_count": self.remaining_scene_count,
            "boundary_revision_id": self.boundary_revision_id,
            "coverage_rate": self.coverage_rate,
        }


def _valid_scene_artifact(
    session: Session, run_id: int, scene_id: int
) -> AnalysisArtifact | None:
    artifact = session.scalar(
        select(AnalysisArtifact)
        .where(
            AnalysisArtifact.run_id == run_id,
            AnalysisArtifact.artifact_type == "scene_analysis",
            AnalysisArtifact.subject_id == str(scene_id),
            AnalysisArtifact.validation_status == "valid",
        )
        .order_by(AnalysisArtifact.id.desc())
    )
    if artifact is None:
        return None
    evidence_count = session.scalar(
        select(func.count())
        .select_from(AnalysisEvidence)
        .where(AnalysisEvidence.artifact_id == artifact.id)
    )
    if int(evidence_count or 0) < 1:
        return None
    return artifact


def is_scene_analysis_complete(session: Session, run_id: int, scene: Scene) -> bool:
    return _valid_scene_artifact(session, run_id, scene.id) is not None


def load_revision_scenes(
    session: Session, run: AnalysisRun
) -> tuple[BoundaryRevision | None, list[Scene]]:
    review = session.scalar(
        select(BoundaryReviewSession)
        .where(BoundaryReviewSession.analysis_run_id == run.id)
        .order_by(BoundaryReviewSession.id.desc())
    )
    if review is None:
        return None, []
    revision = session.scalar(
        select(BoundaryRevision)
        .where(BoundaryRevision.review_session_id == review.id)
        .order_by(BoundaryRevision.id.desc())
    )
    if revision is None:
        return None, []
    scenes = list(
        session.scalars(
            select(Scene)
            .where(Scene.boundary_revision_id == revision.id)
            .order_by(Scene.ordinal)
        )
    )
    return revision, scenes


def scene_analysis_progress(
    session: Session,
    run: AnalysisRun,
    *,
    failed_scene_id: int | None = None,
) -> SceneAnalysisProgress:
    revision, scenes = load_revision_scenes(session, run)
    completed: list[int] = []
    pending: list[int] = []
    for scene in scenes:
        if is_scene_analysis_complete(session, run.id, scene):
            completed.append(scene.id)
        else:
            pending.append(scene.id)
    failed_ids = [failed_scene_id] if failed_scene_id and failed_scene_id in pending else []
    # Also surface last failed scene from failure payload when present.
    if not failed_ids and run.provider_health_at_failure:
        try:
            payload = json.loads(run.provider_health_at_failure)
            failure = payload.get("failure") if isinstance(payload, dict) else None
            if isinstance(failure, dict) and failure.get("failed_scene_id"):
                sid = int(failure["failed_scene_id"])
                if sid in pending:
                    failed_ids = [sid]
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return SceneAnalysisProgress(
        total_scene_count=len(scenes),
        completed_scene_ids=completed,
        failed_scene_ids=failed_ids,
        pending_scene_ids=pending,
        completed_scene_count=len(completed),
        remaining_scene_count=len(pending),
        boundary_revision_id=revision.id if revision else None,
        coverage_rate=float(revision.coverage_rate) if revision else None,
    )


def pending_scenes_for_run(session: Session, run: AnalysisRun) -> list[Scene]:
    _revision, scenes = load_revision_scenes(session, run)
    return [scene for scene in scenes if not is_scene_analysis_complete(session, run.id, scene)]


def _map_scene_analysis_root_code(root_code: str, stage: str) -> str:
    mapping = {
        "PROVIDER_DISABLED": "PROVIDER_DISABLED",
        "PROVIDER_NOT_CONNECTED": "PROVIDER_NOT_CONNECTED",
        "PROVIDER_CONNECTION_ERROR": "PROVIDER_CONNECTION_ERROR",
        "PROVIDER_CONNECT_TIMEOUT": "PROVIDER_CONNECT_TIMEOUT",
        "PROVIDER_READ_TIMEOUT": "PROVIDER_READ_TIMEOUT",
        "PROVIDER_TLS_ERROR": "PROVIDER_TLS_ERROR",
        "JSON_PARSE_FAILED": "JSON_PARSE_FAILED",
        "SCHEMA_VALIDATION_FAILED": "SCHEMA_VALIDATION_FAILED",
        "EVIDENCE_VALIDATION_FAILED": "EVIDENCE_VALIDATION_FAILED",
        "BUSINESS_VALIDATION_FAILED": "BUSINESS_VALIDATION_FAILED",
        "DATABASE_LOCKED": "DATABASE_LOCKED",
    }
    if root_code in mapping:
        return mapping[root_code]
    if stage == "provider_request" and root_code.startswith("PROVIDER_"):
        return root_code
    if "locked" in root_code.lower() or "database is locked" in root_code.lower():
        return "DATABASE_LOCKED"
    if root_code in {"STRUCTURED_OUTPUT_ERROR", "SCENE_PIPELINE_FAILED"}:
        return "SCENE_ANALYSIS_START_FAILED"
    return root_code or "SCENE_ANALYSIS_START_FAILED"


def persist_scene_analysis_failure(
    session: Session,
    run: AnalysisRun,
    exc: Exception,
    *,
    failed_scene: Scene | None = None,
) -> None:
    """Persist accurate Stage-2 failure without rolling back completed scene artifacts."""
    progress = scene_analysis_progress(
        session,
        run,
        failed_scene_id=failed_scene.id if failed_scene else None,
    )
    root_code, stage, retryable, hint = classify_pipeline_error(exc)
    if isinstance(exc, Exception) and "database is locked" in str(exc).lower():
        root_code, stage, retryable, hint = (
            "DATABASE_LOCKED",
            "scene_analysis",
            True,
            "稍后重试；SQLite 短暂锁冲突",
        )
    mapped = _map_scene_analysis_root_code(root_code, stage)
    detail_message = str(exc).strip() or mapped
    run.error_code = "SCENE_ANALYSIS_FAILED"
    run.error_message = "Scene Analysis失败"
    run.root_error_code = mapped
    run.root_error_message = detail_message[:2000]
    run.failed_stage = "scene_analysis"
    run.retryable = bool(retryable)
    run.user_action_hint = hint
    run.completed_at = datetime.now(timezone.utc)
    if progress.completed_scene_count > 0 and progress.remaining_scene_count > 0:
        run.status = "scene_analysis_partial"
    else:
        run.status = "failed"

    failed_invocation_id: int | None = None
    transport_kind = None
    request_id = None
    exception_type = type(exc).__name__
    if isinstance(exc, StructuredOutputError):
        failed_invocation_id = exc.failed_invocation_id
        if exc.provider_error is not None:
            transport_kind = exc.provider_error.transport_kind
            request_id = exc.provider_error.request_id
            exception_type = type(exc.provider_error).__name__
    elif isinstance(exc, ProviderRequestError):
        transport_kind = exc.transport_kind
        request_id = exc.request_id
    if not failed_invocation_id:
        latest = session.scalar(
            select(ModelInvocation)
            .where(
                ModelInvocation.run_id == run.id,
                ModelInvocation.task_type == "scene_analysis",
            )
            .order_by(ModelInvocation.id.desc())
        )
        failed_invocation_id = latest.id if latest else None
    run.failed_invocation_id = failed_invocation_id

    last_resume_client_request_id = None
    if run.raw_output:
        try:
            prior = json.loads(run.raw_output)
            if isinstance(prior, dict):
                last_resume_client_request_id = prior.get("client_request_id") or prior.get(
                    "last_resume_client_request_id"
                )
        except json.JSONDecodeError:
            last_resume_client_request_id = None
    failure = {
        "error_code": mapped,
        "root_error_code": mapped,
        "root_error_message": run.root_error_message,
        "failed_stage": "scene_analysis",
        "exception_type": exception_type,
        "transport_kind": transport_kind,
        "retryable": run.retryable,
        "failed_invocation_id": failed_invocation_id,
        "failed_scene_id": failed_scene.id if failed_scene else None,
        "failed_scene_index": failed_scene.ordinal if failed_scene else None,
        "request_id": request_id,
        "user_action_hint": hint,
        "completed_scene_count": progress.completed_scene_count,
        "remaining_scene_count": progress.remaining_scene_count,
        "total_scene_count": progress.total_scene_count,
        "boundary_revision_id": progress.boundary_revision_id,
        "last_resume_client_request_id": last_resume_client_request_id,
    }
    if isinstance(exc, StructuredOutputError):
        failure.update(exc.as_safe_dict())
        failure["root_error_code"] = mapped
    elif isinstance(exc, ProviderRequestError):
        failure.update(exc.as_safe_dict())
        failure["root_error_code"] = mapped
    run.provider_health_at_failure = json.dumps(
        {"failure": failure}, ensure_ascii=False
    )
    run.raw_output = json.dumps(
        {"kind": "scene_analysis_failure", **failure}, ensure_ascii=False
    )


@dataclass(frozen=True)
class SceneFailurePointers:
    current_failed_scene_id: int | None
    current_failed_scene_index: int | None
    historical_failed_scene_id: int | None
    historical_failed_scene_index: int | None
    historical_failed_invocation_id: int | None
    offline_replay_available: bool
    offline_replay_scene_id: int | None
    failed_scene_http_attempts: int


def _failure_payload(run: AnalysisRun) -> dict:
    historical: dict = {}
    partial: dict = {}
    for source in (run.provider_health_at_failure, run.raw_output):
        if not source:
            continue
        try:
            payload = json.loads(source)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("kind") == "scene_analysis_failure":
            return payload
        failure = payload.get("failure")
        if isinstance(failure, dict) and failure.get("failed_scene_id") is not None:
            historical = failure
        if payload.get("kind") == "scene_analysis_partial":
            partial = payload
        elif payload.get("failed_scene_id") is not None:
            historical = payload
    if historical:
        return historical
    return partial


def resolve_scene_failure_pointers(
    session: Session,
    run: AnalysisRun,
    progress: SceneAnalysisProgress,
    *,
    find_replayable: Callable[[Session, int, Scene], object | None],
    count_http_attempts: Callable[[Session, int, Scene], int],
) -> SceneFailurePointers:
    """Artifact-first failure pointers; historical failures do not block resume."""
    payload = _failure_payload(run)
    historical_scene_id = payload.get("failed_scene_id")
    historical_scene_index = payload.get("failed_scene_index")
    historical_invocation_id = payload.get("failed_invocation_id") or run.failed_invocation_id
    if historical_scene_id is not None:
        historical_scene_id = int(historical_scene_id)
    if historical_scene_index is not None:
        historical_scene_index = int(historical_scene_index)
    if historical_invocation_id is not None:
        historical_invocation_id = int(historical_invocation_id)

    if historical_scene_id is not None and historical_scene_id in progress.completed_scene_ids:
        pass  # keep historical ids for audit display only
    elif historical_scene_id is not None and historical_scene_id not in progress.pending_scene_ids:
        historical_scene_id = None
        historical_scene_index = None

    offline_scene_id: int | None = None
    for scene_id in progress.pending_scene_ids:
        scene = session.get(Scene, scene_id)
        if scene is None or is_scene_analysis_complete(session, run.id, scene):
            continue
        if find_replayable(session, run.id, scene) is not None:
            offline_scene_id = scene.id
            break

    current_scene_id: int | None = None
    current_scene_index: int | None = None
    http_attempts = 0
    if offline_scene_id is not None:
        scene = session.get(Scene, offline_scene_id)
        if scene is not None:
            current_scene_id = scene.id
            current_scene_index = scene.ordinal
            http_attempts = count_http_attempts(session, run.id, scene)

    return SceneFailurePointers(
        current_failed_scene_id=current_scene_id,
        current_failed_scene_index=current_scene_index,
        historical_failed_scene_id=historical_scene_id,
        historical_failed_scene_index=historical_scene_index,
        historical_failed_invocation_id=historical_invocation_id,
        offline_replay_available=offline_scene_id is not None,
        offline_replay_scene_id=offline_scene_id,
        failed_scene_http_attempts=http_attempts,
    )


def sync_run_partial_display(session: Session, run: AnalysisRun) -> SceneAnalysisProgress:
    """Refresh partial-run display fields from valid artifacts (not stale failure blobs)."""
    progress = scene_analysis_progress(session, run)
    if progress.remaining_scene_count == 0:
        clear_scene_analysis_error_fields(run)
        run.status = "succeeded"
        from datetime import datetime, timezone

        run.completed_at = datetime.now(timezone.utc)
        session.commit()
        return progress
    run.status = "scene_analysis_partial"
    run.error_code = "SCENE_ANALYSIS_FAILED"
    run.error_message = "Scene Analysis部分完成"
    run.root_error_code = None
    run.root_error_message = None
    run.failed_stage = "scene_analysis"
    run.retryable = True
    run.user_action_hint = "可继续未完成Scene；如有可离线恢复的失败Scene请先离线重放"
    run.raw_output = json.dumps(
        {
            "kind": "scene_analysis_partial",
            "completed_scene_count": progress.completed_scene_count,
            "remaining_scene_count": progress.remaining_scene_count,
            "total_scene_count": progress.total_scene_count,
            "boundary_revision_id": progress.boundary_revision_id,
            "pending_scene_ids": progress.pending_scene_ids,
        },
        ensure_ascii=False,
    )
    session.commit()
    return progress


def clear_scene_analysis_error_fields(run: AnalysisRun) -> None:
    """Clear current-error display fields; keep historical invocations."""
    run.error_code = None
    run.error_message = None
    run.root_error_code = None
    run.root_error_message = None
    run.failed_stage = None
    run.failed_invocation_id = None
    run.provider_health_at_failure = None
    run.retryable = False
    run.user_action_hint = None
    run.raw_output = None
    run.completed_at = None
