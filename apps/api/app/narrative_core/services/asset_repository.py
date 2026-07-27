"""Narrative Asset / Version / Evidence persistence helpers (Agent E).

Business rules live in ``asset_service`` / ``asset_evidence_service``.
"""

from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    utc_now,
)
from app.narrative_core.enums import AssetLifecycleStatus, OriginType, ReviewStatus


class NarrativeAssetRepository:
    """Low-level CRUD for narrative assets, versions, and evidence rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Assets
    # ------------------------------------------------------------------

    def create_asset(
        self,
        book_id: int,
        asset_key: str,
        *,
        lifecycle_status: str = AssetLifecycleStatus.ACTIVE,
        is_locked: bool = False,
        **fields: Any,
    ) -> NarrativeAsset:
        asset = NarrativeAsset(
            book_id=int(book_id),
            asset_key=str(asset_key),
            lifecycle_status=str(lifecycle_status),
            is_locked=bool(is_locked),
            locked_at=fields.get("locked_at"),
            superseded_by_asset_id=fields.get("superseded_by_asset_id"),
            stale_at=fields.get("stale_at"),
            stale_reason=fields.get("stale_reason"),
            created_at=fields.get("created_at") or utc_now(),
            updated_at=fields.get("updated_at") or utc_now(),
        )
        self._session.add(asset)
        self._session.flush()
        return asset

    def get_asset(self, asset_id: int) -> NarrativeAsset | None:
        return self._session.get(NarrativeAsset, int(asset_id))

    def get_asset_by_key(self, book_id: int, asset_key: str) -> NarrativeAsset | None:
        return self._session.scalar(
            select(NarrativeAsset).where(
                NarrativeAsset.book_id == int(book_id),
                NarrativeAsset.asset_key == str(asset_key),
            )
        )

    def list_assets(
        self,
        book_id: int,
        *,
        include_archived: bool = False,
        include_superseded: bool = False,
        include_stale: bool = True,
        asset_type: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[NarrativeAsset]:
        stmt = select(NarrativeAsset).where(NarrativeAsset.book_id == int(book_id))
        excluded: list[str] = []
        if not include_archived:
            excluded.append(AssetLifecycleStatus.ARCHIVED)
        if not include_superseded:
            excluded.append(AssetLifecycleStatus.SUPERSEDED)
        if not include_stale:
            excluded.append(AssetLifecycleStatus.STALE)
        if excluded:
            stmt = stmt.where(~NarrativeAsset.lifecycle_status.in_(excluded))
        stmt = stmt.order_by(NarrativeAsset.id.asc()).offset(int(offset))
        if limit is not None:
            stmt = stmt.limit(int(limit))
        assets = list(self._session.scalars(stmt).all())
        if asset_type is None:
            return assets
        # Filter by canonical (or latest) version asset_type without joining away
        # assets that have no matching type on any version when caller scopes.
        typed: list[NarrativeAsset] = []
        for asset in assets:
            versions = self.list_versions(asset.id)
            if any(v.asset_type == asset_type for v in versions):
                typed.append(asset)
        return typed

    def touch_asset(self, asset: NarrativeAsset) -> NarrativeAsset:
        asset.updated_at = utc_now()
        self._session.flush()
        return asset

    # ------------------------------------------------------------------
    # Versions
    # ------------------------------------------------------------------

    def create_version(
        self,
        asset_id: int,
        *,
        asset_type: str,
        title: str = "",
        summary: str = "",
        narrative_function: str = "",
        attributes_json: str = "{}",
        confidence: float = 0.0,
        importance: float = 0.0,
        source_fingerprint: str = "",
        origin_type: str = OriginType.MODEL,
        review_status: str = ReviewStatus.CANDIDATE,
        is_canonical: bool = False,
        run_id: int | None = None,
        book_snapshot_id: int | None = None,
        **fields: Any,
    ) -> NarrativeAssetVersion:
        version = NarrativeAssetVersion(
            asset_id=int(asset_id),
            run_id=run_id,
            book_snapshot_id=book_snapshot_id,
            asset_type=str(asset_type),
            title=str(title or ""),
            summary=str(summary or ""),
            narrative_function=str(narrative_function or ""),
            attributes_json=str(attributes_json or "{}"),
            confidence=float(confidence),
            importance=float(importance),
            source_fingerprint=str(source_fingerprint or ""),
            origin_type=str(origin_type),
            review_status=str(review_status),
            is_canonical=bool(is_canonical),
            created_at=fields.get("created_at") or utc_now(),
        )
        self._session.add(version)
        self._session.flush()
        return version

    def get_version(self, asset_version_id: int) -> NarrativeAssetVersion | None:
        return self._session.get(NarrativeAssetVersion, int(asset_version_id))

    def list_versions(self, asset_id: int) -> list[NarrativeAssetVersion]:
        stmt = (
            select(NarrativeAssetVersion)
            .where(NarrativeAssetVersion.asset_id == int(asset_id))
            .order_by(NarrativeAssetVersion.id.asc())
        )
        return list(self._session.scalars(stmt).all())

    def get_canonical_version(self, asset_id: int) -> NarrativeAssetVersion | None:
        return self._session.scalar(
            select(NarrativeAssetVersion).where(
                NarrativeAssetVersion.asset_id == int(asset_id),
                NarrativeAssetVersion.is_canonical.is_(True),
            )
        )

    def clear_canonical_flag(self, asset_id: int) -> None:
        """Clear is_canonical for all versions of an asset (same transaction)."""
        versions = self.list_versions(asset_id)
        for version in versions:
            if version.is_canonical:
                version.is_canonical = False
        self._session.flush()

    def set_canonical_flag(self, version: NarrativeAssetVersion, *, value: bool) -> None:
        version.is_canonical = bool(value)
        self._session.flush()

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------

    def create_evidence(
        self,
        asset_version_id: int,
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
        **fields: Any,
    ) -> NarrativeAssetEvidence:
        evidence = NarrativeAssetEvidence(
            asset_version_id=int(asset_version_id),
            book_snapshot_id=int(book_snapshot_id),
            snapshot_chapter_id=int(snapshot_chapter_id),
            snapshot_paragraph_id=int(snapshot_paragraph_id),
            source_scene_id=source_scene_id,
            paragraph_content_hash=str(paragraph_content_hash),
            start_offset=int(start_offset),
            end_offset=int(end_offset),
            evidence_role=str(evidence_role),
            evidence_label=str(evidence_label or ""),
            created_at=fields.get("created_at") or utc_now(),
        )
        self._session.add(evidence)
        self._session.flush()
        return evidence

    def get_evidence(self, evidence_id: int) -> NarrativeAssetEvidence | None:
        return self._session.get(NarrativeAssetEvidence, int(evidence_id))

    def list_evidence_for_version(
        self, asset_version_id: int
    ) -> list[NarrativeAssetEvidence]:
        stmt = (
            select(NarrativeAssetEvidence)
            .where(NarrativeAssetEvidence.asset_version_id == int(asset_version_id))
            .order_by(NarrativeAssetEvidence.id.asc())
        )
        return list(self._session.scalars(stmt).all())

    def delete_evidence(self, evidence: NarrativeAssetEvidence) -> None:
        self._session.delete(evidence)
        self._session.flush()

    def get_version_with_evidence(
        self, asset_version_id: int
    ) -> NarrativeAssetVersion | None:
        return self._session.scalar(
            select(NarrativeAssetVersion)
            .where(NarrativeAssetVersion.id == int(asset_version_id))
            .options(selectinload(NarrativeAssetVersion.evidence))
        )

    def count_canonical_flags(self, asset_id: int) -> int:
        versions = self.list_versions(asset_id)
        return sum(1 for version in versions if version.is_canonical)

    def list_assets_by_ids(self, asset_ids: Sequence[int]) -> list[NarrativeAsset]:
        if not asset_ids:
            return []
        stmt = select(NarrativeAsset).where(NarrativeAsset.id.in_([int(i) for i in asset_ids]))
        return list(self._session.scalars(stmt).all())
