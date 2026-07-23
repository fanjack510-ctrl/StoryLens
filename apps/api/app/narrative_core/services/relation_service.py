"""Narrative Relation / Version / Evidence service (Agent F).

Stable Relation identity + versioned interpretations.
Evidence validation reuses Phase 1A SnapshotValidationGateway — no second text reader.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import (
    BookSnapshotChapter,
    BookSnapshotParagraph,
    NarrativeAsset,
    NarrativeRelation,
    NarrativeRelationEvidence,
    NarrativeRelationVersion,
)
from app.narrative_core.asset_key import build_relation_key
from app.narrative_core.contracts.snapshot import SnapshotValidationGateway
from app.narrative_core.enums import (
    EvidenceRole,
    OriginType,
    RelationLifecycleStatus,
    RelationType,
    ReviewStatus,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.conflict_service import (
    AnalysisConflictServiceImpl,
    ConflictCreateRequest,
)
from app.narrative_core.services.relation_repository import NarrativeRelationRepository
from app.narrative_core.services.snapshot_service import SnapshotValidationGatewayImpl


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NarrativeRelationServiceImpl:
    """Implements NarrativeRelationService Protocol + list/get helpers."""

    def __init__(
        self,
        session: Session,
        *,
        snapshot_gateway: SnapshotValidationGateway | None = None,
        conflict_service: AnalysisConflictServiceImpl | None = None,
    ) -> None:
        self._session = session
        self._repo = NarrativeRelationRepository(session)
        self._snapshot = snapshot_gateway or SnapshotValidationGatewayImpl(session)
        self._conflicts = conflict_service or AnalysisConflictServiceImpl(session)

    # ------------------------------------------------------------------
    # Stable Relation + Versions
    # ------------------------------------------------------------------

    def create_candidate_relation(
        self,
        book_id: int,
        *,
        source_asset_id: int,
        target_asset_id: int,
        relation_type: str,
        summary: str = "",
        run_id: int | None = None,
        book_snapshot_id: int | None = None,
        disambiguator: str = "",
        **fields: Any,
    ) -> NarrativeRelation:
        self._validate_relation_type(relation_type)
        source, target = self._require_endpoint_assets(
            book_id, source_asset_id, target_asset_id
        )
        if source.id == target.id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_NOT_FOUND,
                "source_asset_id and target_asset_id must be distinct",
            )

        relation_key = self._allocate_relation_key(
            book_id=book_id,
            source_asset_id=source.id,
            target_asset_id=target.id,
            relation_type=relation_type,
            disambiguator=disambiguator,
        )
        relation = self._repo.create_relation(
            book_id=book_id,
            source_asset_id=source.id,
            target_asset_id=target.id,
            relation_key=relation_key,
        )
        self._repo.add_version(
            relation.id,
            relation_type=relation_type,
            summary=summary or "",
            attributes_json=str(fields.get("attributes_json", "{}")),
            confidence=float(fields.get("confidence", 0.0)),
            importance=float(fields.get("importance", 0.0)),
            source_fingerprint=str(fields.get("source_fingerprint", "")),
            origin_type=str(fields.get("origin_type", OriginType.MODEL.value)),
            review_status=ReviewStatus.CANDIDATE.value,
            is_canonical=False,
            run_id=run_id,
            book_snapshot_id=book_snapshot_id,
        )
        return relation

    def add_relation_version(
        self,
        relation_id: int,
        *,
        relation_type: str,
        review_status: str = ReviewStatus.CANDIDATE.value,
        origin_type: str = OriginType.MODEL.value,
        run_id: int | None = None,
        book_snapshot_id: int | None = None,
        **fields: Any,
    ) -> NarrativeRelationVersion:
        relation = self.get_relation(relation_id)
        self._validate_relation_type(relation_type)
        status = ReviewStatus(review_status)
        # Locked relation still allows candidate versions (model or user).
        if (
            relation.is_locked
            and status != ReviewStatus.CANDIDATE
            and OriginType(origin_type) == OriginType.MODEL
        ):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.RELATION_LOCKED,
                f"locked relation {relation_id} blocks non-candidate model versions",
            )
        version = self._repo.add_version(
            relation.id,
            relation_type=relation_type,
            summary=str(fields.get("summary", "")),
            attributes_json=str(fields.get("attributes_json", "{}")),
            confidence=float(fields.get("confidence", 0.0)),
            importance=float(fields.get("importance", 0.0)),
            source_fingerprint=str(fields.get("source_fingerprint", "")),
            origin_type=str(origin_type),
            review_status=status.value,
            is_canonical=False,
            run_id=run_id,
            book_snapshot_id=book_snapshot_id,
        )
        self._repo.touch_relation(relation)
        return version

    def get_relation(self, relation_id: int) -> NarrativeRelation:
        relation = self._repo.get_relation(relation_id)
        if relation is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.RELATION_NOT_FOUND,
                f"relation not found: {relation_id}",
            )
        return relation

    def get_relation_versions(self, relation_id: int) -> list[NarrativeRelationVersion]:
        self.get_relation(relation_id)
        return self._repo.list_versions(relation_id)

    def get_canonical_relation_version(
        self, relation_id: int
    ) -> NarrativeRelationVersion | None:
        self.get_relation(relation_id)
        return self._repo.get_canonical_version(relation_id)

    def list_relations(
        self,
        book_id: int,
        *,
        lifecycle_status: str | None = None,
        source_asset_id: int | None = None,
        target_asset_id: int | None = None,
    ) -> list[NarrativeRelation]:
        return self._repo.list_relations(
            book_id,
            lifecycle_status=lifecycle_status,
            source_asset_id=source_asset_id,
            target_asset_id=target_asset_id,
        )

    def confirm_relation_version(
        self,
        relation_version_id: int,
        *,
        make_canonical: bool = True,
        actor: str = "user",
    ) -> NarrativeRelationVersion:
        version = self._require_version(relation_version_id)
        relation = self.get_relation(version.relation_id)
        status = ReviewStatus(version.review_status)
        if status == ReviewStatus.REJECTED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.REJECTED_CANNOT_BE_CANONICAL,
                f"rejected version {version.id} cannot be confirmed as canonical",
            )
        if status == ReviewStatus.CANDIDATE:
            version.review_status = ReviewStatus.CONFIRMED.value
        # CORRECTED / CONFIRMED keep their review_status.
        self._session.flush()
        if make_canonical:
            self._switch_canonical(
                relation,
                version,
                actor=actor,
            )
        else:
            self._repo.touch_relation(relation)
        return version

    def correct_relation(
        self,
        relation_id: int,
        *,
        based_on_version_id: int,
        summary: str = "",
        make_canonical: bool = True,
        actor: str = "user",
        **fields: Any,
    ) -> NarrativeRelationVersion:
        relation = self.get_relation(relation_id)
        base = self._require_version(based_on_version_id)
        if base.relation_id != relation.id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.RELATION_VERSION_NOT_FOUND,
                f"version {based_on_version_id} does not belong to relation {relation_id}",
            )
        relation_type = str(fields.get("relation_type", base.relation_type))
        self._validate_relation_type(relation_type)
        version = self._repo.add_version(
            relation.id,
            relation_type=relation_type,
            summary=summary if summary != "" else base.summary,
            attributes_json=str(fields.get("attributes_json", base.attributes_json)),
            confidence=float(fields.get("confidence", base.confidence)),
            importance=float(fields.get("importance", base.importance)),
            source_fingerprint=str(
                fields.get("source_fingerprint", base.source_fingerprint)
            ),
            origin_type=OriginType.USER.value,
            review_status=ReviewStatus.CORRECTED.value,
            is_canonical=False,
            run_id=fields.get("run_id"),
            book_snapshot_id=fields.get("book_snapshot_id", base.book_snapshot_id),
        )
        if make_canonical:
            self._switch_canonical(relation, version, actor=actor)
        else:
            self._repo.touch_relation(relation)
        return version

    def reject_relation_version(
        self, relation_version_id: int
    ) -> NarrativeRelationVersion:
        version = self._require_version(relation_version_id)
        relation = self.get_relation(version.relation_id)
        version.review_status = ReviewStatus.REJECTED.value
        if version.is_canonical:
            version.is_canonical = False
        self._repo.touch_relation(relation)
        self._session.flush()
        return version

    def lock_relation(self, relation_id: int) -> NarrativeRelation:
        relation = self.get_relation(relation_id)
        relation.is_locked = True
        relation.locked_at = _utc_now()
        self._repo.touch_relation(relation)
        return relation

    def unlock_relation(self, relation_id: int) -> NarrativeRelation:
        relation = self.get_relation(relation_id)
        relation.is_locked = False
        relation.locked_at = None
        self._repo.touch_relation(relation)
        return relation

    def mark_relation_stale(self, relation_id: int, *, reason: str) -> NarrativeRelation:
        relation = self.get_relation(relation_id)
        relation.lifecycle_status = RelationLifecycleStatus.STALE.value
        relation.stale_at = _utc_now()
        relation.stale_reason = (reason or "").strip() or "stale"
        self._repo.touch_relation(relation)
        return relation

    def clear_relation_stale(self, relation_id: int) -> NarrativeRelation:
        relation = self.get_relation(relation_id)
        if relation.lifecycle_status == RelationLifecycleStatus.STALE.value:
            relation.lifecycle_status = RelationLifecycleStatus.ACTIVE.value
        relation.stale_at = None
        relation.stale_reason = None
        self._repo.touch_relation(relation)
        return relation

    def supersede_relation(
        self, relation_id: int, *, superseded_by_relation_id: int
    ) -> NarrativeRelation:
        relation = self.get_relation(relation_id)
        replacement = self.get_relation(superseded_by_relation_id)
        if replacement.book_id != relation.book_id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.RELATION_NOT_FOUND,
                "superseding relation must belong to the same book",
            )
        if replacement.id == relation.id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.RELATION_NOT_FOUND,
                "relation cannot supersede itself",
            )
        relation.lifecycle_status = RelationLifecycleStatus.SUPERSEDED.value
        relation.superseded_by_relation_id = replacement.id
        self._repo.touch_relation(relation)
        return relation

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------

    def attach_relation_evidence(
        self, relation_version_id: int, **evidence_fields: Any
    ) -> NarrativeRelationEvidence:
        version = self._require_version(relation_version_id)
        relation = self.get_relation(version.relation_id)
        binding = self._validate_evidence_fields(
            book_id=relation.book_id, **evidence_fields
        )
        evidence = self._repo.add_evidence(
            version.id,
            book_snapshot_id=binding["book_snapshot_id"],
            snapshot_chapter_id=binding["snapshot_chapter_id"],
            snapshot_paragraph_id=binding["snapshot_paragraph_id"],
            paragraph_content_hash=binding["paragraph_content_hash"],
            start_offset=binding["start_offset"],
            end_offset=binding["end_offset"],
            evidence_role=binding["evidence_role"],
            evidence_label=binding["evidence_label"],
            source_scene_id=binding["source_scene_id"],
        )
        self._repo.touch_relation(relation)
        return evidence

    def validate_relation_evidence(self, evidence_id: int) -> bool:
        evidence = self._repo.get_evidence(evidence_id)
        if evidence is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_PARAGRAPH_REQUIRED,
                f"relation evidence not found: {evidence_id}",
            )
        version = self._require_version(evidence.relation_version_id)
        relation = self.get_relation(version.relation_id)
        self._validate_evidence_fields(
            book_id=relation.book_id,
            book_snapshot_id=evidence.book_snapshot_id,
            snapshot_chapter_id=evidence.snapshot_chapter_id,
            snapshot_paragraph_id=evidence.snapshot_paragraph_id,
            paragraph_content_hash=evidence.paragraph_content_hash,
            start_offset=evidence.start_offset,
            end_offset=evidence.end_offset,
            evidence_role=evidence.evidence_role,
            evidence_label=evidence.evidence_label,
            source_scene_id=evidence.source_scene_id,
        )
        return True

    def list_relation_version_evidence(
        self, relation_version_id: int
    ) -> list[NarrativeRelationEvidence]:
        self._require_version(relation_version_id)
        return self._repo.list_version_evidence(relation_version_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _allocate_relation_key(
        self,
        *,
        book_id: int,
        source_asset_id: int,
        target_asset_id: int,
        relation_type: str,
        disambiguator: str,
    ) -> str:
        """Stable SHA-256 key; collide → prefer new candidate (disambiguator)."""
        key = build_relation_key(
            book_id=book_id,
            source_asset_id=source_asset_id,
            target_asset_id=target_asset_id,
            relation_type=relation_type,
            disambiguator=disambiguator,
        )
        existing = self._repo.find_by_relation_key(book_id, key)
        if existing is None:
            return key
        # Prefer a new candidate Relation when identity is already taken.
        return build_relation_key(
            book_id=book_id,
            source_asset_id=source_asset_id,
            target_asset_id=target_asset_id,
            relation_type=relation_type,
            disambiguator=f"{disambiguator}:{uuid.uuid4().hex[:12]}",
        )

    def _require_endpoint_assets(
        self, book_id: int, source_asset_id: int, target_asset_id: int
    ) -> tuple[NarrativeAsset, NarrativeAsset]:
        source = self._session.get(NarrativeAsset, source_asset_id)
        target = self._session.get(NarrativeAsset, target_asset_id)
        if source is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_NOT_FOUND,
                f"source asset not found: {source_asset_id}",
            )
        if target is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_NOT_FOUND,
                f"target asset not found: {target_asset_id}",
            )
        if source.book_id != target.book_id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_NOT_FOUND,
                "source/target assets must belong to the same book",
            )
        if source.book_id != book_id or target.book_id != book_id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_NOT_FOUND,
                "relation book_id must match both endpoint assets",
            )
        return source, target

    def _require_version(self, relation_version_id: int) -> NarrativeRelationVersion:
        version = self._repo.get_version(relation_version_id)
        if version is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.RELATION_VERSION_NOT_FOUND,
                f"relation version not found: {relation_version_id}",
            )
        return version

    def _validate_relation_type(self, relation_type: str) -> None:
        try:
            RelationType(relation_type)
        except ValueError as exc:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.RELATION_NOT_FOUND,
                f"unsupported relation_type={relation_type}",
            ) from exc

    def _has_support_evidence(self, version: NarrativeRelationVersion) -> bool:
        for evidence in self._repo.list_version_evidence(version.id):
            if evidence.evidence_role == EvidenceRole.SUPPORT.value:
                return True
        return False

    def _switch_canonical(
        self,
        relation: NarrativeRelation,
        version: NarrativeRelationVersion,
        *,
        actor: str,
    ) -> None:
        """Transactional canonical switch with lock / review / evidence gates."""
        status = ReviewStatus(version.review_status)
        if status == ReviewStatus.REJECTED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.REJECTED_CANNOT_BE_CANONICAL,
                f"rejected version {version.id} cannot be canonical",
            )
        if status == ReviewStatus.CANDIDATE:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CANDIDATE_CANNOT_BE_CANONICAL,
                f"candidate version {version.id} cannot be canonical",
            )
        if status not in (ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CANONICAL_VERSION_REQUIRED,
                f"review_status={status.value} cannot be canonical",
            )
        if relation.is_locked and actor == "model":
            # Record conflict for Integration / UI; do not switch.
            self._conflicts.create_from_request(
                ConflictCreateRequest(
                    book_id=relation.book_id,
                    conflict_type="relation_conflict",
                    left_ref_type="relation",
                    left_ref_id=str(relation.id),
                    right_ref_type="relation_version",
                    right_ref_id=str(version.id),
                    description=(
                        f"locked relation blocks model canonical switch "
                        f"for version {version.id}"
                    ),
                    severity="blocking",
                    run_id=version.run_id,
                    book_snapshot_id=version.book_snapshot_id,
                )
            )
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.RELATION_LOCKED,
                f"locked relation {relation.id} blocks model canonical switch",
            )
        if not self._has_support_evidence(version):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CANONICAL_VERSION_REQUIRED,
                (
                    f"canonical relation version {version.id} requires at least "
                    "one support evidence (context alone is insufficient)"
                ),
            )

        self._repo.clear_canonical_flags(relation.id)
        version.is_canonical = True
        self._repo.touch_relation(relation)
        self._session.flush()

    def _validate_evidence_fields(self, *, book_id: int, **fields: Any) -> dict[str, Any]:
        snapshot_id = fields.get("book_snapshot_id")
        if snapshot_id is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_SNAPSHOT_REQUIRED,
                "book_snapshot_id is required",
            )
        paragraph_id = fields.get("snapshot_paragraph_id")
        if paragraph_id is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_PARAGRAPH_REQUIRED,
                "snapshot_paragraph_id is required",
            )
        chapter_id = fields.get("snapshot_chapter_id")
        if chapter_id is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_SNAPSHOT_PARAGRAPH_MISMATCH,
                "snapshot_chapter_id is required",
            )

        # COMPLETED + book match via Phase 1A gateway (no second body reader).
        self._snapshot.validate_snapshot_for_book(int(snapshot_id), int(book_id))

        chapter = self._session.get(BookSnapshotChapter, int(chapter_id))
        if chapter is None or chapter.snapshot_id != int(snapshot_id):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_SNAPSHOT_PARAGRAPH_MISMATCH,
                "snapshot_chapter_id does not belong to book_snapshot_id",
            )
        paragraph = self._session.get(BookSnapshotParagraph, int(paragraph_id))
        if (
            paragraph is None
            or paragraph.snapshot_id != int(snapshot_id)
            or paragraph.snapshot_chapter_id != int(chapter_id)
        ):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_SNAPSHOT_PARAGRAPH_MISMATCH,
                "snapshot_paragraph_id does not belong to snapshot chapter",
            )

        expected_hash = str(fields.get("paragraph_content_hash") or "")
        if not expected_hash:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_HASH_MISMATCH,
                "paragraph_content_hash is required",
            )
        if expected_hash != paragraph.content_hash:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_HASH_MISMATCH,
                "paragraph_content_hash does not match snapshot paragraph",
            )

        # Recover text only through Snapshot service (gateway impl).
        paragraph_text = self._snapshot.get_snapshot_paragraph_text(int(paragraph_id))
        start_offset = int(fields.get("start_offset", 0))
        end_offset = int(fields.get("end_offset", 0))
        if start_offset < 0 or end_offset < start_offset or end_offset > len(paragraph_text):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_OFFSET_OUT_OF_RANGE,
                "evidence offsets must be within paragraph length",
            )

        role = str(fields.get("evidence_role", EvidenceRole.SUPPORT.value))
        try:
            EvidenceRole(role)
        except ValueError as exc:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_PARAGRAPH_REQUIRED,
                f"unsupported evidence_role={role}",
            ) from exc

        label = str(fields.get("evidence_label", "") or "")
        # Never store full user body in evidence_label.
        if len(label) > 500:
            label = label[:500]

        return {
            "book_snapshot_id": int(snapshot_id),
            "snapshot_chapter_id": int(chapter_id),
            "snapshot_paragraph_id": int(paragraph_id),
            "paragraph_content_hash": expected_hash,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "evidence_role": role,
            "evidence_label": label,
            "source_scene_id": fields.get("source_scene_id"),
        }

    def record_locked_vs_candidate_conflict(
        self,
        relation_id: int,
        candidate_version_id: int,
        *,
        run_id: int | None = None,
    ) -> Any:
        """Helper for Integration: locked Relation vs new model candidate."""
        relation = self.get_relation(relation_id)
        version = self._require_version(candidate_version_id)
        return self._conflicts.create_from_request(
            ConflictCreateRequest(
                book_id=relation.book_id,
                conflict_type="locked_asset_vs_new_run",
                left_ref_type="relation",
                left_ref_id=str(relation.id),
                right_ref_type="relation_version",
                right_ref_id=str(version.id),
                description=(
                    f"locked relation {relation.id} vs candidate version {version.id}"
                ),
                severity="blocking",
                run_id=run_id or version.run_id,
                book_snapshot_id=version.book_snapshot_id,
            )
        )
