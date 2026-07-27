"""WholeBook stage plan contracts (Phase 1C-P freeze)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.narrative_core.contracts.capability import CapabilityDecision
from app.narrative_core.enums import (
    CostClass,
    StageStatus,
    WholeBookAnalysisMode,
    WholeBookStageKey,
)


@dataclass(frozen=True, slots=True)
class WholeBookStageDefinition:
    """Frozen catalog entry for a pipeline stage."""

    stage_key: WholeBookStageKey
    display_name: str
    order: int
    description: str = ""
    required: bool = True
    resumable: bool = True
    retryable: bool = True
    input_contract_version: str = "1"
    output_contract_version: str = "1"
    depends_on: tuple[WholeBookStageKey, ...] = ()
    estimated_cost_class: CostClass | str = CostClass.LOW

    @property
    def label(self) -> str:
        return self.display_name


@dataclass(frozen=True, slots=True)
class WholeBookStagePlan:
    """Ordered stage plan returned by engine.build_stage_plan."""

    mode: WholeBookAnalysisMode
    stages: tuple[WholeBookStageDefinition, ...]


@dataclass(frozen=True, slots=True)
class WholeBookStageContext:
    """Runtime context for execute_stage — must not embed full novel body."""

    run_id: int
    book_id: int
    book_snapshot_id: int
    analysis_mode: WholeBookAnalysisMode
    stage_key: WholeBookStageKey
    capability_context: CapabilityDecision
    run_stage_id: int | None = None
    checkpoint: dict[str, Any] = field(default_factory=dict)
    configuration_fingerprint: str = ""
    # Injected Protocol handles (Integration: relation_writer is first-class).
    snapshot_reader: Any | None = None
    asset_writer: Any | None = None
    relation_writer: Any | None = None
    artifact_writer: Any | None = None
    conflict_sink: Any | None = None
    cancellation_token: Any | None = None
    budget_guard: Any | None = None
    # Non-core extension bag only — do not inject formal Protocol deps here.
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WholeBookStageResult:
    """Canned / real stage output envelope."""

    stage_key: WholeBookStageKey
    status: StageStatus
    output_artifact_ids: tuple[int, ...] = ()
    created_asset_version_ids: tuple[int, ...] = ()
    created_relation_version_ids: tuple[int, ...] = ()
    conflict_ids: tuple[int, ...] = ()
    checkpoint: dict[str, Any] = field(default_factory=dict)
    token_usage: int = 0
    cost: float = 0.0
    warnings: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    @property
    def artifacts_written(self) -> int:
        return len(self.output_artifact_ids)

    @property
    def assets_written(self) -> int:
        return len(self.created_asset_version_ids)

    @property
    def relations_written(self) -> int:
        return len(self.created_relation_version_ids)
