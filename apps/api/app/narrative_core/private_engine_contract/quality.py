"""Quality profile vs analysis mode vs model route separation (Phase 2B-P)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.narrative_core.enums import WholeBookAnalysisMode

# Analysis Mode (product capability mode) — NOT quality, NOT model route.
ANALYSIS_MODE_VALUES: frozenset[str] = frozenset(
    {
        WholeBookAnalysisMode.NATIVE.value,
        WholeBookAnalysisMode.ENHANCED.value,
    }
)


class QualityProfileKey(StrEnum):
    FAST = "fast"
    BALANCED = "balanced"
    HIGH_QUALITY = "high_quality"
    CUSTOM = "custom"


QUALITY_PROFILE_VALUES: frozenset[str] = frozenset(p.value for p in QualityProfileKey)

# Model Route is decided by Provider Policy — separate enum namespace.
MODEL_ROUTE_NAMESPACE = "provider_policy.model_route"

SEPARATION_RULES: frozenset[str] = frozenset(
    {
        "analysis_mode_is_not_quality_profile",
        "quality_profile_is_not_model_route",
        "model_route_from_provider_policy_only",
        "do_not_collapse_three_into_one_enum",
    }
)


@dataclass(frozen=True, slots=True)
class WholeBookQualityProfile:
    profile_key: QualityProfileKey
    provider_policy_key: str
    context_strategy_key: str
    retry_policy_key: str
    evidence_policy_key: str
    budget_policy_key: str
    quality_expectation: str
    user_visible: bool
    custom: bool

    def __post_init__(self) -> None:
        if self.profile_key == QualityProfileKey.CUSTOM and not self.custom:
            raise ValueError("CUSTOM profile must set custom=True")
        if self.profile_key != QualityProfileKey.CUSTOM and self.custom:
            raise ValueError("only CUSTOM profile may set custom=True")
        # Must not expose internal prompts or commercial prices.
        banned = ("prompt_body", "price_cny", "price_usd", "sku")
        blob = "|".join(
            (
                self.provider_policy_key,
                self.context_strategy_key,
                self.retry_policy_key,
                self.evidence_policy_key,
                self.budget_policy_key,
                self.quality_expectation,
            )
        ).lower()
        if any(token in blob for token in banned):
            raise ValueError("quality profile must not embed prompts or commercial prices")


DEFAULT_QUALITY_PROFILES: tuple[WholeBookQualityProfile, ...] = (
    WholeBookQualityProfile(
        profile_key=QualityProfileKey.FAST,
        provider_policy_key="policy.fast",
        context_strategy_key="context.fast",
        retry_policy_key="retry.low",
        evidence_policy_key="evidence.minimal",
        budget_policy_key="budget.tight",
        quality_expectation="fast_preview",
        user_visible=True,
        custom=False,
    ),
    WholeBookQualityProfile(
        profile_key=QualityProfileKey.BALANCED,
        provider_policy_key="policy.balanced",
        context_strategy_key="context.balanced",
        retry_policy_key="retry.default",
        evidence_policy_key="evidence.standard",
        budget_policy_key="budget.standard",
        quality_expectation="balanced",
        user_visible=True,
        custom=False,
    ),
    WholeBookQualityProfile(
        profile_key=QualityProfileKey.HIGH_QUALITY,
        provider_policy_key="policy.high_quality",
        context_strategy_key="context.deep",
        retry_policy_key="retry.high",
        evidence_policy_key="evidence.strict",
        budget_policy_key="budget.relaxed",
        quality_expectation="high_quality",
        user_visible=True,
        custom=False,
    ),
)


def assert_mode_profile_route_separated(
    *,
    analysis_mode: str,
    quality_profile: str,
    model_route: str,
) -> None:
    if analysis_mode == quality_profile:
        raise ValueError("analysis mode must not equal quality profile key")
    if quality_profile == model_route:
        raise ValueError("quality profile must not equal model route")
    if analysis_mode not in ANALYSIS_MODE_VALUES:
        raise ValueError(f"unknown analysis mode: {analysis_mode}")
    if quality_profile not in QUALITY_PROFILE_VALUES:
        raise ValueError(f"unknown quality profile: {quality_profile}")
