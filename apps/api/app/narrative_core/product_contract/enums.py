"""Phase 1D-P product-facing enums (UI / envelope / review).

Reuses narrative_core.enums for ModuleKey / Mode / StageStatus where possible.
Do not duplicate conflicting string values.
"""

from __future__ import annotations

from enum import StrEnum


class WholeBookModuleStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    RUNNING = "running"
    PARTIAL = "partial"
    COMPLETED = "completed"
    FAILED = "failed"
    STALE = "stale"
    BLOCKED = "blocked"


class WholeBookRunViewStatus(StrEnum):
    """Product Run view statuses (subset of staged-run semantics).

    Note: Phase 1A RunStatus also has ``queued``; product view omits it.
    """

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunAllowedAction(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    RETRY = "retry"
    CANCEL = "cancel"
    VIEW_PARTIAL_RESULTS = "view_partial_results"


class EvidenceIntegrityStatus(StrEnum):
    VALID = "valid"
    STALE = "stale"
    HASH_MISMATCH = "hash_mismatch"
    MISSING = "missing"
    INACCESSIBLE = "inaccessible"


class NarrativeReviewAction(StrEnum):
    CONFIRM = "confirm"
    CORRECT = "correct"
    REJECT = "reject"
    LOCK = "lock"
    UNLOCK = "unlock"
    MARK_STALE = "mark_stale"
    RESOLVE_CONFLICT = "resolve_conflict"
    DISMISS_CONFLICT = "dismiss_conflict"


class ReviewTargetType(StrEnum):
    ASSET = "asset"
    ASSET_VERSION = "asset_version"
    RELATION = "relation"
    RELATION_VERSION = "relation_version"
    CONFLICT = "conflict"
    MODULE_RESULT = "module_result"


class StructureMapViewMode(StrEnum):
    STRUCTURE_STAGES = "structure_stages"
    STORYLINES = "storylines"
    CHARACTER_GROWTH = "character_growth"


class ResultNavSectionKey(StrEnum):
    OVERVIEW = "overview"
    STRUCTURE = "structure"
    STORYLINES = "storylines"
    CHARACTERS = "characters"
    RELATIONSHIPS = "relationships"
    HOOKS_PAYOFFS = "hooks_payoffs"
    CAUSAL_TIMELINE = "causal_timeline"
    DIAGNOSTICS = "diagnostics"
    EVIDENCE_CONFLICTS = "evidence_conflicts"
    STRUCTURE_MAP = "structure_map"
