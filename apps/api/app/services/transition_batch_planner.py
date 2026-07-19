import json
import math
from dataclasses import dataclass

from app.services.scene_transitions import AdjacentTransition

OUTPUT_LIMIT = 768
TARGET_TOKENS = math.floor(OUTPUT_LIMIT * 0.72)


def conservative_token_estimate(value: object) -> int:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    ascii_count = sum(ord(char) < 128 for char in text)
    non_ascii_count = len(text) - ascii_count
    # Conservative fallback for the configured provider: ASCII JSON averages
    # no better than four characters per token; CJK is counted one-for-one.
    return math.ceil(ascii_count / 4 + non_ascii_count) + 8


def worst_case_compact_payload(transition_ids: list[str]) -> dict[str, object]:
    decisions = [
        {
            "transition_id": item,
            "boundary": True,
            "goal_relation": "completed_then_new",
            "action_chain_relation": "new_chain",
            "temporal_relation": "major_jump",
            "location_relation": "new_scene_location",
            "viewpoint_relation": "changed",
            "trigger_type": "object",
            "confidence": 1.0,
        }
        for item in transition_ids
    ]
    details = [
        {
            "transition_id": item,
            "reason_code": "primary_goal_reset",
            "previous_primary_goal": "完成旧的持续目标",
            "next_primary_goal": "开始全新的持续目标",
            "concise_reason": "旧目标结束并开始独立行动链",
            "evidence_paragraph_ids": ["P0001", "P0002"],
        }
        for item in transition_ids
    ]
    return {"contract_version": "3.3", "decisions": decisions, "selected_details": details}


def worst_case_candidate_payload(transition_ids: list[str]) -> dict[str, object]:
    return {
        "contract_version": "3.5",
        "decisions": [
            {
                "transition_id": item,
                "boundary_candidate": True,
                "goal_relation": "completed_then_new",
                "action_chain_relation": "new_chain",
                "temporal_relation": "major_jump",
                "location_relation": "new_scene_location",
                "viewpoint_relation": "changed",
                "trigger_type": "explicit_separator",
                "confidence": 1.0,
            }
            for item in transition_ids
        ],
    }


@dataclass(frozen=True)
class TransitionBatch:
    owned_transition_ids: tuple[str, ...]
    context_paragraph_ids: tuple[str, ...]
    worst_case_output_tokens: int


def plan_transition_batches(
    candidates: list[AdjacentTransition], *, contract_version: str = "3.3"
) -> list[TransitionBatch]:
    payload_builder = (
        worst_case_candidate_payload
        if contract_version == "3.5"
        else worst_case_compact_payload
    )
    batches: list[TransitionBatch] = []
    start = 0
    while start < len(candidates):
        end = start
        while end < len(candidates):
            ids = [item.transition_id for item in candidates[start : end + 1]]
            if conservative_token_estimate(payload_builder(ids)) > TARGET_TOKENS:
                break
            end += 1
        if end == start:
            raise ValueError("one compact transition exceeds the safe output budget")
        owned = candidates[start:end]
        context = [owned[0].left_paragraph_id]
        context.extend(item.right_paragraph_id for item in owned)
        batches.append(
            TransitionBatch(
                owned_transition_ids=tuple(item.transition_id for item in owned),
                context_paragraph_ids=tuple(dict.fromkeys(context)),
                worst_case_output_tokens=conservative_token_estimate(
                    payload_builder([item.transition_id for item in owned])
                ),
            )
        )
        start = end
    return batches
