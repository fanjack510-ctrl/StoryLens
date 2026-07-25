"""Frozen Public/Private Whole-Book Overview DTOs (STEP 2.1 / contract v1.0).

Formal POST create endpoint may remain disabled in routers — these DTOs freeze
the wire shape only. Does not implement Orchestrator / Provider / Materializer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.narrative_core.enums import (
    OverviewFieldStatus,
    OverviewProductionStageKey,
    RunStatus,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
    WindowStatus,
)
from app.narrative_core.contracts.whole_book_overview_errors import (
    WholeBookOverviewErrorCode,
)

CONTRACT_VERSION = "1.0"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# API: consent / progress / create / status / preflight / overview / error
# ---------------------------------------------------------------------------


class ConsentPayload(_StrictModel):
    estimated_tokens: int = Field(ge=0)
    estimated_cost: float = Field(ge=0)
    currency: str = "CNY"
    confirmed: bool = False


class CreateRunRequest(_StrictModel):
    mode: WholeBookAnalysisMode = WholeBookAnalysisMode.NATIVE
    module_key: WholeBookModuleKey = WholeBookModuleKey.BOOK_OVERVIEW
    provider_id: str
    model_id: str
    client_request_id: str = Field(min_length=1)
    consent: ConsentPayload

    @field_validator("mode")
    @classmethod
    def _mode_native_default(cls, value: WholeBookAnalysisMode) -> WholeBookAnalysisMode:
        # Contract retains enhanced enum; product entry defaults to native only.
        if value not in (WholeBookAnalysisMode.NATIVE, WholeBookAnalysisMode.ENHANCED):
            raise ValueError(f"unsupported mode: {value}")
        return value


class ProgressDTO(_StrictModel):
    completed_windows: int = Field(ge=0, default=0)
    total_windows: int = Field(ge=0, default=0)
    percent: float = Field(ge=0, le=100, default=0)


class CreateRunResponse(_StrictModel):
    run_id: str
    book_id: str
    snapshot_id: str
    mode: WholeBookAnalysisMode
    module_key: WholeBookModuleKey
    status: RunStatus
    current_stage: OverviewProductionStageKey | None = None
    progress: ProgressDTO
    created_at: datetime


class RunStatusResponse(_StrictModel):
    run_id: str
    book_id: str
    snapshot_id: str
    mode: WholeBookAnalysisMode
    module_key: WholeBookModuleKey
    status: RunStatus
    current_stage: OverviewProductionStageKey | None = None
    progress: ProgressDTO
    estimated_tokens: int | None = None
    actual_tokens: int | None = None
    estimated_cost: float | None = None
    actual_cost: float | None = None
    provider: str | None = None
    model: str | None = None
    error: str | None = None
    error_code: WholeBookOverviewErrorCode | None = None
    retryable: bool = False
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class PreflightResponse(_StrictModel):
    """Native Overview preflight — aligns with existing preflight where possible."""

    book_id: str
    chapter_count: int = Field(ge=0, default=0)
    paragraph_count: int = Field(ge=0, default=0)
    character_count: int = Field(ge=0, default=0)
    snapshot_required: bool = True
    provider_configured: bool = False
    license_allowed: bool = False
    mode: WholeBookAnalysisMode = WholeBookAnalysisMode.NATIVE
    estimated_windows: int = Field(ge=0, default=0)
    estimated_tokens: int = Field(ge=0, default=0)
    estimated_cost: float = Field(ge=0, default=0)
    currency: str = "CNY"
    warnings: list[str] = Field(default_factory=list)
    blocking_errors: list[str] = Field(default_factory=list)
    run_creation_enabled: bool = False


class OverviewField(_StrictModel):
    value: Any = None
    confidence: float = Field(ge=0, le=1, default=0)
    evidence_refs: list[str] = Field(default_factory=list)
    status: OverviewFieldStatus = OverviewFieldStatus.INSUFFICIENT_EVIDENCE

    @model_validator(mode="after")
    def _no_high_confidence_without_evidence(self) -> OverviewField:
        if self.confidence >= 0.8 and not self.evidence_refs:
            raise ValueError("high confidence OverviewField requires evidence_refs")
        if (
            self.status == OverviewFieldStatus.SUPPORTED
            and self.confidence >= 0.8
            and not self.evidence_refs
        ):
            raise ValueError("supported high-confidence field requires evidence_refs")
        return self


class CoverageDTO(_StrictModel):
    original_paragraphs_total: int = Field(ge=0)
    original_paragraphs_covered: int = Field(ge=0)
    original_coverage_percent: float = Field(ge=0, le=100)
    windows_total: int = Field(ge=0)
    windows_completed: int = Field(ge=0)
    evidence_count: int = Field(ge=0, default=0)


class OverviewBodyDTO(_StrictModel):
    novel_type: OverviewField | None = None
    narrative_features: OverviewField | None = None
    core_setting: OverviewField | None = None
    protagonist: OverviewField | None = None
    protagonist_core_goal: OverviewField | None = None
    primary_conflict: OverviewField | None = None
    central_question: OverviewField | None = None
    key_turning_points: OverviewField | None = None
    climax: OverviewField | None = None
    resolved_problem: OverviewField | None = None
    ending_state: OverviewField | None = None
    logline: OverviewField | None = None
    synopsis: OverviewField | None = None


class OverviewApiResponse(_StrictModel):
    run: dict[str, Any]
    book: dict[str, Any]
    snapshot: dict[str, Any]
    coverage: CoverageDTO
    overview: OverviewBodyDTO
    warnings: list[str] = Field(default_factory=list)
    evidence_index: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime
    engine_version: str
    prompt_version: str
    contract_version: str = CONTRACT_VERSION


class ErrorDetail(_StrictModel):
    code: WholeBookOverviewErrorCode
    message: str
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None
    stage_key: str | None = None
    window_index: int | None = None


class ErrorEnvelope(_StrictModel):
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Public ↔ Private exchange
# ---------------------------------------------------------------------------


class OverviewRunRef(_StrictModel):
    run_id: str
    book_id: str
    snapshot_id: str
    mode: WholeBookAnalysisMode = WholeBookAnalysisMode.NATIVE
    engine_version: str
    prompt_version: str


class ChapterRef(_StrictModel):
    chapter_id: str
    chapter_index: int = Field(ge=0)
    title: str = ""


class WindowParagraph(_StrictModel):
    paragraph_id: str = Field(min_length=1)
    chapter_id: str = Field(min_length=1)
    paragraph_index: int = Field(ge=0)
    text: str


class WindowSlice(_StrictModel):
    window_id: str
    window_index: int = Field(ge=0)
    total_windows: int = Field(ge=1)
    start_paragraph_id: str
    end_paragraph_id: str
    chapter_refs: list[ChapterRef] = Field(default_factory=list)
    paragraphs: list[WindowParagraph] = Field(min_length=1)
    input_hash: str = Field(min_length=1)
    status: WindowStatus | None = None


class PriorStateV1(_StrictModel):
    state_version: int = Field(ge=0, default=0)
    characters: list[dict[str, Any]] = Field(default_factory=list)
    aliases: list[dict[str, Any]] = Field(default_factory=list)
    protagonist_candidates: list[dict[str, Any]] = Field(default_factory=list)
    goal_candidates: list[dict[str, Any]] = Field(default_factory=list)
    conflict_candidates: list[dict[str, Any]] = Field(default_factory=list)
    central_question_candidates: list[dict[str, Any]] = Field(default_factory=list)
    major_event_candidates: list[dict[str, Any]] = Field(default_factory=list)
    climax_candidates: list[dict[str, Any]] = Field(default_factory=list)
    ending_state_candidates: list[dict[str, Any]] = Field(default_factory=list)


class WindowConstraints(_StrictModel):
    evidence_required: bool = True
    allowed_entity_types: list[str] = Field(default_factory=list)
    allowed_asset_types: list[str] = Field(default_factory=list)
    max_candidates: dict[str, int] = Field(default_factory=dict)


class WholeBookOverviewWindowInputV1(_StrictModel):
    contract_version: str = CONTRACT_VERSION
    run: OverviewRunRef
    window: WindowSlice
    prior_state: PriorStateV1 = Field(default_factory=PriorStateV1)
    constraints: WindowConstraints = Field(default_factory=WindowConstraints)

    @field_validator("contract_version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        if value != CONTRACT_VERSION:
            raise ValueError(f"unsupported contract_version: {value}")
        return value


class CandidateEntityV1(_StrictModel):
    candidate_id: str
    entity_type: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    confidence: float = Field(ge=0, le=1, default=0)
    evidence_refs: list[str] = Field(default_factory=list)


class CandidateAssetV1(_StrictModel):
    candidate_id: str
    asset_type: str
    title: str = ""
    summary: str = ""
    subject_candidate_ids: list[str] = Field(default_factory=list)
    object_candidate_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1, default=0)
    evidence_refs: list[str] = Field(default_factory=list)
    deduplication_key: str = ""


class CandidateEvidenceV1(_StrictModel):
    evidence_id: str
    paragraph_id: str = Field(min_length=1)
    chapter_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    evidence_role: str = "support"
    confidence: float = Field(ge=0, le=1, default=0)
    supports_candidate_ids: list[str] = Field(default_factory=list)

    @field_validator("paragraph_id")
    @classmethod
    def _paragraph_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("paragraph_id must be non-empty")
        return value


class WindowQualityV1(_StrictModel):
    confidence: float = Field(ge=0, le=1, default=0)
    repair_attempted: bool = False
    repair_succeeded: bool = False


class StateDeltaV1(_StrictModel):
    characters: list[dict[str, Any]] = Field(default_factory=list)
    aliases: list[dict[str, Any]] = Field(default_factory=list)
    protagonist_candidates: list[dict[str, Any]] = Field(default_factory=list)
    goal_candidates: list[dict[str, Any]] = Field(default_factory=list)
    conflict_candidates: list[dict[str, Any]] = Field(default_factory=list)
    central_question_candidates: list[dict[str, Any]] = Field(default_factory=list)
    major_event_candidates: list[dict[str, Any]] = Field(default_factory=list)
    climax_candidates: list[dict[str, Any]] = Field(default_factory=list)
    ending_state_candidates: list[dict[str, Any]] = Field(default_factory=list)


class WholeBookOverviewWindowResultV1(_StrictModel):
    contract_version: str = CONTRACT_VERSION
    run_id: str
    window_id: str
    input_hash: str
    candidate_entities: list[CandidateEntityV1] = Field(default_factory=list)
    candidate_assets: list[CandidateAssetV1] = Field(default_factory=list)
    candidate_evidence: list[CandidateEvidenceV1] = Field(default_factory=list)
    state_delta: StateDeltaV1 = Field(default_factory=StateDeltaV1)
    warnings: list[str] = Field(default_factory=list)
    quality: WindowQualityV1 = Field(default_factory=WindowQualityV1)

    @field_validator("contract_version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        if value != CONTRACT_VERSION:
            raise ValueError(f"unsupported contract_version: {value}")
        return value


class WholeBookOverviewSynthesisInputV1(_StrictModel):
    contract_version: str = CONTRACT_VERSION
    run_id: str
    book_id: str
    snapshot_id: str
    engine_version: str
    prompt_version: str
    entities: list[dict[str, Any]] = Field(default_factory=list)
    assets: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    final_state: PriorStateV1 = Field(default_factory=PriorStateV1)
    snapshot_meta: dict[str, Any] = Field(default_factory=dict)
    selected_evidence: list[CandidateEvidenceV1] = Field(default_factory=list)

    @field_validator("contract_version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        if value != CONTRACT_VERSION:
            raise ValueError(f"unsupported contract_version: {value}")
        return value


class WholeBookOverviewProjectionCandidateV1(_StrictModel):
    contract_version: str = CONTRACT_VERSION
    run_id: str
    novel_type: OverviewField | None = None
    narrative_features: OverviewField | None = None
    core_setting: OverviewField | None = None
    protagonist: OverviewField | None = None
    protagonist_core_goal: OverviewField | None = None
    primary_conflict: OverviewField | None = None
    central_question: OverviewField | None = None
    key_turning_points: OverviewField | None = None
    climax: OverviewField | None = None
    resolved_problem: OverviewField | None = None
    ending_state: OverviewField | None = None
    logline: OverviewField | None = None
    synopsis: OverviewField | None = None
    warnings: list[str] = Field(default_factory=list)

    @field_validator("contract_version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        if value != CONTRACT_VERSION:
            raise ValueError(f"unsupported contract_version: {value}")
        return value


# Aliases matching prompt naming
WindowResultV1 = WholeBookOverviewWindowResultV1
SynthesisInputV1 = WholeBookOverviewSynthesisInputV1
ProjectionCandidateV1 = WholeBookOverviewProjectionCandidateV1
