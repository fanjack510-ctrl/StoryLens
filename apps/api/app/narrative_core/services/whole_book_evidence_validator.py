"""Default Evidence Validator (Agent Q / CHG-038).

Does not call models, write database, mutate assets, or auto-canonical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from sqlalchemy.orm import Session

from app.db.models import BookSnapshotChapter, BookSnapshotParagraph
from app.narrative_core.enums import EvidenceRole
from app.narrative_core.private_engine_contract.evidence import (
    MAX_EVIDENCE_PREVIEW_CHARS,
    EvidenceCandidate,
    EvidenceValidationContext,
    EvidenceValidationIssue,
    EvidenceValidationReport,
    validate_evidence_candidate,
)
from app.narrative_core.private_engine_contract.errors import PrivateEngineErrorCode
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_evidence_pipeline import (
    find_duplicate_candidate_ids,
)


@dataclass(frozen=True, slots=True)
class EvidenceValidatorSnapshotView:
    """Read-only snapshot facts for validation."""

    book_id: int
    book_snapshot_id: int
    chapter_ids: frozenset[int]
    paragraph_ids: frozenset[int]
    paragraph_hashes: Mapping[int, str]
    stable_paragraph_ids: Mapping[int, str]
    paragraph_chapter: Mapping[int, int]
    paragraph_lengths: Mapping[int, int]
    known_output_refs: frozenset[str] = field(default_factory=frozenset)
    known_context_unit_ids: frozenset[str] = field(default_factory=frozenset)


class DefaultEvidenceValidator:
    """Validate EvidenceCandidate against Snapshot facts."""

    def __init__(
        self,
        session: Session | None = None,
        *,
        snapshot_service: BookSnapshotServiceImpl | None = None,
    ) -> None:
        self._session = session
        self._snapshots = snapshot_service
        if session is not None and snapshot_service is None:
            self._snapshots = BookSnapshotServiceImpl(session)

    def build_view_from_session(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        known_output_refs: Sequence[str] = (),
        known_context_unit_ids: Sequence[str] = (),
    ) -> EvidenceValidatorSnapshotView:
        if self._session is None or self._snapshots is None:
            raise RuntimeError("session required to build snapshot view")
        self._snapshots.validate_snapshot_for_book(book_snapshot_id, book_id)
        snapshot = self._snapshots.get_completed_snapshot(book_snapshot_id)
        chapter_ids: set[int] = set()
        paragraph_ids: set[int] = set()
        paragraph_hashes: dict[int, str] = {}
        stable_ids: dict[int, str] = {}
        paragraph_chapter: dict[int, int] = {}
        paragraph_lengths: dict[int, int] = {}
        for chapter in snapshot.chapters:
            chapter_ids.add(int(chapter.id))
            text_len = len(chapter.content_text or "")
            for para in chapter.paragraphs:
                pid = int(para.id)
                paragraph_ids.add(pid)
                paragraph_hashes[pid] = str(para.content_hash)
                stable_ids[pid] = str(para.stable_paragraph_id)
                paragraph_chapter[pid] = int(chapter.id)
                # Length via offsets within chapter body.
                start = int(para.start_offset)
                end = int(para.end_offset)
                paragraph_lengths[pid] = max(0, end - start)
                _ = text_len
        return EvidenceValidatorSnapshotView(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            chapter_ids=frozenset(chapter_ids),
            paragraph_ids=frozenset(paragraph_ids),
            paragraph_hashes=paragraph_hashes,
            stable_paragraph_ids=stable_ids,
            paragraph_chapter=paragraph_chapter,
            paragraph_lengths=paragraph_lengths,
            known_output_refs=frozenset(known_output_refs),
            known_context_unit_ids=frozenset(known_context_unit_ids),
        )

    def validate(
        self,
        candidates: Sequence[EvidenceCandidate],
        view: EvidenceValidatorSnapshotView,
    ) -> EvidenceValidationReport:
        issues: list[EvidenceValidationIssue] = []
        contract_ctx = EvidenceValidationContext(
            book_id=view.book_id,
            book_snapshot_id=view.book_snapshot_id,
            paragraph_hashes=view.paragraph_hashes,
            chapter_ids=view.chapter_ids,
            paragraph_ids=view.paragraph_ids,
            known_output_refs=view.known_output_refs,
        )

        for candidate in candidates:
            issues.extend(validate_evidence_candidate(candidate, contract_ctx))
            issues.extend(self._extra_checks(candidate, view))

        # Duplicates
        for dup_id in find_duplicate_candidate_ids(candidates):
            issues.append(
                EvidenceValidationIssue(
                    code=PrivateEngineErrorCode.MODULE_OUTPUT_DUPLICATE.value,
                    candidate_id=dup_id,
                    message="duplicate evidence fingerprint",
                )
            )

        return EvidenceValidationReport(
            valid=not issues,
            issues=tuple(issues),
            checked_candidate_ids=tuple(c.candidate_id for c in candidates),
        )

    def _extra_checks(
        self,
        candidate: EvidenceCandidate,
        view: EvidenceValidatorSnapshotView,
    ) -> list[EvidenceValidationIssue]:
        issues: list[EvidenceValidationIssue] = []
        cid = candidate.candidate_id

        if candidate.book_id is not None and candidate.book_id != view.book_id:
            issues.append(
                EvidenceValidationIssue(
                    code="CROSS_BOOK_FORBIDDEN",
                    candidate_id=cid,
                    message="evidence must not cross books",
                )
            )
        if candidate.book_snapshot_id != view.book_snapshot_id:
            issues.append(
                EvidenceValidationIssue(
                    code="CROSS_SNAPSHOT_FORBIDDEN",
                    candidate_id=cid,
                    message="evidence must not cross snapshots",
                )
            )

        pid = candidate.snapshot_paragraph_id
        if pid is not None:
            if pid not in view.paragraph_ids:
                issues.append(
                    EvidenceValidationIssue(
                        code="PARAGRAPH_MISSING",
                        candidate_id=cid,
                        message="paragraph not in snapshot",
                    )
                )
            else:
                expected_stable = view.stable_paragraph_ids.get(pid)
                if (
                    candidate.stable_paragraph_id
                    and expected_stable
                    and candidate.stable_paragraph_id != expected_stable
                ):
                    issues.append(
                        EvidenceValidationIssue(
                            code="STABLE_PARAGRAPH_ID_MISMATCH",
                            candidate_id=cid,
                            message="stable paragraph id mismatch",
                        )
                    )
                expected_chapter = view.paragraph_chapter.get(pid)
                if (
                    candidate.snapshot_chapter_id is not None
                    and expected_chapter is not None
                    and candidate.snapshot_chapter_id != expected_chapter
                ):
                    issues.append(
                        EvidenceValidationIssue(
                            code="CHAPTER_PARAGRAPH_MISMATCH",
                            candidate_id=cid,
                            message="paragraph not in declared chapter",
                        )
                    )
                expected_hash = view.paragraph_hashes.get(pid)
                if expected_hash is not None and expected_hash != candidate.paragraph_content_hash:
                    issues.append(
                        EvidenceValidationIssue(
                            code=PrivateEngineErrorCode.MODULE_EVIDENCE_HASH_MISMATCH.value,
                            candidate_id=cid,
                            message="paragraph hash mismatch",
                        )
                    )
                para_len = view.paragraph_lengths.get(pid)
                if (
                    para_len is not None
                    and candidate.start_offset is not None
                    and candidate.end_offset is not None
                ):
                    if candidate.start_offset < 0 or candidate.end_offset > para_len:
                        issues.append(
                            EvidenceValidationIssue(
                                code="OFFSET_OUT_OF_RANGE",
                                candidate_id=cid,
                                message="offset out of paragraph bounds",
                            )
                        )
                    if candidate.end_offset < candidate.start_offset:
                        issues.append(
                            EvidenceValidationIssue(
                                code="OFFSET_INVALID",
                                candidate_id=cid,
                                message="end_offset < start_offset",
                            )
                        )

        if candidate.evidence_role not in (
            EvidenceRole.SUPPORT,
            EvidenceRole.CONTRADICT,
            EvidenceRole.CONTEXT,
        ):
            issues.append(
                EvidenceValidationIssue(
                    code="ROLE_INVALID",
                    candidate_id=cid,
                    message="invalid evidence role",
                )
            )

        if not candidate.target_module_key:
            issues.append(
                EvidenceValidationIssue(
                    code="TARGET_MODULE_MISSING",
                    candidate_id=cid,
                    message="target module missing",
                )
            )
        if not candidate.target_output_ref:
            issues.append(
                EvidenceValidationIssue(
                    code=PrivateEngineErrorCode.MODULE_OUTPUT_REFERENCE_INVALID.value,
                    candidate_id=cid,
                    message="target output missing",
                )
            )
        elif view.known_output_refs and candidate.target_output_ref not in view.known_output_refs:
            issues.append(
                EvidenceValidationIssue(
                    code=PrivateEngineErrorCode.MODULE_OUTPUT_REFERENCE_INVALID.value,
                    candidate_id=cid,
                    message="target output not in known refs",
                )
            )

        if (
            candidate.source_context_unit_id
            and view.known_context_unit_ids
            and candidate.source_context_unit_id not in view.known_context_unit_ids
        ):
            issues.append(
                EvidenceValidationIssue(
                    code="CONTEXT_UNIT_MISSING",
                    candidate_id=cid,
                    message="source context unit missing",
                )
            )

        if candidate.from_derived_summary:
            issues.append(
                EvidenceValidationIssue(
                    code="DERIVED_SUMMARY_AS_FINAL_EVIDENCE",
                    candidate_id=cid,
                    message="derived summary cannot be final original-text evidence",
                )
            )

        if len(candidate.preview) > MAX_EVIDENCE_PREVIEW_CHARS:
            issues.append(
                EvidenceValidationIssue(
                    code="PREVIEW_TOO_LONG",
                    candidate_id=cid,
                    message="preview exceeds max chars",
                )
            )

        return issues

    def validate_single(
        self,
        candidate: EvidenceCandidate,
        view: EvidenceValidatorSnapshotView,
    ) -> EvidenceValidationReport:
        return self.validate((candidate,), view)


def load_paragraph_row(
    session: Session, snapshot_paragraph_id: int
) -> BookSnapshotParagraph | None:
    return session.get(BookSnapshotParagraph, snapshot_paragraph_id)


def load_chapter_row(
    session: Session, snapshot_chapter_id: int
) -> BookSnapshotChapter | None:
    return session.get(BookSnapshotChapter, snapshot_chapter_id)
