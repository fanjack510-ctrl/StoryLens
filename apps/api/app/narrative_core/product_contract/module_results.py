"""Module result payload DTOs (Phase 1D-P freeze — no analysis algorithms)."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    stages: tuple[StructureStageItemDto, ...]
    turning_points: tuple[TurningPointDto, ...]
    act_or_phase_labels: tuple[str, ...]
    chapter_ranges: tuple[tuple[int | None, int | None], ...]
    narrative_function: str
    evidence_refs: tuple[EvidenceRefLite, ...]
    confidence: float | None = None


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


def assert_payload_keys_for_module(
    module_key: WholeBookModuleKey,
    payload: dict[str, Any],
) -> None:
    """Lightweight shape guard — fields present as keys (values may be empty)."""

    dto_cls = MODULE_RESULT_DTO_BY_KEY[module_key]
    required = getattr(dto_cls, "__dataclass_fields__", {})
    missing = [name for name in required if name not in payload]
    if missing:
        raise ValueError(f"{module_key.value} payload missing fields: {missing}")
