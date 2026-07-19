# -*- coding: utf-8 -*-
"""DEFECT-CANARY-001: short-scene key_actions empty-array contract tests."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.schemas.scene import EvidenceField, SceneAnalysisResult
from app.services.prompt_service import load_prompt
from app.services.scene_pipeline import (
    normalize_scene_analysis_result,
    validate_scene_analysis,
)
from app.services.structured_output import extract_json_object


def _field(summary: str, pids: list[str]) -> EvidenceField:
    return EvidenceField(summary=summary, evidence_paragraph_ids=list(pids))


def _base(
    scene_id: str,
    pids: list[str],
    *,
    key_actions: list[EvidenceField] | None = None,
    function_tags: list[str] | None = None,
) -> SceneAnalysisResult:
    return SceneAnalysisResult(
        scene_id=scene_id,
        entry_state=_field("进入状态", pids[:1]),
        goal=_field("场景目标", pids[:1]),
        obstacle=_field("阻碍", pids[:1] if len(pids) == 1 else []),
        key_actions=[] if key_actions is None else key_actions,
        turning_point=_field("", []),
        outcome=_field("结束状态", pids[:1]),
        unresolved_question=_field("悬念", pids[:1]),
        function_tags=function_tags or ["事件推进"],  # type: ignore[arg-type]
        confidence=0.8,
    )


def test_short_dialogue_empty_key_actions_allowed() -> None:
    sid = "B0001-C0001-S0001"
    pids = ["B0001-C0001-P0001", "B0001-C0001-P0002"]
    result = _base(sid, pids, key_actions=[], function_tags=["悬念设置", "人物塑造"])
    validate_scene_analysis(result, sid, set(pids), True)


def test_emotion_push_empty_key_actions_allowed() -> None:
    sid = "B0001-C0001-S0002"
    pids = ["B0001-C0001-P0003"]
    result = _base(sid, pids, key_actions=[], function_tags=["人物塑造", "过渡"])
    validate_scene_analysis(result, sid, set(pids), True)


def test_info_explain_empty_key_actions_allowed() -> None:
    sid = "B0001-C0001-S0003"
    pids = ["B0001-C0001-P0004", "B0001-C0001-P0005"]
    result = _base(sid, pids, key_actions=[], function_tags=["信息揭示", "过渡"])
    validate_scene_analysis(result, sid, set(pids), True)


def test_evidenced_key_action_passes() -> None:
    sid = "B0001-C0001-S0004"
    pids = ["B0001-C0001-P0010", "B0001-C0001-P0011"]
    result = _base(
        sid,
        pids,
        key_actions=[_field("主角关上房门", ["B0001-C0001-P0010"])],
    )
    result.entry_state = _field("门半掩着", ["B0001-C0001-P0010"])
    result.goal = _field("隔绝门外声响", ["B0001-C0001-P0010"])
    result.obstacle = _field("门轴生锈", ["B0001-C0001-P0011"])
    result.outcome = _field("门外安静下来", ["B0001-C0001-P0011"])
    result.unresolved_question = _field("门外是谁", ["B0001-C0001-P0011"])
    validate_scene_analysis(result, sid, set(pids), True)


def test_key_action_with_empty_evidence_rejected() -> None:
    sid = "B0001-C0001-S0005"
    pids = ["B0001-C0001-P0020"]
    result = _base(
        sid,
        pids,
        key_actions=[_field("主角转身离开", [])],
    )
    with pytest.raises(ValueError, match="key_actions 每项必须包含"):
        validate_scene_analysis(result, sid, set(pids), True)


def test_key_action_with_missing_paragraph_rejected() -> None:
    sid = "B0001-C0001-S0006"
    pids = ["B0001-C0001-P0030"]
    result = _base(
        sid,
        pids,
        key_actions=[_field("主角推开门", ["B0001-C0001-P9999"])],
    )
    with pytest.raises(ValueError, match="证据段落不存在"):
        validate_scene_analysis(result, sid, set(pids), True)


def test_key_action_evidence_from_other_scene_rejected() -> None:
    sid = "B0001-C0001-S0007"
    allowed = {"B0001-C0001-P0040", "B0001-C0001-P0041"}
    result = _base(
        sid,
        ["B0001-C0001-P0040"],
        key_actions=[_field("他后退半步", ["B0001-C0001-P0100"])],
    )
    with pytest.raises(ValueError, match="证据段落不存在"):
        validate_scene_analysis(result, sid, allowed, True)


def test_fabricated_action_without_evidence_rejected() -> None:
    """Invented action with empty evidence must not enter succeeded results."""
    sid = "B0001-C0001-S0008"
    pids = ["B0001-C0001-P0050"]
    result = _base(
        sid,
        pids,
        key_actions=[_field("主角召唤神龙摧毁城市", [])],
    )
    with pytest.raises(ValueError, match="key_actions 每项必须包含"):
        validate_scene_analysis(result, sid, set(pids), True)


def test_missing_key_actions_defaults_to_empty_not_fabricated() -> None:
    payload = {
        "scene_id": "B0001-C0001-S0009",
        "entry_state": {"summary": "进入", "evidence_paragraph_ids": ["B0001-C0001-P0060"]},
        "goal": {"summary": "目标", "evidence_paragraph_ids": ["B0001-C0001-P0060"]},
        "obstacle": {"summary": "", "evidence_paragraph_ids": []},
        "turning_point": {"summary": "", "evidence_paragraph_ids": []},
        "outcome": {"summary": "结果", "evidence_paragraph_ids": ["B0001-C0001-P0060"]},
        "unresolved_question": {"summary": "", "evidence_paragraph_ids": []},
        "function_tags": ["过渡"],
        "confidence": 0.5,
    }
    result = SceneAnalysisResult.model_validate(payload)
    assert result.key_actions == []
    normalized = normalize_scene_analysis_result(result, {"B0001-C0001-P0060"})
    assert normalized.key_actions == []
    validate_scene_analysis(normalized, "B0001-C0001-S0009", {"B0001-C0001-P0060"}, True)


def test_null_key_actions_rejected_by_schema() -> None:
    payload = {
        "scene_id": "B0001-C0001-S0010",
        "entry_state": {"summary": "进入", "evidence_paragraph_ids": ["B0001-C0001-P0070"]},
        "goal": {"summary": "目标", "evidence_paragraph_ids": ["B0001-C0001-P0070"]},
        "obstacle": {"summary": "", "evidence_paragraph_ids": []},
        "key_actions": None,
        "turning_point": {"summary": "", "evidence_paragraph_ids": []},
        "outcome": {"summary": "结果", "evidence_paragraph_ids": ["B0001-C0001-P0070"]},
        "unresolved_question": {"summary": "", "evidence_paragraph_ids": []},
        "function_tags": ["过渡"],
        "confidence": 0.5,
    }
    with pytest.raises(ValidationError):
        SceneAnalysisResult.model_validate(payload)


def test_key_actions_wrong_type_rejected() -> None:
    payload = {
        "scene_id": "B0001-C0001-S0011",
        "entry_state": {"summary": "进入", "evidence_paragraph_ids": ["B0001-C0001-P0080"]},
        "goal": {"summary": "目标", "evidence_paragraph_ids": ["B0001-C0001-P0080"]},
        "obstacle": {"summary": "", "evidence_paragraph_ids": []},
        "key_actions": "not-a-list",
        "turning_point": {"summary": "", "evidence_paragraph_ids": []},
        "outcome": {"summary": "结果", "evidence_paragraph_ids": ["B0001-C0001-P0080"]},
        "unresolved_question": {"summary": "", "evidence_paragraph_ids": []},
        "function_tags": ["过渡"],
        "confidence": 0.5,
    }
    with pytest.raises(ValidationError):
        SceneAnalysisResult.model_validate(payload)


def test_markdown_wrapped_json_same_validation() -> None:
    sid = "B0001-C0001-S0012"
    pid = "B0001-C0001-P0090"
    inner = {
        "scene_id": sid,
        "entry_state": {"summary": "进入", "evidence_paragraph_ids": [pid]},
        "goal": {"summary": "目标", "evidence_paragraph_ids": [pid]},
        "obstacle": {"summary": "", "evidence_paragraph_ids": []},
        "key_actions": [],
        "turning_point": {"summary": "", "evidence_paragraph_ids": []},
        "outcome": {"summary": "结果", "evidence_paragraph_ids": [pid]},
        "unresolved_question": {"summary": "", "evidence_paragraph_ids": []},
        "function_tags": ["过渡"],
        "confidence": 0.6,
    }
    wrapped = "```json\n" + json.dumps(inner, ensure_ascii=False) + "\n```"
    parsed = extract_json_object(wrapped)
    result = SceneAnalysisResult.model_validate_json(parsed)
    validate_scene_analysis(result, sid, {pid}, True)


def test_retry_legal_empty_key_actions_succeeds() -> None:
    sid = "B0001-C0001-S0013"
    pids = ["B0001-C0001-P0110"]
    result = _base(sid, pids, key_actions=[])
    validate_scene_analysis(result, sid, set(pids), True)


def test_retry_unevidenced_action_fails() -> None:
    sid = "B0001-C0001-S0014"
    pids = ["B0001-C0001-P0120"]
    result = _base(
        sid,
        pids,
        key_actions=[_field("编造的冲刺", [])],
    )
    with pytest.raises(ValueError, match="key_actions 每项必须包含"):
        validate_scene_analysis(result, sid, set(pids), True)


def test_nonempty_key_actions_regression_still_passes() -> None:
    sid = "B0001-C0001-S0015"
    pid = "B0001-C0001-P0130"
    result = SceneAnalysisResult(
        scene_id=sid,
        entry_state=_field("进入", [pid]),
        goal=_field("目标", [pid]),
        obstacle=_field("阻碍", [pid]),
        key_actions=[_field("行动", [pid])],
        turning_point=_field("", []),
        outcome=_field("结果", [pid]),
        unresolved_question=_field("悬念", [pid]),
        function_tags=["悬念设置"],
        confidence=0.9,
    )
    validate_scene_analysis(result, sid, {pid}, True)


def test_illegal_evidence_still_rejected() -> None:
    sid = "B0001-C0001-S0016"
    pid = "B0001-C0001-P0140"
    result = _base(
        sid,
        [pid],
        key_actions=[_field("行动", ["B0001-C0001-P9999"])],
    )
    with pytest.raises(ValueError, match="证据段落不存在"):
        validate_scene_analysis(result, sid, {pid}, True)


def test_prompt_v32_documents_empty_key_actions() -> None:
    prompt = load_prompt("scene_analysis", "v3.2")
    assert "不得编造动作" in prompt.system
    assert "保持key_actions=[]是合法的" in prompt.repair_template
    assert "无明确动作" in prompt.system


def test_normalize_does_not_fabricate_key_actions() -> None:
    sid = "B0001-C0001-S0017"
    pid = "B0001-C0001-P0150"
    result = _base(sid, [pid], key_actions=[])
    normalized = normalize_scene_analysis_result(result, {pid})
    assert normalized.key_actions == []
