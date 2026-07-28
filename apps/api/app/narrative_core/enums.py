"""Frozen public enums for Narrative Intelligence Core (Phase 1P).

Agents must import these values; do not scatter string literals in services.
"""

from __future__ import annotations

from enum import StrEnum


class AnalysisScopeType(StrEnum):
    CHAPTER = "chapter"
    CHAPTER_RANGE = "chapter_range"
    BOOK = "book"


class SnapshotStatus(StrEnum):
    BUILDING = "building"
    COMPLETED = "completed"
    FAILED = "failed"
    # Invalid: completed snapshot whose referenced live book text drifted or
    # integrity validation failed. Not a retryable building state.
    INVALID = "invalid"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    """Narrative staged-run status constants (AnalysisRun.status string column).

    Not a DB enum — legacy scene-pipeline statuses continue to coexist as free
    strings (e.g. boundary_candidates_running). pause ≠ failed; interrupted ≠ failed.

    STEP 2.1 additive Overview production statuses (preparing/analyzing/
    materializing/synthesizing). Keep queued/running/interrupted for Free.
    """

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PREPARING = "preparing"
    ANALYZING = "analyzing"
    MATERIALIZING = "materializing"
    SYNTHESIZING = "synthesizing"
    PAUSED = "paused"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisType(StrEnum):
    """Compatible + Phase 1 whole-book placeholders only.

    Do not expand with every future module here. Legacy 1.0.5 rows may have
    NULL analysis_type; treat NULL + task_type=scene_pipeline as chapter scene
    pipeline (see contract docs). Do not force backfill in Phase 1P.
    """

    SCENE_PIPELINE = "scene_pipeline"
    WHOLE_BOOK_NATIVE = "whole_book_native"
    WHOLE_BOOK_ENHANCED = "whole_book_enhanced"


# ---------------------------------------------------------------------------
# Phase 1B-P — Entity / Asset / Relation / Evidence / Conflict (frozen)
# ---------------------------------------------------------------------------


class EntityType(StrEnum):
    """Stable entity kinds. Extensible later; never book-specific custom types."""

    CHARACTER = "character"
    LOCATION = "location"
    ORGANIZATION = "organization"
    FACTION = "faction"
    OBJECT = "object"
    CONCEPT = "concept"
    TIMELINE_ENTITY = "timeline_entity"
    UNKNOWN = "unknown"


class EntityLifecycleStatus(StrEnum):
    """Entity identity lifecycle — NOT review/candidate status."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class AliasType(StrEnum):
    DISPLAY = "display"
    NICKNAME = "nickname"
    TITLE = "title"
    TRANSLITERATION = "transliteration"
    OTHER = "other"


class AliasReviewStatus(StrEnum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class AssetLifecycleStatus(StrEnum):
    """Stable asset identity lifecycle — orthogonal to version review_status."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    STALE = "stale"


class AssetType(StrEnum):
    """Extensible asset-type contract. Values are strings; list is minimum set."""

    EVENT = "event"
    GOAL = "goal"
    CONFLICT = "conflict"
    CHOICE = "choice"
    CONSEQUENCE = "consequence"
    QUESTION = "question"
    HOOK = "hook"
    CLUE = "clue"
    FORESHADOWING = "foreshadowing"
    MISDIRECTION = "misdirection"
    REVEAL = "reveal"
    PARTIAL_PAYOFF = "partial_payoff"
    FINAL_PAYOFF = "final_payoff"
    REVERSAL = "reversal"
    STORYLINE = "storyline"
    STRUCTURE_STAGE = "structure_stage"
    CHAPTER_FUNCTION = "chapter_function"
    CHARACTER_ARC_STAGE = "character_arc_stage"
    DIAGNOSIS_INPUT = "diagnosis_input"


class ReviewStatus(StrEnum):
    """Version review status for Asset Version and Relation Version.

    Independent of Lock. candidate never auto-becomes canonical.
    """

    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class OriginType(StrEnum):
    MODEL = "model"
    USER = "user"
    MIGRATED = "migrated"
    SYSTEM = "system"


class EvidenceRole(StrEnum):
    SUPPORT = "support"
    CONTRADICT = "contradict"
    CONTEXT = "context"


class RelationLifecycleStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    STALE = "stale"


class RelationType(StrEnum):
    """Extensible relation-type contract. Existence still requires Evidence."""

    CAUSES = "causes"
    ENABLES = "enables"
    BLOCKS = "blocks"
    ESCALATES = "escalates"
    RESOLVES = "resolves"
    PAYS_OFF = "pays_off"
    FORESHADOWS = "foreshadows"
    REVEALS = "reveals"
    CONTRADICTS = "contradicts"
    BELONGS_TO = "belongs_to"
    ADVANCES = "advances"
    CHANGES_RELATIONSHIP = "changes_relationship"
    PRECEDES = "precedes"
    PARALLELS = "parallels"


class ConflictType(StrEnum):
    LOCKED_ASSET_VS_NEW_RUN = "locked_asset_vs_new_run"
    CANDIDATE_CONTRADICTION = "candidate_contradiction"
    ENTITY_IDENTITY = "entity_identity"
    RELATION_CONFLICT = "relation_conflict"
    EVIDENCE_STALE = "evidence_stale"
    SNAPSHOT_MISMATCH = "snapshot_mismatch"
    DUPLICATE_ASSET_CANDIDATE = "duplicate_asset_candidate"


class ConflictSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class ConflictStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ConflictRefType(StrEnum):
    """Polymorphic reference kinds used by analysis_conflicts left/right refs."""

    ENTITY = "entity"
    ENTITY_ALIAS = "entity_alias"
    ASSET = "asset"
    ASSET_VERSION = "asset_version"
    RELATION = "relation"
    RELATION_VERSION = "relation_version"
    ASSET_EVIDENCE = "asset_evidence"
    RELATION_EVIDENCE = "relation_evidence"
    SNAPSHOT = "snapshot"
    RUN = "run"

    # Legacy values accepted at validation boundary only (map alias → entity_alias).
    ALIAS = "alias"
    EVIDENCE = "evidence"


# ---------------------------------------------------------------------------
# Phase 1C-P — Capability / WholeBook Engine contracts (frozen)
# ---------------------------------------------------------------------------


class CapabilityKey(StrEnum):
    """Canonical capability keys (backend + desktop entitlementApi).

    WB-0.3 adds independent whole-book product capabilities; legacy keys retained.
    """

    WHOLE_BOOK_ANALYSIS = "whole_book_analysis"
    NARRATIVE_ASSET_LIBRARY = "narrative_asset_library"
    STORY_LAB = "story_lab"
    CROSS_BOOK_SEARCH = "cross_book_search"
    ADVANCED_EXPORT = "advanced_export"
    PRO_WHOLE_BOOK_INSIGHTS = "pro_whole_book_insights"
    WHOLE_BOOK_NATIVE = "whole_book_native"
    WHOLE_BOOK_ENHANCED = "whole_book_enhanced"
    CHAPTER_AGGREGATE_INSIGHTS = "chapter_aggregate_insights"


class CapabilityAvailability(StrEnum):
    UNAVAILABLE = "unavailable"
    PREVIEW = "preview"
    AVAILABLE = "available"


class CapabilityReasonCode(StrEnum):
    CAPABILITY_NOT_SHIPPED = "CAPABILITY_NOT_SHIPPED"
    CAPABILITY_NOT_LICENSED = "CAPABILITY_NOT_LICENSED"
    CAPABILITY_QUOTA_EXCEEDED = "CAPABILITY_QUOTA_EXCEEDED"
    CAPABILITY_OFFLINE_NOT_ALLOWED = "CAPABILITY_OFFLINE_NOT_ALLOWED"
    CAPABILITY_LICENSE_EXPIRED = "CAPABILITY_LICENSE_EXPIRED"
    CAPABILITY_LICENSE_INVALID = "CAPABILITY_LICENSE_INVALID"
    CAPABILITY_AVAILABLE = "CAPABILITY_AVAILABLE"
    CAPABILITY_PREVIEW_ONLY = "CAPABILITY_PREVIEW_ONLY"
    CAPABILITY_UNKNOWN = "CAPABILITY_UNKNOWN"
    CAPABILITY_MODE_NOT_SUPPORTED = "CAPABILITY_MODE_NOT_SUPPORTED"
    WHOLE_BOOK_NOT_RELEASED = "whole_book_not_released"


class WholeBookAnalysisMode(StrEnum):
    """Analysis modes for whole-book runs — NOT separate capability keys."""

    NATIVE = "whole_book_native"
    ENHANCED = "whole_book_enhanced"

    @classmethod
    def from_analysis_type(cls, analysis_type: AnalysisType | str) -> WholeBookAnalysisMode:
        value = analysis_type.value if isinstance(analysis_type, AnalysisType) else str(analysis_type)
        if value == AnalysisType.WHOLE_BOOK_NATIVE:
            return cls.NATIVE
        if value == AnalysisType.WHOLE_BOOK_ENHANCED:
            return cls.ENHANCED
        raise ValueError(f"unsupported whole-book analysis mode: {value}")


class WholeBookModuleKey(StrEnum):
    BOOK_OVERVIEW = "book_overview"
    STRUCTURE_STAGES = "structure_stages"
    CHAPTER_FUNCTIONS = "chapter_functions"
    STORYLINES = "storylines"
    CHARACTERS = "characters"
    CHARACTER_ARCS = "character_arcs"
    RELATIONSHIPS = "relationships"
    HOOKS_PAYOFFS = "hooks_payoffs"
    CAUSAL_CHAIN = "causal_chain"
    BASIC_TIMELINE = "basic_timeline"
    DIAGNOSTICS = "diagnostics"


class WholeBookStageKey(StrEnum):
    """Legacy Lab / multi-module 10-stage keys — do not delete or renumber."""

    BUILD_FULLTEXT_INDEX = "build_fulltext_index"
    RESOLVE_ENTITIES = "resolve_entities"
    ANALYZE_STRUCTURE = "analyze_structure"
    ANALYZE_STORYLINES = "analyze_storylines"
    ANALYZE_CHARACTERS = "analyze_characters"
    ANALYZE_HOOKS = "analyze_hooks"
    ANALYZE_CAUSALITY_TIMELINE = "analyze_causality_timeline"
    GENERATE_DIAGNOSTICS = "generate_diagnostics"
    VERIFY_EVIDENCE = "verify_evidence"
    PERSIST_NARRATIVE_ASSETS = "persist_narrative_assets"


class OverviewProductionStageKey(StrEnum):
    """1.1.0 native Overview production stages (separate from WholeBookStageKey)."""

    SNAPSHOT_PREFLIGHT = "snapshot_preflight"
    BUILD_CONTEXT_WINDOWS = "build_context_windows"
    EXTRACT_OVERVIEW_FACTS = "extract_overview_facts"
    MATERIALIZE_ASSETS = "materialize_assets"
    GENERATE_OVERVIEW_PROJECTION = "generate_overview_projection"
    FINALIZE = "finalize"


class WindowStatus(StrEnum):
    """Whole-book window execution status (whole_book_run_windows.status)."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class OverviewFieldStatus(StrEnum):
    """Structured Overview field support status (projection / API)."""

    SUPPORTED = "supported"
    LOW_CONFIDENCE = "low_confidence"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTED = "conflicted"


class QuotaPolicyKind(StrEnum):
    NONE = "none"
    PER_BOOK = "per_book"
    PER_DAY = "per_day"
    CONCURRENT_RUNS = "concurrent_runs"
    CHARACTER_LIMIT = "character_limit"
    TOKEN_BUDGET = "token_budget"
    COST_BUDGET = "cost_budget"


class CostClass(StrEnum):
    FREE = "free"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
