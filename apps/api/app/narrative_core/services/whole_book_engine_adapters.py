"""Minimal WholeBook engine I/O adapters (Phase 1C Agent G).

Adapters delegate to Phase 1A/1B services. They never confirm, correct, lock,
or write ORM rows bypassing services. No second Asset/Relation writer.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AnalysisArtifact, AnalysisRun, Book, BookSnapshot
from app.narrative_core.enums import (
    AssetType,
    ConflictType,
    OriginType,
    RelationType,
    ReviewStatus,
    SnapshotStatus,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.asset_service import NarrativeAssetService
from app.narrative_core.services.conflict_service import ConflictCreateRequest
from app.narrative_core.services.conflict_sink import AnalysisConflictSinkImpl
from app.narrative_core.services.relation_service import NarrativeRelationServiceImpl

MOCK_SOURCE_MARKER = "mock"
MOCK_SYNTHETIC_MARKER = "synthetic"
MOCK_NON_PRODUCTION_MARKER = "non-production"


def mock_source_fingerprint(*parts: str) -> str:
    """Build a source fingerprint that cannot be mistaken for production analysis."""

    joined = "|".join(str(p) for p in parts if p)
    return f"{MOCK_SOURCE_MARKER}:{MOCK_SYNTHETIC_MARKER}:{MOCK_NON_PRODUCTION_MARKER}:{joined}"


class SnapshotReaderAdapter:
    """Read-only snapshot metadata — never loads unbounded book body into DTOs."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_snapshot_meta(self, book_snapshot_id: int) -> dict[str, Any]:
        snapshot = self._session.get(BookSnapshot, int(book_snapshot_id))
        if snapshot is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_NOT_FOUND,
                f"snapshot not found: {book_snapshot_id}",
            )
        return {
            "book_snapshot_id": int(snapshot.id),
            "book_id": int(snapshot.book_id),
            "snapshot_status": str(snapshot.snapshot_status),
            "chapter_count": int(snapshot.chapter_count or 0),
            "paragraph_count": int(snapshot.paragraph_count or 0),
            "character_count": int(snapshot.character_count or 0),
            "content_hash": str(snapshot.content_hash or ""),
            "source_fingerprint": str(snapshot.source_fingerprint or ""),
        }

    def snapshot_is_completed(self, book_snapshot_id: int) -> bool:
        meta = self.get_snapshot_meta(book_snapshot_id)
        return meta["snapshot_status"] == SnapshotStatus.COMPLETED.value

    def require_completed_for_book(self, book_snapshot_id: int, book_id: int) -> dict[str, Any]:
        meta = self.get_snapshot_meta(book_snapshot_id)
        if int(meta["book_id"]) != int(book_id):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH,
                f"snapshot {book_snapshot_id} belongs to book {meta['book_id']}, not {book_id}",
            )
        if meta["snapshot_status"] != SnapshotStatus.COMPLETED.value:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_SNAPSHOT_REQUIRED,
                f"snapshot {book_snapshot_id} is not COMPLETED",
            )
        return meta


class NarrativeAssetWriterAdapter:
    """Candidate-only writer via Phase 1B NarrativeAssetService."""

    def __init__(
        self,
        session: Session,
        *,
        asset_service: NarrativeAssetService | None = None,
    ) -> None:
        self._session = session
        self._assets = asset_service or NarrativeAssetService(session)
        self.last_asset_id: int | None = None
        self.last_version_id: int | None = None
        self.created_asset_ids: list[int] = []
        self.created_version_ids: list[int] = []

    def write_asset_candidate(self, payload: dict[str, Any]) -> int:
        book_id = int(payload["book_id"])
        asset_type = str(payload.get("asset_type") or AssetType.EVENT.value)
        title = str(payload.get("title") or "mock synthetic asset")
        summary = str(payload.get("summary") or "mock/synthetic/non-production")
        run_id = payload.get("run_id")
        book_snapshot_id = payload.get("book_snapshot_id")
        fingerprint = str(
            payload.get("source_fingerprint")
            or mock_source_fingerprint("asset", asset_type, title)
        )
        if MOCK_SOURCE_MARKER not in fingerprint:
            fingerprint = mock_source_fingerprint(fingerprint)

        result = self._assets.create_candidate_asset(
            book_id,
            asset_type=asset_type,
            title=title,
            summary=summary,
            run_id=int(run_id) if run_id is not None else None,
            book_snapshot_id=int(book_snapshot_id) if book_snapshot_id is not None else None,
            identity_fingerprint=str(
                payload.get("identity_fingerprint")
                or mock_source_fingerprint("identity", asset_type, title)
            ),
            independent=bool(payload.get("independent", True)),
            origin_type=str(payload.get("origin_type") or OriginType.SYSTEM.value),
            source_fingerprint=fingerprint,
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            importance=float(payload.get("importance", 0.0) or 0.0),
            attributes_json=payload.get(
                "attributes_json",
                json.dumps(
                    {
                        "mock": True,
                        "synthetic": True,
                        "non_production": True,
                    }
                ),
            ),
        )
        version = result.version
        if bool(getattr(version, "is_canonical", False)):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CANDIDATE_CANNOT_BE_CANONICAL,
                "adapter must never produce canonical asset versions",
            )
        if str(getattr(version, "review_status", "")) != ReviewStatus.CANDIDATE.value:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                "adapter must only create candidate asset versions",
            )
        self.last_asset_id = int(result.asset.id)
        self.last_version_id = int(version.id)
        self.created_asset_ids.append(self.last_asset_id)
        self.created_version_ids.append(self.last_version_id)
        return int(version.id)


class NarrativeRelationWriterAdapter:
    """Candidate-only writer via Phase 1B NarrativeRelationServiceImpl."""

    def __init__(
        self,
        session: Session,
        *,
        relation_service: NarrativeRelationServiceImpl | None = None,
    ) -> None:
        self._session = session
        self._relations = relation_service or NarrativeRelationServiceImpl(session)

    def write_relation_candidate(self, payload: dict[str, Any]) -> int:
        book_id = int(payload["book_id"])
        source_asset_id = int(payload["source_asset_id"])
        target_asset_id = int(payload["target_asset_id"])
        relation_type = str(payload.get("relation_type") or RelationType.BELONGS_TO.value)
        summary = str(payload.get("summary") or "mock/synthetic/non-production relation")
        run_id = payload.get("run_id")
        book_snapshot_id = payload.get("book_snapshot_id")
        fingerprint = str(
            payload.get("source_fingerprint")
            or mock_source_fingerprint("relation", relation_type)
        )
        if MOCK_SOURCE_MARKER not in fingerprint:
            fingerprint = mock_source_fingerprint(fingerprint)

        relation = self._relations.create_candidate_relation(
            book_id,
            source_asset_id=source_asset_id,
            target_asset_id=target_asset_id,
            relation_type=relation_type,
            summary=summary,
            run_id=int(run_id) if run_id is not None else None,
            book_snapshot_id=int(book_snapshot_id) if book_snapshot_id is not None else None,
            identity_fingerprint=str(
                payload.get("identity_fingerprint")
                or mock_source_fingerprint("rel-id", source_asset_id, target_asset_id)
            ),
            origin_type=str(payload.get("origin_type") or OriginType.SYSTEM.value),
            source_fingerprint=fingerprint,
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            importance=float(payload.get("importance", 0.0) or 0.0),
            attributes_json=str(
                payload.get(
                    "attributes_json",
                    json.dumps(
                        {
                            "mock": True,
                            "synthetic": True,
                            "non_production": True,
                        }
                    ),
                )
            ),
        )
        versions = self._relations.get_relation_versions(relation.id)
        if not versions:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.RELATION_VERSION_NOT_FOUND,
                f"no version created for relation {relation.id}",
            )
        version = versions[-1]
        if bool(getattr(version, "is_canonical", False)):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CANDIDATE_CANNOT_BE_CANONICAL,
                "adapter must never produce canonical relation versions",
            )
        if str(getattr(version, "review_status", "")) != ReviewStatus.CANDIDATE.value:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                "adapter must only create candidate relation versions",
            )
        return int(version.id)


class ArtifactWriterAdapter:
    """Minimal artifact writer using legacy analysis_artifacts.

    Integration Issue II-ENGINE-001: WholeBook stage artifact contract lacks
    dedicated typed columns / stage_key binding; this adapter reuses the
    existing AnalysisArtifact table without schema expansion.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self.calls: list[dict[str, Any]] = []

    def write_artifact(self, run_id: int, artifact_type: str, payload: dict[str, Any]) -> int:
        marked = dict(payload)
        marked.setdefault("mock", True)
        marked.setdefault("synthetic", True)
        marked.setdefault("non_production", True)
        row = AnalysisArtifact(
            run_id=int(run_id),
            artifact_type=str(artifact_type),
            subject_type=str(marked.get("subject_type") or "whole_book_mock"),
            subject_id=str(marked.get("subject_id") or str(run_id)),
            schema_version=str(marked.get("schema_version") or "whole_book_mock_v0"),
            prompt_version=str(marked.get("prompt_version") or "none-mock"),
            payload_json=json.dumps(marked, ensure_ascii=False),
            confidence=float(marked.get("confidence", 0.0) or 0.0),
            validation_status="mock_synthetic",
        )
        self._session.add(row)
        self._session.flush()
        self.calls.append(
            {
                "run_id": int(run_id),
                "artifact_type": str(artifact_type),
                "artifact_id": int(row.id),
            }
        )
        return int(row.id)


class AnalysisConflictSinkAdapter:
    """Thin wrapper over Phase 1B AnalysisConflictSinkImpl."""

    def __init__(
        self,
        session: Session,
        *,
        sink: AnalysisConflictSinkImpl | None = None,
    ) -> None:
        self._sink = sink or AnalysisConflictSinkImpl(session)

    def record_conflict(self, request: ConflictCreateRequest) -> int:
        return int(self._sink.record_conflict(request))

    def record_candidate_contradiction(
        self,
        *,
        book_id: int,
        left_ref_type: str,
        left_ref_id: str,
        right_ref_type: str,
        right_ref_id: str,
        description: str = "mock/synthetic conflict",
        run_id: int | None = None,
        book_snapshot_id: int | None = None,
    ) -> int:
        return self.record_conflict(
            ConflictCreateRequest(
                book_id=book_id,
                conflict_type=ConflictType.CANDIDATE_CONTRADICTION.value,
                left_ref_type=left_ref_type,
                left_ref_id=str(left_ref_id),
                right_ref_type=right_ref_type,
                right_ref_id=str(right_ref_id),
                description=description,
                run_id=run_id,
                book_snapshot_id=book_snapshot_id,
            )
        )


class BudgetGuardAdapter:
    """Simple token/cost budget guard for mock orchestration tests."""

    def __init__(
        self,
        *,
        max_tokens: int | None = None,
        max_cost: float | None = None,
        allow: bool = True,
    ) -> None:
        self.max_tokens = max_tokens
        self.max_cost = max_cost
        self.allow = allow
        self.spent_tokens = 0
        self.spent_cost = 0.0
        self.checks: list[dict[str, Any]] = []

    def check_budget(self, *, stage_key: str, estimated_tokens: int = 0) -> bool:
        ok = bool(self.allow)
        if ok and self.max_tokens is not None:
            ok = (self.spent_tokens + int(estimated_tokens)) <= int(self.max_tokens)
        if ok and self.max_cost is not None:
            ok = self.spent_cost <= float(self.max_cost)
        self.checks.append(
            {
                "stage_key": stage_key,
                "estimated_tokens": int(estimated_tokens),
                "allowed": ok,
            }
        )
        return ok

    def record_spend(self, *, stage_key: str, tokens: int = 0, cost_usd: float = 0.0) -> None:
        _ = stage_key
        self.spent_tokens += int(tokens)
        self.spent_cost += float(cost_usd)

    def deny(self) -> None:
        self.allow = False


class CancellationTokenImpl:
    """Mutable cancellation token checked before/after stage execution."""

    def __init__(self, *, cancelled: bool = False) -> None:
        self._cancelled = bool(cancelled)

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_STAGE_CANCELLED,
                "stage cancelled by cancellation token",
            )


class RunBindingResolver:
    """Resolve Run / Book / Snapshot consistency for request validation."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def require_book(self, book_id: int) -> Book:
        book = self._session.get(Book, int(book_id))
        if book is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                f"book_id not found: {book_id}",
            )
        return book

    def require_run(self, run_id: int) -> AnalysisRun:
        run = self._session.get(AnalysisRun, int(run_id))
        if run is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                f"run_id not found: {run_id}",
            )
        return run

    def validate_run_snapshot_consistency(
        self,
        *,
        run_id: int,
        book_id: int,
        book_snapshot_id: int,
    ) -> AnalysisRun:
        run = self.require_run(run_id)
        if run.book_id is None or int(run.book_id) != int(book_id):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                f"run {run_id} book_id {run.book_id} != request book_id {book_id}",
            )
        if run.book_snapshot_id is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_RUN_SNAPSHOT_MISMATCH,
                f"run {run_id} has no bound snapshot",
            )
        if int(run.book_snapshot_id) != int(book_snapshot_id):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_RUN_SNAPSHOT_MISMATCH,
                (
                    f"run snapshot {run.book_snapshot_id} != request snapshot "
                    f"{book_snapshot_id}"
                ),
            )
        return run


__all__ = [
    "MOCK_SOURCE_MARKER",
    "MOCK_SYNTHETIC_MARKER",
    "MOCK_NON_PRODUCTION_MARKER",
    "mock_source_fingerprint",
    "SnapshotReaderAdapter",
    "NarrativeAssetWriterAdapter",
    "NarrativeRelationWriterAdapter",
    "ArtifactWriterAdapter",
    "AnalysisConflictSinkAdapter",
    "BudgetGuardAdapter",
    "CancellationTokenImpl",
    "RunBindingResolver",
]
