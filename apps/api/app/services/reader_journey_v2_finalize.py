"""Post-process helpers for Reader Journey v2.0 runs (no model calls)."""

from __future__ import annotations

from typing import Any

from app.schemas.reader_journey_v2 import (
    FORMULA_VERSION_V2,
    SceneReaderJourneyProfileItemV2,
)
from app.services.reader_journey_v2_config import (
    load_formula_v2_bundle,
    load_scene_role_targets_bundle,
)
from app.services.reader_journey_v2_derivation import (
    chapter_mean_reading_momentum,
    derive_chapter_profiles,
)
from app.services.reader_journey_v2_diagnosis import diagnose_chapter
from app.services.reader_journey_v2_question_lifecycle import (
    build_question_lifecycle,
    lifecycle_status_counts,
)


def build_config_provenance_block() -> dict[str, Any]:
    """Public (path-free) provenance for role targets + formulas_v2."""
    roles = load_scene_role_targets_bundle()
    formulas = load_formula_v2_bundle()
    quality_flags: list[str] = []
    quality_flags.extend(roles.provenance.quality_flags)
    quality_flags.extend(formulas.provenance.quality_flags)
    return {
        "scene_role_targets": roles.provenance.to_public_dict(),
        "formulas_v2": formulas.provenance.to_public_dict(),
        "quality_flags": sorted(set(quality_flags)),
        "derivation_formula_version": FORMULA_VERSION_V2,
        "role_targets_ready": roles.ok,
    }


def finalize_v2_profiles(
    profiles: list[SceneReaderJourneyProfileItemV2],
) -> tuple[list[SceneReaderJourneyProfileItemV2], dict[str, Any]]:
    """Map levels, derive metrics/dropoff, build lifecycle + diagnoses."""
    role_bundle = load_scene_role_targets_bundle()
    formula_bundle = load_formula_v2_bundle()
    derived = derive_chapter_profiles(
        profiles,
        formula_config=formula_bundle.config,
        role_targets=role_bundle,
    )
    lifecycle = build_question_lifecycle(derived)
    diagnoses = diagnose_chapter(derived, lifecycle=lifecycle)
    provenance = {
        "scene_role_targets": role_bundle.provenance.to_public_dict(),
        "formulas_v2": formula_bundle.provenance.to_public_dict(),
        "quality_flags": sorted(
            set(role_bundle.provenance.quality_flags)
            | set(formula_bundle.provenance.quality_flags)
        ),
        "derivation_formula_version": FORMULA_VERSION_V2,
        "role_targets_ready": role_bundle.ok,
    }
    stats: dict[str, Any] = {
        "formula_version": FORMULA_VERSION_V2,
        "contract_family": "reader_journey_v2",
        "average_reading_momentum": chapter_mean_reading_momentum(derived),
        "question_lifecycle": [item.model_dump() for item in lifecycle],
        "question_lifecycle_counts": lifecycle_status_counts(lifecycle),
        "scene_diagnoses": [item.model_dump() for item in diagnoses],
        "main_curve_scene_count": sum(
            1 for item in derived if item.include_in_main_curve is not False and item.node_type != "beat"
        ),
        "beat_count": sum(1 for item in derived if item.node_type == "beat"),
        # Explicitly document removal of legacy consecutive-no-payoff floor.
        "legacy_consecutive_no_payoff_floor_applied": False,
        "config_provenance": provenance,
    }
    return derived, stats
