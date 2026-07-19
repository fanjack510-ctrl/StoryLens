import pytest

from app.schemas.scene import CompactTransitionClassificationResultV34
from app.services.compact_transition_adapter_v34 import compact_v34_to_canonical
from app.services.scene_transitions import build_adjacent_transitions


def _decision(**overrides):
    value = {
        "transition_id": "T0001",
        "boundary": True,
        "goal_relation": "interrupted",
        "action_chain_relation": "new_chain",
        "temporal_relation": "continuous",
        "location_relation": "same",
        "viewpoint_relation": "same",
        "trigger_type": "goal",
        "confidence": 0.8,
    }
    value.update(overrides)
    return value


def _adapt(item, evidence=("P1", "P2")):
    result = CompactTransitionClassificationResultV34.model_validate(
        {
            "contract_version": "3.4",
            "decisions": [item],
            "boundary_evidence": (
                [{"transition_id": "T0001", "evidence_paragraph_ids": list(evidence)}]
                if item["boundary"]
                else []
            ),
        }
    )
    return compact_v34_to_canonical(
        result,
        expected_transition_ids=["T0001"],
        candidates=build_adjacent_transitions(["P1", "P2"]),
        allowed_paragraph_ids={"P1", "P2"},
        chapter_id="C1",
    )


@pytest.mark.parametrize("trigger", ["goal", "object", "location", "time", "viewpoint"])
def test_interrupted_goal_with_new_chain_is_a_canonical_boundary(trigger):
    boundary = _adapt(_decision(trigger_type=trigger)).boundaries[0]
    assert boundary.reason_code == "primary_goal_reset"
    assert boundary.reason_summary == "原核心目标被中断，下一段开始新的持续行动链。"
    assert boundary.after_paragraph_id == "P1"


@pytest.mark.parametrize(
    "item",
    [
        _decision(boundary=False, action_chain_relation="continuous"),
        _decision(boundary=False, trigger_type="none"),
        _decision(boundary=False, goal_relation="same"),
        _decision(boundary=False, goal_relation="refined"),
    ],
)
def test_brief_interruption_or_same_action_chain_remains_non_boundary(item):
    assert _adapt(item).boundaries == []


def test_interrupted_goal_cannot_claim_boundary_for_continuous_chain():
    with pytest.raises(ValueError, match="conflicts"):
        _adapt(_decision(action_chain_relation="continuous"))


def test_interrupted_goal_boundary_requires_business_confidence_threshold():
    with pytest.raises(ValueError, match="below 0.60"):
        _adapt(_decision(confidence=0.59))


@pytest.mark.parametrize("evidence", [("P1",), ("P2",)])
def test_interrupted_goal_boundary_requires_evidence_from_both_sides(evidence):
    with pytest.raises(ValueError, match="cover both sides"):
        _adapt(_decision(), evidence)


@pytest.mark.parametrize(
    ("relation", "summary"),
    [
        ("completed_then_new", "原核心目标已经完成，下一段开始新的持续行动。"),
        ("replaced", "原核心目标被替换，下一段开始新的持续行动。"),
    ],
)
def test_existing_goal_reset_results_keep_canonical_reason(relation, summary):
    boundary = _adapt(_decision(goal_relation=relation, trigger_type="none")).boundaries[0]
    assert boundary.reason_code == "primary_goal_reset"
    assert boundary.reason_summary == summary
