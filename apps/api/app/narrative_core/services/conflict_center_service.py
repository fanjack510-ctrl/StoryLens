"""Phase 1D Agent L — Conflict Center projection (read + mock interaction).

Projects AnalysisConflict rows into ConflictCenterItemDto.
Mutations go through Review Action Adapter / Conflict Service — never ORM writes.
Blocking conflicts are never auto-resolved.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AnalysisConflict
from app.narrative_core.enums import ConflictSeverity, ConflictStatus, ConflictType
from app.narrative_core.product_contract.conflict_center import (
    BLOCKING_CONFLICTS_AUTO_RESOLVE_FORBIDDEN,
    ConflictCenterItemDto,
    ConflictRefDto,
)
from app.narrative_core.product_contract.enums import NarrativeReviewAction
from app.narrative_core.product_contract.evidence import WholeBookEvidenceRefDto
from app.narrative_core.services.conflict_service import AnalysisConflictServiceImpl
from app.narrative_core.services.evidence_read_service import EvidenceReadService
from app.narrative_core.services.review_action_adapter import (
    NarrativeReviewActionAdapter,
    ReviewActionResult,
    build_review_action_request,
)


def _parse_resolution(raw: str | None) -> dict[str, Any] | None:
    if not raw or not str(raw).strip() or str(raw).strip() == "{}":
        return None
    try:
        loaded = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return {"raw": str(raw)}
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.isoformat()


def _allowed_actions(status: ConflictStatus, severity: ConflictSeverity) -> tuple[NarrativeReviewAction, ...]:
    if status != ConflictStatus.OPEN:
        return ()
    # Open conflicts (including blocking) require explicit human actions.
    actions = [
        NarrativeReviewAction.RESOLVE_CONFLICT,
        NarrativeReviewAction.DISMISS_CONFLICT,
    ]
    if severity == ConflictSeverity.BLOCKING:
        # Still allow resolve/dismiss — never auto.
        pass
    return tuple(actions)


class ConflictCenterService:
    """Read-only projector + thin mutation facade via Review Action Adapter."""

    def __init__(
        self,
        session: Session,
        *,
        conflict_service: AnalysisConflictServiceImpl | None = None,
        evidence_read: EvidenceReadService | None = None,
        review_adapter: NarrativeReviewActionAdapter | None = None,
    ) -> None:
        self._session = session
        self._conflicts = conflict_service or AnalysisConflictServiceImpl(session)
        self._evidence = evidence_read or EvidenceReadService(session)
        self._review = review_adapter or NarrativeReviewActionAdapter(session)

    @property
    def blocking_auto_resolve_forbidden(self) -> bool:
        return BLOCKING_CONFLICTS_AUTO_RESOLVE_FORBIDDEN

    def list_conflict_center_items(
        self,
        book_id: int,
        *,
        status: str | None = None,
        severity: str | None = None,
        conflict_type: str | None = None,
        include_evidence: bool = True,
    ) -> list[ConflictCenterItemDto]:
        rows = self._conflicts.list_analysis_conflicts(
            int(book_id),
            status=status,
            severity=severity,
            conflict_type=conflict_type,
        )
        return [
            self.project_conflict_item(row, include_evidence=include_evidence)
            for row in rows
        ]

    def get_conflict_center_item(
        self,
        conflict_id: int,
        *,
        include_evidence: bool = True,
    ) -> ConflictCenterItemDto:
        row = self._conflicts.get_analysis_conflict(int(conflict_id))
        return self.project_conflict_item(row, include_evidence=include_evidence)

    def project_conflict_item(
        self,
        row: AnalysisConflict,
        *,
        include_evidence: bool = True,
    ) -> ConflictCenterItemDto:
        severity = ConflictSeverity(str(row.severity))
        status = ConflictStatus(str(row.status))
        conflict_type = ConflictType(str(row.conflict_type))
        evidence_refs: tuple[WholeBookEvidenceRefDto, ...] = ()
        if include_evidence:
            evidence_refs = self._evidence_refs_for_conflict(row)

        affected_modules = self._infer_modules(row)
        affected_chapters = self._infer_chapters(evidence_refs)

        return ConflictCenterItemDto(
            conflict_id=int(row.id),
            conflict_type=conflict_type,
            severity=severity,
            status=status,
            left_ref=ConflictRefDto(
                ref_type=str(row.left_ref_type),
                ref_id=str(row.left_ref_id),
                label=f"{row.left_ref_type}:{row.left_ref_id}",
                version=None,
            ),
            right_ref=ConflictRefDto(
                ref_type=str(row.right_ref_type),
                ref_id=str(row.right_ref_id),
                label=f"{row.right_ref_type}:{row.right_ref_id}",
                version=None,
            ),
            description=str(row.description or ""),
            affected_modules=affected_modules,
            affected_chapters=affected_chapters,
            evidence_refs=evidence_refs,
            created_at=_iso(row.created_at),
            resolution=_parse_resolution(row.resolution_json),
            allowed_actions=_allowed_actions(status, severity),
            defer_allowed=status == ConflictStatus.OPEN,
        )

    def compare_conflict_sides(
        self, conflict_id: int
    ) -> dict[str, Any]:
        """Return left/right refs for comparison UI — no full body text."""
        item = self.get_conflict_center_item(conflict_id, include_evidence=True)
        return {
            "conflict_id": item.conflict_id,
            "left_ref": {
                "ref_type": item.left_ref.ref_type,
                "ref_id": item.left_ref.ref_id,
                "label": item.left_ref.label,
            },
            "right_ref": {
                "ref_type": item.right_ref.ref_type,
                "ref_id": item.right_ref.ref_id,
                "label": item.right_ref.label,
            },
            "evidence_refs": [
                {
                    "evidence_id": e.evidence_id,
                    "evidence_role": e.evidence_role.value
                    if hasattr(e.evidence_role, "value")
                    else e.evidence_role,
                    "paragraph_preview": e.paragraph_preview,
                    "integrity_status": e.integrity_status.value
                    if hasattr(e.integrity_status, "value")
                    else e.integrity_status,
                    "deep_link": e.deep_link,
                }
                for e in item.evidence_refs
            ],
            "severity": item.severity.value,
            "status": item.status.value,
            "blocking_auto_resolve_forbidden": self.blocking_auto_resolve_forbidden,
        }

    def resolve_via_review(
        self,
        conflict_id: int,
        *,
        actor: str,
        resolution_payload: dict[str, Any],
        idempotency_key: str,
        reason: str | None = None,
    ) -> ReviewActionResult:
        assert self.blocking_auto_resolve_forbidden
        request = build_review_action_request(
            action=NarrativeReviewAction.RESOLVE_CONFLICT,
            target_type="conflict",
            target_id=conflict_id,
            expected_version=conflict_id,
            actor=actor,
            idempotency_key=idempotency_key,
            resolution_payload=resolution_payload,
            reason=reason,
        )
        return self._review.submit_review_action(request)

    def dismiss_via_review(
        self,
        conflict_id: int,
        *,
        actor: str,
        idempotency_key: str,
        reason: str | None = None,
        resolution_payload: dict[str, Any] | None = None,
    ) -> ReviewActionResult:
        request = build_review_action_request(
            action=NarrativeReviewAction.DISMISS_CONFLICT,
            target_type="conflict",
            target_id=conflict_id,
            expected_version=conflict_id,
            actor=actor,
            idempotency_key=idempotency_key,
            resolution_payload=resolution_payload
            or {
                "schema": "analysis_conflict_resolution",
                "version": "1",
                "action": "dismiss",
            },
            reason=reason,
        )
        return self._review.submit_review_action(request)

    def defer_conflict(
        self,
        conflict_id: int,
        *,
        actor: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Defer is a soft UI state — does not close the conflict row."""
        item = self.get_conflict_center_item(conflict_id, include_evidence=False)
        if item.status != ConflictStatus.OPEN:
            return {
                "ok": False,
                "conflict_id": conflict_id,
                "message": f"cannot defer non-open conflict ({item.status.value})",
            }
        return {
            "ok": True,
            "conflict_id": conflict_id,
            "deferred": True,
            "actor": actor,
            "reason": reason,
            "status_unchanged": item.status.value,
            "message": "deferred for later — conflict remains open",
        }

    # ------------------------------------------------------------------

    def _evidence_refs_for_conflict(
        self, row: AnalysisConflict
    ) -> tuple[WholeBookEvidenceRefDto, ...]:
        """Best-effort: if refs point at asset/relation versions, list their evidence."""
        refs: list[WholeBookEvidenceRefDto] = []
        for ref_type, ref_id in (
            (str(row.left_ref_type), str(row.left_ref_id)),
            (str(row.right_ref_type), str(row.right_ref_id)),
        ):
            try:
                if ref_type in {"asset_version", "narrative_asset_version"}:
                    refs.extend(
                        self._evidence.list_asset_version_evidence_refs(int(ref_id))
                    )
                elif ref_type in {"relation_version", "narrative_relation_version"}:
                    refs.extend(
                        self._evidence.list_relation_version_evidence_refs(int(ref_id))
                    )
            except (LookupError, ValueError, TypeError):
                continue
        # Deduplicate by evidence_id+type
        seen: set[tuple[str, str]] = set()
        unique: list[WholeBookEvidenceRefDto] = []
        for e in refs:
            key = (str(e.evidence_type), str(e.evidence_id))
            if key in seen:
                continue
            seen.add(key)
            unique.append(e)
        return tuple(unique)

    @staticmethod
    def _infer_modules(row: AnalysisConflict) -> tuple[str, ...]:
        ctype = str(row.conflict_type)
        if "relation" in ctype:
            return ("relationships",)
        if "entity" in ctype:
            return ("characters",)
        if "evidence" in ctype or "snapshot" in ctype:
            return ("evidence_conflicts",)
        return ("diagnostics", "evidence_conflicts")

    @staticmethod
    def _infer_chapters(
        evidence_refs: tuple[WholeBookEvidenceRefDto, ...]
    ) -> tuple[int, ...]:
        chapters: list[int] = []
        for e in evidence_refs:
            if e.source_chapter_id is not None:
                chapters.append(int(e.source_chapter_id))
        return tuple(sorted(set(chapters)))
