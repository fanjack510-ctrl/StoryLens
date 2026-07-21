"""Level → mapped_score mapping for Reader Journey v2.0 (program-owned)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.schemas.reader_journey_v2 import (
    LEVEL_METRIC_KEYS,
    ScoredLevelField,
    SceneReaderJourneyProfileItemV2,
)

DEFAULT_FORMULA_V2_PATH = Path("config/reader_journey_formulas_v2.json")

DEFAULT_LEVEL_MAP = {
    0: 10,
    1: 30,
    2: 50,
    3: 65,
    4: 80,
    5: 95,
}
DEFAULT_NO_EVIDENCE_CAP = 40


def load_formula_v2_config(path: Path = DEFAULT_FORMULA_V2_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "version": "2.0",
            "level_to_mapped_score": {str(k): v for k, v in DEFAULT_LEVEL_MAP.items()},
            "no_evidence_mapped_score_cap": DEFAULT_NO_EVIDENCE_CAP,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def level_to_mapped_score(
    level: int,
    *,
    has_evidence: bool,
    config: dict[str, Any] | None = None,
) -> int:
    cfg = config or load_formula_v2_config()
    raw_map = cfg.get("level_to_mapped_score") or {}
    mapping = {int(k): int(v) for k, v in raw_map.items()} or dict(DEFAULT_LEVEL_MAP)
    capped_level = max(0, min(5, int(level)))
    score = int(mapping.get(capped_level, DEFAULT_LEVEL_MAP[capped_level]))
    if not has_evidence:
        cap = int(cfg.get("no_evidence_mapped_score_cap", DEFAULT_NO_EVIDENCE_CAP))
        score = min(score, cap)
    return max(0, min(100, score))


def apply_mapped_scores(
    field: ScoredLevelField,
    *,
    config: dict[str, Any] | None = None,
) -> ScoredLevelField:
    """Overwrite mapped_score from level; model-provided mapped_score is ignored."""
    has_evidence = bool(field.evidence_paragraph_ids)
    mapped = level_to_mapped_score(field.level, has_evidence=has_evidence, config=config)
    return field.model_copy(update={"mapped_score": mapped})


def apply_profile_mapped_scores(
    profile: SceneReaderJourneyProfileItemV2,
    *,
    config: dict[str, Any] | None = None,
) -> SceneReaderJourneyProfileItemV2:
    cfg = config or load_formula_v2_config()
    data = profile.model_dump()
    for key in LEVEL_METRIC_KEYS:
        raw = data.get(key)
        if not isinstance(raw, dict):
            continue
        field = ScoredLevelField.model_validate(raw)
        data[key] = apply_mapped_scores(field, config=cfg).model_dump()
    return SceneReaderJourneyProfileItemV2.model_validate(data)


def mapped_or_zero(field: ScoredLevelField | None) -> float:
    if field is None:
        return 0.0
    if field.mapped_score is None:
        return float(level_to_mapped_score(field.level, has_evidence=bool(field.evidence_paragraph_ids)))
    return float(field.mapped_score)
