# -*- coding: utf-8 -*-
"""Targeted Reader Journey Evidence repair (DEFECT-CANARY-011 / change v1.0.6).

Prefer directed patches over full Journey regeneration. Never forge Evidence,
never borrow from other Scenes, never mutate unrelated Profiles.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.reader_journey import SceneReaderJourneyBatchResult
from app.services.validation_errors import StructuralValidationError

NESTED_EVIDENCE_FIELDS = (
    "reader_question_created",
    "reader_question_answered",
    "reader_question_out",
    "payoffs",
    "hooks",
    "techniques",
    "risk_points",
    "emotion_beats",
    "information_changes",
    "character_effects",
)


class JourneyEvidencePatchOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["replace_evidence", "remove_evidence_ids", "remove_node"]
    target_path: str
    target_scene_id: int
    old_evidence_ids: list[str] = Field(default_factory=list)
    new_evidence_ids: list[str] = Field(default_factory=list)


class JourneyEvidenceRepairPatchResult(BaseModel):
    """Directed patch contract for JOURNEY_EVIDENCE_OUT_OF_SCOPE structural repair."""

    model_config = ConfigDict(extra="forbid")
    contract_version: str = "patch-1.0"
    patches: list[JourneyEvidencePatchOp] = Field(default_factory=list, max_length=16)


JourneyEvidenceRepairPatchResult.CONTRACT_VERSION = "patch-1.0"  # type: ignore[attr-defined]


def owner_scene_for_paragraph(
    paragraph_id: str, paragraph_ids_by_scene: dict[int, set[str]]
) -> int | None:
    for scene_id, ids in paragraph_ids_by_scene.items():
        if paragraph_id in ids:
            return int(scene_id)
    return None


def collect_oos_violations(
    result: SceneReaderJourneyBatchResult,
    paragraph_ids_by_scene: dict[int, set[str]],
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for profile in result.profiles:
        allowed = paragraph_ids_by_scene.get(profile.scene_id, set())
        for field_name in NESTED_EVIDENCE_FIELDS:
            for index, nested in enumerate(getattr(profile, field_name)):
                ids = list(getattr(nested, "evidence_paragraph_ids", None) or [])
                bad = [item for item in ids if item and item not in allowed]
                if not bad:
                    continue
                violations.append(
                    {
                        "error_code": "JOURNEY_EVIDENCE_OUT_OF_SCOPE",
                        "target_path": (
                            f"profiles[scene_id={profile.scene_id}]."
                            f"{field_name}[{index}].evidence_paragraph_ids"
                        ),
                        "target_scene_id": profile.scene_id,
                        "field_name": field_name,
                        "index": index,
                        "invalid_evidence_ids": bad,
                        "allowed_evidence_ids": sorted(allowed),
                        "original_invalid_node": nested.model_dump(mode="json"),
                        "invalid_evidence_owner_scenes": {
                            pid: owner_scene_for_paragraph(pid, paragraph_ids_by_scene)
                            for pid in bad
                        },
                    }
                )
        top_ids = list(profile.evidence_paragraph_ids)
        top_bad = [item for item in top_ids if item and item not in allowed]
        if top_bad:
            violations.append(
                {
                    "error_code": "JOURNEY_EVIDENCE_OUT_OF_SCOPE",
                    "target_path": (
                        f"profiles[scene_id={profile.scene_id}].evidence_paragraph_ids"
                    ),
                    "target_scene_id": profile.scene_id,
                    "field_name": "evidence_paragraph_ids",
                    "index": None,
                    "invalid_evidence_ids": top_bad,
                    "allowed_evidence_ids": sorted(allowed),
                    "original_invalid_node": {"evidence_paragraph_ids": top_ids},
                    "invalid_evidence_owner_scenes": {
                        pid: owner_scene_for_paragraph(pid, paragraph_ids_by_scene)
                        for pid in top_bad
                    },
                }
            )
    return violations


def snippets_for_scene(
    input_snapshot: dict[str, Any], scene_id: int, *, max_chars: int = 120
) -> list[dict[str, str]]:
    snippets: list[dict[str, str]] = []
    targets = input_snapshot.get("profiles_target") or []
    if not isinstance(targets, list):
        return snippets
    for item in targets:
        if not isinstance(item, dict) or int(item.get("scene_id") or -1) != int(scene_id):
            continue
        for para in item.get("paragraphs") or []:
            if not isinstance(para, dict) or not para.get("id"):
                continue
            text = str(para.get("text") or "")
            snippets.append({"id": str(para["id"]), "text": text[:max_chars]})
    return snippets


def build_targeted_repair_context(
    *,
    result: SceneReaderJourneyBatchResult,
    paragraph_ids_by_scene: dict[int, set[str]],
    input_snapshot: dict[str, Any],
    primary_error: str = "JOURNEY_EVIDENCE_OUT_OF_SCOPE",
) -> dict[str, Any]:
    violations = collect_oos_violations(result, paragraph_ids_by_scene)
    if not violations:
        return {
            "error_code": primary_error,
            "violations": [],
            "targets": [],
        }
    targets = []
    for item in violations:
        scene_id = int(item["target_scene_id"])
        targets.append(
            {
                "error_code": primary_error,
                "target_path": item["target_path"],
                "invalid_evidence_ids": item["invalid_evidence_ids"],
                "target_scene_id": scene_id,
                "allowed_evidence_ids": item["allowed_evidence_ids"],
                "allowed_evidence_snippets": snippets_for_scene(input_snapshot, scene_id),
                "original_invalid_node": item["original_invalid_node"],
                "invalid_evidence_owner_scenes": item.get("invalid_evidence_owner_scenes"),
            }
        )
    return {
        "error_code": primary_error,
        "instruction": (
            "Return ONLY a directed Evidence patch JSON. Do not regenerate the full Journey. "
            "Only modify listed error nodes. Do not change Scene IDs, Scene count, or legal Profiles. "
            "Do not cite Evidence from other Scenes. Do not forge Evidence IDs. "
            "Replace only when a current-Scene snippet semantically matches the node; "
            "otherwise remove the unsupported Evidence IDs or remove the unsupported node."
        ),
        "targets": targets,
        "violations": violations,
    }


def _token_set(text: str) -> set[str]:
    """Tokenize for lightweight semantic overlap (CJK unigrams + latin words)."""
    tokens: set[str] = set()
    for tok in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text.lower()):
        if tok.strip():
            tokens.add(tok)
    return tokens


def semantic_match_score(node: dict[str, Any], snippet_text: str) -> float:
    parts = [
        str(node.get("question") or ""),
        str(node.get("summary") or ""),
        str(node.get("trigger_summary") or ""),
        str(node.get("answer_summary") or ""),
        str(node.get("label") or ""),
        str(node.get("trait_or_change") or ""),
    ]
    node_tokens = _token_set(" ".join(parts))
    snip_tokens = _token_set(snippet_text)
    if not node_tokens or not snip_tokens:
        return 0.0
    overlap = len(node_tokens & snip_tokens)
    return overlap / max(1, len(node_tokens))


def propose_deterministic_evidence_patches(
    *,
    result: SceneReaderJourneyBatchResult,
    paragraph_ids_by_scene: dict[int, set[str]],
    input_snapshot: dict[str, Any],
    min_score: float = 0.15,
) -> JourneyEvidenceRepairPatchResult:
    """Offline/deterministic patch proposer for tests and optional local repair."""
    violations = collect_oos_violations(result, paragraph_ids_by_scene)
    patches: list[JourneyEvidencePatchOp] = []
    for item in violations:
        scene_id = int(item["target_scene_id"])
        allowed = set(item["allowed_evidence_ids"])
        snippets = {
            s["id"]: s["text"] for s in snippets_for_scene(input_snapshot, scene_id)
        }
        node = item["original_invalid_node"]
        best_id = None
        best_score = 0.0
        for pid, text in snippets.items():
            if pid not in allowed:
                continue
            score = semantic_match_score(node if isinstance(node, dict) else {}, text)
            if score > best_score:
                best_score = score
                best_id = pid
        if best_id is not None and best_score >= min_score:
            patches.append(
                JourneyEvidencePatchOp(
                    op="replace_evidence",
                    target_path=str(item["target_path"]),
                    target_scene_id=scene_id,
                    old_evidence_ids=list(item["invalid_evidence_ids"]),
                    new_evidence_ids=[best_id],
                )
            )
        else:
            # No semantic match: remove unsupported judgment node (not forge).
            patches.append(
                JourneyEvidencePatchOp(
                    op="remove_node",
                    target_path=str(item["target_path"]),
                    target_scene_id=scene_id,
                    old_evidence_ids=list(item["invalid_evidence_ids"]),
                    new_evidence_ids=[],
                )
            )
    return JourneyEvidenceRepairPatchResult(patches=patches)


def _parse_path(path: str) -> tuple[int, str, int | None]:
    """profiles[scene_id=N].field[i].evidence_paragraph_ids → (scene_id, field, index)."""
    m = re.match(
        r"profiles\[scene_id=(\d+)\]\.([a-z_]+)(?:\[(\d+)\])?(?:\.evidence_paragraph_ids)?$",
        path,
    )
    if not m:
        raise StructuralValidationError(
            f"unsupported patch target_path: {path}",
            "JOURNEY_REPAIR_VALIDATION_FAILED",
            failed_field="target_path",
        )
    scene_id = int(m.group(1))
    field = m.group(2)
    index = int(m.group(3)) if m.group(3) is not None else None
    return scene_id, field, index


def _profile_dict_by_scene(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for profile in payload.get("profiles") or []:
        if isinstance(profile, dict) and profile.get("scene_id") is not None:
            out[int(profile["scene_id"])] = profile
    return out


def apply_evidence_patches(
    original: SceneReaderJourneyBatchResult,
    patch_result: JourneyEvidenceRepairPatchResult,
    *,
    paragraph_ids_by_scene: dict[int, set[str]],
    allowed_paths: set[str] | None = None,
    require_semantic_match: bool = True,
    input_snapshot: dict[str, Any] | None = None,
    min_score: float = 0.15,
) -> SceneReaderJourneyBatchResult:
    """Apply directed patches with hard guardrails."""
    if not patch_result.patches:
        raise StructuralValidationError(
            "empty evidence repair patch",
            "JOURNEY_REPAIR_NO_PROGRESS",
            failed_field="patches",
        )
    before = original.model_dump(mode="json")
    after = copy.deepcopy(before)
    before_profiles = _profile_dict_by_scene(before)
    touched_scenes: set[int] = set()

    for patch in patch_result.patches:
        scene_id, field, index = _parse_path(patch.target_path)
        if patch.target_scene_id != scene_id:
            raise StructuralValidationError(
                "patch target_scene_id mismatches target_path",
                "JOURNEY_REPAIR_VALIDATION_FAILED",
                failed_field="target_scene_id",
            )
        if allowed_paths is not None and patch.target_path not in allowed_paths:
            raise StructuralValidationError(
                f"patch targets non-error path: {patch.target_path}",
                "JOURNEY_REPAIR_VALIDATION_FAILED",
                failed_field="target_path",
            )
        profiles = after.get("profiles") or []
        target_profile = next(
            (p for p in profiles if isinstance(p, dict) and int(p.get("scene_id")) == scene_id),
            None,
        )
        if target_profile is None:
            raise StructuralValidationError(
                f"patch scene missing: {scene_id}",
                "JOURNEY_REPAIR_VALIDATION_FAILED",
                failed_field="target_scene_id",
            )
        allowed = paragraph_ids_by_scene.get(scene_id, set())
        touched_scenes.add(scene_id)

        if field == "evidence_paragraph_ids" and index is None:
            ids = list(target_profile.get("evidence_paragraph_ids") or [])
            if patch.op == "replace_evidence":
                _assert_replace_legal(
                    patch,
                    allowed=allowed,
                    node={"evidence_paragraph_ids": ids},
                    require_semantic_match=require_semantic_match,
                    input_snapshot=input_snapshot or {},
                    scene_id=scene_id,
                    min_score=min_score,
                )
                cleaned = [i for i in ids if i not in set(patch.old_evidence_ids)]
                for nid in patch.new_evidence_ids:
                    if nid not in cleaned:
                        cleaned.append(nid)
                target_profile["evidence_paragraph_ids"] = cleaned
            elif patch.op in {"remove_evidence_ids", "remove_node"}:
                target_profile["evidence_paragraph_ids"] = [
                    i for i in ids if i not in set(patch.old_evidence_ids)
                ]
            continue

        if field not in NESTED_EVIDENCE_FIELDS or index is None:
            raise StructuralValidationError(
                f"unsupported patch field: {field}",
                "JOURNEY_REPAIR_VALIDATION_FAILED",
                failed_field=field,
            )
        items = list(target_profile.get(field) or [])
        if index < 0 or index >= len(items):
            raise StructuralValidationError(
                f"patch index out of range: {patch.target_path}",
                "JOURNEY_REPAIR_VALIDATION_FAILED",
                failed_field=field,
            )
        node = items[index]
        if not isinstance(node, dict):
            raise StructuralValidationError(
                "patch node is not an object",
                "JOURNEY_REPAIR_VALIDATION_FAILED",
                failed_field=field,
            )
        if patch.op == "remove_node":
            del items[index]
            target_profile[field] = items
            continue
        ids = list(node.get("evidence_paragraph_ids") or [])
        if patch.op == "replace_evidence":
            _assert_replace_legal(
                patch,
                allowed=allowed,
                node=node,
                require_semantic_match=require_semantic_match,
                input_snapshot=input_snapshot or {},
                scene_id=scene_id,
                min_score=min_score,
            )
            cleaned = [i for i in ids if i not in set(patch.old_evidence_ids)]
            for nid in patch.new_evidence_ids:
                if nid not in cleaned:
                    cleaned.append(nid)
            node["evidence_paragraph_ids"] = cleaned
            items[index] = node
            target_profile[field] = items
        elif patch.op == "remove_evidence_ids":
            node["evidence_paragraph_ids"] = [
                i for i in ids if i not in set(patch.old_evidence_ids)
            ]
            items[index] = node
            target_profile[field] = items

    # Guard: scene count / ids unchanged; untouched profiles byte-identical.
    after_profiles = _profile_dict_by_scene(after)
    if set(before_profiles) != set(after_profiles):
        raise StructuralValidationError(
            "repair changed Scene IDs",
            "JOURNEY_REPAIR_VALIDATION_FAILED",
            failed_field="scene_id",
        )
    if len(before.get("profiles") or []) != len(after.get("profiles") or []):
        raise StructuralValidationError(
            "repair changed Scene count",
            "JOURNEY_REPAIR_VALIDATION_FAILED",
            failed_field="profiles",
        )
    for sid, before_prof in before_profiles.items():
        if sid in touched_scenes:
            continue
        if json.dumps(before_prof, sort_keys=True, ensure_ascii=False) != json.dumps(
            after_profiles[sid], sort_keys=True, ensure_ascii=False
        ):
            raise StructuralValidationError(
                f"repair mutated unrelated Profile scene_id={sid}",
                "JOURNEY_REPAIR_VALIDATION_FAILED",
                failed_field="profiles",
            )

    return SceneReaderJourneyBatchResult.model_validate(after)


def _assert_replace_legal(
    patch: JourneyEvidencePatchOp,
    *,
    allowed: set[str],
    node: dict[str, Any],
    require_semantic_match: bool,
    input_snapshot: dict[str, Any],
    scene_id: int,
    min_score: float,
) -> None:
    if not patch.new_evidence_ids:
        raise StructuralValidationError(
            "replace_evidence requires new_evidence_ids",
            "JOURNEY_REPAIR_VALIDATION_FAILED",
            failed_field="new_evidence_ids",
        )
    forged = [i for i in patch.new_evidence_ids if i not in allowed]
    if forged:
        raise StructuralValidationError(
            f"repair forged or out-of-scope Evidence: {forged[:3]}",
            "JOURNEY_REPAIR_VALIDATION_FAILED",
            failed_field="new_evidence_ids",
        )
    if not require_semantic_match:
        return
    snippets = {
        s["id"]: s["text"] for s in snippets_for_scene(input_snapshot, scene_id)
    }
    for nid in patch.new_evidence_ids:
        text = snippets.get(nid, "")
        if semantic_match_score(node, text) < min_score:
            raise StructuralValidationError(
                f"repair Evidence lacks semantic match: {nid}",
                "JOURNEY_REPAIR_VALIDATION_FAILED",
                failed_field="new_evidence_ids",
            )


def violation_fingerprint(violations: list[dict[str, Any]]) -> list[tuple]:
    rows = []
    for item in violations:
        rows.append(
            (
                item.get("target_path"),
                tuple(item.get("invalid_evidence_ids") or []),
            )
        )
    return sorted(rows)


def is_repair_no_progress(
    before: SceneReaderJourneyBatchResult,
    after: SceneReaderJourneyBatchResult,
    paragraph_ids_by_scene: dict[int, set[str]],
) -> bool:
    before_v = collect_oos_violations(before, paragraph_ids_by_scene)
    after_v = collect_oos_violations(after, paragraph_ids_by_scene)
    if not before_v:
        return False
    if violation_fingerprint(before_v) == violation_fingerprint(after_v):
        return True
    # Also: target fields unchanged even if other noise differs.
    before_nodes = {
        (v["target_path"], json.dumps(v["original_invalid_node"], sort_keys=True))
        for v in before_v
    }
    after_map = {
        v["target_path"]: json.dumps(v["original_invalid_node"], sort_keys=True)
        for v in after_v
    }
    if before_nodes and all(
        after_map.get(path) == node for path, node in before_nodes if path in after_map
    ):
        # Same illegal nodes still present with identical content.
        if set(after_map) >= {p for p, _ in before_nodes}:
            return True
    return False


def render_targeted_repair_user_content(context: dict[str, Any], raw_response: str) -> str:
    return (
        "定向修复 Reader Journey Evidence 越界。只返回 patch JSON，禁止重生成完整 Journey。\n\n"
        f"repair_context:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"original_invalid_json:\n{raw_response}\n\n"
        "patch schema: "
        '{"contract_version":"patch-1.0","patches":[{"op":"replace_evidence|remove_evidence_ids|remove_node",'
        '"target_path":"...","target_scene_id":0,"old_evidence_ids":[],"new_evidence_ids":[]}]}'
    )
