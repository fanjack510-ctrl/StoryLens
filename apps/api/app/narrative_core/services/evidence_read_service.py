"""Phase 1D Agent L — read-only Evidence Adapter.

Projects Asset / Relation Evidence into WholeBookEvidenceRefDto.
Uses Phase 1A Snapshot Reader only — never live Paragraph rows as Evidence body.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.db.models import (
    BookSnapshot,
    BookSnapshotChapter,
    BookSnapshotParagraph,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    NarrativeRelation,
    NarrativeRelationEvidence,
    NarrativeRelationVersion,
)
from app.narrative_core.enums import EvidenceRole, SnapshotStatus
from app.narrative_core.hash_canon import calculate_text_hash
from app.narrative_core.product_contract.enums import EvidenceIntegrityStatus
from app.narrative_core.product_contract.evidence import (
    MAX_PARAGRAPH_PREVIEW_CHARS,
    WholeBookEvidenceRefDto,
)
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl

EvidenceType = Literal["asset_evidence", "relation_evidence"]


@dataclass(frozen=True, slots=True)
class EvidenceTextResult:
    evidence_id: int
    evidence_type: EvidenceType
    integrity_status: EvidenceIntegrityStatus
    text: str | None
    preview: str
    warning: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceIntegrityResult:
    evidence_id: int
    evidence_type: EvidenceType
    integrity_status: EvidenceIntegrityStatus
    detail: str = ""


def build_evidence_deep_link(
    *,
    book_id: int,
    source_chapter_id: int | None,
    source_scene_id: int | None,
    stable_paragraph_id: str | None,
    book_snapshot_id: int,
    paragraph_content_hash: str,
    integrity_status: EvidenceIntegrityStatus,
) -> str:
    """Build query-string deep link. Hash mismatch links stay marked, never silent."""
    params: list[str] = []
    if source_chapter_id is not None:
        params.append(f"chapter={int(source_chapter_id)}")
    if source_scene_id is not None:
        params.append(f"scene={int(source_scene_id)}")
    if stable_paragraph_id:
        params.append(f"paragraph={stable_paragraph_id}")
    params.append("view=reading")
    params.append(f"bookSnapshotId={int(book_snapshot_id)}")
    params.append(f"paragraphContentHash={paragraph_content_hash}")
    params.append(f"integrityStatus={integrity_status.value}")
    if integrity_status == EvidenceIntegrityStatus.HASH_MISMATCH:
        params.append("locateBlocked=1")
    return f"/books/{int(book_id)}?{'&'.join(params)}"


def _clip_preview(text: str) -> str:
    if len(text) <= MAX_PARAGRAPH_PREVIEW_CHARS:
        return text
    return text[: MAX_PARAGRAPH_PREVIEW_CHARS - 1] + "…"


class EvidenceReadService:
    """Read-only Evidence adapter for Asset and Relation evidence."""

    def __init__(
        self,
        session: Session,
        *,
        snapshot_service: BookSnapshotServiceImpl | None = None,
    ) -> None:
        self._session = session
        self._snapshots = snapshot_service or BookSnapshotServiceImpl(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_evidence_ref(
        self,
        evidence_id: int,
        *,
        evidence_type: EvidenceType,
    ) -> WholeBookEvidenceRefDto:
        row, etype, book_id = self._load_evidence(evidence_id, evidence_type)
        integrity = self.validate_evidence_integrity(evidence_id, evidence_type=etype)
        chapter_title, source_chapter_id, stable_paragraph_id = self._chapter_meta(row)
        preview = ""
        if integrity.integrity_status not in {
            EvidenceIntegrityStatus.MISSING,
            EvidenceIntegrityStatus.INACCESSIBLE,
        }:
            preview_result = self.get_evidence_preview(
                evidence_id, evidence_type=etype
            )
            preview = preview_result.preview
        deep_link = build_evidence_deep_link(
            book_id=book_id,
            source_chapter_id=source_chapter_id,
            source_scene_id=row.source_scene_id,
            stable_paragraph_id=stable_paragraph_id,
            book_snapshot_id=int(row.book_snapshot_id),
            paragraph_content_hash=str(row.paragraph_content_hash),
            integrity_status=integrity.integrity_status,
        )
        role = row.evidence_role
        if isinstance(role, EvidenceRole):
            evidence_role = role
        else:
            evidence_role = EvidenceRole(str(role))
        return WholeBookEvidenceRefDto(
            evidence_id=int(row.id),
            evidence_type=etype,
            book_snapshot_id=int(row.book_snapshot_id),
            snapshot_chapter_id=int(row.snapshot_chapter_id)
            if row.snapshot_chapter_id is not None
            else None,
            snapshot_paragraph_id=int(row.snapshot_paragraph_id)
            if row.snapshot_paragraph_id is not None
            else None,
            source_chapter_id=source_chapter_id,
            source_scene_id=int(row.source_scene_id)
            if row.source_scene_id is not None
            else None,
            stable_paragraph_id=stable_paragraph_id,
            paragraph_content_hash=str(row.paragraph_content_hash),
            start_offset=int(row.start_offset),
            end_offset=int(row.end_offset),
            evidence_role=evidence_role,
            evidence_label=str(row.evidence_label or ""),
            chapter_title=chapter_title,
            paragraph_preview=preview,
            deep_link=deep_link,
            integrity_status=integrity.integrity_status,
        )

    def get_evidence_preview(
        self,
        evidence_id: int,
        *,
        evidence_type: EvidenceType,
    ) -> EvidenceTextResult:
        text_result = self.get_evidence_text(
            evidence_id, evidence_type=evidence_type, include_full=False
        )
        return text_result

    def get_evidence_text(
        self,
        evidence_id: int,
        *,
        evidence_type: EvidenceType,
        include_full: bool = True,
    ) -> EvidenceTextResult:
        """On-demand Snapshot body read. Full text is not retained on DTO."""
        row, etype, _book_id = self._load_evidence(evidence_id, evidence_type)
        integrity = self.validate_evidence_integrity(evidence_id, evidence_type=etype)
        status = integrity.integrity_status
        if status in {
            EvidenceIntegrityStatus.MISSING,
            EvidenceIntegrityStatus.INACCESSIBLE,
        }:
            return EvidenceTextResult(
                evidence_id=int(row.id),
                evidence_type=etype,
                integrity_status=status,
                text=None,
                preview="",
                warning=integrity.detail or status.value,
            )

        try:
            paragraph_text = self._snapshots.get_snapshot_paragraph_text(
                int(row.snapshot_paragraph_id)
            )
        except Exception as exc:  # noqa: BLE001 — map to integrity status
            return EvidenceTextResult(
                evidence_id=int(row.id),
                evidence_type=etype,
                integrity_status=EvidenceIntegrityStatus.INACCESSIBLE,
                text=None,
                preview="",
                warning=str(exc),
            )

        start = int(row.start_offset)
        end = int(row.end_offset)
        warning: str | None = None
        if start < 0 or end < start or end > len(paragraph_text):
            status = EvidenceIntegrityStatus.STALE
            warning = f"offset [{start},{end}) out of paragraph length {len(paragraph_text)}"
            excerpt = ""
        else:
            excerpt = paragraph_text[start:end]

        preview = _clip_preview(excerpt)
        full = excerpt if include_full else None
        if status == EvidenceIntegrityStatus.HASH_MISMATCH:
            warning = warning or "paragraph_content_hash mismatch — do not silent-locate"
        return EvidenceTextResult(
            evidence_id=int(row.id),
            evidence_type=etype,
            integrity_status=status,
            text=full,
            preview=preview,
            warning=warning,
        )

    def validate_evidence_integrity(
        self,
        evidence_id: int,
        *,
        evidence_type: EvidenceType,
    ) -> EvidenceIntegrityResult:
        row, etype, book_id = self._load_evidence(evidence_id, evidence_type)

        snapshot = self._session.get(BookSnapshot, int(row.book_snapshot_id))
        if snapshot is None:
            return EvidenceIntegrityResult(
                evidence_id=int(row.id),
                evidence_type=etype,
                integrity_status=EvidenceIntegrityStatus.MISSING,
                detail="book_snapshot not found",
            )
        if int(snapshot.book_id) != int(book_id):
            return EvidenceIntegrityResult(
                evidence_id=int(row.id),
                evidence_type=etype,
                integrity_status=EvidenceIntegrityStatus.INACCESSIBLE,
                detail="snapshot book mismatch",
            )
        if snapshot.snapshot_status != SnapshotStatus.COMPLETED.value:
            return EvidenceIntegrityResult(
                evidence_id=int(row.id),
                evidence_type=etype,
                integrity_status=EvidenceIntegrityStatus.INACCESSIBLE,
                detail=f"snapshot status={snapshot.snapshot_status}",
            )

        paragraph = self._session.get(
            BookSnapshotParagraph, int(row.snapshot_paragraph_id)
        )
        if paragraph is None:
            return EvidenceIntegrityResult(
                evidence_id=int(row.id),
                evidence_type=etype,
                integrity_status=EvidenceIntegrityStatus.MISSING,
                detail="snapshot paragraph missing",
            )
        if int(paragraph.snapshot_id) != int(row.book_snapshot_id):
            return EvidenceIntegrityResult(
                evidence_id=int(row.id),
                evidence_type=etype,
                integrity_status=EvidenceIntegrityStatus.MISSING,
                detail="paragraph does not belong to evidence snapshot",
            )

        chapter = self._session.get(BookSnapshotChapter, int(row.snapshot_chapter_id))
        if chapter is None or int(chapter.snapshot_id) != int(row.book_snapshot_id):
            return EvidenceIntegrityResult(
                evidence_id=int(row.id),
                evidence_type=etype,
                integrity_status=EvidenceIntegrityStatus.MISSING,
                detail="snapshot chapter missing",
            )

        # Hash vs snapshot paragraph (Evidence source of truth).
        if str(paragraph.content_hash) != str(row.paragraph_content_hash):
            return EvidenceIntegrityResult(
                evidence_id=int(row.id),
                evidence_type=etype,
                integrity_status=EvidenceIntegrityStatus.HASH_MISMATCH,
                detail="stored paragraph_content_hash != snapshot paragraph.content_hash",
            )

        try:
            restored = self._snapshots.get_snapshot_paragraph_text(int(paragraph.id))
        except Exception as exc:  # noqa: BLE001
            return EvidenceIntegrityResult(
                evidence_id=int(row.id),
                evidence_type=etype,
                integrity_status=EvidenceIntegrityStatus.INACCESSIBLE,
                detail=str(exc),
            )

        restored_hash = calculate_text_hash(restored)
        if restored_hash != str(row.paragraph_content_hash):
            return EvidenceIntegrityResult(
                evidence_id=int(row.id),
                evidence_type=etype,
                integrity_status=EvidenceIntegrityStatus.HASH_MISMATCH,
                detail="restored snapshot text hash mismatch",
            )

        start = int(row.start_offset)
        end = int(row.end_offset)
        if start < 0 or end < start or end > len(restored):
            return EvidenceIntegrityResult(
                evidence_id=int(row.id),
                evidence_type=etype,
                integrity_status=EvidenceIntegrityStatus.STALE,
                detail=f"offset [{start},{end}) out of range len={len(restored)}",
            )

        return EvidenceIntegrityResult(
            evidence_id=int(row.id),
            evidence_type=etype,
            integrity_status=EvidenceIntegrityStatus.VALID,
            detail="ok",
        )

    def build_evidence_deep_link(
        self,
        evidence_id: int,
        *,
        evidence_type: EvidenceType,
    ) -> str:
        ref = self.get_evidence_ref(evidence_id, evidence_type=evidence_type)
        return ref.deep_link

    def list_asset_version_evidence_refs(
        self, asset_version_id: int
    ) -> list[WholeBookEvidenceRefDto]:
        rows = (
            self._session.query(NarrativeAssetEvidence)
            .filter(NarrativeAssetEvidence.asset_version_id == asset_version_id)
            .order_by(NarrativeAssetEvidence.id.asc())
            .all()
        )
        return [
            self.get_evidence_ref(int(r.id), evidence_type="asset_evidence") for r in rows
        ]

    def list_relation_version_evidence_refs(
        self, relation_version_id: int
    ) -> list[WholeBookEvidenceRefDto]:
        rows = (
            self._session.query(NarrativeRelationEvidence)
            .filter(
                NarrativeRelationEvidence.relation_version_id == relation_version_id
            )
            .order_by(NarrativeRelationEvidence.id.asc())
            .all()
        )
        return [
            self.get_evidence_ref(int(r.id), evidence_type="relation_evidence")
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_evidence(
        self,
        evidence_id: int,
        evidence_type: EvidenceType,
    ) -> tuple[
        NarrativeAssetEvidence | NarrativeRelationEvidence,
        EvidenceType,
        int,
    ]:
        if evidence_type == "asset_evidence":
            row = self._session.get(NarrativeAssetEvidence, int(evidence_id))
            if row is None:
                raise LookupError(f"asset evidence not found: {evidence_id}")
            version = self._session.get(NarrativeAssetVersion, row.asset_version_id)
            if version is None:
                raise LookupError(f"asset version missing for evidence {evidence_id}")
            asset = self._session.get(NarrativeAsset, version.asset_id)
            if asset is None:
                raise LookupError(f"asset missing for evidence {evidence_id}")
            return row, "asset_evidence", int(asset.book_id)

        row = self._session.get(NarrativeRelationEvidence, int(evidence_id))
        if row is None:
            raise LookupError(f"relation evidence not found: {evidence_id}")
        version = self._session.get(NarrativeRelationVersion, row.relation_version_id)
        if version is None:
            raise LookupError(f"relation version missing for evidence {evidence_id}")
        relation = self._session.get(NarrativeRelation, version.relation_id)
        if relation is None:
            raise LookupError(f"relation missing for evidence {evidence_id}")
        return row, "relation_evidence", int(relation.book_id)

    def _chapter_meta(
        self,
        row: NarrativeAssetEvidence | NarrativeRelationEvidence,
    ) -> tuple[str, int | None, str | None]:
        chapter = self._session.get(BookSnapshotChapter, int(row.snapshot_chapter_id))
        paragraph = self._session.get(
            BookSnapshotParagraph, int(row.snapshot_paragraph_id)
        )
        title = ""
        source_chapter_id: int | None = None
        if chapter is not None:
            title = str(chapter.title or "")
            source_chapter_id = (
                int(chapter.source_chapter_id)
                if chapter.source_chapter_id is not None
                else None
            )
        stable: str | None = None
        if paragraph is not None:
            stable = str(paragraph.stable_paragraph_id)
        return title, source_chapter_id, stable
