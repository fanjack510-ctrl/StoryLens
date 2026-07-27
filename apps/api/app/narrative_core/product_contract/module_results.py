"""Module result payload DTOs (Phase 1D-P freeze — no analysis algorithms)."""

from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import MISSING
from typing import Any

from app.narrative_core.enums import WholeBookModuleKey


@dataclass(frozen=True, slots=True)
class EvidenceRefLite:
    evidence_id: int | str
    evidence_role: str = "support"


@dataclass(frozen=True, slots=True)
class BookOverviewResultDto:
    logline: str
    premise: str
    central_question: str
    primary_conflict: str
    protagonist_asset_id: int | None
    major_storyline_ids: tuple[int, ...]
    structure_summary: str
    ending_state: str
    evidence_refs: tuple[EvidenceRefLite, ...]
    confidence: float | None = None


# --- Citation Evidence Contract V2 (CHG-058) — alongside V1, not a replacement ---


class ClaimStatus:
    """Claim status string constants (product DTO; not a DB enum)."""

    OBSERVED = "observed"
    INFERRED = "inferred"
    NOT_OBSERVED = "not_observed"


CLAIM_STATUS_VALUES: tuple[str, ...] = (
    ClaimStatus.OBSERVED,
    ClaimStatus.INFERRED,
    ClaimStatus.NOT_OBSERVED,
)


@dataclass(frozen=True, slots=True)
class CitedClaimDto:
    value: str | None
    status: str
    citation_ids: tuple[str, ...] = ()
    confidence: float | None = None

    def __post_init__(self) -> None:
        status = str(self.status or "").strip()
        if status not in CLAIM_STATUS_VALUES:
            raise ValueError(f"invalid claim status: {self.status!r}")
        object.__setattr__(self, "status", status)
        ids = tuple(str(x) for x in (self.citation_ids or ()))
        object.__setattr__(self, "citation_ids", ids)
        nonempty = isinstance(self.value, str) and bool(self.value.strip())
        if status in (ClaimStatus.OBSERVED, ClaimStatus.INFERRED):
            if not nonempty:
                raise ValueError("observed/inferred claim requires non-empty value")
            if not ids:
                raise ValueError("observed/inferred claim requires at least one citation_id")
        elif status == ClaimStatus.NOT_OBSERVED:
            if ids:
                raise ValueError("not_observed claim must not carry citation_ids")
            if nonempty:
                raise ValueError("not_observed claim must not carry a content value")


@dataclass(frozen=True, slots=True)
class BookOverviewResultV2:
    """Claim-bound BookOverview contract (evidence_contract_version=v2)."""

    logline: CitedClaimDto
    premise: CitedClaimDto
    central_question: CitedClaimDto
    primary_conflict: CitedClaimDto
    structure_summary: CitedClaimDto
    ending_state: CitedClaimDto
    contract_version: str = "v2"
    overall_confidence: float | None = None

    def __post_init__(self) -> None:
        if str(self.contract_version or "") != "v2":
            raise ValueError("BookOverviewResultV2.contract_version must be 'v2'")


@dataclass(frozen=True, slots=True)
class StructureStageItemDto:
    stage_id: str
    label: str
    chapter_range: tuple[int | None, int | None] = (None, None)
    narrative_function: str = ""
    order: int = 0


@dataclass(frozen=True, slots=True)
class TurningPointDto:
    turning_point_id: str
    label: str
    chapter_id: int | None = None
    summary: str = ""


@dataclass(frozen=True, slots=True)
class StructureStagesResultDto:
    """V1 Structure Stages result — keep read-only for historical projection."""

    stages: tuple[StructureStageItemDto, ...]
    turning_points: tuple[TurningPointDto, ...]
    act_or_phase_labels: tuple[str, ...]
    chapter_ranges: tuple[tuple[int | None, int | None], ...]
    narrative_function: str
    evidence_refs: tuple[EvidenceRefLite, ...]
    confidence: float | None = None


# --- Structure Stages Citation Evidence Contract V2 (CHG-20260725-001) ---


class CoverageScope:
    """coverage_scope string constants (product DTO; not a DB enum)."""

    LOCAL = "local"
    PARTIAL_SPAN = "partial_span"
    FULL_SELECTED_RANGE = "full_selected_range"
    INSUFFICIENT = "insufficient"


COVERAGE_SCOPE_VALUES: tuple[str, ...] = (
    CoverageScope.LOCAL,
    CoverageScope.PARTIAL_SPAN,
    CoverageScope.FULL_SELECTED_RANGE,
    CoverageScope.INSUFFICIENT,
)


def normalize_coverage_scope_wire(value: Any) -> str | None:
    """Coerce private-engine enum / repr values to wire-format coverage_scope strings."""

    if value is None:
        return None
    if hasattr(value, "value"):
        return str(getattr(value, "value"))
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("CoverageScope."):
        return text.rsplit(".", 1)[-1].lower()
    return text


@dataclass(frozen=True, slots=True)
class CitedBoundaryDto:
    """Boundary locator bound to catalog citation_ids (value/note optional)."""

    citation_ids: tuple[str, ...]
    value: str | None = None
    note: str | None = None
    status: str | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        ids = tuple(str(x) for x in (self.citation_ids or ()))
        object.__setattr__(self, "citation_ids", ids)
        if not ids:
            raise ValueError("CitedBoundaryDto requires at least one citation_id")
        if self.status is not None:
            status = str(self.status or "").strip()
            if status and status not in CLAIM_STATUS_VALUES:
                raise ValueError(f"invalid boundary status: {self.status!r}")
            object.__setattr__(self, "status", status or None)


@dataclass(frozen=True, slots=True)
class StructureStageV2:
    """Wire-compatible with private StructureStageV2 (local refs + cited summary)."""

    local_stage_ref: str
    title: str
    summary: CitedClaimDto
    start_boundary: CitedBoundaryDto
    end_boundary: CitedBoundaryDto
    order_index: int = 0
    stage_type: str = "unknown"
    supporting_citation_ids: tuple[str, ...] = ()
    related_turning_point_refs: tuple[str, ...] = ()
    narrative_function: str | None = None
    confidence: float | None = None
    # Formal persistence key (STAGE-NNN) — filled by mapper; optional on wire.
    stage_key: str | None = None
    chapter_range: tuple[int | None, int | None] = (None, None)

    def __post_init__(self) -> None:
        ref = str(self.local_stage_ref or "").strip()
        if not ref:
            raise ValueError("StructureStageV2.local_stage_ref required")
        object.__setattr__(self, "local_stage_ref", ref)
        object.__setattr__(
            self,
            "supporting_citation_ids",
            tuple(str(x) for x in (self.supporting_citation_ids or ())),
        )
        object.__setattr__(
            self,
            "related_turning_point_refs",
            tuple(str(x) for x in (self.related_turning_point_refs or ())),
        )


@dataclass(frozen=True, slots=True)
class TurningPointV2:
    local_turning_point_ref: str
    title: str
    description: CitedClaimDto
    citation_ids: tuple[str, ...] = ()
    order_index: int = 0
    turning_point_type: str = "unknown"
    before_state: str | None = None
    after_state: str | None = None
    impact: str | None = None
    related_stage_refs: tuple[str, ...] = ()
    confidence: float | None = None
    turning_point_key: str | None = None
    chapter_id: int | None = None

    def __post_init__(self) -> None:
        ref = str(self.local_turning_point_ref or "").strip()
        if not ref:
            raise ValueError("TurningPointV2.local_turning_point_ref required")
        object.__setattr__(self, "local_turning_point_ref", ref)
        object.__setattr__(
            self,
            "citation_ids",
            tuple(str(x) for x in (self.citation_ids or ())),
        )
        object.__setattr__(
            self,
            "related_stage_refs",
            tuple(str(x) for x in (self.related_stage_refs or ())),
        )


@dataclass(frozen=True, slots=True)
class StructureStagesResultV2:
    """Claim-bound Structure Stages contract (evidence_contract_version=v2)."""

    stages: tuple[StructureStageV2, ...]
    turning_points: tuple[TurningPointV2, ...]
    coverage_scope: str
    contract_version: str = "v2"
    evidence_contract_version: str = "v2"
    analysis_confidence: float | None = None
    overall_confidence: float | None = None
    limitations: tuple[str, ...] = ()
    context_capabilities: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if str(self.contract_version or "") != "v2":
            raise ValueError("StructureStagesResultV2.contract_version must be 'v2'")
        if str(self.evidence_contract_version or "v2") != "v2":
            raise ValueError("evidence_contract_version must be 'v2'")
        scope = str(self.coverage_scope or "").strip()
        if scope not in COVERAGE_SCOPE_VALUES:
            raise ValueError(f"invalid coverage_scope: {self.coverage_scope!r}")
        object.__setattr__(self, "coverage_scope", scope)
        object.__setattr__(
            self,
            "limitations",
            tuple(str(x) for x in (self.limitations or ())),
        )
        if scope == CoverageScope.INSUFFICIENT and self.stages:
            raise ValueError("insufficient coverage_scope forbids non-empty stages")
        if scope != CoverageScope.INSUFFICIENT and not self.stages:
            raise ValueError("non-insufficient coverage_scope requires ≥1 stage")
        if self.overall_confidence is None and self.analysis_confidence is not None:
            object.__setattr__(self, "overall_confidence", self.analysis_confidence)


@dataclass(frozen=True, slots=True)
class ChapterFunctionsResultDto:
    chapter_id: int
    chapter_order: int
    function_labels: tuple[str, ...]
    primary_storyline_ids: tuple[int, ...]
    character_focus_ids: tuple[int, ...]
    hook_ids: tuple[int, ...]
    payoff_ids: tuple[int, ...]
    change_summary: str
    evidence_refs: tuple[EvidenceRefLite, ...]


@dataclass(frozen=True, slots=True)
class StorylinesResultDto:
    storyline_asset_id: int
    title: str
    summary: str
    storyline_type: str
    chapter_range: tuple[int | None, int | None]
    key_event_ids: tuple[int, ...]
    involved_entity_ids: tuple[int, ...]
    relation_ids: tuple[int, ...]
    status: str
    evidence_refs: tuple[EvidenceRefLite, ...]


@dataclass(frozen=True, slots=True)
class CharactersResultDto:
    entity_id: int
    canonical_name: str
    aliases: tuple[str, ...]
    role: str
    goal_asset_ids: tuple[int, ...]
    conflict_asset_ids: tuple[int, ...]
    choice_asset_ids: tuple[int, ...]
    consequence_asset_ids: tuple[int, ...]
    arc_stage_ids: tuple[int, ...]
    chapter_range: tuple[int | None, int | None]
    evidence_refs: tuple[EvidenceRefLite, ...]


@dataclass(frozen=True, slots=True)
class CharacterArcsResultDto:
    entity_id: int
    canonical_name: str
    aliases: tuple[str, ...]
    role: str
    goal_asset_ids: tuple[int, ...]
    conflict_asset_ids: tuple[int, ...]
    choice_asset_ids: tuple[int, ...]
    consequence_asset_ids: tuple[int, ...]
    arc_stage_ids: tuple[int, ...]
    chapter_range: tuple[int | None, int | None]
    evidence_refs: tuple[EvidenceRefLite, ...]


@dataclass(frozen=True, slots=True)
class RelationshipChangeDto:
    chapter_id: int | None
    summary: str
    from_stage: str | None = None
    to_stage: str | None = None


@dataclass(frozen=True, slots=True)
class RelationshipsResultDto:
    source_entity_id: int
    target_entity_id: int
    relationship_stage: str
    relation_asset_ids: tuple[int, ...]
    changes: tuple[RelationshipChangeDto, ...]
    chapter_range: tuple[int | None, int | None]
    evidence_refs: tuple[EvidenceRefLite, ...]


@dataclass(frozen=True, slots=True)
class HooksPayoffsResultDto:
    hook_asset_id: int
    hook_type: str
    setup_chapter: int | None
    payoff_asset_ids: tuple[int, ...]
    payoff_status: str
    payoff_chapters: tuple[int, ...]
    delay: int | None
    evidence_refs: tuple[EvidenceRefLite, ...]


@dataclass(frozen=True, slots=True)
class CausalChainResultDto:
    source_asset_id: int
    target_asset_id: int
    relation_id: int
    causal_type: str
    strength: float | None
    evidence_refs: tuple[EvidenceRefLite, ...]


@dataclass(frozen=True, slots=True)
class TimelineItemDto:
    item_id: str
    story_time: str | None
    narrative_order: int
    chapter_id: int | None
    event_asset_ids: tuple[int, ...]
    certainty: str
    summary: str = ""


@dataclass(frozen=True, slots=True)
class BasicTimelineResultDto:
    timeline_items: tuple[TimelineItemDto, ...]
    story_time: str | None
    narrative_order: tuple[int, ...]
    chapter_id: int | None
    event_asset_ids: tuple[int, ...]
    certainty: str
    evidence_refs: tuple[EvidenceRefLite, ...]


@dataclass(frozen=True, slots=True)
class DiagnosticItemDto:
    diagnostic_id: str
    category: str
    severity: str
    affected_asset_ids: tuple[int, ...]
    affected_chapters: tuple[int, ...]
    evidence_refs: tuple[EvidenceRefLite, ...]
    explanation: str
    user_actionable: bool
    recommendation: str


@dataclass(frozen=True, slots=True)
class DiagnosticsResultDto:
    diagnostic_items: tuple[DiagnosticItemDto, ...]
    category: str | None = None
    severity: str | None = None
    affected_asset_ids: tuple[int, ...] = ()
    affected_chapters: tuple[int, ...] = ()
    evidence_refs: tuple[EvidenceRefLite, ...] = ()
    explanation: str = ""
    user_actionable: bool = False
    recommendation: str = ""


MODULE_RESULT_DTO_BY_KEY: dict[WholeBookModuleKey, type] = {
    WholeBookModuleKey.BOOK_OVERVIEW: BookOverviewResultDto,
    WholeBookModuleKey.STRUCTURE_STAGES: StructureStagesResultDto,
    WholeBookModuleKey.CHAPTER_FUNCTIONS: ChapterFunctionsResultDto,
    WholeBookModuleKey.STORYLINES: StorylinesResultDto,
    WholeBookModuleKey.CHARACTERS: CharactersResultDto,
    WholeBookModuleKey.CHARACTER_ARCS: CharacterArcsResultDto,
    WholeBookModuleKey.RELATIONSHIPS: RelationshipsResultDto,
    WholeBookModuleKey.HOOKS_PAYOFFS: HooksPayoffsResultDto,
    WholeBookModuleKey.CAUSAL_CHAIN: CausalChainResultDto,
    WholeBookModuleKey.BASIC_TIMELINE: BasicTimelineResultDto,
    WholeBookModuleKey.DIAGNOSTICS: DiagnosticsResultDto,
}

MODULE_RESULT_DTO_NAMES: tuple[str, ...] = tuple(
    cls.__name__ for cls in MODULE_RESULT_DTO_BY_KEY.values()
)


def resolve_module_result_dto_class(
    module_key: WholeBookModuleKey,
    payload: Mapping[str, Any],
) -> type:
    """Select V1 vs V2 DTO class from contract/schema markers on the payload."""

    data = dict(payload or {})
    schema = str(
        data.get("schema")
        or data.get("dto_schema_id")
        or data.get("structured_output_schema")
        or ""
    )
    contract = str(data.get("contract_version") or "").strip().lower()
    evidence_ver = str(data.get("evidence_contract_version") or "").strip().lower()
    is_v2 = contract == "v2" or evidence_ver == "v2"
    if module_key == WholeBookModuleKey.STRUCTURE_STAGES:
        if is_v2 or "StructureStagesResultV2" in schema:
            return StructureStagesResultV2
    if module_key == WholeBookModuleKey.BOOK_OVERVIEW:
        if is_v2 or "BookOverviewResultV2" in schema:
            return BookOverviewResultV2
    return MODULE_RESULT_DTO_BY_KEY[module_key]


def assert_payload_keys_for_module(
    module_key: WholeBookModuleKey,
    payload: dict[str, Any],
    *,
    dto_cls: type | None = None,
) -> None:
    """Lightweight shape guard — fields present as keys (values may be empty)."""

    dto_cls = dto_cls or resolve_module_result_dto_class(module_key, payload)
    required = getattr(dto_cls, "__dataclass_fields__", {})
    missing = [
        name
        for name, spec in required.items()
        if spec.default is MISSING
        and spec.default_factory is MISSING
        and name not in payload
    ]
    if missing:
        raise ValueError(f"{module_key.value} payload missing fields: {missing}")
