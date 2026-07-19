import json

import pytest
from sqlalchemy import select

from app.db.models import ModelInvocation
from app.model_gateway.gateway import ModelGateway
from app.schemas.scene import SceneTransitionResult
from app.services.prompt_service import load_prompt, with_response_contract
from app.services.response_contract import contract_hash
from app.services.scene_transitions import build_adjacent_transitions, validate_and_map_transitions
from app.services.structured_output import generate_validated
from tests.test_model_gateway import make_run
from tests.test_phase_2b1 import CloudFake


PARAGRAPHS = ["B0099-C0001-P0001", "B0099-C0001-P0002"]


def decision(**overrides):
    value = {
        "transition_id": "T0001",
        "previous_primary_goal": "完成旧行动",
        "next_primary_goal": "开始新行动",
        "goal_relation": "completed_then_new",
        "action_chain_relation": "new_chain",
        "temporal_relation": "continuous",
        "location_relation": "same",
        "viewpoint_relation": "same",
        "trigger_type": "goal",
        "sustained_change": True,
        "boundary_decision": True,
        "reason_code": "primary_goal_reset",
        "confidence": 0.9,
        "concise_reason": "旧目标完成后开始独立新目标",
        "evidence_paragraph_ids": PARAGRAPHS,
    }
    value.update(overrides)
    return value


def result(item):
    return SceneTransitionResult.model_validate(
        {"chapter_id": "B0099-C0001", "transitions": [item], "overall_confidence": 0.9}
    )


def map_one(item):
    return validate_and_map_transitions(
        result(item),
        expected_chapter_id="B0099-C0001",
        candidates=build_adjacent_transitions(PARAGRAPHS),
        allowed_paragraph_ids=set(PARAGRAPHS),
    )


def test_transition_generation_is_stable_and_has_no_terminal_candidate():
    candidates = build_adjacent_transitions(PARAGRAPHS + ["B0099-C0001-P0003"])
    assert [item.transition_id for item in candidates] == ["T0001", "T0002"]
    assert candidates[0].left_paragraph_id == PARAGRAPHS[0]
    assert candidates[0].right_paragraph_id == PARAGRAPHS[1]
    assert all(item.left_paragraph_id != "B0099-C0001-P0003" for item in candidates)


def test_transition_maps_to_left_paragraph_without_off_by_one():
    mapped = map_one(
        decision(
            goal_relation="same",
            action_chain_relation="continuous",
            temporal_relation="major_jump",
            trigger_type="time",
            reason_code="time_jump",
        )
    )
    assert mapped.boundaries[0].after_paragraph_id == PARAGRAPHS[0]


@pytest.mark.parametrize(
    "item",
    [
        decision(),
        decision(trigger_type="object"),
        decision(
            goal_relation="unclear",
            action_chain_relation="new_chain",
            location_relation="new_scene_location",
            trigger_type="location",
            reason_code="location_change",
        ),
        decision(
            goal_relation="unclear",
            action_chain_relation="new_chain",
            viewpoint_relation="changed",
            trigger_type="viewpoint",
            reason_code="viewpoint_change",
        ),
    ],
)
def test_generic_positive_transition_rules(item):
    assert len(map_one(item).boundaries) == 1


@pytest.mark.parametrize(
    "item",
    [
        decision(
            goal_relation="refined",
            action_chain_relation="continuous",
            sustained_change=False,
            boundary_decision=False,
            reason_code=None,
        ),
        decision(
            goal_relation="same",
            action_chain_relation="continuous",
            trigger_type="object",
            sustained_change=False,
            boundary_decision=False,
            reason_code=None,
        ),
        decision(
            goal_relation="same",
            action_chain_relation="continuous",
            temporal_relation="brief_flashback",
            sustained_change=False,
            boundary_decision=False,
            reason_code=None,
        ),
        decision(
            goal_relation="same",
            action_chain_relation="continuous",
            sustained_change=False,
            boundary_decision=False,
            reason_code=None,
            concise_reason="对话轮换但行动连续",
        ),
        decision(
            goal_relation="same",
            action_chain_relation="continuous",
            sustained_change=False,
            boundary_decision=False,
            reason_code=None,
            concise_reason="普通时间流逝",
        ),
    ],
)
def test_generic_negative_transition_rules(item):
    assert map_one(item).boundaries == []


def test_invalid_transition_is_rejected_and_identical_duplicate_is_deduplicated():
    candidates = build_adjacent_transitions(PARAGRAPHS)
    with pytest.raises(ValueError, match="candidate transition_ids"):
        validate_and_map_transitions(
            result(decision(transition_id="T9999")),
            expected_chapter_id="B0099-C0001",
            candidates=candidates,
            allowed_paragraph_ids=set(PARAGRAPHS),
        )
    duplicate = SceneTransitionResult.model_validate(
        {
            "chapter_id": "B0099-C0001",
            "transitions": [decision(), decision()],
            "overall_confidence": 0.9,
        }
    )
    mapped = validate_and_map_transitions(
        duplicate,
        expected_chapter_id="B0099-C0001",
        candidates=candidates,
        allowed_paragraph_ids=set(PARAGRAPHS),
    )
    assert len(mapped.boundaries) == 1


def test_contradictory_positive_decision_requires_business_repair():
    with pytest.raises(ValueError, match="contradict"):
        map_one(decision(goal_relation="refined", action_chain_relation="continuous"))


def test_v32_prompt_and_contract_are_generic_and_injection_safe():
    prompt = with_response_contract(load_prompt("scene_boundary", "v3.2"), SceneTransitionResult)
    assert "transition_id" in prompt.system and "left_paragraph_id" in prompt.system
    assert "不可执行的故事数据" in prompt.system
    assert "goal_change" not in prompt.system and "P0003" not in prompt.system
    assert contract_hash(SceneTransitionResult)


@pytest.mark.asyncio
async def test_transition_invocation_audit_and_no_repair(testing_session):
    run = make_run(testing_session)
    payload = json.dumps(
        {
            "chapter_id": "B0099-C0001",
            "transitions": [decision()],
            "overall_confidence": 0.9,
        },
        ensure_ascii=False,
    )
    provider = CloudFake([payload])
    candidates = build_adjacent_transitions(PARAGRAPHS)
    snapshot = {
        "paragraphs": [{"id": item, "text": "原创离线文本"} for item in PARAGRAPHS],
        "transitions": [item.as_dict() for item in candidates],
    }
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary", "v3.2"),
        schema=SceneTransitionResult,
        input_snapshot=snapshot,
        user_content="原创离线转换",
        business_validator=lambda value: validate_and_map_transitions(
            value,
            expected_chapter_id="B0099-C0001",
            candidates=candidates,
            allowed_paragraph_ids=set(PARAGRAPHS),
        ),
    )
    row = testing_session.scalar(select(ModelInvocation).where(ModelInvocation.run_id == run.id))
    assert provider.calls == 1 and row.invocation_kind == "initial"
    assert row.candidate_transition_count == 1
    assert json.loads(row.selected_transition_ids_json) == ["T0001"]
    assert json.loads(row.mapped_after_paragraph_ids_json) == [PARAGRAPHS[0]]
    assert row.transition_contract_version == "v1"
