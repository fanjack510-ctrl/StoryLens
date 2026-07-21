"""Post-process helpers for Reader Journey v2.0 runs (no model calls)."""

from __future__ import annotations

from typing import Any

from app.schemas.reader_journey_v2 import (
    FORMULA_VERSION_V2,
    SceneReaderJourneyProfileItemV2,
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


def finalize_v2_profiles(
    profiles: list[SceneReaderJourneyProfileItemV2],
) -> tuple[list[SceneReaderJourneyProfileItemV2], dict[str, Any]]:
    """Map levels, derive metrics/dropoff, build lifecycle + diagnoses."""
    derived = derive_chapter_profiles(profiles)
    lifecycle = build_question_lifecycle(derived)
    diagnoses = diagnose_chapter(derived, lifecycle=lifecycle)
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
    }
    return derived, stats
