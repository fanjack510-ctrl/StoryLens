"""Evidence Validator runtime adapter (Phase 2B Integration / CHG-040).

Bridges Agent R EvidenceValidator Protocol (EvidenceValidationContext) to
Agent Q DefaultEvidenceValidator (EvidenceValidatorSnapshotView).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from app.narrative_core.private_engine_contract.evidence import (
    EvidenceCandidate,
    EvidenceValidationContext,
    EvidenceValidationReport,
)
from app.narrative_core.services.whole_book_evidence_validator import (
    DefaultEvidenceValidator,
    EvidenceValidatorSnapshotView,
)


@dataclass
class DefaultEvidenceValidatorRuntimeAdapter:
    """Satisfies Runner Protocol while delegating to Q DefaultEvidenceValidator."""

    validator: DefaultEvidenceValidator = field(default_factory=DefaultEvidenceValidator)
    snapshot_view: EvidenceValidatorSnapshotView | None = None
    views_by_snapshot: dict[int, EvidenceValidatorSnapshotView] = field(default_factory=dict)

    def register_view(self, view: EvidenceValidatorSnapshotView) -> None:
        self.views_by_snapshot[view.book_snapshot_id] = view
        self.snapshot_view = view

    def validate(
        self,
        candidates: Sequence[EvidenceCandidate],
        ctx: EvidenceValidationContext,
    ) -> EvidenceValidationReport:
        view = self._resolve_view(ctx)
        return self.validator.validate(tuple(candidates), view)

    def _resolve_view(self, ctx: EvidenceValidationContext) -> EvidenceValidatorSnapshotView:
        if ctx.book_snapshot_id in self.views_by_snapshot:
            base = self.views_by_snapshot[ctx.book_snapshot_id]
        elif self.snapshot_view is not None and self.snapshot_view.book_snapshot_id == ctx.book_snapshot_id:
            base = self.snapshot_view
        else:
            # Fixture/unit path: synthesize a view from the contract context only.
            base = EvidenceValidatorSnapshotView(
                book_id=ctx.book_id if ctx.book_id is not None else 0,
                book_snapshot_id=ctx.book_snapshot_id,
                chapter_ids=frozenset(ctx.chapter_ids or ()),
                paragraph_ids=frozenset(ctx.paragraph_ids or ()),
                paragraph_hashes=dict(ctx.paragraph_hashes or {}),
                stable_paragraph_ids={},
                paragraph_chapter={},
                paragraph_lengths={},
                known_output_refs=frozenset(ctx.known_output_refs or ()),
                known_context_unit_ids=frozenset(),
            )
        # Merge known output refs from the call context.
        known_outputs = frozenset(base.known_output_refs) | frozenset(ctx.known_output_refs or ())
        paragraph_hashes: Mapping[int, str] = dict(base.paragraph_hashes)
        if ctx.paragraph_hashes:
            paragraph_hashes = {**paragraph_hashes, **dict(ctx.paragraph_hashes)}
        return EvidenceValidatorSnapshotView(
            book_id=base.book_id,
            book_snapshot_id=base.book_snapshot_id,
            chapter_ids=frozenset(base.chapter_ids) | frozenset(ctx.chapter_ids or ()),
            paragraph_ids=frozenset(base.paragraph_ids) | frozenset(ctx.paragraph_ids or ()),
            paragraph_hashes=paragraph_hashes,
            stable_paragraph_ids=base.stable_paragraph_ids,
            paragraph_chapter=base.paragraph_chapter,
            paragraph_lengths=base.paragraph_lengths,
            known_output_refs=known_outputs,
            known_context_unit_ids=base.known_context_unit_ids,
        )


__all__ = ["DefaultEvidenceValidatorRuntimeAdapter"]
