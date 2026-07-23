"""Narrative Asset / Version service (Agent E).

Stable identity (NarrativeAsset) vs interpretation (NarrativeAssetVersion).
Canonical switches are transactional; Lock is orthogonal to review_status.
Does not create AnalysisConflict rows — returns ConflictRequest for Agent F.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import NarrativeAsset, NarrativeAssetVersion, utc_now
from app.narrative_core.asset_key import build_asset_key
from app.narrative_core.enums import (
    AssetLifecycleStatus,
    ConflictRefType,
    ConflictType,
    OriginType,
    ReviewStatus,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.asset_evidence_service import NarrativeAssetEvidenceService
from app.narrative_core.services.asset_repository import NarrativeAssetRepository


_CANONICAL_ELIGIBLE = frozenset({ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED})
_USER_PROTECTED = frozenset({ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED})


@dataclass(frozen=True)
class AssetCanonicalConflictRequest:
    """Payload for Integration / Agent F to open an AnalysisConflict.

    Agent E must not write analysis_conflicts itself.
    """

    book_id: int
    asset_id: int
    locked_canonical_version_id: int | None
    candidate_version_id: int
    conflict_type: str = ConflictType.LOCKED_ASSET_VS_NEW_RUN
    left_ref_type: str = ConflictRefType.ASSET_VERSION
    right_ref_type: str = ConflictRefType.ASSET_VERSION
    description: str = ""
    reason: str = "locked_or_protected_canonical"


@dataclass(frozen=True)
class AssetMutationResult:
    """Uniform return for confirm / correct / model promote attempts."""

    asset: NarrativeAsset
    version: NarrativeAssetVersion
    conflict_request: AssetCanonicalConflictRequest | None = None
    canonical_switched: bool = False


class NarrativeAssetService:
    """Implements NarrativeAssetService Protocol + Phase 1B Agent E surface."""

    def __init__(
        self,
        session: Session,
        *,
        repository: NarrativeAssetRepository | None = None,
        evidence_service: NarrativeAssetEvidenceService | None = None,
    ) -> None:
        self._session = session
        self._repo = repository or NarrativeAssetRepository(session)
        self._evidence = evidence_service or NarrativeAssetEvidenceService(
            session, repository=self._repo
        )

    # ------------------------------------------------------------------
    # Asset key helpers (stable SHA-256 via frozen build_asset_key)
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_asset_key(
        *,
        book_id: int,
        asset_type: str,
        identity_fingerprint: str | None = None,
        stable_label: str | None = None,
        disambiguator: str = "",
        independent: bool = False,
    ) -> str:
        """Build a stable asset_key.

        Prefer an explicit ``identity_fingerprint`` from the caller. Mutable
        title/summary must not be used alone as identity. When no stable
        fingerprint is available, pass ``independent=True`` (or omit both
        fingerprint and label) to create a unique unbound key — never force
        merge via Python ``hash()`` or mutable summaries.
        """
        fingerprint = (identity_fingerprint or "").strip()
        label = (stable_label or "").strip()
        if independent or (not fingerprint and not label):
            # Independent candidate identity — unique, stable for this row only.
            unbound = disambiguator or f"independent:{secrets.token_hex(16)}"
            return build_asset_key(
                book_id=book_id,
                asset_type=asset_type,
                stable_label=fingerprint or label or "unbound",
                disambiguator=unbound,
            )
        return build_asset_key(
            book_id=book_id,
            asset_type=asset_type,
            stable_label=fingerprint or label,
            disambiguator=disambiguator,
        )

    # ------------------------------------------------------------------
    # Create / versions
    # ------------------------------------------------------------------

    def create_candidate_asset(
        self,
        book_id: int,
        *,
        asset_type: str,
        title: str,
        summary: str = "",
        run_id: int | None = None,
        book_snapshot_id: int | None = None,
        stable_label: str | None = None,
        identity_fingerprint: str | None = None,
        disambiguator: str = "",
        independent: bool = False,
        asset_key: str | None = None,
        reuse_existing_key: bool = True,
        **fields: Any,
    ) -> AssetMutationResult:
        """Create stable Asset + first candidate version. Never auto-canonical."""
        key = asset_key or self.resolve_asset_key(
            book_id=book_id,
            asset_type=asset_type,
            identity_fingerprint=identity_fingerprint,
            stable_label=stable_label,
            disambiguator=disambiguator,
            independent=independent,
        )

        asset: NarrativeAsset | None = None
        if reuse_existing_key and not independent:
            asset = self._repo.get_asset_by_key(book_id, key)

        if asset is None:
            try:
                with self._session.begin_nested():
                    asset = self._repo.create_asset(book_id, key)
            except IntegrityError:
                # Concurrent create with same key — reuse winner when allowed.
                asset = self._repo.get_asset_by_key(book_id, key)
                if asset is None or not reuse_existing_key:
                    raise

        version = self._repo.create_version(
            asset.id,
            asset_type=asset_type,
            title=title,
            summary=summary,
            narrative_function=str(fields.get("narrative_function", "") or ""),
            attributes_json=self._attrs_json(fields.get("attributes_json", "{}")),
            confidence=float(fields.get("confidence", 0.0) or 0.0),
            importance=float(fields.get("importance", 0.0) or 0.0),
            source_fingerprint=str(fields.get("source_fingerprint", "") or ""),
            origin_type=str(fields.get("origin_type", OriginType.MODEL)),
            review_status=ReviewStatus.CANDIDATE,
            is_canonical=False,
            run_id=run_id,
            book_snapshot_id=book_snapshot_id,
        )
        self._repo.touch_asset(asset)
        self._session.flush()
        return AssetMutationResult(asset=asset, version=version)

    def add_asset_version(
        self,
        asset_id: int,
        *,
        asset_type: str,
        title: str,
        review_status: str = ReviewStatus.CANDIDATE,
        origin_type: str = OriginType.MODEL,
        run_id: int | None = None,
        book_snapshot_id: int | None = None,
        **fields: Any,
    ) -> NarrativeAssetVersion:
        asset = self._require_asset(asset_id)
        status = ReviewStatus(str(review_status))
        # New versions are never auto-canonical; confirm/correct own the switch.
        version = self._repo.create_version(
            asset.id,
            asset_type=asset_type,
            title=title,
            summary=str(fields.get("summary", "") or ""),
            narrative_function=str(fields.get("narrative_function", "") or ""),
            attributes_json=self._attrs_json(fields.get("attributes_json", "{}")),
            confidence=float(fields.get("confidence", 0.0) or 0.0),
            importance=float(fields.get("importance", 0.0) or 0.0),
            source_fingerprint=str(fields.get("source_fingerprint", "") or ""),
            origin_type=str(origin_type),
            review_status=status,
            is_canonical=False,
            run_id=run_id,
            book_snapshot_id=book_snapshot_id,
        )
        self._repo.touch_asset(asset)
        self._session.flush()
        return version

    def get_asset(self, asset_id: int) -> NarrativeAsset:
        return self._require_asset(asset_id)

    def get_asset_versions(self, asset_id: int) -> list[NarrativeAssetVersion]:
        self._require_asset(asset_id)
        return self._repo.list_versions(asset_id)

    def get_canonical_asset_version(self, asset_id: int) -> NarrativeAssetVersion | None:
        self._require_asset(asset_id)
        return self._repo.get_canonical_version(asset_id)

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
        """List assets for a book.

        Default excludes ``archived`` / ``superseded``. Pass explicit flags to
        include them. ``stale`` is included by default (stale ≠ rejected).
        """
        return self._repo.list_assets(
            book_id,
            include_archived=include_archived,
            include_superseded=include_superseded,
            include_stale=include_stale,
            asset_type=asset_type,
            limit=limit,
            offset=offset,
        )

    # ------------------------------------------------------------------
    # Review / canonical
    # ------------------------------------------------------------------

    def confirm_asset_version(
        self,
        asset_version_id: int,
        *,
        make_canonical: bool = True,
        actor: str = "user",
    ) -> AssetMutationResult:
        version = self._require_version(asset_version_id)
        asset = self._require_asset(version.asset_id)

        if version.review_status == ReviewStatus.REJECTED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.REJECTED_CANNOT_BE_CANONICAL,
                f"rejected version {version.id} cannot be confirmed/canonical",
            )

        version.review_status = ReviewStatus.CONFIRMED
        self._session.flush()

        if not make_canonical:
            self._repo.touch_asset(asset)
            return AssetMutationResult(asset=asset, version=version)

        return self._try_switch_canonical(asset, version, actor=actor)

    def correct_asset(
        self,
        asset_id: int,
        *,
        based_on_version_id: int,
        title: str,
        summary: str = "",
        make_canonical: bool = True,
        actor: str = "user",
        **fields: Any,
    ) -> AssetMutationResult:
        """User correction creates a new Version — never mutates the prior row."""
        asset = self._require_asset(asset_id)
        base = self._require_version(based_on_version_id)
        if base.asset_id != asset.id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_VERSION_NOT_FOUND,
                f"version {based_on_version_id} does not belong to asset {asset_id}",
            )

        corrected = self._repo.create_version(
            asset.id,
            asset_type=str(fields.get("asset_type", base.asset_type)),
            title=title,
            summary=summary,
            narrative_function=str(
                fields.get("narrative_function", base.narrative_function) or ""
            ),
            attributes_json=self._attrs_json(
                fields.get("attributes_json", base.attributes_json)
            ),
            confidence=float(fields.get("confidence", base.confidence) or 0.0),
            importance=float(fields.get("importance", base.importance) or 0.0),
            source_fingerprint=str(
                fields.get("source_fingerprint", base.source_fingerprint) or ""
            ),
            origin_type=OriginType.USER,
            review_status=ReviewStatus.CORRECTED,
            is_canonical=False,
            run_id=fields.get("run_id"),
            book_snapshot_id=fields.get("book_snapshot_id", base.book_snapshot_id),
        )
        # Prior version rows are retained forever.
        if not make_canonical:
            self._repo.touch_asset(asset)
            return AssetMutationResult(asset=asset, version=corrected)

        return self._try_switch_canonical(asset, corrected, actor=actor)

    def reject_asset_version(self, asset_version_id: int) -> NarrativeAssetVersion:
        version = self._require_version(asset_version_id)
        asset = self._require_asset(version.asset_id)
        was_canonical = bool(version.is_canonical)
        version.review_status = ReviewStatus.REJECTED
        if was_canonical:
            version.is_canonical = False
        self._repo.touch_asset(asset)
        self._session.flush()
        return version

    def _try_switch_canonical(
        self,
        asset: NarrativeAsset,
        version: NarrativeAssetVersion,
        *,
        actor: str,
    ) -> AssetMutationResult:
        if version.review_status == ReviewStatus.REJECTED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.REJECTED_CANNOT_BE_CANONICAL,
                f"rejected version {version.id} cannot become canonical",
            )
        if version.review_status == ReviewStatus.CANDIDATE:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CANDIDATE_CANNOT_BE_CANONICAL,
                f"candidate version {version.id} cannot become canonical",
            )
        if version.review_status not in _CANONICAL_ELIGIBLE:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CANONICAL_VERSION_REQUIRED,
                f"version {version.id} review_status={version.review_status}",
            )

        current = self._repo.get_canonical_version(asset.id)

        # Locked asset: model must not switch canonical — return ConflictRequest.
        if actor == "model" and asset.is_locked:
            return AssetMutationResult(
                asset=asset,
                version=version,
                conflict_request=AssetCanonicalConflictRequest(
                    book_id=asset.book_id,
                    asset_id=asset.id,
                    locked_canonical_version_id=None if current is None else current.id,
                    candidate_version_id=version.id,
                    conflict_type=ConflictType.LOCKED_ASSET_VS_NEW_RUN,
                    description=(
                        f"model attempted canonical switch on locked asset {asset.id}"
                    ),
                    reason="asset_locked",
                ),
                canonical_switched=False,
            )

        # New model run must not replace user confirmed/corrected canonical.
        if (
            actor == "model"
            and current is not None
            and current.id != version.id
            and current.review_status in _USER_PROTECTED
        ):
            return AssetMutationResult(
                asset=asset,
                version=version,
                conflict_request=AssetCanonicalConflictRequest(
                    book_id=asset.book_id,
                    asset_id=asset.id,
                    locked_canonical_version_id=current.id,
                    candidate_version_id=version.id,
                    conflict_type=ConflictType.DUPLICATE_ASSET_CANDIDATE,
                    description=(
                        f"model must not replace user {current.review_status} "
                        f"canonical version {current.id}"
                    ),
                    reason="user_protected_canonical",
                ),
                canonical_switched=False,
            )

        try:
            # Single transaction / savepoint: clear old + set new together.
            with self._session.begin_nested():
                self._repo.clear_canonical_flag(asset.id)
                # Re-load version after clear (same identity).
                target = self._require_version(version.id)
                if target.review_status not in _CANONICAL_ELIGIBLE:
                    raise NarrativeCoreError(
                        NarrativeCoreErrorCode.CANONICAL_VERSION_REQUIRED,
                        f"version {target.id} not eligible after clear",
                    )
                target.is_canonical = True
                self._session.flush()
            self._repo.touch_asset(asset)
            self._session.flush()
            refreshed = self._require_version(version.id)
            return AssetMutationResult(
                asset=asset,
                version=refreshed,
                canonical_switched=True,
            )
        except IntegrityError as exc:
            # Partial unique index / race — leave state unchanged in savepoint.
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.CANONICAL_VERSION_REQUIRED,
                f"canonical switch failed for asset {asset.id}: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Lock / stale / supersede
    # ------------------------------------------------------------------

    def lock_asset(self, asset_id: int) -> NarrativeAsset:
        asset = self._require_asset(asset_id)
        asset.is_locked = True
        asset.locked_at = utc_now()
        self._repo.touch_asset(asset)
        self._session.flush()
        return asset

    def unlock_asset(self, asset_id: int) -> NarrativeAsset:
        asset = self._require_asset(asset_id)
        asset.is_locked = False
        asset.locked_at = None
        self._repo.touch_asset(asset)
        self._session.flush()
        return asset

    def mark_asset_stale(self, asset_id: int, *, reason: str) -> NarrativeAsset:
        """Mark stale context — does not reject versions or delete evidence."""
        asset = self._require_asset(asset_id)
        if asset.lifecycle_status == AssetLifecycleStatus.SUPERSEDED:
            # Superseded stays superseded; still record stale markers.
            asset.stale_at = utc_now()
            asset.stale_reason = str(reason)
        elif asset.lifecycle_status != AssetLifecycleStatus.ARCHIVED:
            asset.lifecycle_status = AssetLifecycleStatus.STALE
            asset.stale_at = utc_now()
            asset.stale_reason = str(reason)
        else:
            asset.stale_at = utc_now()
            asset.stale_reason = str(reason)
        self._repo.touch_asset(asset)
        self._session.flush()
        return asset

    def clear_asset_stale(self, asset_id: int) -> NarrativeAsset:
        asset = self._require_asset(asset_id)
        asset.stale_at = None
        asset.stale_reason = None
        if asset.lifecycle_status == AssetLifecycleStatus.STALE:
            asset.lifecycle_status = AssetLifecycleStatus.ACTIVE
        self._repo.touch_asset(asset)
        self._session.flush()
        return asset

    def supersede_asset(
        self, asset_id: int, *, superseded_by_asset_id: int
    ) -> NarrativeAsset:
        """Replace stable identity with another — not a version update."""
        asset = self._require_asset(asset_id)
        replacement = self._require_asset(superseded_by_asset_id)
        if replacement.book_id != asset.book_id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_NOT_FOUND,
                "supersede target must share the same book_id",
            )
        if replacement.id == asset.id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_NOT_FOUND,
                "asset cannot supersede itself",
            )
        asset.lifecycle_status = AssetLifecycleStatus.SUPERSEDED
        asset.superseded_by_asset_id = replacement.id
        self._repo.touch_asset(asset)
        self._session.flush()
        return asset

    # ------------------------------------------------------------------
    # Evidence delegation (Protocol surface)
    # ------------------------------------------------------------------

    def attach_asset_evidence(
        self, asset_version_id: int, **evidence_fields: Any
    ) -> Any:
        return self._evidence.attach_asset_evidence(asset_version_id, **evidence_fields)

    def validate_asset_evidence(self, evidence_id: int) -> bool:
        return self._evidence.validate_asset_evidence(evidence_id)

    def list_asset_version_evidence(self, asset_version_id: int) -> Any:
        return self._evidence.list_asset_version_evidence(asset_version_id)

    def remove_candidate_evidence(self, evidence_id: int, *, actor: str = "model") -> None:
        self._evidence.remove_candidate_evidence(evidence_id, actor=actor)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_asset(self, asset_id: int) -> NarrativeAsset:
        asset = self._repo.get_asset(asset_id)
        if asset is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_NOT_FOUND,
                f"asset not found: {asset_id}",
            )
        return asset

    def _require_version(self, asset_version_id: int) -> NarrativeAssetVersion:
        version = self._repo.get_version(asset_version_id)
        if version is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_VERSION_NOT_FOUND,
                f"asset version not found: {asset_version_id}",
            )
        return version

    @staticmethod
    def _attrs_json(value: Any) -> str:
        if value is None:
            return "{}"
        if isinstance(value, str):
            return value or "{}"
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
