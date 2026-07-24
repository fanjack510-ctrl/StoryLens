"""Evidence Candidate builder and Coverage calculator (Agent Q / CHG-038).

No model calls. No automatic novel understanding. Candidates only from explicit
Snapshot paragraph/offset inputs, fake module output refs, or fixture matches.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.narrative_core.enums import EvidenceRole, WholeBookModuleKey
from app.narrative_core.hash_canon import calculate_text_hash
from app.narrative_core.private_engine_contract.evidence import (
    MAX_EVIDENCE_PREVIEW_CHARS,
    EvidenceCandidate,
    EvidenceCoverageReport,
    build_coverage_report,
)


EVIDENCE_POLICY_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class EvidencePolicy:
    """Versioned generic evidence policy — not per-book thresholds."""

    policy_key: str
    policy_version: str
    min_coverage_ratio: float
    min_critical_coverage_ratio: float
    critical_claim_keys: frozenset[str] = field(default_factory=frozenset)
    require_support_for_acceptance: bool = True

    def __post_init__(self) -> None:
        if not self.policy_key.strip() or not self.policy_version.strip():
            raise ValueError("policy_key and policy_version required")
        if not (0.0 <= self.min_coverage_ratio <= 1.0):
            raise ValueError("min_coverage_ratio must be in [0,1]")
        if not (0.0 <= self.min_critical_coverage_ratio <= 1.0):
            raise ValueError("min_critical_coverage_ratio must be in [0,1]")


DEFAULT_EVIDENCE_POLICIES: dict[str, EvidencePolicy] = {
    "evidence.minimal": EvidencePolicy(
        policy_key="evidence.minimal",
        policy_version=EVIDENCE_POLICY_VERSION,
        min_coverage_ratio=0.5,
        min_critical_coverage_ratio=1.0,
        critical_claim_keys=frozenset(),
        require_support_for_acceptance=True,
    ),
    "evidence.standard": EvidencePolicy(
        policy_key="evidence.standard",
        policy_version=EVIDENCE_POLICY_VERSION,
        min_coverage_ratio=0.75,
        min_critical_coverage_ratio=1.0,
        critical_claim_keys=frozenset({"logline", "turning_point", "primary_storyline"}),
        require_support_for_acceptance=True,
    ),
    "evidence.strict": EvidencePolicy(
        policy_key="evidence.strict",
        policy_version=EVIDENCE_POLICY_VERSION,
        min_coverage_ratio=0.9,
        min_critical_coverage_ratio=1.0,
        critical_claim_keys=frozenset(
            {"logline", "turning_point", "primary_storyline", "stage_boundary"}
        ),
        require_support_for_acceptance=True,
    ),
}


def get_evidence_policy(policy_key: str) -> EvidencePolicy:
    if policy_key not in DEFAULT_EVIDENCE_POLICIES:
        # Unknown keys still versioned via standard defaults (generic, not book-specific).
        return EvidencePolicy(
            policy_key=policy_key,
            policy_version=EVIDENCE_POLICY_VERSION,
            min_coverage_ratio=0.75,
            min_critical_coverage_ratio=1.0,
            critical_claim_keys=frozenset({"logline"}),
            require_support_for_acceptance=True,
        )
    return DEFAULT_EVIDENCE_POLICIES[policy_key]


@dataclass(frozen=True, slots=True)
class ExplicitParagraphEvidenceInput:
    book_id: int
    book_snapshot_id: int
    snapshot_chapter_id: int
    snapshot_paragraph_id: int
    stable_paragraph_id: str
    paragraph_content_hash: str
    start_offset: int
    end_offset: int
    evidence_role: EvidenceRole | str
    target_module_key: WholeBookModuleKey | str
    target_output_ref: str
    extraction_method: str = "explicit_offset"
    confidence: float | None = None
    source_context_unit_id: str | None = None
    preview: str = ""
    from_derived_summary: bool = False


@dataclass(frozen=True, slots=True)
class FakeModuleOutputEvidenceRef:
    """Evidence ref emitted by Fake Module Output — not model inference."""

    book_id: int
    book_snapshot_id: int
    snapshot_chapter_id: int
    snapshot_paragraph_id: int
    stable_paragraph_id: str
    paragraph_content_hash: str
    start_offset: int
    end_offset: int
    evidence_role: EvidenceRole | str
    target_module_key: WholeBookModuleKey | str
    target_output_ref: str
    preview: str = ""
    source_context_unit_id: str | None = None


@dataclass(frozen=True, slots=True)
class FixtureExactMatchEvidenceInput:
    """Test fixture exact match — not novel understanding."""

    book_id: int
    book_snapshot_id: int
    snapshot_chapter_id: int
    snapshot_paragraph_id: int
    stable_paragraph_id: str
    paragraph_content_hash: str
    matched_text: str
    paragraph_text: str
    evidence_role: EvidenceRole | str
    target_module_key: WholeBookModuleKey | str
    target_output_ref: str
    source_context_unit_id: str | None = None


def _role(value: EvidenceRole | str) -> EvidenceRole:
    return value if isinstance(value, EvidenceRole) else EvidenceRole(str(value))


def _preview(text: str) -> str:
    cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(cleaned) <= MAX_EVIDENCE_PREVIEW_CHARS:
        return cleaned
    return cleaned[: MAX_EVIDENCE_PREVIEW_CHARS - 1] + "…"


def make_candidate_id(
    *,
    book_snapshot_id: int,
    snapshot_paragraph_id: int,
    start_offset: int,
    end_offset: int,
    evidence_role: str,
    target_module_key: str,
    target_output_ref: str,
    paragraph_content_hash: str,
) -> str:
    payload = "|".join(
        (
            str(book_snapshot_id),
            str(snapshot_paragraph_id),
            str(start_offset),
            str(end_offset),
            evidence_role,
            target_module_key,
            target_output_ref,
            paragraph_content_hash,
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"evc:{book_snapshot_id}:{digest}"


class EvidenceCandidateBuilder:
    """Build EvidenceCandidate from explicit inputs only — no model selection."""

    def __init__(self, *, private_selection_hook: Any | None = None) -> None:
        # Thin hook only — proprietary evidence selection stays in private package.
        self._private_selection_hook = private_selection_hook

    def set_private_selection_hook(self, hook: Any | None) -> None:
        self._private_selection_hook = hook

    def apply_private_selection(
        self,
        candidates: Sequence[EvidenceCandidate],
        *,
        module_key: str | WholeBookModuleKey | None = None,
    ) -> tuple[EvidenceCandidate, ...]:
        """Optional private ranking/filter; never invents paragraph offsets."""

        hook = self._private_selection_hook
        if hook is None:
            return tuple(candidates)
        if hasattr(hook, "select_evidence"):
            selected = hook.select_evidence(
                candidates=tuple(candidates), module_key=module_key
            )
            if selected is not None:
                return tuple(selected)
        return tuple(candidates)

    def from_explicit_paragraph(
        self, inp: ExplicitParagraphEvidenceInput
    ) -> EvidenceCandidate:
        if inp.from_derived_summary:
            # Still construct so Validator can reject as final source evidence.
            pass
        role = _role(inp.evidence_role)
        module_key = (
            inp.target_module_key.value
            if isinstance(inp.target_module_key, WholeBookModuleKey)
            else str(inp.target_module_key)
        )
        candidate_id = make_candidate_id(
            book_snapshot_id=inp.book_snapshot_id,
            snapshot_paragraph_id=inp.snapshot_paragraph_id,
            start_offset=inp.start_offset,
            end_offset=inp.end_offset,
            evidence_role=role.value,
            target_module_key=module_key,
            target_output_ref=inp.target_output_ref,
            paragraph_content_hash=inp.paragraph_content_hash,
        )
        return EvidenceCandidate(
            candidate_id=candidate_id,
            book_snapshot_id=inp.book_snapshot_id,
            snapshot_chapter_id=inp.snapshot_chapter_id,
            snapshot_paragraph_id=inp.snapshot_paragraph_id,
            stable_paragraph_id=inp.stable_paragraph_id,
            paragraph_content_hash=inp.paragraph_content_hash,
            start_offset=inp.start_offset,
            end_offset=inp.end_offset,
            evidence_role=role,
            target_module_key=inp.target_module_key,
            target_output_ref=inp.target_output_ref,
            extraction_method=inp.extraction_method,
            confidence=inp.confidence,
            source_context_unit_id=inp.source_context_unit_id,
            book_id=inp.book_id,
            preview=_preview(inp.preview),
            from_derived_summary=inp.from_derived_summary,
        )

    def from_fake_module_output(
        self, ref: FakeModuleOutputEvidenceRef
    ) -> EvidenceCandidate:
        return self.from_explicit_paragraph(
            ExplicitParagraphEvidenceInput(
                book_id=ref.book_id,
                book_snapshot_id=ref.book_snapshot_id,
                snapshot_chapter_id=ref.snapshot_chapter_id,
                snapshot_paragraph_id=ref.snapshot_paragraph_id,
                stable_paragraph_id=ref.stable_paragraph_id,
                paragraph_content_hash=ref.paragraph_content_hash,
                start_offset=ref.start_offset,
                end_offset=ref.end_offset,
                evidence_role=ref.evidence_role,
                target_module_key=ref.target_module_key,
                target_output_ref=ref.target_output_ref,
                extraction_method="fake_module_output_ref",
                source_context_unit_id=ref.source_context_unit_id,
                preview=ref.preview,
                from_derived_summary=False,
            )
        )

    def from_fixture_exact_match(
        self, inp: FixtureExactMatchEvidenceInput
    ) -> EvidenceCandidate:
        idx = inp.paragraph_text.find(inp.matched_text)
        if idx < 0:
            raise ValueError("fixture matched_text not found in paragraph_text")
        start = idx
        end = idx + len(inp.matched_text)
        return self.from_explicit_paragraph(
            ExplicitParagraphEvidenceInput(
                book_id=inp.book_id,
                book_snapshot_id=inp.book_snapshot_id,
                snapshot_chapter_id=inp.snapshot_chapter_id,
                snapshot_paragraph_id=inp.snapshot_paragraph_id,
                stable_paragraph_id=inp.stable_paragraph_id,
                paragraph_content_hash=inp.paragraph_content_hash,
                start_offset=start,
                end_offset=end,
                evidence_role=inp.evidence_role,
                target_module_key=inp.target_module_key,
                target_output_ref=inp.target_output_ref,
                extraction_method="fixture_exact_match",
                source_context_unit_id=inp.source_context_unit_id,
                preview=inp.matched_text,
                from_derived_summary=False,
            )
        )


@dataclass(frozen=True, slots=True)
class ClaimEvidenceBinding:
    claim_key: str
    critical: bool = False
    support_candidate_ids: tuple[str, ...] = ()
    contradict_candidate_ids: tuple[str, ...] = ()
    context_candidate_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WholeBookEvidenceCoverageReport:
    total_claims: int
    claims_with_support: int
    claims_with_contradiction: int
    claims_with_context: int
    unsupported_claims: tuple[str, ...]
    invalid_evidence: tuple[str, ...]
    duplicate_evidence: tuple[str, ...]
    coverage_ratio: float
    critical_coverage_ratio: float
    accepted: bool
    policy_key: str
    policy_version: str
    module_key: str
    contradictory_claim_keys: tuple[str, ...] = ()
    explanation: str = ""

    def to_contract_report(self) -> EvidenceCoverageReport:
        return build_coverage_report(
            module_key=self.module_key,
            required_claims=self.total_claims,
            evidenced_claims=self.claims_with_support,
            missing_target_refs=self.unsupported_claims,
        )


class EvidenceCoverageCalculator:
    """Coverage ≠ quality score. Thresholds from versioned EvidencePolicy only."""

    def calculate(
        self,
        *,
        module_key: str,
        claims: Sequence[ClaimEvidenceBinding],
        policy: EvidencePolicy,
        invalid_candidate_ids: Sequence[str] = (),
        duplicate_candidate_ids: Sequence[str] = (),
    ) -> WholeBookEvidenceCoverageReport:
        total = len(claims)
        with_support = 0
        with_contradict = 0
        with_context = 0
        unsupported: list[str] = []
        contradictory: list[str] = []
        critical_total = 0
        critical_supported = 0

        for claim in claims:
            has_support = bool(claim.support_candidate_ids)
            has_contradict = bool(claim.contradict_candidate_ids)
            has_context = bool(claim.context_candidate_ids)
            if has_support:
                with_support += 1
            if has_contradict:
                with_contradict += 1
                contradictory.append(claim.claim_key)
            if has_context:
                with_context += 1
            if not has_support:
                unsupported.append(claim.claim_key)
            is_critical = claim.critical or claim.claim_key in policy.critical_claim_keys
            if is_critical:
                critical_total += 1
                if has_support:
                    critical_supported += 1

        coverage_ratio = (with_support / total) if total else 1.0
        critical_ratio = (
            (critical_supported / critical_total) if critical_total else 1.0
        )

        accepted = True
        if policy.require_support_for_acceptance and unsupported:
            # Critical unsupported blocks acceptance.
            critical_unsupported = [
                c.claim_key
                for c in claims
                if (c.critical or c.claim_key in policy.critical_claim_keys)
                and not c.support_candidate_ids
            ]
            if critical_unsupported:
                accepted = False
        if coverage_ratio < policy.min_coverage_ratio:
            accepted = False
        if critical_ratio < policy.min_critical_coverage_ratio:
            accepted = False

        explanation = (
            f"policy={policy.policy_key}@{policy.policy_version}; "
            f"support={with_support}/{total}; "
            f"critical={critical_supported}/{critical_total}; "
            f"contradict={len(contradictory)}; "
            f"invalid={len(invalid_candidate_ids)}; "
            f"duplicate={len(duplicate_candidate_ids)}; "
            f"accepted={accepted}"
        )

        return WholeBookEvidenceCoverageReport(
            total_claims=total,
            claims_with_support=with_support,
            claims_with_contradiction=with_contradict,
            claims_with_context=with_context,
            unsupported_claims=tuple(unsupported),
            invalid_evidence=tuple(invalid_candidate_ids),
            duplicate_evidence=tuple(duplicate_candidate_ids),
            coverage_ratio=coverage_ratio,
            critical_coverage_ratio=critical_ratio,
            accepted=accepted,
            policy_key=policy.policy_key,
            policy_version=policy.policy_version,
            module_key=module_key,
            contradictory_claim_keys=tuple(contradictory),
            explanation=explanation,
        )


def candidate_fingerprint(candidate: EvidenceCandidate) -> str:
    """Structural fingerprint for duplicate detection (not preview text)."""
    payload = {
        "book_snapshot_id": candidate.book_snapshot_id,
        "snapshot_paragraph_id": candidate.snapshot_paragraph_id,
        "start_offset": candidate.start_offset,
        "end_offset": candidate.end_offset,
        "role": candidate.evidence_role.value
        if isinstance(candidate.evidence_role, EvidenceRole)
        else str(candidate.evidence_role),
        "target_module_key": str(candidate.target_module_key),
        "target_output_ref": candidate.target_output_ref,
        "paragraph_content_hash": candidate.paragraph_content_hash,
    }
    return calculate_text_hash(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def find_duplicate_candidate_ids(
    candidates: Sequence[EvidenceCandidate],
) -> tuple[str, ...]:
    seen: dict[str, str] = {}
    dupes: list[str] = []
    for candidate in candidates:
        fp = candidate_fingerprint(candidate)
        if fp in seen:
            dupes.append(candidate.candidate_id)
        else:
            seen[fp] = candidate.candidate_id
    return tuple(dupes)
