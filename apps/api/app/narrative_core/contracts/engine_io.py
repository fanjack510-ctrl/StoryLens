"""WholeBook engine I/O Protocol contracts (Agent G implements writers)."""

from __future__ import annotations

from typing import Any, Protocol

from app.narrative_core.contracts.conflict import AnalysisConflictSink


class SnapshotReader(Protocol):
    """Read-only snapshot access — never loads unbounded full book into DTOs."""

    def get_snapshot_meta(self, book_snapshot_id: int) -> dict[str, Any]:
        ...

    def snapshot_is_completed(self, book_snapshot_id: int) -> bool:
        ...


class NarrativeAssetWriter(Protocol):
    def write_asset_candidate(self, payload: dict[str, Any]) -> int:
        ...


class NarrativeRelationWriter(Protocol):
    def write_relation_candidate(self, payload: dict[str, Any]) -> int:
        ...


class ArtifactWriter(Protocol):
    def write_artifact(self, run_id: int, artifact_type: str, payload: dict[str, Any]) -> int:
        ...


class BudgetGuard(Protocol):
    def check_budget(self, *, stage_key: str, estimated_tokens: int = 0) -> bool:
        ...

    def record_spend(self, *, stage_key: str, tokens: int = 0, cost_usd: float = 0.0) -> None:
        ...


class CancellationToken(Protocol):
    def is_cancelled(self) -> bool:
        ...

    def raise_if_cancelled(self) -> None:
        ...


__all__ = [
    "SnapshotReader",
    "NarrativeAssetWriter",
    "NarrativeRelationWriter",
    "ArtifactWriter",
    "BudgetGuard",
    "CancellationToken",
    "AnalysisConflictSink",
]
