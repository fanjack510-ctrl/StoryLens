from app.schemas.scene import (
    CompactTransitionClassificationResultV34,
    SceneBoundary,
    SceneBoundaryResult,
)
from app.services.scene_transitions import AdjacentTransition

REASONS = {
    "explicit_scene_separator": "出现明确的场景分隔，下一段开始新的叙事单元。",
    "viewpoint_change": "叙事主体发生切换，下一段形成独立行动链。",
    "location_change": "地点发生变化，下一段开始新的连续行动。",
    "time_jump": "时间进入新的阶段，下一段开始独立叙事。",
    "primary_goal_reset": "原核心目标已经结束或被替换，下一段开始新的持续行动。",
}
STATES = {
    "explicit_scene_separator": ("上一叙事单元结束", "新的叙事单元开始"),
    "viewpoint_change": ("原叙事主体行动结束", "新叙事主体开始独立行动"),
    "location_change": ("原地点行动结束", "新地点行动开始"),
    "time_jump": ("原时间阶段结束", "新时间阶段开始"),
    "primary_goal_reset": ("原核心目标结束或被替换", "新的持续目标开始"),
}


def deterministic_reason(decision) -> str | None:
    if decision.trigger_type == "explicit_separator":
        return "explicit_scene_separator"
    if decision.viewpoint_relation == "changed" and decision.action_chain_relation == "new_chain":
        return "viewpoint_change"
    if (
        decision.location_relation == "new_scene_location"
        and decision.action_chain_relation == "new_chain"
    ):
        return "location_change"
    if decision.temporal_relation == "major_jump":
        return "time_jump"
    if (
        decision.goal_relation in {"completed_then_new", "replaced", "interrupted"}
        and decision.action_chain_relation == "new_chain"
        and (
            decision.goal_relation != "interrupted"
            or decision.trigger_type in {"goal", "object", "location", "time", "viewpoint"}
        )
    ):
        return "primary_goal_reset"
    return None


def compact_v34_to_canonical(
    result: CompactTransitionClassificationResultV34,
    *,
    expected_transition_ids: list[str],
    candidates: list[AdjacentTransition],
    allowed_paragraph_ids: set[str],
    chapter_id: str,
) -> SceneBoundaryResult:
    decision_ids = [item.transition_id for item in result.decisions]
    if decision_ids != expected_transition_ids or len(decision_ids) != len(set(decision_ids)):
        raise ValueError("v3.4 decisions must cover owned transitions exactly once in order")
    by_id = {item.transition_id: item for item in candidates}
    if any(item not in by_id for item in decision_ids):
        raise ValueError("v3.4 response contains invalid transition_id")
    evidence = {item.transition_id: item for item in result.boundary_evidence}
    if len(evidence) != len(result.boundary_evidence):
        raise ValueError("duplicate boundary_evidence transition_id")
    selected = {item.transition_id for item in result.decisions if item.boundary}
    if set(evidence) != selected:
        raise ValueError("boundary_evidence must match boundary=true decisions exactly")
    boundaries = []
    for decision in result.decisions:
        reason_code = deterministic_reason(decision)
        if decision.boundary != (reason_code is not None):
            raise ValueError("boundary decision conflicts with deterministic enum rules")
        if not decision.boundary:
            continue
        evidence_item = evidence[decision.transition_id]
        if any(item not in allowed_paragraph_ids for item in evidence_item.evidence_paragraph_ids):
            raise ValueError("boundary evidence is outside the allowed context")
        previous, following = STATES[reason_code]
        candidate = by_id[decision.transition_id]
        if decision.goal_relation == "interrupted":
            if decision.confidence < 0.60:
                raise ValueError("interrupted goal boundary confidence is below 0.60")
            if not {
                candidate.left_paragraph_id,
                candidate.right_paragraph_id,
            }.issubset(set(evidence_item.evidence_paragraph_ids)):
                raise ValueError("interrupted goal boundary evidence must cover both sides")
        reason_summary = REASONS[reason_code]
        if reason_code == "primary_goal_reset":
            reason_summary = {
                "completed_then_new": "原核心目标已经完成，下一段开始新的持续行动。",
                "replaced": "原核心目标被替换，下一段开始新的持续行动。",
                "interrupted": "原核心目标被中断，下一段开始新的持续行动链。",
            }[decision.goal_relation]
        boundaries.append(
            SceneBoundary(
                after_paragraph_id=candidate.left_paragraph_id,
                reason_code=reason_code,
                reason_summary=reason_summary,
                previous_scene_end_state=previous,
                next_scene_start_state=following,
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
