"""Phase 1B-P DTO dataclasses (Contract freeze — not full business payloads)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class EvidenceBindingDTO:
    """Shared Evidence shape for Asset and Relation evidence rows."""

    book_snapshot_id: int
    snapshot_chapter_id: int
    snapshot_paragraph_id: int
    paragraph_content_hash: str
    start_offset: int
    end_offset: int
    evidence_role: str = "support"
    evidence_label: str = ""
    source_scene_id: int | None = None


@dataclass(frozen=True)
class CanonicalVersionSwitchDTO:
    """Transactional canonical switch intent (service-layer Contract).

    Rules:
    - Clear prior is_canonical for the same stable id in the same transaction.
    - Set new version is_canonical=True only if review_status in {confirmed, corrected}.
    - rejected and candidate must not become canonical.
    - Locked stable row blocks model-driven switches; user unlock required.
    """

    stable_id: int
    new_version_id: int
    actor: str
    reason: str = ""


@dataclass(frozen=True)
class PatternMapAssetProjectionDTO:
    """Derived projection consumed by Pattern Map — NOT an ORM table."""

    asset_id: int
    asset_version_id: int
    asset_type: str
    title: str
    confidence: float
    review_status: str
    evidence_count: int
    start_chapter_id: int | None = None
    end_chapter_id: int | None = None
    related_character_ids: tuple[str, ...] = ()
    related_storyline_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PatternMapRelationProjectionDTO:
    """Derived projection for Pattern Map edges — NOT an ORM table."""

    relation_id: int
    relation_version_id: int
    source_asset_id: int
    target_asset_id: int
    relation_type: str
    confidence: float
    review_status: str
    evidence_count: int


@dataclass
class AnalysisConflictDTO:
    id: int | None
    book_id: int
    conflict_type: str
    left_ref_type: str
    left_ref_id: str
    right_ref_type: str
    right_ref_id: str
    description: str = ""
    severity: str = "warning"
    status: str = "open"
    run_id: int | None = None
    book_snapshot_id: int | None = None
    resolution_json: str = "{}"
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime | None = field(default=None)
