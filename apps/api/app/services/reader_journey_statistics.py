"""Deterministic chapter-level Reader Journey statistics."""

from __future__ import annotations

from app.db.models import Scene, SceneReaderJourneyProfile
from app.schemas.reader_journey import SceneReaderJourneyProfileItem
from app.services.reader_journey_question_lifecycle import (
    build_question_chains,
    diagnose_dropped_high_strength_questions,
)

def compute_deterministic_statistics(
    scenes: list[Scene],
    profiles: list[SceneReaderJourneyProfile],
    *,
    phase_count: int,
    boundary_stats: dict[str, int] | None = None,
) -> dict[str, object]:
    by_ordinal = {item.scene_ordinal: item for item in profiles}
    engagement_curve = [
        {"scene_ordinal": scene.ordinal, "engagement": by_ordinal[scene.ordinal].engagement_score}
        for scene in scenes
        if scene.ordinal in by_ordinal
    ]
    valence_curve = [
        {
            "scene_ordinal": scene.ordinal,
            "start": by_ordinal[scene.ordinal].emotional_valence_start,
            "end": by_ordinal[scene.ordinal].emotional_valence_end,
        }
        for scene in scenes
        if scene.ordinal in by_ordinal
    ]
    arousal_curve = [
        {
            "scene_ordinal": scene.ordinal,
            "start": by_ordinal[scene.ordinal].arousal_start,
            "end": by_ordinal[scene.ordinal].arousal_end,
        }
        for scene in scenes
        if scene.ordinal in by_ordinal
    ]
    paragraph_counts = []
    single_scene_ordinals = []
    for scene in scenes:
        start_idx = int(scene.start_paragraph_id.rsplit("-P", 1)[-1])
        end_idx = int(scene.end_paragraph_id.rsplit("-P", 1)[-1])
        count = end_idx - start_idx + 1
        paragraph_counts.append(count)
        if scene.start_paragraph_id == scene.end_paragraph_id:
            single_scene_ordinals.append(scene.ordinal)
    longest = max(scenes, key=lambda s: (
        int(s.end_paragraph_id.rsplit("-P", 1)[-1])
        - int(s.start_paragraph_id.rsplit("-P", 1)[-1])
        + 1
    ))
    longest_count = (
        int(longest.end_paragraph_id.rsplit("-P", 1)[-1])
        - int(longest.start_paragraph_id.rsplit("-P", 1)[-1])
        + 1
    )
    strong_hooks = [p.scene_id for p in profiles if p.hook_score >= 70]
    medium_hooks = [p.scene_id for p in profiles if 40 <= p.hook_score < 70]
    weak_hooks = [p.scene_id for p in profiles if p.hook_score < 40]
    risk_scenes = [p.scene_id for p in profiles if p.dropoff_risk_score >= 60]
    low_payoff_runs = _max_consecutive(
        [p.payoff_score < 30 for p in sorted(profiles, key=lambda x: x.scene_ordinal)]
    )
    high_load_runs = _max_consecutive(
        [p.cognitive_load_score >= 70 for p in sorted(profiles, key=lambda x: x.scene_ordinal)]
    )
    stats = boundary_stats or {}
    profile_items = [
        SceneReaderJourneyProfileItem.model_validate_json(item.payload_json)
        for item in profiles
    ]
    question_chain_diagnostics = diagnose_dropped_high_strength_questions(profile_items)
    return {
        "total_scene_count": len(scenes),
        "phase_count": phase_count,
        "coverage_rate": 1.0 if len(profiles) == len(scenes) else len(profiles) / max(len(scenes), 1),
        "single_scene_phase_count": len(single_scene_ordinals),
        "longest_scene_ordinal": longest.ordinal,
        "longest_scene_paragraph_count": longest_count,
        "average_paragraph_count": round(sum(paragraph_counts) / max(len(paragraph_counts), 1), 2),
        "manual_added_boundary_count": stats.get("manual_added_boundary_count", 0),
        "model_accepted_boundary_count": stats.get("model_accepted_boundary_count", 0),
        "user_accepted_conflict_count": stats.get("user_accepted_conflict_count", 0),
        "evidence_coverage_rate": 1.0,
        "engagement_curve": engagement_curve,
        "valence_curve": valence_curve,
        "arousal_curve": arousal_curve,
        "strong_hook_scene_ids": strong_hooks,
        "medium_hook_scene_ids": medium_hooks,
        "weak_hook_scene_ids": weak_hooks,
        "risk_scene_ids": risk_scenes,
        "max_consecutive_low_payoff_span": low_payoff_runs,
        "max_consecutive_high_cognitive_load_span": high_load_runs,
        "question_chains": build_question_chains(profile_items),
        "question_chain_diagnostics": question_chain_diagnostics,
    }


def _max_consecutive(flags: list[bool]) -> int:
    best = current = 0
    for flag in flags:
        if flag:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best
