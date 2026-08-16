"""Post-process helpers for Reader Journey v2.0 runs (no model calls)."""

from __future__ import annotations

from typing import Any, Mapping

from app.schemas.reader_journey_v2 import (
    FORMULA_VERSION_V2,
    SceneReaderJourneyProfileItemV2,
)
from app.services.reader_journey_v2_config import (
    load_formula_v2_bundle,
    load_scene_role_targets_bundle,
)
from app.narrative_core.long_novel.chapter_focus import apply_formula_weights
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
    *,
    formula_weights: Mapping[str, Mapping[str, float]] | None = None,
    suppressed_diagnoses: frozenset[str] | None = None,
) -> tuple[list[SceneReaderJourneyProfileItemV2], dict[str, Any]]:
    """Map levels, derive metrics/dropoff, build lifecycle + diagnoses.

    ``formula_weights`` comes from the book's confirmed profile. Omitted or empty means the
    shipped weighting, so every caller that predates the profile layer keeps its exact
    behaviour and an unprofiled book is unaffected. ``suppressed_diagnoses`` works the same
    way: empty means every code fires, which is what an unconfirmed book gets.
    """
    role_bundle = load_scene_role_targets_bundle()
    formula_bundle = load_formula_v2_bundle()
    config = apply_formula_weights(formula_bundle.config, formula_weights or {})
    derived = derive_chapter_profiles(
        profiles,
        formula_config=config,
        role_targets=role_bundle,
    )
    lifecycle = build_question_lifecycle(derived)
    diagnoses = diagnose_chapter(
        derived, lifecycle=lifecycle, suppressed=suppressed_diagnoses
    )
    provenance = {
        "scene_role_targets": role_bundle.provenance.to_public_dict(),
        "formulas_v2": formula_bundle.provenance.to_public_dict(),
        "quality_flags": sorted(
            set(role_bundle.provenance.quality_flags)
            | set(formula_bundle.provenance.quality_flags)
        ),
        "derivation_formula_version": FORMULA_VERSION_V2,
        "role_targets_ready": role_bundle.ok,
        # Which weighting actually ran. Without this a stored result cannot be read back:
        # two chapters of different books would carry the same formula_version and different
        # numbers, with nothing on the record saying why.
        "profile_formula_weights": {
            block: dict(table) for block, table in (formula_weights or {}).items()
        },
        # Which defect flags this book's profile withdrew. A suppressed warning that leaves
        # no trace is indistinguishable from a warning that never applied.
        "profile_suppressed_diagnoses": sorted(suppressed_diagnoses or ()),
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
