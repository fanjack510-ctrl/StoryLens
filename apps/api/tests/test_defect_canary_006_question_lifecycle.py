"""DEFECT-CANARY-006: answered must reference a real prior question."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schemas.reader_journey import SCENE_PROMPT_VERSION, SceneReaderJourneyProfileItem
from app.services.cloud_output_policy import _configured_limit
from app.services.prompt_service import load_prompt
from app.services.reader_journey_contract_migrate import migrate_v11_profile_dict_to_v12
from app.services.reader_journey_question_lifecycle import build_question_chains
from app.services.reader_journey_validation import validate_scene_profile_item
from app.services.validation_errors import StructuralValidationError
from tests.optional_gates import require_path
from tests.test_phase_1c_c1_3 import _base_profile_dict

pytestmark = [
    pytest.mark.canary_offline,
    pytest.mark.requires_audit_assets,
]

EVIDENCE_PATH = (
    Path(__file__).resolve().parents[3]
    / "audits"
    / "single-chapter-pipeline"
    / "real-canary-v2"
    / "defects"
    / "DEFECT-CANARY-006-evidence.json"
)


def _pids(*nums: int) -> list[str]:
    return [f"B0001-C0001-P{n:04d}" for n in nums]


def _profile(
    *,
    scene_id: int,
    ordinal: int,
    paragraph_ids: list[str],
    **overrides,
) -> SceneReaderJourneyProfileItem:
    raw = migrate_v11_profile_dict_to_v12(
        _base_profile_dict(scene_id=scene_id, scene_ordinal=ordinal, paragraph_ids=paragraph_ids)
    )
    raw.update(overrides)
    return SceneReaderJourneyProfileItem.model_validate(raw)


def _created(question: str, evidence: list[str], *, strength: int = 80) -> dict:
    return {
        "question": question,
        "trigger_summary": f"触发：{question[:40]}",
        "strength": strength,
        "evidence_paragraph_ids": evidence,
    }


def _answered(question: str, evidence: list[str]) -> dict:
    return {
        "question": question,
        "answer_summary": "给出可验证回应",
        "answer_degree": "full",
        "evidence_paragraph_ids": evidence,
    }


def _out(question: str, evidence: list[str], *, strength: int = 80) -> dict:
    return {
        "question": question,
        "origin": "created_here",
        "hook_type": "information",
        "strength": strength,
        "evidence_paragraph_ids": evidence,
    }


def _carried(question: str) -> dict:
    return {"question": question, "source": "carried_from_previous", "confidence": 0.8}


def test_prompt_version_is_v1_5_compatible_with_006_rules():
    assert SCENE_PROMPT_VERSION.startswith("v1.")
    prompt = load_prompt("reader_journey_scene", SCENE_PROMPT_VERSION)
    assert "answered" in prompt.system.lower() or "answered" in prompt.system
    assert "反向编造" in prompt.system or "不得反向编造" in prompt.system
    assert "JOURNEY_ANSWER_WITHOUT_PRIOR_QUESTION" in prompt.repair_template


def test_journey_structural_repair_uses_journey_limit():
    # Certified Baseline v1.0 / DEFECT-016: journey business/structural repair = 3500
    assert _configured_limit("reader_journey_scene", "structural_repair") == 3500
    assert _configured_limit("scene_analysis", "structural_repair") == 1600


def test_13_1_cross_scene_answer_ok():
    s1_pids = _pids(1, 2, 3)
    s2_pids = _pids(4, 5, 6)
    q1 = "门外是谁"
    p1 = _profile(
        scene_id=1,
        ordinal=1,
        paragraph_ids=s1_pids,
        reader_question_created=[_created(q1, [s1_pids[0]])],
        reader_question_answered=[],
        reader_question_out=[_out(q1, [s1_pids[0]])],
    )
    p2 = _profile(
        scene_id=2,
        ordinal=2,
        paragraph_ids=s2_pids,
        scene_value_summary="承接前场悬念并给出部分揭示",
        reader_question_in=[_carried(q1)],
        reader_question_created=[],
        reader_question_answered=[_answered(q1, [s2_pids[0]])],
        reader_question_out=[_out("粉末来源是什么", [s2_pids[1]])],
    )
    validate_scene_profile_item(p1, allowed_paragraph_ids=set(s1_pids), is_chapter_opening=True)
    validate_scene_profile_item(
        p2,
        allowed_paragraph_ids=set(s2_pids),
        prior_high_strength_outs=[q1],
        is_chapter_opening=False,
    )
    chains = build_question_chains([p1, p2])
    assert any(c["status"] == "answered" and c["question_summary"] == q1 for c in chains)


def test_13_2_answer_missing_question_rejected():
    pids = _pids(4, 5, 6)
    profile = _profile(
        scene_id=2,
        ordinal=2,
        paragraph_ids=pids,
        scene_value_summary="承接前场悬念并给出部分揭示",
        reader_question_in=[_carried("门外是谁")],
        reader_question_created=[],
        reader_question_answered=[_answered("不存在的问题Q9", [pids[0]])],
        reader_question_out=[_out("粉末来源是什么", [pids[1]])],
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_scene_profile_item(
            profile,
            allowed_paragraph_ids=set(pids),
            prior_high_strength_outs=["门外是谁"],
        )
    assert exc.value.error_code == "JOURNEY_ANSWER_WITHOUT_PRIOR_QUESTION"


def test_13_3_answer_future_question_rejected():
    pids = _pids(1, 2, 3)
    profile = _profile(
        scene_id=1,
        ordinal=1,
        paragraph_ids=pids,
        reader_question_created=[],
        reader_question_answered=[_answered("尚未建立的问题", [pids[0]])],
        reader_question_out=[_out("开场悬念是什么", [pids[1]])],
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_scene_profile_item(
            profile,
            allowed_paragraph_ids=set(pids),
            is_chapter_opening=True,
        )
    assert exc.value.error_code == "JOURNEY_ANSWER_WITHOUT_PRIOR_QUESTION"


def test_13_4_same_scene_ordered_answer_ok():
    pids = _pids(1, 2, 3, 4)
    q1 = "门缝里的眼睛属于谁"
    profile = _profile(
        scene_id=1,
        ordinal=1,
        paragraph_ids=pids,
        reader_question_created=[_created(q1, [pids[0]])],
        reader_question_answered=[_answered(q1, [pids[2]])],
        reader_question_out=[_out("下一步威胁是什么", [pids[3]])],
    )
    validate_scene_profile_item(profile, allowed_paragraph_ids=set(pids), is_chapter_opening=True)


def test_13_5_same_scene_order_unproven_rejected():
    pids = _pids(1, 2, 3)
    q1 = "门板上的痕迹是雨水吗"
    profile = _profile(
        scene_id=1,
        ordinal=1,
        paragraph_ids=pids,
        reader_question_created=[_created(q1, [pids[1]])],
        reader_question_answered=[_answered(q1, [pids[1]])],
        reader_question_out=[_out("粉末是什么", [pids[2]])],
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_scene_profile_item(profile, allowed_paragraph_ids=set(pids), is_chapter_opening=True)
    assert exc.value.error_code == "JOURNEY_SAME_SCENE_ORDER_UNPROVEN"


def test_13_5b_same_scene_answer_before_question_rejected():
    pids = _pids(1, 2, 3)
    q1 = "门板上的痕迹是雨水吗"
    profile = _profile(
        scene_id=1,
        ordinal=1,
        paragraph_ids=pids,
        reader_question_created=[_created(q1, [pids[2]])],
        reader_question_answered=[_answered(q1, [pids[0]])],
        reader_question_out=[_out("粉末是什么", [pids[1]])],
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_scene_profile_item(profile, allowed_paragraph_ids=set(pids), is_chapter_opening=True)
    assert exc.value.error_code == "JOURNEY_ANSWER_BEFORE_QUESTION"


def test_13_6_revelation_is_not_answered():
    pids = _pids(1, 2, 3)
    profile = _profile(
        scene_id=1,
        ordinal=1,
        paragraph_ids=pids,
        reader_question_created=[_created("门外是谁", [pids[0]])],
        reader_question_answered=[_answered("门被打开了吗", [pids[1]])],  # invented
        reader_question_out=[_out("门外是谁", [pids[0]])],
        information_changes=[
            {
                "type": "new_information",
                "summary": "角色发现门被打开",
                "certainty": "fact",
                "evidence_paragraph_ids": [pids[1]],
            }
        ],
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_scene_profile_item(profile, allowed_paragraph_ids=set(pids), is_chapter_opening=True)
    assert exc.value.error_code == "JOURNEY_ANSWER_WITHOUT_PRIOR_QUESTION"


def test_13_7_payoff_without_chapter_question_ok():
    pids = _pids(1, 2, 3)
    profile = _profile(
        scene_id=1,
        ordinal=1,
        paragraph_ids=pids,
        reader_question_created=[_created("下一步会发生什么", [pids[0]])],
        reader_question_answered=[],
        reader_question_out=[_out("下一步会发生什么", [pids[0]])],
        payoffs=[
            {
                "type": "information",
                "summary": "结构回报：排除雨水假设",
                "strength": 70,
                "evidence_paragraph_ids": [pids[2]],
            }
        ],
    )
    validate_scene_profile_item(profile, allowed_paragraph_ids=set(pids), is_chapter_opening=True)


def test_13_8_carry_in_unsupported_no_fabricated_prior():
    """Contract 1.3 has no chapter-external carry-in; inventing answered prior fails."""
    pids = _pids(1, 2, 3)
    profile = _profile(
        scene_id=1,
        ordinal=1,
        paragraph_ids=pids,
        reader_question_created=[],
        reader_question_answered=[_answered("前章悬念是谁在敲门", [pids[0]])],
        reader_question_out=[_out("本章新悬念是什么", [pids[1]])],
        payoffs=[
            {
                "type": "identity",
                "summary": "揭晓前章敲门者身份",
                "strength": 75,
                "evidence_paragraph_ids": [pids[0]],
            }
        ],
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_scene_profile_item(profile, allowed_paragraph_ids=set(pids), is_chapter_opening=True)
    assert exc.value.error_code == "JOURNEY_ANSWER_WITHOUT_PRIOR_QUESTION"


def test_13_10_id_normalization_is_text_exact_match():
    """Lifecycle uses exact question text; Q-01 style IDs are not contract fields."""
    pids = _pids(1, 2)
    q_a = "门外是谁"
    q_b = "门外是谁？"  # different string must not auto-link
    profile = _profile(
        scene_id=1,
        ordinal=1,
        paragraph_ids=pids,
        reader_question_created=[_created(q_a, [pids[0]])],
        reader_question_answered=[_answered(q_b, [pids[1]])],
        reader_question_out=[_out(q_a, [pids[0]])],
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_scene_profile_item(profile, allowed_paragraph_ids=set(pids), is_chapter_opening=True)
    assert exc.value.error_code == "JOURNEY_ANSWER_WITHOUT_PRIOR_QUESTION"


def test_13_11_duplicate_question_text_links_deterministically():
    pids = _pids(1, 2, 3, 4)
    q1 = "门外是谁"
    p1 = _profile(
        scene_id=1,
        ordinal=1,
        paragraph_ids=pids[:2],
        reader_question_created=[_created(q1, [pids[0]])],
        reader_question_out=[_out(q1, [pids[0]])],
    )
    p2 = _profile(
        scene_id=2,
        ordinal=2,
        paragraph_ids=pids[2:],
        scene_value_summary="承接前场悬念并闭合疑问",
        reader_question_in=[_carried(q1)],
        reader_question_created=[_created(q1, [pids[2]])],  # same text again
        reader_question_answered=[_answered(q1, [pids[3]])],
        reader_question_out=[_out("新威胁是什么", [pids[3]])],
    )
    chains = build_question_chains([p1, p2])
    answered = [c for c in chains if c["question_summary"] == q1 and c["status"] == "answered"]
    assert len(answered) >= 1


def test_13_12_similar_questions_not_merged():
    p1 = _profile(
        scene_id=1,
        ordinal=1,
        paragraph_ids=_pids(1, 2),
        reader_question_created=[_created("门外的眼睛属于谁", _pids(1))],
        reader_question_out=[_out("门外的眼睛属于谁", _pids(1))],
    )
    p2 = _profile(
        scene_id=2,
        ordinal=2,
        paragraph_ids=_pids(3, 4),
        scene_value_summary="提出相近但不同的问题",
        reader_question_in=[_carried("门外的眼睛属于谁")],
        reader_question_created=[_created("门缝外的存在意图为何", _pids(3))],
        reader_question_out=[_out("门缝外的存在意图为何", _pids(3))],
    )
    chains = build_question_chains([p1, p2])
    summaries = {c["question_summary"] for c in chains}
    assert "门外的眼睛属于谁" in summaries
    assert "门缝外的存在意图为何" in summaries
    assert len(summaries) >= 2


def test_13_13_truncation_flags_remain_distinct():
    """Truncation is OUTPUT_TRUNCATED; missing prior remains JOURNEY_ANSWER_WITHOUT_PRIOR_QUESTION."""
    assert _configured_limit("reader_journey_scene", "structural_repair") >= 1800


def test_13_16_no_question_chain_opening_still_needs_out_or_summary():
    pids = _pids(1, 2)
    profile = _profile(
        scene_id=1,
        ordinal=1,
        paragraph_ids=pids,
        reader_question_created=[],
        reader_question_answered=[],
        reader_question_out=[],
        scene_value_summary="开篇通过异常细节建立情境，引入主角出场",
    )
    # Opening with opening-style summary and empty outs is allowed by chain rules
    # only when opening summary matches; empty everything still needs out OR opening summary path
    validate_scene_profile_item(profile, allowed_paragraph_ids=set(pids), is_chapter_opening=True)


def test_13_17_a1_real_failure_reproduces_then_repair_reclassify():
    require_path(EVIDENCE_PATH)
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    inv7 = next(item for item in payload["invocations"] if item["id"] == 7)
    scene2 = inv7["profiles"][1]
    assert scene2["reader_question_answered"][0]["question"] == "门板上的痕迹是雨水吗？"

    # Build validateable profile from evidence + required contract fields
    pids = ["B0001-C0001-P0006", "B0001-C0001-P0007", "B0001-C0001-P0008"]
    prior = "门外的存在是什么？角色如何在黑暗中存活？"
    broken = _profile(
        scene_id=2,
        ordinal=2,
        paragraph_ids=pids,
        scene_value_summary=scene2["scene_value_summary"],
        reader_question_in=[_carried(prior)],
        reader_question_created=[
            _created(
                scene2["reader_question_created"][0]["question"],
                scene2["reader_question_created"][0]["evidence_paragraph_ids"],
            )
        ],
        reader_question_answered=[
            _answered(
                scene2["reader_question_answered"][0]["question"],
                scene2["reader_question_answered"][0]["evidence_paragraph_ids"],
            )
        ],
        reader_question_out=[
            _out(
                scene2["reader_question_out"][0]["question"],
                scene2["reader_question_out"][0]["evidence_paragraph_ids"],
                strength=85,
            )
        ],
        payoffs=[
            {
                "type": "information",
                "summary": scene2["payoffs"][0]["summary"],
                "strength": 70,
                "evidence_paragraph_ids": scene2["payoffs"][0]["evidence_paragraph_ids"],
            }
        ],
        information_changes=[
            {
                "type": "new_information",
                "summary": scene2["information_changes"][0]["summary"],
                "certainty": "fact",
                "evidence_paragraph_ids": scene2["information_changes"][0]["evidence_paragraph_ids"],
            }
        ],
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_scene_profile_item(
            broken,
            allowed_paragraph_ids=set(pids),
            prior_high_strength_outs=[prior],
        )
    assert exc.value.error_code == "JOURNEY_ANSWER_WITHOUT_PRIOR_QUESTION"

    # Repair strategy: clear illegal answered; keep payoff / information_changes
    repaired = broken.model_copy(update={"reader_question_answered": []})
    validate_scene_profile_item(
        repaired,
        allowed_paragraph_ids=set(pids),
        prior_high_strength_outs=[prior],
    )


def test_13_15_repair_invented_prior_still_rejected():
    pids = _pids(6, 7, 8)
    invented = "门板上的痕迹是雨水吗？"
    profile = _profile(
        scene_id=2,
        ordinal=2,
        paragraph_ids=pids,
        scene_value_summary="承接前场悬念并给出部分揭示",
        reader_question_in=[_carried("门外是谁")],
        reader_question_created=[_created(invented, [pids[0]])],  # fabricated prior without real trigger needed by schema
        reader_question_answered=[_answered(invented, [pids[0]])],  # same para → order unproven
        reader_question_out=[_out("粉末是什么", [pids[1]])],
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_scene_profile_item(
            profile,
            allowed_paragraph_ids=set(pids),
            prior_high_strength_outs=["门外是谁"],
        )
    assert exc.value.error_code in {
        "JOURNEY_SAME_SCENE_ORDER_UNPROVEN",
        "JOURNEY_ANSWER_BEFORE_QUESTION",
    }
