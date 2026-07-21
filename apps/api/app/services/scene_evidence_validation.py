"""Work-agnostic Scene evidence mapping validation (CHG-20260721-012).

Does not retune Reader Journey V2 score weights/formulas.
Never branches on book title, character name, or hard-coded scene ids.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Sequence

from app.services.validation_errors import StructuralValidationError

def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "scene_evidence_validation.json").exists():
            return parent
    return here.parents[4]


REPO_ROOT = _repo_root()
CONFIG_PATH = REPO_ROOT / "config" / "scene_evidence_validation.json"

FieldClass = Literal["local", "holistic", "hybrid", "unknown"]


@dataclass(frozen=True)
class EvidenceFieldView:
    """Normalized view of one analysis field's evidence + rationale/summary."""

    field_name: str
    evidence_paragraph_ids: tuple[str, ...]
    rationale: str = ""
    required: bool = False


@dataclass
class BoundaryMeta:
    signals: list[str] = field(default_factory=list)
    suspected_split_points: list[str] = field(default_factory=list)
    consolidation_confidence: float | None = None
    boundary_confidence: float | None = None
    paragraph_count: int | None = None
    multiple_structure_tasks: bool = False


@dataclass
class EvidenceValidationIssue:
    error_code: str
    message: str
    details: dict[str, Any]
    repairable: bool = True
    suggested_action: str | None = None


class SceneEvidenceValidationError(StructuralValidationError):
    """Structured evidence / boundary business validation failure."""

    def __init__(
        self,
        message: str,
        error_code: str,
        *,
        details: dict[str, Any] | None = None,
        repairable: bool = True,
        suggested_action: str | None = None,
        no_model_repair: bool | None = None,
    ) -> None:
        repair_context = {
            "details": details or {},
            "repairable": repairable,
            "suggested_action": suggested_action,
        }
        if no_model_repair is None:
            no_model_repair = not repairable
        super().__init__(
            message,
            error_code,
            no_model_repair=no_model_repair,
            failed_field=None,
            repair_context=repair_context,
        )
        self.details = details or {}
        self.repairable = repairable
        self.suggested_action = suggested_action


@lru_cache(maxsize=1)
def load_evidence_validation_config() -> dict[str, Any]:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("scene_evidence_validation.json must be an object")
    return raw


def field_class_for(field_name: str, config: Mapping[str, Any] | None = None) -> FieldClass:
    cfg = config or load_evidence_validation_config()
    classes = cfg.get("field_classes") or {}
    base = field_name.split(".")[0]
    # key_actions.0 → key_actions
    if base == "key_actions" or field_name.startswith("key_actions"):
        base = "key_actions"
    for kind in ("local", "holistic", "hybrid"):
        names = classes.get(kind) or []
        if base in names or field_name in names:
            return kind  # type: ignore[return-value]
    return "unknown"


def normalize_rationale(text: str | None) -> str:
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", str(text)).strip().lower()
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"[，。！？、；：,.!?;:\"'“”‘’（）()【】\[\]…—\-_/\\]", "", value)
    return value


def _tokenize(text: str) -> set[str]:
    normalized = normalize_rationale(text)
    if not normalized:
        return set()
    # Character bigrams for short Chinese rationales; also keep 2+ char alnum runs.
    tokens: set[str] = set()
    latin = re.findall(r"[a-z0-9]{2,}", normalized)
    tokens.update(latin)
    compact = re.sub(r"[a-z0-9]+", "", normalized)
    if len(compact) <= 1:
        if compact:
            tokens.add(compact)
    else:
        for i in range(len(compact) - 1):
            tokens.add(compact[i : i + 2])
    return tokens


def rationale_jaccard(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def dedupe_preserve_order(ids: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in ids:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def is_full_scene_evidence(
    evidence_ids: Sequence[str],
    scene_paragraph_ids: Sequence[str],
) -> bool:
    scene_set = {str(x) for x in scene_paragraph_ids}
    evid_set = {str(x) for x in evidence_ids}
    return bool(scene_set) and evid_set == scene_set


def scene_length_band(paragraph_count: int, config: Mapping[str, Any] | None = None) -> str:
    cfg = config or load_evidence_validation_config()
    bands = cfg.get("scene_length_bands") or {}
    micro = int(bands.get("micro_max_paragraphs", 3))
    short = int(bands.get("short_max_paragraphs", 6))
    if paragraph_count <= micro:
        return "micro"
    if paragraph_count <= short:
        return "short"
    return "medium_long"


def assess_boundary_too_broad(
    *,
    scene_id: str,
    paragraph_count: int,
    boundary: BoundaryMeta | None,
    config: Mapping[str, Any] | None = None,
) -> EvidenceValidationIssue | None:
    """Return SCENE_BOUNDARY_TOO_BROAD when generic boundary signals indicate multi-event scope."""
    cfg = config or load_evidence_validation_config()
    meta = boundary or BoundaryMeta(paragraph_count=paragraph_count)
    signals = list(meta.signals or [])
    known = set(cfg.get("boundary_signals") or [])

    if meta.consolidation_confidence is not None and meta.consolidation_confidence < 0.45:
        signals.append("low_consolidation_confidence")
    if meta.boundary_confidence is not None and meta.boundary_confidence < 0.45:
        signals.append("low_boundary_confidence")
    if paragraph_count >= 12 and meta.multiple_structure_tasks:
        signals.append("excessive_paragraphs_with_multiple_tasks")
    if len(meta.suspected_split_points or []) >= 2:
        signals.append("multiple_event_clusters")

    # Keep only configured generic signals (no novel-specific strings).
    signals = [s for s in dict.fromkeys(signals) if s in known or s.startswith("generic_")]
    strong = {
        "multiple_event_clusters",
        "excessive_paragraphs_with_multiple_tasks",
        "time_change",
        "location_change",
        "goal_change",
        "conflict_object_change",
    }
    hit_strong = [s for s in signals if s in strong]
    low_conf = [
        s
        for s in signals
        if s in {"low_consolidation_confidence", "low_boundary_confidence"}
    ]
    if len(hit_strong) >= 2 or (hit_strong and low_conf):
        err_meta = (cfg.get("error_codes") or {}).get("SCENE_BOUNDARY_TOO_BROAD") or {}
        return EvidenceValidationIssue(
            error_code="SCENE_BOUNDARY_TOO_BROAD",
            message="current scene may contain multiple independent events",
            details={
                "scene_id": scene_id,
                "scene_paragraph_count": paragraph_count,
                "boundary_signals": signals,
                "suspected_split_points": list(meta.suspected_split_points or []),
                "repairable": bool(err_meta.get("repairable", True)),
                "suggested_action": err_meta.get("suggested_action", "rerun_scene_boundary"),
            },
            repairable=bool(err_meta.get("repairable", True)),
            suggested_action=str(err_meta.get("suggested_action") or "rerun_scene_boundary"),
        )
    return None


def _duplicate_rationale_groups(
    fields: Sequence[EvidenceFieldView],
    *,
    threshold: float,
) -> list[list[str]]:
    groups: list[list[str]] = []
    used: set[str] = set()
    for i, left in enumerate(fields):
        if left.field_name in used:
            continue
        group = [left.field_name]
        for right in fields[i + 1 :]:
            if right.field_name in used:
                continue
            same_exact = normalize_rationale(left.rationale) == normalize_rationale(
                right.rationale
            ) and bool(normalize_rationale(left.rationale))
            similar = rationale_jaccard(left.rationale, right.rationale) >= threshold
            if same_exact or similar:
                group.append(right.field_name)
                used.add(right.field_name)
        if len(group) >= 2:
            used.add(left.field_name)
            groups.append(group)
    return groups


def _mechanical_template_rationale(text: str) -> bool:
    normalized = normalize_rationale(text)
    if not normalized:
        return True
    # Generic "whole scene embodies X" templates without field-specific angle.
    patterns = (
        r"本场全部内容体现",
        r"整场都体现",
        r"全部段落体现",
        r"allcontentshow",
        r"wholesceneembodies",
        r"entirelyreflects",
    )
    return any(re.search(p, text) or re.search(p, normalized) for p in patterns)


def validate_evidence_mapping(
    *,
    scene_id: str,
    scene_paragraph_ids: Sequence[str],
    fields: Sequence[EvidenceFieldView],
    boundary: BoundaryMeta | None = None,
    config: Mapping[str, Any] | None = None,
) -> None:
    """Validate evidence mapping. Raises SceneEvidenceValidationError on hard failures."""
    cfg = config or load_evidence_validation_config()
    ordered_scene = dedupe_preserve_order(list(scene_paragraph_ids))
    scene_set = set(ordered_scene)
    paragraph_count = len(ordered_scene)
    band = scene_length_band(paragraph_count, cfg)
    overbroad_cfg = cfg.get("overbroad_reuse") or {}
    jaccard_threshold = float(overbroad_cfg.get("rationale_jaccard_duplicate", 0.92))

    # 1) Boundary-first (never mask as evidence overbroad).
    boundary_issue = assess_boundary_too_broad(
        scene_id=scene_id,
        paragraph_count=paragraph_count,
        boundary=boundary,
        config=cfg,
    )
    if boundary_issue is not None:
        raise SceneEvidenceValidationError(
            boundary_issue.message,
            boundary_issue.error_code,
            details=boundary_issue.details,
            repairable=boundary_issue.repairable,
            suggested_action=boundary_issue.suggested_action,
        )

    # 2) Base legality.
    missing_fields: list[str] = []
    outside: list[dict[str, str]] = []
    empty_rationale_required: list[str] = []
    for item in fields:
        ids = dedupe_preserve_order(item.evidence_paragraph_ids)
        if item.required and not ids:
            missing_fields.append(item.field_name)
        if item.required and ids and not (item.rationale or "").strip():
            empty_rationale_required.append(item.field_name)
        for pid in ids:
            if pid not in scene_set:
                outside.append({"field_path": item.field_name, "paragraph_id": pid})

    if outside:
        err_meta = (cfg.get("error_codes") or {}).get("EVIDENCE_OUTSIDE_SCENE") or {}
        raise SceneEvidenceValidationError(
            "evidence paragraph ids must belong to the current scene",
            "EVIDENCE_OUTSIDE_SCENE",
            details={
                "scene_id": scene_id,
                "invalid_paragraph_ids": [row["paragraph_id"] for row in outside],
                "affected_fields": sorted({row["field_path"] for row in outside}),
                "repairable": True,
                "suggested_action": err_meta.get("suggested_action", "evidence_remap_repair"),
            },
            repairable=True,
            suggested_action=str(err_meta.get("suggested_action") or "evidence_remap_repair"),
        )

    if missing_fields:
        err_meta = (cfg.get("error_codes") or {}).get("EVIDENCE_MISSING") or {}
        raise SceneEvidenceValidationError(
            "required fields must include evidence",
            "EVIDENCE_MISSING",
            details={
                "scene_id": scene_id,
                "affected_fields": missing_fields,
                "repairable": True,
                "suggested_action": err_meta.get("suggested_action", "evidence_remap_repair"),
            },
            repairable=True,
            suggested_action=str(err_meta.get("suggested_action") or "evidence_remap_repair"),
        )

    # Empty rationale on required evidenced fields → soft signal only unless overbroad.
    active = [
        EvidenceFieldView(
            field_name=item.field_name,
            evidence_paragraph_ids=tuple(dedupe_preserve_order(item.evidence_paragraph_ids)),
            rationale=item.rationale or "",
            required=item.required,
        )
        for item in fields
        if dedupe_preserve_order(item.evidence_paragraph_ids)
        or (item.rationale or "").strip()
    ]

    local_fields = [f for f in active if field_class_for(f.field_name, cfg) == "local"]
    full_scene_local = [
        f for f in local_fields if is_full_scene_evidence(f.evidence_paragraph_ids, ordered_scene)
    ]
    local_needing = [f for f in local_fields if f.evidence_paragraph_ids]
    ratio = (
        (len(full_scene_local) / len(local_needing)) if local_needing else 0.0
    )

    # Micro / short: shared full-scene evidence is allowed.
    if band in {"micro", "short"}:
        return

    # Medium-long: holistic/hybrid full-scene is fine; local overbroad needs multi-factor.
    min_local = int(overbroad_cfg.get("min_local_fields_full_scene", 5))
    min_ratio = float(overbroad_cfg.get("min_local_full_scene_ratio", 0.7))

    if len(full_scene_local) < min_local or ratio < min_ratio:
        return

    # Shared identical full-scene set among those local fields?
    sets = {tuple(sorted(f.evidence_paragraph_ids)) for f in full_scene_local}
    if len(sets) != 1:
        return

    dup_groups = _duplicate_rationale_groups(full_scene_local, threshold=jaccard_threshold)
    mechanical = [
        f.field_name
        for f in full_scene_local
        if _mechanical_template_rationale(f.rationale) or not (f.rationale or "").strip()
    ]
    # Must have highly duplicated / empty / mechanical rationales — not evidence alone.
    rationale_bad = bool(dup_groups) or len(mechanical) >= min_local
    if not rationale_bad:
        return

    shared = list(next(iter(sets)))
    err_meta = (cfg.get("error_codes") or {}).get("EVIDENCE_OVERBROAD_REUSE") or {}
    raise SceneEvidenceValidationError(
        "local analysis fields reuse full-scene evidence indiscriminately",
        "EVIDENCE_OVERBROAD_REUSE",
        details={
            "scene_id": scene_id,
            "scene_paragraph_count": paragraph_count,
            "affected_fields": [f.field_name for f in full_scene_local],
            "shared_evidence": shared,
            "local_field_count": len(local_needing),
            "full_scene_reuse_ratio": round(ratio, 4),
            "duplicate_rationale_groups": dup_groups,
            "mechanical_or_empty_rationale_fields": mechanical,
            "empty_rationale_required_fields": empty_rationale_required,
            "repairable": True,
            "suggested_action": err_meta.get("suggested_action", "evidence_remap_repair"),
            "aux_reason": "EVIDENCE_RATIONALE_DUPLICATED" if dup_groups else None,
        },
        repairable=True,
        suggested_action=str(err_meta.get("suggested_action") or "evidence_remap_repair"),
    )


def scene_analysis_fields_from_result(result: Any) -> list[EvidenceFieldView]:
    """Build EvidenceFieldView list from SceneAnalysisResult (summary as rationale)."""
    views: list[EvidenceFieldView] = []

    def add(name: str, field_obj: Any, *, required: bool = False) -> None:
        if field_obj is None:
            return
        summary = str(getattr(field_obj, "summary", "") or "")
        ids = list(getattr(field_obj, "evidence_paragraph_ids", []) or [])
        # Skip completely empty optional fields.
        if not required and not summary.strip() and not ids:
            return
        views.append(
            EvidenceFieldView(
                field_name=name,
                evidence_paragraph_ids=tuple(ids),
                rationale=summary,
                required=required,
            )
        )

    add("entry_state", result.entry_state, required=True)
    add("goal", result.goal, required=True)
    add("obstacle", result.obstacle, required=False)
    for index, action in enumerate(getattr(result, "key_actions", []) or []):
        add(f"key_actions.{index}", action, required=True)
    add("turning_point", result.turning_point, required=False)
    add("outcome", result.outcome, required=True)
    add("unresolved_question", result.unresolved_question, required=False)
    return views


def v2_level_fields_from_profile(profile: Any) -> list[EvidenceFieldView]:
    """Build EvidenceFieldView list from SceneReaderJourneyProfileItemV2 level metrics."""
    cfg = load_evidence_validation_config()
    names: list[str] = []
    for kind in ("local", "holistic", "hybrid"):
        names.extend(list((cfg.get("field_classes") or {}).get(kind) or []))
    views: list[EvidenceFieldView] = []
    for name in names:
        # Skip scene-analysis-only names when absent on V2 profile.
        field_obj = getattr(profile, name, None)
        if field_obj is None:
            continue
        if not hasattr(field_obj, "evidence_paragraph_ids"):
            continue
        rationale = str(getattr(field_obj, "rationale", "") or "")
        ids = list(getattr(field_obj, "evidence_paragraph_ids", []) or [])
        if not ids and not rationale.strip():
            continue
        views.append(
            EvidenceFieldView(
                field_name=name,
                evidence_paragraph_ids=tuple(ids),
                rationale=rationale,
                required=False,
            )
        )
    return views


def apply_evidence_remap_patch(
    *,
    fields: dict[str, dict[str, Any]],
    patch: Mapping[str, Mapping[str, Any]],
    allowed_ids: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """Apply evidence-only remap. Never mutates level / mapped_score / diagnosis scores.

    ``fields`` and return value: field_name → {evidence_paragraph_ids, rationale?, level?, ...}
    """
    allowed = set(dedupe_preserve_order(list(allowed_ids)))
    forbidden_keys = {
        "level",
        "mapped_score",
        "plot_progress",
        "reading_tension",
        "pacing_speed",
        "hook",
        "payoff",
        "reading_momentum",
        "diagnosis",
        "primary_diagnosis",
        "question_lifecycle",
    }
    out: dict[str, dict[str, Any]] = {
        key: dict(value) for key, value in fields.items()
    }
    for field_name, change in patch.items():
        if field_name not in out:
            continue
        target = dict(out[field_name])
        for banned in forbidden_keys:
            if banned in change:
                # Ignore attempts to rewrite scores/levels.
                continue
        if "evidence_paragraph_ids" in change:
            ids = dedupe_preserve_order(list(change.get("evidence_paragraph_ids") or []))
            target["evidence_paragraph_ids"] = [pid for pid in ids if pid in allowed]
        if "rationale" in change and isinstance(change.get("rationale"), str):
            # Allow short field-targeted rationale rewrite only.
            target["rationale"] = str(change["rationale"])[:240]
        out[field_name] = target
    return out


def evidence_repair_attempt_allowed(
    *,
    prior_attempts: int,
    config: Mapping[str, Any] | None = None,
) -> bool:
    cfg = config or load_evidence_validation_config()
    max_attempts = int((cfg.get("overbroad_reuse") or {}).get("max_evidence_repair_attempts", 1))
    return prior_attempts < max_attempts


def user_copy_for_error(error_code: str) -> dict[str, str]:
    cfg = load_evidence_validation_config()
    meta = (cfg.get("error_codes") or {}).get(error_code) or {}
    return {
        "title": str(meta.get("user_title_zh") or "分析未完成"),
        "lead": str(meta.get("user_lead_zh") or ""),
        "button": str(meta.get("user_button_zh") or "查看问题"),
        "suggested_action": str(meta.get("suggested_action") or ""),
    }


def classify_evidence_error_payload(exc: BaseException) -> dict[str, Any] | None:
    if isinstance(exc, SceneEvidenceValidationError):
        return {
            "error_code": exc.error_code,
            "message": str(exc),
            "details": dict(exc.details),
            "repairable": bool(exc.repairable),
            "suggested_action": exc.suggested_action,
        }
    if isinstance(exc, StructuralValidationError) and getattr(exc, "repair_context", None):
        ctx = exc.repair_context or {}
        details = ctx.get("details") if isinstance(ctx, dict) else None
        if isinstance(details, dict) and exc.error_code in {
            "EVIDENCE_OVERBROAD_REUSE",
            "SCENE_BOUNDARY_TOO_BROAD",
            "EVIDENCE_OUTSIDE_SCENE",
            "EVIDENCE_MISSING",
        }:
            return {
                "error_code": exc.error_code,
                "message": str(exc),
                "details": details,
                "repairable": bool(ctx.get("repairable", True)),
                "suggested_action": ctx.get("suggested_action"),
            }
    return None
