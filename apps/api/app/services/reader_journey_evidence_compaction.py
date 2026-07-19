# -*- coding: utf-8 -*-
"""Targeted Reader Journey Evidence count compaction (DEFECT-CANARY-016).

When top-level evidence_paragraph_ids exceeds contract maxItems=16 after
order-preserving dedupe and rejection of out-of-scope / unknown IDs, request a
minimal compaction patch — never regenerate the full Profile, never mechanically
truncate to the first 16 IDs.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.validation_errors import StructuralValidationError

EVIDENCE_MAX_ITEMS = 16
COMPACTION_CONTRACT_VERSION = "compaction-1.0"

PROTECTED_PROFILE_FIELDS = (
    "scene_id",
    "scene_ordinal",
    "scene_value_summary",
    "reader_question_in",
    "reader_question_created",
    "reader_question_answered",
    "reader_question_out",
    "dominant_emotion",
    "emotional_valence_start",
    "emotional_valence_end",
    "arousal_start",
    "arousal_end",
    "curiosity_score",
    "tension_score",
    "payoff_score",
    "hook_score",
    "information_gain_score",
    "emotional_resonance_score",
    "cognitive_load_score",
    "dropoff_risk_score",
    "payoffs",
    "hooks",
    "techniques",
    "risk_points",
    "emotion_beats",
    "information_changes",
    "character_effects",
    "writing_takeaways",
    "confidence",
)


class JourneyEvidenceCompactionPatchResult(BaseModel):
    """Directed compaction patch — only Evidence selection, never full Profile."""

    model_config = ConfigDict(extra="forbid")
    contract_version: str = COMPACTION_CONTRACT_VERSION
    replacement_evidence_paragraph_ids: list[str] = Field(
        default_factory=list, max_length=EVIDENCE_MAX_ITEMS
    )
    removed_evidence_paragraph_ids: list[str] = Field(default_factory=list)
    selection_reason: str = Field(min_length=1, max_length=400)

    @field_validator("replacement_evidence_paragraph_ids")
    @classmethod
    def _replacement_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("replacement_evidence_paragraph_ids must be unique")
        return value


JourneyEvidenceCompactionPatchResult.CONTRACT_VERSION = COMPACTION_CONTRACT_VERSION  # type: ignore[attr-defined]


def normalize_evidence_ids(
    ids: list[Any],
    *,
    allowed_ids: set[str] | None = None,
) -> list[str]:
    """Order-preserving dedupe; optionally reject OOS / unknown IDs.

    Does NOT mechanically truncate to maxItems.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in ids or []:
        if raw is None:
            continue
        item = str(raw).strip()
        if not item or item in seen:
            continue
        if allowed_ids is not None and item not in allowed_ids:
            continue
        seen.add(item)
        out.append(item)
    return out


def paragraph_ids_by_scene_from_snapshot(
    input_snapshot: dict[str, Any],
) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for item in input_snapshot.get("profiles_target") or []:
        if not isinstance(item, dict) or item.get("scene_id") is None:
            continue
        sid = int(item["scene_id"])
        ids = {
            str(p["id"])
            for p in (item.get("paragraphs") or [])
            if isinstance(p, dict) and p.get("id")
        }
        out[sid] = ids
    return out


def normalize_batch_payload_evidence(
    payload: dict[str, Any],
    paragraph_ids_by_scene: dict[int, set[str]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize top-level evidence lists; return (payload, count_violations)."""
    data = copy.deepcopy(payload)
    violations: list[dict[str, Any]] = []
    for profile in data.get("profiles") or []:
        if not isinstance(profile, dict) or profile.get("scene_id") is None:
            continue
        scene_id = int(profile["scene_id"])
        allowed = paragraph_ids_by_scene.get(scene_id)
        raw_ids = list(profile.get("evidence_paragraph_ids") or [])
        normalized = normalize_evidence_ids(raw_ids, allowed_ids=allowed)
        profile["evidence_paragraph_ids"] = normalized
        if len(normalized) > EVIDENCE_MAX_ITEMS:
            violations.append(
                {
                    "error_code": "JOURNEY_EVIDENCE_COUNT_INVALID",
                    "target_path": (
                        f"profiles[scene_id={scene_id}].evidence_paragraph_ids"
                    ),
                    "scene_id": scene_id,
                    "max_items": EVIDENCE_MAX_ITEMS,
                    "current_evidence_ids": list(normalized),
                    "count": len(normalized),
                }
            )
    return data, violations


def _profile_claims(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "scene_value_summary": profile.get("scene_value_summary"),
        "hook_score": profile.get("hook_score"),
        "payoff_score": profile.get("payoff_score"),
        "tension_score": profile.get("tension_score"),
        "curiosity_score": profile.get("curiosity_score"),
        "dominant_emotion": profile.get("dominant_emotion"),
        "hooks": profile.get("hooks") or [],
        "payoffs": profile.get("payoffs") or [],
        "techniques": [
            {
                "code": t.get("code"),
                "name": t.get("name"),
                "mechanism": t.get("mechanism"),
            }
            for t in (profile.get("techniques") or [])
            if isinstance(t, dict)
        ],
        "reader_question_created": [
            {"question": q.get("question")}
            for q in (profile.get("reader_question_created") or [])
            if isinstance(q, dict)
        ],
        "reader_question_out": [
            {"question": q.get("question")}
            for q in (profile.get("reader_question_out") or [])
            if isinstance(q, dict)
        ],
        "risk_points": [
            {"type": r.get("type"), "summary": r.get("summary")}
            for r in (profile.get("risk_points") or [])
            if isinstance(r, dict)
        ],
    }


def snippets_for_ids(
    input_snapshot: dict[str, Any],
    scene_id: int,
    evidence_ids: list[str],
    *,
    max_chars: int = 120,
) -> list[dict[str, str]]:
    by_id: dict[str, str] = {}
    for item in input_snapshot.get("profiles_target") or []:
        if not isinstance(item, dict) or int(item.get("scene_id") or -1) != int(scene_id):
            continue
        for para in item.get("paragraphs") or []:
            if not isinstance(para, dict) or not para.get("id"):
                continue
            by_id[str(para["id"])] = str(para.get("text") or "")[:max_chars]
    return [{"id": pid, "text": by_id.get(pid, "")} for pid in evidence_ids]


def build_compaction_repair_context(
    *,
    payload: dict[str, Any],
    violations: list[dict[str, Any]],
    input_snapshot: dict[str, Any],
) -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    profiles = {
        int(p["scene_id"]): p
        for p in (payload.get("profiles") or [])
        if isinstance(p, dict) and p.get("scene_id") is not None
    }
    for item in violations:
        scene_id = int(item["scene_id"])
        profile = profiles.get(scene_id) or {}
        current = list(item.get("current_evidence_ids") or [])
        targets.append(
            {
                "error_code": "JOURNEY_EVIDENCE_COUNT_INVALID",
                "target_path": item["target_path"],
                "scene_id": scene_id,
                "max_items": EVIDENCE_MAX_ITEMS,
                "current_evidence_ids": current,
                "evidence_snippets": snippets_for_ids(
                    input_snapshot, scene_id, current
                ),
                "profile_claims": _profile_claims(profile),
                "protected_profile_fields": list(PROTECTED_PROFILE_FIELDS),
            }
        )
    return {
        "error_code": "JOURNEY_EVIDENCE_COUNT_INVALID",
        "instruction": (
            "Return ONLY an Evidence compaction patch JSON. "
            "Do not regenerate the full Profile or Journey. "
            "replacement_evidence_paragraph_ids must be a subset of current_evidence_ids, "
            f"unique, and at most {EVIDENCE_MAX_ITEMS} items. "
            "Do not add new IDs. Do not modify any protected_profile_fields. "
            "Keep the minimal sufficient Evidence supporting core Profile claims. "
            "If compression is impossible without inventing IDs, fail clearly — do not forge."
        ),
        "targets": targets,
        "violations": violations,
    }


def render_compaction_repair_user_content(
    context: dict[str, Any], raw_response: str
) -> str:
    return (
        "定向压缩 Reader Journey Profile 顶层 Evidence 数量。"
        "只返回 compaction patch JSON，禁止重生成完整 Profile。\n\n"
        f"repair_context:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"original_invalid_json:\n{raw_response}\n\n"
        "patch schema: "
        '{"contract_version":"compaction-1.0",'
        '"replacement_evidence_paragraph_ids":["..."],'
        '"removed_evidence_paragraph_ids":["..."],'
        '"selection_reason":"..."}'
    )


def apply_evidence_compaction(
    original_payload: dict[str, Any],
    patch: JourneyEvidenceCompactionPatchResult,
    *,
    scene_id: int,
    current_evidence_ids: list[str],
    max_items: int = EVIDENCE_MAX_ITEMS,
) -> dict[str, Any]:
    """Apply compaction patch; never mutate protected Profile fields."""
    if patch.contract_version != COMPACTION_CONTRACT_VERSION:
        raise StructuralValidationError(
            f"unsupported compaction contract_version: {patch.contract_version}",
            "JOURNEY_EVIDENCE_COMPACTION_INVALID",
            failed_field="contract_version",
        )
    replacement = list(patch.replacement_evidence_paragraph_ids)
    if len(replacement) > max_items:
        raise StructuralValidationError(
            f"compaction replacement has {len(replacement)} items; max is {max_items}",
            "JOURNEY_EVIDENCE_COMPACTION_INVALID",
            failed_field="replacement_evidence_paragraph_ids",
        )
    current_set = set(current_evidence_ids)
    if any(pid not in current_set for pid in replacement):
        raise StructuralValidationError(
            "compaction introduced Evidence IDs not in current_evidence_ids",
            "JOURNEY_EVIDENCE_COMPACTION_INVALID",
            failed_field="replacement_evidence_paragraph_ids",
        )
    # Preserve relative order from current list.
    order = {pid: idx for idx, pid in enumerate(current_evidence_ids)}
    replacement_sorted = sorted(replacement, key=lambda pid: order.get(pid, 10**9))
    if replacement_sorted == list(current_evidence_ids):
        raise StructuralValidationError(
            "compaction made no progress on Evidence count",
            "JOURNEY_EVIDENCE_COMPACTION_NO_PROGRESS",
            failed_field="replacement_evidence_paragraph_ids",
            no_model_repair=True,
        )
    if len(replacement_sorted) > max_items:
        raise StructuralValidationError(
            "compaction still exceeds max_items",
            "JOURNEY_EVIDENCE_COMPACTION_INVALID",
            failed_field="replacement_evidence_paragraph_ids",
        )

    after = copy.deepcopy(original_payload)
    target = next(
        (
            p
            for p in (after.get("profiles") or [])
            if isinstance(p, dict) and int(p.get("scene_id")) == int(scene_id)
        ),
        None,
    )
    if target is None:
        raise StructuralValidationError(
            f"compaction target scene missing: {scene_id}",
            "JOURNEY_EVIDENCE_COMPACTION_INVALID",
            failed_field="scene_id",
        )
    before_profile = next(
        (
            p
            for p in (original_payload.get("profiles") or [])
            if isinstance(p, dict) and int(p.get("scene_id")) == int(scene_id)
        ),
        {},
    )
    target["evidence_paragraph_ids"] = replacement_sorted

    # Guard: protected fields byte-identical; other profiles untouched.
    for field in PROTECTED_PROFILE_FIELDS:
        if json.dumps(before_profile.get(field), sort_keys=True, ensure_ascii=False) != json.dumps(
            target.get(field), sort_keys=True, ensure_ascii=False
        ):
            raise StructuralValidationError(
                f"compaction mutated protected field: {field}",
                "JOURNEY_EVIDENCE_COMPACTION_INVALID",
                failed_field=field,
            )
    before_profiles = {
        int(p["scene_id"]): p
        for p in (original_payload.get("profiles") or [])
        if isinstance(p, dict) and p.get("scene_id") is not None
    }
    after_profiles = {
        int(p["scene_id"]): p
        for p in (after.get("profiles") or [])
        if isinstance(p, dict) and p.get("scene_id") is not None
    }
    if set(before_profiles) != set(after_profiles) or len(before_profiles) != len(
        after_profiles
    ):
        raise StructuralValidationError(
            "compaction changed Scene IDs or count",
            "JOURNEY_EVIDENCE_COMPACTION_INVALID",
            failed_field="profiles",
        )
    for sid, before in before_profiles.items():
        if sid == int(scene_id):
            continue
        if json.dumps(before, sort_keys=True, ensure_ascii=False) != json.dumps(
            after_profiles[sid], sort_keys=True, ensure_ascii=False
        ):
            raise StructuralValidationError(
                f"compaction mutated unrelated Profile scene_id={sid}",
                "JOURNEY_EVIDENCE_COMPACTION_INVALID",
                failed_field="profiles",
            )
    return after


def mechanical_truncate_forbidden(ids: list[str], max_items: int = EVIDENCE_MAX_ITEMS) -> list[str]:
    """Explicit non-API: tests assert production code never uses this for remediation."""
    raise RuntimeError("mechanical truncate of Evidence is forbidden")
