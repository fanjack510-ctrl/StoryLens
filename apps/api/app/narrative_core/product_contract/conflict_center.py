"""Conflict Center DTO contract (Phase 1D-P).

Blocking conflicts must not be auto-adjudicated by the system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.narrative_core.enums import ConflictSeverity, ConflictStatus, ConflictType
from app.narrative_core.product_contract.enums import NarrativeReviewAction
from app.narrative_core.product_contract.evidence import WholeBookEvidenceRefDto


@dataclass(frozen=True, slots=True)
class ConflictRefDto:
    ref_type: str
    ref_id: str
    label: str = ""
    version: int | str | None = None


@dataclass(frozen=True, slots=True)
class ConflictCenterItemDto:
    conflict_id: int | str
    conflict_type: ConflictType
    severity: ConflictSeverity
    status: ConflictStatus
    left_ref: ConflictRefDto
    right_ref: ConflictRefDto
    description: str
    affected_modules: tuple[str, ...]
    affected_chapters: tuple[int, ...]
    evidence_refs: tuple[WholeBookEvidenceRefDto, ...]
    created_at: str
    resolution: dict[str, Any] | None = None
    allowed_actions: tuple[NarrativeReviewAction, ...] = ()
    defer_allowed: bool = True

    def __post_init__(self) -> None:
        if (
            self.severity == ConflictSeverity.BLOCKING
            and self.status == ConflictStatus.OPEN
            and NarrativeReviewAction.RESOLVE_CONFLICT not in self.allowed_actions
            and NarrativeReviewAction.DISMISS_CONFLICT not in self.allowed_actions
        ):
            # open blocking conflicts still require explicit human action set by backend
            pass


BLOCKING_CONFLICTS_AUTO_RESOLVE_FORBIDDEN = True
