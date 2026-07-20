"""DEFECT-CANARY-007: hook_score distribution + business error passthrough."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schemas.reader_journey import SCENE_PROMPT_VERSION, SceneReaderJourneyProfileItem
from app.services.prompt_service import load_prompt
from app.services.reader_journey_contract_migrate import migrate_v11_profile_dict_to_v12
from app.services.reader_journey_pipeline import _classify_journey_error
from app.services.scene_pipeline import classify_pipeline_error
from app.services.reader_journey_validation import validate_score_distribution
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
    / "real-canary-v3"
    / "defects"
    / "DEFECT-CANARY-007-evidence.json"
)


def _pids(*nums: int, book: str = "B0002") -> list[str]:
    return [f"{book}-C0001-P{n:04d}" for n in nums]


def _profile(
    *,
    scene_id: int,
    ordinal: int,
    paragraph_ids: list[str],
    hook_score: int,
    hooks: list[dict],
    tension: int = 50,
    curiosity: int = 50,
    dropoff: int = 25,
    **overrides,
) -> SceneReaderJourneyProfileItem:
    raw = migrate_v11_profile_dict_to_v12(
        _base_profile_dict(scene_id=scene_id, scene_ordinal=ordinal, paragraph_ids=paragraph_ids)
    )
    raw.update(
        {
            "hook_score": hook_score,
            "tension_score": tension,
            "curiosity_score": curiosity,
            "dropoff_risk_score": dropoff,
            "hooks": hooks,
            "scene_value_summary": overrides.pop(
                "scene_value_summary", f"Scene{ordinal}通过结构悬念建立继续阅读动力"
            ),
        }
    )
    if ordinal > 1:
        raw["reader_question_in"] = [
            {
                "question": "前序悬念是否升级",
                "source": "carried_from_previous",
                "confidence": 0.7,
            }
        ]
    raw.update(overrides)
    return SceneReaderJourneyProfileItem.model_validate(raw)


def _hook(summary: str, evidence: list[str], *, strength: int = 85) -> dict:
    return {
        "type": "information",
        "summary": summary,
        "strength": strength,
        "evidence_paragraph_ids": evidence,
    }


def test_prompt_version_v1_6_has_score_anchors():
    assert SCENE_PROMPT_VERSION == "v1.6"
    prompt = load_prompt("reader_journey_scene", "v1.6")
    assert "hook_score" in prompt.system
    assert "91—100" in prompt.system or "91-100" in prompt.system
    # Prior certified prompt retained for regression comparison.
    prior = load_prompt("reader_journey_scene", "v1.5")
    assert "hook_score" in prior.system


def test_all_high_with_evidence_warns_not_fails():
    profiles = [
        _profile(
            scene_id=1,
            ordinal=1,
            paragraph_ids=_pids(1, 2, 3, 4),
            hook_score=90,
            hooks=[_hook("神秘女性身份成谜", _pids(4), strength=90)],
            dropoff=30,
        ),
        _profile(
            scene_id=2,
            ordinal=2,
            paragraph_ids=_pids(5, 6, 7, 8, 9, 10),
            hook_score=85,
            hooks=[_hook("红灯与追兵同步暗示监控", _pids(10))],
            dropoff=28,
        ),
        _profile(
            scene_id=3,
            ordinal=3,
            paragraph_ids=_pids(11, 12),
            hook_score=85,
            hooks=[_hook("湿纸内容未知", _pids(12))],
            dropoff=35,
        ),
    ]
    assessment = validate_score_distribution(profiles)
    assert assessment["requires_review"] is True
    assert assessment["warnings"]
    assert any("ALL_HIGH" in w["code"] or "SMALL_SAMPLE" in w["code"] for w in assessment["warnings"])


def test_a2_real_scores_offline_reproduce():
    require_path(EVIDENCE_PATH)
    rows = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    profiles = []
    for row in rows:
        pids = []
        for h in row["hooks"]:
            pids.extend(h["evidence"])
        pids = list(dict.fromkeys(pids))
        if not pids:
            pids = _pids(1, 2)
        if len(pids) == 1:
            pids = pids + [pids[0][:-4] + f"{int(pids[0][-4:]) + 1:04d}"]
        kwargs = dict(
            scene_id=row["ordinal"],
            ordinal=row["ordinal"],
            paragraph_ids=sorted(set(pids)),
            hook_score=row["hook_score"],
            tension=row["tension"],
            curiosity=row["curiosity"],
            dropoff=20 + row["ordinal"],
            hooks=[
                _hook(h["summary"], h["evidence"], strength=h.get("strength") or 80)
                for h in row["hooks"]
            ],
            scene_value_summary=row["scene_value_summary"],
        )
        if row.get("payoffs"):
            kwargs["payoffs"] = [
                {
                    "type": "information",
                    "summary": p["summary"],
                    "strength": p.get("strength") or 40,
                    "evidence_paragraph_ids": [pids[0]],
                }
                for p in row["payoffs"]
            ]
        profiles.append(_profile(**kwargs))
    # Pre-fix: legacy rule would have failed; new rule warns.
    assessment = validate_score_distribution(profiles)
    assert [p.hook_score for p in profiles] == [90, 85, 85]
    assert assessment["requires_review"] is True
    assert not any(
        isinstance(w, Exception) for w in assessment["warnings"]
    )


def test_high_without_hook_object_fails():
    profile = _profile(
        scene_id=1,
        ordinal=1,
        paragraph_ids=_pids(1, 2),
        hook_score=90,
        hooks=[],
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_score_distribution([profile])
    assert exc.value.error_code == "JOURNEY_HIGH_HOOK_WITHOUT_HOOK_OBJECT"


def test_high_without_evidence_fails():
    profile = _profile(
        scene_id=1,
        ordinal=1,
        paragraph_ids=_pids(1, 2),
        hook_score=90,
        hooks=[
            {
                "type": "danger",
                "summary": "悬念但无证据",
                "strength": 90,
                "evidence_paragraph_ids": [],
            }
        ],
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_score_distribution([profile])
    assert exc.value.error_code == "JOURNEY_HIGH_HOOK_WITHOUT_EVIDENCE"


def test_two_scene_all_high_does_not_auto_fail():
    profiles = [
        _profile(
            scene_id=1,
            ordinal=1,
            paragraph_ids=_pids(1, 2),
            hook_score=88,
            hooks=[_hook("开场断点", _pids(1))],
            dropoff=30,
        ),
        _profile(
            scene_id=2,
            ordinal=2,
            paragraph_ids=_pids(3, 4),
            hook_score=86,
            hooks=[_hook("升级断点", _pids(3))],
            dropoff=32,
        ),
    ]
    assessment = validate_score_distribution(profiles)
    assert assessment["requires_review"] is True


def test_repeated_identical_scores_warn():
    profiles = [
        _profile(
            scene_id=i,
            ordinal=i,
            paragraph_ids=_pids(i, i + 10),
            hook_score=85,
            hooks=[_hook(f"悬念{i}", _pids(i))],
            dropoff=20 + i,
        )
        for i in range(1, 4)
    ]
    assessment = validate_score_distribution(profiles)
    assert any(w["code"] == "JOURNEY_REPEATED_SCORE_PATTERN" for w in assessment["warnings"])


def test_business_error_passthrough_not_unexpected():
    exc = StructuralValidationError(
        "不允许所有 Scene 的 hook_score 都高于 80",
        error_code="JOURNEY_SCORE_DISTRIBUTION_SUSPICIOUS",
    )
    code, stage, _retryable, _hint = _classify_journey_error(exc)
    assert code == "JOURNEY_SCORE_DISTRIBUTION_SUSPICIOUS"
    assert code != "PIPELINE_UNEXPECTED_ERROR"
    assert "journey" in stage or "business" in stage

    code2, stage2, _, _ = classify_pipeline_error(exc)
    assert code2 == "JOURNEY_SCORE_DISTRIBUTION_SUSPICIOUS"
    assert stage2 == "business_validation"


def test_unknown_exception_still_unexpected():
    code, stage, _, _ = classify_pipeline_error(RuntimeError("boom-unknown"))
    assert code == "PIPELINE_UNEXPECTED_ERROR"
    assert stage == "pipeline"


def test_high_hook_with_evidence_mixed_distribution_ok_without_review():
    profiles = [
        _profile(
            scene_id=1,
            ordinal=1,
            paragraph_ids=_pids(1, 2),
            hook_score=90,
            hooks=[_hook("强断点", _pids(1), strength=90)],
            dropoff=40,
        ),
        _profile(
            scene_id=2,
            ordinal=2,
            paragraph_ids=_pids(3, 4),
            hook_score=55,
            hooks=[_hook("中等牵引", _pids(3), strength=55)],
            dropoff=30,
        ),
        _profile(
            scene_id=3,
            ordinal=3,
            paragraph_ids=_pids(5, 6),
            hook_score=35,
            hooks=[_hook("弱悬念", _pids(5), strength=35)],
            dropoff=25,
        ),
    ]
    assessment = validate_score_distribution(profiles)
    assert assessment["requires_review"] is False
    assert assessment["warnings"] == []
