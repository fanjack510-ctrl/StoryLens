"""Reader Journey API routes."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisRun,
    Chapter,
    ChapterReaderJourneySummary,
    ReaderJourneyPhase,
    ReaderJourneyRun,
    SceneReaderJourneyProfile,
)
from app.db.session import get_db, get_session_factory
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.registry import get_model_gateway
from app.schemas.reader_journey import (
    CHAPTER_CONTRACT_VERSION,
    SCENE_CONTRACT_VERSION,
    SCENE_PROMPT_VERSION,
    ReaderJourneyCreateRequest,
    ReaderJourneyPhaseSummary,
    ReaderJourneyPreflightRequest,
    ReaderJourneyPreflightResponse,
    ReaderJourneyProfileSummary,
    ReaderJourneyProgressResponse,
    ReaderJourneyResultResponse,
    ReaderJourneyOfflineReplayRequest,
    ReaderJourneyOfflineReplayResponse,
    ReaderJourneyResumeRequest,
    ReaderJourneyRunAccepted,
    ReaderJourneySemanticRecalibrateRequest,
    ReaderJourneySemanticRecalibrateResponse,
)
from app.services.credentials.service import get_credential_store
from app.services.reader_journey_batch_planner import PLANNER_VERSION
from app.services.reader_journey_engagement import compute_engagement
from app.services.reader_journey_offline_replay import offline_replay_journey_profiles
from app.services.reader_journey_pipeline import build_preflight_payload, execute_reader_journey
from app.services.reader_journey_progress import (
    find_recoverable_journey_run,
    load_revision_scenes,
    reader_journey_progress,
    require_completed_scene_analysis,
)
from app.services.reader_journey_semantic_calibrate import semantic_recalibrate_journey_run
from app.services.reader_journey_version import (
    is_v2_journey_run,
    merge_run_provenance,
    new_journey_version_fields,
    resolve_versions_for_new_run,
)
from app.services.reader_journey_visualization import build_reader_journey_visualization
from app.services.reader_journey_v2_compatibility import (
    enrich_result_compatibility,
    is_v2_contract,
)
from app.services.analysis_integrity_guard import (
    redact_visualization_for_integrity,
    scan_reader_journey_integrity,
)
from app.services.analysis_grounding import ERROR_RUN_SCOPE


router = APIRouter(prefix="/api/v1")


def error(status_code: int, code: str, message: str, **details) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error_code": code, "message": message, "details": details or {}},
    )


def _serialize_profile(row: SceneReaderJourneyProfile, genre: str) -> ReaderJourneyProfileSummary:
    payload = json.loads(row.payload_json or "{}")
    from app.schemas.reader_journey import SceneReaderJourneyProfileItem

    profile = SceneReaderJourneyProfileItem.model_validate(payload)
    engagement = compute_engagement(profile, genre=genre)
    return ReaderJourneyProfileSummary(
        scene_id=row.scene_id,
        scene_ordinal=row.scene_ordinal,
        scene_value_summary=row.scene_value_summary,
        dominant_emotion=row.dominant_emotion,
        engagement=engagement,
        reader_question_in=[item.get("question", "") for item in payload.get("reader_question_in", [])],
        reader_question_out=[item.get("question", "") for item in payload.get("reader_question_out", [])],
        payoffs=[item.get("summary", "") for item in payload.get("payoffs", [])],
        hooks=[item.get("summary", "") for item in payload.get("hooks", [])],
        risk_points=[item.get("summary", "") for item in payload.get("risk_points", [])],
        evidence_paragraph_ids=list(payload.get("evidence_paragraph_ids", [])),
        confidence=row.confidence,
    )


def _serialize_result(session: Session, journey_run: ReaderJourneyRun) -> ReaderJourneyResultResponse:
    phases = list(
        session.scalars(
            select(ReaderJourneyPhase)
            .where(ReaderJourneyPhase.reader_journey_run_id == journey_run.id)
            .order_by(ReaderJourneyPhase.ordinal)
        )
    )
    profiles = list(
        session.scalars(
            select(SceneReaderJourneyProfile)
            .where(SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id)
            .order_by(SceneReaderJourneyProfile.scene_ordinal)
        )
    )
    summary = session.scalar(
        select(ChapterReaderJourneySummary).where(
            ChapterReaderJourneySummary.reader_journey_run_id == journey_run.id
        )
    )
    chapter_summary = None
    deterministic = None
    diagnosis = None
    if summary:
        chapter_summary = {
            "chapter_value_summary": summary.chapter_value_summary,
            "overall_engagement_score": summary.overall_engagement_score,
            "chapter_reader_question_chain": json.loads(summary.chapter_reader_question_chain_json or "[]"),
            "pacing_diagnosis": json.loads(summary.pacing_diagnosis_json or "[]"),
        }
        deterministic = json.loads(summary.deterministic_statistics_json or "{}")
        diagnosis = summary.one_sentence_diagnosis
    visualization = None
    try:
        integrity_payload = scan_reader_journey_integrity(session, journey_run=journey_run)
    except Exception:
        integrity_payload = {
            "integrity_status": "unavailable",
            "trusted": False,
            "issues": [],
        }
    if journey_run.status == "succeeded":
        try:
            visualization = build_reader_journey_visualization(session, journey_run)
            visualization = redact_visualization_for_integrity(visualization, integrity_payload)
        except Exception:
            visualization = None
    contract_version = journey_run.scene_contract_version
    compat = enrich_result_compatibility(
        {},
        scene_contract_version=contract_version,
        scene_prompt_version=journey_run.scene_prompt_version,
        formula_version=journey_run.formula_version,
    )
    v2_lifecycle = None
    v2_diagnoses = None
    if is_v2_contract(contract_version) and deterministic:
        raw_life = deterministic.get("question_lifecycle")
        raw_diag = deterministic.get("scene_diagnoses")
        if isinstance(raw_life, list):
            v2_lifecycle = raw_life
        if isinstance(raw_diag, list):
            v2_diagnoses = raw_diag
    return ReaderJourneyResultResponse(
        journey_run_id=journey_run.id,
        analysis_run_id=journey_run.analysis_run_id,
        book_id=journey_run.book_id,
        chapter_id=journey_run.chapter_id,
        status=journey_run.status,
        provider_name=journey_run.provider_name,
        model_name=journey_run.model_name,
        scene_prompt_version=journey_run.scene_prompt_version,
        chapter_prompt_version=journey_run.chapter_prompt_version,
        formula_version=journey_run.formula_version,
        scene_contract_version=contract_version,
        contract_version=contract_version,
        calibration_status_label=compat.get("calibration_status_label"),
        legacy_uncalibrated=bool(compat.get("legacy_uncalibrated")),
        display_mode=compat.get("display_mode"),
        phases=[
            ReaderJourneyPhaseSummary(
                ordinal=phase.ordinal,
                title=phase.title,
                start_scene_ordinal=phase.start_scene_ordinal,
                end_scene_ordinal=phase.end_scene_ordinal,
                primary_reader_question=phase.primary_reader_question,
                dominant_emotion=phase.dominant_emotion,
                reading_payoff=phase.reading_payoff,
                continuation_motivation=phase.continuation_motivation,
                summary=phase.summary,
                confidence=phase.confidence,
            )
            for phase in phases
        ],
        scene_profiles=[_serialize_profile(item, journey_run.genre) for item in profiles],
        chapter_summary=chapter_summary,
        deterministic_statistics=deterministic,
        one_sentence_diagnosis=diagnosis,
        visualization=visualization,
        created_at=journey_run.created_at,
        started_at=journey_run.started_at,
        updated_at=journey_run.updated_at,
        completed_at=journey_run.completed_at,
        scene_revision_id=journey_run.scene_revision_id,
        result_status=journey_run.result_status,
        error_code=journey_run.root_error_code,
        retryable=bool(journey_run.retryable),
        total_scene_count=journey_run.total_scene_count,
        completed_scene_count=journey_run.completed_scene_count,
        v2_question_lifecycle=v2_lifecycle,
        v2_scene_diagnoses=v2_diagnoses,
        integrity=integrity_payload,
        integrity_status=str(integrity_payload.get("integrity_status") or ""),
        trusted=bool(integrity_payload.get("trusted")),
    )


@router.post(
    "/analysis-runs/{run_id}/reader-journey/preflight",
    response_model=ReaderJourneyPreflightResponse,
)
def reader_journey_preflight(
    run_id: int,
    request: ReaderJourneyPreflightRequest | None = None,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
) -> ReaderJourneyPreflightResponse:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    if run.status != "succeeded":
        raise error(409, "ANALYSIS_RUN_NOT_SUCCEEDED", "分析运行尚未成功完成")
    _revision, scenes = load_revision_scenes(session, run.id)
    require_completed_scene_analysis(session, run, scenes)
    try:
        store = get_credential_store()
    except Exception:
        store = None
    payload = build_preflight_payload(
        session,
        run,
        gateway=gateway,
        store=store,
        cloud_consent=bool(request.cloud_consent if request else False),
        provider_name=request.provider_name if request else None,
    )
    return ReaderJourneyPreflightResponse.model_validate(payload)


@router.post(
    "/analysis-runs/{run_id}/reader-journey",
    response_model=ReaderJourneyRunAccepted,
    status_code=202,
)
async def create_reader_journey(
    run_id: int,
    request: ReaderJourneyCreateRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    session_factory: sessionmaker = Depends(get_session_factory),
) -> ReaderJourneyRunAccepted:
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    if run.status != "succeeded":
        raise error(409, "ANALYSIS_RUN_NOT_SUCCEEDED", "分析运行尚未成功完成")
    if run.sends_content_to_cloud and not request.cloud_consent:
        raise error(422, "CLOUD_CONSENT_REQUIRED", "需要云端正文传输同意")
    existing = session.scalar(
        select(ReaderJourneyRun).where(
            ReaderJourneyRun.analysis_run_id == run.id,
            ReaderJourneyRun.client_request_id == request.client_request_id,
        )
    )
    if existing:
        return ReaderJourneyRunAccepted(
            journey_run_id=existing.id,
            status=existing.status,
            idempotent_replay=True,
        )
    recoverable = find_recoverable_journey_run(session, run.id)
    if recoverable is not None and not request.force_new_version:
        progress = reader_journey_progress(session, recoverable)
        return ReaderJourneyRunAccepted(
            journey_run_id=recoverable.id,
            status=recoverable.status,
            existing_journey_run_id=recoverable.id,
            idempotent_replay=True,
            recovery_recommended=progress.recovery_safe,
            creation_blocked_reason="ACTIVE_OR_RECOVERABLE_JOURNEY_EXISTS",
        )
    _revision, scenes = load_revision_scenes(session, run.id)
    require_completed_scene_analysis(session, run, scenes)
    chapter = session.get(Chapter, int(run.subject_id))
    version_fields = new_journey_version_fields()
    journey_run = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=chapter.book_id if chapter else 0,
        chapter_id=int(run.subject_id),
        status="queued",
        current_stage=None,
        provider_name=request.provider_name or run.provider,
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
        cloud_consent=request.cloud_consent,
        client_request_id=request.client_request_id,
        failure_details_json=version_fields["failure_details_json"],
    )
    session.add(journey_run)
    session.commit()
    background.add_task(execute_reader_journey, session_factory, gateway, journey_run.id)
    return ReaderJourneyRunAccepted(journey_run_id=journey_run.id, status=journey_run.status)


@router.get(
    "/analysis-runs/{run_id}/reader-journey",
    response_model=ReaderJourneyResultResponse | None,
)
def get_reader_journey_for_run(
    run_id: int,
    book_id: int | None = None,
    chapter_id: int | None = None,
    journey_run_id: int | None = None,
    session: Session = Depends(get_db),
) -> ReaderJourneyResultResponse | None:
    analysis_run = session.get(AnalysisRun, run_id)
    if analysis_run is None:
        raise error(404, "ANALYSIS_RUN_NOT_FOUND", "分析运行不存在")
    if chapter_id is not None and str(analysis_run.subject_id) != str(chapter_id):
        raise error(
            409,
            ERROR_RUN_SCOPE,
            "analysis_run与chapter不匹配",
            analysis_run_id=run_id,
            chapter_id=chapter_id,
        )
    if book_id is not None:
        chapter = (
            session.get(Chapter, int(analysis_run.subject_id))
            if str(analysis_run.subject_id).isdigit()
            else None
        )
        if chapter is None or int(chapter.book_id) != int(book_id):
            raise error(
                409,
                ERROR_RUN_SCOPE,
                "analysis_run与book不匹配",
                analysis_run_id=run_id,
                book_id=book_id,
            )
    journey_run: ReaderJourneyRun | None = None
    if journey_run_id is not None:
        journey_run = session.get(ReaderJourneyRun, journey_run_id)
        if journey_run is None or int(journey_run.analysis_run_id) != int(run_id):
            raise error(404, "READER_JOURNEY_RUN_NOT_FOUND", "读者旅程运行不存在")
    else:
        journey_run = session.scalar(
            select(ReaderJourneyRun)
            .where(ReaderJourneyRun.analysis_run_id == run_id)
            .order_by(ReaderJourneyRun.id.desc())
        )
    if journey_run is None:
        return None
    if book_id is not None and int(journey_run.book_id) != int(book_id):
        raise error(409, ERROR_RUN_SCOPE, "reader journey与book不匹配", book_id=book_id)
    if chapter_id is not None and int(journey_run.chapter_id) != int(chapter_id):
        raise error(409, ERROR_RUN_SCOPE, "reader journey与chapter不匹配", chapter_id=chapter_id)
    return _serialize_result(session, journey_run)


@router.get(
    "/reader-journey-runs/{journey_run_id}",
    response_model=ReaderJourneyResultResponse,
)
def get_reader_journey_run(
    journey_run_id: int,
    session: Session = Depends(get_db),
) -> ReaderJourneyResultResponse:
    journey_run = session.get(ReaderJourneyRun, journey_run_id)
    if journey_run is None:
        raise error(404, "READER_JOURNEY_RUN_NOT_FOUND", "读者旅程运行不存在")
    return _serialize_result(session, journey_run)


@router.get(
    "/reader-journey-runs/{journey_run_id}/progress",
    response_model=ReaderJourneyProgressResponse,
)
def reader_journey_progress_endpoint(
    journey_run_id: int,
    session: Session = Depends(get_db),
) -> ReaderJourneyProgressResponse:
    journey_run = session.get(ReaderJourneyRun, journey_run_id)
    if journey_run is None:
        raise error(404, "READER_JOURNEY_RUN_NOT_FOUND", "读者旅程运行不存在")
    progress = reader_journey_progress(session, journey_run)
    return ReaderJourneyProgressResponse.model_validate(progress.as_dict())


@router.post(
    "/reader-journey-runs/{journey_run_id}/resume",
    response_model=ReaderJourneyRunAccepted,
    status_code=202,
)
async def resume_reader_journey(
    journey_run_id: int,
    request: ReaderJourneyResumeRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    session_factory: sessionmaker = Depends(get_session_factory),
) -> ReaderJourneyRunAccepted:
    journey_run = session.get(ReaderJourneyRun, journey_run_id)
    if journey_run is None:
        raise error(404, "READER_JOURNEY_RUN_NOT_FOUND", "读者旅程运行不存在")
    if journey_run.status == "succeeded":
        return ReaderJourneyRunAccepted(journey_run_id=journey_run.id, status=journey_run.status)
    # Orphan fake-running (no heartbeat / unfinished invocation) → recoverable first.
    from app.services.reader_journey_recovery import (
        JOURNEY_ACTIVE_WORKER_STATUSES,
        reclaim_stale_journey_if_needed,
    )

    if journey_run.status in JOURNEY_ACTIVE_WORKER_STATUSES:
        reclaim_stale_journey_if_needed(session, journey_run)
        session.refresh(journey_run)
    if journey_run.status in {
        "scene_profiles_running",
        "chapter_synthesis_running",
        "running",
        "summary_running",
        "phase_analysis_running",
    }:
        raise error(409, "READER_JOURNEY_ALREADY_RUNNING", "读者旅程正在运行")
    progress = reader_journey_progress(session, journey_run)
    if progress.blind_resume_blocked:
        reason = progress.resume_block_reason
        message = {
            "offline_replay_required": "请先离线恢复已有响应，再恢复剩余任务",
            "contract_outdated": "请升级Reader Journey契约后恢复",
            "planner_outdated": "请升级批次规划后恢复",
        }.get(reason or "", "当前失败态不支持盲目恢复；请按恢复预检重试")
        raise error(
            409,
            journey_run.root_error_code or "JOURNEY_RESUME_BLOCKED",
            message,
        )
    analysis_run = session.get(AnalysisRun, journey_run.analysis_run_id)
    if analysis_run and analysis_run.sends_content_to_cloud and not request.cloud_consent:
        raise error(422, "CLOUD_CONSENT_REQUIRED", "需要云端正文传输同意")
    previous_contract = journey_run.scene_contract_version
    previous_prompt = journey_run.scene_prompt_version
    details: dict = {}
    try:
        details = json.loads(journey_run.failure_details_json or "{}")
    except json.JSONDecodeError:
        details = {}
    # Never convert an existing V2 run into legacy on resume, and never auto-upgrade
    # a legacy run into V2 (user must force_new_version to create a new V2 run).
    if is_v2_journey_run(journey_run):
        v2 = resolve_versions_for_new_run(pipeline_id="v2")
        for field, value in v2.as_run_fields().items():
            setattr(journey_run, field, value)
        journey_run.failure_details_json = merge_run_provenance(
            journey_run.failure_details_json, v2
        )
    else:
        if previous_contract != SCENE_CONTRACT_VERSION:
            audit = details.get("resume_audit")
            audits = audit if isinstance(audit, list) else ([audit] if audit else [])
            audits.append(
                {
                    "original_scene_contract_version": previous_contract,
                    "resumed_scene_contract_version": SCENE_CONTRACT_VERSION,
                    "prompt_version": SCENE_PROMPT_VERSION,
                    "planner_version": PLANNER_VERSION,
                    "resume_reason": "contract_semantics_upgrade",
                    "previous_prompt_version": previous_prompt,
                }
            )
            details["resume_audit"] = audits
            journey_run.failure_details_json = json.dumps(details, ensure_ascii=False)
        journey_run.scene_prompt_version = SCENE_PROMPT_VERSION
        journey_run.scene_contract_version = SCENE_CONTRACT_VERSION
        journey_run.chapter_contract_version = CHAPTER_CONTRACT_VERSION
    journey_run.status = "queued"
    journey_run.current_stage = None
    journey_run.cloud_consent = request.cloud_consent
    journey_run.planner_version = PLANNER_VERSION
    journey_run.retryable = False
    journey_run.root_error_code = None
    journey_run.root_error_message = None
    journey_run.failed_stage = None
    journey_run.failed_scene_id = None
    journey_run.failed_scene_ordinal = None
    journey_run.failed_invocation_id = None
    journey_run.completed_at = None
    session.commit()
    background.add_task(execute_reader_journey, session_factory, gateway, journey_run.id)
    return ReaderJourneyRunAccepted(journey_run_id=journey_run.id, status=journey_run.status)


@router.post(
    "/reader-journey-runs/{journey_run_id}/scene-profiles/offline-replay",
    response_model=ReaderJourneyOfflineReplayResponse,
)
def offline_replay_reader_journey(
    journey_run_id: int,
    request: ReaderJourneyOfflineReplayRequest | None = None,
    session: Session = Depends(get_db),
) -> ReaderJourneyOfflineReplayResponse:
    journey_run = session.get(ReaderJourneyRun, journey_run_id)
    if journey_run is None:
        raise error(404, "READER_JOURNEY_RUN_NOT_FOUND", "读者旅程运行不存在")
    if journey_run.status in {"scene_profiles_running", "chapter_synthesis_running", "queued"}:
        raise error(409, "READER_JOURNEY_ALREADY_RUNNING", "读者旅程正在运行")
    body = request or ReaderJourneyOfflineReplayRequest()
    if not body.confirmed:
        raise error(422, "CONFIRMATION_REQUIRED", "需要 confirmed=true 才能执行离线重放")
    try:
        result = offline_replay_journey_profiles(
            session,
            journey_run_id,
            invocation_ids=body.invocation_ids,
        )
    except ValueError as exc:
        raise error(404, "READER_JOURNEY_RUN_NOT_FOUND", str(exc)) from exc
    return ReaderJourneyOfflineReplayResponse.model_validate(result)


@router.post(
    "/reader-journey-runs/{journey_run_id}/semantic-recalibrate",
    response_model=ReaderJourneySemanticRecalibrateResponse,
)
def semantic_recalibrate_reader_journey(
    journey_run_id: int,
    request: ReaderJourneySemanticRecalibrateRequest | None = None,
    session: Session = Depends(get_db),
) -> ReaderJourneySemanticRecalibrateResponse:
    """Zero-cost deterministic recalibration from existing Scene Profiles."""
    journey_run = session.get(ReaderJourneyRun, journey_run_id)
    if journey_run is None:
        raise error(404, "READER_JOURNEY_RUN_NOT_FOUND", "读者旅程运行不存在")
    if journey_run.status in {"scene_profiles_running", "chapter_synthesis_running", "queued"}:
        raise error(409, "READER_JOURNEY_ALREADY_RUNNING", "读者旅程正在运行")
    body = request or ReaderJourneySemanticRecalibrateRequest()
    if not body.confirmed:
        raise error(422, "CONFIRMATION_REQUIRED", "需要 confirmed=true 才能执行语义校准")
    try:
        result = semantic_recalibrate_journey_run(session, journey_run_id)
    except ValueError as exc:
        code = str(exc)
        if code == "SCENE_PROFILES_INCOMPLETE":
            raise error(409, code, "Scene Profile 未全部完成，无法离线语义校准") from exc
        raise error(404, "READER_JOURNEY_RUN_NOT_FOUND", str(exc)) from exc
    return ReaderJourneySemanticRecalibrateResponse.model_validate(result)


@router.post("/reader-journey-runs/{journey_run_id}/cancel")
def cancel_reader_journey(
    journey_run_id: int,
    session: Session = Depends(get_db),
) -> dict[str, object]:
    journey_run = session.get(ReaderJourneyRun, journey_run_id)
    if journey_run is None:
        raise error(404, "READER_JOURNEY_RUN_NOT_FOUND", "读者旅程运行不存在")
    if journey_run.status in {"succeeded", "cancelled"}:
        return {"journey_run_id": journey_run.id, "status": journey_run.status}
    journey_run.status = "cancelled"
    journey_run.completed_at = datetime.now(timezone.utc)
    session.commit()
    return {"journey_run_id": journey_run.id, "status": journey_run.status}


@router.get("/reader-journey-runs/{journey_run_id}/export")
def export_reader_journey(
    journey_run_id: int,
    format: str = "json",
    session: Session = Depends(get_db),
):
    journey_run = session.get(ReaderJourneyRun, journey_run_id)
    if journey_run is None:
        raise error(404, "READER_JOURNEY_RUN_NOT_FOUND", "读者旅程运行不存在")
    if format != "json":
        raise error(400, "UNSUPPORTED_FORMAT", "仅支持 json 导出")
    payload = _serialize_result(session, journey_run).model_dump(mode="json")
    return JSONResponse(content=payload)
