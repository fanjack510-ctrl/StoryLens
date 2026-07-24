"""Evidence candidate pipeline contracts (Phase 2B-P).

Validator does NOT call models or mutate assets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.narrative_core.enums import EvidenceRole, WholeBookModuleKey
from app.narrative_core.private_engine_contract.errors import PrivateEngineErrorCode

MAX_EVIDENCE_PREVIEW_CHARS = 160


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    candidate_id: str
    book_snapshot_id: int
    snapshot_chapter_id: int | None
    snapshot_paragraph_id: int | None
    stable_paragraph_id: str | None
    paragraph_content_hash: str
    start_offset: int | None
    end_offset: int | None
    evidence_role: EvidenceRole
    target_module_key: WholeBookModuleKey | str
    target_output_ref: str
    extraction_method: str
    confidence: float | None
    source_context_unit_id: str | None
    book_id: int | None = None
    preview: str = ""
    from_derived_summary: bool = False
    # Provider DTO alias before Public canonicalization (audit only; never a gate).
    provider_output_ref: str | None = None

    def __post_init__(self) -> None:
        if self.evidence_role not in (
            EvidenceRole.SUPPORT,
            EvidenceRole.CONTRADICT,
            EvidenceRole.CONTEXT,
        ):
            raise ValueError("evidence_role must be support/contradict/context")
        if len(self.preview) > MAX_EVIDENCE_PREVIEW_CHARS:
            raise ValueError(f"preview must be <= {MAX_EVIDENCE_PREVIEW_CHARS} chars")
        if self.start_offset is not None and self.end_offset is not None:
            if self.start_offset < 0 or self.end_offset < self.start_offset:
                raise ValueError("invalid evidence offsets")


@dataclass(frozen=True, slots=True)
class EvidenceSelectionResult:
    selected: tuple[EvidenceCandidate, ...]
    rejected: tuple[EvidenceCandidate, ...]
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceValidationIssue:
    code: str
    candidate_id: str | None
    message: str


@dataclass(frozen=True, slots=True)
class EvidenceValidationReport:
    valid: bool
    issues: tuple[EvidenceValidationIssue, ...]
    checked_candidate_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceCoverageReport:
    module_key: str
    required_claims: int
    evidenced_claims: int
    coverage_ratio: float
    incomplete: bool
    missing_target_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceValidationContext:
    """Snapshot facts for validation — no ORM mutation, no model calls."""

    book_id: int
    book_snapshot_id: int
    paragraph_hashes: Mapping[int, str] = field(default_factory=dict)
    chapter_ids: frozenset[int] = field(default_factory=frozenset)
    paragraph_ids: frozenset[int] = field(default_factory=frozenset)
    known_output_refs: frozenset[str] = field(default_factory=frozenset)


def validate_evidence_candidate(
    candidate: EvidenceCandidate,
    ctx: EvidenceValidationContext,
) -> list[EvidenceValidationIssue]:
    issues: list[EvidenceValidationIssue] = []
    cid = candidate.candidate_id

    if candidate.book_snapshot_id != ctx.book_snapshot_id:
        issues.append(
            EvidenceValidationIssue(
                code=PrivateEngineErrorCode.MODULE_EVIDENCE_HASH_MISMATCH.value,
                candidate_id=cid,
                message="snapshot mismatch",
            )
        )
    if candidate.book_id is not None and candidate.book_id != ctx.book_id:
        issues.append(
            EvidenceValidationIssue(
                code="CROSS_BOOK_FORBIDDEN",
                candidate_id=cid,
                message="evidence must not cross books",
            )
        )
    if candidate.snapshot_chapter_id is not None and candidate.snapshot_chapter_id not in ctx.chapter_ids:
        if ctx.chapter_ids:
            issues.append(
                EvidenceValidationIssue(
                    code="CHAPTER_MISSING",
                    candidate_id=cid,
                    message="chapter not in snapshot",
                )
            )
    if candidate.snapshot_paragraph_id is not None:
        if ctx.paragraph_ids and candidate.snapshot_paragraph_id not in ctx.paragraph_ids:
            issues.append(
                EvidenceValidationIssue(
                    code="PARAGRAPH_MISSING",
                    candidate_id=cid,
                    message="paragraph not in snapshot",
                )
            )
        expected = ctx.paragraph_hashes.get(candidate.snapshot_paragraph_id)
        if expected is not None and expected != candidate.paragraph_content_hash:
            issues.append(
                EvidenceValidationIssue(
                    code=PrivateEngineErrorCode.MODULE_EVIDENCE_HASH_MISMATCH.value,
                    candidate_id=cid,
                    message="paragraph hash mismatch",
                )
            )
    if candidate.start_offset is not None and candidate.end_offset is not None:
        if candidate.start_offset < 0 or candidate.end_offset < candidate.start_offset:
            issues.append(
                EvidenceValidationIssue(
                    code="OFFSET_INVALID",
                    candidate_id=cid,
                    message="invalid offsets",
                )
            )
    if len(candidate.preview) > MAX_EVIDENCE_PREVIEW_CHARS:
        issues.append(
            EvidenceValidationIssue(
                code="PREVIEW_TOO_LONG",
                candidate_id=cid,
                message="preview too long",
            )
        )
    if candidate.target_output_ref and ctx.known_output_refs:
        if candidate.target_output_ref not in ctx.known_output_refs:
            issues.append(
                EvidenceValidationIssue(
                    code=PrivateEngineErrorCode.MODULE_OUTPUT_REFERENCE_INVALID.value,
                    candidate_id=cid,
                    message="target output missing",
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
    return issues


def validate_evidence_candidates(
    candidates: Sequence[EvidenceCandidate],
    ctx: EvidenceValidationContext,
) -> EvidenceValidationReport:
    all_issues: list[EvidenceValidationIssue] = []
    for candidate in candidates:
        all_issues.extend(validate_evidence_candidate(candidate, ctx))
    return EvidenceValidationReport(
        valid=not all_issues,
        issues=tuple(all_issues),
        checked_candidate_ids=tuple(c.candidate_id for c in candidates),
    )


def build_coverage_report(
    *,
    module_key: str,
    required_claims: int,
    evidenced_claims: int,
    missing_target_refs: Sequence[str] = (),
) -> EvidenceCoverageReport:
    if required_claims < 0 or evidenced_claims < 0:
        raise ValueError("claim counts must be >= 0")
    ratio = (evidenced_claims / required_claims) if required_claims else 1.0
    incomplete = evidenced_claims < required_claims
    return EvidenceCoverageReport(
        module_key=module_key,
        required_claims=required_claims,
        evidenced_claims=evidenced_claims,
        coverage_ratio=ratio,
        incomplete=incomplete,
        missing_target_refs=tuple(missing_target_refs),
    )


def fake_evidence_candidates(
    *,
    book_id: int = 1,
    book_snapshot_id: int = 1,
) -> tuple[EvidenceCandidate, ...]:
    return (
        EvidenceCandidate(
            candidate_id="ev-fake-1",
            book_snapshot_id=book_snapshot_id,
            snapshot_chapter_id=1,
            snapshot_paragraph_id=1,
            stable_paragraph_id="p1",
            paragraph_content_hash="fake-para-hash-1",
            start_offset=0,
            end_offset=10,
            evidence_role=EvidenceRole.SUPPORT,
            target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            target_output_ref="book_overview.logline",
            extraction_method="fake",
            confidence=0.5,
            source_context_unit_id="chapter:1",
            book_id=book_id,
            preview="合成短句。",
            from_derived_summary=False,
        ),
    )
