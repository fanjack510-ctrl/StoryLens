"""Reader Journey pipeline version resolution (v2 vs legacy_v1).

Product default for *new* runs is v2. Existing contract 1.x runs remain legacy.
Does not retune formulas or auto-upgrade old runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.schemas.reader_journey_v2 import (
    CHAPTER_PROMPT_VERSION_V2,
    FORMULA_VERSION_V2,
    SCENE_CONTRACT_VERSION_V2,
    SCENE_PROMPT_VERSION_V2,
)
from app.services.reader_journey_v2_compatibility import is_legacy_contract, is_v2_contract

DEFAULT_PIPELINE_VERSION_PATH = Path("config/reader_journey_pipeline_version.json")

SOURCE_MODE_V2_NATIVE = "v2_native"
SOURCE_MODE_LEGACY = "legacy_adapter"
SCORES_ORIGIN_PROGRAM = "program_finalize_v2"
DIAGNOSES_ORIGIN_PROGRAM = "program_diagnose_chapter"
DISPLAY_BANNER_V2 = "V2真实正文分析"
DISPLAY_BANNER_LEGACY = "旧版未校准分析，仅供章内走势参考"


@dataclass(frozen=True)
class ReaderJourneyPipelineVersions:
    pipeline_id: str
    contract_version: str
    chapter_contract_version: str
    scene_prompt_version: str
    chapter_prompt_version: str
    formula_version: str
    formula_config_path: str
    source_mode: str
    display_banner: str
    scores_origin: str
    diagnoses_origin: str

    def as_run_fields(self) -> dict[str, str]:
        return {
            "scene_contract_version": self.contract_version,
            "chapter_contract_version": self.chapter_contract_version,
            "scene_prompt_version": self.scene_prompt_version,
            "chapter_prompt_version": self.chapter_prompt_version,
            "formula_version": self.formula_version,
        }

    def provenance(self) -> dict[str, str]:
        return {
            "source_mode": self.source_mode,
            "display_banner": self.display_banner,
            "scores_origin": self.scores_origin,
            "diagnoses_origin": self.diagnoses_origin,
            "pipeline_id": self.pipeline_id,
        }


_V2_FALLBACK = ReaderJourneyPipelineVersions(
    pipeline_id="v2",
    contract_version=SCENE_CONTRACT_VERSION_V2,
    chapter_contract_version=SCENE_CONTRACT_VERSION_V2,
    scene_prompt_version=SCENE_PROMPT_VERSION_V2,
    chapter_prompt_version=CHAPTER_PROMPT_VERSION_V2,
    formula_version=FORMULA_VERSION_V2,
    formula_config_path="config/reader_journey_formulas_v2.json",
    source_mode=SOURCE_MODE_V2_NATIVE,
    display_banner=DISPLAY_BANNER_V2,
    scores_origin=SCORES_ORIGIN_PROGRAM,
    diagnoses_origin=DIAGNOSES_ORIGIN_PROGRAM,
)


def load_pipeline_version_config(
    path: Path = DEFAULT_PIPELINE_VERSION_PATH,
) -> dict[str, Any]:
    if not path.exists():
        return {
            "version": "1.0",
            "default_pipeline": "v2",
            "pipelines": {"v2": _V2_FALLBACK.__dict__},
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _versions_from_block(pipeline_id: str, block: dict[str, Any]) -> ReaderJourneyPipelineVersions:
    return ReaderJourneyPipelineVersions(
        pipeline_id=pipeline_id,
        contract_version=str(block.get("contract_version", SCENE_CONTRACT_VERSION_V2)),
        chapter_contract_version=str(
            block.get("chapter_contract_version", block.get("contract_version", SCENE_CONTRACT_VERSION_V2))
        ),
        scene_prompt_version=str(block.get("scene_prompt_version", SCENE_PROMPT_VERSION_V2)),
        chapter_prompt_version=str(block.get("chapter_prompt_version", CHAPTER_PROMPT_VERSION_V2)),
        formula_version=str(block.get("formula_version", FORMULA_VERSION_V2)),
        formula_config_path=str(
            block.get("formula_config", "config/reader_journey_formulas_v2.json")
        ),
        source_mode=str(block.get("source_mode", SOURCE_MODE_V2_NATIVE)),
        display_banner=str(block.get("display_banner", DISPLAY_BANNER_V2)),
        scores_origin=str(block.get("scores_origin", SCORES_ORIGIN_PROGRAM)),
        diagnoses_origin=str(block.get("diagnoses_origin", DIAGNOSES_ORIGIN_PROGRAM)),
    )


def resolve_versions_for_new_run(
    *,
    path: Path = DEFAULT_PIPELINE_VERSION_PATH,
    pipeline_id: str | None = None,
) -> ReaderJourneyPipelineVersions:
    """Versions for newly created Reader Journey runs (product default)."""
    cfg = load_pipeline_version_config(path)
    chosen = pipeline_id or str(cfg.get("default_pipeline") or "v2")
    pipelines = cfg.get("pipelines") or {}
    block = pipelines.get(chosen)
    if not isinstance(block, dict):
        if chosen == "legacy_v1":
            from app.schemas.reader_journey import (
                CHAPTER_CONTRACT_VERSION,
                CHAPTER_PROMPT_VERSION,
                SCENE_CONTRACT_VERSION,
                SCENE_PROMPT_VERSION,
            )

            return ReaderJourneyPipelineVersions(
                pipeline_id="legacy_v1",
                contract_version=SCENE_CONTRACT_VERSION,
                chapter_contract_version=CHAPTER_CONTRACT_VERSION,
                scene_prompt_version=SCENE_PROMPT_VERSION,
                chapter_prompt_version=CHAPTER_PROMPT_VERSION,
                formula_version="1.0",
                formula_config_path="config/reader_journey_formulas.json",
                source_mode=SOURCE_MODE_LEGACY,
                display_banner=DISPLAY_BANNER_LEGACY,
                scores_origin="legacy_engagement",
                diagnoses_origin="legacy_chapter_synthesis",
            )
        return _V2_FALLBACK
    return _versions_from_block(chosen, block)


def is_v2_journey_run(journey_run: Any) -> bool:
    contract = getattr(journey_run, "scene_contract_version", None)
    if is_v2_contract(str(contract or "")):
        return True
    try:
        details = json.loads(getattr(journey_run, "failure_details_json", None) or "{}")
    except (TypeError, json.JSONDecodeError):
        details = {}
    return details.get("source_mode") == SOURCE_MODE_V2_NATIVE


def is_legacy_journey_run(journey_run: Any) -> bool:
    if is_v2_journey_run(journey_run):
        return False
    contract = getattr(journey_run, "scene_contract_version", None)
    return is_legacy_contract(str(contract or "")) or True


def merge_run_provenance(existing_json: str | None, versions: ReaderJourneyPipelineVersions) -> str:
    try:
        details = json.loads(existing_json or "{}")
    except json.JSONDecodeError:
        details = {}
    if not isinstance(details, dict):
        details = {}
    details.update(versions.provenance())
    return json.dumps(details, ensure_ascii=False)


def load_formula_for_pipeline(versions: ReaderJourneyPipelineVersions) -> dict[str, Any]:
    from app.services.reader_journey_engagement import load_formula_config

    return load_formula_config(Path(versions.formula_config_path))


def new_journey_version_fields(
    versions: ReaderJourneyPipelineVersions | None = None,
) -> dict[str, Any]:
    """Fields + provenance JSON for a newly created Reader Journey run."""
    chosen = versions or resolve_versions_for_new_run()
    formula = load_formula_for_pipeline(chosen)
    fields = chosen.as_run_fields()
    return {
        **fields,
        "formula_version": chosen.formula_version or str(formula.get("version", chosen.formula_version)),
        "genre": str(formula.get("default_genre", "suspense")),
        "failure_details_json": merge_run_provenance(None, chosen),
        "_pipeline_versions": chosen,
    }
