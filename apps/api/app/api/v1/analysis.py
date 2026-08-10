import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.v1.router import error
from app.core.config import get_settings
from app.db.models import (
    AnalysisArtifact,
    AnalysisRun,
    ApplicationSetting,
    BoundaryDetectionBatchCheckpoint,
    BoundaryReviewSession,
    BoundaryRevision,
    Chapter,
    CloudBudgetReservation,
    ModelInvocation,
    Paragraph,
    RequestGateDecision,
    Scene,
)
from app.db.session import get_db, get_session_factory
from app.model_gateway.gateway import ModelGateway, ProviderNotFoundError
from app.model_gateway.registry import get_model_gateway
from app.schemas.scene import (
    AnalysisRunAccepted,
    AnalysisRunCreate,
    BoundaryRecoveryContinueRequest,
    BoundaryRecoveryContinueResponse,
    BoundaryRecoveryPreflightResponse,
    BoundaryRecoverPreflightResponse,
    BoundaryRecoveryPreflightRequest,
    AnalysisPreflightRequest,
    AnalysisPreflightResponse,
    AnalysisRunResponse,
    ArtifactResponse,
    ModelInvocationResponse,
    ProviderStatusResponse,
    SceneAnalysisOfflineReplayRequest,
    SceneAnalysisOfflineReplayResponse,
    SceneAnalysisResumePreflightRequest,
    SceneAnalysisResumePreflightResponse,
    SceneAnalysisResumeRequest,
    SceneParagraphItem,
    SceneParagraphsResponse,
    SceneResponse,
    RunResultsResponse,
    RunResultsRunInfo,
    RunResultsChapterInfo,
    RunResultsBoundaryRevisionInfo,
    RunResultsSummary,
    SceneResultItem,
    SceneResultScene,
    SceneResultArtifact,
    SceneEvidenceItem,
)
from app.services.prompt_service import load_prompt
from app.services.scene_pipeline import execute_scene_pipeline
from app.schemas.settings import CloudBudgetUpdate
from app.services.budget_reservation import (
    InsufficientBudgetReservation,
    active_reservation_totals,
    available_remaining,
    reserve_budget,
)
from app.services.cloud_budget import daily_usage
from app.services.cloud_pricing import pricing_status
from app.services.credentials.base import CredentialStore
from app.services.credentials.service import get_credential_store
from app.services.analysis_execution_plan import build_analysis_execution_plan
from app.services.provider_eligibility import (
    ProviderEligibilityService,
    evaluate_manual_boundary_candidate,
    provider_eligibility,
)
from app.services.staged_budget import (
    STAGE_ANALYSIS,
    STAGE_BOUNDARY,
    estimate_stage1_boundary,
    estimate_stage1_boundary_remaining,
    estimate_stage2_scene_analysis,
    exceeded_dimensions,
)
from app.services.boundary_review_service import analyze_confirmed_review
from app.services.boundary_detection_checkpoints import (
    clone_recovered_checkpoints,
    recover_boundary_detection_from_invocations,
)
from app.services.provider_runtime_service import ProviderRuntimeService
from app.services.scene_analysis_progress import (
    clear_scene_analysis_error_fields,
    pending_scenes_for_run,
    resolve_scene_failure_pointers,
    scene_analysis_progress,
)
from app.services.scene_analysis_offline_replay import (
    SCENE_ANALYSIS_MAX_HTTP_ATTEMPTS,
    _scene_paragraphs,
    count_scene_http_attempts,
    find_replayable_scene_invocation,
    offline_replay_scene_analysis,
)
from app.services.scene_pipeline import (
    describe_scene_validation_failure,
    normalize_scene_analysis_result,
    validate_scene_analysis,
)
from app.schemas.scene import SceneAnalysisResult
from app.services.scene_results_service import build_run_results, RunResultsBundle

router = APIRouter(prefix="/api/v1")


def _budget_http_error(exc: InsufficientBudgetReservation) -> HTTPException:
    return HTTPException(status_code=409, detail=exc.as_error_detail())


def _load_budget_block(run: AnalysisRun) -> dict:
    if not run.raw_output:
        return {}
    try:
        payload = json.loads(run.raw_output)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) and payload.get("kind") == "budget_block" else {}


def _build_scene_validation_detail(
    session: Session,
    failure_pointers,
    invocation: ModelInvocation | None,
) -> dict | None:
    target_id = (
        failure_pointers.historical_failed_scene_id
        or failure_pointers.offline_replay_scene_id
        or failure_pointers.current_failed_scene_id
    )
    if target_id is None or invocation is None or not invocation.parsed_response_json:
        return None
    scene = session.get(Scene, int(target_id))
    if scene is None:
        return None
    try:
        included = _scene_paragraphs(session, scene)
        allowed = {item.id for item in included}
        raw = SceneAnalysisResult.model_validate(json.loads(invocation.parsed_response_json))
        normalized = normalize_scene_analysis_result(raw, allowed)
        detail = describe_scene_validation_failure(
            raw, allowed, invocation.error_message or ""
        )
        detail["offline_replay_eligible"] = False
        try:
            validate_scene_analysis(normalized, scene.scene_key, allowed, True)
            detail["offline_replay_eligible"] = True
        except ValueError as exc:
            detail["post_normalization_error"] = str(exc)
        return detail
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def serialize_run(session: Session, run: AnalysisRun) -> AnalysisRunResponse:
    # Whole-book overview runs are not chapter scene pipelines — skip heavy enrichment
    # so Task Center listing never depends on Provider / journey / checkpoint paths.
    if (run.task_type or "") == "whole_book_overview" or (run.subject_type or "") == "book":
        base = AnalysisRunResponse.model_validate(run)
        failed_invocation = None
        failed_window_index = None
        inv_id = run.failed_invocation_id
        if inv_id is None:
            # Fallback: latest failed window's provider attempt.
            from app.db.models import WholeBookRunWindow

            failed_win = session.scalar(
                select(WholeBookRunWindow)
                .where(
                    WholeBookRunWindow.run_id == run.id,
                    WholeBookRunWindow.status == "failed",
                )
                .order_by(WholeBookRunWindow.window_index.asc())
            )
            if failed_win is not None:
                failed_window_index = int(failed_win.window_index)
                inv_id = failed_win.provider_attempt_id
        else:
            from app.db.models import WholeBookRunWindow

            failed_win = session.scalar(
                select(WholeBookRunWindow)
                .where(
                    WholeBookRunWindow.run_id == run.id,
                    WholeBookRunWindow.status == "failed",
                )
                .order_by(WholeBookRunWindow.window_index.asc())
            )
            if failed_win is not None:
                failed_window_index = int(failed_win.window_index)
        if inv_id is not None:
            inv = session.get(ModelInvocation, inv_id)
            if inv is not None:
                parsed_meta: dict = {}
                try:
                    raw_parsed = json.loads(inv.parsed_response_json or "{}")
                    if isinstance(raw_parsed, dict):
                        parsed_meta = raw_parsed
                except json.JSONDecodeError:
                    parsed_meta = {}
                failed_invocation = {
                    "id": inv.id,
                    "invocation_kind": inv.invocation_kind,
                    "attempt_no": inv.attempt_no,
                    "http_request_sent": inv.http_request_sent,
                    "http_status": inv.http_status_code,
                    "http_status_code": inv.http_status_code,
                    "json_valid": inv.parsed_response_json is not None,
                    "schema_valid": inv.error_code
                    not in {"PROVIDER_OUTPUT_INVALID", "SCHEMA_VALIDATION_FAILED"},
                    "error_code": inv.error_code,
                    "error_message": inv.error_message,
                    "finish_reason": inv.finish_reason,
                    "input_tokens": inv.input_tokens,
                    "output_tokens": inv.output_tokens,
                    "total_tokens": inv.total_tokens,
                    "estimated_cost": inv.estimated_cost,
                    "latency_ms": inv.latency_ms,
                    "request_id": inv.request_id,
                    "provider_name": inv.provider_name,
                    "model_name": inv.model_name,
                    "repair_attempted": bool(parsed_meta.get("repair_attempted")),
                    "text_len": parsed_meta.get("text_len"),
                    "has_json_fence": parsed_meta.get("has_json_fence"),
                }
        return base.model_copy(
            update={
                "current_stage": run.failed_stage or run.status,
                "effective_status": run.status,
                "actual_failed_stage": run.failed_stage,
                "chapter_complete": False,
                "scene_pipeline_complete": False,
                "failed_invocation": failed_invocation,
                "failed_invocation_id": inv_id or run.failed_invocation_id,
                "failed_scene_index": failed_window_index,
                "validation_error_code": run.error_code,
            }
        )

    block = _load_budget_block(run)
    reservation = session.scalar(
        select(CloudBudgetReservation)
        .where(CloudBudgetReservation.run_id == run.id)
        .order_by(desc(CloudBudgetReservation.id))
    )
    stage_map = {
        "queued": STAGE_BOUNDARY,
        "running": STAGE_BOUNDARY,
        "boundary_candidates_running": STAGE_BOUNDARY,
        "awaiting_boundary_review": "boundary_review",
        "boundary_confirmed": STAGE_ANALYSIS,
        "boundary_confirmed_budget_blocked": STAGE_ANALYSIS,
        "scene_analysis_running": STAGE_ANALYSIS,
        "scene_analysis_partial": STAGE_ANALYSIS,
        "awaiting_provider_recovery": STAGE_ANALYSIS,
        "succeeded": "completed",
    }
    failure_details = None
    failed_invocation = None
    validation_error_code = None
    failed_transition_id = None
    failed_batch_index = None
    legacy_classification_warning = False
    if run.provider_health_at_failure:
        try:
            payload = json.loads(run.provider_health_at_failure)
            if isinstance(payload, dict) and "failure" in payload:
                failure_details = payload.get("failure")
            elif isinstance(payload, dict) and "provider_name" in payload:
                failure_details = {"health": payload}
        except json.JSONDecodeError:
            failure_details = None
    if (
        run.root_error_code == "BUSINESS_VALIDATION_FAILED"
        and run.failed_invocation_id
    ):
        inv = session.get(ModelInvocation, run.failed_invocation_id)
        if inv is not None and (inv.error_code or "").startswith("PROVIDER"):
            legacy_classification_warning = True
    invocation = (
        session.get(ModelInvocation, run.failed_invocation_id)
        if run.failed_invocation_id
        else None
    )
    if invocation is not None:
        validation_error_code = invocation.error_code
        failed_invocation = {
            "id": invocation.id,
            "invocation_kind": invocation.invocation_kind,
            "attempt_no": invocation.attempt_no,
            "http_request_sent": invocation.http_request_sent,
            "http_status": invocation.http_status_code,
            "json_valid": invocation.parsed_response_json is not None,
            "schema_valid": (
                invocation.parsed_response_json is not None
                and invocation.error_code != "SCHEMA_VALIDATION_FAILED"
            ),
            "error_code": invocation.error_code,
            "error_message": invocation.error_message,
            "finish_reason": invocation.finish_reason,
            "requested_output_tokens": invocation.requested_output_tokens,
            "input_tokens": invocation.input_tokens,
            "output_tokens": invocation.output_tokens,
            "total_tokens": invocation.total_tokens,
            "estimated_cost": invocation.estimated_cost,
            "latency_ms": invocation.latency_ms,
            "request_id": invocation.request_id,
        }
    checkpoints = list(
        session.scalars(
            select(BoundaryDetectionBatchCheckpoint)
            .where(BoundaryDetectionBatchCheckpoint.run_id == run.id)
            .order_by(BoundaryDetectionBatchCheckpoint.batch_index)
        )
    )
    reusable = [
        item
        for item in checkpoints
        if item.status in {"completed", "conflicted_completed"}
    ]
    conflicted_count = sum(
        item.status == "conflicted_completed" for item in reusable
    )
    checkpoint_total_count = len(checkpoints)
    for checkpoint in checkpoints:
        if checkpoint.invocation_id == run.failed_invocation_id:
            failed_batch_index = checkpoint.batch_index
            issues = json.loads(checkpoint.issues_json or "[]")
            if issues:
                failed_transition_id = issues[0].get("transition_id")
                validation_error_code = issues[0].get("conflict_code")
            break
    if (
        not checkpoints
        and run.prompt_version == "v3.5"
        and run.failed_invocation_id
    ):
        try:
            from app.services.boundary_detection_checkpoints import (
                recover_boundary_detection_from_invocations,
            )

            recovery = recover_boundary_detection_from_invocations(
                session, run.id, persist=False
            )
            reusable = recovery.recovered
            conflicted_count = recovery.conflicted_batch_count
            checkpoint_total_count = recovery.total_detection_batch_count
            for item in recovery.recovered:
                if item.get("invocation_id") == run.failed_invocation_id:
                    failed_batch_index = int(item["batch_index"])
                    issues = item.get("issues") or []
                    if issues:
                        issue = issues[0]
                        failed_transition_id = str(issue.get("transition_id"))
                        validation_error_code = str(issue.get("conflict_code"))
                    break
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    progress = scene_analysis_progress(session, run)
    failure_pointers = resolve_scene_failure_pointers(
        session,
        run,
        progress,
        find_replayable=find_replayable_scene_invocation,
        count_http_attempts=count_scene_http_attempts,
    )
    failed_scene_id = failure_pointers.current_failed_scene_id
    failed_scene_index = failure_pointers.current_failed_scene_index
    historical_failed_scene_id = failure_pointers.historical_failed_scene_id
    historical_failed_scene_index = failure_pointers.historical_failed_scene_index
    historical_failed_invocation_id = failure_pointers.historical_failed_invocation_id
    offline_replay_available = failure_pointers.offline_replay_available
    failed_scene_http_attempts = failure_pointers.failed_scene_http_attempts
    scene_validation_detail = _build_scene_validation_detail(
        session, failure_pointers, invocation
    )
    detection_stages = {
        "provider_request",
        "boundary_candidates",
        "boundary_detection",
        "json_validation",
        "schema_validation",
        "structured_output",
        "structural_validation",
        "business_validation",
    }
    remaining_detection = max(0, checkpoint_total_count - len(reusable))
    detection_recovery_available = bool(
        remaining_detection > 0
        and (
            run.status in {"boundary_candidates_partial", "failed_provider", "failed_structural"}
            or (
                str(run.status).startswith("failed")
                and (run.failed_stage or "") in detection_stages
            )
        )
    )
    scene_analysis_resume_available = bool(
        progress.total_scene_count > 0
        and progress.remaining_scene_count > 0
        and (
            run.status
            in {
                "boundary_confirmed",
                "boundary_confirmed_budget_blocked",
                "scene_analysis_partial",
                "awaiting_provider_recovery",
            }
            or (
                run.status == "failed"
                and run.failed_stage in {"scene_analysis", "scene_analysis_budget"}
            )
        )
    )
    offline_replay_available = failure_pointers.offline_replay_available
    failed_scene_http_attempts = failure_pointers.failed_scene_http_attempts
    if (
        run.failed_stage == "scene_analysis"
        or run.status in {"scene_analysis_partial", "awaiting_provider_recovery"}
    ):
        detection_recovery_available = False
        remaining_detection = 0
    base = AnalysisRunResponse.model_validate(run)
    from app.services.chapter_analysis_completion import chapter_completion_payload

    chapter_meta = chapter_completion_payload(session, run)
    # Map stage for UI checklist while journey is pending/running.
    current_stage = stage_map.get(
        run.status, run.failed_stage if run.status.startswith("failed") else run.status
    )
    if chapter_meta["effective_status"] in {"partial_complete", "journey_running", "journey_failed"}:
        current_stage = "reader_journey"
    elif chapter_meta["chapter_complete"]:
        current_stage = "completed"

    # CHG-20260728-040: aggregate invocation usage even when reservation is released.
    inv_rows = list(
        session.scalars(select(ModelInvocation).where(ModelInvocation.run_id == run.id))
    )
    usage_invocation_count = len(inv_rows)
    usage_input = sum(int(i.input_tokens or 0) for i in inv_rows)
    usage_output = sum(int(i.output_tokens or 0) for i in inv_rows)
    usage_total = sum(int(i.total_tokens or 0) for i in inv_rows)
    cost_values = [i.estimated_cost for i in inv_rows if i.estimated_cost is not None]
    usage_cost_unknown = bool(inv_rows) and len(cost_values) < len(inv_rows)
    usage_estimated_cost = float(sum(cost_values)) if cost_values else None

    failure_substage = None
    failure_reason_code = run.root_error_code
    if run.root_error_code and str(run.root_error_code).startswith("SCENE_BOUNDARY_"):
        failure_substage = "scene_boundary_adjudication"
    elif any(i.task_type == "scene_boundary_adjudication" for i in inv_rows) and (
        run.status.startswith("failed") or run.root_error_code in {"OUTPUT_TRUNCATED"}
    ):
        failure_substage = "scene_boundary_adjudication"

    from app.db.models import AnalysisArtifact
    from app.services.boundary_adjudication_checkpoints import (
        ARTIFACT_TYPE,
        load_adjudication_plan,
    )

    adj_artifacts = list(
        session.scalars(
            select(AnalysisArtifact).where(
                AnalysisArtifact.run_id == run.id,
                AnalysisArtifact.artifact_type == ARTIFACT_TYPE,
            )
        )
    )
    boundary_batch_completed = len(adj_artifacts)
    boundary_candidate_completed = 0
    for art in adj_artifacts:
        try:
            payload = json.loads(art.payload_json or "{}")
            boundary_candidate_completed += len(payload.get("target_candidate_ids") or [])
        except json.JSONDecodeError:
            pass

    plan = load_adjudication_plan(session, run_id=run.id)
    if plan is None and (run.recovered_from_run_id or run.retry_of_run_id):
        plan = load_adjudication_plan(
            session,
            run_id=int(run.recovered_from_run_id or run.retry_of_run_id),
        )

    boundary_candidate_total = None
    boundary_batch_total = None
    adj_invs = [i for i in inv_rows if i.task_type == "scene_boundary_adjudication"]
    if plan:
        boundary_candidate_total = int(plan.get("boundary_candidate_total") or 0) or None
        boundary_batch_total = int(plan.get("boundary_batch_total") or 0) or None
    if adj_invs or adj_artifacts or failure_substage == "scene_boundary_adjudication":
        if boundary_candidate_total is None:
            selected: list[str] = []
            for i in inv_rows:
                if i.task_type != "scene_boundary" or not i.selected_transition_ids_json:
                    continue
                try:
                    selected.extend(json.loads(i.selected_transition_ids_json))
                except json.JSONDecodeError:
                    pass
            if selected:
                boundary_candidate_total = len(list(dict.fromkeys(selected)))
            elif adj_artifacts:
                boundary_candidate_total = boundary_candidate_completed or None
        if boundary_candidate_total is not None and boundary_batch_total is None:
            from math import ceil

            boundary_batch_total = max(
                boundary_batch_completed,
                int(ceil(boundary_candidate_total / 10)) if boundary_candidate_total else 0,
            )
        if boundary_batch_total is not None:
            boundary_batch_total = max(boundary_batch_total, boundary_batch_completed)

    last_adj = adj_invs[-1] if adj_invs else None
    trunc_attempts = sum(
        1
        for i in adj_invs
        if i.finish_reason in {"length", "max_tokens"}
        or (i.error_code or "").endswith("TRUNCATED")
        or (i.error_code or "").endswith("TRUNCATED_AT_HARD_CAP")
    )

    return base.model_copy(
        update={
            "budget_required": block.get("required"),
            "budget_remaining": block.get("remaining"),
            "exceeded_dimensions": block.get("exceeded_dimensions"),
            "reservation_status": reservation.status if reservation else None,
            "current_stage": current_stage,
            "failure_details": failure_details,
            "legacy_classification_warning": legacy_classification_warning,
            "exception_type": (failure_details or {}).get("exception_type"),
            "transport_kind": (failure_details or {}).get("transport_kind"),
            "actual_failed_stage": run.failed_stage,
            "failed_invocation": failed_invocation,
            "validation_error_code": validation_error_code,
            "failed_transition_id": failed_transition_id,
            "failed_batch_index": failed_batch_index,
            "reusable_checkpoint_count": len(reusable),
            "conflicted_checkpoint_count": conflicted_count,
            "checkpoint_total_count": checkpoint_total_count,
            "checkpoint_available": detection_recovery_available,
            "recovered_from_run_id": run.recovered_from_run_id,
            "scene_analysis_resume_available": scene_analysis_resume_available,
            "detection_recovery_available": detection_recovery_available,
            "remaining_detection_batch_count": remaining_detection if detection_recovery_available else 0,
            "boundary_revision_id": progress.boundary_revision_id,
            "total_scene_count": progress.total_scene_count,
            "completed_scene_count": progress.completed_scene_count,
            "remaining_scene_count": progress.remaining_scene_count,
            "failed_scene_id": int(failed_scene_id) if failed_scene_id is not None else None,
            "failed_scene_index": int(failed_scene_index) if failed_scene_index is not None else None,
            "historical_failed_scene_id": (
                int(historical_failed_scene_id)
                if historical_failed_scene_id is not None
                else None
            ),
            "historical_failed_scene_index": (
                int(historical_failed_scene_index)
                if historical_failed_scene_index is not None
                else None
            ),
            "historical_failed_invocation_id": (
                int(historical_failed_invocation_id)
                if historical_failed_invocation_id is not None
                else None
            ),
            "scene_analysis_coverage_rate": progress.coverage_rate,
            "offline_replay_available": offline_replay_available,
            "failed_scene_http_attempts": failed_scene_http_attempts,
            "scene_analysis_max_http_attempts": SCENE_ANALYSIS_MAX_HTTP_ATTEMPTS,
            "completed_scene_ids": progress.completed_scene_ids,
            "remaining_scene_ids": progress.pending_scene_ids,
            "scene_validation_detail": scene_validation_detail,
            "chapter_complete": chapter_meta["chapter_complete"],
            "scene_pipeline_complete": chapter_meta["scene_pipeline_complete"],
            "effective_status": chapter_meta["effective_status"],
            "checkpoint_stage": chapter_meta["checkpoint_stage"],
            "resume_stage": chapter_meta["resume_stage"],
            "journey_run_id": chapter_meta["journey_run_id"],
            "journey_status": chapter_meta["journey_status"],
            "journey_completed_scene_count": chapter_meta.get(
                "journey_completed_scene_count"
            ),
            "journey_total_scene_count": chapter_meta.get("journey_total_scene_count"),
            "journey_retryable": chapter_meta.get("journey_retryable"),
            "journey_result_available": bool(
                chapter_meta.get("journey_result_available")
            ),
            "journey_error_code": chapter_meta.get("journey_error_code"),
            "primary_action": chapter_meta.get("primary_action"),
            "failure_substage": failure_substage,
            "failure_reason_code": failure_reason_code,
            "boundary_candidate_total": boundary_candidate_total,
            "boundary_candidate_completed": boundary_candidate_completed,
            "boundary_batch_total": boundary_batch_total,
            "boundary_batch_completed": boundary_batch_completed,
            "usage_invocation_count": usage_invocation_count,
            "usage_input_tokens": usage_input if usage_invocation_count else None,
            "usage_output_tokens": usage_output if usage_invocation_count else None,
            "usage_total_tokens": usage_total if usage_invocation_count else None,
            "usage_estimated_cost": usage_estimated_cost,
            "usage_cost_unknown": usage_cost_unknown,
            "last_requested_output_tokens": (
                last_adj.requested_output_tokens if last_adj else None
            ),
            "last_actual_output_tokens": (
                last_adj.actual_output_tokens or last_adj.output_tokens if last_adj else None
            ),
            "last_finish_reason": last_adj.finish_reason if last_adj else None,
            "truncation_attempt_count": trunc_attempts if adj_invs else None,
            "status_version": int(getattr(run, "status_version", 0) or 0),
            "cancellation_requested_at": getattr(run, "cancellation_requested_at", None),
            "cancelled_at": getattr(run, "cancelled_at", None),
            "cancellation_reason": getattr(run, "cancellation_reason", None),
            "cancelled_by": getattr(run, "cancelled_by", None),
            "can_cancel": _run_can_cancel(run),
            "can_restart_as_new_task": run.status
            in {
                "cancelled",
                "failed",
                "failed_provider",
                "failed_structural",
                "succeeded",
                "completed",
            },
        }
    )


def _run_can_cancel(run: AnalysisRun) -> bool:
    from app.services.task_cancellation import CANCELABLE_STATUSES, CANCEL_IN_PROGRESS

    if run.status in CANCEL_IN_PROGRESS:
        return False
    return run.status in CANCELABLE_STATUSES


class AnalysisRunCancelRequest(BaseModel):
    reason: str = "user_requested"
    expected_version: int | None = None
    client_request_id: str | None = None


class AnalysisRunCancelResponse(BaseModel):
    task_id: int
    previous_status: str
    current_status: str
    cancellation_requested_at: datetime | None = None
    cancelled_at: datetime | None = None
    message: str
    already_requested: bool = False
    already_cancelled: bool = False
    already_completed: bool = False
    cannot_cancel: bool = False
    can_restart_as_new_task: bool = True
    status_version: int = 0



@router.get("/analysis-runs", response_model=list[AnalysisRunResponse])
def list_analysis_runs(
    status: str | None = None,
    provider: str | None = None,
    book_id: int | None = None,
    offset: int = 0,
    limit: int = 50,
    session: Session = Depends(get_db),
) -> list[AnalysisRunResponse]:
    query = select(AnalysisRun)
    if status:
        query = query.where(AnalysisRun.status == status)
    if provider:
        query = query.where(AnalysisRun.provider == provider)
    if book_id is not None:
        chapter_ids = select(Chapter.id).where(Chapter.book_id == book_id)
        book_subject = str(int(book_id))
        query = query.where(
            (AnalysisRun.subject_id.in_(chapter_ids))
            | (
                (AnalysisRun.subject_type == "book")
                & (AnalysisRun.subject_id == book_subject)
            )
            | (AnalysisRun.book_id == int(book_id))
        )
    runs = list(
        session.scalars(
            query.order_by(desc(AnalysisRun.created_at)).offset(offset).limit(min(limit, 200))
        )
    )
    serialized = [serialize_run(session, run) for run in runs]
    # CHG-084: ensure WholeBookRun projections appear even if shadow AnalysisRun missing.
    from app.narrative_core.whole_book_v2.task_center_projection import (
        merge_whole_book_runs_into_task_list,
    )

    return merge_whole_book_runs_into_task_list(
        session,
        serialized,
        status=status,
        provider=provider,
        book_id=book_id,
        limit=min(limit, 200),
    )


@router.get("/model-providers", response_model=list[ProviderStatusResponse])
async def providers(
    gateway: ModelGateway = Depends(get_model_gateway),
    session: Session = Depends(get_db),
    store: CredentialStore = Depends(get_credential_store),
) -> list[ProviderStatusResponse]:
    from app.services.provider_runtime import bind_gateway_runtime

    bind_gateway_runtime(gateway, session, store)
    result = []
    for provider in gateway.providers():
        capabilities = provider.capabilities()
        health = None if capabilities.cloud else await provider.health()
        eligibility = evaluate_manual_boundary_candidate(
            session, provider_name=provider.name, capabilities=capabilities,
            store=store, pricing_path=Path("config/cloud_pricing.json"),
        ) if capabilities.cloud else provider_eligibility(
            session, provider_name=provider.name, capabilities=capabilities,
            healthy=health.status == "healthy", store=store,
            pricing_path=Path("config/cloud_pricing.json"),
        )
        if capabilities.cloud:
            readiness = all(
                bool(eligibility[field])
                for field in ("enabled", "configured", "connected", "credential_configured")
            )
            eligibility["healthy"] = readiness and bool(eligibility["enabled"])
            if not eligibility["enabled"]:
                status = "disabled"
                detail = "provider_disabled"
            else:
                status = "healthy" if readiness else "unhealthy"
                detail = "configuration readiness (no external request)"
        else:
            status = health.status
            detail = health.detail
        # Keep capabilities.enabled aligned with ProviderConfiguration for cloud.
        caps = capabilities.model_copy(update={"enabled": bool(eligibility["enabled"])})
        result.append(
            ProviderStatusResponse.model_validate({
                "capability_schema_version": "1c-a-2",
                "name": provider.name,
                "default_model": provider.default_model,
                "capabilities": caps,
                **eligibility,
                "supports_boundary_candidates": capabilities.supports_boundary_candidates,
                "requires_boundary_review": capabilities.requires_boundary_review,
                "automatic_boundary_routing": capabilities.automatic_boundary_routing,
                "running": health.status == "healthy" if not capabilities.cloud else None,
                "status": status,
                "detail": detail,
                "eligible_for_automatic_analysis": (
                    eligibility["automatic_route_eligible"]
                    if capabilities.cloud
                    else capabilities.enabled
                    and not capabilities.manual_only
                    and health.status == "healthy"
                ),
                "eligibility_status": eligibility.get("status", "eligible" if eligibility["manual_boundary_candidate_eligible"] else "blocked"),
                "evaluated_at": eligibility.get("evaluated_at", datetime.now(timezone.utc).isoformat()),
                "health_state": eligibility.get("health_state", "healthy" if eligibility["healthy"] else "unhealthy"),
                "health_source": eligibility.get("health_source", "live_probe"),
                "health_checked_at": eligibility.get("health_checked_at", datetime.now(timezone.utc).isoformat()),
                "provider_state_version": eligibility.get("provider_state_version", "local-live"),
            })
        )
    return result


@router.get("/analysis-execution-plan")
def get_analysis_execution_plan(
    mode: str = "BALANCED",
    gateway: ModelGateway = Depends(get_model_gateway),
    session: Session = Depends(get_db),
    store: CredentialStore = Depends(get_credential_store),
) -> dict:
    """Zero-network start-analysis readiness plan (SSOT for dialog gate)."""
    from app.services.provider_runtime import bind_gateway_runtime

    bind_gateway_runtime(gateway, session, store)
    plan = build_analysis_execution_plan(
        session,
        gateway=gateway,
        store=store,
        mode=mode,
        pricing_path=Path("config/cloud_pricing.json"),
    )
    return plan.as_dict()


def _preflight_estimate(session: Session, chapter_id: int) -> tuple[int, int, float]:
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    estimate = estimate_stage1_boundary(paragraphs)
    return (
        estimate.worst_case_request_count,
        estimate.worst_case_total_tokens,
        estimate.worst_case_cost,
    )


@router.post("/analysis-runs/preflight", response_model=AnalysisPreflightResponse)
def analysis_preflight(
    request: AnalysisPreflightRequest,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    store: CredentialStore = Depends(get_credential_store),
) -> AnalysisPreflightResponse:
    chapter = session.get(Chapter, request.chapter_id)
    if chapter is None:
        raise error(404, "CHAPTER_NOT_FOUND", "章节不存在")
    provider = gateway.get(request.provider)
    if request.capability_schema_version != "1c-a-2":
        raise error(409, "PROVIDER_STATE_CHANGED", "Provider能力契约已更新，请刷新后重新确认。")
    evaluation = evaluate_manual_boundary_candidate(
        session, provider_name=provider.name, capabilities=provider.capabilities(),
        store=store, pricing_path=Path("config/cloud_pricing.json"),
    )
    if request.provider_state_version != evaluation["provider_state_version"]:
        raise error(409, "PROVIDER_STATE_CHANGED", "Provider状态已变化，请刷新后重新确认。")
    health_state = evaluation["health_state"]
    health_error = evaluation.get("health_error_code")
    if health_state == "stale" or health_error == "PROVIDER_HEALTH_STALE":
        raise error(
            409,
            "PROVIDER_HEALTH_STALE",
            "AI 服务健康状态已过期，请重新验证连接。",
            details={
                "provider": request.provider,
                "health_source": evaluation.get("health_source"),
                "health_checked_at": evaluation.get("health_checked_at"),
                "freshness_age_seconds": evaluation.get("freshness_age_seconds"),
                "health_ttl_seconds": evaluation.get("health_ttl_seconds"),
            },
        )
    if health_error == "PROVIDER_HEALTH_NOT_VERIFIED":
        raise error(409, "PROVIDER_HEALTH_NOT_VERIFIED", "AI 服务尚未验证，请先在设置中完成验证。")
    if health_error == "PROVIDER_MODEL_NOT_VERIFIED":
        raise error(
            409,
            "PROVIDER_MODEL_NOT_VERIFIED",
            "当前分析模式将使用的模型尚未验证，请先验证该模型。",
        )
    if health_error == "PROVIDER_CREDENTIAL_CHANGED":
        raise error(409, "PROVIDER_CREDENTIAL_CHANGED", "API Key 或凭据已变化，请重新验证连接。")
    if health_error == "PROVIDER_CONFIGURATION_INCOMPLETE":
        raise error(
            409,
            "PROVIDER_CONFIGURATION_INCOMPLETE",
            "AI 服务配置已变化或不完整，请检查设置后重新验证。",
        )
    if health_state == "unhealthy":
        raise error(409, "PROVIDER_UNHEALTHY", "Provider健康检查失败。")
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == chapter.id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    pricing_path = Path("config/cloud_pricing.json")
    estimate = estimate_stage1_boundary(paragraphs, pricing_path=pricing_path)
    cloud_row = session.get(ApplicationSetting, "cloud_enabled")
    budget_row = session.get(ApplicationSetting, "cloud_budget_settings")
    cloud_enabled = bool(json.loads(cloud_row.value_json)) if cloud_row else False
    budget = CloudBudgetUpdate.model_validate(
        json.loads(budget_row.value_json) if budget_row else {}
    ).model_dump()
    pricing = pricing_status(pricing_path)
    usage = daily_usage(session, budget, cloud_enabled, pricing)
    active_req, active_tok, active_cost = active_reservation_totals(session)
    remaining = available_remaining(
        remaining_requests=usage["remaining_requests"],
        remaining_tokens=usage["remaining_tokens"],
        remaining_cost=usage["remaining_estimated_cost"],
        reserved_requests=active_req,
        reserved_tokens=active_tok,
        reserved_cost=active_cost,
    )
    required = estimate.required
    exceeded = exceeded_dimensions(required, remaining)
    within = not exceeded and "budget_unavailable" not in evaluation["manual_selection_blockers"]
    session.add(
        RequestGateDecision(
            run_id=None,
            allowed=within and bool(evaluation["manual_boundary_candidate_eligible"]),
            reason_code=(
                "PREFLIGHT_WITHIN_BUDGET" if within else "PREFLIGHT_INSUFFICIENT_BUDGET"
            ),
            budget_snapshot_json=json.dumps(
                {
                    "stage": STAGE_BOUNDARY,
                    "required": required.__dict__,
                    "remaining": remaining.__dict__,
                    "exceeded_dimensions": exceeded,
                },
                sort_keys=True,
            ),
            estimated_request_cost=required.estimated_cost,
        )
    )
    session.commit()
    return AnalysisPreflightResponse(
        eligible=bool(evaluation["manual_boundary_candidate_eligible"]) and within,
        blockers=list(evaluation["manual_selection_blockers"])
        + ([f"budget:{dim}" for dim in exceeded] if exceeded else []),
        provider_health_state=evaluation["health_state"],
        health_source=evaluation["health_source"],
        evaluated_at=evaluation["evaluated_at"],
        provider_state_version=evaluation["provider_state_version"],
        estimated_requests=estimate.expected_request_count,
        estimated_tokens=estimate.estimated_total_tokens,
        estimated_cost=estimate.estimated_cost,
        within_budget=within,
        capability_schema_version="1c-a-2",
        analysis_mode=request.analysis_mode,
        stage=STAGE_BOUNDARY,
        paragraph_count=estimate.paragraph_count,
        transition_count=estimate.transition_count,
        detection_batch_count=estimate.detection_batch_count,
        adjudication_batch_count_estimated=estimate.adjudication_batch_count_estimated,
        scene_count=0,
        expected_request_count=estimate.expected_request_count,
        worst_case_request_count=estimate.worst_case_request_count,
        estimated_input_tokens=estimate.estimated_input_tokens,
        worst_case_input_tokens=estimate.worst_case_input_tokens,
        estimated_output_tokens=estimate.estimated_output_tokens,
        worst_case_output_tokens=estimate.worst_case_output_tokens,
        estimated_total_tokens=estimate.estimated_total_tokens,
        worst_case_total_tokens=estimate.worst_case_total_tokens,
        worst_case_cost=estimate.worst_case_cost,
        currency=estimate.currency,
        remaining={
            "requests": remaining.requests,
            "tokens": remaining.tokens,
            "estimated_cost": remaining.estimated_cost,
        },
        exceeded_dimensions=exceeded,
        pricing_version=estimate.pricing_version,
        estimated=True,
        reserved={
            "requests": active_req,
            "tokens": active_tok,
            "estimated_cost": round(active_cost, 6),
        },
    )


@router.get("/model-providers/{provider_name}/health")
async def provider_health(
    provider_name: str,
    gateway: ModelGateway = Depends(get_model_gateway),
    session: Session = Depends(get_db),
    store: CredentialStore = Depends(get_credential_store),
) -> dict[str, str | None]:
    from app.services.provider_runtime_service import ProviderRuntimeService

    try:
        provider = gateway.get(provider_name)
    except ProviderNotFoundError as exc:
        raise error(404, "PROVIDER_NOT_FOUND", "模型 Provider 不存在") from exc
    ProviderRuntimeService.bind_gateway(gateway, session, store)
    return (await provider.health()).model_dump()


def _effective_mode_for_provider(
    session: Session,
    gateway: ModelGateway,
    provider_is_cloud: bool,
    configured_mode: str | None,
) -> str:
    from app.services.execution_mode import (
        cloud_enabled_from_session,
        resolve_effective_execution_mode,
    )

    local_available = any(
        (not p.capabilities().cloud) and p.capabilities().enabled for p in gateway.providers()
    )
    return resolve_effective_execution_mode(
        provider_is_cloud=provider_is_cloud,
        cloud_enabled=cloud_enabled_from_session(session),
        configured_execution_mode=configured_mode,
        local_provider_available=local_available,
    )


def create_run_record(
    session: Session,
    chapter: Chapter,
    request: AnalysisRunCreate,
    gateway: ModelGateway,
    retry_of: int | None = None,
) -> AnalysisRun:
    try:
        provider = gateway.get(request.provider_name)
    except ProviderNotFoundError as exc:
        raise error(404, "PROVIDER_NOT_FOUND", "模型 Provider 不存在") from exc
    if provider.capabilities().manual_only:
        raise error(422, "MANUAL_ONLY_PROVIDER", "该模型仅允许手动短任务，不参与自动分析")
    capabilities = provider.capabilities()
    if not capabilities.cloud and not capabilities.enabled:
        raise error(422, "PROVIDER_DISABLED", "模型 Provider 未启用")
    effective_mode = _effective_mode_for_provider(
        session, gateway, bool(capabilities.cloud), request.execution_mode
    )
    # Persist / validate the effective mode (coerce stale local for cloud providers).
    request.execution_mode = effective_mode  # type: ignore[assignment]
    if capabilities.cloud:
        if effective_mode not in {"cloud", "hybrid"}:
            raise error(422, "CLOUD_MODE_REQUIRED", "云端 Provider 需要 cloud 或 hybrid 模式")
        if not request.cloud_consent:
            raise error(422, "CLOUD_CONSENT_REQUIRED", "发送正文到云端前必须明确同意")
    elif effective_mode in {"cloud", "hybrid"}:
        raise error(422, "LOCAL_PROVIDER_MODE_MISMATCH", "本地 Provider 不会自动切换到云端")
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == chapter.id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    input_hash = hashlib.sha256(
        "\n".join(f"{item.id}:{item.normalized_text}" for item in paragraphs).encode()
    ).hexdigest()
    prompt_version = (
        "v3.5"
        if capabilities.cloud
        else ("v2" if capabilities.profile_name == "qwen3_14b_dev" else "v1")
    )
    boundary_prompt = load_prompt("scene_boundary", prompt_version)
    analysis_prompt = load_prompt(
        "scene_analysis",
        "v3.1" if prompt_version in {"v3.2", "v3.3", "v3.4", "v3.5"} else prompt_version,
    )
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider=provider.name,
        model=provider.default_model,
        prompt_version=prompt_version,
        schema_version="v1",
        prompt_hash=hashlib.sha256(
            (boundary_prompt.content_hash + analysis_prompt.content_hash).encode()
        ).hexdigest(),
        input_hash=input_hash,
        status="queued",
        retry_of_run_id=retry_of,
        execution_mode=request.execution_mode,
        analysis_mode=request.analysis_mode,
        cloud_consent=request.cloud_consent,
        cloud_consent_at=(datetime.now(timezone.utc) if request.cloud_consent else None),
        sends_content_to_cloud=capabilities.sends_content_to_cloud,
        content_hash=input_hash,
        client_request_id=request.client_request_id,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


@router.post(
    "/chapters/{chapter_id}/analysis-runs",
    response_model=AnalysisRunAccepted,
    status_code=202,
)
async def create_analysis_run(
    chapter_id: int,
    request: AnalysisRunCreate,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    session_factory=Depends(get_session_factory),
    store: CredentialStore = Depends(get_credential_store),
) -> AnalysisRunAccepted:
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        raise error(404, "CHAPTER_NOT_FOUND", "章节不存在")
    if chapter.section_type == "front_matter":
        raise error(422, "FRONT_MATTER_ANALYSIS_DISABLED", "前置内容默认不参与场景分析")
    if request.client_request_id:
        existing_request = session.scalar(
            select(AnalysisRun).where(AnalysisRun.client_request_id == request.client_request_id)
        )
        if existing_request is not None:
            return AnalysisRunAccepted(run_id=existing_request.id, status=existing_request.status)
    provider = gateway.get(request.provider_name)
    ProviderRuntimeService.bind_gateway(gateway, session, store)
    capabilities = provider.capabilities()
    effective_mode = _effective_mode_for_provider(
        session, gateway, bool(capabilities.cloud), request.execution_mode
    )
    request.execution_mode = effective_mode  # type: ignore[assignment]
    if capabilities.cloud:
        if effective_mode not in {"cloud", "hybrid"}:
            raise error(422, "CLOUD_MODE_REQUIRED", "云端 Provider 需要 cloud 或 hybrid 模式")
        if not request.cloud_consent:
            raise error(422, "CLOUD_CONSENT_REQUIRED", "发送正文到云端前必须明确同意")
    if not capabilities.enabled:
        raise error(422, "PROVIDER_DISABLED", "模型 Provider 未启用")
    health = None if capabilities.cloud else await provider.health()
    eligibility = evaluate_manual_boundary_candidate(
        session, provider_name=provider.name, capabilities=capabilities,
        store=store, pricing_path=Path("config/cloud_pricing.json"),
    ) if capabilities.cloud else provider_eligibility(
        session, provider_name=provider.name, capabilities=capabilities,
        healthy=health.status == "healthy", store=store,
        pricing_path=Path("config/cloud_pricing.json"),
    )
    if request.selected_provider and request.selected_provider != request.provider_name:
        raise error(409, "PROVIDER_STATE_CHANGED", "Provider选择已变化，请重新确认。")
    if capabilities.cloud and (
        request.capability_schema_version != "1c-a-2"
        or request.provider_state_version != eligibility.get("provider_state_version")
    ):
        raise error(409, "PROVIDER_STATE_CHANGED", "Provider状态已变化，请刷新后重新确认。")
    if request.analysis_mode == "assisted_boundary_review" and not provider.capabilities().cloud:
        raise error(409, "NO_MANUAL_BOUNDARY_PROVIDER", "人工边界审阅模式需要云端候选Provider")
    if provider.capabilities().cloud and request.analysis_mode == "assisted_boundary_review":
        if not eligibility["manual_boundary_candidate_eligible"]:
            blockers = eligibility["manual_selection_blockers"]
            code = (
                "CLOUD_MASTER_SWITCH_OFF" if "cloud_master_switch_off" in blockers
                else "PROVIDER_NOT_CONNECTED" if "provider_disconnected" in blockers
                else "BUDGET_NOT_AVAILABLE" if any(
                    item in blockers for item in ("pricing_unavailable", "budget_unavailable")
                ) else "NO_MANUAL_BOUNDARY_PROVIDER"
            )
            raise error(409, code, "；".join(blockers))
    elif provider.capabilities().cloud and not eligibility["automatic_route_eligible"]:
        raise error(409, "AUTOMATIC_ROUTING_NOT_ALLOWED", "当前Provider不允许自动边界路由")
    if provider.capabilities().manual_only:
        raise error(422, "MANUAL_ONLY_PROVIDER", "该模型仅允许手动短任务，不参与自动分析")
    if not capabilities.cloud and not provider.capabilities().enabled:
        raise error(422, "PROVIDER_DISABLED", "模型 Provider 未启用")
    if not capabilities.cloud and health.status != "healthy":
        code = (
            "MODEL_SERVER_NOT_RUNNING"
            if not provider.capabilities().cloud
            else "PROVIDER_UNHEALTHY"
        )
        raise error(422, code, "模型服务未运行或健康检查未通过")
    if not request.force:
        existing = session.scalar(
            select(AnalysisRun)
            .where(
                AnalysisRun.subject_type == "chapter",
                AnalysisRun.subject_id == str(chapter_id),
                AnalysisRun.provider == request.provider_name,
                AnalysisRun.status.in_([
                    "queued", "running", "boundary_candidates_running",
                    "awaiting_boundary_review", "boundary_confirmed",
                    "boundary_confirmed_budget_blocked", "scene_analysis_running", "succeeded",
                ]),
            )
            .order_by(desc(AnalysisRun.id))
        )
        if existing is not None:
            chapter_book_id = int(chapter.book_id) if chapter.book_id is not None else None
            raise error(
                409,
                "ANALYSIS_RUN_EXISTS",
                "该章节已有相同 Provider 的运行记录",
                details={
                    "existing_run_id": int(existing.id),
                    "existing_run_status": str(existing.status or ""),
                    "existing_run_type": str(existing.task_type or ""),
                    "book_id": chapter_book_id,
                    "chapter_id": int(chapter_id),
                },
            )
    reservation = None
    if provider.capabilities().cloud:
        cloud_row = session.get(ApplicationSetting, "cloud_enabled")
        budget_row = session.get(ApplicationSetting, "cloud_budget_settings")
        cloud_enabled = bool(json.loads(cloud_row.value_json)) if cloud_row else False
        budget = CloudBudgetUpdate.model_validate(
            json.loads(budget_row.value_json) if budget_row else {}
        ).model_dump()
        pricing_path = Path("config/cloud_pricing.json")
        pricing = pricing_status(pricing_path)
        usage = daily_usage(session, budget, cloud_enabled, pricing)
        paragraphs = list(
            session.scalars(
                select(Paragraph)
                .where(Paragraph.chapter_id == chapter.id)
                .order_by(Paragraph.paragraph_index)
            )
        )
        if request.analysis_mode == "assisted_boundary_review":
            estimate = estimate_stage1_boundary(paragraphs, pricing_path=pricing_path)
            stage = STAGE_BOUNDARY
        else:
            # Legacy automatic cloud path still stages boundary+analysis together.
            estimate = estimate_stage1_boundary(paragraphs, pricing_path=pricing_path)
            stage = STAGE_BOUNDARY
        try:
            reservation = reserve_budget(
                session,
                run_id=None,
                stage=stage,
                required_requests=estimate.expected_request_count,
                required_tokens=estimate.estimated_total_tokens,
                required_cost=estimate.estimated_cost,
                remaining_requests=usage["remaining_requests"],
                remaining_tokens=usage["remaining_tokens"],
                remaining_cost=usage["remaining_estimated_cost"],
                expected_requests=estimate.expected_request_count,
                worst_case_requests=estimate.worst_case_request_count,
                pricing_version=estimate.pricing_version,
            )
        except InsufficientBudgetReservation as exc:
            raise _budget_http_error(exc) from exc
        # Create-time temporary request allowance: re-check cost/token hard ceilings.
        # Temporary auth may cover request shortfall only — never raise daily cost limit.
        if request.run_temporary_request_allowance is not None:
            from app.services.analysis_recovery_center import build_full_pipeline_advisory

            active_req, active_tok, active_cost = active_reservation_totals(session)
            remaining = available_remaining(
                remaining_requests=usage["remaining_requests"],
                remaining_tokens=usage["remaining_tokens"],
                remaining_cost=usage["remaining_estimated_cost"],
                reserved_requests=active_req,
                reserved_tokens=active_tok,
                reserved_cost=active_cost,
            )
            advisory = build_full_pipeline_advisory(
                session,
                paragraph_count=int(estimate.paragraph_count or 0),
                stage1_expected=estimate.expected_request_count,
                stage1_worst=estimate.worst_case_request_count,
                stage1_tokens=estimate.estimated_total_tokens,
                stage1_worst_tokens=estimate.worst_case_total_tokens,
                stage1_cost=estimate.estimated_cost,
                stage1_worst_cost=estimate.worst_case_cost,
                remaining=remaining,
            )
            hard = [
                dim
                for dim in (advisory.exceeded_dimensions or [])
                if dim in {"tokens", "estimated_cost"}
            ]
            if hard:
                raise error(
                    409,
                    "FULL_PIPELINE_HARD_BUDGET_INSUFFICIENT",
                    "费用或Token预算不足以覆盖完整分析，不能仅用技术请求临时授权创建任务。"
                    + (f" {advisory.message}" if advisory.message else ""),
                )
    run = create_run_record(session, chapter, request, gateway)
    if reservation:
        reservation.run_id = run.id
        session.commit()
    if (
        request.run_temporary_request_allowance is not None
        and int(request.run_temporary_request_allowance.extra_requests or 0) > 0
        and request.client_request_id
    ):
        from app.services.run_scoped_budget_auth import apply_run_budget_auth

        apply_run_budget_auth(
            run,
            extra_requests=int(request.run_temporary_request_allowance.extra_requests),
            extra_tokens=0,
            extra_cost=0.0,
            client_request_id=request.client_request_id,
        )
        session.commit()
    if request.analysis_mode == "assisted_boundary_review":
        run.status = "boundary_candidates_running"
        session.commit()
    background.add_task(execute_scene_pipeline, session_factory, gateway, run.id)
    return AnalysisRunAccepted(run_id=run.id, status=run.status)


@router.get("/analysis-runs/{run_id}", response_model=AnalysisRunResponse)
def get_analysis_run(run_id: int, session: Session = Depends(get_db)) -> AnalysisRunResponse:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    return serialize_run(session, run)


@router.post(
    "/analysis-runs/{run_id}/cancel",
    response_model=AnalysisRunCancelResponse,
)
def cancel_analysis_run(
    run_id: int,
    request: AnalysisRunCancelRequest | None = None,
    session: Session = Depends(get_db),
) -> AnalysisRunCancelResponse:
    """Cooperative user cancel — persists request; workers stop at checkpoints."""
    from app.services.task_cancellation import request_cancel

    body = request or AnalysisRunCancelRequest()
    try:
        result = request_cancel(
            session,
            run_id,
            reason=body.reason or "user_requested",
            expected_version=body.expected_version,
            client_request_id=body.client_request_id,
        )
    except LookupError:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在") from None
    except ValueError as exc:
        if "VERSION_CONFLICT" in str(exc):
            raise error(409, "ANALYSIS_RUN_VERSION_CONFLICT", "任务状态已变化，请刷新后重试") from None
        raise error(400, "CANCEL_REJECTED", "无法停止该任务") from None
    return AnalysisRunCancelResponse(
        task_id=result.task_id,
        previous_status=result.previous_status,
        current_status=result.current_status,
        cancellation_requested_at=result.cancellation_requested_at,
        cancelled_at=result.cancelled_at,
        message=result.message,
        already_requested=result.already_requested,
        already_cancelled=result.already_cancelled,
        already_completed=result.already_completed,
        cannot_cancel=result.cannot_cancel,
        can_restart_as_new_task=result.can_restart_as_new_task,
        status_version=result.status_version,
    )


def _boundary_recovery_budget(
    session: Session, source: AnalysisRun
) -> tuple[object, object, list[str], object]:
    report = recover_boundary_detection_from_invocations(
        session, source.id, persist=False
    )
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == int(source.subject_id))
            .order_by(Paragraph.paragraph_index)
        )
    )
    estimate = estimate_stage1_boundary_remaining(
        paragraphs,
        {int(item["batch_index"]) for item in report.recovered},
        pricing_path=Path("config/cloud_pricing.json"),
    )
    cloud_row = session.get(ApplicationSetting, "cloud_enabled")
    budget_row = session.get(ApplicationSetting, "cloud_budget_settings")
    cloud_enabled = bool(json.loads(cloud_row.value_json)) if cloud_row else False
    budget = CloudBudgetUpdate.model_validate(
        json.loads(budget_row.value_json) if budget_row else {}
    ).model_dump()
    usage = daily_usage(
        session,
        budget,
        cloud_enabled,
        pricing_status(Path("config/cloud_pricing.json")),
    )
    active_req, active_tok, active_cost = active_reservation_totals(session)
    remaining = available_remaining(
        remaining_requests=usage["remaining_requests"],
        remaining_tokens=usage["remaining_tokens"],
        remaining_cost=usage["remaining_estimated_cost"],
        reserved_requests=active_req,
        reserved_tokens=active_tok,
        reserved_cost=active_cost,
    )
    exceeded = exceeded_dimensions(estimate.required, remaining)
    return report, estimate, exceeded, remaining


ACTIVE_RECOVERY_STATUSES = (
    "queued",
    "running",
    "boundary_candidates_running",
    "boundary_candidates_partial",
    "awaiting_boundary_review",
    "boundary_confirmed",
    "boundary_confirmed_budget_blocked",
    "scene_analysis_running",
    "succeeded",
)

_BLOCKER_HINTS = {
    "cloud_master_switch_off": "请先开启云端总开关",
    "provider_disabled": "请在Provider设置中启用该Provider",
    "provider_not_configured": "请完善Base URL或Workspace配置",
    "credential_missing": "请重新保存API Key",
    "provider_disconnected": "请先完成真实连接测试",
    "pricing_unavailable": "请检查云端定价表是否可用",
    "budget_unavailable": "请提高日请求/Token/费用预算",
    "boundary_candidates_not_supported": "该Provider不支持边界候选",
    "provider_unhealthy": "请先完成真实连接测试后再恢复",
    "provider_health_stale": "Provider健康状态已过期，请刷新或重新验证连接",
    "provider_state_stale": "Provider状态已变化，请刷新后重新确认",
}


def _existing_recovery_run(session: Session, source_run_id: int) -> AnalysisRun | None:
    return session.scalar(
        select(AnalysisRun)
        .where(
            AnalysisRun.recovered_from_run_id == source_run_id,
            AnalysisRun.status.in_(list(ACTIVE_RECOVERY_STATUSES)),
        )
        .order_by(desc(AnalysisRun.id))
    )


def _recovery_response(
    run: AnalysisRun,
    *,
    reused_batch_count: int,
    remaining_batch_count: int,
    reservation_id: int | None,
    idempotent_replay: bool = False,
) -> BoundaryRecoveryContinueResponse:
    return BoundaryRecoveryContinueResponse(
        run_id=run.id,
        recovered_from_run_id=int(run.recovered_from_run_id or 0),
        status=run.status,
        reused_batch_count=reused_batch_count,
        remaining_batch_count=remaining_batch_count,
        reservation_id=reservation_id,
        request_id=run.client_request_id,
        idempotent_replay=idempotent_replay,
    )


def _source_provider_name(source: AnalysisRun) -> str:
    # AnalysisRun.provider is the persisted provider_name for the source run.
    return str(source.provider)


def _evaluate_recovery_provider(
    session: Session,
    source: AnalysisRun,
    gateway: ModelGateway,
    store: CredentialStore,
) -> tuple[object, dict[str, object]]:
    provider_name = _source_provider_name(source)
    provider = gateway.get(provider_name)
    ProviderRuntimeService.bind_gateway(gateway, session, store)
    eligibility = ProviderEligibilityService.evaluate_manual_boundary_candidate(
        session,
        provider_name=provider.name,
        capabilities=provider.capabilities(),
        store=store,
        pricing_path=Path("config/cloud_pricing.json"),
    )
    return provider, eligibility


def _raise_manual_boundary_provider_error(
    *,
    provider_name: str,
    eligibility: dict[str, object],
) -> None:
    blockers = list(eligibility.get("manual_selection_blockers") or [])
    if not blockers:
        blockers = ["boundary_candidates_not_supported"]
    hint = "；".join(_BLOCKER_HINTS.get(item, item) for item in blockers)
    raise HTTPException(
        status_code=409,
        detail={
            "error_code": "NO_MANUAL_BOUNDARY_PROVIDER",
            "message": f"Provider {provider_name} 当前不可用于恢复",
            "provider_name": provider_name,
            "blockers": blockers,
            "provider_state_version": eligibility.get("provider_state_version"),
            "health_state": eligibility.get("health_state"),
            "health_source": eligibility.get("health_source"),
            "details": {
                "provider_name": provider_name,
                "blockers": blockers,
                "health_state": eligibility.get("health_state"),
                "health_source": eligibility.get("health_source"),
            },
            "user_action_hint": hint or "请检查Provider资格后重试",
            "retryable": False,
        },
    )


@router.get(
    "/analysis-runs/{run_id}/recovery-preflight",
    response_model=BoundaryRecoveryPreflightResponse,
)
def boundary_recovery_preflight(
    run_id: int, session: Session = Depends(get_db)
) -> BoundaryRecoveryPreflightResponse:
    source = session.get(AnalysisRun, run_id)
    if source is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    if source.analysis_mode != "assisted_boundary_review":
        raise error(409, "RUN_NOT_ASSISTED_REVIEW", "仅人工边界审阅任务支持检查点恢复")
    report, estimate, exceeded, remaining = _boundary_recovery_budget(session, source)
    existing = _existing_recovery_run(session, source.id)
    blockers: list[str] = []
    if report.recovered_batch_count <= 0 and not report.remaining_batch_indices:
        blockers.append("NO_RECOVERABLE_CHECKPOINTS")
    if exceeded:
        blockers.append("INSUFFICIENT_BUDGET_RESERVATION")
    if existing is not None:
        blockers.append("RECOVERY_ALREADY_EXISTS")
    return BoundaryRecoveryPreflightResponse(
        source_run_id=source.id,
        chapter_id=int(source.subject_id),
        recovered_batch_count=report.recovered_batch_count,
        total_detection_batch_count=report.total_detection_batch_count,
        remaining_detection_batch_count=len(report.remaining_batch_indices),
        semantic_conflict_count=report.semantic_conflict_count,
        expected_request_count=estimate.expected_request_count,
        worst_case_request_count=estimate.worst_case_request_count,
        estimated_total_tokens=estimate.estimated_total_tokens,
        worst_case_total_tokens=estimate.worst_case_total_tokens,
        estimated_cost=estimate.estimated_cost,
        worst_case_cost=estimate.worst_case_cost,
        currency=estimate.currency,
        pricing_version=estimate.pricing_version,
        remaining={
            "requests": remaining.requests,
            "tokens": remaining.tokens,
            "estimated_cost": remaining.estimated_cost,
        },
        within_budget=not exceeded,
        exceeded_dimensions=exceeded,
        requires_cloud_consent=source.sends_content_to_cloud,
        existing_recovery_run_id=existing.id if existing else None,
        blockers=blockers,
    )


@router.post(
    "/analysis-runs/{run_id}/recover/preflight",
    response_model=BoundaryRecoverPreflightResponse,
)
def recover_preflight(
    run_id: int,
    request: BoundaryRecoveryPreflightRequest,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    store: CredentialStore = Depends(get_credential_store),
) -> BoundaryRecoverPreflightResponse:
    """Zero-side-effect recovery readiness check using unified eligibility."""
    source = session.get(AnalysisRun, run_id)
    if source is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    if source.analysis_mode != "assisted_boundary_review":
        raise error(409, "RUN_NOT_ASSISTED_REVIEW", "仅人工边界审阅任务支持检查点恢复")
    if source.sends_content_to_cloud and not request.cloud_consent:
        raise error(422, "CLOUD_CONSENT_REQUIRED", "继续云端任务前必须重新同意发送正文")
    _provider, eligibility = _evaluate_recovery_provider(
        session, source, gateway, store
    )
    report, estimate, exceeded, remaining = _boundary_recovery_budget(session, source)
    blockers = list(eligibility.get("manual_selection_blockers") or [])
    if exceeded:
        blockers.append("budget_unavailable")
    existing = _existing_recovery_run(session, source.id)
    if existing is not None:
        blockers.append("RECOVERY_ALREADY_EXISTS")
    if report.recovered_batch_count <= 0 and not report.remaining_batch_indices:
        blockers.append("NO_RECOVERABLE_CHECKPOINTS")
    eligible = bool(eligibility["manual_boundary_candidate_eligible"]) and not exceeded
    return BoundaryRecoverPreflightResponse(
        source_run_id=source.id,
        provider_name=_source_provider_name(source),
        eligible=eligible and "RECOVERY_ALREADY_EXISTS" not in blockers,
        blockers=list(dict.fromkeys(blockers)),
        provider_state_version=str(eligibility["provider_state_version"]),
        capability_schema_version=str(
            eligibility.get("capability_schema_version") or "1c-a-2"
        ),
        health_state=str(eligibility.get("health_state") or "unknown"),
        health_source=str(eligibility.get("health_source") or "unknown"),
        reused_batch_count=report.recovered_batch_count,
        remaining_batch_count=len(report.remaining_batch_indices),
        expected_requests=estimate.expected_request_count,
        worst_case_requests=estimate.worst_case_request_count,
        estimated_tokens=estimate.estimated_total_tokens,
        worst_case_tokens=estimate.worst_case_total_tokens,
        estimated_cost=estimate.estimated_cost,
        worst_case_cost=estimate.worst_case_cost,
        currency=estimate.currency,
        remaining_budget={
            "requests": remaining.requests,
            "tokens": remaining.tokens,
            "estimated_cost": remaining.estimated_cost,
        },
        within_budget=not exceeded,
        exceeded_dimensions=exceeded,
        requires_cloud_consent=bool(source.sends_content_to_cloud),
    )


def _continue_from_checkpoints_impl(
    run_id: int,
    request: BoundaryRecoveryContinueRequest,
    background: BackgroundTasks,
    session: Session,
    gateway: ModelGateway,
    session_factory,
    store: CredentialStore,
) -> BoundaryRecoveryContinueResponse:
    source = session.get(AnalysisRun, run_id)
    if source is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    if source.analysis_mode != "assisted_boundary_review":
        raise error(409, "RUN_NOT_ASSISTED_REVIEW", "仅人工边界审阅任务支持检查点恢复")
    if not request.confirmed:
        raise error(422, "RECOVERY_CONFIRMATION_REQUIRED", "必须确认从已有结果继续")
    if source.sends_content_to_cloud and not request.cloud_consent:
        raise error(422, "CLOUD_CONSENT_REQUIRED", "继续云端任务前必须重新同意发送正文")
    existing = session.scalar(
        select(AnalysisRun).where(
            AnalysisRun.client_request_id == request.client_request_id
        )
    )
    if existing is not None:
        report = recover_boundary_detection_from_invocations(
            session, source.id, persist=False
        )
        return _recovery_response(
            existing,
            reused_batch_count=report.recovered_batch_count,
            remaining_batch_count=len(report.remaining_batch_indices),
            reservation_id=None,
            idempotent_replay=True,
        )
    existing_source = _existing_recovery_run(session, source.id)
    if existing_source is not None:
        report = recover_boundary_detection_from_invocations(
            session, source.id, persist=False
        )
        return _recovery_response(
            existing_source,
            reused_batch_count=report.recovered_batch_count,
            remaining_batch_count=len(report.remaining_batch_indices),
            reservation_id=None,
            idempotent_replay=True,
        )
    provider, eligibility = _evaluate_recovery_provider(
        session, source, gateway, store
    )
    if not request.provider_state_version:
        raise error(
            422,
            "REQUEST_VALIDATION_ERROR",
            "缺少 provider_state_version，请先调用 recover/preflight",
        )
    if request.provider_state_version != eligibility.get("provider_state_version"):
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "PROVIDER_STATE_CHANGED",
                "message": "Provider状态已变化，请刷新后重新确认",
                "provider_name": provider.name,
                "blockers": ["provider_state_stale"],
                "provider_state_version": eligibility.get("provider_state_version"),
                "health_state": eligibility.get("health_state"),
                "health_source": eligibility.get("health_source"),
                "user_action_hint": _BLOCKER_HINTS["provider_state_stale"],
                "retryable": True,
            },
        )
    if not eligibility["manual_boundary_candidate_eligible"]:
        _raise_manual_boundary_provider_error(
            provider_name=provider.name, eligibility=eligibility
        )
    report = recover_boundary_detection_from_invocations(
        session, source.id, persist=True
    )
    if report.recovered_batch_count <= 0 and report.remaining_batch_indices:
        # Still allow continuing from zero checkpoints when invocations can be rebuilt later.
        pass
    if report.recovered_batch_count <= 0 and not report.remaining_batch_indices:
        raise error(409, "NO_RECOVERABLE_CHECKPOINTS", "没有可复用的检查点或未完成批次")
    _report, estimate, exceeded, remaining = _boundary_recovery_budget(session, source)
    if exceeded:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "INSUFFICIENT_BUDGET_RESERVATION",
                "message": "继续运行的剩余预算不足",
                "details": {
                    "exceeded_dimensions": exceeded,
                    "required": {
                        "requests": estimate.expected_request_count,
                        "tokens": estimate.estimated_total_tokens,
                        "estimated_cost": estimate.estimated_cost,
                    },
                    "remaining": {
                        "requests": remaining.requests,
                        "tokens": remaining.tokens,
                        "estimated_cost": remaining.estimated_cost,
                    },
                },
                "user_action_hint": "请提高云端预算后重试",
                "retryable": True,
                "stage": STAGE_BOUNDARY,
                "required": {
                    "requests": estimate.expected_request_count,
                    "tokens": estimate.estimated_total_tokens,
                    "estimated_cost": estimate.estimated_cost,
                },
                "remaining": {
                    "requests": remaining.requests,
                    "tokens": remaining.tokens,
                    "estimated_cost": remaining.estimated_cost,
                },
                "exceeded_dimensions": exceeded,
            },
        )
    try:
        reservation = reserve_budget(
            session,
            run_id=None,
            stage=STAGE_BOUNDARY,
            required_requests=estimate.expected_request_count,
            required_tokens=estimate.estimated_total_tokens,
            required_cost=estimate.estimated_cost,
            remaining_requests=remaining.requests,
            remaining_tokens=remaining.tokens,
            remaining_cost=remaining.estimated_cost,
            expected_requests=estimate.expected_request_count,
            worst_case_requests=estimate.worst_case_request_count,
            pricing_version=estimate.pricing_version,
        )
    except InsufficientBudgetReservation as exc:
        raise _budget_http_error(exc) from exc
    chapter = session.get(Chapter, int(source.subject_id))
    if chapter is None:
        raise error(404, "CHAPTER_NOT_FOUND", "章节不存在")
    try:
        run = create_run_record(
            session,
            chapter,
            AnalysisRunCreate(
                provider_name=source.provider,
                force=True,
                execution_mode=source.execution_mode,
                cloud_consent=request.cloud_consent,
                analysis_mode="assisted_boundary_review",
                client_request_id=request.client_request_id,
            ),
            gateway,
        )
    except Exception as exc:
        raise error(
            500, "RECOVERY_RUN_CREATE_FAILED", f"创建恢复任务失败：{exc}"
        ) from exc
    run.recovered_from_run_id = source.id
    run.status = "boundary_candidates_running"
    reservation.run_id = run.id
    session.commit()
    clone_recovered_checkpoints(session, source.id, run)
    background.add_task(execute_scene_pipeline, session_factory, gateway, run.id)
    return _recovery_response(
        run,
        reused_batch_count=report.recovered_batch_count,
        remaining_batch_count=len(report.remaining_batch_indices),
        reservation_id=reservation.id,
        idempotent_replay=False,
    )


@router.post(
    "/analysis-runs/{run_id}/continue-from-checkpoints",
    response_model=BoundaryRecoveryContinueResponse,
    status_code=202,
)
def continue_from_checkpoints(
    run_id: int,
    request: BoundaryRecoveryContinueRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    session_factory=Depends(get_session_factory),
    store: CredentialStore = Depends(get_credential_store),
) -> BoundaryRecoveryContinueResponse:
    return _continue_from_checkpoints_impl(
        run_id, request, background, session, gateway, session_factory, store
    )


@router.post(
    "/analysis-runs/{run_id}/recover",
    response_model=BoundaryRecoveryContinueResponse,
    status_code=202,
)
def recover_from_checkpoints(
    run_id: int,
    request: BoundaryRecoveryContinueRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    session_factory=Depends(get_session_factory),
    store: CredentialStore = Depends(get_credential_store),
) -> BoundaryRecoveryContinueResponse:
    """Canonical recovery endpoint; aliases continue-from-checkpoints."""
    return _continue_from_checkpoints_impl(
        run_id, request, background, session, gateway, session_factory, store
    )


def _scene_analysis_resumable(run: AnalysisRun) -> bool:
    if run.status in {
        "boundary_confirmed",
        "boundary_confirmed_budget_blocked",
        "scene_analysis_partial",
        "awaiting_provider_recovery",
    }:
        return True
    if run.status == "failed" and run.failed_stage == "scene_analysis":
        return True
    return False


def _build_scene_analysis_resume_preflight(
    session: Session,
    run: AnalysisRun,
    gateway: ModelGateway,
    store: CredentialStore,
    *,
    cloud_consent: bool,
) -> SceneAnalysisResumePreflightResponse:
    if not _scene_analysis_resumable(run) and run.status != "scene_analysis_running":
        raise error(409, "RUN_NOT_RESUMABLE", "当前任务不可继续Scene Analysis")
    review = session.scalar(
        select(BoundaryReviewSession)
        .where(BoundaryReviewSession.analysis_run_id == run.id)
        .order_by(desc(BoundaryReviewSession.id))
    )
    if review is None or review.status != "confirmed":
        raise error(409, "BOUNDARY_REVIEW_REQUIRED", "需要已确认的边界审阅")
    pending = pending_scenes_for_run(session, run)
    progress = scene_analysis_progress(session, run)
    if progress.total_scene_count <= 0:
        raise error(409, "BOUNDARY_REVISION_MISSING", "缺少可复用Scene")
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == review.chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    pricing_path = Path("config/cloud_pricing.json")
    estimate = estimate_stage2_scene_analysis(
        session, pending if pending else [], paragraphs, pricing_path=pricing_path
    )
    # Empty pending → zero cost estimate still structured
    if not pending:
        estimate = estimate_stage2_scene_analysis(
            session, [], paragraphs, pricing_path=pricing_path
        )
    resolved = ProviderRuntimeService.resolve_for_run(
        gateway, session, run, store, task_type="scene_analysis"
    )
    from app.services.staged_budget import BudgetAmounts

    remaining = resolved.eligibility.get("remaining_budget") or {}
    exceeded = exceeded_dimensions(
        BudgetAmounts(
            requests=estimate.worst_case_request_count,
            tokens=estimate.worst_case_total_tokens,
            estimated_cost=estimate.worst_case_cost,
        ),
        BudgetAmounts(
            requests=int(remaining.get("requests") or 0),
            tokens=int(remaining.get("tokens") or 0),
            estimated_cost=float(remaining.get("estimated_cost") or 0),
        ),
    )
    blockers = list(resolved.eligibility.get("blockers") or [])
    if run.sends_content_to_cloud and not cloud_consent:
        blockers.append("cloud_consent_required")
    within = not exceeded and "budget_unavailable" not in blockers
    return SceneAnalysisResumePreflightResponse(
        run_id=run.id,
        boundary_revision_id=progress.boundary_revision_id,
        total_scene_count=progress.total_scene_count,
        completed_scene_count=progress.completed_scene_count,
        remaining_scene_count=progress.remaining_scene_count,
        remaining_scene_ids=list(progress.pending_scene_ids),
        expected_requests=estimate.expected_request_count if pending else 0,
        worst_case_requests=estimate.worst_case_request_count if pending else 0,
        estimated_tokens=estimate.estimated_total_tokens if pending else 0,
        worst_case_tokens=estimate.worst_case_total_tokens if pending else 0,
        estimated_cost=estimate.estimated_cost if pending else 0.0,
        worst_case_cost=estimate.worst_case_cost if pending else 0.0,
        remaining_budget={
            "requests": int(remaining.get("requests") or 0),
            "tokens": int(remaining.get("tokens") or 0),
            "estimated_cost": float(remaining.get("estimated_cost") or 0),
        },
        within_budget=within,
        exceeded_dimensions=list(exceeded),
        provider_state_version=resolved.provider_state_version,
        provider_name=run.provider,
        eligible=bool(resolved.eligibility.get("eligible")) and within,
        blockers=list(dict.fromkeys(blockers)),
        requires_cloud_consent=bool(run.sends_content_to_cloud),
        estimated=True,
        currency=estimate.currency,
        coverage_rate=progress.coverage_rate,
    )


@router.get(
    "/analysis-runs/{run_id}/resume-scene-analysis/preflight",
    response_model=SceneAnalysisResumePreflightResponse,
)
def resume_scene_analysis_preflight_get(
    run_id: int,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    store: CredentialStore = Depends(get_credential_store),
) -> SceneAnalysisResumePreflightResponse:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    return _build_scene_analysis_resume_preflight(
        session, run, gateway, store, cloud_consent=False
    )


@router.post(
    "/analysis-runs/{run_id}/resume-scene-analysis/preflight",
    response_model=SceneAnalysisResumePreflightResponse,
)
def resume_scene_analysis_preflight_post(
    run_id: int,
    request: SceneAnalysisResumePreflightRequest,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    store: CredentialStore = Depends(get_credential_store),
) -> SceneAnalysisResumePreflightResponse:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    return _build_scene_analysis_resume_preflight(
        session, run, gateway, store, cloud_consent=bool(request.cloud_consent)
    )


@router.post(
    "/analysis-runs/{run_id}/resume-scene-analysis",
    response_model=AnalysisRunAccepted,
    status_code=202,
)
async def resume_scene_analysis(
    run_id: int,
    background: BackgroundTasks,
    request: SceneAnalysisResumeRequest | None = None,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    session_factory=Depends(get_session_factory),
    store: CredentialStore = Depends(get_credential_store),
) -> AnalysisRunAccepted:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    payload = request or SceneAnalysisResumeRequest(
        client_request_id=f"legacy-resume-{run.id}",
        cloud_consent=bool(run.cloud_consent),
        confirmed=True,
    )
    if run.status == "succeeded":
        return AnalysisRunAccepted(run_id=run.id, status=run.status)
    if run.status == "scene_analysis_running":
        if run.raw_output:
            try:
                marker = json.loads(run.raw_output)
                if (
                    isinstance(marker, dict)
                    and marker.get("kind") == "scene_analysis_resume"
                    and marker.get("client_request_id") == payload.client_request_id
                ):
                    return AnalysisRunAccepted(run_id=run.id, status=run.status)
            except json.JSONDecodeError:
                pass
        raise error(409, "SCENE_ANALYSIS_ALREADY_RUNNING", "Scene Analysis正在执行，请勿重复提交")
    if not _scene_analysis_resumable(run):
        raise error(409, "RUN_NOT_RESUMABLE", "仅边界已确认或Scene Analysis失败的任务可继续")
    if not payload.confirmed:
        raise error(422, "RESUME_CONFIRMATION_REQUIRED", "必须确认继续Scene Analysis")
    if run.sends_content_to_cloud and not payload.cloud_consent:
        raise error(422, "CLOUD_CONSENT_REQUIRED", "继续云端任务前必须重新同意发送正文")

    # Idempotent replay for same client_request_id after prior resume marker.
    if run.raw_output:
        try:
            marker = json.loads(run.raw_output)
            if (
                isinstance(marker, dict)
                and marker.get("kind") == "scene_analysis_resume"
                and marker.get("client_request_id") == payload.client_request_id
                and run.status in {"scene_analysis_running", "succeeded"}
            ):
                return AnalysisRunAccepted(run_id=run.id, status=run.status)
            # Same client_request_id already produced a terminal partial/failure — do not rebill.
            if (
                isinstance(marker, dict)
                and marker.get("kind") in {"scene_analysis_failure", "scene_analysis_partial"}
                and marker.get("last_resume_client_request_id") == payload.client_request_id
            ):
                return AnalysisRunAccepted(run_id=run.id, status=run.status)
        except json.JSONDecodeError:
            pass

    review = session.scalar(
        select(BoundaryReviewSession)
        .where(BoundaryReviewSession.analysis_run_id == run.id)
        .order_by(desc(BoundaryReviewSession.id))
    )
    if review is None or review.status != "confirmed":
        raise error(409, "BOUNDARY_REVIEW_REQUIRED", "需要已确认的边界审阅")
    revision = session.scalar(
        select(BoundaryRevision)
        .where(BoundaryRevision.review_session_id == review.id)
        .order_by(desc(BoundaryRevision.id))
    )
    if revision is None:
        raise error(409, "BOUNDARY_REVISION_MISSING", "缺少边界修订")
    pending = pending_scenes_for_run(session, run)
    if not pending:
        clear_scene_analysis_error_fields(run)
        run.status = "succeeded"
        run.completed_at = datetime.now(timezone.utc)
        session.commit()
        return AnalysisRunAccepted(run_id=run.id, status=run.status)

    # Cap paid retries on the first pending scene to avoid infinite billing loops.
    # Provider-recovery cycles may legitimately exceed the single-pass HTTP cap.
    from app.core.config import get_settings
    from app.services.scene_analysis_provider_recovery import (
        STATUS_AWAITING_PROVIDER_RECOVERY,
        load_recovery_state,
        policy_from_settings,
    )

    first_pending = pending[0]
    http_attempts = count_scene_http_attempts(session, run.id, first_pending)
    recovery_policy = policy_from_settings(get_settings())
    recovery_state = load_recovery_state(run)
    in_provider_recovery = (
        run.status == STATUS_AWAITING_PROVIDER_RECOVERY
        or bool(recovery_state.get("recovery_audits"))
        or (
            run.root_error_code
            in {
                "PROVIDER_REMOTE_DISCONNECT",
                "PROVIDER_CONNECT_TIMEOUT",
                "PROVIDER_READ_TIMEOUT",
                "PROVIDER_CONNECTION_ERROR",
            }
        )
    )
    max_http_for_resume = SCENE_ANALYSIS_MAX_HTTP_ATTEMPTS
    if in_provider_recovery:
        # Allow one transport budget per recovery cycle beyond the base cap.
        max_http_for_resume = SCENE_ANALYSIS_MAX_HTTP_ATTEMPTS + (
            recovery_policy.max_recovery_cycles
            * max(1, int(get_settings().aliyun_transport_max_attempts))
        )
    if http_attempts >= max_http_for_resume:
        offline_ok = find_replayable_scene_invocation(session, run.id, first_pending) is not None
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "SCENE_ANALYSIS_ATTEMPT_LIMIT",
                "message": (
                    f"Scene #{first_pending.id} 已达 HTTP 尝试上限"
                    f"（{http_attempts}/{max_http_for_resume}），拒绝再次付费调用"
                ),
                "failed_scene_id": first_pending.id,
                "failed_scene_index": first_pending.ordinal,
                "http_attempts": http_attempts,
                "max_http_attempts": max_http_for_resume,
                "offline_replay_available": offline_ok,
                "user_action_hint": (
                    "请使用离线重放已有响应；勿再次点击继续Scene Analysis"
                    if offline_ok
                    else "请查看失败Scene详情后再决定是否强制重试"
                ),
                "retryable": False,
            },
        )

    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == review.chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    pricing_path = Path("config/cloud_pricing.json")
    estimate = estimate_stage2_scene_analysis(
        session, pending, paragraphs, pricing_path=pricing_path
    )
    resolved = ProviderRuntimeService.resolve_for_run(
        gateway, session, run, store, task_type="scene_analysis"
    )
    if payload.provider_state_version and (
        payload.provider_state_version != resolved.provider_state_version
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "PROVIDER_STATE_CHANGED",
                "message": "Provider状态已变化，请刷新后重新确认",
                "provider_state_version": resolved.provider_state_version,
                "retryable": True,
            },
        )
    if not resolved.eligibility.get("eligible"):
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "PROVIDER_NOT_ELIGIBLE",
                "message": "当前Provider不可用于Scene Analysis",
                "blockers": resolved.eligibility.get("blockers"),
                "provider_state_version": resolved.provider_state_version,
                "retryable": False,
            },
        )
    remaining = resolved.eligibility.get("remaining_budget") or {}
    try:
        reserve_budget(
            session,
            run_id=run.id,
            stage=STAGE_ANALYSIS,
            required_requests=estimate.expected_request_count,
            required_tokens=estimate.estimated_total_tokens,
            required_cost=estimate.estimated_cost,
            remaining_requests=int(remaining.get("requests") or 0),
            remaining_tokens=int(remaining.get("tokens") or 0),
            remaining_cost=float(remaining.get("estimated_cost") or 0),
            expected_requests=estimate.expected_request_count,
            worst_case_requests=estimate.worst_case_request_count,
            pricing_version=estimate.pricing_version,
        )
    except InsufficientBudgetReservation as exc:
        run.status = "boundary_confirmed_budget_blocked"
        run.error_code = "INSUFFICIENT_BUDGET_RESERVATION"
        run.failed_stage = "scene_analysis_budget"
        run.retryable = True
        run.user_action_hint = exc.as_error_detail()["user_action_hint"]  # type: ignore[index]
        run.raw_output = json.dumps(
            {"kind": "budget_block", **exc.as_error_detail()}, ensure_ascii=False
        )
        session.commit()
        raise _budget_http_error(exc) from exc

    if payload.cloud_consent:
        run.cloud_consent = True
        run.cloud_consent_at = datetime.now(timezone.utc)
    from app.services.scene_analysis_provider_recovery import (
        STATUS_AWAITING_PROVIDER_RECOVERY,
        load_recovery_state,
        resume_from_provider_recovery,
    )

    recovery_blob = load_recovery_state(run) if run.status == STATUS_AWAITING_PROVIDER_RECOVERY else {}
    if run.status == STATUS_AWAITING_PROVIDER_RECOVERY:
        resume_from_provider_recovery(run)
    else:
        clear_scene_analysis_error_fields(run)
        run.status = "scene_analysis_running"
    resume_marker = {
        "kind": "scene_analysis_resume",
        "client_request_id": payload.client_request_id,
        "remaining_scene_count": len(pending),
        "boundary_revision_id": revision.id,
    }
    if recovery_blob:
        resume_marker["provider_recovery"] = {
            "recovery_cycles": recovery_blob.get("recovery_cycles"),
            "recovery_started_at": recovery_blob.get("recovery_started_at"),
            "recovery_audits": recovery_blob.get("recovery_audits"),
        }
    run.raw_output = json.dumps(resume_marker, ensure_ascii=False)
    session.commit()
    background.add_task(analyze_confirmed_review, session_factory, gateway, review.id)
    return AnalysisRunAccepted(run_id=run.id, status=run.status)


@router.post(
    "/analysis-runs/{run_id}/replay-scene-analysis-offline",
    response_model=SceneAnalysisOfflineReplayResponse,
)
@router.post(
    "/analysis-runs/{run_id}/scene-analysis/offline-replay",
    response_model=SceneAnalysisOfflineReplayResponse,
)
def replay_scene_analysis_offline(
    run_id: int,
    request: SceneAnalysisOfflineReplayRequest | None = None,
    session: Session = Depends(get_db),
) -> SceneAnalysisOfflineReplayResponse:
    """Persist Artifact from a stored parsed response. Never sends provider HTTP."""
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    if not _scene_analysis_resumable(run) and run.status != "succeeded":
        raise error(409, "RUN_NOT_RESUMABLE", "当前状态不可离线重放Scene Analysis")
    payload = request or SceneAnalysisOfflineReplayRequest()
    if not payload.confirmed:
        raise error(422, "OFFLINE_REPLAY_CONFIRMATION_REQUIRED", "必须确认离线恢复")
    try:
        result = offline_replay_scene_analysis(
            session,
            run,
            scene_id=payload.scene_id,
            invocation_id=payload.invocation_id,
            client_request_id=payload.client_request_id,
        )
    except ValueError as exc:
        code = str(exc)
        mapping = {
            "NO_REPLAYABLE_RESPONSE": (
                409,
                "NO_REPLAYABLE_RESPONSE",
                "没有可通过当前校验的已有响应，无法离线恢复",
            ),
            "OFFLINE_REPLAY_VALIDATION_FAILED": (
                422,
                "OFFLINE_REPLAY_VALIDATION_FAILED",
                "指定Invocation无法通过Schema或业务校验，无法离线恢复",
            ),
            "SCENE_NOT_FOUND": (404, "SCENE_NOT_FOUND", "指定Scene不存在"),
            "NO_PENDING_SCENE": (409, "NO_PENDING_SCENE", "没有待恢复的Scene"),
            "RUN_HAS_NO_SCENES": (409, "RUN_HAS_NO_SCENES", "Run没有可分析Scene"),
        }
        status, err, msg = mapping.get(code, (422, "OFFLINE_REPLAY_FAILED", code))
        raise error(status, err, msg) from exc
    return SceneAnalysisOfflineReplayResponse(
        run_id=result.run_id,
        scene_id=result.scene_id,
        artifact_id=result.artifact_id,
        invocation_id=result.invocation_id,
        status=result.status,
        completed_scene_count=result.completed_scene_count,
        remaining_scene_count=result.remaining_scene_count,
        remaining_scene_ids=result.remaining_scene_ids,
        offline_replay_available=result.offline_replay_available,
        idempotent_replay=result.idempotent_replay,
        message=result.message,
        http_request_sent=False,
        request_id=result.request_id,
    )


@router.post("/analysis-runs/{run_id}/retry", response_model=AnalysisRunAccepted, status_code=202)
async def retry_analysis_run(
    run_id: int,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    session_factory=Depends(get_session_factory),
) -> AnalysisRunAccepted:
    old = session.get(AnalysisRun, run_id)
    if old is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    if old.status != "failed":
        raise error(409, "RUN_NOT_RETRYABLE", "仅失败运行可以重跑")
    chapter = session.get(Chapter, int(old.subject_id))
    if chapter is None:
        raise error(404, "CHAPTER_NOT_FOUND", "章节不存在")
    request = AnalysisRunCreate(
        provider_name=old.provider,
        force=True,
        execution_mode=old.execution_mode,
        cloud_consent=old.cloud_consent,
    )
    provider = gateway.get(request.provider_name)
    health = await provider.health()
    if health.status != "healthy":
        raise error(422, "MODEL_SERVER_NOT_RUNNING", "模型服务未运行，暂时不能重试")
    run = create_run_record(session, chapter, request, gateway, retry_of=old.id)
    background.add_task(execute_scene_pipeline, session_factory, gateway, run.id)
    return AnalysisRunAccepted(run_id=run.id, status=run.status)


@router.get("/chapters/{chapter_id}/scenes", response_model=list[SceneResponse])
def list_scenes(chapter_id: int, session: Session = Depends(get_db)) -> list[Scene]:
    latest_run_id = session.scalar(
        select(AnalysisRun.id)
        .where(
            AnalysisRun.subject_id == str(chapter_id),
            AnalysisRun.subject_type == "chapter",
            AnalysisRun.status == "succeeded",
        )
        .order_by(desc(AnalysisRun.id))
        .limit(1)
    )
    if latest_run_id is None:
        return []
    run = session.get(AnalysisRun, latest_run_id)
    if run is None:
        return []
    from app.services.scene_analysis_progress import load_revision_scenes

    _revision, scenes = load_revision_scenes(session, run)
    return scenes


def resolve_scene(session: Session, scene_id: str) -> Scene | None:
    if scene_id.isdigit():
        return session.get(Scene, int(scene_id))
    return session.scalar(
        select(Scene)
        .join(AnalysisRun, AnalysisRun.id == Scene.created_by_run_id)
        .where(Scene.scene_key == scene_id, AnalysisRun.status == "succeeded")
        .order_by(desc(Scene.created_by_run_id))
    )


@router.get("/analysis-runs/{run_id}/scenes", response_model=list[SceneResponse])
def run_scenes(run_id: int, session: Session = Depends(get_db)) -> list[Scene]:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    from app.services.scene_analysis_progress import load_revision_scenes

    _revision, scenes = load_revision_scenes(session, run)
    return scenes


@router.get(
    "/analysis-runs/{run_id}/model-invocations",
    response_model=list[ModelInvocationResponse],
)
def run_invocations(
    run_id: int,
    include_raw: bool = False,
    session: Session = Depends(get_db),
) -> list[ModelInvocationResponse]:
    if session.get(AnalysisRun, run_id) is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    rows = list(
        session.scalars(
            select(ModelInvocation)
            .where(ModelInvocation.run_id == run_id)
            .order_by(ModelInvocation.id)
        )
    )
    allow_raw = include_raw and get_settings().app_env == "development"
    response: list[ModelInvocationResponse] = []
    for row in rows:
        data = ModelInvocationResponse.model_validate(row).model_dump()
        data["raw_response_text"] = row.raw_response_text if allow_raw else None
        data["input_snapshot_json"] = row.input_snapshot_json if allow_raw else None
        response.append(ModelInvocationResponse.model_validate(data))
    return response


@router.get("/scenes/{scene_id}", response_model=SceneResponse)
def get_scene(scene_id: str, session: Session = Depends(get_db)) -> Scene:
    scene = resolve_scene(session, scene_id)
    if scene is None:
        raise error(404, "SCENE_NOT_FOUND", "场景不存在")
    return scene


@router.get("/scenes/{scene_id}/analysis-artifacts", response_model=list[ArtifactResponse])
def scene_artifacts(scene_id: str, session: Session = Depends(get_db)) -> list[AnalysisArtifact]:
    scene = resolve_scene(session, scene_id)
    if scene is None:
        raise error(404, "SCENE_NOT_FOUND", "场景不存在")
    return list(
        session.scalars(
            select(AnalysisArtifact)
            .where(
                AnalysisArtifact.subject_type == "scene",
                AnalysisArtifact.subject_id == str(scene.id),
            )
            .order_by(AnalysisArtifact.id)
        )
    )


def _serialize_scene_result_item(bundle) -> SceneResultItem:
    scene = bundle.scene
    artifact_view: SceneResultArtifact | None = None
    if bundle.artifact is not None:
        artifact_view = SceneResultArtifact(
            id=bundle.artifact.id,
            schema_version=bundle.artifact.schema_version,
            prompt_version=bundle.artifact.prompt_version,
            provider=bundle.provider,
            model=bundle.model,
            confidence=bundle.artifact.confidence,
            validation_status=bundle.artifact.validation_status,
            created_at=bundle.artifact.created_at,
            offline_recovered=bundle.offline_recovered,
            analysis=bundle.analysis,
        )
    return SceneResultItem(
        scene=SceneResultScene(
            id=scene.id,
            scene_key=scene.scene_key,
            ordinal=scene.ordinal,
            start_paragraph_id=scene.start_paragraph_id,
            end_paragraph_id=scene.end_paragraph_id,
            paragraph_count=bundle.paragraph_count,
            is_single_paragraph=bundle.is_single_paragraph,
            boundary_source=scene.boundary_source,
            boundary_revision_id=scene.boundary_revision_id,
            boundary_detected=scene.boundary_detected,
            boundary_confidence=scene.boundary_confidence,
        ),
        analysis_artifact=artifact_view,
        evidence=[SceneEvidenceItem(**item) for item in bundle.evidence],
        illegal_evidence=bundle.illegal_evidence,
        revision=None,
    )


def _serialize_run_results(bundle: RunResultsBundle) -> RunResultsResponse:
    revision = bundle.boundary_revision
    revision_info = None
    if revision is not None:
        revision_info = RunResultsBoundaryRevisionInfo(
            id=revision.id,
            revision_number=revision.revision_number,
            coverage_rate=revision.coverage_rate,
            confirmed_by=revision.confirmed_by,
            confirmed_at=revision.confirmed_at,
        )
    return RunResultsResponse(
        run=RunResultsRunInfo(
            id=bundle.run.id,
            status=bundle.run.status,
            provider=bundle.run.provider,
            model=bundle.run.model,
            prompt_version=bundle.run.prompt_version,
            schema_version=bundle.run.schema_version,
            analysis_mode=bundle.run.analysis_mode,
            execution_mode=bundle.run.execution_mode,
            completed_at=bundle.run.completed_at,
        ),
        chapter=RunResultsChapterInfo(
            id=bundle.chapter.id,
            book_id=bundle.chapter.book_id,
            chapter_index=bundle.chapter.chapter_index,
            title=bundle.chapter.title,
            display_title=bundle.chapter.display_title or None,
        ),
        boundary_revision=revision_info,
        summary=RunResultsSummary(**bundle.summary),
        scenes=[_serialize_scene_result_item(item) for item in bundle.scenes],
    )


def _require_completed_run(session: Session, run_id: int) -> AnalysisRun:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    if run.status != "succeeded":
        raise error(
            409,
            "RUN_NOT_COMPLETED",
            "该分析运行尚未完成，无法查看完整结果",
        )
    return run


@router.get("/analysis-runs/{run_id}/results", response_model=RunResultsResponse)
def run_results(run_id: int, session: Session = Depends(get_db)) -> RunResultsResponse:
    run = _require_completed_run(session, run_id)
    try:
        bundle = build_run_results(session, run)
    except ValueError as exc:
        raise error(404, str(exc), "结果关联章节不存在")
    return _serialize_run_results(bundle)


@router.get("/scenes/{scene_id}/analysis", response_model=SceneResultItem)
def scene_analysis(scene_id: str, session: Session = Depends(get_db)) -> SceneResultItem:
    scene = resolve_scene(session, scene_id)
    if scene is None:
        raise error(404, "SCENE_NOT_FOUND", "场景不存在")
    run = session.get(AnalysisRun, scene.created_by_run_id)
    if run is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    from app.services.scene_results_service import (
        _chapter_paragraph_ids,
        build_scene_bundle,
    )

    ordered_ids = _chapter_paragraph_ids(session, scene.chapter_id)
    invocations = list(
        session.scalars(
            select(ModelInvocation).where(
                ModelInvocation.run_id == run.id,
                ModelInvocation.task_type == "scene_analysis",
            )
        )
    )
    bundle = build_scene_bundle(session, run, scene, ordered_ids, invocations)
    return _serialize_scene_result_item(bundle)


@router.get("/scenes/{scene_id}/paragraphs", response_model=SceneParagraphsResponse)
def scene_paragraphs(scene_id: str, session: Session = Depends(get_db)) -> SceneParagraphsResponse:
    scene = resolve_scene(session, scene_id)
    if scene is None:
        raise error(404, "SCENE_NOT_FOUND", "场景不存在")
    ordered = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == scene.chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    ids = [item.id for item in ordered]
    try:
        start = ids.index(scene.start_paragraph_id)
        end = ids.index(scene.end_paragraph_id)
    except ValueError:
        raise error(422, "SCENE_RANGE_INVALID", "场景段落范围无效")
    if start > end:
        start, end = end, start
    in_scene_ids = set(ids[start : end + 1])
    return SceneParagraphsResponse(
        scene_id=scene.id,
        scene_key=scene.scene_key,
        ordinal=scene.ordinal,
        start_paragraph_id=scene.start_paragraph_id,
        end_paragraph_id=scene.end_paragraph_id,
        paragraphs=[
            SceneParagraphItem(
                id=item.id,
                paragraph_index=item.paragraph_index,
                raw_text=item.raw_text,
                in_scene=item.id in in_scene_ids,
            )
            for item in ordered[start : end + 1]
        ],
    )


@router.get("/analysis-runs/{run_id}/results/export")
def export_run_results(
    run_id: int, format: str = "json", session: Session = Depends(get_db)
):
    from fastapi.responses import JSONResponse, PlainTextResponse

    run = _require_completed_run(session, run_id)
    try:
        bundle = build_run_results(session, run)
    except ValueError as exc:
        raise error(404, str(exc), "结果关联章节不存在")
    if format == "markdown":
        from app.services.scene_results_export import render_markdown

        return PlainTextResponse(
            render_markdown(bundle),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename=run-{run_id}-results.md"
            },
        )
    payload = _serialize_run_results(bundle).model_dump(mode="json")
    return JSONResponse(
        payload,
        headers={
            "Content-Disposition": f"attachment; filename=run-{run_id}-results.json"
        },
    )
