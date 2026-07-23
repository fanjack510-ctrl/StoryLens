"""Narrative Relation / Version / Evidence repository (Agent F).

Persists stable Relation identity and versioned interpretations.
Does not call models or implement Asset services.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    NarrativeRelation,
    NarrativeRelationEvidence,
    NarrativeRelationVersion,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NarrativeRelationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_relation(
        self,
        *,
        book_id: int,
        source_asset_id: int,
        target_asset_id: int,
        relation_key: str,
        lifecycle_status: str = "active",
        is_locked: bool = False,
    ) -> NarrativeRelation:
        row = NarrativeRelation(
            book_id=book_id,
            source_asset_id=source_asset_id,
            target_asset_id=target_asset_id,
            relation_key=relation_key,
            lifecycle_status=lifecycle_status,
            is_locked=is_locked,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        self._session.add(row)
        self._session.flush()
        return row

    def get_relation(self, relation_id: int) -> NarrativeRelation | None:
        return self._session.get(NarrativeRelation, relation_id)

    def find_by_relation_key(
        self, book_id: int, relation_key: str
    ) -> NarrativeRelation | None:
        return self._session.scalar(
            select(NarrativeRelation).where(
                NarrativeRelation.book_id == book_id,
                NarrativeRelation.relation_key == relation_key,
            )
        )

    def list_relations(
        self,
        book_id: int,
        *,
        lifecycle_status: str | None = None,
        source_asset_id: int | None = None,
        target_asset_id: int | None = None,
    ) -> list[NarrativeRelation]:
        stmt = select(NarrativeRelation).where(NarrativeRelation.book_id == book_id)
        if lifecycle_status is not None:
            stmt = stmt.where(NarrativeRelation.lifecycle_status == lifecycle_status)
        if source_asset_id is not None:
            stmt = stmt.where(NarrativeRelation.source_asset_id == source_asset_id)
        if target_asset_id is not None:
            stmt = stmt.where(NarrativeRelation.target_asset_id == target_asset_id)
        stmt = stmt.order_by(NarrativeRelation.id.asc())
        return list(self._session.scalars(stmt).all())

    def add_version(
        self,
        relation_id: int,
        *,
        relation_type: str,
        summary: str = "",
        attributes_json: str = "{}",
        confidence: float = 0.0,
        importance: float = 0.0,
        source_fingerprint: str = "",
        origin_type: str = "model",
        review_status: str = "candidate",
        is_canonical: bool = False,
        run_id: int | None = None,
        book_snapshot_id: int | None = None,
    ) -> NarrativeRelationVersion:
        row = NarrativeRelationVersion(
            relation_id=relation_id,
            run_id=run_id,
            book_snapshot_id=book_snapshot_id,
            relation_type=relation_type,
            summary=summary,
            attributes_json=attributes_json,
            confidence=confidence,
            importance=importance,
            source_fingerprint=source_fingerprint,
            origin_type=origin_type,
            review_status=review_status,
            is_canonical=is_canonical,
            created_at=_utc_now(),
        )
        self._session.add(row)
        self._session.flush()
        return row

    def get_version(self, relation_version_id: int) -> NarrativeRelationVersion | None:
        return self._session.get(NarrativeRelationVersion, relation_version_id)

    def list_versions(self, relation_id: int) -> list[NarrativeRelationVersion]:
        stmt = (
            select(NarrativeRelationVersion)
            .where(NarrativeRelationVersion.relation_id == relation_id)
            .order_by(NarrativeRelationVersion.id.asc())
        )
        return list(self._session.scalars(stmt).all())

    def get_canonical_version(
        self, relation_id: int
    ) -> NarrativeRelationVersion | None:
        return self._session.scalar(
            select(NarrativeRelationVersion).where(
                NarrativeRelationVersion.relation_id == relation_id,
                NarrativeRelationVersion.is_canonical.is_(True),
            )
        )

    def clear_canonical_flags(self, relation_id: int) -> None:
        for version in self.list_versions(relation_id):
            if version.is_canonical:
                version.is_canonical = False
        self._session.flush()

    def add_evidence(
        self,
        relation_version_id: int,
        *,
        book_snapshot_id: int,
        snapshot_chapter_id: int,
        snapshot_paragraph_id: int,
        paragraph_content_hash: str,
        start_offset: int,
        end_offset: int,
        evidence_role: str = "support",
        evidence_label: str = "",
        source_scene_id: int | None = None,
    ) -> NarrativeRelationEvidence:
        row = NarrativeRelationEvidence(
            relation_version_id=relation_version_id,
            book_snapshot_id=book_snapshot_id,
            snapshot_chapter_id=snapshot_chapter_id,
            snapshot_paragraph_id=snapshot_paragraph_id,
            source_scene_id=source_scene_id,
            paragraph_content_hash=paragraph_content_hash,
            start_offset=start_offset,
            end_offset=end_offset,
            evidence_role=evidence_role,
            evidence_label=evidence_label,
            created_at=_utc_now(),
        )
        self._session.add(row)
        self._session.flush()
        return row

    def get_evidence(self, evidence_id: int) -> NarrativeRelationEvidence | None:
        return self._session.get(NarrativeRelationEvidence, evidence_id)

    def list_version_evidence(
        self, relation_version_id: int
    ) -> list[NarrativeRelationEvidence]:
        stmt = (
            select(NarrativeRelationEvidence)
            .where(
                NarrativeRelationEvidence.relation_version_id == relation_version_id
            )
            .order_by(NarrativeRelationEvidence.id.asc())
        )
        return list(self._session.scalars(stmt).all())

    def touch_relation(self, relation: NarrativeRelation) -> None:
        relation.updated_at = _utc_now()
        self._session.flush()
