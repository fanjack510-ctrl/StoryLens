"""Legacy Reader Journey compatibility helpers for v2.0 coexistence."""

from __future__ import annotations

from typing import Any

from app.schemas.reader_journey_v2 import (
    LEGACY_CONTRACT_VERSIONS,
    SCENE_CONTRACT_VERSION_V2,
    SCENE_PROMPT_VERSION_V2,
)


def is_legacy_contract(contract_version: str | None) -> bool:
    if not contract_version:
        return True
    version = str(contract_version).strip()
    if version in LEGACY_CONTRACT_VERSIONS:
        return True
    if version.startswith("1."):
        return True
    return False


def is_v2_contract(contract_version: str | None) -> bool:
    if not contract_version:
        return False
    version = str(contract_version).strip()
    return version == SCENE_CONTRACT_VERSION_V2 or version.startswith("2.")


def calibration_label(contract_version: str | None, *, prompt_version: str | None = None) -> str:
    """Return display/calibration label for API consumers."""
    if is_v2_contract(contract_version):
        return "v2_calibrated"
    # Old analyses are readable but not on the v2 formula scale.
    _ = prompt_version
    return "legacy_uncalibrated"


def enrich_result_compatibility(
    payload: dict[str, Any],
    *,
    scene_contract_version: str | None,
    scene_prompt_version: str | None = None,
    formula_version: str | None = None,
) -> dict[str, Any]:
    """Attach non-breaking compatibility fields for dual-version API responses."""
    enriched = dict(payload)
    enriched["contract_version"] = scene_contract_version
    enriched["scene_contract_version"] = scene_contract_version
    enriched["scene_prompt_version"] = scene_prompt_version
    enriched["formula_version"] = formula_version
    enriched["calibration_status_label"] = calibration_label(
        scene_contract_version, prompt_version=scene_prompt_version
    )
    enriched["legacy_uncalibrated"] = is_legacy_contract(scene_contract_version)
    enriched["display_mode"] = "v2" if is_v2_contract(scene_contract_version) else "legacy_v1"
    enriched["current_v2_prompt_version"] = SCENE_PROMPT_VERSION_V2
    enriched["current_v2_contract_version"] = SCENE_CONTRACT_VERSION_V2
    return enriched
