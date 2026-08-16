"""Official Reader Journey V2 execution path (product + harness share this).

Model emits levels only. Program maps → derive → diagnosis → lifecycle → persist.
Does not depend on fixture paths, book titles, or fixed run ids.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisArtifact,
    AnalysisRun,
    Chapter,
    Paragraph,
    ReaderJourneyRun,
    SceneReaderJourneyProfile,
)
from app.model_gateway.gateway import ModelGateway
from app.schemas.reader_journey_v2 import (
    SCENE_PROMPT_VERSION_V2,
    SceneReaderJourneyBatchResultV2,
    SceneReaderJourneyProfileItemV2,
)
from app.services.budget_reservation import release_run_reservation, reserve_budget
from app.services.cloud_pricing import pricing_status
from app.narrative_core.long_novel.chapter_focus import (
    apply_chapter_focus,
    chapter_foci_for_book,
    formula_weights_for_book,
    required_axis_keys as required_axis_keys_for,
    selected_axes,
    suppressed_diagnoses_for_book,
)
from app.services.prompt_service import load_prompt
from app.services.reader_journey_batch_planner import (
    plan_scene_batches,
    split_batch_after_truncation,
)
from app.services.reader_journey_batch_planner import ReaderJourneySceneBatch
from app.services.reader_journey_pipeline import (
    JourneySingleProfileTruncatedError,
    _budget_remaining,
    _classify_journey_error,
    _paragraph_ids_for_scene,
)
from app.services.reader_journey_progress import (
    is_scene_profile_complete,
    require_completed_scene_analysis,
    scene_analysis_artifact,
    sync_journey_run_counts,
)
from app.services.reader_journey_v2_finalize import finalize_v2_profiles
from app.services.reader_journey_v2_persist import (
    persist_finalized_v2_profiles,
    strip_model_mapped_scores,
)
from app.services.reader_journey_version import (
    merge_run_provenance,
    resolve_versions_for_new_run,
)
from app.services.staged_budget import (
    STAGE_READER_JOURNEY_SCENE,
    estimate_reader_journey_scene_profiles,
)
from app.services.structured_output import StructuredOutputError, generate_validated
from app.services.task_cancellation import (
    AnalysisCancellationRequested,
    raise_if_cancel_requested,
    try_finalize_if_cancel_requested,
)
from app.services.validation_errors import StructuralValidationError

logger = logging.getLogger(__name__)


def validate_scene_batch_result_v2(
    value: SceneReaderJourneyBatchResultV2,
    *,
    expected_scene_ids: set[int],
    paragraph_ids_by_scene: dict[int, set[str]],
    boundary_meta_by_scene: dict[int, object] | None = None,
    allowed_axis_keys: set[str] | None = None,
    required_axis_keys: set[str] | None = None,
) -> None:
    """Lightweight V2 business validation — no v1 engagement / q_in rules."""
    from app.services.scene_evidence_validation import (
        BoundaryMeta,
        SceneEvidenceValidationError,
        validate_evidence_mapping,
        v2_level_fields_from_profile,
    )

    got = {int(item.scene_id) for item in value.profiles}
    if got != expected_scene_ids:
        raise StructuralValidationError(
            f"expected scenes {sorted(expected_scene_ids)}, got {sorted(got)}",
            "JOURNEY_SCENE_ID_MISMATCH",
            no_model_repair=False,
        )
    for profile in value.profiles:
        allowed = paragraph_ids_by_scene.get(int(profile.scene_id)) or set()
        for pid in profile.evidence_paragraph_ids:
            if allowed and pid not in allowed:
                raise StructuralValidationError(
                    f"scene {profile.scene_id} evidence {pid} not in scene paragraphs",
                    "JOURNEY_EVIDENCE_OUT_OF_SCENE",
                    no_model_repair=False,
                )
        _validate_genre_axes(
            profile,
            allowed_axis_keys=allowed_axis_keys,
            required_axis_keys=required_axis_keys,
            allowed=allowed,
        )
        if not allowed:
            continue
        ordered = sorted(allowed)
        raw_boundary = (boundary_meta_by_scene or {}).get(int(profile.scene_id))
        boundary = raw_boundary if isinstance(raw_boundary, BoundaryMeta) else None
        if isinstance(raw_boundary, dict):
            boundary = BoundaryMeta(
                signals=list(raw_boundary.get("signals") or []),
                suspected_split_points=list(raw_boundary.get("suspected_split_points") or []),
                consolidation_confidence=raw_boundary.get("consolidation_confidence"),
                boundary_confidence=raw_boundary.get("boundary_confidence"),
                paragraph_count=len(ordered),
                multiple_structure_tasks=bool(raw_boundary.get("multiple_structure_tasks")),
            )
        try:
            validate_evidence_mapping(
                scene_id=str(profile.scene_id),
                scene_paragraph_ids=ordered,
                fields=v2_level_fields_from_profile(profile),
                boundary=boundary,
            )
        except SceneEvidenceValidationError:
            raise


#: Which scored field each craft flag must agree with, and the level it may not exceed
#: (or, for redundancy, may not fall below — redundancy is the one axis where low is good).
_FLAG_FIELD_BOUNDS: dict[str, tuple[str, str, int]] = {
    "setup_contradiction": ("setup_consistency", "max", 3),
    "unclear_reference": ("clarity", "max", 3),
    "causal_gap": ("causal_coherence", "max", 3),
    "redundant_passage": ("redundancy", "min", 3),
}


def _validate_genre_axes(
    profile: SceneReaderJourneyProfileItemV2,
    *,
    allowed_axis_keys: set[str] | None,
    required_axis_keys: set[str] | None,
    allowed: set[str],
) -> None:
    """Keep the profile-selected axes and the craft flags honest.

    Two things go wrong without this. The model invents axis keys — an unprompted run
    returned ``mystery_hook`` and ``clue_fairness``, names that exist nowhere in the
    profile vocabulary and so can never be compared across books. And it raises a flag
    while leaving the corresponding score at 5, which reads on screen as "no problems"
    directly above a named problem.
    """
    for axis in profile.genre_axes:
        # None means the caller has no opinion (legacy paths). An *empty set* is a real
        # answer — this book confirmed no profile, so no axis key is legal and anything
        # here was invented.
        if allowed_axis_keys is not None and axis.key not in allowed_axis_keys:
            raise StructuralValidationError(
                f"scene {profile.scene_id} genre axis {axis.key!r} is not one of "
                f"{sorted(allowed_axis_keys)}",
                "JOURNEY_GENRE_AXIS_UNKNOWN",
                no_model_repair=False,
            )
        for pid in axis.evidence_paragraph_ids:
            if allowed and pid not in allowed:
                raise StructuralValidationError(
                    f"scene {profile.scene_id} genre axis {axis.key} evidence {pid} "
                    "not in scene paragraphs",
                    "JOURNEY_EVIDENCE_OUT_OF_SCENE",
                    no_model_repair=False,
                )
    if required_axis_keys:
        missing = required_axis_keys - {axis.key for axis in profile.genre_axes}
        if missing:
            raise StructuralValidationError(
                f"scene {profile.scene_id} is missing genre axes {sorted(missing)}",
                "JOURNEY_GENRE_AXIS_MISSING",
                no_model_repair=False,
            )
    for flag in profile.craft_flags:
        bound = _FLAG_FIELD_BOUNDS.get(flag.kind)
        if bound is None:
            continue
        field_name, direction, limit = bound
        level = int(getattr(profile, field_name).level)
        if (direction == "max" and level > limit) or (direction == "min" and level < limit):
            raise StructuralValidationError(
                f"scene {profile.scene_id} raised {flag.kind} but {field_name}={level} "
                f"({direction} {limit})",
                "JOURNEY_CRAFT_FLAG_INCONSISTENT",
                no_model_repair=False,
            )
        for pid in flag.evidence_paragraph_ids:
            if allowed and pid not in allowed:
                raise StructuralValidationError(
                    f"scene {profile.scene_id} craft flag evidence {pid} "
                    "not in scene paragraphs",
                    "JOURNEY_EVIDENCE_OUT_OF_SCENE",
                    no_model_repair=False,
                )


def _load_v2_profiles_from_artifacts(
    session: Session, journey_run: ReaderJourneyRun
) -> list[SceneReaderJourneyProfileItemV2]:
    rows = list(
        session.scalars(
            select(AnalysisArtifact)
            .where(
                AnalysisArtifact.run_id == journey_run.analysis_run_id,
                AnalysisArtifact.artifact_type == "reader_journey_scene_profile_v2",
            )
            .order_by(AnalysisArtifact.id)
        )
    )
    # Prefer latest artifact per scene_id, scoped to this journey's scenes.
    # Without scoping, rematerialized revisions merge prior-journey scene ids.
    allowed_scene_ids = {
        int(row.scene_id)
        for row in session.scalars(
            select(SceneReaderJourneyProfile).where(
                SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id
            )
        )
    }
    if not allowed_scene_ids:
        try:
            allowed_scene_ids = {
                int(item) for item in json.loads(journey_run.included_scene_ids_json or "[]")
            }
        except (TypeError, ValueError, json.JSONDecodeError):
            allowed_scene_ids = set()
    by_scene: dict[int, AnalysisArtifact] = {}
    for row in rows:
        try:
            sid = int(row.subject_id)
        except (TypeError, ValueError):
            continue
        if allowed_scene_ids and sid not in allowed_scene_ids:
            continue
        by_scene[sid] = row
    profiles: list[SceneReaderJourneyProfileItemV2] = []
    for artifact in by_scene.values():
        payload = json.loads(artifact.payload_json or "{}")
        # Drop program-owned derived fields if present from a prior finalize rewrite.
        for key in (
            "plot_progress",
            "reading_tension",
            "pacing_fit",
            "hook_payoff_fit",
            "reading_momentum",
            "dropoff_risk",
            "pacing_fit_status",
            "pacing_fit_reason_code",
            "hook_payoff_fit_status",
            "hook_payoff_fit_reason_code",
        ):
            payload.pop(key, None)
        profile = SceneReaderJourneyProfileItemV2.model_validate(payload)
        profiles.append(strip_model_mapped_scores(profile))
    return sorted(profiles, key=lambda item: item.scene_ordinal)


def _mark_scene_complete_stub(
    session: Session,
    journey_run: ReaderJourneyRun,
    profile: SceneReaderJourneyProfileItemV2,
) -> None:
    """Persist V2 artifact so resume can skip completed scenes; full row rewrite at finalize."""
    if is_scene_profile_complete(session, journey_run.id, profile.scene_id):
        # Still refresh artifact for levels.
        pass
    artifact = AnalysisArtifact(
        run_id=journey_run.analysis_run_id,
        artifact_type="reader_journey_scene_profile_v2",
        subject_type="scene",
        subject_id=str(profile.scene_id),
        schema_version="2.0",
        prompt_version="2.0",
        payload_json=json.dumps(
            strip_model_mapped_scores(profile).model_dump(), ensure_ascii=False
        ),
        confidence=profile.confidence,
        validation_status="valid",
    )
    session.add(artifact)
    session.flush()
    # Minimal stub row so is_scene_profile_complete / counts work during resume.
    existing = session.scalar(
        select(SceneReaderJourneyProfile).where(
            SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id,
            SceneReaderJourneyProfile.scene_id == profile.scene_id,
        )
    )
    if existing is None:
        session.add(
            SceneReaderJourneyProfile(
                reader_journey_run_id=journey_run.id,
                scene_id=profile.scene_id,
                scene_ordinal=profile.scene_ordinal,
                scene_value_summary=(profile.scene_value_summary or "")[:160],
                dominant_emotion="",
                emotional_valence_start=0,
                emotional_valence_end=0,
                arousal_start=0,
                arousal_end=0,
                curiosity_score=0,
                tension_score=0,
                payoff_score=0,
                hook_score=0,
                information_gain_score=0,
                emotional_resonance_score=0,
                cognitive_load_score=0,
                dropoff_risk_score=0,
                engagement_score=0,
                confidence=profile.confidence,
                payload_json="{}",
                # Mark valid so resume skips re-invoking completed scenes; finalize rewrites rows.
                validation_status="valid",
                artifact_id=artifact.id,
            )
        )
    else:
        existing.artifact_id = artifact.id
        existing.scene_value_summary = (profile.scene_value_summary or "")[:160]
        existing.validation_status = "valid"


async def execute_reader_journey_v2(
    session_factory: sessionmaker[Session],
    gateway: ModelGateway,
    journey_run_id: int,
) -> None:
    """Default product V2 path. Reuses budget gates and batch planner."""
    from app.services.credentials.service import get_credential_store
    from app.services.provider_runtime_service import ProviderRuntimeService

    versions = resolve_versions_for_new_run()
    current_batch: ReaderJourneySceneBatch | None = None
    try:
        with session_factory() as session:
            journey_run = session.get(ReaderJourneyRun, journey_run_id)
            if journey_run is None:
                return
            if journey_run.status in {"succeeded", "cancelled"}:
                return
            analysis_run = session.get(AnalysisRun, journey_run.analysis_run_id)
            if analysis_run is None:
                return
            from app.services.scene_boundary_manual_review import load_journey_bound_scenes
            from app.services.reader_journey_progress import scene_analysis_artifact

            _revision, scenes = load_journey_bound_scenes(session, journey_run)
            # CHG-015: rematerialized scenes may still be analyzing.
            missing = [
                s.id
                for s in scenes
                if scene_analysis_artifact(session, analysis_run.id, s.id) is None
            ]
            if missing:
                journey_run.status = "starting"
                journey_run.current_stage = "starting"
                journey_run.root_error_code = "WAITING_SCENE_ANALYSIS"
                journey_run.root_error_message = "确认后的场景分析尚未完成"
                journey_run.failed_stage = "scene_analysis"
                journey_run.retryable = True
                journey_run.completed_at = None
                journey_run.updated_at = datetime.now(timezone.utc)
                session.commit()
                logger.info(
                    "reader_journey_v2_waiting_scene_analysis journey_run_id=%s missing=%s",
                    journey_run_id,
                    missing,
                )
                return

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

            require_completed_scene_analysis(session, analysis_run, scenes)
            chapter = session.get(Chapter, journey_run.chapter_id)
            paragraphs = list(
                session.scalars(
                    select(Paragraph)
                    .where(Paragraph.chapter_id == journey_run.chapter_id)
                    .order_by(Paragraph.paragraph_index)
                )
            )
            position = {item.id: index for index, item in enumerate(paragraphs)}
            progress = sync_journey_run_counts(session, journey_run)

            # Keep V2 versions; do not rewrite to legacy v1.6.
            for field, value in versions.as_run_fields().items():
                setattr(journey_run, field, value)
            journey_run.failure_details_json = merge_run_provenance(
                journey_run.failure_details_json, versions
            )
            journey_run.status = "scene_profiles_running"
            journey_run.current_stage = STAGE_READER_JOURNEY_SCENE
            journey_run.started_at = journey_run.started_at or datetime.now(timezone.utc)
            journey_run.root_error_code = None
            journey_run.root_error_message = None
            journey_run.failed_stage = None
            journey_run.retryable = False
            journey_run.completed_at = None
            session.commit()

            scene_prompt = apply_chapter_focus(
                load_prompt(
                    "reader_journey_scene", versions.scene_prompt_version or SCENE_PROMPT_VERSION_V2
                ),
                session,
                journey_run.book_id,
            )
            # The axis keys this book's confirmed profile actually asked for. Empty for an
            # unprofiled book, which the validator reads as "no genre axes are legal here" —
            # the model must then return the empty list the base prompt asks for.
            _book_axes = selected_axes(chapter_foci_for_book(session, journey_run.book_id))
            allowed_axis_keys = {axis.key for axis in _book_axes}
            # The gated axes are excluded from "required" — see required_axis_keys.
            required_axis_keys = required_axis_keys_for(_book_axes)
            completed_ids = set(progress.completed_scene_ids)
            batches = plan_scene_batches(
                scenes,
                completed_scene_ids=completed_ids,
                paragraphs=paragraphs,
            )
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

            prior_summaries: list[str] = []
            # The chapter's own ends, taken from the full scene list rather than the batch —
            # a batch boundary is a token-budget artefact and must not be read as a chapter
            # opening or ending.
            chapter_ordinals = [item.ordinal for item in scenes]
            first_scene_ordinal = min(chapter_ordinals) if chapter_ordinals else None
            last_scene_ordinal = max(chapter_ordinals) if chapter_ordinals else None
            work: deque[ReaderJourneySceneBatch] = deque(batches)
            while work:
                raise_if_cancel_requested(session, analysis_run.id)
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
                            # Batching means a scene arrives without knowing where it sits in
                            # the chapter, and two of the profile-selected axes (开篇抓力,
                            # 断章质量) are properties of the chapter's ends. Stating it beats
                            # letting the model infer it from an ordinal it cannot bound.
                            "is_chapter_opening": scene.ordinal == first_scene_ordinal,
                            "is_chapter_ending": scene.ordinal == last_scene_ordinal,
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
                    "profiles_target": scene_payloads,
                    "owned_scene_ids_json": json.dumps(batch.scene_ids),
                    "contract_version": "2.0",
                    "pipeline": "v2",
                }
                paragraph_ids_by_scene = {
                    scene.id: _paragraph_ids_for_scene(scene, paragraphs, position)
                    for scene in batch_scenes
                }
                user_content = scene_prompt.user_template.format(
                    genre=journey_run.genre,
                    chapter_title=(chapter.display_title or chapter.title) if chapter else "",
                    input_json=json.dumps(
                        {"profiles_target": scene_payloads}, ensure_ascii=False
                    ),
                    previous_scene_summary=prev_summary,
                    next_scene_context=next_context,
                )
                try:
                    result = await generate_validated(
                        session=session,
                        gateway=gateway,
                        run_id=analysis_run.id,
                        provider_name=journey_run.provider_name,
                        task_type="reader_journey_scene",
                        prompt=scene_prompt,
                        schema=SceneReaderJourneyBatchResultV2,
                        input_snapshot=snapshot,
                        user_content=user_content,
                        business_validator=lambda value: validate_scene_batch_result_v2(
                            value,
                            expected_scene_ids={item["scene_id"] for item in scene_payloads},
                            paragraph_ids_by_scene=paragraph_ids_by_scene,
                            allowed_axis_keys=allowed_axis_keys,
                            required_axis_keys=required_axis_keys,
                        ),
                        initial_invocation_kind=invocation_kind,
                        allow_truncation_retry=False,
                    )
                except StructuredOutputError as exc:
                    if exc.error_code == "OUTPUT_TRUNCATED" and len(batch_scenes) > 1:
                        left, right = split_batch_after_truncation(batch)
                        work.appendleft(right)
                        work.appendleft(left)
                        continue
                    if exc.error_code == "OUTPUT_TRUNCATED" and len(batch_scenes) == 1:
                        raise JourneySingleProfileTruncatedError(
                            "单个Scene的读者旅程Profile输出仍超过上限，无法继续拆批",
                            failed_invocation_id=exc.failed_invocation_id,
                        ) from exc
                    raise

                for profile in sorted(result.profiles, key=lambda item: item.scene_ordinal):
                    cleaned = strip_model_mapped_scores(profile)
                    _mark_scene_complete_stub(session, journey_run, cleaned)
                    prior_summaries.append((cleaned.scene_value_summary or "").strip())
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

            if try_finalize_if_cancel_requested(session, analysis_run.id):
                return
            raw_profiles = _load_v2_profiles_from_artifacts(session, journey_run)
            derived, stats = finalize_v2_profiles(
                raw_profiles,
                formula_weights=formula_weights_for_book(session, journey_run.book_id),
                suppressed_diagnoses=suppressed_diagnoses_for_book(
                    session, journey_run.book_id
                ),
            )
            paragraph_ids_by_scene = {
                int(scene.id): list(_paragraph_ids_for_scene(scene, paragraphs, position))
                for scene in scenes
            }
            persist_finalized_v2_profiles(
                session,
                journey_run=journey_run,
                derived=derived,
                finalize_stats=stats,
                paragraph_ids_by_scene=paragraph_ids_by_scene,
            )
            journey_run.failure_details_json = merge_run_provenance(
                journey_run.failure_details_json, versions
            )
            journey_run.status = "succeeded"
            journey_run.current_stage = "succeeded"
            journey_run.completed_at = datetime.now(timezone.utc)
            journey_run.completed_scene_count = len(derived)
            journey_run.remaining_scene_count = 0
            journey_run.remaining_scene_ids_json = "[]"
            journey_run.completed_scene_ids_json = json.dumps(
                [p.scene_id for p in derived], ensure_ascii=False
            )
            session.commit()
            logger.info(
                "reader_journey_v2_succeeded journey_run_id=%s scenes=%s beats=%s",
                journey_run.id,
                len(derived),
                stats.get("beat_count"),
            )
    except AnalysisCancellationRequested:
        raise
    except Exception as exc:  # noqa: BLE001
        # CHG-015: rematerialized scenes may still be analyzing — wait, do not fail
        # as journey-synthesis failure or map to interrupted in the UI.
        if "SCENE_ANALYSIS_INCOMPLETE" in str(exc):
            with session_factory() as session:
                journey_run = session.get(ReaderJourneyRun, journey_run_id)
                if journey_run is None:
                    return
                journey_run.status = "starting"
                journey_run.current_stage = "starting"
                journey_run.root_error_code = "WAITING_SCENE_ANALYSIS"
                journey_run.root_error_message = "确认后的场景分析尚未完成"
                journey_run.failed_stage = "scene_analysis"
                journey_run.retryable = True
                journey_run.completed_at = None
                journey_run.updated_at = datetime.now(timezone.utc)
                session.commit()
            logger.info(
                "reader_journey_v2_waiting_scene_analysis journey_run_id=%s",
                journey_run_id,
            )
            return
        root_code, stage, retryable, hint = _classify_journey_error(exc)
        with session_factory() as session:
            journey_run = session.get(ReaderJourneyRun, journey_run_id)
            if journey_run is None:
                return
            analysis_run = session.get(AnalysisRun, journey_run.analysis_run_id)
            if analysis_run is not None:
                from app.services.chapter_analysis_completion import mark_journey_failed_on_run

                mark_journey_failed_on_run(session, analysis_run)
                release_run_reservation(
                    session, analysis_run.id, stage=STAGE_READER_JOURNEY_SCENE
                )
            if (
                int(journey_run.completed_scene_count or 0) > 0
                and int(journey_run.remaining_scene_count or 0) > 0
            ):
                journey_run.status = "scene_profiles_partial"
            else:
                journey_run.status = "failed"
            journey_run.root_error_code = root_code
            journey_run.root_error_message = str(exc)[:500]
            journey_run.failed_stage = stage
            journey_run.retryable = retryable
            journey_run.completed_at = datetime.now(timezone.utc)
            journey_run.updated_at = datetime.now(timezone.utc)
            details: dict[str, Any] = {}
            try:
                details = json.loads(journey_run.failure_details_json or "{}")
            except json.JSONDecodeError:
                details = {}
            details["hint"] = hint
            if current_batch is not None:
                details["failed_batch_scene_ids"] = list(current_batch.scene_ids)
            journey_run.failure_details_json = json.dumps(details, ensure_ascii=False)
            session.commit()
        logger.exception("reader_journey_v2_failed journey_run_id=%s", journey_run_id)
