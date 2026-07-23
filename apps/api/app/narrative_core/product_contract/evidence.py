"""Evidence reference DTO for whole-book UI (Phase 1D-P).

Preview is short only; full body via Snapshot Reader. Drawer does not mutate DB.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.narrative_core.enums import EvidenceRole
from app.narrative_core.product_contract.enums import EvidenceIntegrityStatus

MAX_PARAGRAPH_PREVIEW_CHARS = 160


@dataclass(frozen=True, slots=True)
class WholeBookEvidenceRefDto:
    evidence_id: int | str
    evidence_type: str  # asset_evidence | relation_evidence
    book_snapshot_id: int
    snapshot_chapter_id: int | None
    snapshot_paragraph_id: int | None
    source_chapter_id: int | None
    source_scene_id: int | None
    stable_paragraph_id: str | None
    paragraph_content_hash: str
    start_offset: int | None
    end_offset: int | None
    evidence_role: EvidenceRole
    evidence_label: str
    chapter_title: str
    paragraph_preview: str
    deep_link: str
    integrity_status: EvidenceIntegrityStatus

    def __post_init__(self) -> None:
        if len(self.paragraph_preview) > MAX_PARAGRAPH_PREVIEW_CHARS:
            raise ValueError(
                f"paragraph_preview must be <= {MAX_PARAGRAPH_PREVIEW_CHARS} chars"
            )
