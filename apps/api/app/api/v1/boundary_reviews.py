from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.v1.router import error
from app.db.models import (
    AnalysisRun,
    ApplicationSetting,
    BoundaryReviewDecision,
    BoundaryReviewSession,
    BoundaryRevision,
    Chapter,
    Paragraph,
    Scene,
)
from app.db.session import get_db, get_session_factory
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.registry import get_model_gateway
from app.schemas.boundary_review import (
    BoundaryDecisionUpdate,
    BoundaryReviewConfirm,
    BoundaryReviewDecisionResponse,
    BoundaryReviewResponse,
    FinalBoundaryConfirmRequest,
    FinalBoundaryProposalResponse,
    FinalSceneRangeItem,
    ManualBoundaryCreate,
    ReviewParagraph,
    ScenePreviewItem,
    ScenePreviewResponse,
)
from app.schemas.scene import BoundaryConfirmResponse, SceneAnalysisPreflightResponse
from app.schemas.settings import CloudBudgetUpdate
from app.services.budget_reservation import (
    InsufficientBudgetReservation,
    active_reservation_totals,
    available_remaining,
    reserve_budget,
)
from app.services.cloud_budget import daily_usage
from app.services.cloud_pricing import pricing_status
from app.services.staged_budget import (
    STAGE_ANALYSIS,
    estimate_stage2_scene_analysis,
    exceeded_dimensions,
)
from app.services.boundary_review_mode import get_boundary_review_mode, is_confirm_only
from app.services.boundary_review_service import (
    BoundaryReviewIncomplete,
    confirm_review,
    confirm_review_from_final_proposal,
    analyze_confirmed_review,
    create_review_session,
    preview_ranges,
    update_counts,
)
from app.services.final_boundary_proposal import build_final_boundary_proposal

router = APIRouter(prefix="/api/v1")


def _budget_http_error(exc: InsufficientBudgetReservation) -> HTTPException:
    return HTTPException(status_code=409, detail=exc.as_error_detail())


def _stage2_context(session: Session, review: BoundaryReviewSession):
    revision = session.scalar(
        select(BoundaryRevision)
        .where(BoundaryRevision.review_session_id == review.id)
        .order_by(desc(BoundaryRevision.id))
    )
    scenes = []
    if revision is not None:
        scenes = list(
            session.scalars(
                select(Scene)
                .where(Scene.boundary_revision_id == revision.id)
                .order_by(Scene.ordinal)
            )
        )
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == review.chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    return revision, scenes, paragraphs


def _stage2_budget_view(session: Session, scenes, paragraphs):
    pricing_path = Path("config/cloud_pricing.json")
    estimate = estimate_stage2_scene_analysis(
        session, scenes, paragraphs, pricing_path=pricing_path
    )
    cloud_row = session.get(ApplicationSetting, "cloud_enabled")
    budget_row = session.get(ApplicationSetting, "cloud_budget_settings")
    cloud_enabled = bool(json.loads(cloud_row.value_json)) if cloud_row else False
    budget = CloudBudgetUpdate.model_validate(
        json.loads(budget_row.value_json) if budget_row else {}
    ).model_dump()
    usage = daily_usage(session, budget, cloud_enabled, pricing_status(pricing_path))
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
    return estimate, remaining, exceeded, {
        "requests": active_req,
        "tokens": active_tok,
        "estimated_cost": round(active_cost, 6),
    }


def _review(session: Session, review_id: int) -> BoundaryReviewSession:
    value = session.get(BoundaryReviewSession, review_id)
    if value is None:
        raise error(404, "BOUNDARY_REVIEW_NOT_FOUND", "边界审阅不存在")
    return value


def _response(session: Session, review: BoundaryReviewSession) -> BoundaryReviewResponse:
    decisions = list(
        session.scalars(
            select(BoundaryReviewDecision)
            .where(BoundaryReviewDecision.review_session_id == review.id)
            .order_by(
                BoundaryReviewDecision.review_priority,
                BoundaryReviewDecision.left_paragraph_id,
            )
        )
    )
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == review.chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    return BoundaryReviewResponse(
        **{
            key: getattr(review, key)
            for key in (
                "id", "book_id", "chapter_id", "analysis_run_id", "prompt_version",
                "provider", "model", "status", "candidate_count", "accepted_count",
                "rejected_count", "manually_added_count", "created_at", "completed_at",
            )
        },
        decisions=[BoundaryReviewDecisionResponse.model_validate(item) for item in decisions],
        paragraphs=[ReviewParagraph.model_validate(item, from_attributes=True) for item in paragraphs],
    )


@router.get("/books/{book_id}/chapters/{chapter_id}/boundary-review")
def get_chapter_review(
    book_id: int, chapter_id: int, session: Session = Depends(get_db)
) -> BoundaryReviewResponse:
    chapter = session.get(Chapter, chapter_id)
    if chapter is None or chapter.book_id != book_id:
        raise error(404, "CHAPTER_NOT_FOUND", "章节不存在")
    review = session.scalar(
        select(BoundaryReviewSession)
        .where(BoundaryReviewSession.chapter_id == chapter_id)
        .order_by(desc(BoundaryReviewSession.id))
    )
    if review is None:
        raise error(404, "BOUNDARY_REVIEW_NOT_FOUND", "本章尚无边界审阅")
    return _response(session, review)


@router.post("/analysis-runs/{run_id}/boundary-review/start", status_code=201)
def start_review(run_id: int, session: Session = Depends(get_db)) -> BoundaryReviewResponse:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    try:
        return _response(session, create_review_session(session, run))
    except ValueError as exc:
        raise error(422, "BOUNDARY_REVIEW_INVALID", str(exc)) from exc


@router.put("/boundary-reviews/{review_id}/decisions/{transition_id}")
def decide(
    review_id: int,
    transition_id: str,
    value: BoundaryDecisionUpdate,
    session: Session = Depends(get_db),
) -> BoundaryReviewResponse:
    review = _review(session, review_id)
    if review.status in {"confirmed", "cancelled", "superseded"}:
        raise error(409, "BOUNDARY_REVIEW_CLOSED", "审阅已经关闭")
    decision = session.scalar(
        select(BoundaryReviewDecision).where(
            BoundaryReviewDecision.review_session_id == review_id,
            BoundaryReviewDecision.transition_id == transition_id,
            BoundaryReviewDecision.model_candidate.is_(True),
        )
    )
    if decision is None:
        raise error(404, "TRANSITION_NOT_FOUND", "候选转换不存在")
    if (
        decision.semantic_conflict
        and value.user_decision == "accept"
        and value.manual_reason_type is None
    ):
        raise error(
            422,
            "MANUAL_CONFLICT_REASON_REQUIRED",
            "接受语义冲突候选时必须选择人工边界原因",
        )
    decision.user_decision = value.user_decision
    decision.user_reason = value.user_reason
    decision.manual_reason_type = value.manual_reason_type
    decision.final_boundary = value.user_decision == "accept"
    review.status = "in_review"
    update_counts(session, review)
    session.commit()
    return _response(session, review)


@router.post("/boundary-reviews/{review_id}/manual-boundaries", status_code=201)
def add_manual(
    review_id: int,
    value: ManualBoundaryCreate,
    session: Session = Depends(get_db),
) -> BoundaryReviewResponse:
    review = _review(session, review_id)
    if review.status in {"confirmed", "cancelled", "superseded"}:
        raise error(409, "BOUNDARY_REVIEW_CLOSED", "审阅已经关闭")
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == review.chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    positions = {item.id: index for index, item in enumerate(paragraphs)}
    index = positions.get(value.left_paragraph_id)
    if index is None or index >= len(paragraphs) - 1:
        raise error(422, "INVALID_BOUNDARY_POSITION", "不能在章节范围外或最后一段后新增边界")
    duplicate = session.scalar(
        select(BoundaryReviewDecision).where(
            BoundaryReviewDecision.review_session_id == review.id,
            BoundaryReviewDecision.left_paragraph_id == value.left_paragraph_id,
        )
    )
    if duplicate:
        raise error(409, "DUPLICATE_BOUNDARY", "该段落间隙已有边界决定")
    session.add(
        BoundaryReviewDecision(
            review_session_id=review.id,
            transition_id=f"M-{value.left_paragraph_id}",
            left_paragraph_id=value.left_paragraph_id,
            right_paragraph_id=paragraphs[index + 1].id,
            model_candidate=False,
            model_confidence=0,
            review_priority="high",
            user_decision="manually_added",
            user_reason=value.user_reason,
            final_boundary=True,
            first_pass_json="{}",
        )
    )
    review.status = "in_review"
    session.flush()
    update_counts(session, review)
    session.commit()
    return _response(session, review)


@router.delete("/boundary-reviews/{review_id}/manual-boundaries/{transition_id}", status_code=204)
def delete_manual(
    review_id: int, transition_id: str, session: Session = Depends(get_db)
) -> Response:
    review = _review(session, review_id)
    decision = session.scalar(
        select(BoundaryReviewDecision).where(
            BoundaryReviewDecision.review_session_id == review.id,
            BoundaryReviewDecision.transition_id == transition_id,
            BoundaryReviewDecision.model_candidate.is_(False),
        )
    )
    if decision is None:
        raise error(404, "MANUAL_BOUNDARY_NOT_FOUND", "人工边界不存在")
    session.delete(decision)
    session.flush()
    update_counts(session, review)
    session.commit()
    return Response(status_code=204)


@router.get("/boundary-reviews/{review_id}/scene-preview")
def preview(review_id: int, session: Session = Depends(get_db)) -> ScenePreviewResponse:
    review = _review(session, review_id)
    paragraphs, _, ranges = preview_ranges(session, review)
    positions = {item.id: index for index, item in enumerate(paragraphs)}
    return ScenePreviewResponse(
        review_id=review.id,
        coverage_rate=1.0,
        scenes=[
            ScenePreviewItem(
                ordinal=index,
                start_paragraph_id=start.id,
                end_paragraph_id=end.id,
                paragraph_count=positions[end.id] - positions[start.id] + 1,
            )
            for index, (start, end) in enumerate(ranges, 1)
        ],
    )


@router.get(
    "/boundary-reviews/{review_id}/scene-analysis-preflight",
    response_model=SceneAnalysisPreflightResponse,
)
def scene_analysis_preflight(
    review_id: int, session: Session = Depends(get_db)
) -> SceneAnalysisPreflightResponse:
    review = _review(session, review_id)
    paragraphs, boundary_ids, ranges = preview_ranges(session, review)
    # Use preview ranges as provisional scenes for estimate before confirm.
    class _Tmp:
        def __init__(self, ordinal, start, end, key):
            self.ordinal = ordinal
            self.start_paragraph_id = start.id
            self.end_paragraph_id = end.id
            self.scene_key = key

    chapter = session.get(Chapter, review.chapter_id)
    provisional = [
        _Tmp(
            index,
            start,
            end,
            f"B{chapter.book_id:04d}-C{chapter.chapter_index:04d}-PRE-{index:04d}",
        )
        for index, (start, end) in enumerate(ranges, 1)
    ]
    estimate, remaining, exceeded, reserved = _stage2_budget_view(
        session, provisional, paragraphs
    )
    return SceneAnalysisPreflightResponse(
        scene_count=estimate.scene_count,
        expected_request_count=estimate.expected_request_count,
        worst_case_request_count=estimate.worst_case_request_count,
        estimated_input_tokens=estimate.estimated_input_tokens,
        worst_case_input_tokens=estimate.worst_case_input_tokens,
        estimated_output_tokens=estimate.estimated_output_tokens,
        worst_case_output_tokens=estimate.worst_case_output_tokens,
        estimated_total_tokens=estimate.estimated_total_tokens,
        worst_case_total_tokens=estimate.worst_case_total_tokens,
        estimated_cost=estimate.estimated_cost,
        worst_case_cost=estimate.worst_case_cost,
        currency=estimate.currency,
        remaining={
            "requests": remaining.requests,
            "tokens": remaining.tokens,
            "estimated_cost": remaining.estimated_cost,
        },
        reserved=reserved,
        within_budget=not exceeded,
        exceeded_dimensions=exceeded,
        pricing_version=estimate.pricing_version,
        estimated=True,
    )


@router.post("/boundary-reviews/{review_id}/confirm", response_model=BoundaryConfirmResponse)
def confirm(
    review_id: int,
    value: BoundaryReviewConfirm,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    session_factory=Depends(get_session_factory),
) -> BoundaryConfirmResponse:
    if is_confirm_only():
        raise error(
            409,
            "CONFIRM_ONLY_MODE",
            "请使用整体确认接口确认场景划分",
        )
    review = _review(session, review_id)
    try:
        revision, scenes = confirm_review(session, review, value.confirmed_by)
    except BoundaryReviewIncomplete as exc:
        raise HTTPException(status_code=409, detail=exc.as_error_detail()) from exc
    except ValueError as exc:
        raise error(409, "BOUNDARY_REVIEW_INCOMPLETE", str(exc)) from exc
    return _launch_stage2_after_confirm(
        session, review, revision, scenes, background, gateway, session_factory
    )


@router.get(
    "/boundary-reviews/{review_id}/final-proposal",
    response_model=FinalBoundaryProposalResponse,
)
def get_final_proposal(
    review_id: int, session: Session = Depends(get_db)
) -> FinalBoundaryProposalResponse:
    review = _review(session, review_id)
    proposal = build_final_boundary_proposal(session, review)
    chapter = session.get(Chapter, review.chapter_id)
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == review.chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    return FinalBoundaryProposalResponse(
        review_id=proposal.review_id,
        analysis_run_id=proposal.analysis_run_id,
        chapter_id=proposal.chapter_id,
        boundary_review_mode=get_boundary_review_mode(),
        validation_status=proposal.validation_status,
        proposal_fingerprint=proposal.proposal_fingerprint,
        final_boundary_left_ids=proposal.final_boundary_left_ids,
        final_scene_ranges=[
            FinalSceneRangeItem.model_validate(item) for item in proposal.final_scene_ranges
        ],
        source_summary=proposal.source_summary,
        unresolved_reason=proposal.unresolved_reason,
        paragraph_count=proposal.paragraph_count,
        scene_count=proposal.scene_count,
        chapter_title=(chapter.display_title or chapter.title) if chapter else None,
        paragraphs=[
            ReviewParagraph(id=p.id, paragraph_index=p.paragraph_index, raw_text=p.raw_text)
            for p in paragraphs
        ],
    )


@router.post(
    "/boundary-reviews/{review_id}/confirm-final-proposal",
    response_model=BoundaryConfirmResponse,
)
def confirm_final_proposal(
    review_id: int,
    value: FinalBoundaryConfirmRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    session_factory=Depends(get_session_factory),
) -> BoundaryConfirmResponse:
    review = _review(session, review_id)
    try:
        revision, scenes, idempotent = confirm_review_from_final_proposal(
            session,
            review,
            confirmed_by=value.confirmed_by,
            proposal_fingerprint=value.proposal_fingerprint,
        )
    except ValueError as exc:
        message = str(exc)
        if "fingerprint" in message:
            raise error(409, "PROPOSAL_FINGERPRINT_MISMATCH", message) from exc
        if "unresolved" in message.lower() or "无法" in message:
            raise error(409, "BOUNDARY_PROPOSAL_UNRESOLVED", message) from exc
        raise error(409, "BOUNDARY_REVIEW_INCOMPLETE", message) from exc

    if idempotent:
        run = session.get(AnalysisRun, review.analysis_run_id)
        return BoundaryConfirmResponse(
            revision_id=revision.id,
            revision_number=revision.revision_number,
            scene_count=len(scenes),
            coverage_rate=revision.coverage_rate,
            run_status=run.status if run else "boundary_confirmed",
            scene_analysis_started=run.status == "scene_analysis_running" if run else False,
            budget_blocked=run.status == "boundary_confirmed_budget_blocked" if run else False,
            stage=STAGE_ANALYSIS,
        )

    return _launch_stage2_after_confirm(
        session, review, revision, scenes, background, gateway, session_factory
    )


def _launch_stage2_after_confirm(
    session: Session,
    review: BoundaryReviewSession,
    revision,
    scenes,
    background: BackgroundTasks,
    gateway: ModelGateway,
    session_factory,
) -> BoundaryConfirmResponse:
    run = session.get(AnalysisRun, review.analysis_run_id)
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == review.chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    estimate, remaining, exceeded, _reserved = _stage2_budget_view(session, scenes, paragraphs)
    if exceeded:
        run.status = "boundary_confirmed_budget_blocked"
        run.error_code = "INSUFFICIENT_BUDGET_RESERVATION"
        run.failed_stage = "scene_analysis_budget"
        run.retryable = True
        hint_parts = []
        if "requests" in exceeded:
            hint_parts.append(
                f"请求次数不足：最坏需要{estimate.worst_case_request_count}次，"
                f"当前剩余{remaining.requests}次。"
            )
        if "tokens" in exceeded:
            hint_parts.append(
                f"Token不足：最坏需要{estimate.worst_case_total_tokens} Token，"
                f"当前剩余{remaining.tokens} Token。"
            )
        if "estimated_cost" in exceeded:
            hint_parts.append(
                f"费用不足：最坏需要约{estimate.worst_case_cost} CNY，"
                f"当前剩余约{remaining.estimated_cost} CNY。"
            )
        run.user_action_hint = " ".join(hint_parts)
        run.raw_output = json.dumps(
            {
                "kind": "budget_block",
                "error_code": "INSUFFICIENT_BUDGET_RESERVATION",
                "stage": STAGE_ANALYSIS,
                "required": {
                    "requests": estimate.worst_case_request_count,
                    "tokens": estimate.worst_case_total_tokens,
                    "estimated_cost": estimate.worst_case_cost,
                },
                "remaining": {
                    "requests": remaining.requests,
                    "tokens": remaining.tokens,
                    "estimated_cost": remaining.estimated_cost,
                },
                "exceeded_dimensions": exceeded,
                "pricing_version": estimate.pricing_version,
            },
            ensure_ascii=False,
        )
        session.commit()
        return BoundaryConfirmResponse(
            revision_id=revision.id,
            revision_number=revision.revision_number,
            scene_count=len(scenes),
            coverage_rate=revision.coverage_rate,
            run_status=run.status,
            scene_analysis_started=False,
            budget_blocked=True,
            stage=STAGE_ANALYSIS,
            required={
                "requests": estimate.worst_case_request_count,
                "tokens": estimate.worst_case_total_tokens,
                "estimated_cost": estimate.worst_case_cost,
            },
            remaining={
                "requests": remaining.requests,
                "tokens": remaining.tokens,
                "estimated_cost": remaining.estimated_cost,
            },
            exceeded_dimensions=exceeded,
            user_action_hint=run.user_action_hint,
        )
    provider = gateway.get(run.provider)
    if provider.capabilities().cloud:
        pricing_path = Path("config/cloud_pricing.json")
        cloud_row = session.get(ApplicationSetting, "cloud_enabled")
        budget_row = session.get(ApplicationSetting, "cloud_budget_settings")
        cloud_enabled = bool(json.loads(cloud_row.value_json)) if cloud_row else False
        budget = CloudBudgetUpdate.model_validate(
            json.loads(budget_row.value_json) if budget_row else {}
        ).model_dump()
        usage = daily_usage(session, budget, cloud_enabled, pricing_status(pricing_path))
        from app.services.run_scoped_budget_auth import apply_run_auth_to_usage

        usage = apply_run_auth_to_usage(run, usage, budget)
        try:
            reserve_budget(
                session,
                run_id=run.id,
                stage=STAGE_ANALYSIS,
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
            run.status = "boundary_confirmed_budget_blocked"
            run.error_code = "INSUFFICIENT_BUDGET_RESERVATION"
            run.failed_stage = "scene_analysis_budget"
            run.retryable = True
            run.user_action_hint = exc.as_error_detail()["user_action_hint"]  # type: ignore[index]
            run.raw_output = json.dumps(
                {"kind": "budget_block", **exc.as_error_detail()}, ensure_ascii=False
            )
            session.commit()
            return BoundaryConfirmResponse(
                revision_id=revision.id,
                revision_number=revision.revision_number,
                scene_count=len(scenes),
                coverage_rate=revision.coverage_rate,
                run_status=run.status,
                scene_analysis_started=False,
                budget_blocked=True,
                stage=STAGE_ANALYSIS,
                required=exc.as_error_detail()["required"],  # type: ignore[arg-type]
                remaining=exc.as_error_detail()["remaining"],  # type: ignore[arg-type]
                exceeded_dimensions=list(exc.exceeded_dimensions),
                user_action_hint=run.user_action_hint,
            )
    run.status = "scene_analysis_running"
    session.commit()
    from app.services.credentials.service import get_credential_store
    from app.services.provider_runtime_service import ProviderRuntimeService

    try:
        store = get_credential_store()
    except Exception:
        store = None
    ProviderRuntimeService.resolve_for_run(
        gateway, session, run, store, task_type="scene_analysis"
    )
    background.add_task(analyze_confirmed_review, session_factory, gateway, review.id)
    return BoundaryConfirmResponse(
        revision_id=revision.id,
        revision_number=revision.revision_number,
        scene_count=len(scenes),
        coverage_rate=revision.coverage_rate,
        run_status=run.status,
        scene_analysis_started=True,
        budget_blocked=False,
        stage=STAGE_ANALYSIS,
    )


@router.post("/boundary-reviews/{review_id}/cancel", status_code=204)
def cancel(review_id: int, session: Session = Depends(get_db)) -> Response:
    review = _review(session, review_id)
    if review.status == "confirmed":
        raise error(409, "BOUNDARY_REVIEW_CONFIRMED", "已确认审阅不能取消")
    review.status = "cancelled"
    review.completed_at = datetime.now(timezone.utc)
    run = session.get(AnalysisRun, review.analysis_run_id)
    run.status = "review_cancelled"
    session.commit()
    return Response(status_code=204)
