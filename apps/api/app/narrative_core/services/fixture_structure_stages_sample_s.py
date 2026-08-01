"""Public-side Sample S structure stages V2 fixture (TEST DATA — not production analysis)."""

from __future__ import annotations

from typing import Any, Literal, Sequence

FixtureStructureMode = Literal[
    "multi_stage",
    "non_three_act",
    "variable_count",
    "tp_empty",
    "insufficient",
    "failed_empty",
]


def _claim(value: str, citation_ids: Sequence[str], *, confidence: float = 0.7) -> dict[str, Any]:
    return {
        "value": value,
        "status": "observed",
        "citation_ids": list(citation_ids),
        "confidence": confidence,
    }


def _boundary(citation_ids: Sequence[str]) -> dict[str, Any]:
    return {"citation_ids": list(citation_ids), "note": None, "value": None}


def _stage(
    *,
    ref: str,
    order: int,
    title: str,
    stage_type: str,
    summary: str,
    start_cids: Sequence[str],
    end_cids: Sequence[str],
    narrative_function: str,
    tp_refs: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "local_stage_ref": ref,
        "order_index": order,
        "stage_type": stage_type,
        "title": title,
        "summary": _claim(summary, start_cids),
        "start_boundary": _boundary(start_cids),
        "end_boundary": _boundary(end_cids),
        "supporting_citation_ids": [],
        "related_turning_point_refs": list(tp_refs),
        "narrative_function": narrative_function,
        "confidence": 0.65,
    }


def build_fixture_structure_stages_v2(
    *,
    citation_ids: Sequence[str],
    mode: FixtureStructureMode = "multi_stage",
    context_capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a StructureStagesResultV2 wire dict bound to catalog citation_ids.

    Marked as fixture/test data via limitations and result_origin downstream.
    """

    cids = [str(x) for x in citation_ids if str(x).strip()]
    if mode == "insufficient":
        return {
            "contract_version": "v2",
            "evidence_contract_version": "v2",
            "coverage_scope": "insufficient",
            "stages": [],
            "turning_points": [],
            "analysis_confidence": 0.0,
            "overall_confidence": 0.0,
            "limitations": [
                "FIXTURE_TEST_DATA",
                "context insufficient for local stages",
                "STRUCTURE_EMPTY_OBSERVATION_PERMITTED",
            ],
            "context_capabilities": dict(context_capabilities or {}),
            "empty_reason": "STRUCTURE_EMPTY_OBSERVATION_PERMITTED",
        }

    if mode == "failed_empty":
        # Illegal empty under non-insufficient binding — for fail-closed tests.
        return {
            "contract_version": "v2",
            "evidence_contract_version": "v2",
            "coverage_scope": "full_selected_range",
            "stages": [],
            "turning_points": [],
            "analysis_confidence": 0.0,
            "limitations": ["FIXTURE_TEST_DATA"],
            "context_capabilities": dict(context_capabilities or {}),
        }

    if len(cids) < 2:
        raise ValueError("fixture structure stages require ≥2 citation_ids")

    c1, c2 = cids[0], cids[1]
    c3 = cids[2] if len(cids) > 2 else c2
    c4 = cids[3] if len(cids) > 3 else c3

    if mode == "non_three_act":
        stages = [
            _stage(
                ref="S1",
                order=0,
                title="开端线索",
                stage_type="setup",
                summary="【测试数据】开端建立调查动机。",
                start_cids=[c1],
                end_cids=[c2],
                narrative_function="establish stakes",
            ),
            _stage(
                ref="S2",
                order=1,
                title="规则碰撞",
                stage_type="escalation",
                summary="【测试数据】冲突围绕隐藏规则升级。",
                start_cids=[c2],
                end_cids=[c3],
                narrative_function="raise pressure",
                tp_refs=["TP1"],
            ),
            _stage(
                ref="S3",
                order=2,
                title="真相逼近",
                stage_type="reveal",
                summary="【测试数据】信息回收逼近核心问题。",
                start_cids=[c3],
                end_cids=[c4],
                narrative_function="narrow mystery",
                tp_refs=["TP1"],
            ),
            _stage(
                ref="S4",
                order=3,
                title="临时收束",
                stage_type="resolution",
                summary="【测试数据】阶段收束但不强制三幕模板。",
                start_cids=[c4],
                end_cids=[c4],
                narrative_function="temporary closure",
            ),
        ]
        turning_points = [
            {
                "local_turning_point_ref": "TP1",
                "order_index": 0,
                "turning_point_type": "reveal",
                "title": "规则缺口暴露",
                "description": _claim("【测试数据】规则缺口改变调查方向。", [c2], confidence=0.55),
                "before_state": "封锁",
                "after_state": "突破",
                "impact": "转向源头",
                "citation_ids": [c2],
                "related_stage_refs": ["S2", "S3"],
                "confidence": 0.55,
            }
        ]
        coverage = "full_selected_range"
    elif mode == "variable_count":
        stages = [
            _stage(
                ref="S1",
                order=0,
                title="单阶段全跨度",
                stage_type="arc",
                summary="【测试数据】可变阶段数：仅一个合法阶段。",
                start_cids=[c1],
                end_cids=[c4],
                narrative_function="span selection",
            )
        ]
        turning_points = []
        coverage = "full_selected_range"
    elif mode == "tp_empty":
        stages = [
            _stage(
                ref="S1",
                order=0,
                title="阶段一",
                stage_type="rising",
                summary="【测试数据】有效阶段，转折点为空。",
                start_cids=[c1],
                end_cids=[c2],
                narrative_function="advance",
            ),
            _stage(
                ref="S2",
                order=1,
                title="阶段二",
                stage_type="climax",
                summary="【测试数据】第二阶段，无转折点。",
                start_cids=[c3],
                end_cids=[c4],
                narrative_function="resolve",
            ),
        ]
        turning_points = []
        coverage = "full_selected_range"
    else:  # multi_stage
        stages = [
            _stage(
                ref="S1",
                order=0,
                title="Stage S1",
                stage_type="rising",
                summary="【测试数据】合成结构阶段 S1 摘要",
                start_cids=[c1],
                end_cids=[c2],
                narrative_function="advance plot",
                tp_refs=["TP1"],
            ),
            _stage(
                ref="S2",
                order=1,
                title="Stage S2",
                stage_type="climax",
                summary="【测试数据】合成结构阶段 S2 摘要",
                start_cids=[c3],
                end_cids=[c4],
                narrative_function="resolve tension",
                tp_refs=["TP1"],
            ),
        ]
        turning_points = [
            {
                "local_turning_point_ref": "TP1",
                "order_index": 0,
                "turning_point_type": "reveal",
                "title": "TP TP1",
                "description": _claim("【测试数据】合成转折点 TP1 描述", [c2], confidence=0.5),
                "before_state": "before",
                "after_state": "after",
                "impact": "impact",
                "citation_ids": [c2],
                "related_stage_refs": ["S1", "S2"],
                "confidence": 0.5,
            }
        ]
        coverage = "full_selected_range"

    return {
        "contract_version": "v2",
        "evidence_contract_version": "v2",
        "coverage_scope": coverage,
        "stages": stages,
        "turning_points": turning_points,
        "analysis_confidence": 0.8,
        "overall_confidence": 0.8,
        "limitations": ["FIXTURE_TEST_DATA"],
        "context_capabilities": dict(context_capabilities or {}),
    }
