"""Read-only NarrativeProjectionSource Protocol (Phase 1D Integration).

Decouples Structure Map / Review consumers from WholeBookResultIndexService
implementation details. Result Projection implements this Protocol.
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from app.narrative_core.product_contract.result_envelope import ReviewSummaryDto
from app.narrative_core.services.whole_book_result_projection import (
    ConflictSummaryDto,
    EvidenceIndexEntry,
    ProjectionAssetRow,
    ProjectionRelationRow,
)


@runtime_checkable
class NarrativeProjectionSource(Protocol):
    """Read-only projection inputs for Structure Map and related consumers."""

    def get_canonical_assets_for_projection(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None = None,
        limit: int | None = None,
    ) -> tuple[ProjectionAssetRow, ...]: ...

    def get_candidate_assets_for_projection(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None = None,
        limit: int | None = None,
    ) -> tuple[ProjectionAssetRow, ...]: ...

    def get_canonical_relations_for_projection(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None = None,
        limit: int | None = None,
    ) -> tuple[ProjectionRelationRow, ...]: ...

    def get_candidate_relations_for_projection(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None = None,
        limit: int | None = None,
    ) -> tuple[ProjectionRelationRow, ...]: ...

    def get_evidence_index(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        asset_version_ids: Sequence[int] = (),
        relation_version_ids: Sequence[int] = (),
        limit: int = 500,
    ) -> tuple[EvidenceIndexEntry, ...]: ...

    def get_review_summary(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None = None,
    ) -> ReviewSummaryDto: ...

    def get_conflict_summary(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        run_id: int | None = None,
    ) -> ConflictSummaryDto: ...


__all__ = ["NarrativeProjectionSource"]
