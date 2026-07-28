"""Whole-book contract v1 Pydantic wire/persistence models (frozen semantics)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .common import (
    AssetTypeStr,
    EvidenceKeyStr,
    RelationTypeStr,
    Sha256Str,
    StageCodeStr,
    UtcDatetime,
    dedupe_preserve_order,
    dedupe_sorted_positive_ints,
    is_json_compatible,
    sha256_hex,
    scan_sensitive_payload,
)
from .constants import (
    ANALYSIS_PROVENANCE_VERSION,
    BOOK_OVERVIEW_CLAIM_KEYS_V1,
    BOOK_OVERVIEW_RESULT_VERSION,
    SNAPSHOT_LOCATOR_VERSION,
    WHOLE_BOOK_CONTRACT_VERSION,
)
from .enums import (
    ArtifactState,
    ConflictStatus,
    EntityType,
    EvidenceState,
    NarrativeRefKind,
    OverviewClaimAvailability,
    ResultOrigin,
    SnapshotStatus,
    WholeBookMode,
    WholeBookRunStatus,
    WholeBookStageStatus,
    WholeBookUnitStatus,
)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


PositiveInt = Annotated[int, Field(gt=0)]
NonNegInt = Annotated[int, Field(ge=0)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


# ---------------------------------------------------------------------------
# Provenance / Input usage
# ---------------------------------------------------------------------------


class AnalysisProvenanceV1(ContractModel):
    provenance_version: Literal["analysis_provenance_v1"] = ANALYSIS_PROVENANCE_VERSION  # type: ignore[assignment]
    run_id: PositiveInt
    snapshot_id: PositiveInt
    window_ids: list[PositiveInt] = Field(default_factory=list)
    engine_id: str = Field(min_length=1, max_length=128)
    engine_version: str = Field(min_length=1, max_length=64)
    contract_version: Literal["whole_book_contract_v1"] = WHOLE_BOOK_CONTRACT_VERSION  # type: ignore[assignment]
    prompt_version: str | None = Field(default=None, max_length=128)
    provider_id: str | None = Field(default=None, max_length=128)
    model_name: str | None = Field(default=None, max_length=128)
    result_origin: ResultOrigin
    source_mode: WholeBookMode
    deterministic: bool
    config_hashes: dict[str, Sha256Str] = Field(default_factory=dict)
    generated_at: UtcDatetime

    @field_validator("window_ids")
    @classmethod
    def _sort_unique_windows(cls, v: list[int]) -> list[int]:
        return dedupe_sorted_positive_ints(v)

    @field_validator("provider_id")
    @classmethod
    def _no_key_in_provider(cls, v: str | None) -> str | None:
        if v is None:
            return v
        lower = v.lower()
        if "key" in lower and ("api" in lower or "secret" in lower):
            raise ValueError("provider_id must not contain API key material")
        if v.startswith("sk-"):
            raise ValueError("provider_id must not look like an API key")
        return v

    @model_validator(mode="after")
    def _formal_engine_required(self) -> AnalysisProvenanceV1:
        if self.result_origin == ResultOrigin.formal and not self.deterministic:
            if not self.engine_id or not self.engine_version:
                raise ValueError("formal non-deterministic provenance requires engine_id/engine_version")
        return self


class WholeBookInputUsageV1(ContractModel):
    full_text_snapshot_used: bool
    chapter_analysis_asset_count: NonNegInt
    reader_journey_asset_count: NonNegInt
    confirmed_whole_book_asset_count: NonNegInt

    def validate_for_mode(self, mode: WholeBookMode) -> None:
        if not self.full_text_snapshot_used:
            raise ValueError("full_text_snapshot_used must be true for all whole-book modes")
        if mode == WholeBookMode.whole_book_native:
            if self.chapter_analysis_asset_count != 0:
                raise ValueError("native mode forbids chapter_analysis_asset_count > 0")
            if self.reader_journey_asset_count != 0:
                raise ValueError("native mode forbids reader_journey_asset_count > 0")


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


class BookSnapshotMetadataV1(ContractModel):
    snapshot_id: PositiveInt
    book_id: PositiveInt
    snapshot_version: PositiveInt
    status: SnapshotStatus
    content_hash: Sha256Str
    chapter_count: NonNegInt
    paragraph_count: NonNegInt
    character_count: NonNegInt
    created_at: UtcDatetime
    completed_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def _status_rules(self) -> BookSnapshotMetadataV1:
        if self.status == SnapshotStatus.completed:
            if self.completed_at is None:
                raise ValueError("completed snapshot requires completed_at")
        if self.status == SnapshotStatus.building:
            if self.completed_at is not None:
                raise ValueError("building snapshot must have completed_at=null")
        return self


class SnapshotChapterV1(ContractModel):
    snapshot_chapter_id: PositiveInt
    snapshot_id: PositiveInt
    chapter_id: PositiveInt
    chapter_index: NonNegInt
    title: str = Field(default="", max_length=500)
    chapter_hash: Sha256Str
    paragraph_count: NonNegInt
    character_count: NonNegInt


class SnapshotParagraphV1(ContractModel):
    snapshot_paragraph_id: PositiveInt
    snapshot_id: PositiveInt
    snapshot_chapter_id: PositiveInt
    chapter_id: PositiveInt
    chapter_index: NonNegInt
    paragraph_index: NonNegInt
    global_paragraph_index: NonNegInt
    text: str
    text_hash: Sha256Str
    character_count: NonNegInt

    @model_validator(mode="after")
    def _text_consistency(self) -> SnapshotParagraphV1:
        if self.character_count != len(self.text):
            raise ValueError("character_count must equal len(text)")
        expected = sha256_hex(self.text)
        if self.text_hash != expected:
            raise ValueError("text_hash must equal SHA-256 of Snapshot text")
        return self


# ---------------------------------------------------------------------------
# Evidence locator
# ---------------------------------------------------------------------------


class SnapshotEvidenceLocatorV1(ContractModel):
    locator_version: Literal["snapshot_paragraph_v1"] = SNAPSHOT_LOCATOR_VERSION  # type: ignore[assignment]
    snapshot_id: PositiveInt
    snapshot_chapter_id: PositiveInt
    snapshot_paragraph_id: PositiveInt
    chapter_id: PositiveInt
    chapter_index: NonNegInt
    paragraph_index: NonNegInt
    global_paragraph_index: NonNegInt
    start_offset: NonNegInt
    end_offset: int = Field(gt=0)
    quote_text: str = Field(min_length=1)
    quote_hash: Sha256Str
    paragraph_text_hash: Sha256Str

    @model_validator(mode="after")
    def _offset_and_quote(self) -> SnapshotEvidenceLocatorV1:
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be > start_offset")
        expected_quote = sha256_hex(self.quote_text)
        if self.quote_hash != expected_quote:
            raise ValueError("quote_hash must equal SHA-256 of quote_text")
        return self


# ---------------------------------------------------------------------------
# Run / Stage / Checkpoint
# ---------------------------------------------------------------------------


class WholeBookRunV1(ContractModel):
    run_id: PositiveInt
    book_id: PositiveInt
    snapshot_id: PositiveInt
    mode: WholeBookMode
    status: WholeBookRunStatus
    current_stage_code: StageCodeStr | None = None
    idempotency_key: str = Field(min_length=1, max_length=128)
    engine_id: str = Field(min_length=1, max_length=128)
    engine_version: str = Field(min_length=1, max_length=64)
    contract_version: Literal["whole_book_contract_v1"] = WHOLE_BOOK_CONTRACT_VERSION  # type: ignore[assignment]
    prompt_version: str | None = Field(default=None, max_length=128)
    result_origin: ResultOrigin
    input_usage: WholeBookInputUsageV1
    consent_id: PositiveInt | None = None
    cost_policy_id: PositiveInt | None = None
    created_at: UtcDatetime
    started_at: UtcDatetime | None = None
    paused_at: UtcDatetime | None = None
    completed_at: UtcDatetime | None = None
    failed_at: UtcDatetime | None = None
    cancelled_at: UtcDatetime | None = None
    failure_code: str | None = Field(default=None, max_length=128)
    failure_message_safe: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _run_rules(self) -> WholeBookRunV1:
        self.input_usage.validate_for_mode(self.mode)
        if self.status == WholeBookRunStatus.completed and self.completed_at is None:
            raise ValueError("completed run requires completed_at")
        if self.status == WholeBookRunStatus.failed:
            if self.failed_at is None:
                raise ValueError("failed run requires failed_at")
            if not self.failure_code:
                raise ValueError("failed run requires failure_code")
        if self.status == WholeBookRunStatus.cancelled and self.cancelled_at is None:
            raise ValueError("cancelled run requires cancelled_at")
        if self.failure_message_safe:
            lower = self.failure_message_safe.lower()
            if "sk-" in lower or "api_key" in lower:
                raise ValueError("failure_message_safe must not contain secrets")
        return self


class WholeBookRunStageV1(ContractModel):
    stage_id: PositiveInt
    run_id: PositiveInt
    stage_code: StageCodeStr
    sequence: NonNegInt
    status: WholeBookStageStatus
    progress_current: NonNegInt
    progress_total: NonNegInt
    started_at: UtcDatetime | None = None
    completed_at: UtcDatetime | None = None
    last_error_code: str | None = Field(default=None, max_length=128)
    last_error_message_safe: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _progress_rules(self) -> WholeBookRunStageV1:
        if self.progress_current > self.progress_total:
            raise ValueError("progress_current must be <= progress_total")
        if self.status == WholeBookStageStatus.completed:
            if self.progress_current != self.progress_total:
                raise ValueError("completed stage requires progress_current == progress_total")
            if self.completed_at is None:
                raise ValueError("completed stage requires completed_at")
        return self


class WholeBookCheckpointV1(ContractModel):
    checkpoint_id: PositiveInt
    run_id: PositiveInt
    stage_code: StageCodeStr
    checkpoint_key: str = Field(min_length=1, max_length=128)
    sequence_no: NonNegInt
    completed_unit_count: NonNegInt
    last_completed_window_id: PositiveInt | None = None
    payload_hash: Sha256Str
    checkpoint_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: UtcDatetime

    @field_validator("checkpoint_payload")
    @classmethod
    def _payload_json(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not is_json_compatible(v):
            raise ValueError("checkpoint_payload must be JSON-compatible")
        issues = scan_sensitive_payload(v)
        if issues:
            raise ValueError(f"checkpoint_payload sensitive content: {','.join(issues)}")
        return v


# ---------------------------------------------------------------------------
# Window / Coverage
# ---------------------------------------------------------------------------


class WholeBookWindowV1(ContractModel):
    window_id: PositiveInt
    run_id: PositiveInt
    snapshot_id: PositiveInt
    window_index: NonNegInt
    first_global_paragraph_index: NonNegInt
    last_global_paragraph_index: NonNegInt
    chapter_start_index: NonNegInt
    chapter_end_index: NonNegInt
    paragraph_count: int = Field(gt=0)
    character_count: int = Field(gt=0)
    token_estimate: NonNegInt
    overlap_before_paragraphs: NonNegInt
    overlap_after_paragraphs: NonNegInt
    window_hash: Sha256Str
    idempotency_key: str = Field(min_length=1, max_length=128)
    status: WholeBookUnitStatus

    @model_validator(mode="after")
    def _window_range(self) -> WholeBookWindowV1:
        if self.last_global_paragraph_index < self.first_global_paragraph_index:
            raise ValueError("last_global_paragraph_index must be >= first")
        if self.chapter_end_index < self.chapter_start_index:
            raise ValueError("chapter_end_index must be >= chapter_start_index")
        return self


class WholeBookWindowCoverageV1(ContractModel):
    snapshot_id: PositiveInt
    run_id: PositiveInt
    total_paragraphs: NonNegInt
    covered_unique_paragraphs: NonNegInt
    duplicated_paragraphs: NonNegInt
    uncovered_paragraphs: NonNegInt
    coverage_ratio: float = Field(ge=0.0, le=1.0)
    order_valid: bool
    first_global_paragraph_index: NonNegInt | None = None
    last_global_paragraph_index: NonNegInt | None = None

    @model_validator(mode="after")
    def _coverage_math(self) -> WholeBookWindowCoverageV1:
        expected_uncovered = self.total_paragraphs - self.covered_unique_paragraphs
        if expected_uncovered < 0:
            raise ValueError("covered_unique_paragraphs cannot exceed total_paragraphs")
        if self.uncovered_paragraphs != expected_uncovered:
            raise ValueError("uncovered_paragraphs must equal total - covered_unique")
        if self.total_paragraphs == 0:
            expected_ratio = 1.0
        else:
            expected_ratio = self.covered_unique_paragraphs / self.total_paragraphs
        if abs(self.coverage_ratio - expected_ratio) > 1e-9:
            raise ValueError("coverage_ratio mismatch")
        return self


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


class CandidateEvidenceV1(ContractModel):
    evidence_key: EvidenceKeyStr
    locator: SnapshotEvidenceLocatorV1
    confidence: Confidence
    note_safe: str | None = Field(default=None, max_length=500)


class CandidateEntityAliasV1(ContractModel):
    name: str = Field(min_length=1, max_length=300)
    confidence: Confidence
    evidence_keys: list[EvidenceKeyStr] = Field(min_length=1)

    @field_validator("evidence_keys")
    @classmethod
    def _dedupe_keys(cls, v: list[str]) -> list[str]:
        out = dedupe_preserve_order(v)
        if not out:
            raise ValueError("evidence_keys must be non-empty")
        return out


class CandidateEntityV1(ContractModel):
    candidate_key: str = Field(min_length=1, max_length=128)
    entity_type: EntityType
    canonical_name: str = Field(min_length=1, max_length=300)
    aliases: list[CandidateEntityAliasV1] = Field(default_factory=list)
    confidence: Confidence
    evidence_keys: list[EvidenceKeyStr] = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("evidence_keys")
    @classmethod
    def _dedupe_keys(cls, v: list[str]) -> list[str]:
        return dedupe_preserve_order(v)

    @field_validator("attributes")
    @classmethod
    def _attrs_json(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not is_json_compatible(v):
            raise ValueError("attributes must be JSON-compatible")
        return v


class CandidateAssetV1(ContractModel):
    candidate_key: str = Field(min_length=1, max_length=128)
    asset_type: AssetTypeStr
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=4000)
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: Confidence
    subject_entity_keys: list[str] = Field(default_factory=list)
    evidence_keys: list[EvidenceKeyStr] = Field(min_length=1)

    @field_validator("subject_entity_keys")
    @classmethod
    def _dedupe_subjects(cls, v: list[str]) -> list[str]:
        return dedupe_preserve_order(v)

    @field_validator("evidence_keys")
    @classmethod
    def _dedupe_keys(cls, v: list[str]) -> list[str]:
        return dedupe_preserve_order(v)

    @field_validator("payload")
    @classmethod
    def _payload_json(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not is_json_compatible(v):
            raise ValueError("payload must be JSON-compatible")
        return v


class CandidateNarrativeRefV1(ContractModel):
    kind: NarrativeRefKind
    candidate_key: str = Field(min_length=1, max_length=128)


class CandidateRelationV1(ContractModel):
    candidate_key: str = Field(min_length=1, max_length=128)
    relation_type: RelationTypeStr
    subject: CandidateNarrativeRefV1
    object: CandidateNarrativeRefV1
    confidence: Confidence
    evidence_keys: list[EvidenceKeyStr] = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("evidence_keys")
    @classmethod
    def _dedupe_keys(cls, v: list[str]) -> list[str]:
        return dedupe_preserve_order(v)

    @field_validator("attributes")
    @classmethod
    def _attrs_json(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not is_json_compatible(v):
            raise ValueError("attributes must be JSON-compatible")
        return v


# ---------------------------------------------------------------------------
# Persisted narrative + engine window I/O
# ---------------------------------------------------------------------------


class EntityAliasV1(ContractModel):
    name: str = Field(min_length=1)
    confidence: Confidence
    evidence_ids: list[PositiveInt] = Field(min_length=1)


class PersistedNarrativeEntityV1(ContractModel):
    entity_id: PositiveInt
    snapshot_id: PositiveInt
    entity_type: EntityType
    canonical_name: str = Field(min_length=1)
    aliases: list[EntityAliasV1] = Field(default_factory=list)
    state: ArtifactState
    confidence: Confidence
    current_version_no: PositiveInt
    created_by_run_id: PositiveInt
    updated_by_run_id: PositiveInt | None = None
    user_confirmed_at: UtcDatetime | None = None
    evidence_ids: list[PositiveInt] = Field(default_factory=list)
    provenance: AnalysisProvenanceV1

    @model_validator(mode="after")
    def _confirmed_ts(self) -> PersistedNarrativeEntityV1:
        if self.state == ArtifactState.confirmed and self.user_confirmed_at is None:
            raise ValueError("confirmed entity requires user_confirmed_at")
        return self


class PersistedNarrativeAssetV1(ContractModel):
    asset_id: PositiveInt
    snapshot_id: PositiveInt
    asset_type: AssetTypeStr
    title: str = Field(min_length=1)
    state: ArtifactState
    confidence: Confidence
    subject_entity_ids: list[PositiveInt] = Field(default_factory=list)
    current_version_id: PositiveInt
    created_by_run_id: PositiveInt
    updated_by_run_id: PositiveInt | None = None
    evidence_ids: list[PositiveInt] = Field(default_factory=list)
    provenance: AnalysisProvenanceV1


class NarrativeAssetVersionV1(ContractModel):
    asset_version_id: PositiveInt
    asset_id: PositiveInt
    version_no: PositiveInt
    state: ArtifactState
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_hash: Sha256Str
    source_run_id: PositiveInt
    source_window_ids: list[PositiveInt] = Field(default_factory=list)
    evidence_ids: list[PositiveInt] = Field(default_factory=list)
    created_by: Literal["engine", "user"]
    created_at: UtcDatetime
    is_current: bool

    @field_validator("payload")
    @classmethod
    def _payload_json(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not is_json_compatible(v):
            raise ValueError("payload must be JSON-compatible")
        return v

    @field_validator("source_window_ids")
    @classmethod
    def _sort_windows(cls, v: list[int]) -> list[int]:
        return dedupe_sorted_positive_ints(v) if v else v


class PersistedEvidenceV1(ContractModel):
    evidence_id: PositiveInt
    snapshot_id: PositiveInt
    locator: SnapshotEvidenceLocatorV1
    state: EvidenceState
    confidence: Confidence
    created_by_run_id: PositiveInt
    created_at: UtcDatetime


class NarrativeRefV1(ContractModel):
    kind: NarrativeRefKind
    id: PositiveInt


class PersistedNarrativeRelationV1(ContractModel):
    relation_id: PositiveInt
    snapshot_id: PositiveInt
    relation_type: RelationTypeStr
    subject: NarrativeRefV1
    object: NarrativeRefV1
    state: ArtifactState
    confidence: Confidence
    current_version_id: PositiveInt
    evidence_ids: list[PositiveInt] = Field(min_length=1)
    created_by_run_id: PositiveInt
    provenance: AnalysisProvenanceV1

    @model_validator(mode="after")
    def _not_identical_unless_alias(self) -> PersistedNarrativeRelationV1:
        same = self.subject.kind == self.object.kind and self.subject.id == self.object.id
        if same and self.relation_type != "alias_of":
            raise ValueError("subject and object must differ unless relation_type=alias_of")
        return self


class AnalysisConflictV1(ContractModel):
    conflict_id: PositiveInt
    snapshot_id: PositiveInt
    target: NarrativeRefV1
    confirmed_version_id: PositiveInt
    proposed_version_id: PositiveInt
    conflict_type: str = Field(min_length=1, max_length=128)
    status: ConflictStatus
    summary_safe: str = Field(min_length=1, max_length=1000)
    created_by_run_id: PositiveInt
    created_at: UtcDatetime
    resolved_at: UtcDatetime | None = None
    resolution_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _conflict_rules(self) -> AnalysisConflictV1:
        if self.confirmed_version_id == self.proposed_version_id:
            raise ValueError("confirmed_version_id must differ from proposed_version_id")
        if self.status == ConflictStatus.open:
            if self.resolved_at is not None:
                raise ValueError("open conflict must have resolved_at=null")
        else:
            if self.resolved_at is None:
                raise ValueError("resolved/dismissed conflict requires resolved_at")
        return self


class WholeBookWindowAnalysisRequestV1(ContractModel):
    contract_version: Literal["whole_book_contract_v1"] = WHOLE_BOOK_CONTRACT_VERSION  # type: ignore[assignment]
    run: WholeBookRunV1
    snapshot: BookSnapshotMetadataV1
    window: WholeBookWindowV1
    paragraphs: list[SnapshotParagraphV1]
    existing_confirmed_entities: list[PersistedNarrativeEntityV1] = Field(default_factory=list)
    existing_confirmed_assets: list[PersistedNarrativeAssetV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _window_paragraphs(self) -> WholeBookWindowAnalysisRequestV1:
        if self.contract_version != WHOLE_BOOK_CONTRACT_VERSION:
            raise ValueError("contract_version mismatch")
        if not self.paragraphs:
            raise ValueError("paragraphs must be non-empty for window analysis")
        idxs = [p.global_paragraph_index for p in self.paragraphs]
        if idxs != sorted(idxs):
            raise ValueError("paragraphs must be sorted by global_paragraph_index ascending")
        if idxs[0] != self.window.first_global_paragraph_index:
            raise ValueError("first paragraph must match window.first_global_paragraph_index")
        if idxs[-1] != self.window.last_global_paragraph_index:
            raise ValueError("last paragraph must match window.last_global_paragraph_index")
        snap_ids = {p.snapshot_id for p in self.paragraphs}
        if len(snap_ids) != 1 or self.window.snapshot_id not in snap_ids:
            raise ValueError("all paragraphs.snapshot_id must equal window.snapshot_id")
        if self.run.mode == WholeBookMode.whole_book_native:
            # Native must not carry chapter-analysis assets as substitutes; confirmed
            # whole-book entities/assets may be empty. Chapter assets are not a field
            # here — enforce via input_usage on run.
            self.run.input_usage.validate_for_mode(WholeBookMode.whole_book_native)
        return self


class WholeBookWindowAnalysisResponseV1(ContractModel):
    contract_version: Literal["whole_book_contract_v1"] = WHOLE_BOOK_CONTRACT_VERSION  # type: ignore[assignment]
    run_id: PositiveInt
    snapshot_id: PositiveInt
    window_id: PositiveInt
    entities: list[CandidateEntityV1] = Field(default_factory=list)
    assets: list[CandidateAssetV1] = Field(default_factory=list)
    evidences: list[CandidateEvidenceV1] = Field(default_factory=list)
    relations: list[CandidateRelationV1] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: AnalysisProvenanceV1

    @field_validator("warnings")
    @classmethod
    def _warn_len(cls, v: list[str]) -> list[str]:
        for item in v:
            if len(item) > 500:
                raise ValueError("each warning max 500 chars")
        return v


# ---------------------------------------------------------------------------
# Overview / Synthesis
# ---------------------------------------------------------------------------


class BookOverviewClaimV1(ContractModel):
    claim_key: Literal[
        "genre_and_narrative_features",
        "core_setting",
        "protagonist",
        "protagonist_core_goal",
        "main_conflict",
        "core_question",
        "final_resolution",
        "important_characters",
        "key_events",
    ]
    availability: OverviewClaimAvailability
    summary: str | None = Field(default=None, max_length=5000)
    confidence: Confidence | None = None
    evidence_ids: list[PositiveInt] = Field(default_factory=list)
    supporting_asset_ids: list[PositiveInt] = Field(default_factory=list)
    conflict_ids: list[PositiveInt] = Field(default_factory=list)

    @model_validator(mode="after")
    def _claim_rules(self) -> BookOverviewClaimV1:
        if self.availability == OverviewClaimAvailability.available:
            if not self.summary:
                raise ValueError("available claim requires summary")
            if self.confidence is None:
                raise ValueError("available claim requires confidence")
            if not self.evidence_ids:
                raise ValueError("available claim requires at least one evidence_id")
        elif self.availability == OverviewClaimAvailability.unavailable:
            if self.confidence is not None:
                raise ValueError("unavailable claim must have confidence=null")
        elif self.availability == OverviewClaimAvailability.insufficient_evidence:
            if self.summary:
                # May explain insufficiency but must not assert a determined conclusion.
                # Soft check: empty evidence is allowed.
                pass
        return self


class BookOverviewResultV1(ContractModel):
    result_version: Literal["book_overview_v1"] = BOOK_OVERVIEW_RESULT_VERSION  # type: ignore[assignment]
    contract_version: Literal["whole_book_contract_v1"] = WHOLE_BOOK_CONTRACT_VERSION  # type: ignore[assignment]
    run_id: PositiveInt
    book_id: PositiveInt
    snapshot_id: PositiveInt
    mode: WholeBookMode
    result_origin: ResultOrigin
    status: Literal["completed", "partial", "unavailable"]
    claims: list[BookOverviewClaimV1]
    important_entity_ids: list[PositiveInt] = Field(default_factory=list)
    key_event_asset_ids: list[PositiveInt] = Field(default_factory=list)
    coverage: WholeBookWindowCoverageV1
    input_usage: WholeBookInputUsageV1
    warnings: list[str] = Field(default_factory=list)
    provenance: AnalysisProvenanceV1
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _overview_rules(self) -> BookOverviewResultV1:
        self.input_usage.validate_for_mode(self.mode)
        keys = [c.claim_key for c in self.claims]
        if len(keys) != len(set(keys)):
            raise ValueError("claim_key must be unique within claims")
        if self.status == "completed":
            missing = set(BOOK_OVERVIEW_CLAIM_KEYS_V1) - set(keys)
            if missing:
                raise ValueError(f"completed overview missing claim_keys: {sorted(missing)}")
        if self.result_origin == ResultOrigin.fixture and self.provenance.result_origin != ResultOrigin.fixture:
            raise ValueError("fixture result requires fixture provenance")
        if self.result_origin == ResultOrigin.formal and self.provenance.result_origin != ResultOrigin.formal:
            raise ValueError("formal result requires formal provenance")
        for claim in self.claims:
            if claim.availability == OverviewClaimAvailability.available and not claim.evidence_ids:
                raise ValueError("available claim requires evidence")
        return self


class WholeBookSynthesisRequestV1(ContractModel):
    contract_version: Literal["whole_book_contract_v1"] = WHOLE_BOOK_CONTRACT_VERSION  # type: ignore[assignment]
    run: WholeBookRunV1
    snapshot: BookSnapshotMetadataV1
    coverage: WholeBookWindowCoverageV1
    entities: list[PersistedNarrativeEntityV1] = Field(default_factory=list)
    assets: list[PersistedNarrativeAssetV1] = Field(default_factory=list)
    relations: list[PersistedNarrativeRelationV1] = Field(default_factory=list)
    evidences: list[PersistedEvidenceV1] = Field(default_factory=list)
    open_conflicts: list[AnalysisConflictV1] = Field(default_factory=list)


class WholeBookSynthesisResponseV1(ContractModel):
    contract_version: Literal["whole_book_contract_v1"] = WHOLE_BOOK_CONTRACT_VERSION  # type: ignore[assignment]
    result: BookOverviewResultV1
