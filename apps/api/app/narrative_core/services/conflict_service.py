"""Analysis Conflict service + minimal Conflict Request interface (Agent F).

Agent E / Integration may import ``ConflictCreateRequest`` and
``AnalysisConflictServiceImpl`` without pulling Relation services
(avoids circular dependency).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisConflict,
    AnalysisRun,
    BookSnapshot,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    NarrativeEntity,
    NarrativeEntityAlias,
    NarrativeRelation,
    NarrativeRelationEvidence,
    NarrativeRelationVersion,
)
from app.narrative_core.enums import (
    ConflictRefType,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode


RESOLUTION_SCHEMA = "analysis_conflict_resolution"
RESOLUTION_VERSION = "1"

_CANONICAL_REF_TYPES = frozenset(
    {
        ConflictRefType.ENTITY,
        ConflictRefType.ENTITY_ALIAS,
        ConflictRefType.ASSET,
        ConflictRefType.ASSET_VERSION,
        ConflictRefType.RELATION,
        ConflictRefType.RELATION_VERSION,
        ConflictRefType.ASSET_EVIDENCE,
        ConflictRefType.RELATION_EVIDENCE,
        ConflictRefType.SNAPSHOT,
        ConflictRefType.RUN,
    }
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _strip_body_like_text(description: str, *, max_len: int = 500) -> str:
    """Keep conflict description short; never persist full user body text."""
    text = (description or "").strip()
    if len(text) > max_len:
        return text[:max_len]
    return text


def normalize_conflict_ref_type(ref_type: str) -> str:
    """Map legacy ref types; reject ambiguous legacy ``evidence``."""
    value = str(ref_type or "").strip()
    if value == ConflictRefType.ALIAS.value:
        return ConflictRefType.ENTITY_ALIAS.value
    if value == ConflictRefType.EVIDENCE.value:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
            "legacy ref_type 'evidence' is ambiguous; use asset_evidence or relation_evidence",
        )
    try:
        normalized = ConflictRefType(value)
    except ValueError as exc:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
            f"unsupported ref_type={ref_type}",
        ) from exc
    if normalized not in _CANONICAL_REF_TYPES:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
            f"unsupported ref_type={ref_type}",
        )
    return normalized.value


def _parse_ref_id(ref_id: str) -> int:
    text = str(ref_id or "").strip()
    if not text.isdigit():
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
            f"ref_id must be numeric: {ref_id!r}",
        )
    return int(text)


def _resolve_ref_book_id(session: Session, ref_type: str, ref_id: str) -> int:
    """Load ref object and return its book_id; raise if missing."""
    normalized = normalize_conflict_ref_type(ref_type)
    pk = _parse_ref_id(ref_id)

    if normalized == ConflictRefType.ENTITY.value:
        row = session.get(NarrativeEntity, pk)
        if row is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"entity ref not found: {ref_id}",
            )
        return int(row.book_id)

    if normalized == ConflictRefType.ENTITY_ALIAS.value:
        row = session.get(NarrativeEntityAlias, pk)
        if row is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"entity_alias ref not found: {ref_id}",
            )
        entity = session.get(NarrativeEntity, row.entity_id)
        if entity is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"entity_alias {ref_id} has no parent entity",
            )
        return int(entity.book_id)

    if normalized == ConflictRefType.ASSET.value:
        row = session.get(NarrativeAsset, pk)
        if row is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"asset ref not found: {ref_id}",
            )
        return int(row.book_id)

    if normalized == ConflictRefType.ASSET_VERSION.value:
        row = session.get(NarrativeAssetVersion, pk)
        if row is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"asset_version ref not found: {ref_id}",
            )
        asset = session.get(NarrativeAsset, row.asset_id)
        if asset is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"asset_version {ref_id} has no parent asset",
            )
        return int(asset.book_id)

    if normalized == ConflictRefType.RELATION.value:
        row = session.get(NarrativeRelation, pk)
        if row is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"relation ref not found: {ref_id}",
            )
        return int(row.book_id)

    if normalized == ConflictRefType.RELATION_VERSION.value:
        row = session.get(NarrativeRelationVersion, pk)
        if row is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"relation_version ref not found: {ref_id}",
            )
        relation = session.get(NarrativeRelation, row.relation_id)
        if relation is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"relation_version {ref_id} has no parent relation",
            )
        return int(relation.book_id)

    if normalized == ConflictRefType.ASSET_EVIDENCE.value:
        row = session.get(NarrativeAssetEvidence, pk)
        if row is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"asset_evidence ref not found: {ref_id}",
            )
        version = session.get(NarrativeAssetVersion, row.asset_version_id)
        if version is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"asset_evidence {ref_id} has no parent version",
            )
        asset = session.get(NarrativeAsset, version.asset_id)
        if asset is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"asset_evidence {ref_id} has no parent asset",
            )
        return int(asset.book_id)

    if normalized == ConflictRefType.RELATION_EVIDENCE.value:
        row = session.get(NarrativeRelationEvidence, pk)
        if row is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"relation_evidence ref not found: {ref_id}",
            )
        version = session.get(NarrativeRelationVersion, row.relation_version_id)
        if version is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"relation_evidence {ref_id} has no parent version",
            )
        relation = session.get(NarrativeRelation, version.relation_id)
        if relation is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"relation_evidence {ref_id} has no parent relation",
            )
        return int(relation.book_id)

    if normalized == ConflictRefType.SNAPSHOT.value:
        row = session.get(BookSnapshot, pk)
        if row is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"snapshot ref not found: {ref_id}",
            )
        return int(row.book_id)

    if normalized == ConflictRefType.RUN.value:
        row = session.get(AnalysisRun, pk)
        if row is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"run ref not found: {ref_id}",
            )
        book_id = getattr(row, "book_id", None)
        if book_id is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
                f"run {ref_id} has no book_id",
            )
        return int(book_id)

    raise NarrativeCoreError(
        NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
        f"unsupported ref_type={ref_type}",
    )


def _validate_conflict_refs(
    session: Session,
    *,
    book_id: int,
    left_ref_type: str,
    left_ref_id: str,
    right_ref_type: str,
    right_ref_id: str,
) -> tuple[str, str, str, str]:
    left_type = normalize_conflict_ref_type(left_ref_type)
    right_type = normalize_conflict_ref_type(right_ref_type)
    left_id = str(_parse_ref_id(left_ref_id))
    right_id = str(_parse_ref_id(right_ref_id))

    if not left_id or not right_id:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.CONFLICT_REF_INVALID,
            "both left and right refs are required",
        )

    left_book = _resolve_ref_book_id(session, left_type, left_id)
    right_book = _resolve_ref_book_id(session, right_type, right_id)
    expected = int(book_id)
    if left_book != expected or right_book != expected:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.CONFLICT_CROSS_BOOK,
            (
                f"conflict refs must belong to book_id={expected}; "
                f"left={left_book}, right={right_book}"
            ),
        )
    return left_type, left_id, right_type, right_id


def normalize_resolution_json(resolution_json: str | dict[str, Any] | None) -> str:
    """Ensure resolution_json always carries schema + version."""
    if resolution_json is None or resolution_json == "":
        payload: dict[str, Any] = {}
    elif isinstance(resolution_json, dict):
        payload = dict(resolution_json)
    else:
        raw = str(resolution_json).strip() or "{}"
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"resolution_json must be valid JSON: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ValueError("resolution_json must be a JSON object")
        payload = loaded

    payload.setdefault("schema", RESOLUTION_SCHEMA)
    payload.setdefault("version", RESOLUTION_VERSION)
    if payload.get("schema") != RESOLUTION_SCHEMA:
        raise ValueError(f"resolution_json.schema must be {RESOLUTION_SCHEMA}")
    if not payload.get("version"):
        raise ValueError("resolution_json.version is required")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class ConflictCreateRequest:
    """Minimal request surface for Agent E / Integration callers."""

    book_id: int
    conflict_type: str
    left_ref_type: str
    left_ref_id: str
    right_ref_type: str
    right_ref_id: str
    description: str = ""
    severity: str = ConflictSeverity.WARNING.value
    run_id: int | None = None
    book_snapshot_id: int | None = None


class AnalysisConflictServiceImpl:
    """Persists conflicts only — never auto-adjudicates blocking conflicts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_from_request(self, request: ConflictCreateRequest) -> AnalysisConflict:
        return self.create_analysis_conflict(
            request.book_id,
            conflict_type=request.conflict_type,
            left_ref_type=request.left_ref_type,
            left_ref_id=request.left_ref_id,
            right_ref_type=request.right_ref_type,
            right_ref_id=request.right_ref_id,
            description=request.description,
            severity=request.severity,
            run_id=request.run_id,
            book_snapshot_id=request.book_snapshot_id,
        )

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
        severity: str = ConflictSeverity.WARNING.value,
        run_id: int | None = None,
        book_snapshot_id: int | None = None,
    ) -> AnalysisConflict:
        try:
            ConflictType(conflict_type)
        except ValueError as exc:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_NOT_FOUND,
                f"unsupported conflict_type={conflict_type}",
            ) from exc
        try:
            ConflictSeverity(severity)
        except ValueError as exc:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_NOT_FOUND,
                f"unsupported severity={severity}",
            ) from exc

        left_type, left_id, right_type, right_id = _validate_conflict_refs(
            self._session,
            book_id=int(book_id),
            left_ref_type=left_ref_type,
            left_ref_id=left_ref_id,
            right_ref_type=right_ref_type,
            right_ref_id=right_ref_id,
        )

        row = AnalysisConflict(
            book_id=int(book_id),
            run_id=run_id,
            book_snapshot_id=book_snapshot_id,
            conflict_type=str(conflict_type),
            left_ref_type=left_type,
            left_ref_id=left_id,
            right_ref_type=right_type,
            right_ref_id=right_id,
            description=_strip_body_like_text(description),
            severity=str(severity),
            status=ConflictStatus.OPEN.value,
            resolution_json="{}",
            created_at=_utc_now(),
        )
        self._session.add(row)
        self._session.flush()
        return row

    def get_analysis_conflict(self, conflict_id: int) -> AnalysisConflict:
        row = self._session.get(AnalysisConflict, conflict_id)
        if row is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_NOT_FOUND,
                f"conflict not found: {conflict_id}",
            )
        return row

    def list_analysis_conflicts(
        self,
        book_id: int,
        *,
        status: str | None = None,
        conflict_type: str | None = None,
        severity: str | None = None,
    ) -> list[AnalysisConflict]:
        stmt = select(AnalysisConflict).where(AnalysisConflict.book_id == book_id)
        if status is not None:
            stmt = stmt.where(AnalysisConflict.status == status)
        if conflict_type is not None:
            stmt = stmt.where(AnalysisConflict.conflict_type == conflict_type)
        if severity is not None:
            stmt = stmt.where(AnalysisConflict.severity == severity)
        stmt = stmt.order_by(AnalysisConflict.id.asc())
        return list(self._session.scalars(stmt).all())

    def resolve_analysis_conflict(
        self,
        conflict_id: int,
        *,
        resolved_by: str,
        resolution_json: str | dict[str, Any] = "{}",
    ) -> AnalysisConflict:
        return self._close_conflict(
            conflict_id,
            status=ConflictStatus.RESOLVED.value,
            resolved_by=resolved_by,
            resolution_json=resolution_json,
        )

    def dismiss_analysis_conflict(
        self,
        conflict_id: int,
        *,
        resolved_by: str,
        resolution_json: str | dict[str, Any] = "{}",
    ) -> AnalysisConflict:
        return self._close_conflict(
            conflict_id,
            status=ConflictStatus.DISMISSED.value,
            resolved_by=resolved_by,
            resolution_json=resolution_json,
        )

    def _close_conflict(
        self,
        conflict_id: int,
        *,
        status: str,
        resolved_by: str,
        resolution_json: str | dict[str, Any],
    ) -> AnalysisConflict:
        row = self.get_analysis_conflict(conflict_id)
        if row.status != ConflictStatus.OPEN.value:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CONFLICT_ALREADY_CLOSED,
                f"conflict {conflict_id} already {row.status}",
            )
        # Blocking conflicts still require explicit user/system close —
        # this method never auto-resolves; caller must invoke it.
        row.status = status
        row.resolved_by = (resolved_by or "").strip() or "user"
        row.resolved_at = _utc_now()
        row.resolution_json = normalize_resolution_json(resolution_json)
        self._session.flush()
        return row
