"""Candidate Persistence Adapter boundary (Phase 2B Integration / CHG-040).

Protocol + recording sink only. No production ORM writes, no auto confirm/lock,
no canonical overwrite. Real Phase 1B persistence wiring is deferred.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from app.narrative_core.services.whole_book_candidate_builder import (
    AssetCandidateCommand,
    ConflictCandidateCommand,
    EvidenceCandidateCommand,
    ModuleCandidateBuildResult,
    RelationCandidateCommand,
    StageArtifactPayload,
)


@runtime_checkable
class CandidatePersistenceAdapter(Protocol):
    """Persistence boundary — Integration may record, never auto-promote."""

    def persist_commands(self, built: ModuleCandidateBuildResult) -> Mapping[str, Any]: ...


@dataclass
class RecordingCandidatePersistenceSink:
    """Test/integration sink: records calls without writing formal database rows."""

    calls: list[ModuleCandidateBuildResult] = field(default_factory=list)
    allow_production_write: bool = False

    def persist_commands(self, built: ModuleCandidateBuildResult) -> Mapping[str, Any]:
        if self.allow_production_write:
            raise RuntimeError("production candidate writes are forbidden in Phase 2B")
        if built.orm_written:
            raise RuntimeError("orm_written must remain false")
        if built.auto_confirm or built.auto_lock or built.canonical_overwrite:
            raise RuntimeError("auto confirm/lock/canonical forbidden")
        # mock=false must not be used by Fake Runtime paths.
        for cmd in (
            *built.asset_commands,
            *built.relation_commands,
            *built.evidence_commands,
            *built.conflict_commands,
        ):
            if getattr(cmd.contract, "mock", True) is False and built.synthetic:
                raise RuntimeError("Fake Runtime must not emit mock=false contracts")
        if built.stage_artifact is not None:
            if built.stage_artifact.contract.mock is False and built.synthetic:
                raise RuntimeError("Fake Runtime stage artifact must stay mock/synthetic")
        self.calls.append(built)
        return {
            "recorded": True,
            "orm_written": False,
            "auto_confirm": False,
            "auto_lock": False,
            "canonical_overwrite": False,
            "synthetic": built.synthetic,
            "rejected": built.rejected,
            "asset_count": len(built.asset_commands),
            "relation_count": len(built.relation_commands),
            "evidence_count": len(built.evidence_commands),
            "conflict_count": len(built.conflict_commands),
            "has_stage_artifact": built.stage_artifact is not None,
        }

    def reset(self) -> None:
        self.calls.clear()


@dataclass(frozen=True, slots=True)
class CandidateCommandBatch:
    asset_commands: tuple[AssetCandidateCommand, ...] = ()
    relation_commands: tuple[RelationCandidateCommand, ...] = ()
    evidence_commands: tuple[EvidenceCandidateCommand, ...] = ()
    conflict_commands: tuple[ConflictCandidateCommand, ...] = ()
    stage_artifact: StageArtifactPayload | None = None


def summarize_commands(built: ModuleCandidateBuildResult) -> dict[str, Any]:
    return {
        "rejected": built.rejected,
        "output_fingerprint": built.output_fingerprint,
        "orm_written": built.orm_written,
        "auto_confirm": built.auto_confirm,
        "auto_lock": built.auto_lock,
        "canonical_overwrite": built.canonical_overwrite,
        "synthetic": built.synthetic,
        "asset_commands": len(built.asset_commands),
        "relation_commands": len(built.relation_commands),
        "evidence_commands": len(built.evidence_commands),
        "conflict_commands": len(built.conflict_commands),
        "stage_artifact": built.stage_artifact is not None,
    }


__all__ = [
    "CandidateCommandBatch",
    "CandidatePersistenceAdapter",
    "RecordingCandidatePersistenceSink",
    "summarize_commands",
]
