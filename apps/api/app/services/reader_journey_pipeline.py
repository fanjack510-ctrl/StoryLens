"""Reader Journey analysis pipeline — Scene profiles + Chapter synthesis."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    Chapter,
    ChapterReaderJourneySummary,
    Paragraph,
    ReaderJourneyPhase,
    ReaderJourneyRun,
    Scene,
    SceneReaderJourneyProfile,
)
from app.model_gateway.gateway import ModelGateway
from app.schemas.reader_journey import (
    CHAPTER_CONTRACT_VERSION,
    CHAPTER_PROMPT_VERSION,
    CONTRACT_VERSION,
    SCENE_CONTRACT_VERSION,
    SCENE_PROMPT_VERSION,
    ChapterReaderJourneySynthesisResult,
    SceneReaderJourneyBatchResult,
    SceneReaderJourneyProfileItem,
)
from app.services.budget_reservation import release_run_reservation, reserve_budget
from app.services.cloud_pricing import pricing_status
from app.services.prompt_service import load_prompt
from app.services.reader_journey_batch_planner import (
    PLANNER_VERSION,
    ReaderJourneySceneBatch,
    format_batch_plan_report,
    plan_scene_batches,
    split_batch_after_truncation,
)
from app.services.reader_journey_engagement import compute_engagement
from app.services.reader_journey_progress import (
    is_scene_profile_complete,
    load_revision_scenes,
    require_completed_scene_analysis,
    scene_analysis_artifact,
    sync_journey_run_counts,
)


def _scenes_for_journey_run(
    session: Session,
    journey_run: ReaderJourneyRun,
    analysis_run: AnalysisRun,
) -> tuple[object | None, list[Scene]]:
    from app.services.scene_boundary_manual_review import (
        SceneBoundaryError,
        load_journey_bound_scenes,
    )

    try:
        return load_journey_bound_scenes(session, journey_run)
    except SceneBoundaryError:
        return load_revision_scenes(session, analysis_run.id)
from app.services.reader_journey_semantic_calibrate import (
    apply_deterministic_qin,
    build_deterministic_chapter_diagnosis,
    build_journey_nodes,
    contains_banned_chapter_phrase,
    enrich_hook_structure,
    inject_consecutive_no_payoff_risks,
)
from app.services.reader_journey_statistics import compute_deterministic_statistics
from app.services.reader_journey_validation import (
    validate_chapter_synthesis,
    validate_scene_batch_result,
    validate_score_distribution,
)
from app.services.scene_pipeline import classify_pipeline_error
from app.services.staged_budget import (
    STAGE_READER_JOURNEY_CHAPTER,
    STAGE_READER_JOURNEY_SCENE,
    BudgetAmounts,
    estimate_reader_journey_chapter_synthesis,
    estimate_reader_journey_scene_profiles,
    estimate_to_dict,
    exceeded_dimensions,
)
from app.services.structured_output import StructuredOutputError, generate_validated
from app.services.validation_errors import StructuralValidationError

logger = logging.getLogger(__name__)


class JourneySingleProfileTruncatedError(StructuredOutputError):
    def __init__(
        self,
        message: str = "单个Scene Profile输出仍被截断",
        *,
        failed_invocation_id: int | None = None,
    ) -> None:
        super().__init__(
            message,
            "JOURNEY_SINGLE_PROFILE_OUTPUT_TRUNCATED",
            category="structured_output",
            retryable=False,
            failed_invocation_id=failed_invocation_id,
        )


def _budget_remaining(
    session: Session,
    pricing_path: Path,
    analysis_run: AnalysisRun | None = None,
) -> BudgetAmounts:
    from app.db.models import ApplicationSetting
    from app.schemas.settings import CloudBudgetUpdate
    from app.services.budget_reservation import active_reservation_totals, available_remaining
    from app.services.cloud_budget import daily_usage
    from app.services.run_scoped_budget_auth import apply_run_auth_to_usage

    cloud_row = session.get(ApplicationSetting, "cloud_enabled")
    budget_row = session.get(ApplicationSetting, "cloud_budget_settings")
    cloud_enabled = bool(json.loads(cloud_row.value_json)) if cloud_row else False
    budget = CloudBudgetUpdate.model_validate(
        json.loads(budget_row.value_json) if budget_row else {}
    ).model_dump()
    pricing = pricing_status(pricing_path)
    usage = daily_usage(session, budget, cloud_enabled, pricing)
    usage = apply_run_auth_to_usage(analysis_run, usage, budget)
    active_req, active_tok, active_cost = active_reservation_totals(session)
    return available_remaining(
        remaining_requests=usage["remaining_requests"],
        remaining_tokens=usage["remaining_tokens"],
        remaining_cost=usage["remaining_estimated_cost"],
        reserved_requests=active_req,
        reserved_tokens=active_tok,
        reserved_cost=active_cost,
    )


def _paragraph_ids_for_scene(scene: Scene, paragraphs: list[Paragraph], position: dict[str, int]) -> set[str]:
    start = position[scene.start_paragraph_id]
    end = position[scene.end_paragraph_id]
    return {item.id for item in paragraphs[start : end + 1]}


def _collect_evidence_rows(profile: SceneReaderJourneyProfileItem) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for paragraph_id in profile.evidence_paragraph_ids:
        rows.append(("evidence_paragraph_ids", paragraph_id))
    for index, item in enumerate(profile.reader_question_answered):
        for paragraph_id in item.evidence_paragraph_ids:
            rows.append((f"reader_question_answered[{index}].evidence", paragraph_id))
    for index, item in enumerate(profile.payoffs):
        for paragraph_id in item.evidence_paragraph_ids:
            rows.append((f"payoffs[{index}].evidence", paragraph_id))
    for index, item in enumerate(profile.hooks):
        for paragraph_id in item.evidence_paragraph_ids:
            rows.append((f"hooks[{index}].evidence", paragraph_id))
    for index, item in enumerate(profile.techniques):
        for paragraph_id in item.evidence_paragraph_ids:
            rows.append((f"techniques[{index}].evidence", paragraph_id))
    for index, item in enumerate(profile.risk_points):
        for paragraph_id in item.evidence_paragraph_ids:
            rows.append((f"risk_points[{index}].evidence", paragraph_id))
    for index, item in enumerate(profile.information_changes):
        for paragraph_id in item.evidence_paragraph_ids:
            rows.append((f"information_changes[{index}].evidence", paragraph_id))
    for index, item in enumerate(profile.character_effects):
        for paragraph_id in item.evidence_paragraph_ids:
            rows.append((f"character_effects[{index}].evidence", paragraph_id))
    return rows


def _persist_profile(
    session: Session,
    journey_run: ReaderJourneyRun,
    profile: SceneReaderJourneyProfileItem,
    *,
    paragraphs_by_id: dict[str, Paragraph],
    genre: str,
) -> SceneReaderJourneyProfile | None:
    if is_scene_profile_complete(session, journey_run.id, profile.scene_id):
        return None
    engagement = compute_engagement(profile, genre=genre)
    payload = profile.model_dump()
    from app.db.models import Scene
    from app.services.analysis_context_fingerprint import (
        compute_source_context_fingerprint,
        paragraph_content_hash,
    )
    from app.services.analysis_integrity_guard import scan_journey_profile_grounding

    scene = session.get(Scene, profile.scene_id)
    if scene is not None:
        ordered = []
        for pid, paragraph in sorted(
            (
                (pid, p)
                for pid, p in paragraphs_by_id.items()
                if p.chapter_id == scene.chapter_id
            ),
            key=lambda item: item[1].paragraph_index,
        ):
            # Keep only paragraphs inside scene span when available.
            start = paragraphs_by_id.get(scene.start_paragraph_id)
            end = paragraphs_by_id.get(scene.end_paragraph_id)
            if start and end:
                lo = min(start.paragraph_index, end.paragraph_index)
                hi = max(start.paragraph_index, end.paragraph_index)
                if not (lo <= paragraph.paragraph_index <= hi):
                    continue
            ordered.append(paragraph)
        if ordered:
            payload["source_context_fingerprint"] = compute_source_context_fingerprint(
                book_id=journey_run.book_id,
                chapter_id=journey_run.chapter_id,
                analysis_run_id=journey_run.analysis_run_id,
                scene_id=profile.scene_id,
                ordered_paragraph_ids=[p.id for p in ordered],
                paragraph_content_hashes=[paragraph_content_hash(p.raw_text) for p in ordered],
                prompt_version=journey_run.scene_prompt_version,
                contract_version=journey_run.scene_contract_version,
                formula_version=journey_run.formula_version,
            )
    validation_status = "valid"
    artifact = AnalysisArtifact(
        run_id=journey_run.analysis_run_id,
        artifact_type="reader_journey_scene_profile",
        subject_type="scene",
        subject_id=str(profile.scene_id),
        schema_version=CONTRACT_VERSION,
        prompt_version=SCENE_PROMPT_VERSION,
        payload_json=json.dumps(payload, ensure_ascii=False),
        confidence=profile.confidence,
        validation_status=validation_status,
    )
    session.add(artifact)
    session.flush()
    for path, paragraph_id in _collect_evidence_rows(profile):
        paragraph = paragraphs_by_id[paragraph_id]
        session.add(
            AnalysisEvidence(
                artifact_id=artifact.id,
                field_path=path,
                paragraph_id=paragraph_id,
                paragraph_hash=hashlib.sha256(paragraph.raw_text.encode()).hexdigest(),
            )
        )
    row = SceneReaderJourneyProfile(
        reader_journey_run_id=journey_run.id,
        scene_id=profile.scene_id,
        scene_ordinal=profile.scene_ordinal,
        scene_value_summary=profile.scene_value_summary,
        dominant_emotion=profile.dominant_emotion,
        emotional_valence_start=profile.emotional_valence_start,
        emotional_valence_end=profile.emotional_valence_end,
        arousal_start=profile.arousal_start,
        arousal_end=profile.arousal_end,
        curiosity_score=profile.curiosity_score,
        tension_score=profile.tension_score,
        payoff_score=profile.payoff_score,
        hook_score=profile.hook_score,
        information_gain_score=profile.information_gain_score,
        emotional_resonance_score=profile.emotional_resonance_score,
        cognitive_load_score=profile.cognitive_load_score,
        dropoff_risk_score=profile.dropoff_risk_score,
        engagement_score=engagement.engagement_score,
        confidence=profile.confidence,
        payload_json=json.dumps(payload, ensure_ascii=False),
        validation_status=validation_status,
        artifact_id=artifact.id,
    )
    session.add(row)
    session.flush()
    # Read-time style grounding without mutating provider raw responses.
    try:
        report = scan_journey_profile_grounding(
            session,
            profile=row,
            book_id=journey_run.book_id,
            chapter_id=journey_run.chapter_id,
            analysis_run_id=journey_run.analysis_run_id,
            prompt_version=journey_run.scene_prompt_version,
            contract_version=journey_run.scene_contract_version,
            formula_version=journey_run.formula_version,
        )
        if report.integrity_status in {"data_integrity_failed", "invalid_context"}:
            row.validation_status = report.integrity_status
            artifact.validation_status = report.integrity_status
            session.flush()
    except Exception:
        pass
    return row


def _boundary_stats(scenes: list[Scene]) -> dict[str, int]:
    manual = sum(1 for s in scenes if s.boundary_source == "user_added")
    model_accepted = sum(1 for s in scenes if s.boundary_source == "model_accepted")
    conflict = sum(1 for s in scenes if s.boundary_source == "user_accepted_model_conflict")
    return {
        "manual_added_boundary_count": manual,
        "model_accepted_boundary_count": model_accepted,
        "user_accepted_conflict_count": conflict,
    }


def _classify_journey_error(exc: Exception) -> tuple[str, str, bool, str]:
    if isinstance(exc, JourneySingleProfileTruncatedError):
        return (
            "JOURNEY_SINGLE_PROFILE_OUTPUT_TRUNCATED",
            "reader_journey_scene_profiles",
            False,
            "单Scene输出仍截断；除非契约/规划器升级否则不可盲目重试",
        )
    if isinstance(exc, StructuralValidationError):
        code = exc.error_code or "STRUCTURAL_VALIDATION_FAILED"
        retryable = not bool(exc.no_model_repair)
        if code.startswith("JOURNEY_"):
            return (
                code,
                "reader_journey_business_validation",
                retryable,
                "查看业务校验详情；可定向 repair 或离线重放",
            )
        return (
            code,
            "structural_validation",
            retryable,
            "结构校验失败；检查覆盖与引用",
        )
    if isinstance(exc, StructuredOutputError) and exc.error_code.startswith("JOURNEY_"):
        retryable = bool(exc.retryable)
        hint = "可尝试离线重放或恢复" if retryable else "契约冲突不可模型修复；请离线重放或升级契约"
        return (
            exc.error_code,
            "reader_journey_scene_profiles",
            retryable,
            hint,
        )
    root_code, stage, retryable, hint = classify_pipeline_error(exc)
    if root_code == "OUTPUT_TRUNCATED":
        return (
            "OUTPUT_TRUNCATED",
            "reader_journey_scene_profiles",
            True,
            "可在升级批次规划后恢复；勿原样重试同一超大批次",
        )
    return root_code, stage, retryable, hint


async def execute_reader_journey(
    session_factory: sessionmaker[Session],
    gateway: ModelGateway,
    journey_run_id: int,
) -> None:
    """Dispatch to V2 or legacy pipeline based on the run's persisted contract.

    Outer worker boundary (CHG-20260727-019): task-level exceptions are persisted
    in a short transaction and must not terminate the Sidecar process.
    """
    from app.services.reader_journey_recovery import persist_journey_worker_failure
    from app.services.reader_journey_version import is_v2_journey_run
    from app.services.reader_journey_v2_execution import execute_reader_journey_v2
    from app.services.task_cancellation import (
        AnalysisCancellationRequested,
        try_finalize_if_cancel_requested,
    )

    try:
        with session_factory() as session:
            journey_run = session.get(ReaderJourneyRun, journey_run_id)
            if journey_run is None:
                return
            if journey_run.status in {"succeeded", "cancelled"}:
                return
            if try_finalize_if_cancel_requested(session, journey_run.analysis_run_id):
                return
            if is_v2_journey_run(journey_run):
                await execute_reader_journey_v2(session_factory, gateway, journey_run_id)
                return

        await _execute_reader_journey_legacy(session_factory, gateway, journey_run_id)
    except AnalysisCancellationRequested as exc:
        with session_factory() as session:
            try_finalize_if_cancel_requested(session, exc.run_id)
    except Exception as exc:  # noqa: BLE001 — worker isolation; keep Sidecar alive
        persist_journey_worker_failure(session_factory, journey_run_id, exc)
        logger.exception(
            "reader_journey_worker_boundary journey_run_id=%s", journey_run_id
        )


async def _execute_reader_journey_legacy(
    session_factory: sessionmaker[Session],
    gateway: ModelGateway,
    journey_run_id: int,
) -> None:
    from app.services.credentials.service import get_credential_store
    from app.services.provider_runtime_service import ProviderRuntimeService

    with session_factory() as session:
        journey_run = session.get(ReaderJourneyRun, journey_run_id)
        if journey_run is None:
            return
        if journey_run.status in {"succeeded", "cancelled"}:
            return
        analysis_run = session.get(AnalysisRun, journey_run.analysis_run_id)
        if analysis_run is None:
            return
        _chapter = session.get(Chapter, journey_run.chapter_id)
        _revision, scenes = _scenes_for_journey_run(session, journey_run, analysis_run)
        require_completed_scene_analysis(session, analysis_run, scenes)
        try:
            store = get_credential_store()
        except Exception:
            store = None
        resolved = ProviderRuntimeService.resolve_for_run(
            gateway,
            session,
            analysis_run,
            store,
            task_type="reader_journey_scene",
        )
        if not resolved.eligibility.get("eligible"):
            journey_run.status = "failed"
            journey_run.root_error_code = "PROVIDER_DISABLED"
            journey_run.root_error_message = "Provider资格检查失败"
            journey_run.retryable = False
            journey_run.completed_at = datetime.now(timezone.utc)
            session.commit()
            return

    current_batch: ReaderJourneySceneBatch | None = None
    score_assessment: dict[str, object] = {}
    try:
        with session_factory() as session:
            journey_run = session.get(ReaderJourneyRun, journey_run_id)
            analysis_run = session.get(AnalysisRun, journey_run.analysis_run_id)
            chapter = session.get(Chapter, journey_run.chapter_id)
            _revision, scenes = _scenes_for_journey_run(session, journey_run, analysis_run)
            paragraphs = list(
                session.scalars(
                    select(Paragraph)
                    .where(Paragraph.chapter_id == journey_run.chapter_id)
                    .order_by(Paragraph.paragraph_index)
                )
            )
            by_id = {item.id: item for item in paragraphs}
            position = {item.id: index for index, item in enumerate(paragraphs)}
            progress = sync_journey_run_counts(session, journey_run)

            previous_prompt = journey_run.scene_prompt_version
            previous_contract = journey_run.scene_contract_version
            previous_planner = getattr(journey_run, "planner_version", None) or "1.0"
            journey_run.scene_prompt_version = SCENE_PROMPT_VERSION
            journey_run.scene_contract_version = SCENE_CONTRACT_VERSION
            journey_run.chapter_contract_version = CHAPTER_CONTRACT_VERSION
            journey_run.planner_version = PLANNER_VERSION
            if (
                previous_prompt != SCENE_PROMPT_VERSION
                or previous_contract != SCENE_CONTRACT_VERSION
                or previous_planner != PLANNER_VERSION
            ):
                details: dict = {}
                try:
                    details = json.loads(journey_run.failure_details_json or "{}")
                except json.JSONDecodeError:
                    details = {}
                details["resume_audit"] = {
                    "resumed_with_prompt_version": SCENE_PROMPT_VERSION,
                    "resumed_with_contract_version": SCENE_CONTRACT_VERSION,
                    "resumed_with_planner_version": PLANNER_VERSION,
                    "previous_prompt_version": previous_prompt,
                    "previous_contract_version": previous_contract,
                    "previous_planner_version": previous_planner,
                    "original_scene_contract_version": previous_contract,
                    "resumed_scene_contract_version": SCENE_CONTRACT_VERSION,
                    "prompt_version": SCENE_PROMPT_VERSION,
                    "planner_version": PLANNER_VERSION,
                    "resume_reason": (
                        "contract_semantics_upgrade"
                        if previous_contract != SCENE_CONTRACT_VERSION
                        else "planner_or_prompt_upgrade"
                    ),
                }
                journey_run.failure_details_json = json.dumps(details, ensure_ascii=False)

            journey_run.status = "scene_profiles_running"
            journey_run.current_stage = STAGE_READER_JOURNEY_SCENE
            journey_run.started_at = journey_run.started_at or datetime.now(timezone.utc)
            journey_run.root_error_code = None
            journey_run.root_error_message = None
            journey_run.failed_stage = None
            journey_run.failed_scene_id = None
            journey_run.failed_scene_ordinal = None
            journey_run.failed_invocation_id = None
            journey_run.retryable = False
            journey_run.completed_at = None
            session.commit()

            scene_prompt = load_prompt("reader_journey_scene", SCENE_PROMPT_VERSION)
            completed_ids = set(progress.completed_scene_ids)
            batches = plan_scene_batches(
                scenes,
                completed_scene_ids=completed_ids,
                paragraphs=paragraphs,
            )
            prior_summaries = [
                row.scene_value_summary
                for row in session.scalars(
                    select(SceneReaderJourneyProfile)
                    .where(SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id)
                    .order_by(SceneReaderJourneyProfile.scene_ordinal)
                )
            ]
            prior_high_strength_outs: list[str] = []
            for row in session.scalars(
                select(SceneReaderJourneyProfile)
                .where(SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id)
                .order_by(SceneReaderJourneyProfile.scene_ordinal)
            ):
                payload = json.loads(row.payload_json or "{}")
                for item in payload.get("reader_question_out") or []:
                    if isinstance(item, dict) and int(item.get("strength") or 0) >= 50:
                        question = (item.get("question") or "").strip()
                        if question:
                            prior_high_strength_outs.append(question)
            pricing_path = Path("config/cloud_pricing.json")
            pricing = pricing_status(pricing_path)
            remaining = _budget_remaining(session, pricing_path, analysis_run)
            stage1 = estimate_reader_journey_scene_profiles(
                scenes,
                paragraphs,
                remaining_scene_ids=set(progress.remaining_scene_ids),
                pricing_path=pricing_path,
            )
            reserve_budget(
                session,
                run_id=analysis_run.id,
                stage=STAGE_READER_JOURNEY_SCENE,
                required_requests=stage1.expected_request_count,
                required_tokens=stage1.estimated_total_tokens,
                required_cost=stage1.estimated_cost,
                remaining_requests=remaining.requests,
                remaining_tokens=remaining.tokens,
                remaining_cost=remaining.estimated_cost,
                expected_requests=stage1.expected_request_count,
                worst_case_requests=stage1.worst_case_request_count,
                pricing_version=pricing.get("pricing_version"),
            )
            session.commit()

            work: deque[ReaderJourneySceneBatch] = deque(batches)
            while work:
                batch = work.popleft()
                current_batch = batch
                batch_scenes = batch.scenes
                scene_payloads = []
                for scene in batch_scenes:
                    if is_scene_profile_complete(session, journey_run.id, scene.id):
                        continue
                    included = paragraphs[
                        position[scene.start_paragraph_id] : position[scene.end_paragraph_id] + 1
                    ]
                    analysis = scene_analysis_artifact(session, analysis_run.id, scene.id)
                    scene_payloads.append(
                        {
                            "scene_id": scene.id,
                            "scene_ordinal": scene.ordinal,
                            "scene_key": scene.scene_key,
                            "boundary_source": scene.boundary_source,
                            "paragraphs": [
                                {"id": item.id, "text": item.normalized_text}
                                for item in included
                            ],
                            "scene_analysis": json.loads(analysis.payload_json)
                            if analysis
                            else {},
                        }
                    )
                if not scene_payloads:
                    continue
                prev_scene = None
                next_scene = None
                first_ord = batch_scenes[0].ordinal
                last_ord = batch_scenes[-1].ordinal
                for scene in scenes:
                    if scene.ordinal == first_ord - 1:
                        prev_scene = scene
                    if scene.ordinal == last_ord + 1:
                        next_scene = scene
                prev_summary = ""
                if prev_scene:
                    prev_profile = session.scalar(
                        select(SceneReaderJourneyProfile).where(
                            SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id,
                            SceneReaderJourneyProfile.scene_id == prev_scene.id,
                        )
                    )
                    prev_summary = prev_profile.scene_value_summary if prev_profile else ""
                next_context = ""
                if next_scene:
                    next_context = f"Scene {next_scene.ordinal}: {next_scene.scene_key}"
                invocation_kind = (
                    "split_batch_request"
                    if batch.split_from_truncation
                    else "normal_batch_request"
                )
                snapshot = {
                    "book_id": journey_run.book_id,
                    "chapter_id": journey_run.chapter_id,
                    "analysis_run_id": analysis_run.id,
                    "scene_ids": list(batch.scene_ids),
                    "prompt_version": journey_run.scene_prompt_version,
                    "contract_version": journey_run.scene_contract_version,
                    "formula_version": journey_run.formula_version,
                    "analysis_mode": "reader_journey_scene",
                    "profiles_target": scene_payloads,
                    "owned_scene_ids_json": json.dumps(batch.scene_ids),
                    "owned_scene_ordinals_json": json.dumps(batch.scene_ordinals),
                    "estimated_output_tokens": batch.estimated_output_tokens,
                    "planner_version": batch.planner_version,
                    "batch_index": batch.batch_index,
                    "batch_count": batch.batch_count,
                    "audit_type": batch.audit_type,
                    "invocation_request_type": invocation_kind,
                    "paragraph_ids": [
                        pid
                        for scene in batch_scenes
                        for pid in _paragraph_ids_for_scene(scene, paragraphs, position)
                    ],
                }
                paragraph_ids_by_scene = {
                    scene.id: _paragraph_ids_for_scene(scene, paragraphs, position)
                    for scene in batch_scenes
                }
                user_content = scene_prompt.user_template.format(
                    genre=journey_run.genre,
                    chapter_title=chapter.display_title or chapter.title,
                    input_json=json.dumps(
                        {"profiles_target": scene_payloads}, ensure_ascii=False
                    ),
                    previous_scene_summary=prev_summary,
                    next_scene_context=next_context,
                    character_names="",
                )
                try:
                    result = await generate_validated(
                        session=session,
                        gateway=gateway,
                        run_id=analysis_run.id,
                        provider_name=journey_run.provider_name,
                        task_type="reader_journey_scene",
                        prompt=scene_prompt,
                        schema=SceneReaderJourneyBatchResult,
                        input_snapshot=snapshot,
                        user_content=user_content,
                        business_validator=lambda value: validate_scene_batch_result(
                            value,
                            expected_scene_ids={item["scene_id"] for item in scene_payloads},
                            paragraph_ids_by_scene=paragraph_ids_by_scene,
                            prior_summaries=prior_summaries,
                            prior_high_strength_outs=prior_high_strength_outs,
                        ),
                        initial_invocation_kind=invocation_kind,
                        allow_truncation_retry=False,
                    )
                except StructuredOutputError as exc:
                    if exc.error_code == "OUTPUT_TRUNCATED" and len(batch_scenes) > 1:
                        left, right = split_batch_after_truncation(batch)
                        logger.info(
                            "reader_journey_batch_split journey_run_id=%s scenes=%s left=%s right=%s",
                            journey_run.id,
                            batch.scene_ids,
                            left.scene_ids,
                            right.scene_ids,
                        )
                        work.appendleft(right)
                        work.appendleft(left)
                        continue
                    if exc.error_code == "OUTPUT_TRUNCATED" and len(batch_scenes) == 1:
                        raise JourneySingleProfileTruncatedError(
                            "单个Scene的读者旅程Profile输出仍超过上限，无法继续拆批",
                            failed_invocation_id=exc.failed_invocation_id,
                        ) from exc
                    raise
                # Deterministic semantic calibration before persist (zero extra HTTP).
                prior_items: list[SceneReaderJourneyProfileItem] = []
                if prior_summaries:
                    # Rebuild prior profiles from already persisted rows for q_in carry.
                    prior_rows = list(
                        session.scalars(
                            select(SceneReaderJourneyProfile)
                            .where(
                                SceneReaderJourneyProfile.reader_journey_run_id
                                == journey_run.id
                            )
                            .order_by(SceneReaderJourneyProfile.scene_ordinal)
                        )
                    )
                    prior_items = [
                        SceneReaderJourneyProfileItem.model_validate_json(row.payload_json)
                        for row in prior_rows
                    ]
                batch_items = sorted(result.profiles, key=lambda item: item.scene_ordinal)
                merged = prior_items + batch_items
                calibrated_merged = apply_deterministic_qin(merged)
                by_id_cal = {item.scene_id: item for item in calibrated_merged}
                calibrated_batch = [by_id_cal[item.scene_id] for item in batch_items]
                structured_batch: list[SceneReaderJourneyProfileItem] = []
                for index, profile in enumerate(calibrated_batch):
                    nxt = (
                        calibrated_batch[index + 1]
                        if index + 1 < len(calibrated_batch)
                        else None
                    )
                    structured_batch.append(
                        enrich_hook_structure(profile, next_profile=nxt)
                    )
                for profile in structured_batch:
                    persisted = _persist_profile(
                        session,
                        journey_run,
                        profile,
                        paragraphs_by_id=by_id,
                        genre=journey_run.genre,
                    )
                    if persisted is not None:
                        prior_summaries.append(profile.scene_value_summary.strip())
                        prior_high_strength_outs.extend(
                            item.question
                            for item in profile.reader_question_out
                            if item.strength >= 50
                        )
                session.commit()
                sync_journey_run_counts(session, journey_run)
                session.commit()

            release_run_reservation(session, analysis_run.id, stage=STAGE_READER_JOURNEY_SCENE)
            progress = sync_journey_run_counts(session, journey_run)
            if progress.remaining_scene_count > 0:
                journey_run.status = "scene_profiles_partial"
                journey_run.retryable = True
                session.commit()
                return

            all_profiles = list(
                session.scalars(
                    select(SceneReaderJourneyProfile)
                    .where(SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id)
                    .order_by(SceneReaderJourneyProfile.scene_ordinal)
                )
            )
            profile_items = [
                SceneReaderJourneyProfileItem.model_validate_json(item.payload_json)
                for item in all_profiles
            ]
            profile_items = inject_consecutive_no_payoff_risks(
                apply_deterministic_qin(profile_items)
            )
            by_ordinal_final = {item.scene_ordinal: item for item in profile_items}
            for row in all_profiles:
                item = by_ordinal_final[row.scene_ordinal]
                engagement = compute_engagement(item, genre=journey_run.genre)
                row.payload_json = item.model_dump_json()
                row.dropoff_risk_score = item.dropoff_risk_score
                row.engagement_score = engagement.engagement_score
                row.engagement_breakdown_json = engagement.model_dump_json()
            session.commit()
            score_assessment = validate_score_distribution(profile_items)
            if score_assessment.get("warnings"):
                details = {}
                try:
                    details = json.loads(journey_run.failure_details_json or "{}")
                except json.JSONDecodeError:
                    details = {}
                details["score_distribution_warnings"] = score_assessment.get("warnings")
                details["requires_review"] = bool(score_assessment.get("requires_review"))
                journey_run.failure_details_json = json.dumps(details, ensure_ascii=False)
                session.commit()

            journey_run.status = "chapter_synthesis_running"
            journey_run.current_stage = STAGE_READER_JOURNEY_CHAPTER
            session.commit()

            stage2 = estimate_reader_journey_chapter_synthesis(scenes, pricing_path=pricing_path)
            remaining = _budget_remaining(session, pricing_path, analysis_run)
            reserve_budget(
                session,
                run_id=analysis_run.id,
                stage=STAGE_READER_JOURNEY_CHAPTER,
                required_requests=stage2.expected_request_count,
                required_tokens=stage2.estimated_total_tokens,
                required_cost=stage2.estimated_cost,
                remaining_requests=remaining.requests,
                remaining_tokens=remaining.tokens,
                remaining_cost=remaining.estimated_cost,
                expected_requests=stage2.expected_request_count,
                worst_case_requests=stage2.worst_case_request_count,
                pricing_version=pricing.get("pricing_version"),
            )
            session.commit()

            chapter_prompt = load_prompt("reader_journey_chapter", CHAPTER_PROMPT_VERSION)
            synthesis_input = {
                "scene_profiles": [
                    {
                        "scene_ordinal": item.scene_ordinal,
                        "scene_value_summary": item.scene_value_summary,
                        "dominant_emotion": item.dominant_emotion,
                        "engagement_score": item.engagement_score,
                        "reader_questions_in": json.loads(item.payload_json).get(
                            "reader_question_in", []
                        ),
                        "reader_questions_out": json.loads(item.payload_json).get(
                            "reader_question_out", []
                        ),
                        "payoffs": json.loads(item.payload_json).get("payoffs", []),
                        "hooks": json.loads(item.payload_json).get("hooks", []),
                        "techniques": json.loads(item.payload_json).get("techniques", []),
                        "risk_points": json.loads(item.payload_json).get("risk_points", []),
                        "start_scene_ordinal": item.scene_ordinal,
                        "end_scene_ordinal": item.scene_ordinal,
                    }
                    for item in all_profiles
                ]
            }
            chapter_result = await generate_validated(
                session=session,
                gateway=gateway,
                run_id=analysis_run.id,
                provider_name=journey_run.provider_name,
                task_type="reader_journey_chapter",
                prompt=chapter_prompt,
                schema=ChapterReaderJourneySynthesisResult,
                input_snapshot=synthesis_input,
                user_content=chapter_prompt.user_template.format(
                    input_json=json.dumps(synthesis_input, ensure_ascii=False)
                ),
                business_validator=lambda value: validate_chapter_synthesis(
                    value,
                    total_scene_count=len(scenes),
                    enforce_anti_generic=False,
                ),
            )
            diagnosis_blob = "\n".join(
                [chapter_result.one_sentence_diagnosis]
                + list(chapter_result.pacing_diagnosis)
                + list(chapter_result.chapter_strengths)
                + list(chapter_result.chapter_risks)
            )
            if contains_banned_chapter_phrase(diagnosis_blob):
                nodes = build_journey_nodes(scenes, profile_items)
                rebuilt = build_deterministic_chapter_diagnosis(
                    profile_items,
                    journey_nodes=nodes,
                    question_chains=[],
                )
                chapter_result = chapter_result.model_copy(
                    update={
                        "one_sentence_diagnosis": rebuilt["one_sentence_diagnosis"],
                        "pacing_diagnosis": rebuilt["pacing_diagnosis"],
                        "chapter_strengths": rebuilt["chapter_strengths"],
                        "chapter_risks": rebuilt["chapter_risks"],
                        "chapter_reader_question_chain": rebuilt[
                            "chapter_reader_question_chain"
                        ],
                        "contract_version": CHAPTER_CONTRACT_VERSION,
                    }
                )
            validate_chapter_synthesis(
                chapter_result,
                total_scene_count=len(scenes),
                enforce_anti_generic=True,
            )
            for phase in chapter_result.phases:
                session.add(
                    ReaderJourneyPhase(
                        reader_journey_run_id=journey_run.id,
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
                        payload_json=phase.model_dump_json(),
                    )
                )
            stats = compute_deterministic_statistics(
                scenes,
                all_profiles,
                phase_count=len(chapter_result.phases),
                boundary_stats=_boundary_stats(scenes),
            )
            stats["journey_nodes"] = build_journey_nodes(scenes, profile_items)
            stats["semantic_calibration_version"] = SCENE_CONTRACT_VERSION
            if score_assessment:
                stats["score_distribution_warnings"] = score_assessment.get("warnings") or []
                stats["requires_review"] = bool(score_assessment.get("requires_review"))
            overall_engagement = round(
                sum(item.engagement_score for item in all_profiles) / max(len(all_profiles), 1)
            )
            session.add(
                ChapterReaderJourneySummary(
                    reader_journey_run_id=journey_run.id,
                    chapter_value_summary=chapter_result.one_sentence_diagnosis,
                    chapter_reader_question_chain_json=json.dumps(
                        chapter_result.chapter_reader_question_chain, ensure_ascii=False
                    ),
                    overall_engagement_score=overall_engagement,
                    strongest_hook_scene_ids_json=json.dumps(
                        stats.get("strong_hook_scene_ids", []), ensure_ascii=False
                    ),
                    strongest_payoff_scene_ids_json=json.dumps(
                        [p.scene_id for p in all_profiles if p.payoff_score >= 70],
                        ensure_ascii=False,
                    ),
                    risk_scene_ids_json=json.dumps(
                        stats.get("risk_scene_ids", []), ensure_ascii=False
                    ),
                    positive_feedback_distribution_json=json.dumps({}, ensure_ascii=False),
                    hook_distribution_json=json.dumps(
                        {
                            "strong": stats.get("strong_hook_scene_ids", []),
                            "medium": stats.get("medium_hook_scene_ids", []),
                            "weak": stats.get("weak_hook_scene_ids", []),
                        },
                        ensure_ascii=False,
                    ),
                    emotion_trend_summary="",
                    pacing_diagnosis_json=json.dumps(
                        chapter_result.pacing_diagnosis, ensure_ascii=False
                    ),
                    one_sentence_diagnosis=chapter_result.one_sentence_diagnosis,
                    deterministic_statistics_json=json.dumps(stats, ensure_ascii=False),
                    payload_json=chapter_result.model_dump_json(),
                    validation_status="valid",
                )
            )
            journey_run.status = "succeeded"
            journey_run.current_stage = None
            journey_run.completed_at = datetime.now(timezone.utc)
            journey_run.retryable = False
            sync_journey_run_counts(session, journey_run)
            analysis_run = session.get(AnalysisRun, journey_run.analysis_run_id)
            if analysis_run is not None:
                from app.services.chapter_analysis_completion import (
                    finalize_chapter_analysis,
                    is_chapter_analysis_complete,
                )

                if is_chapter_analysis_complete(session, analysis_run):
                    finalize_chapter_analysis(session, analysis_run)
            session.commit()
    except Exception as exc:
        with session_factory() as session:
            journey_run = session.get(ReaderJourneyRun, journey_run_id)
            analysis_run = session.get(AnalysisRun, journey_run.analysis_run_id)
            if analysis_run is not None:
                from app.services.chapter_analysis_completion import mark_journey_failed_on_run

                mark_journey_failed_on_run(session, analysis_run)
            root_code, stage, retryable, hint = _classify_journey_error(exc)
            progress = sync_journey_run_counts(session, journey_run)
            journey_run.failed_stage = journey_run.current_stage or STAGE_READER_JOURNEY_SCENE
            journey_run.root_error_code = root_code
            journey_run.root_error_message = str(exc)[:2000]
            journey_run.retryable = bool(retryable)
            journey_run.completed_at = datetime.now(timezone.utc)
            if current_batch and current_batch.scenes:
                journey_run.failed_scene_id = current_batch.scenes[0].id
                journey_run.failed_scene_ordinal = current_batch.scenes[0].ordinal
            if isinstance(exc, StructuredOutputError):
                journey_run.failed_invocation_id = exc.failed_invocation_id
            details = {
                "hint": hint,
                "stage": stage,
                "failed_batch_scene_ids": current_batch.scene_ids if current_batch else [],
                "failed_batch_scene_ordinals": (
                    current_batch.scene_ordinals if current_batch else []
                ),
                "planner_version": PLANNER_VERSION,
            }
            if isinstance(exc, StructuredOutputError):
                details.update(exc.as_safe_dict())
            journey_run.failure_details_json = json.dumps(details, ensure_ascii=False)
            if progress.completed_scene_count > 0 and progress.remaining_scene_count > 0:
                journey_run.status = "scene_profiles_partial"
            else:
                journey_run.status = "failed"
            session.commit()
            if analysis_run:
                release_run_reservation(session, analysis_run.id, stage=STAGE_READER_JOURNEY_SCENE)
                release_run_reservation(session, analysis_run.id, stage=STAGE_READER_JOURNEY_CHAPTER)
            logger.error(
                "reader_journey_failed journey_run_id=%s code=%s stage=%s scene=%s invocation=%s err=%s",
                journey_run_id,
                root_code,
                journey_run.failed_stage,
                journey_run.failed_scene_id,
                journey_run.failed_invocation_id,
                str(exc)[:500],
            )
        return
    finally:
        with session_factory() as session:
            journey_run = session.get(ReaderJourneyRun, journey_run_id)
            if journey_run is None:
                return
            analysis_run = session.get(AnalysisRun, journey_run.analysis_run_id)
            if analysis_run:
                release_run_reservation(session, analysis_run.id, stage=STAGE_READER_JOURNEY_SCENE)
                release_run_reservation(session, analysis_run.id, stage=STAGE_READER_JOURNEY_CHAPTER)


def build_preflight_payload(
    session: Session,
    analysis_run: AnalysisRun,
    *,
    gateway: ModelGateway,
    store,
    cloud_consent: bool,
    provider_name: str | None = None,
    remaining_scene_ids: set[int] | None = None,
    recovery_mode: bool = False,
    existing_journey_run_id: int | None = None,
) -> dict[str, object]:
    from app.services.provider_runtime_service import ProviderRuntimeService

    _revision, scenes = load_revision_scenes(session, analysis_run.id)
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == int(analysis_run.subject_id))
            .order_by(Paragraph.paragraph_index)
        )
    )
    require_completed_scene_analysis(session, analysis_run, scenes)
    resolved = ProviderRuntimeService.resolve_for_run(
        gateway,
        session,
        analysis_run,
        store,
        task_type="reader_journey_scene",
    )
    pricing_path = Path("config/cloud_pricing.json")
    pricing = pricing_status(pricing_path)
    remaining = _budget_remaining(session, pricing_path, analysis_run)
    pending_ids = remaining_scene_ids
    if pending_ids is None:
        pending_ids = {scene.id for scene in scenes}
    stage1 = estimate_reader_journey_scene_profiles(
        scenes,
        paragraphs,
        remaining_scene_ids=pending_ids,
        pricing_path=pricing_path,
    )
    from app.db.models import ReaderJourneyRun as _ReaderJourneyRun
    from app.services.reader_journey_version import (
        is_v2_journey_run,
        resolve_versions_for_new_run,
    )

    versions = resolve_versions_for_new_run()
    use_v2_preflight = True
    if existing_journey_run_id is not None:
        existing_jr = session.get(_ReaderJourneyRun, existing_journey_run_id)
        if existing_jr is not None:
            use_v2_preflight = is_v2_journey_run(existing_jr)
            if use_v2_preflight:
                versions = resolve_versions_for_new_run(pipeline_id="v2")
            else:
                versions = resolve_versions_for_new_run(pipeline_id="legacy_v1")

    if use_v2_preflight:
        # V2: model scene levels only; chapter diagnosis is program-owned (no stage2 model).
        stage2 = estimate_reader_journey_chapter_synthesis(scenes, pricing_path=pricing_path)
        stage2_requests = 0
        stage2_tokens = 0
        stage2_cost = 0.0
        stage2_worst_requests = 0
        stage2_worst_tokens = 0
        stage2_worst_cost = 0.0
    else:
        stage2 = estimate_reader_journey_chapter_synthesis(scenes, pricing_path=pricing_path)
        stage2_requests = stage2.expected_request_count
        stage2_tokens = stage2.estimated_total_tokens
        stage2_cost = stage2.estimated_cost
        stage2_worst_requests = stage2.worst_case_request_count
        stage2_worst_tokens = stage2.worst_case_total_tokens
        stage2_worst_cost = stage2.worst_case_cost

    pending_scenes = [scene for scene in scenes if scene.id in pending_ids]
    batches = plan_scene_batches(pending_scenes, paragraphs=paragraphs)
    # Hard gate: estimated remaining work (not worst-case).
    required = BudgetAmounts(
        stage1.expected_request_count + stage2_requests,
        stage1.estimated_total_tokens + stage2_tokens,
        round(stage1.estimated_cost + stage2_cost, 6),
    )
    dims = exceeded_dimensions(required, remaining)
    return {
        "analysis_run_id": analysis_run.id,
        "total_scenes": len(scenes),
        "remaining_scenes": len(pending_scenes),
        "scene_batch_count": len(batches),
        "expected_requests": stage1.expected_request_count + stage2_requests,
        "worst_case_requests": stage1.worst_case_request_count + stage2_worst_requests,
        "estimated_tokens": stage1.estimated_total_tokens + stage2_tokens,
        "worst_case_tokens": stage1.worst_case_total_tokens + stage2_worst_tokens,
        "estimated_cost": round(stage1.estimated_cost + stage2_cost, 6),
        "worst_case_cost": round(stage1.worst_case_cost + stage2_worst_cost, 6),
        "within_budget": not dims,
        "exceeded_dimensions": dims,
        "pricing_version": pricing.get("pricing_version"),
        "provider_state_version": resolved.provider_state_version,
        "provider_name": provider_name or analysis_run.provider,
        "eligible": bool(resolved.eligibility.get("eligible")),
        "blockers": list(resolved.eligibility.get("blockers") or []),
        "requires_cloud_consent": bool(analysis_run.sends_content_to_cloud),
        "currency": stage1.currency,
        "estimated": True,
        "stage1_scene_profiles": estimate_to_dict(stage1),
        "stage2_chapter_synthesis": estimate_to_dict(stage2)
        if not use_v2_preflight
        else {
            **estimate_to_dict(stage2),
            "expected_request_count": 0,
            "worst_case_request_count": 0,
            "estimated_total_tokens": 0,
            "worst_case_total_tokens": 0,
            "estimated_cost": 0.0,
            "worst_case_cost": 0.0,
            "note": "v2_native: chapter diagnosis is program-owned (no model)",
        },
        "planner_version": PLANNER_VERSION,
        "scene_prompt_version": versions.scene_prompt_version,
        "scene_contract_version": versions.contract_version,
        "pipeline_id": versions.pipeline_id,
        "source_mode": versions.source_mode,
        "batch_plan": format_batch_plan_report(batches),
        "recovery_mode": recovery_mode,
        "existing_journey_run_id": existing_journey_run_id,
    }
