import pytest
from pydantic import ValidationError

from app.schemas.scene import CompactTransitionClassificationResult
from app.services.compact_transition_adapter import compact_to_canonical
from app.services.scene_transitions import build_adjacent_transitions
from app.services.transition_batch_planner import (
    TARGET_TOKENS,
    plan_transition_batches,
)


IDS = ["P0001", "P0002", "P0003"]
CANDIDATES = build_adjacent_transitions(IDS)


def compact(decisions, details=()):
    return CompactTransitionClassificationResult.model_validate(
        {"contract_version": "3.3", "decisions": decisions, "selected_details": details}
    )


def item(tid="T0001", boundary=False, **overrides):
    value = {
        "transition_id": tid,
        "boundary": boundary,
        "goal_relation": "same",
        "action_chain_relation": "continuous",
        "temporal_relation": "continuous",
        "location_relation": "same",
        "viewpoint_relation": "same",
        "trigger_type": "none",
        "confidence": 0.1,
    }
    value.update(overrides)
    return value


def detail(tid="T0001", reason="time_jump"):
    return {
        "transition_id": tid,
        "reason_code": reason,
        "previous_primary_goal": "旧目标",
        "next_primary_goal": "新目标",
        "concise_reason": "进入新阶段",
        "evidence_paragraph_ids": ["P0001", "P0002"],
    }


def adapt(value, expected=("T0001", "T0002")):
    return compact_to_canonical(
        value,
        expected_transition_ids=list(expected),
        candidates=CANDIDATES,
        allowed_paragraph_ids=set(IDS),
        chapter_id="C1",
    )


def test_compact_dto_forbids_extra_fields():
    with pytest.raises(ValidationError):
        compact([{**item(), "explanation": "not allowed"}])


@pytest.mark.parametrize(
    "decisions,details",
    [
        ([item("T0001")], []),
        ([item("T0001"), item("T0001")], []),
        ([item("T9999"), item("T0002")], []),
        ([item("T0001", True), item("T0002")], []),
        ([item("T0001"), item("T0002")], [detail("T0001")]),
        (
            [item("T0001", True, temporal_relation="major_jump"), item("T0002")],
            [detail("T0001"), detail("T0001")],
        ),
    ],
)
def test_compact_coverage_and_detail_mismatches_are_rejected(decisions, details):
    with pytest.raises(ValueError):
        adapt(compact(decisions, details))


def test_time_jump_same_goal_maps_to_left_paragraph():
    value = compact(
        [item("T0001", True, temporal_relation="major_jump"), item("T0002")],
        [detail("T0001", "time_jump")],
    )
    assert adapt(value).boundaries[0].after_paragraph_id == "P0001"


@pytest.mark.parametrize(
    "decision,selected_detail",
    [
        (
            item(
                "T0001",
                True,
                goal_relation="replaced",
                action_chain_relation="new_chain",
                trigger_type="goal",
            ),
            detail("T0001", "primary_goal_reset"),
        ),
        (
            item(
                "T0001",
                True,
                goal_relation="completed_then_new",
                action_chain_relation="new_chain",
                trigger_type="object",
            ),
            detail("T0001", "primary_goal_reset"),
        ),
    ],
)
def test_goal_and_object_resets_map(decision, selected_detail):
    assert len(adapt(compact([decision, item("T0002")], [selected_detail])).boundaries) == 1


def test_refined_goal_cannot_claim_primary_goal_reset():
    value = compact(
        [item("T0001", True, goal_relation="refined"), item("T0002")],
        [detail("T0001", "primary_goal_reset")],
    )
    with pytest.raises(ValueError, match="contradict"):
        adapt(value)


def test_batch_planner_capacity_and_owned_coverage():
    eight = build_adjacent_transitions([f"P{i:04d}" for i in range(9)])
    eight_batches = plan_transition_batches(eight)
    assert len(eight_batches) > 1
    assert all(batch.worst_case_output_tokens <= TARGET_TOKENS < 768 for batch in eight_batches)
    ten = build_adjacent_transitions([f"P{i:04d}" for i in range(11)])
    batches = plan_transition_batches(ten)
    owned = [item for batch in batches for item in batch.owned_transition_ids]
    assert owned == [item.transition_id for item in ten]
    assert len(owned) == len(set(owned)) and len(batches) > 1


def test_false_decisions_do_not_need_selected_details():
    value = compact([item("T0001"), item("T0002")])
    assert adapt(value).boundaries == []


def test_compact_schema_has_additional_properties_false():
    schema = CompactTransitionClassificationResult.model_json_schema()
    assert schema["additionalProperties"] is False
    assert all(value.get("additionalProperties") is False for value in schema["$defs"].values())
