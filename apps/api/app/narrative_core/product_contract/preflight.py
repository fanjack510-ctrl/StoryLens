"""Preflight page model contract (Phase 1D-P).

Preflight is read-only and separated from real Run creation.
Default: run_creation_enabled=False. No force-start bypass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey
from app.narrative_core.product_contract.keys import resolve_modules_with_dependencies


@dataclass(frozen=True, slots=True)
class PreflightBookStatusDto:
    book_id: int
    title: str
    chapter_count: int
    paragraph_count: int
    character_count: int
    current_snapshot_id: int | None
    snapshot_created_at: str | None
    body_changed_since_snapshot: bool
    snapshot_rebuild_required: bool


@dataclass(frozen=True, slots=True)
class PreflightSnapshotStatusDto:
    snapshot_id: int | None
    status: str | None
    created_at: str | None
    chapter_count: int = 0
    paragraph_count: int = 0
    character_count: int = 0
    integrity_ok: bool = False


@dataclass(frozen=True, slots=True)
class PreflightCapabilityStatusDto:
    capability_key: str
    allowed: bool
    reason_code: str
    availability: str
    message: str = ""


@dataclass(frozen=True, slots=True)
class PreflightQuotaStatusDto:
    allowed: bool
    reason_code: str = ""
    remaining: dict[str, Any] = field(default_factory=dict)
    estimated_usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PreflightEngineStatusDto:
    engine_id: str | None
    available: bool
    supports_mode: bool
    message: str = ""


@dataclass(frozen=True, slots=True)
class PreflightStagePlanItemDto:
    stage_key: str
    display_name: str
    order: int
    required: bool
    estimated_cost_class: str
    produced_module_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PreflightSourceCoverageDto:
    fulltext_snapshot_ready: bool
    enhanced_asset_coverage_ratio: float | None = None
    scene_coverage_ratio: float | None = None
    reader_journey_coverage_ratio: float | None = None
    chapter_analysis_coverage_ratio: float | None = None
    enhanced_degraded: bool = False


@dataclass(frozen=True, slots=True)
class PreflightEstimatedUsageDto:
    estimated_token_input: int | None = None
    estimated_token_output: int | None = None
    estimated_cost: float | None = None
    estimated_duration_class: str = "unknown"
    currency: str = "USD"


@dataclass(frozen=True, slots=True)
class WholeBookPreflightPageModel:
    """Frontend Preflight page model — must not create a production Run."""

    book: PreflightBookStatusDto
    snapshot: PreflightSnapshotStatusDto
    capability: PreflightCapabilityStatusDto
    quota: PreflightQuotaStatusDto
    engine: PreflightEngineStatusDto
    analysis_mode: WholeBookAnalysisMode
    requested_modules: tuple[WholeBookModuleKey, ...]
    resolved_modules: tuple[WholeBookModuleKey, ...]
    stage_plan: tuple[PreflightStagePlanItemDto, ...]
    source_coverage: PreflightSourceCoverageDto
    estimated_usage: PreflightEstimatedUsageDto
    blocking_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    run_creation_enabled: bool = False
    confirmation_required: bool = True
    auto_fill_notes: tuple[str, ...] = ()
    force_start_allowed: bool = False  # MUST remain False — no bypass button

    def __post_init__(self) -> None:
        if self.force_start_allowed:
            raise ValueError("force_start_allowed must remain False")


def build_resolved_modules(
    requested: tuple[WholeBookModuleKey | str, ...],
) -> tuple[tuple[WholeBookModuleKey, ...], tuple[str, ...]]:
    modules, _stages, notes = resolve_modules_with_dependencies(requested)
    return modules, notes
