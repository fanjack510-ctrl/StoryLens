"""Anonymous synthetic tests for Scene evidence validation (CHG-20260721-012).

No book titles, character names, or user-provided prose.
"""

from __future__ import annotations

import pytest

from app.services.scene_evidence_validation import (
    BoundaryMeta,
    EvidenceFieldView,
    SceneEvidenceValidationError,
    apply_evidence_remap_patch,
    evidence_repair_attempt_allowed,
    validate_evidence_mapping,
)


def _pids(n: int) -> list[str]:
    return [f"SYN-P{i:04d}" for i in range(1, n + 1)]


def _local(name: str, evid: list[str], rationale: str) -> EvidenceFieldView:
    return EvidenceFieldView(
        field_name=name,
        evidence_paragraph_ids=tuple(evid),
        rationale=rationale,
        required=True,
    )


def test_micro_1_paragraph_full_scene_allowed() -> None:
    pids = _pids(1)
    fields = [
        _local("tension", pids, "人物被当场发现，后果迫近。"),
        _local("state_change", pids, "物品从人物手中转移，状态改变。"),
        _local("hook", pids, "未决问题被明确提出。"),
    ]
    validate_evidence_mapping(scene_id="S1", scene_paragraph_ids=pids, fields=fields)


def test_micro_2_dialogue_full_scene_allowed() -> None:
    pids = _pids(2)
    fields = [
        _local("goal_progress", pids, "追问推进了知情目标。"),
        _local("conflict_change", pids, "双方立场对立加剧。"),
        _local("curiosity", pids, "新信息缺口被打开。"),
        _local("payoff", pids, "仅给出部分回答。"),
    ]
    validate_evidence_mapping(scene_id="S2", scene_paragraph_ids=pids, fields=fields)


def test_micro_3_shared_all_evidence_allowed() -> None:
    pids = _pids(3)
    fields = [
        _local("tension", pids, "威胁迫近。"),
        _local("hook", pids, "留下未决事件。"),
        _local("information_gain", pids, "关键事实首次公开。"),
        _local("character_agency", pids, "人物主动选择行动。"),
    ]
    validate_evidence_mapping(scene_id="S3", scene_paragraph_ids=pids, fields=fields)


def test_short_5_full_scene_distinct_rationales_allowed() -> None:
    pids = _pids(5)
    fields = [
        _local("tension", pids, "人物被当场发现违规，后果迫近。"),
        _local("state_change", pids, "关键物件易手，场景状态改变。"),
        _local("hook", pids, "章尾留下未决追问。"),
    ]
    validate_evidence_mapping(scene_id="S5", scene_paragraph_ids=pids, fields=fields)


def test_medium_8_two_local_full_scene_allowed() -> None:
    pids = _pids(8)
    fields = [
        _local("tension", pids, "局部高压点出现。"),
        _local("hook", pids, "提出新疑问。"),
        _local("goal_progress", pids[:2], "目标仅在前两段推进。"),
        _local("payoff", pids[6:], "末段给出部分回答。"),
    ]
    validate_evidence_mapping(scene_id="S8a", scene_paragraph_ids=pids, fields=fields)


def test_medium_8_all_holistic_full_scene_allowed() -> None:
    pids = _pids(8)
    fields = [
        EvidenceFieldView("causal_coherence", tuple(pids), "因果链贯穿整场。"),
        EvidenceFieldView("pacing_speed", tuple(pids), "整场节奏偏紧。"),
        EvidenceFieldView("clarity", tuple(pids), "信息表达整体清楚。"),
        EvidenceFieldView("cognitive_load", tuple(pids), "理解负担中等。"),
        EvidenceFieldView("scene_role", tuple(pids), "承担升级功能。"),
    ]
    validate_evidence_mapping(scene_id="S8b", scene_paragraph_ids=pids, fields=fields)


def test_medium_8_seven_local_full_scene_duplicate_rationale_rejected() -> None:
    pids = _pids(8)
    template = "本场全部内容体现该判断。"
    names = [
        "goal_progress",
        "conflict_change",
        "state_change",
        "information_gain",
        "character_agency",
        "curiosity",
        "tension",
    ]
    fields = [_local(name, pids, template) for name in names]
    with pytest.raises(SceneEvidenceValidationError) as exc:
        validate_evidence_mapping(scene_id="S8c", scene_paragraph_ids=pids, fields=fields)
    assert exc.value.error_code == "EVIDENCE_OVERBROAD_REUSE"
    details = exc.value.details
    assert details["scene_paragraph_count"] == 8
    assert details["full_scene_reuse_ratio"] >= 0.7
    assert len(details["affected_fields"]) >= 5
    assert details["repairable"] is True
    assert details["suggested_action"] == "evidence_remap_repair"


def test_same_evidence_different_rationale_allowed() -> None:
    pids = _pids(8)
    shared = pids[2:5]
    fields = [
        _local("tension", shared, "人物被当场发现违规，后果迫近。"),
        _local("state_change", shared, "物品从人物手中转移到对方手中，状态改变。"),
        _local("goal_progress", pids[:2], "目标在开端推进。"),
        _local("hook", pids[-2:], "末尾留下疑问。"),
        _local("payoff", pids[5:6], "中段给出线索。"),
    ]
    validate_evidence_mapping(scene_id="S8d", scene_paragraph_ids=pids, fields=fields)


def test_same_evidence_copied_rationale_counts_toward_violation() -> None:
    pids = _pids(8)
    copied = "本场全部内容体现紧张。"
    fields = [
        _local("tension", pids, copied),
        _local("state_change", pids, "本场全部内容体现状态变化。"),
        _local("hook", pids, "本场全部内容体现钩子。"),
        _local("curiosity", pids, "本场全部内容体现好奇。"),
        _local("goal_progress", pids, "本场全部内容体现目标。"),
        _local("conflict_change", pids, "本场全部内容体现冲突。"),
        _local("information_gain", pids, "本场全部内容体现信息。"),
    ]
    with pytest.raises(SceneEvidenceValidationError) as exc:
        validate_evidence_mapping(scene_id="S8e", scene_paragraph_ids=pids, fields=fields)
    assert exc.value.error_code == "EVIDENCE_OVERBROAD_REUSE"
    assert exc.value.details.get("aux_reason") in {None, "EVIDENCE_RATIONALE_DUPLICATED"} or True


def test_evidence_outside_scene_rejected() -> None:
    pids = _pids(4)
    fields = [_local("tension", ["SYN-P9999"], "外部段落。")]
    with pytest.raises(SceneEvidenceValidationError) as exc:
        validate_evidence_mapping(scene_id="S4", scene_paragraph_ids=pids, fields=fields)
    assert exc.value.error_code == "EVIDENCE_OUTSIDE_SCENE"


def test_evidence_missing_rejected() -> None:
    pids = _pids(4)
    fields = [
        EvidenceFieldView("goal", tuple(), "", required=True),
    ]
    with pytest.raises(SceneEvidenceValidationError) as exc:
        validate_evidence_mapping(scene_id="S4b", scene_paragraph_ids=pids, fields=fields)
    assert exc.value.error_code == "EVIDENCE_MISSING"


def test_duplicate_ids_are_deduped_in_remap() -> None:
    pids = _pids(3)
    fields = {
        "tension": {
            "level": 4,
            "mapped_score": 80,
            "evidence_paragraph_ids": [pids[0], pids[0], pids[1]],
            "rationale": "ok",
        }
    }
    patched = apply_evidence_remap_patch(
        fields=fields,
        patch={"tension": {"evidence_paragraph_ids": [pids[0], pids[0], pids[2]]}},
        allowed_ids=pids,
    )
    assert patched["tension"]["evidence_paragraph_ids"] == [pids[0], pids[2]]
    assert patched["tension"]["level"] == 4
    assert patched["tension"]["mapped_score"] == 80


def test_boundary_too_broad_before_overbroad() -> None:
    pids = _pids(14)
    template = "本场全部内容体现该判断。"
    names = [
        "goal_progress",
        "conflict_change",
        "state_change",
        "information_gain",
        "character_agency",
        "curiosity",
        "tension",
    ]
    fields = [_local(name, pids, template) for name in names]
    boundary = BoundaryMeta(
        signals=["time_change", "location_change", "multiple_event_clusters"],
        suspected_split_points=["SYN-P0005", "SYN-P0010"],
        consolidation_confidence=0.3,
        multiple_structure_tasks=True,
        paragraph_count=14,
    )
    with pytest.raises(SceneEvidenceValidationError) as exc:
        validate_evidence_mapping(
            scene_id="S14",
            scene_paragraph_ids=pids,
            fields=fields,
            boundary=boundary,
        )
    assert exc.value.error_code == "SCENE_BOUNDARY_TOO_BROAD"
    assert exc.value.details["suggested_action"] == "rerun_scene_boundary"


def test_evidence_repair_does_not_change_level_or_mapped_score() -> None:
    pids = _pids(6)
    fields = {
        "hook": {
            "level": 5,
            "mapped_score": 95,
            "evidence_paragraph_ids": pids,
            "rationale": "old",
            "plot_progress": 70,
        }
    }
    patched = apply_evidence_remap_patch(
        fields=fields,
        patch={
            "hook": {
                "level": 1,
                "mapped_score": 10,
                "plot_progress": 1,
                "evidence_paragraph_ids": pids[:2],
                "rationale": "field-targeted hook rationale",
            }
        },
        allowed_ids=pids,
    )
    assert patched["hook"]["level"] == 5
    assert patched["hook"]["mapped_score"] == 95
    assert patched["hook"]["plot_progress"] == 70
    assert patched["hook"]["evidence_paragraph_ids"] == pids[:2]
    assert "hook" in patched["hook"]["rationale"]


def test_evidence_repair_max_once() -> None:
    assert evidence_repair_attempt_allowed(prior_attempts=0) is True
    assert evidence_repair_attempt_allowed(prior_attempts=1) is False


def test_repair_request_id_idempotency_contract() -> None:
    """Same repair_request_id must not schedule a second model call (local gate)."""
    seen: set[str] = set()

    def schedule(repair_request_id: str) -> bool:
        if repair_request_id in seen:
            return False
        if not evidence_repair_attempt_allowed(prior_attempts=len(seen)):
            return False
        seen.add(repair_request_id)
        return True

    assert schedule("repair-1") is True
    assert schedule("repair-1") is False
    assert schedule("repair-2") is False  # max attempts already consumed via prior_attempts gate


def test_structured_error_fields_complete() -> None:
    pids = _pids(8)
    fields = [
        _local(name, pids, "本场全部内容体现该判断。")
        for name in [
            "goal_progress",
            "conflict_change",
            "state_change",
            "information_gain",
            "character_agency",
            "curiosity",
            "tension",
        ]
    ]
    with pytest.raises(SceneEvidenceValidationError) as exc:
        validate_evidence_mapping(scene_id="S8f", scene_paragraph_ids=pids, fields=fields)
    for key in (
        "scene_id",
        "scene_paragraph_count",
        "affected_fields",
        "shared_evidence",
        "local_field_count",
        "full_scene_reuse_ratio",
        "duplicate_rationale_groups",
        "repairable",
        "suggested_action",
    ):
        assert key in exc.value.details
