import pytest
from pydantic import ValidationError

from app.db.models import Paragraph
from app.schemas.scene import (
    BoundaryCandidateAdjudicationResult,
    CompactTransitionCandidateDecision,
    CompactTransitionClassificationResultV35,
)
from app.services.scene_boundary_adjudicator import (
    adjudicated_to_canonical,
    deterministic_evidence,
    plan_adjudication_batches,
    validate_adjudication,
    validate_candidate_detection,
)
from app.services.scene_pipeline import scene_ranges
from app.services.scene_transitions import build_adjacent_transitions


def decision(transition_id="T0001", candidate=True, **values):
    item = {
        "transition_id": transition_id,
        "boundary_candidate": candidate,
        "goal_relation": "replaced" if candidate else "same",
        "action_chain_relation": "new_chain" if candidate else "continuous",
        "temporal_relation": "continuous",
        "location_relation": "same",
        "viewpoint_relation": "same",
        "trigger_type": "goal" if candidate else "none",
        "confidence": 0.8,
    }
    item.update(values)
    return CompactTransitionCandidateDecision.model_validate(item)


def result(*items):
    return BoundaryCandidateAdjudicationResult.model_validate(
        {"contract_version": "1.0", "verdicts": list(items)}
    )


def verdict(transition_id="T0001", accept=True, **values):
    item = {
        "transition_id": transition_id,
        "accept": accept,
        "scope_relation": "primary_scene_change" if accept else "local_subgoal_change",
        "continuity_relation": "new_scene_chain" if accept else "same_scene_chain",
        "confidence": 0.9,
    }
    item.update(values)
    return item


def test_v35_provider_contract_has_no_evidence_or_final_boundary_field():
    schema = CompactTransitionClassificationResultV35.model_json_schema()
    dumped = str(schema)
    assert "boundary_evidence" not in dumped
    assert "boundary_candidate" in dumped
    with pytest.raises(ValidationError):
        CompactTransitionClassificationResultV35.model_validate(
            {
                "contract_version": "3.5",
                "decisions": [decision().model_dump()],
                "boundary_evidence": [],
            }
        )


def test_detection_requires_exact_order_and_legal_candidate_combination():
    validate_candidate_detection([decision()], ["T0001"])
    with pytest.raises(ValueError, match="exactly once"):
        validate_candidate_detection([decision()], ["T0002"])
    with pytest.raises(ValueError, match="conflicts"):
        validate_candidate_detection(
            [decision(action_chain_relation="continuous")], ["T0001"]
        )


def test_no_candidates_produce_no_adjudication_batches():
    transitions = build_adjacent_transitions(["P1", "P2"])
    assert plan_adjudication_batches([], transitions, {"P1": "a", "P2": "b"}) == []


def test_candidate_adjudication_has_exact_stable_coverage():
    validate_adjudication(result(verdict()), ["T0001"])
    with pytest.raises(ValueError, match="exactly once"):
        validate_adjudication(result(verdict("T0002")), ["T0001"])
    with pytest.raises(ValueError, match="exactly once"):
        validate_adjudication(result(verdict(), verdict()), ["T0001"])


@pytest.mark.parametrize(
    "scope,continuity",
    [
        ("local_subgoal_change", "same_scene_chain"),
        ("temporary_interruption", "resumes_previous_chain"),
        ("primary_scene_change", "same_scene_chain"),
    ],
)
def test_non_scene_level_or_continuous_verdicts_are_rejected(scope, continuity):
    validate_adjudication(
        result(verdict(accept=False, scope_relation=scope, continuity_relation=continuity)),
        ["T0001"],
    )


def test_accept_requires_primary_change_and_new_scene_chain():
    with pytest.raises(ValueError, match="conflicts"):
        validate_adjudication(
            result(verdict(scope_relation="local_subgoal_change")), ["T0001"]
        )


def test_second_pass_reject_removes_candidate_and_accept_preserves_reason():
    transitions = build_adjacent_transitions(["P1", "P2"])
    rejected = adjudicated_to_canonical(
        chapter_id="C1",
        decisions=[decision()],
        verdicts=result(verdict(accept=False)),
        candidates=transitions,
        allowed_paragraph_ids={"P1", "P2"},
    )
    accepted = adjudicated_to_canonical(
        chapter_id="C1",
        decisions=[decision()],
        verdicts=result(verdict()),
        candidates=transitions,
        allowed_paragraph_ids={"P1", "P2"},
    )
    assert rejected.boundaries == []
    assert accepted.boundaries[0].reason_code == "primary_goal_reset"
    assert deterministic_evidence(transitions[0]) == ("P1", "P2")


def test_batch_seam_candidate_receives_three_preceding_paragraphs():
    ids = [f"P{i}" for i in range(1, 10)]
    transitions = build_adjacent_transitions(ids)
    batch = plan_adjudication_batches(
        ["T0007"], transitions, {item: item for item in ids}
    )[0]
    assert batch.context_paragraph_ids == ("P4", "P5", "P6", "P7", "P8", "P9")


def test_adjudication_planner_splits_deterministically_under_token_limit():
    ids = [f"P{i}" for i in range(1, 12)]
    transitions = build_adjacent_transitions(ids)
    text = {item: "通用叙事文本" * 30 for item in ids}
    batches = plan_adjudication_batches(
        ["T0002", "T0008"], transitions, text, max_input_tokens=1_500
    )
    assert [item.candidate_transition_ids for item in batches] == [("T0002",), ("T0008",)]
    assert all(item.input_token_estimate <= 1_500 for item in batches)


def test_scene_ranges_remain_continuous_without_overlap():
    paragraphs = [
        Paragraph(
            id=f"P{i}", book_id=1, chapter_id=1, paragraph_index=i,
            raw_text=str(i), normalized_text=str(i), char_start=i, char_end=i + 1,
        )
        for i in range(1, 5)
    ]
    ranges = scene_ranges(paragraphs, [paragraphs[1].id])
    assert ranges[0] == (paragraphs[0], paragraphs[1])
    assert ranges[1] == (paragraphs[2], paragraphs[-1])
