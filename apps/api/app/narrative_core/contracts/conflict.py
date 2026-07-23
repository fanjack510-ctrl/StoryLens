"""Analysis Conflict Protocol contracts (Agent F implements)."""

from __future__ import annotations

from typing import Any, Protocol

from app.narrative_core.services.conflict_service import ConflictCreateRequest


class AnalysisConflictSink(Protocol):
    """Minimal public surface for recording open Analysis Conflicts."""

    def record_conflict(self, request: ConflictCreateRequest) -> int:
        """Persist an open conflict; return conflict id. Never auto-adjudicates."""


class AnalysisConflictService(Protocol):
    def create_analysis_conflict(
        self,
        book_id: int,
        *,
        conflict_type: str,
        left_ref_type: str,
        left_ref_id: str,
        right_ref_type: str,
        right_ref_id: str,
        description: str = "",
        severity: str = "warning",
        run_id: int | None = None,
        book_snapshot_id: int | None = None,
    ) -> Any:
        """Record conflict only — no automatic adjudication in Phase 1B-P."""

    def get_analysis_conflict(self, conflict_id: int) -> Any:
        ...

    def list_analysis_conflicts(
        self,
        book_id: int,
        *,
        status: str | None = None,
        conflict_type: str | None = None,
        severity: str | None = None,
    ) -> list[Any]:
        ...

    def resolve_analysis_conflict(
        self,
        conflict_id: int,
        *,
        resolved_by: str,
        resolution_json: str = "{}",
    ) -> Any:
        ...

    def dismiss_analysis_conflict(
        self,
        conflict_id: int,
        *,
        resolved_by: str,
        resolution_json: str = "{}",
    ) -> Any:
        ...
