"""Real analysis usage fields (Phase 2B-P). Estimate vs actual; synthetic vs real."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModuleUsageCounters:
    module_key: str
    provider_calls: int = 0
    provider_input_tokens: int = 0
    provider_output_tokens: int = 0
    retries: int = 0


@dataclass(frozen=True, slots=True)
class StageUsageCounters:
    stage_key: str
    provider_calls: int = 0
    provider_input_tokens: int = 0
    provider_output_tokens: int = 0
    retries: int = 0


@dataclass(frozen=True, slots=True)
class WholeBookUsageEstimate:
    context_characters: int
    context_tokens_estimated: int
    provider_input_tokens: int
    provider_output_tokens: int
    provider_cost: float | None
    synthetic: bool = True

    def __post_init__(self) -> None:
        if self.context_characters < 0 or self.context_tokens_estimated < 0:
            raise ValueError("estimates must be >= 0")


@dataclass(frozen=True, slots=True)
class WholeBookUsageActual:
    context_characters: int
    context_tokens_estimated: int
    provider_input_tokens: int
    provider_output_tokens: int
    cached_tokens: int
    provider_cost: float | None
    retries: int
    module_usage: tuple[ModuleUsageCounters, ...] = ()
    stage_usage: tuple[StageUsageCounters, ...] = ()
    synthetic: bool = False

    def __post_init__(self) -> None:
        if min(
            self.context_characters,
            self.context_tokens_estimated,
            self.provider_input_tokens,
            self.provider_output_tokens,
            self.cached_tokens,
            self.retries,
        ) < 0:
            raise ValueError("usage counters must be >= 0")


@dataclass(frozen=True, slots=True)
class WholeBookUsageReport:
    estimate: WholeBookUsageEstimate | None
    actual: WholeBookUsageActual | None
    estimate_vs_actual_separated: bool = True
    synthetic_vs_real_separated: bool = True
    commercial_price_exposed: bool = False

    def __post_init__(self) -> None:
        if not self.estimate_vs_actual_separated or not self.synthetic_vs_real_separated:
            raise ValueError("estimate/actual and synthetic/real must stay separated")
        if self.commercial_price_exposed:
            raise ValueError("must not expose commercial prices in usage report")


def fake_usage_report() -> WholeBookUsageReport:
    return WholeBookUsageReport(
        estimate=WholeBookUsageEstimate(
            context_characters=100,
            context_tokens_estimated=40,
            provider_input_tokens=16,
            provider_output_tokens=32,
            provider_cost=0.0,
            synthetic=True,
        ),
        actual=WholeBookUsageActual(
            context_characters=100,
            context_tokens_estimated=40,
            provider_input_tokens=16,
            provider_output_tokens=32,
            cached_tokens=0,
            provider_cost=0.0,
            retries=0,
            module_usage=(ModuleUsageCounters(module_key="book_overview"),),
            stage_usage=(StageUsageCounters(stage_key="analyze_structure"),),
            synthetic=True,
        ),
    )


def usage_fields_required() -> frozenset[str]:
    return frozenset(
        {
            "context_characters",
            "context_tokens_estimated",
            "provider_input_tokens",
            "provider_output_tokens",
            "cached_tokens",
            "provider_cost",
            "retries",
            "module_usage",
            "stage_usage",
        }
    )
