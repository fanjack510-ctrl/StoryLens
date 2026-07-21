"""Deterministic derived metrics for Reader Journey v2.0."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from app.schemas.reader_journey_v2 import (
    DerivedMetricsV2,
    FORMULA_VERSION_V2,
    SceneReaderJourneyProfileItemV2,
)
from app.services.reader_journey_v2_mapping import (
    apply_profile_mapped_scores,
    load_formula_v2_config,
    mapped_or_zero,
)

DEFAULT_ROLE_TARGETS_PATH = Path("config/scene_role_targets.json")


def load_scene_role_targets(path: Path = DEFAULT_ROLE_TARGETS_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"version": "1.0", "roles": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _clamp_0_100(value: float | Decimal) -> float:
    return float(max(0, min(100, value)))


def _round1(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def fit_to_band(value: float, band: list[float] | tuple[float, float], *, config: dict[str, Any]) -> float:
    """In-band → 90; each point outside band lowers fit by 2; clamp 0–100."""
    fit_cfg = config.get("fit_to_band") or {}
    in_band = float(fit_cfg.get("in_band_score", 90))
    per_point = float(fit_cfg.get("per_point_penalty", 2))
    low, high = float(band[0]), float(band[1])
    if low > high:
        low, high = high, low
    if low <= value <= high:
        return _clamp_0_100(in_band)
    distance = (low - value) if value < low else (value - high)
    return _clamp_0_100(in_band - distance * per_point)


def compute_plot_progress(profile: SceneReaderJourneyProfileItemV2, *, weights: dict[str, float]) -> float:
    total = (
        mapped_or_zero(profile.goal_progress) * float(weights.get("goal_progress", 0.25))
        + mapped_or_zero(profile.conflict_change) * float(weights.get("conflict_change", 0.20))
        + mapped_or_zero(profile.state_change) * float(weights.get("state_change", 0.20))
        + mapped_or_zero(profile.information_gain) * float(weights.get("information_gain", 0.15))
        + mapped_or_zero(profile.character_agency) * float(weights.get("character_agency", 0.10))
        + mapped_or_zero(profile.causal_coherence) * float(weights.get("causal_coherence", 0.10))
    )
    return _clamp_0_100(total)


def compute_reading_tension(profile: SceneReaderJourneyProfileItemV2, *, weights: dict[str, float]) -> float:
    total = (
        mapped_or_zero(profile.curiosity) * float(weights.get("curiosity", 0.40))
        + mapped_or_zero(profile.tension) * float(weights.get("tension", 0.35))
        + mapped_or_zero(profile.emotional_investment) * float(weights.get("emotional_investment", 0.25))
    )
    return _clamp_0_100(total)


def compute_pacing_fit(
    profile: SceneReaderJourneyProfileItemV2,
    *,
    role_targets: dict[str, Any],
    formula_config: dict[str, Any],
) -> float:
    roles = role_targets.get("roles") or {}
    role_cfg = roles.get(profile.scene_role) or {}
    band = role_cfg.get("pacing_speed") or [0, 100]
    return fit_to_band(mapped_or_zero(profile.pacing_speed), band, config=formula_config)


def compute_hook_payoff_fit(
    profile: SceneReaderJourneyProfileItemV2,
    *,
    role_targets: dict[str, Any],
    formula_config: dict[str, Any],
) -> float:
    roles = role_targets.get("roles") or {}
    role_cfg = roles.get(profile.scene_role) or {}
    hook_band = role_cfg.get("hook") or [0, 100]
    payoff_band = role_cfg.get("payoff") or [0, 100]
    hook_w = float(role_cfg.get("hook_weight", 0.5))
    payoff_w = float(role_cfg.get("payoff_weight", 0.5))
    hook_fit = fit_to_band(mapped_or_zero(profile.hook), hook_band, config=formula_config)
    payoff_fit = fit_to_band(mapped_or_zero(profile.payoff), payoff_band, config=formula_config)
    return _clamp_0_100(hook_fit * hook_w + payoff_fit * payoff_w)


def compute_penalties(profile: SceneReaderJourneyProfileItemV2, *, config: dict[str, Any]) -> tuple[float, float, float]:
    pen = config.get("penalties") or {}
    clarity = mapped_or_zero(profile.clarity)
    cognitive = mapped_or_zero(profile.cognitive_load)
    redundancy = mapped_or_zero(profile.redundancy)
    clarity_below = float(pen.get("clarity_below", 60))
    clarity_factor = float(pen.get("clarity_factor", 0.25))
    cognitive_above = float(pen.get("cognitive_load_above", 60))
    cognitive_factor = float(pen.get("cognitive_load_factor", 0.15))
    redundancy_above = float(pen.get("redundancy_above", 50))
    redundancy_factor = float(pen.get("redundancy_factor", 0.10))
    clarity_penalty = max(0.0, (clarity_below - clarity) * clarity_factor) if clarity < clarity_below else 0.0
    cognitive_penalty = (
        max(0.0, (cognitive - cognitive_above) * cognitive_factor) if cognitive > cognitive_above else 0.0
    )
    redundancy_penalty = (
        max(0.0, (redundancy - redundancy_above) * redundancy_factor) if redundancy > redundancy_above else 0.0
    )
    return clarity_penalty, cognitive_penalty, redundancy_penalty


def compute_reading_momentum(
    *,
    plot_progress: float,
    reading_tension: float,
    pacing_fit: float,
    hook_payoff_fit: float,
    clarity_penalty: float,
    cognitive_load_penalty: float,
    redundancy_penalty: float,
    weights: dict[str, float],
) -> float:
    total = (
        plot_progress * float(weights.get("plot_progress", 0.30))
        + reading_tension * float(weights.get("reading_tension", 0.25))
        + pacing_fit * float(weights.get("pacing_fit", 0.20))
        + hook_payoff_fit * float(weights.get("hook_payoff_fit", 0.25))
        - clarity_penalty
        - cognitive_load_penalty
        - redundancy_penalty
    )
    return _clamp_0_100(total)


def base_dropoff_risk(reading_momentum: float) -> float:
    return _clamp_0_100(100.0 - reading_momentum)


def apply_dropoff_adjustments(
    profiles: list[SceneReaderJourneyProfileItemV2],
    *,
    config: dict[str, Any] | None = None,
) -> list[SceneReaderJourneyProfileItemV2]:
    """Derive dropoff_risk from reading_momentum with chapter-level rules.

    Does NOT use the legacy consecutive-no-payoff → floor 55 rule.
    Scene boundary anomalies are marked as data_quality_issue only.
    """
    cfg = config or load_formula_v2_config()
    drop_cfg = cfg.get("dropoff_risk") or {}
    decline_bonus = float(drop_cfg.get("consecutive_decline_bonus", 8))
    low_threshold = float(drop_cfg.get("consecutive_low_momentum_threshold", 45))
    low_count = int(drop_cfg.get("consecutive_low_momentum_count", 3))
    low_bonus = float(drop_cfg.get("consecutive_low_momentum_bonus", 15))
    hook_threshold = float(drop_cfg.get("unpaid_hook_threshold", 75))
    hook_bonus = float(drop_cfg.get("unpaid_hook_bonus", 10))
    span = int(drop_cfg.get("reasonable_payoff_span_scenes", 3))

    ordered = sorted(profiles, key=lambda item: item.scene_ordinal)
    momentums = [float(item.reading_momentum or 0.0) for item in ordered]
    result: list[SceneReaderJourneyProfileItemV2] = []

    for index, profile in enumerate(ordered):
        risk = base_dropoff_risk(momentums[index])
        # Two consecutive clear declines ending at this scene.
        if index >= 2:
            d1 = momentums[index - 1] - momentums[index - 2]
            d2 = momentums[index] - momentums[index - 1]
            if d1 < -0.5 and d2 < -0.5:
                risk = _clamp_0_100(risk + decline_bonus)
        # Three consecutive low momentum including this scene.
        if index >= low_count - 1:
            window = momentums[index - low_count + 1 : index + 1]
            if len(window) == low_count and all(value < low_threshold for value in window):
                risk = _clamp_0_100(risk + low_bonus)
        # High hook without payoff within reasonable span.
        hook_score = mapped_or_zero(profile.hook)
        payoff_score = mapped_or_zero(profile.payoff)
        if hook_score > hook_threshold and payoff_score < 40:
            future_payoff = False
            for ahead in ordered[index + 1 : index + 1 + span]:
                if mapped_or_zero(ahead.payoff) >= 50:
                    future_payoff = True
                    break
            if not future_payoff:
                risk = _clamp_0_100(risk + hook_bonus)

        data = profile.model_dump()
        data["dropoff_risk"] = _round1(risk)
        if profile.node_type == "beat":
            data["include_in_main_curve"] = False
            data["include_in_chapter_mean"] = False
            # Boundary anomaly is data quality, not literary diagnosis.
            if profile.data_quality_issue is None and (
                not profile.evidence_paragraph_ids
                or len(profile.scene_value_summary.strip()) < 4
            ):
                data["data_quality_issue"] = "scene_boundary_anomaly"
        result.append(SceneReaderJourneyProfileItemV2.model_validate(data))
    return result


def derive_scene_metrics(
    profile: SceneReaderJourneyProfileItemV2,
    *,
    formula_config: dict[str, Any] | None = None,
    role_targets: dict[str, Any] | None = None,
) -> tuple[SceneReaderJourneyProfileItemV2, DerivedMetricsV2]:
    cfg = formula_config or load_formula_v2_config()
    roles = role_targets or load_scene_role_targets()
    scored = apply_profile_mapped_scores(profile, config=cfg)
    weight_block = cfg.get("weights") or {}
    plot = compute_plot_progress(scored, weights=weight_block.get("plot_progress") or {})
    tension = compute_reading_tension(scored, weights=weight_block.get("reading_tension") or {})
    pacing = compute_pacing_fit(scored, role_targets=roles, formula_config=cfg)
    hook_payoff = compute_hook_payoff_fit(scored, role_targets=roles, formula_config=cfg)
    clarity_p, cognitive_p, redundancy_p = compute_penalties(scored, config=cfg)
    momentum = compute_reading_momentum(
        plot_progress=plot,
        reading_tension=tension,
        pacing_fit=pacing,
        hook_payoff_fit=hook_payoff,
        clarity_penalty=clarity_p,
        cognitive_load_penalty=cognitive_p,
        redundancy_penalty=redundancy_p,
        weights=weight_block.get("reading_momentum") or {},
    )
    dropoff = base_dropoff_risk(momentum)
    derived = DerivedMetricsV2(
        plot_progress=_round1(plot),
        reading_tension=_round1(tension),
        pacing_fit=_round1(pacing),
        hook_payoff_fit=_round1(hook_payoff),
        clarity_penalty=_round1(clarity_p),
        cognitive_load_penalty=_round1(cognitive_p),
        redundancy_penalty=_round1(redundancy_p),
        reading_momentum=_round1(momentum),
        dropoff_risk=_round1(dropoff),
        formula_version=str(cfg.get("version", FORMULA_VERSION_V2)),
    )
    updated = scored.model_copy(
        update={
            "plot_progress": derived.plot_progress,
            "reading_tension": derived.reading_tension,
            "pacing_fit": derived.pacing_fit,
            "hook_payoff_fit": derived.hook_payoff_fit,
            "reading_momentum": derived.reading_momentum,
            "dropoff_risk": derived.dropoff_risk,
            "include_in_main_curve": scored.node_type != "beat",
            "include_in_chapter_mean": scored.node_type != "beat",
        }
    )
    return updated, derived


def derive_chapter_profiles(
    profiles: list[SceneReaderJourneyProfileItemV2],
    *,
    formula_config: dict[str, Any] | None = None,
    role_targets: dict[str, Any] | None = None,
) -> list[SceneReaderJourneyProfileItemV2]:
    cfg = formula_config or load_formula_v2_config()
    roles = role_targets or load_scene_role_targets()
    derived_list: list[SceneReaderJourneyProfileItemV2] = []
    for profile in sorted(profiles, key=lambda item: item.scene_ordinal):
        updated, _ = derive_scene_metrics(profile, formula_config=cfg, role_targets=roles)
        derived_list.append(updated)
    return apply_dropoff_adjustments(derived_list, config=cfg)


def chapter_mean_reading_momentum(profiles: list[SceneReaderJourneyProfileItemV2]) -> float | None:
    values = [
        float(item.reading_momentum)
        for item in profiles
        if item.include_in_chapter_mean is not False
        and item.node_type != "beat"
        and item.reading_momentum is not None
    ]
    if not values:
        return None
    return _round1(sum(values) / len(values))
