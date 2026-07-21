"""Unified Analysis Recovery Center routes (Phase 1D-C1-UAT-12).

Kept outside frozen analysis.py contract surface.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.v1.router import error
from app.db.models import (
    AnalysisRun,
    ApplicationSetting,
    BoundaryReviewSession,
    Chapter,
    Paragraph,
    ReaderJourneyRun,
)
from app.db.session import get_db, get_session_factory
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.registry import get_model_gateway
from app.schemas.analysis_recovery import (
    AnalysisRecoverRequest,
    AnalysisRecoverResponse,
    AnalysisRecoveryPlanResponse,
    FullPipelineBudgetAdvisory,
)
from app.schemas.scene import AnalysisPreflightRequest
from app.schemas.settings import CloudBudgetUpdate
from app.services.analysis_recovery_center import (
    build_full_pipeline_advisory,
    build_recovery_plan,
    execute_unified_recover,
)
from app.services.budget_reservation import active_reservation_totals, available_remaining
from app.services.cloud_budget import daily_usage
from app.services.cloud_pricing import pricing_status
from app.services.credentials.base import CredentialStore
from app.services.credentials.service import get_credential_store
from app.services.provider_eligibility import evaluate_manual_boundary_candidate
from app.services.staged_budget import estimate_stage1_boundary
from app.services.boundary_review_service import analyze_confirmed_review
from app.services.reader_journey_batch_planner import PLANNER_VERSION
from app.services.reader_journey_engagement import load_formula_config
from app.services.reader_journey_pipeline import execute_reader_journey
from app.services.reader_journey_progress import (
    find_recoverable_journey_run,
    load_revision_scenes,
    require_completed_scene_analysis,
)
from app.schemas.reader_journey import (
    CHAPTER_CONTRACT_VERSION,
    CHAPTER_PROMPT_VERSION,
    SCENE_CONTRACT_VERSION,
    SCENE_PROMPT_VERSION,
)

router = APIRouter(tags=["analysis-recovery"])


@router.get(
    "/analysis-runs/{run_id}/recovery-plan",
    response_model=AnalysisRecoveryPlanResponse,
)
def get_analysis_recovery_plan(
    run_id: int,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    store: CredentialStore = Depends(get_credential_store),
) -> AnalysisRecoveryPlanResponse:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    return build_recovery_plan(session, run, gateway, store)


@router.post(
    "/analysis-runs/{run_id}/recover",
    status_code=202,
)
def recover_analysis_run(
    run_id: int,
    request: AnalysisRecoverRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    session_factory=Depends(get_session_factory),
    store: CredentialStore = Depends(get_credential_store),
):
    """Unified recover when recovery_mode=unified; else legacy boundary recover.

    Registered before the frozen analysis.py alias so Recovery Center owns /recover.
    """
    mode = request.recovery_mode
    if mode is None:
        mode = "boundary_checkpoints"
    if mode == "boundary_checkpoints":
        from app.api.v1.analysis import _continue_from_checkpoints_impl
        from app.schemas.scene import BoundaryRecoveryContinueRequest

        legacy = BoundaryRecoveryContinueRequest(
            client_request_id=request.client_request_id,
            cloud_consent=request.cloud_consent,
            confirmed=request.confirmed,
            provider_state_version=request.provider_state_version,
        )
        return _continue_from_checkpoints_impl(
            run_id, legacy, background, session, gateway, session_factory, store
        )
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")

    def _resume_scene() -> None:
        from app.services.scene_analysis_provider_recovery import (
            STATUS_AWAITING_PROVIDER_RECOVERY,
            resume_from_provider_recovery,
        )

        fresh = session.get(AnalysisRun, run_id)
        if fresh is None or fresh.status == "scene_analysis_running":
            return
        if fresh.status == STATUS_AWAITING_PROVIDER_RECOVERY:
            resume_from_provider_recovery(fresh)
        review = session.scalar(
            select(BoundaryReviewSession)
            .where(BoundaryReviewSession.analysis_run_id == fresh.id)
            .order_by(desc(BoundaryReviewSession.id))
        )
        if review is None:
            session.commit()
            return
        try:
            raw = json.loads(fresh.raw_output or "{}")
            if not isinstance(raw, dict):
                raw = {}
        except json.JSONDecodeError:
            raw = {}
        raw["kind"] = "scene_analysis_resume"
        raw["client_request_id"] = request.client_request_id
        fresh.raw_output = json.dumps(raw, ensure_ascii=False, sort_keys=True)
        if fresh.status != "scene_analysis_running":
            fresh.status = "scene_analysis_running"
        fresh.error_code = None
        fresh.error_message = None
        session.commit()
        background.add_task(analyze_confirmed_review, session_factory, gateway, review.id)

    def _start_journey() -> int | None:
        fresh = session.get(AnalysisRun, run_id)
        if fresh is None or fresh.status != "succeeded":
            return None
        existing = session.scalar(
            select(ReaderJourneyRun).where(
                ReaderJourneyRun.analysis_run_id == fresh.id,
                ReaderJourneyRun.client_request_id == request.client_request_id,
            )
        )
        if existing is not None:
            return int(existing.id)
        recoverable = find_recoverable_journey_run(session, fresh.id)
        if recoverable is not None:
            return int(recoverable.id)
        _revision, scenes = load_revision_scenes(session, fresh.id)
        require_completed_scene_analysis(session, fresh, scenes)
        chapter = session.get(Chapter, int(fresh.subject_id))
        formula = load_formula_config()
        journey_run = ReaderJourneyRun(
            analysis_run_id=fresh.id,
            book_id=chapter.book_id if chapter else 0,
            chapter_id=int(fresh.subject_id),
            status="queued",
            current_stage=None,
            provider_name=fresh.provider,
            model_name=fresh.model,
            scene_prompt_version=SCENE_PROMPT_VERSION,
            chapter_prompt_version=CHAPTER_PROMPT_VERSION,
            scene_contract_version=SCENE_CONTRACT_VERSION,
            chapter_contract_version=CHAPTER_CONTRACT_VERSION,
            planner_version=PLANNER_VERSION,
            formula_version=str(formula.get("version", "1.0")),
            genre=str(formula.get("default_genre", "suspense")),
            total_scene_count=len(scenes),
            completed_scene_count=0,
            remaining_scene_count=len(scenes),
            completed_scene_ids_json="[]",
            remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
            cloud_consent=request.cloud_consent,
            client_request_id=request.client_request_id,
        )
        session.add(journey_run)
        session.commit()
        background.add_task(execute_reader_journey, session_factory, gateway, journey_run.id)
        return int(journey_run.id)

    def _resume_boundary() -> int | None:
        from app.api.v1.analysis import (
            _continue_from_checkpoints_impl,
            _evaluate_recovery_provider,
        )
        from app.schemas.scene import BoundaryRecoveryContinueRequest
        from fastapi import HTTPException

        fresh = session.get(AnalysisRun, run_id)
        if fresh is None:
            return None
        if fresh.status in {"boundary_candidates_running", "running", "queued"}:
            return int(fresh.id)
        existing = session.scalar(
            select(AnalysisRun)
            .where(
                AnalysisRun.recovered_from_run_id == fresh.id,
                AnalysisRun.status.in_(
                    [
                        "queued",
                        "running",
                        "boundary_candidates_running",
                        "boundary_candidates_partial",
                        "awaiting_boundary_review",
                        "boundary_confirmed",
                        "scene_analysis_running",
                        "succeeded",
                    ]
                ),
            )
            .order_by(desc(AnalysisRun.id))
        )
        if existing is not None:
            return int(existing.id)
        _provider, eligibility = _evaluate_recovery_provider(
            session, fresh, gateway, store
        )
        legacy = BoundaryRecoveryContinueRequest(
            client_request_id=request.client_request_id,
            cloud_consent=request.cloud_consent,
            confirmed=True,
            provider_state_version=str(eligibility.get("provider_state_version") or ""),
        )
        try:
            result = _continue_from_checkpoints_impl(
                run_id,
                legacy,
                background,
                session,
                gateway,
                session_factory,
                store,
            )
        except HTTPException:
            return None
        return int(getattr(result, "run_id", None) or 0) or None

    return execute_unified_recover(
        session,
        run,
        request,
        gateway,
        store,
        background_resume_scene=_resume_scene if request.resume and request.confirmed else None,
        background_start_journey=_start_journey if request.resume and request.confirmed else None,
        background_resume_boundary=_resume_boundary
        if request.resume and request.confirmed
        else None,
    )


@router.post(
    "/analysis-runs/full-pipeline-preflight",
    response_model=FullPipelineBudgetAdvisory,
)
def full_pipeline_preflight(
    request: AnalysisPreflightRequest,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    store: CredentialStore = Depends(get_credential_store),
) -> FullPipelineBudgetAdvisory:
    """Create-time full-pipeline budget advisory (does not reserve)."""
    chapter = session.get(Chapter, request.chapter_id)
    if chapter is None:
        raise error(404, "CHAPTER_NOT_FOUND", "章节不存在")
    provider = gateway.get(request.provider)
    evaluation = evaluate_manual_boundary_candidate(
        session,
        provider_name=provider.name,
        capabilities=provider.capabilities(),
        store=store,
        pricing_path=Path("config/cloud_pricing.json"),
    )
    if request.provider_state_version != evaluation["provider_state_version"]:
        raise error(409, "PROVIDER_STATE_CHANGED", "Provider状态已变化，请刷新后重新确认。")
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == chapter.id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    estimate = estimate_stage1_boundary(paragraphs, pricing_path=Path("config/cloud_pricing.json"))
    cloud_row = session.get(ApplicationSetting, "cloud_enabled")
    budget_row = session.get(ApplicationSetting, "cloud_budget_settings")
    cloud_enabled = bool(json.loads(cloud_row.value_json)) if cloud_row else False
    budget = CloudBudgetUpdate.model_validate(
        json.loads(budget_row.value_json) if budget_row else {}
    ).model_dump()
    usage = daily_usage(
        session, budget, cloud_enabled, pricing_status(Path("config/cloud_pricing.json"))
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
    return build_full_pipeline_advisory(
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
