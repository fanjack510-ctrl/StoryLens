"""Whole-book contract v1 constants (frozen)."""

from __future__ import annotations

WHOLE_BOOK_CONTRACT_VERSION = "whole_book_contract_v1"
SNAPSHOT_LOCATOR_VERSION = "snapshot_paragraph_v1"
ANALYSIS_PROVENANCE_VERSION = "analysis_provenance_v1"
BOOK_OVERVIEW_RESULT_VERSION = "book_overview_v1"
WHOLE_BOOK_SCHEMA_NAME = "storylens_whole_book_contract_v1"

# Reserved stage codes for WB-1 (contract-only; no state machine here).
WHOLE_BOOK_STAGE_CODES_V1: tuple[str, ...] = (
    "snapshot",
    "windowing",
    "extract_entities_events",
    "materialize_assets",
    "synthesize_overview",
    "synthesize_structure_stages",
    "synthesize_chapter_functions",
    "project_result",
    "finalize",
)

# Reserved asset types (registry-extensible; not a DB enum column).
WHOLE_BOOK_ASSET_TYPES_V1: tuple[str, ...] = (
    "character_profile",
    "event",
    "goal",
    "conflict",
    "question",
    "setting_fact",
    "overview_claim",
)

# Reserved relation types (registry-extensible; not a DB enum column).
WHOLE_BOOK_RELATION_TYPES_V1: tuple[str, ...] = (
    "alias_of",
    "participates_in",
    "causes",
    "precedes",
    "supports",
    "opposes",
    "supports_claim",
    "conflicts_with",
)

BOOK_OVERVIEW_CLAIM_KEYS_V1: tuple[str, ...] = (
    "genre_and_narrative_features",
    "core_setting",
    "protagonist",
    "protagonist_core_goal",
    "main_conflict",
    "core_question",
    "final_resolution",
    "important_characters",
    "key_events",
)

# Wire models included in Public/Private schema identity hash.
WIRE_MODEL_NAMES_V1: tuple[str, ...] = (
    "BookSnapshotMetadataV1",
    "SnapshotChapterV1",
    "SnapshotParagraphV1",
    "SnapshotEvidenceLocatorV1",
    "WholeBookRunV1",
    "WholeBookWindowV1",
    "WholeBookWindowCoverageV1",
    "AnalysisProvenanceV1",
    "WholeBookInputUsageV1",
    "WholeBookWindowAnalysisRequestV1",
    "CandidateEvidenceV1",
    "CandidateEntityAliasV1",
    "CandidateEntityV1",
    "CandidateAssetV1",
    "CandidateNarrativeRefV1",
    "CandidateRelationV1",
    "WholeBookWindowAnalysisResponseV1",
    "PersistedNarrativeEntityV1",
    "PersistedNarrativeAssetV1",
    "NarrativeAssetVersionV1",
    "PersistedEvidenceV1",
    "NarrativeRefV1",
    "PersistedNarrativeRelationV1",
    "AnalysisConflictV1",
    "BookOverviewClaimV1",
    "BookOverviewResultV1",
    "WholeBookSynthesisRequestV1",
    "WholeBookSynthesisResponseV1",
)

# Public-only persistence DTOs (not in wire identity hash).
PUBLIC_ONLY_MODEL_NAMES_V1: tuple[str, ...] = (
    "WholeBookRunStageV1",
    "WholeBookCheckpointV1",
)
