from app.schemas.scene import (
    CompactTransitionClassificationResult,
    SceneBoundary,
    SceneBoundaryResult,
)
from app.services.scene_transitions import AdjacentTransition


def _valid_selected(decision, detail) -> bool:
    if detail.reason_code == "time_jump":
        return decision.temporal_relation == "major_jump"
    if detail.reason_code == "location_change":
        return (
            decision.location_relation == "new_scene_location"
            and decision.action_chain_relation == "new_chain"
        )
    if detail.reason_code == "viewpoint_change":
        return (
            decision.viewpoint_relation == "changed"
            and decision.action_chain_relation == "new_chain"
        )
    if detail.reason_code == "primary_goal_reset":
        return (
            decision.goal_relation in {"completed_then_new", "replaced"}
            and decision.action_chain_relation == "new_chain"
            and decision.trigger_type in {"goal", "object"}
        )
    return (
        detail.reason_code == "explicit_scene_separator"
        and decision.trigger_type == "explicit_separator"
    )


def compact_to_canonical(
    result: CompactTransitionClassificationResult,
    *,
    expected_transition_ids: list[str],
    candidates: list[AdjacentTransition],
    allowed_paragraph_ids: set[str],
    chapter_id: str,
) -> SceneBoundaryResult:
    decision_ids = [item.transition_id for item in result.decisions]
    if decision_ids != expected_transition_ids or len(decision_ids) != len(set(decision_ids)):
        raise ValueError("compact decisions must cover owned transitions exactly once in order")
    by_id = {item.transition_id: item for item in candidates}
    if any(item not in by_id for item in decision_ids):
        raise ValueError("compact response contains an invalid transition_id")
    details = {item.transition_id: item for item in result.selected_details}
    if len(details) != len(result.selected_details):
        raise ValueError("duplicate selected_details transition_id")
    selected = {item.transition_id for item in result.decisions if item.boundary}
    if set(details) != selected:
        raise ValueError("selected_details must match boundary=true decisions exactly")
    boundaries = []
    for decision in result.decisions:
        if not decision.boundary:
            continue
        detail = details[decision.transition_id]
        if not _valid_selected(decision, detail):
            raise ValueError("compact transition fields contradict selected detail")
        if any(item not in allowed_paragraph_ids for item in detail.evidence_paragraph_ids):
            raise ValueError("compact transition evidence is outside the input")
        candidate = by_id[decision.transition_id]
        boundaries.append(
            SceneBoundary(
                after_paragraph_id=candidate.left_paragraph_id,
                reason_code=detail.reason_code,
                reason_summary=detail.concise_reason,
                previous_scene_end_state=detail.previous_primary_goal,
                next_scene_start_state=detail.next_primary_goal,
                confidence=decision.confidence,
            )
        )
    confidence = (
        sum(item.confidence for item in result.decisions) / len(result.decisions)
        if result.decisions
        else 1.0
    )
    return SceneBoundaryResult(
        chapter_id=chapter_id, boundaries=boundaries, overall_confidence=confidence
    )
