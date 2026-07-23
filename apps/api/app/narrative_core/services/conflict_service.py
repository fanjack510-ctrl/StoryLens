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

from app.db.models import AnalysisConflict
from app.narrative_core.enums import ConflictSeverity, ConflictStatus, ConflictType
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode


RESOLUTION_SCHEMA = "analysis_conflict_resolution"
RESOLUTION_VERSION = "1"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _strip_body_like_text(description: str, *, max_len: int = 500) -> str:
    """Keep conflict description short; never persist full user body text."""
    text = (description or "").strip()
    if len(text) > max_len:
        return text[:max_len]
    return text


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

        row = AnalysisConflict(
            book_id=int(book_id),
            run_id=run_id,
            book_snapshot_id=book_snapshot_id,
            conflict_type=str(conflict_type),
            left_ref_type=str(left_ref_type),
            left_ref_id=str(left_ref_id),
            right_ref_type=str(right_ref_type),
            right_ref_id=str(right_ref_id),
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
