"""Persist Reader Journey V2 finalize outputs into product tables (no model calls).

Single fact implementation shared by product pipeline and harness wrappers.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    ChapterReaderJourneySummary,
    ReaderJourneyPhase,
    ReaderJourneyRun,
    SceneReaderJourneyProfile,
)
from app.schemas.reader_journey import SceneReaderJourneyProfileItem
from app.schemas.reader_journey_v2 import (
    FORMULA_VERSION_V2,
    SCENE_CONTRACT_VERSION_V2,
    SceneReaderJourneyProfileItemV2,
)
from app.services.reader_journey_v2_mapping import mapped_or_zero
from app.services.reader_journey_version import (
    DIAGNOSES_ORIGIN_PROGRAM,
    DISPLAY_BANNER_V2,
    SCORES_ORIGIN_PROGRAM,
    SOURCE_MODE_V2_NATIVE,
)


def strip_model_mapped_scores(
    profile: SceneReaderJourneyProfileItemV2,
) -> SceneReaderJourneyProfileItemV2:
    """Model must not own mapped_score — clear before program mapping."""
    updates: dict[str, Any] = {}
    for key in (
        "goal_progress",
        "conflict_change",
        "state_change",
        "information_gain",
        "character_agency",
        "causal_coherence",
        "curiosity",
        "tension",
        "emotional_investment",
        "pacing_speed",
        "hook",
        "payoff",
        "setup_consistency",
        "question_lifecycle",
        "emotional_valence_start",
        "emotional_valence_end",
        "arousal_start",
        "arousal_end",
        "clarity",
        "cognitive_load",
        "redundancy",
    ):
        field = getattr(profile, key)
        if field.mapped_score is not None:
            updates[key] = field.model_copy(update={"mapped_score": None})
    if not updates:
        return profile
    return profile.model_copy(update=updates)


def v2_profile_to_v1_compat_payload(
    profile: SceneReaderJourneyProfileItemV2,
    *,
    paragraph_ids: list[str],
) -> dict[str, Any]:
    """Build a valid v1 SceneReaderJourneyProfileItem dict for visualization builders."""
    first = paragraph_ids[0] if paragraph_ids else "P0001"
    curiosity = int(mapped_or_zero(profile.curiosity))
    tension = int(mapped_or_zero(profile.tension))
    payoff = int(mapped_or_zero(profile.payoff))
    hook = int(mapped_or_zero(profile.hook))
    info = int(mapped_or_zero(profile.information_gain))
    emotion = int(mapped_or_zero(profile.emotional_investment))
    cognitive = int(mapped_or_zero(profile.cognitive_load))
    dropoff = int(round(float(profile.dropoff_risk or 0)))
    valence_start = int(round((mapped_or_zero(profile.emotional_valence_start) - 50) * 2))
    valence_end = int(round((mapped_or_zero(profile.emotional_valence_end) - 50) * 2))
    valence_start = max(-100, min(100, valence_start))
    valence_end = max(-100, min(100, valence_end))
    arousal_start = int(mapped_or_zero(profile.arousal_start))
    arousal_end = int(mapped_or_zero(profile.arousal_end))
    q = (profile.hook.rationale or profile.scene_value_summary or "本章疑问")[:160]
    question = q if ("？" in q or "?" in q) else f"{q}？"
    return {
        "scene_id": profile.scene_id,
        "scene_ordinal": profile.scene_ordinal,
        "scene_value_summary": profile.scene_value_summary[:160],
        "reader_question_in": [],
        "reader_question_created": [
            {
                "question": question,
                "trigger_summary": "场景推进触发",
                "strength": hook,
                "evidence_paragraph_ids": [first],
            }
        ]
        if profile.node_type != "beat"
        else [],
        "reader_question_answered": [],
        "reader_question_out": [
            {
                "question": question,
                "origin": "created_here",
                "hook_type": "information",
                "strength": hook,
                "evidence_paragraph_ids": [first],
            }
        ]
        if profile.node_type != "beat" and hook >= 50
        else [],
        "dominant_emotion": "紧张" if tension >= 50 else "平静",
        "emotional_valence_start": valence_start,
        "emotional_valence_end": valence_end,
        "arousal_start": arousal_start,
        "arousal_end": arousal_end,
        "curiosity_score": curiosity,
        "tension_score": tension,
        "payoff_score": payoff,
        "hook_score": hook,
        "information_gain_score": info,
        "emotional_resonance_score": emotion,
        "cognitive_load_score": cognitive,
        "dropoff_risk_score": dropoff,
        "payoffs": [],
        "hooks": [
            {
                "type": "information",
                "summary": question[:120],
                "gap": question[:120],
                "continue_drive": "继续阅读",
                "strength": hook,
                "evidence_paragraph_ids": [first],
            }
        ]
        if hook >= 40
        else [],
        "techniques": [],
        "risk_points": [],
        "character_effects": [],
        "writing_takeaways": [],
        "evidence_paragraph_ids": list(profile.evidence_paragraph_ids)[:16] or [first],
        "confidence": float(profile.confidence),
    }


def build_v2_scene_score_patch(profile: SceneReaderJourneyProfileItemV2) -> dict[str, Any]:
    return {
        "reading_momentum": profile.reading_momentum,
        "plot_progress": profile.plot_progress,
        "reading_tension": profile.reading_tension,
        "pacing_speed": mapped_or_zero(profile.pacing_speed),
        "pacing_fit": profile.pacing_fit,
        "pacing_fit_status": profile.pacing_fit_status or (
            "unavailable" if profile.pacing_fit is None else "ok"
        ),
        "pacing_fit_reason_code": profile.pacing_fit_reason_code,
        "hook": mapped_or_zero(profile.hook),
        "payoff": mapped_or_zero(profile.payoff),
        "hook_payoff_fit": profile.hook_payoff_fit,
        "hook_payoff_fit_status": profile.hook_payoff_fit_status,
        "hook_payoff_fit_reason_code": profile.hook_payoff_fit_reason_code,
        "emotional_investment": mapped_or_zero(profile.emotional_investment),
        "clarity": mapped_or_zero(profile.clarity),
        "dropoff_risk": profile.dropoff_risk,
    }


def build_v2_node_override(profile: SceneReaderJourneyProfileItemV2) -> dict[str, Any]:
    return {
        "node_type": profile.node_type,
        "role": "beat" if profile.node_type == "beat" else "core",
        "scene_role": profile.scene_role,
        "include_in_main_curve": profile.include_in_main_curve is not False
        and profile.node_type != "beat",
        "include_in_chapter_mean": profile.include_in_chapter_mean is not False
        and profile.node_type != "beat",
    }


def build_v2_dimension_insights_patch(
    profile: SceneReaderJourneyProfileItemV2,
) -> dict[str, Any] | None:
    if profile.dimension_insights is None:
        return None
    payload = profile.dimension_insights.model_dump(exclude_none=True)
    return payload or None


def build_v2_deterministic_statistics(
    *,
    derived: list[SceneReaderJourneyProfileItemV2],
    finalize_stats: dict[str, Any],
) -> dict[str, Any]:
    v2_scene_scores = {
        str(profile.scene_ordinal): build_v2_scene_score_patch(profile) for profile in derived
    }
    v2_node_overrides = {
        str(profile.scene_ordinal): build_v2_node_override(profile) for profile in derived
    }
    v2_dimension_insights: dict[str, Any] = {}
    for profile in derived:
        patch = build_v2_dimension_insights_patch(profile)
        if patch:
            v2_dimension_insights[str(profile.scene_ordinal)] = patch
    result = {
        "source_mode": SOURCE_MODE_V2_NATIVE,
        "contract_version": SCENE_CONTRACT_VERSION_V2,
        "prompt_version": "2.0",
        "formula_version": FORMULA_VERSION_V2,
        "question_lifecycle": finalize_stats.get("question_lifecycle") or [],
        "scene_diagnoses": finalize_stats.get("scene_diagnoses") or [],
        "v2_scene_scores": v2_scene_scores,
        "v2_node_overrides": v2_node_overrides,
        "average_reading_momentum": finalize_stats.get("average_reading_momentum"),
        "legacy_consecutive_no_payoff_floor_applied": False,
        "scores_origin": SCORES_ORIGIN_PROGRAM,
        "diagnoses_origin": DIAGNOSES_ORIGIN_PROGRAM,
        "prewritten_scores": False,
        "prewritten_diagnoses": False,
        "config_provenance": finalize_stats.get("config_provenance") or {},
    }
    if v2_dimension_insights:
        result["v2_dimension_insights"] = v2_dimension_insights
    return result


def ensure_basic_phases(
    session: Session,
    journey_run: ReaderJourneyRun,
    derived: list[SceneReaderJourneyProfileItemV2],
) -> None:
    """Create ordinal-third phases when none exist (generic titles only)."""
    from sqlalchemy import func, select

    existing = session.scalar(
        select(func.count())
        .select_from(ReaderJourneyPhase)
        .where(ReaderJourneyPhase.reader_journey_run_id == journey_run.id)
    )
    if int(existing or 0) > 0:
        return
    n = len(derived)
    if n <= 0:
        return
    cuts = [1, max(1, n // 3), max(1, (2 * n) // 3), n]
    specs = [
        (1, "开端", cuts[0], cuts[1]),
        (2, "发展", cuts[1] + 1 if cuts[1] < n else n, cuts[2]),
        (3, "收束", cuts[2] + 1 if cuts[2] < n else n, cuts[3]),
    ]
    for ordinal, title, start, end in specs:
        if start > end:
            continue
        session.add(
            ReaderJourneyPhase(
                reader_journey_run_id=journey_run.id,
                ordinal=ordinal,
                title=title,
                start_scene_ordinal=start,
                end_scene_ordinal=end,
                primary_reader_question="",
                dominant_emotion="",
                reading_payoff="",
                continuation_motivation="",
                summary=title,
                confidence=0.8,
                payload_json="{}",
            )
        )


def persist_finalized_v2_profiles(
    session: Session,
    *,
    journey_run: ReaderJourneyRun,
    derived: list[SceneReaderJourneyProfileItemV2],
    finalize_stats: dict[str, Any],
    paragraph_ids_by_scene: dict[int, list[str]],
) -> dict[str, Any]:
    """Write Scene profiles + chapter summary + provenance for a finished V2 run."""
    from sqlalchemy import delete

    session.execute(
        delete(SceneReaderJourneyProfile).where(
            SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id
        )
    )
    session.execute(
        delete(ChapterReaderJourneySummary).where(
            ChapterReaderJourneySummary.reader_journey_run_id == journey_run.id
        )
    )
    for profile in derived:
        pids = paragraph_ids_by_scene.get(int(profile.scene_id)) or list(
            profile.evidence_paragraph_ids
        )
        if not pids:
            pids = ["P0001"]
        v1_dict = v2_profile_to_v1_compat_payload(profile, paragraph_ids=pids)
        v1_item = SceneReaderJourneyProfileItem.model_validate(v1_dict)
        artifact = AnalysisArtifact(
            run_id=journey_run.analysis_run_id,
            artifact_type="reader_journey_scene_profile_v2",
            subject_type="scene",
            subject_id=str(profile.scene_id),
            schema_version=SCENE_CONTRACT_VERSION_V2,
            prompt_version="2.0",
            payload_json=json.dumps(profile.model_dump(), ensure_ascii=False),
            confidence=profile.confidence,
            validation_status="valid",
        )
        session.add(artifact)
        session.flush()
        for pid in list(profile.evidence_paragraph_ids)[:16]:
            session.add(
                AnalysisEvidence(
                    artifact_id=artifact.id,
                    field_path="evidence_paragraph_ids",
                    paragraph_id=pid,
                    paragraph_hash=pid,
                )
            )
        momentum = float(profile.reading_momentum or 0)
        session.add(
            SceneReaderJourneyProfile(
                reader_journey_run_id=journey_run.id,
                scene_id=profile.scene_id,
                scene_ordinal=profile.scene_ordinal,
                scene_value_summary=v1_item.scene_value_summary,
                dominant_emotion=v1_item.dominant_emotion,
                emotional_valence_start=v1_item.emotional_valence_start,
                emotional_valence_end=v1_item.emotional_valence_end,
                arousal_start=v1_item.arousal_start,
                arousal_end=v1_item.arousal_end,
                curiosity_score=v1_item.curiosity_score,
                tension_score=v1_item.tension_score,
                payoff_score=v1_item.payoff_score,
                hook_score=v1_item.hook_score,
                information_gain_score=v1_item.information_gain_score,
                emotional_resonance_score=v1_item.emotional_resonance_score,
                cognitive_load_score=v1_item.cognitive_load_score,
                dropoff_risk_score=v1_item.dropoff_risk_score,
                engagement_score=int(round(momentum)),
                confidence=profile.confidence,
                payload_json=json.dumps(v1_item.model_dump(), ensure_ascii=False),
                validation_status="valid",
                artifact_id=artifact.id,
            )
        )

    deterministic = build_v2_deterministic_statistics(
        derived=derived, finalize_stats=finalize_stats
    )
    avg = float(finalize_stats.get("average_reading_momentum") or 0)
    session.add(
        ChapterReaderJourneySummary(
            reader_journey_run_id=journey_run.id,
            chapter_value_summary="V2 程序派生动量与诊断（非预写分数）。",
            chapter_reader_question_chain_json=json.dumps(
                deterministic.get("question_lifecycle") or [], ensure_ascii=False
            ),
            overall_engagement_score=int(round(avg)),
            strongest_hook_scene_ids_json="[]",
            strongest_payoff_scene_ids_json="[]",
            risk_scene_ids_json="[]",
            positive_feedback_distribution_json="{}",
            hook_distribution_json="{}",
            emotion_trend_summary="",
            pacing_diagnosis_json=json.dumps([], ensure_ascii=False),
            one_sentence_diagnosis="V2 原生：程序 finalize/diagnosis，无预写分数或诊断。",
            deterministic_statistics_json=json.dumps(deterministic, ensure_ascii=False),
            payload_json=json.dumps(
                {
                    "source_mode": SOURCE_MODE_V2_NATIVE,
                    "display_banner": DISPLAY_BANNER_V2,
                    "scores_origin": SCORES_ORIGIN_PROGRAM,
                    "diagnoses_origin": DIAGNOSES_ORIGIN_PROGRAM,
                },
                ensure_ascii=False,
            ),
            validation_status="valid",
        )
    )
    ensure_basic_phases(session, journey_run, derived)
    return deterministic
