"""Asset Evidence validation and attachment (Agent E).

Must reuse Phase 1A SnapshotValidationGateway / BookSnapshotService —
never a second body-reader path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import (
    BookSnapshotChapter,
    BookSnapshotParagraph,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
)
from app.narrative_core.contracts.dto import EvidenceBindingDTO
from app.narrative_core.contracts.snapshot import SnapshotValidationGateway
from app.narrative_core.enums import EvidenceRole, ReviewStatus
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.asset_repository import NarrativeAssetRepository
from app.narrative_core.services.snapshot_service import (
    BookSnapshotServiceImpl,
    SnapshotValidationGatewayImpl,
)
from app.narrative_core.services.version_binding import assert_evidence_matches_version_snapshot


_FORMAL_REVIEW = frozenset({ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED})


@dataclass(frozen=True)
class EvidenceValidationResult:
    ok: bool
    paragraph_text: str = ""
    excerpt: str = ""


class NarrativeAssetEvidenceService:
    """Evidence bind/validate/list/remove for Asset Versions."""

    def __init__(
        self,
        session: Session,
        *,
        snapshot_gateway: SnapshotValidationGateway | None = None,
        snapshot_service: BookSnapshotServiceImpl | None = None,
        repository: NarrativeAssetRepository | None = None,
    ) -> None:
        self._session = session
        self._repo = repository or NarrativeAssetRepository(session)
        # Production default: real Snapshot gateway / paragraph restore.
        self._gateway: SnapshotValidationGateway = (
            snapshot_gateway or SnapshotValidationGatewayImpl(session)
        )
        self._snapshots: BookSnapshotServiceImpl = snapshot_service or (
            snapshot_gateway  # type: ignore[assignment]
            if isinstance(snapshot_gateway, BookSnapshotServiceImpl)
            else BookSnapshotServiceImpl(session)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def attach_asset_evidence(
        self,
        asset_version_id: int,
        **evidence_fields: Any,
    ) -> NarrativeAssetEvidence:
        version = self._require_version(asset_version_id)
        asset = self._require_asset(version.asset_id)
        self._assert_may_mutate_evidence(asset, version, actor=str(evidence_fields.pop("actor", "model")))

        binding = self._coerce_binding(evidence_fields)
        self._validate_binding_against_snapshot(asset, binding)
        assert_evidence_matches_version_snapshot(
            version_snapshot_id=version.book_snapshot_id,
            evidence_snapshot_id=int(binding.book_snapshot_id),
        )

        return self._repo.create_evidence(
            version.id,
            book_snapshot_id=binding.book_snapshot_id,
            snapshot_chapter_id=binding.snapshot_chapter_id,
            snapshot_paragraph_id=binding.snapshot_paragraph_id,
            paragraph_content_hash=binding.paragraph_content_hash,
            start_offset=binding.start_offset,
            end_offset=binding.end_offset,
            evidence_role=binding.evidence_role,
            evidence_label=binding.evidence_label,
            source_scene_id=binding.source_scene_id,
        )

    def validate_asset_evidence(self, evidence_id: int) -> bool:
        evidence = self._repo.get_evidence(evidence_id)
        if evidence is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_VERSION_NOT_FOUND,
                f"evidence not found: {evidence_id}",
            )
        version = self._require_version(evidence.asset_version_id)
        asset = self._require_asset(version.asset_id)
        binding = EvidenceBindingDTO(
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
        self._validate_binding_against_snapshot(asset, binding)
        assert_evidence_matches_version_snapshot(
            version_snapshot_id=version.book_snapshot_id,
            evidence_snapshot_id=int(evidence.book_snapshot_id),
        )
        return True

    def list_asset_version_evidence(
        self, asset_version_id: int
    ) -> list[NarrativeAssetEvidence]:
        self._require_version(asset_version_id)
        return self._repo.list_evidence_for_version(asset_version_id)

    def remove_candidate_evidence(
        self,
        evidence_id: int,
        *,
        actor: str = "model",
    ) -> None:
        evidence = self._repo.get_evidence(evidence_id)
        if evidence is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_VERSION_NOT_FOUND,
                f"evidence not found: {evidence_id}",
            )
        version = self._require_version(evidence.asset_version_id)
        asset = self._require_asset(version.asset_id)

        # confirmed/corrected canonical evidence must not be silently deleted by model.
        if actor == "model":
            if version.is_canonical and version.review_status in _FORMAL_REVIEW:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.ASSET_LOCKED,
                    "model cannot delete evidence on confirmed/corrected canonical version",
                )
            if asset.is_locked and version.review_status in _FORMAL_REVIEW:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.ASSET_LOCKED,
                    "model cannot modify formal evidence on locked asset",
                )
            if version.review_status != ReviewStatus.CANDIDATE:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.ASSET_LOCKED,
                    "model may only remove candidate evidence",
                )
        self._repo.delete_evidence(evidence)

    def restore_evidence_excerpt(self, evidence_id: int) -> str:
        """Recover excerpt text via Phase 1A snapshot paragraph APIs."""
        evidence = self._repo.get_evidence(evidence_id)
        if evidence is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_VERSION_NOT_FOUND,
                f"evidence not found: {evidence_id}",
            )
        paragraph_text = self._snapshots.get_snapshot_paragraph_text(
            evidence.snapshot_paragraph_id
        )
        start = evidence.start_offset
        end = evidence.end_offset
        if start < 0 or end < start or end > len(paragraph_text):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_OFFSET_OUT_OF_RANGE,
                f"offset [{start},{end}) out of paragraph length {len(paragraph_text)}",
            )
        return paragraph_text[start:end]

    # ------------------------------------------------------------------
    # Validation internals
    # ------------------------------------------------------------------

    def _validate_binding_against_snapshot(
        self,
        asset: NarrativeAsset,
        binding: EvidenceBindingDTO,
    ) -> EvidenceValidationResult:
        if binding.book_snapshot_id is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_SNAPSHOT_REQUIRED,
                "book_snapshot_id is required",
            )
        if binding.snapshot_paragraph_id is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_PARAGRAPH_REQUIRED,
                "snapshot_paragraph_id is required",
            )

        role = str(binding.evidence_role or EvidenceRole.SUPPORT)
        if role not in {r.value for r in EvidenceRole}:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_SNAPSHOT_PARAGRAPH_MISMATCH,
                f"invalid evidence_role: {role}",
            )

        # Snapshot must exist, be COMPLETED, and match Asset book_id.
        self._gateway.validate_snapshot_for_book(
            int(binding.book_snapshot_id), int(asset.book_id)
        )

        chapter = self._session.get(BookSnapshotChapter, int(binding.snapshot_chapter_id))
        if chapter is None or chapter.snapshot_id != int(binding.book_snapshot_id):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_SNAPSHOT_PARAGRAPH_MISMATCH,
                "snapshot_chapter does not belong to snapshot",
            )

        paragraph = self._session.get(
            BookSnapshotParagraph, int(binding.snapshot_paragraph_id)
        )
        if paragraph is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_PARAGRAPH_REQUIRED,
                f"snapshot paragraph not found: {binding.snapshot_paragraph_id}",
            )
        if paragraph.snapshot_id != int(binding.book_snapshot_id):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_SNAPSHOT_PARAGRAPH_MISMATCH,
                "snapshot_paragraph does not belong to snapshot",
            )
        if paragraph.snapshot_chapter_id != int(binding.snapshot_chapter_id):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_SNAPSHOT_PARAGRAPH_MISMATCH,
                "snapshot_paragraph does not belong to snapshot_chapter",
            )

        if paragraph.content_hash != binding.paragraph_content_hash:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_HASH_MISMATCH,
                "paragraph_content_hash does not match snapshot paragraph",
            )

        # Restore body via Phase 1A service (not a second reader).
        paragraph_text = self._snapshots.get_snapshot_paragraph_text(paragraph.id)
        start = int(binding.start_offset)
        end = int(binding.end_offset)
        length = len(paragraph_text)
        if start < 0 or end < start or end > length:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_OFFSET_OUT_OF_RANGE,
                f"offset [{start},{end}) out of paragraph length {length}",
            )

        return EvidenceValidationResult(
            ok=True,
            paragraph_text=paragraph_text,
            excerpt=paragraph_text[start:end],
        )

    def _coerce_binding(self, fields: dict[str, Any]) -> EvidenceBindingDTO:
        if "binding" in fields and isinstance(fields["binding"], EvidenceBindingDTO):
            return fields["binding"]

        required = (
            "book_snapshot_id",
            "snapshot_chapter_id",
            "snapshot_paragraph_id",
            "paragraph_content_hash",
            "start_offset",
            "end_offset",
        )
        missing = [name for name in required if name not in fields or fields[name] is None]
        if "book_snapshot_id" in missing:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_SNAPSHOT_REQUIRED,
                "book_snapshot_id is required",
            )
        if "snapshot_paragraph_id" in missing:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_PARAGRAPH_REQUIRED,
                "snapshot_paragraph_id is required",
            )
        if missing:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_PARAGRAPH_REQUIRED,
                f"missing evidence fields: {', '.join(missing)}",
            )

        role = str(fields.get("evidence_role", EvidenceRole.SUPPORT))
        if role not in {r.value for r in EvidenceRole}:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.EVIDENCE_SNAPSHOT_PARAGRAPH_MISMATCH,
                f"invalid evidence_role: {role}",
            )

        return EvidenceBindingDTO(
            book_snapshot_id=int(fields["book_snapshot_id"]),
            snapshot_chapter_id=int(fields["snapshot_chapter_id"]),
            snapshot_paragraph_id=int(fields["snapshot_paragraph_id"]),
            paragraph_content_hash=str(fields["paragraph_content_hash"]),
            start_offset=int(fields["start_offset"]),
            end_offset=int(fields["end_offset"]),
            evidence_role=role,
            evidence_label=str(fields.get("evidence_label", "") or ""),
            source_scene_id=(
                None
                if fields.get("source_scene_id") is None
                else int(fields["source_scene_id"])
            ),
        )

    def _assert_may_mutate_evidence(
        self,
        asset: NarrativeAsset,
        version: NarrativeAssetVersion,
        *,
        actor: str,
    ) -> None:
        if actor != "model":
            return
        # Locked asset: formal evidence must not be model-modified.
        if asset.is_locked and (
            version.is_canonical and version.review_status in _FORMAL_REVIEW
        ):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_LOCKED,
                "model cannot modify formal evidence on locked asset",
            )

    def _require_version(self, asset_version_id: int) -> NarrativeAssetVersion:
        version = self._repo.get_version(asset_version_id)
        if version is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_VERSION_NOT_FOUND,
                f"asset version not found: {asset_version_id}",
            )
        return version

    def _require_asset(self, asset_id: int) -> NarrativeAsset:
        asset = self._repo.get_asset(asset_id)
        if asset is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.ASSET_NOT_FOUND,
                f"asset not found: {asset_id}",
            )
        return asset
