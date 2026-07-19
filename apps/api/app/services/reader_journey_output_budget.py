# -*- coding: utf-8 -*-
"""Reader Journey schema output-token budget checks (DEFECT-CANARY-016)."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.schemas.reader_journey import (
    CHAPTER_CONTRACT_VERSION,
    SCENE_CONTRACT_VERSION,
    ChapterReaderJourneySynthesisResult,
    SceneReaderJourneyBatchResult,
)
from app.services.reader_journey_evidence_compaction import (
    COMPACTION_CONTRACT_VERSION,
    EVIDENCE_MAX_ITEMS,
    JourneyEvidenceCompactionPatchResult,
)
from app.services.reader_journey_targeted_repair import JourneyEvidenceRepairPatchResult
from app.services.transition_batch_planner import conservative_token_estimate

# Project constants — must not be hard-coded only inside Canary scripts.
READER_JOURNEY_OUTPUT_BUDGET_SAFETY_MARGIN = 256
# Plus tokenization is denser than conservative_token_estimate on real Journey JSON
# (C3 Scene7: estimate 1216 vs reported 2088 ≈ 1.72×).
READER_JOURNEY_OUTPUT_TOKEN_ESTIMATE_MULTIPLIER = 1.75
# Observed dense single-Scene Profile (canary-v12 inv30, finish=stop).
READER_JOURNEY_SCENE_OBSERVED_OUTPUT_TOKENS = 2088
# Cap synthetic/heuristic inflation vs fixture (prevents infinite max_output_tokens).
READER_JOURNEY_SCENE_SYNTHETIC_SCALE_CAP = 1.35
READER_JOURNEY_CHAPTER_OUTPUT_ANCHOR_TOKENS = 2400
_NESTED_EVIDENCE_BUDGET_COUNT = 2

_REPO_ROOT = Path(__file__).resolve().parents[4]
_C3_SCENE7_FIXTURE = (
    _REPO_ROOT
    / "audits/single-chapter-pipeline/real-canary-v12/defects"
    / "DEFECT-CANARY-016-attempt1-normal-parsed.json"
)

_FILL_160 = 28
_FILL_180 = 32
_FILL_120 = 24
_FILL_80 = 16
_FILL_40 = 12


def _pad(text: str, n: int) -> str:
    unit = "证据充分的核心判断描述"
    out = text
    while len(out) < n:
        out += unit
    return out[:n]


def max_legal_single_scene_profile_payload() -> dict[str, Any]:
    """Max-cardinality legal single-Scene Profile (operational dense fill)."""
    pid = [f"B0001-C0001-P{i:04d}" for i in range(1, EVIDENCE_MAX_ITEMS + 1)]

    def ev(n: int = 2) -> list[str]:
        return pid[:n]

    def nested(n: int = 2, *, with_hook_struct: bool = False) -> list[dict[str, Any]]:
        items = []
        for i in range(n):
            row: dict[str, Any] = {
                "type": "information" if not with_hook_struct else "danger",
                "summary": _pad(f"判断{i}", _FILL_160),
                "strength": 100,
                "evidence_paragraph_ids": ev(_NESTED_EVIDENCE_BUDGET_COUNT),
            }
            if with_hook_struct:
                row.update(
                    {
                        "known": _pad("已知", _FILL_80),
                        "gap": _pad("缺口", _FILL_80),
                        "continue_drive": _pad("继续", _FILL_80),
                        "next_handoff": _pad("承接", _FILL_80),
                    }
                )
            items.append(row)
        return items

    profile = {
        "scene_id": 1,
        "scene_ordinal": 1,
        "scene_value_summary": _pad("场景价值", _FILL_160),
        "reader_question_in": [
            {
                "question": _pad("承接问题", _FILL_160),
                "source": "carried_from_previous",
                "confidence": 1.0,
            }
        ],
        "reader_question_created": [
            {
                "question": _pad("新问题", _FILL_160),
                "trigger_summary": _pad("触发", _FILL_160),
                "strength": 100,
                "evidence_paragraph_ids": ev(2),
            }
            for _ in range(2)
        ],
        "reader_question_answered": [
            {
                "question": _pad("已答问题", _FILL_160),
                "answer_summary": _pad("回答", _FILL_160),
                "answer_degree": "full",
                "evidence_paragraph_ids": ev(_NESTED_EVIDENCE_BUDGET_COUNT),
            }
            for _ in range(2)
        ],
        "reader_question_out": [
            {
                "question": _pad("遗留问题", _FILL_160),
                "origin": "created_here",
                "strength": 100,
                "evidence_paragraph_ids": ev(_NESTED_EVIDENCE_BUDGET_COUNT),
                "hook_type": "danger",
            }
            for _ in range(2)
        ],
        "dominant_emotion": _pad("紧张", _FILL_80),
        "emotional_valence_start": -100,
        "emotional_valence_end": 100,
        "arousal_start": 100,
        "arousal_end": 100,
        "curiosity_score": 100,
        "tension_score": 100,
        "payoff_score": 100,
        "hook_score": 100,
        "information_gain_score": 100,
        "emotional_resonance_score": 100,
        "cognitive_load_score": 100,
        "dropoff_risk_score": 100,
        "payoffs": nested(2),
        "hooks": nested(2, with_hook_struct=True),
        "techniques": [
            {
                "code": f"TECH_{i}",
                "name": _pad("技法名", _FILL_80),
                "mechanism": _pad("机制", _FILL_180),
                "reader_effect": _pad("读者效果", _FILL_120),
                "transfer_formula": _pad("迁移", _FILL_160),
                "risk": _pad("风险提示", _FILL_120),
                "evidence_paragraph_ids": ev(_NESTED_EVIDENCE_BUDGET_COUNT),
            }
            for i in range(3)
        ],
        "risk_points": [
            {
                "type": "weak_hook",
                "summary": _pad("风险", _FILL_160),
                "severity": 100,
                "evidence_paragraph_ids": ev(_NESTED_EVIDENCE_BUDGET_COUNT),
            }
            for _ in range(2)
        ],
        "emotion_beats": [
            {
                "label": _pad("情绪", _FILL_80),
                "valence": -50,
                "arousal": 80,
                "evidence_paragraph_ids": ev(_NESTED_EVIDENCE_BUDGET_COUNT),
            }
            for _ in range(4)
        ],
        "information_changes": [
            {
                "type": "new_information",
                "summary": _pad("信息变化", _FILL_160),
                "certainty": "fact",
                "evidence_paragraph_ids": ev(_NESTED_EVIDENCE_BUDGET_COUNT),
            }
            for _ in range(3)
        ],
        "character_effects": [
            {
                "character_name": _pad("角色", _FILL_80),
                "trait_or_change": _pad("变化", _FILL_160),
                "method": "action",
                "evidence_paragraph_ids": ev(_NESTED_EVIDENCE_BUDGET_COUNT),
            }
            for _ in range(2)
        ],
        "writing_takeaways": [
            {
                "summary": _pad("写作启示", _FILL_160),
                "applicable_when": _pad("适用", _FILL_120),
                "avoid_when": _pad("避免", _FILL_120),
            }
            for _ in range(2)
        ],
        "confidence": 1.0,
        "evidence_paragraph_ids": pid,
    }
    return {"contract_version": SCENE_CONTRACT_VERSION, "profiles": [profile]}


def max_legal_chapter_journey_payload() -> dict[str, Any]:
    phases = [
        {
            "ordinal": i,
            "title": _pad(f"阶段{i}", _FILL_40),
            "start_scene_ordinal": i,
            "end_scene_ordinal": i,
            "primary_reader_question": _pad("主问题", _FILL_120),
            "dominant_emotion": _pad("情绪", _FILL_40),
            "reading_payoff": _pad("回报", _FILL_120),
            "continuation_motivation": _pad("继续动机", _FILL_120),
            "summary": _pad("阶段摘要", _FILL_160),
            "confidence": 1.0,
        }
        for i in range(1, 9)
    ]
    return {
        "contract_version": CHAPTER_CONTRACT_VERSION,
        "phases": phases,
        "chapter_reader_question_chain": [_pad(f"链{i}", _FILL_120) for i in range(8)],
        "pacing_diagnosis": [_pad(f"节奏{i}", _FILL_120) for i in range(6)],
        "chapter_strengths": [_pad(f"优点{i}", _FILL_120) for i in range(6)],
        "chapter_risks": [_pad(f"风险{i}", _FILL_120) for i in range(6)],
        "one_sentence_diagnosis": _pad("一句话诊断", _FILL_160),
    }


def max_legal_evidence_compaction_patch_payload() -> dict[str, Any]:
    ids = [f"B0001-C0001-P{i:04d}" for i in range(1, EVIDENCE_MAX_ITEMS + 1)]
    return {
        "contract_version": COMPACTION_CONTRACT_VERSION,
        "replacement_evidence_paragraph_ids": ids,
        "removed_evidence_paragraph_ids": [
            f"B0001-C0001-P{i:04d}" for i in range(17, 25)
        ],
        "selection_reason": _pad(
            "保留支持核心判断的最少充分证据，去掉重复场景枚举段落。", 200
        ),
    }


def max_legal_oos_patch_payload() -> dict[str, Any]:
    return {
        "contract_version": "patch-1.0",
        "patches": [
            {
                "op": "replace_evidence",
                "target_path": (
                    f"profiles[scene_id=1].techniques[{i}].evidence_paragraph_ids"
                ),
                "target_scene_id": 1,
                "old_evidence_ids": [f"B0001-C0001-P{j:04d}" for j in range(1, 5)],
                "new_evidence_ids": [f"B0001-C0001-P{j:04d}" for j in range(10, 14)],
            }
            for i in range(8)
        ],
    }


def estimate_patch_schema_tokens(payload: dict[str, Any]) -> int:
    """ASCII-heavy patches: mild multiplier only."""
    raw = int(conservative_token_estimate(payload))
    return int(math.ceil(raw * 1.25))


def estimate_scene_profile_schema_tokens() -> int:
    """Fixture-anchored estimate for max-legal single-Scene Profile output."""
    synthetic = max_legal_single_scene_profile_payload()
    synthetic_raw = int(conservative_token_estimate(synthetic))
    fixture_raw = synthetic_raw
    if _C3_SCENE7_FIXTURE.exists():
        data = json.loads(_C3_SCENE7_FIXTURE.read_text(encoding="utf-8"))
        if data.get("profiles"):
            data["profiles"][0]["evidence_paragraph_ids"] = list(
                data["profiles"][0].get("evidence_paragraph_ids") or []
            )[:EVIDENCE_MAX_ITEMS]
            data = {"contract_version": SCENE_CONTRACT_VERSION, "profiles": [data["profiles"][0]]}
            fixture_raw = int(conservative_token_estimate(data))
    scale = min(
        synthetic_raw / max(fixture_raw, 1),
        READER_JOURNEY_SCENE_SYNTHETIC_SCALE_CAP,
    )
    return int(
        math.ceil(READER_JOURNEY_SCENE_OBSERVED_OUTPUT_TOKENS * max(1.0, scale))
    )


def estimate_chapter_schema_tokens() -> int:
    raw = int(conservative_token_estimate(max_legal_chapter_journey_payload()))
    scaled = int(math.ceil(raw * READER_JOURNEY_OUTPUT_TOKEN_ESTIMATE_MULTIPLIER * 0.55))
    return max(READER_JOURNEY_CHAPTER_OUTPUT_ANCHOR_TOKENS, scaled)


def build_output_budget_audit() -> dict[str, Any]:
    settings = get_settings()
    margin = READER_JOURNEY_OUTPUT_BUDGET_SAFETY_MARGIN

    SceneReaderJourneyBatchResult.model_validate(max_legal_single_scene_profile_payload())
    ChapterReaderJourneySynthesisResult.model_validate(max_legal_chapter_journey_payload())
    JourneyEvidenceCompactionPatchResult.model_validate(
        max_legal_evidence_compaction_patch_payload()
    )
    JourneyEvidenceRepairPatchResult.model_validate(max_legal_oos_patch_payload())

    scene_tokens = estimate_scene_profile_schema_tokens()
    rows = [
        {
            "invocation_type": "reader_journey_scene_batch",
            "schema_version": SCENE_CONTRACT_VERSION,
            "max_items": {"evidence_paragraph_ids": EVIDENCE_MAX_ITEMS},
            "estimated_schema_tokens": scene_tokens,
            "configured_max_output_tokens": settings.cloud_output_reader_journey_scene,
            "safety_margin": margin,
        },
        {
            "invocation_type": "reader_journey_targeted_evidence_compaction",
            "schema_version": COMPACTION_CONTRACT_VERSION,
            "max_items": {"replacement_evidence_paragraph_ids": EVIDENCE_MAX_ITEMS},
            "estimated_schema_tokens": estimate_patch_schema_tokens(
                max_legal_evidence_compaction_patch_payload()
            ),
            "configured_max_output_tokens": (
                settings.cloud_output_reader_journey_evidence_repair
            ),
            "safety_margin": margin,
        },
        {
            "invocation_type": "reader_journey_chapter",
            "schema_version": CHAPTER_CONTRACT_VERSION,
            "max_items": {"phases": 8},
            "estimated_schema_tokens": estimate_chapter_schema_tokens(),
            "configured_max_output_tokens": settings.cloud_output_reader_journey_chapter,
            "safety_margin": margin,
        },
        {
            "invocation_type": "reader_journey_scene_schema_repair",
            "schema_version": SCENE_CONTRACT_VERSION,
            "max_items": {"evidence_paragraph_ids": EVIDENCE_MAX_ITEMS},
            "estimated_schema_tokens": scene_tokens,
            "configured_max_output_tokens": (
                settings.cloud_output_reader_journey_schema_repair
            ),
            "safety_margin": margin,
        },
        {
            "invocation_type": "reader_journey_targeted_evidence_patch",
            "schema_version": "patch-1.0",
            "max_items": {"patches": 16},
            "estimated_schema_tokens": estimate_patch_schema_tokens(
                max_legal_oos_patch_payload()
            ),
            "configured_max_output_tokens": (
                settings.cloud_output_reader_journey_business_repair
            ),
            "safety_margin": margin,
        },
    ]
    for row in rows:
        need = int(row["estimated_schema_tokens"]) + int(row["safety_margin"])
        row["required_max_output_tokens"] = need
        row["budget_pass"] = int(row["configured_max_output_tokens"]) >= need

    return {
        "audit_id": "reader-journey-output-budget-v1",
        "safety_margin_constant": "READER_JOURNEY_OUTPUT_BUDGET_SAFETY_MARGIN",
        "safety_margin": margin,
        "scene_observed_output_tokens": READER_JOURNEY_SCENE_OBSERVED_OUTPUT_TOKENS,
        "scene_synthetic_scale_cap": READER_JOURNEY_SCENE_SYNTHETIC_SCALE_CAP,
        "estimator": (
            "fixture_anchored_observed_scale for scene/schema_repair; "
            "patch mild multiplier; chapter anchor blend"
        ),
        "fill_policy": "max_legal_cardinality_with_operational_dense_fill",
        "hard_cap_note": "Configured limits must remain ≤ typical cloud hard cap 4000",
        "invocations": rows,
        "all_pass": all(bool(r["budget_pass"]) for r in rows),
    }


def budget_gate_verdict(audit: dict[str, Any] | None = None) -> str:
    data = audit if audit is not None else build_output_budget_audit()
    return (
        "READER_JOURNEY_OUTPUT_BUDGET_PASS"
        if data.get("all_pass")
        else "READER_JOURNEY_OUTPUT_BUDGET_FAIL"
    )
