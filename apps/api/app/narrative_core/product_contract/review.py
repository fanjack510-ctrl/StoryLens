"""Narrative review action request contract (Phase 1D-P).

correct creates a new Version; never overwrite. Frontend must not set is_canonical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.narrative_core.product_contract.enums import (
    NarrativeReviewAction,
    ReviewTargetType,
)


@dataclass(frozen=True, slots=True)
class NarrativeReviewAuditContract:
    """Minimal audit contract — implementation may expand later."""

    action: NarrativeReviewAction
    target_type: ReviewTargetType
    target_id: str
    actor: str
    idempotency_key: str
    reason: str | None = None
    created_at: str | None = None


@dataclass(frozen=True, slots=True)
class NarrativeReviewActionRequest:
    action: NarrativeReviewAction
    target_type: ReviewTargetType
    target_id: str
    expected_version: int | str
    actor: str
    correction_payload: dict[str, Any] = field(default_factory=dict)
    evidence_changes: tuple[dict[str, Any], ...] = ()
    resolution_payload: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        if self.expected_version is None or self.expected_version == "":
            raise ValueError("expected_version is required for concurrency control")
        if self.action == NarrativeReviewAction.CORRECT and not self.correction_payload:
            raise ValueError("correct requires correction_payload")
        if self.action == NarrativeReviewAction.RESOLVE_CONFLICT:
            if "schema" not in self.resolution_payload or "version" not in self.resolution_payload:
                raise ValueError("resolve_conflict requires resolution_payload.schema/version")
        if "is_canonical" in self.correction_payload:
            raise ValueError("frontend must not set is_canonical directly")
