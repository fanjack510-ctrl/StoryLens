from dataclasses import dataclass

from app.schemas.scene import (
    BoundaryCandidateAdjudicationResult,
    CandidateReviewIssue,
    CandidateReviewValidationResult,
    CompactTransitionCandidateDecision,
    SceneBoundary,
    SceneBoundaryResult,
)
from app.services.compact_transition_adapter_v34 import REASONS, STATES, deterministic_reason
from app.services.scene_transitions import AdjacentTransition
from app.services.transition_batch_planner import conservative_token_estimate
from app.services.validation_errors import StructuralValidationError

MAX_ADJUDICATION_INPUT_TOKENS = 12_000


@dataclass(frozen=True)
class AdjudicationBatch:
    candidate_transition_ids: tuple[str, ...]
    context_paragraph_ids: tuple[str, ...]
    input_token_estimate: int


def deterministic_evidence(transition: AdjacentTransition) -> tuple[str, str]:
    return transition.left_paragraph_id, transition.right_paragraph_id


def validate_candidate_detection(
    decisions: list[CompactTransitionCandidateDecision],
    expected_transition_ids: list[str],
) -> None:
    validate_candidate_detection_structure(decisions, expected_transition_ids)
    for item in decisions:
        legal = deterministic_reason(item) is not None
        if item.boundary_candidate != legal:
            raise ValueError("candidate decision conflicts with deterministic enum rules")


def validate_candidate_detection_structure(
    decisions: list[CompactTransitionCandidateDecision],
    expected_transition_ids: list[str],
) -> None:
    ids = [item.transition_id for item in decisions]
    if ids != expected_transition_ids or len(ids) != len(set(ids)):
        raise StructuralValidationError(
            "v3.5 decisions must cover owned transitions exactly once in order"
        )


def validate_candidate_detection_for_review(
    decisions: list[CompactTransitionCandidateDecision],
    expected_transition_ids: list[str],
) -> CandidateReviewValidationResult:
    """Keep structural validation strict while routing semantic conflicts to review."""
    validate_candidate_detection_structure(decisions, expected_transition_ids)
    valid: list[CompactTransitionCandidateDecision] = []
    conflicted: list[CompactTransitionCandidateDecision] = []
    issues: list[CandidateReviewIssue] = []
    for item in decisions:
        reason = deterministic_reason(item)
        legal = reason is not None
        if item.boundary_candidate == legal:
            valid.append(item)
            continue
        conflict_code = (
            "CANDIDATE_TRUE_WITHOUT_LEGAL_REASON"
            if item.boundary_candidate
            else "CANDIDATE_FALSE_WITH_LEGAL_REASON"
        )
        priority = "high"
        safe_message = (
            "模型认为这里可能是场景边界，但其结构化分类未满足确定性边界规则，需要人工判断。"
            if item.boundary_candidate
            else "结构化分类满足确定性边界规则，但模型未标记候选，需要人工判断。"
        )
        conflicted.append(item)
        issues.append(
            CandidateReviewIssue(
                transition_id=item.transition_id,
                conflict_code=conflict_code,
                boundary_candidate=item.boundary_candidate,
                deterministic_legal=legal,
                deterministic_reason=reason,
                goal_relation=item.goal_relation,
                action_chain_relation=item.action_chain_relation,
                temporal_relation=item.temporal_relation,
                location_relation=item.location_relation,
                viewpoint_relation=item.viewpoint_relation,
                trigger_type=item.trigger_type,
                confidence=item.confidence,
                review_priority=priority,
                safe_message=safe_message,
            )
        )
    return CandidateReviewValidationResult(
        valid_decisions=valid,
        conflicted_decisions=conflicted,
        issues=issues,
    )


def _context_ids(candidate: AdjacentTransition, all_candidates: list[AdjacentTransition]) -> list[str]:
    index = all_candidates.index(candidate)
    start = max(0, index - 3)
    end = min(len(all_candidates), index + 4)
    ids = [all_candidates[start].left_paragraph_id]
    ids.extend(item.right_paragraph_id for item in all_candidates[start:end])
    return list(dict.fromkeys(ids))


def plan_adjudication_batches(
    candidate_ids: list[str],
    all_candidates: list[AdjacentTransition],
    paragraph_text: dict[str, str],
    *,
    max_input_tokens: int = MAX_ADJUDICATION_INPUT_TOKENS,
) -> list[AdjudicationBatch]:
    if not candidate_ids:
        return []
    by_id = {item.transition_id: item for item in all_candidates}
    batches: list[AdjudicationBatch] = []
    current: list[str] = []
    current_context: list[str] = []
    for transition_id in candidate_ids:
        candidate = by_id.get(transition_id)
        if candidate is None:
            raise ValueError("invalid adjudication candidate")
        context = list(dict.fromkeys(current_context + _context_ids(candidate, all_candidates)))
        payload = {
            "candidate_transition_ids": current + [transition_id],
            "paragraphs": [{"id": item, "text": paragraph_text[item]} for item in context],
        }
        estimate = conservative_token_estimate(payload)
        if current and estimate > max_input_tokens:
            prior_payload = {
                "candidate_transition_ids": current,
                "paragraphs": [
                    {"id": item, "text": paragraph_text[item]} for item in current_context
                ],
            }
            batches.append(
                AdjudicationBatch(
                    tuple(current),
                    tuple(current_context),
                    conservative_token_estimate(prior_payload),
                )
            )
            current, current_context = [transition_id], _context_ids(candidate, all_candidates)
        else:
            current.append(transition_id)
            current_context = context
    final_payload = {
        "candidate_transition_ids": current,
        "paragraphs": [{"id": item, "text": paragraph_text[item]} for item in current_context],
    }
    estimate = conservative_token_estimate(final_payload)
    if estimate > max_input_tokens:
        raise ValueError("one adjudication candidate exceeds the input token budget")
    batches.append(AdjudicationBatch(tuple(current), tuple(current_context), estimate))
    return batches


def validate_adjudication(
    value: BoundaryCandidateAdjudicationResult, expected_candidate_ids: list[str]
) -> None:
    ids = [item.transition_id for item in value.verdicts]
    if ids != expected_candidate_ids or len(ids) != len(set(ids)):
        raise ValueError("adjudication must cover candidates exactly once in order")
    for verdict in value.verdicts:
        legal_accept = (
            verdict.scope_relation == "primary_scene_change"
            and verdict.continuity_relation == "new_scene_chain"
        )
        if verdict.accept != legal_accept:
            raise ValueError("adjudication verdict conflicts with deterministic rules")


def adjudicated_to_canonical(
    *,
    chapter_id: str,
    decisions: list[CompactTransitionCandidateDecision],
    verdicts: BoundaryCandidateAdjudicationResult,
    candidates: list[AdjacentTransition],
    allowed_paragraph_ids: set[str],
) -> SceneBoundaryResult:
    candidate_decisions = [item for item in decisions if item.boundary_candidate]
    validate_adjudication(verdicts, [item.transition_id for item in candidate_decisions])
    by_transition = {item.transition_id: item for item in candidates}
    accepted = {item.transition_id for item in verdicts.verdicts if item.accept}
    boundaries: list[SceneBoundary] = []
    for decision in candidate_decisions:
        if decision.transition_id not in accepted:
            continue
        transition = by_transition[decision.transition_id]
        evidence = set(deterministic_evidence(transition))
        if not evidence.issubset(allowed_paragraph_ids):
            raise ValueError("deterministic boundary evidence is outside the chapter")
        reason = deterministic_reason(decision)
        if reason is None:
            raise ValueError("accepted candidate has no canonical reason")
        summary = REASONS[reason]
        if reason == "primary_goal_reset":
            summary = {
                "completed_then_new": "原核心目标已经完成，下一段开始新的持续行动。",
                "replaced": "原核心目标被替换，下一段开始新的持续行动。",
                "interrupted": "原核心目标被中断，下一段开始新的持续行动链。",
            }.get(decision.goal_relation, summary)
        previous, following = STATES[reason]
        boundaries.append(
            SceneBoundary(
                after_paragraph_id=transition.left_paragraph_id,
                reason_code=reason,
                reason_summary=summary,
                previous_scene_end_state=previous,
                next_scene_start_state=following,
                confidence=decision.confidence,
            )
        )
    confidence = (
        sum(item.confidence for item in decisions) / len(decisions) if decisions else 1.0
    )
    return SceneBoundaryResult(
        chapter_id=chapter_id, boundaries=boundaries, overall_confidence=confidence
    )


def adjudication_snapshot(
    *,
    chapter_id: str,
    title: str,
    batch: AdjudicationBatch,
    candidates: list[AdjacentTransition],
    decisions: list[CompactTransitionCandidateDecision],
    paragraph_text: dict[str, str],
) -> dict[str, object]:
    by_id = {item.transition_id: item for item in candidates}
    decision_by_id = {item.transition_id: item for item in decisions}
    return {
        "chapter_id": chapter_id,
        "chapter_title": title,
        "total_transition_count": len(candidates),
        "candidate_transition_ids": list(batch.candidate_transition_ids),
        "candidates": [
            {
                **by_id[item].as_dict(),
                "transition_ordinal": candidates.index(by_id[item]) + 1,
                "first_pass": decision_by_id[item].model_dump(),
            }
            for item in batch.candidate_transition_ids
        ],
        "paragraphs": [
            {"id": item, "text": paragraph_text[item]} for item in batch.context_paragraph_ids
        ],
    }
