import pytest
from pydantic import ValidationError

from app.schemas.scene import CompactTransitionClassificationResultV34
from app.services.compact_transition_adapter_v34 import compact_v34_to_canonical
from app.services.scene_transitions import build_adjacent_transitions


def decision(boundary=False, **overrides):
    value = {
        "transition_id": "T0001",
        "boundary": boundary,
        "goal_relation": "same",
        "action_chain_relation": "continuous",
        "temporal_relation": "continuous",
        "location_relation": "same",
        "viewpoint_relation": "same",
        "trigger_type": "none",
        "confidence": 0.5,
    }
    value.update(overrides)
    return value


def payload(item, evidence=()):
    return CompactTransitionClassificationResultV34.model_validate(
        {"contract_version": "3.4", "decisions": [item], "boundary_evidence": evidence}
    )


def adapt(value):
    return compact_v34_to_canonical(
        value,
        expected_transition_ids=["T0001"],
        candidates=build_adjacent_transitions(["P1", "P2"]),
        allowed_paragraph_ids={"P1", "P2"},
        chapter_id="C1",
    )


def evidence():
    return [{"transition_id": "T0001", "evidence_paragraph_ids": ["P1", "P2"]}]


def test_v34_forbids_duplicate_semantic_text_fields():
    with pytest.raises(ValidationError):
        payload({**decision(), "reason_code": "time_jump"})


@pytest.mark.parametrize(
    "item,reason",
    [
        (decision(True, temporal_relation="major_jump"), "time_jump"),
        (
            decision(True, location_relation="new_scene_location", action_chain_relation="new_chain"),
            "location_change",
        ),
        (
            decision(True, viewpoint_relation="changed", action_chain_relation="new_chain"),
            "viewpoint_change",
        ),
        (
            decision(True, goal_relation="replaced", action_chain_relation="new_chain"),
            "primary_goal_reset",
        ),
        (
            decision(
                True,
                trigger_type="object",
                goal_relation="replaced",
                action_chain_relation="new_chain",
            ),
            "primary_goal_reset",
        ),
    ],
)
def test_v34_deterministically_generates_canonical_reason(item, reason):
    boundary = adapt(payload(item, evidence())).boundaries[0]
    assert boundary.reason_code == reason
    assert boundary.reason_summary and boundary.previous_scene_end_state


def test_v34_rejects_boundary_evidence_mismatch_and_invalid_id():
    with pytest.raises(ValueError):
        adapt(payload(decision(True, temporal_relation="major_jump")))
    with pytest.raises(ValueError):
        adapt(
            payload(
                decision(True, temporal_relation="major_jump"),
                [{"transition_id": "T0001", "evidence_paragraph_ids": ["P9"]}],
            )
        )


def test_v34_rejects_enum_boundary_contradiction():
    with pytest.raises(ValueError, match="conflicts"):
        adapt(payload(decision(True), evidence()))
    with pytest.raises(ValueError, match="conflicts"):
        adapt(payload(decision(False, temporal_relation="major_jump")))


def test_v34_schema_forbids_additional_properties():
    schema = CompactTransitionClassificationResultV34.model_json_schema()
    assert schema["additionalProperties"] is False
    assert all(item.get("additionalProperties") is False for item in schema["$defs"].values())
