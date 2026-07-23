"""AnalysisConflictSink — cycle-free Conflict persistence adapter (Phase 1B Integration).

Asset / Relation services depend on this Protocol only. The Impl forwards to
``AnalysisConflictServiceImpl`` without pulling Relation repositories into Asset.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import AnalysisConflict
from app.narrative_core.contracts.conflict import AnalysisConflictSink
from app.narrative_core.services.conflict_service import (
    AnalysisConflictServiceImpl,
    ConflictCreateRequest,
)


class AnalysisConflictSinkImpl:
    """Default sink → AnalysisConflictServiceImpl."""

    def __init__(
        self,
        session: Session,
        *,
        conflict_service: AnalysisConflictServiceImpl | None = None,
    ) -> None:
        self._conflicts = conflict_service or AnalysisConflictServiceImpl(session)

    def record_conflict(self, request: ConflictCreateRequest) -> int:
        row: AnalysisConflict = self._conflicts.create_from_request(request)
        return int(row.id)


class NullAnalysisConflictSink:
    """Test / dry-run sink that does not persist (returns sentinel 0)."""

    def record_conflict(self, request: ConflictCreateRequest) -> int:  # noqa: ARG002
        return 0


__all__ = [
    "AnalysisConflictSink",
    "AnalysisConflictSinkImpl",
    "NullAnalysisConflictSink",
]
