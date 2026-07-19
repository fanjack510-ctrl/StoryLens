from dataclasses import dataclass

from app.schemas.scene import SceneBoundary, SceneBoundaryResult, SceneTransitionResult


@dataclass(frozen=True)
class AdjacentTransition:
    transition_id: str
    left_paragraph_id: str
    right_paragraph_id: str

    def as_dict(self) -> dict[str, str]:
        return {
            "transition_id": self.transition_id,
            "left_paragraph_id": self.left_paragraph_id,
            "right_paragraph_id": self.right_paragraph_id,
        }


def build_adjacent_transitions(paragraph_ids: list[str]) -> list[AdjacentTransition]:
    return [
        AdjacentTransition(f"T{index:04d}", left, right)
        for index, (left, right) in enumerate(
            zip(paragraph_ids, paragraph_ids[1:], strict=False), 1
        )
    ]


def _supports_boundary(decision) -> bool:
    if not decision.boundary_decision:
        return False
    if decision.temporal_relation == "brief_flashback":
        return False
    if decision.reason_code == "location_change":
        return (
            decision.location_relation == "new_scene_location"
            and decision.action_chain_relation == "new_chain"
        )
    if decision.reason_code == "time_jump":
        return decision.temporal_relation == "major_jump"
    if decision.reason_code == "viewpoint_change":
        return (
            decision.viewpoint_relation == "changed"
            and decision.action_chain_relation == "new_chain"
        )
    if decision.reason_code == "primary_goal_reset":
        return (
            decision.goal_relation in {"completed_then_new", "replaced"}
            and decision.action_chain_relation == "new_chain"
            and decision.sustained_change
            and decision.trigger_type in {"goal", "object"}
        )
    if decision.reason_code == "explicit_scene_separator":
        return decision.trigger_type == "explicit_separator"
    return False


def validate_and_map_transitions(
    result: SceneTransitionResult,
    *,
    expected_chapter_id: str,
    candidates: list[AdjacentTransition],
    allowed_paragraph_ids: set[str],
) -> SceneBoundaryResult:
    if result.chapter_id != expected_chapter_id:
        raise ValueError("transition chapter id mismatch")
    by_id = {item.transition_id: item for item in candidates}
    unique_decisions = {}
    for item in result.transitions:
        previous = unique_decisions.get(item.transition_id)
        if previous is not None and previous != item:
            raise ValueError("conflicting duplicate transition_id")
        unique_decisions[item.transition_id] = item
    decision_ids = list(unique_decisions)
    if set(decision_ids) != set(by_id):
        raise ValueError("all and only candidate transition_ids must be classified")
    boundaries: list[SceneBoundary] = []
    for decision in unique_decisions.values():
        candidate = by_id[decision.transition_id]
        if any(item not in allowed_paragraph_ids for item in decision.evidence_paragraph_ids):
            raise ValueError("transition evidence references an invalid paragraph")
        supported = _supports_boundary(decision)
        if decision.boundary_decision and not supported:
            raise ValueError("transition fields contradict boundary_decision")
        if not decision.boundary_decision:
            if decision.reason_code is not None:
                raise ValueError("rejected transition must not include reason_code")
            continue
        boundaries.append(
            SceneBoundary(
                after_paragraph_id=candidate.left_paragraph_id,
                reason_code=decision.reason_code,
                reason_summary=decision.concise_reason,
                previous_scene_end_state=decision.previous_primary_goal,
                next_scene_start_state=decision.next_primary_goal,
                confidence=decision.confidence,
            )
        )
    return SceneBoundaryResult(
        chapter_id=result.chapter_id,
        boundaries=boundaries,
        overall_confidence=result.overall_confidence,
    )
