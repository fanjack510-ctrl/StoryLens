"""``InvariantValidator`` — every invariant declared in ``01 §6``.

An invariant here is not a style rule. Each one is a property whose violation produces a
result that *looks* correct: an unresolvable reference, a claim with no support, a reused
asset that was never produced from the input it claims. None of those raise on their own,
which is why they are checked explicitly rather than trusted to surface.

Two design notes:

* Every check returns :class:`Violation` objects rather than raising, so a run can report
  *all* of what is wrong instead of the first thing. The caller decides what is fatal.
* ``INV-10`` is absent because it was deleted as vacuous — its content followed from INV-4
  and INV-5. The gap in the numbering is deliberate; renumbering would break every
  cross-reference in the frozen contracts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from app.narrative_core.long_novel.contracts.enums import RunPhase, Topic
from app.narrative_core.long_novel.errors import LongNovelError, LongNovelErrorCode

__all__ = ["Violation", "InvariantReport", "InvariantValidator", "NO_PROSE_COPY_MAX_RUN"]

#: Longest verbatim run of snapshot text an asset above L1 may contain. Above this it is a
#: copy, not a reference, and the traceability guarantee becomes a formality.
NO_PROSE_COPY_MAX_RUN = 120


@dataclass(frozen=True)
class Violation:
    invariant: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class InvariantReport:
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def add(self, invariant: str, message: str, **detail: Any) -> None:
        self.violations.append(Violation(invariant, message, detail))

    def raise_if_violated(self) -> None:
        if self.violations:
            first = self.violations[0]
            raise LongNovelError(
                LongNovelErrorCode.INVARIANT_VIOLATED,
                f"{first.invariant}: {first.message}"
                + (f" (and {len(self.violations) - 1} more)" if len(self.violations) > 1 else ""),
                detail={
                    "violations": [
                        {"invariant": v.invariant, "message": v.message, **v.detail}
                        for v in self.violations
                    ]
                },
            )


class InvariantValidator:
    """Stateless checks over in-memory structures.

    Deliberately not database-bound: the same checks must run against hand-built assets in
    unit tests and against loaded rows in an integration run, and a validator that can only
    see a database cannot be exercised before the pipeline exists.
    """

    # ---------------------------------------------------------------- INV-1
    def validate_reference_resolution(
        self, referenced_ids: Iterable[str], available_ids: Iterable[str], *, level: str
    ) -> InvariantReport:
        """Every ID an asset references exists at a lower level in the same run."""
        report = InvariantReport()
        available = set(available_ids)
        for ref in referenced_ids:
            if ref not in available:
                report.add("INV-1", f"{level} references {ref!r}, which resolves to nothing", ref=ref)
        return report

    # ---------------------------------------------------------------- INV-2
    def validate_write_phase(
        self, table: str, writer_phase: RunPhase, current_phase: RunPhase
    ) -> InvariantReport:
        """A component never writes a row owned by a lower level."""
        report = InvariantReport()
        if writer_phase is not current_phase:
            report.add(
                "INV-2",
                f"{table} may only be written in phase {writer_phase.value}, not {current_phase.value}",
                table=table,
            )
        return report

    # ---------------------------------------------------------------- INV-3
    def validate_block_immutability(
        self, before: Mapping[str, Any], after: Mapping[str, Any]
    ) -> InvariantReport:
        """Block rows are never UPDATEd except to set ``superseded_by_revision``.

        Facts and evidence hold foreign keys into a *specific* block revision and must still
        resolve against a superseded one during rebase, which is why blocks are insert-only
        while the derived views above them are replaced in place.
        """
        report = InvariantReport()
        for key, old in before.items():
            if key == "superseded_by_revision":
                continue
            if key in after and after[key] != old:
                report.add(
                    "INV-3",
                    f"block column {key!r} was mutated in place ({old!r} -> {after[key]!r}); "
                    "re-extraction must insert asset_revision + 1",
                    column=key,
                )
        return report

    # ---------------------------------------------------------------- INV-4
    def validate_chapter_coverage(
        self,
        snapshot_chapter_orders: Sequence[int],
        block_chapter_map: Mapping[str, Sequence[int]],
        part_counts: Mapping[int, int] | None = None,
    ) -> InvariantReport:
        """Every chapter is in exactly one block, or in exactly ``part_count`` blocks."""
        report = InvariantReport()
        seen: dict[int, int] = {}
        for chapters in block_chapter_map.values():
            for order in chapters:
                seen[order] = seen.get(order, 0) + 1
        parts = dict(part_counts or {})
        for order in snapshot_chapter_orders:
            count = seen.get(order, 0)
            expected = parts.get(order, 1)
            if count != expected:
                report.add(
                    "INV-4",
                    f"chapter {order} appears in {count} block(s), expected {expected}",
                    chapter_order=order,
                )
        for order in seen:
            if order not in set(snapshot_chapter_orders):
                report.add("INV-4", f"block covers chapter {order}, absent from the snapshot", chapter_order=order)
        return report

    # ---------------------------------------------------------------- INV-5
    def validate_nested_coverage(
        self,
        block_to_partition: Mapping[str, str],
        partition_to_stage: Mapping[str, str],
        all_blocks: Iterable[str],
        all_partitions: Iterable[str],
    ) -> InvariantReport:
        """Strict nesting: block ⊂ exactly one partition ⊂ exactly one stage.

        Scheme A: stage boundaries may fall only on partition boundaries. Chapter-level
        refinement was removed precisely because it made this nesting unsatisfiable.
        """
        report = InvariantReport()
        for block in all_blocks:
            if block not in block_to_partition:
                report.add("INV-5", f"block {block} belongs to no partition", block_key=block)
        for partition in all_partitions:
            if partition not in partition_to_stage:
                report.add("INV-5", f"partition {partition} belongs to no stage", partition_key=partition)
        return report

    # ---------------------------------------------------------------- INV-6
    def validate_no_prose_copy(
        self, asset_text: str, snapshot_text: str, *, max_run: int = NO_PROSE_COPY_MAX_RUN
    ) -> InvariantReport:
        """No asset above L1 contains a long verbatim run of snapshot text.

        Checked by sampling windows of exactly ``max_run + 1`` characters rather than by
        computing a longest common substring: this is O(n) in the asset, and the pipeline
        runs it over every asset in a book.
        """
        report = InvariantReport()
        if len(asset_text) <= max_run:
            return report
        window = max_run + 1
        for start in range(0, len(asset_text) - window + 1):
            fragment = asset_text[start : start + window]
            if fragment in snapshot_text:
                report.add(
                    "INV-6",
                    f"asset contains a {window}-character verbatim run of snapshot text",
                    fragment_head=fragment[:40],
                )
                break
        return report

    # ---------------------------------------------------------------- INV-7
    def validate_evidence_anchor(
        self, refs: Iterable[Mapping[str, Any]], known_paragraphs: Mapping[int, str]
    ) -> InvariantReport:
        """Every ``EvidenceRef`` resolves, and its paragraph hash matches the snapshot."""
        report = InvariantReport()
        for ref in refs:
            paragraph_ref = ref.get("paragraph_ref")
            if paragraph_ref not in known_paragraphs:
                report.add(
                    "INV-7",
                    f"evidence anchor [p:{paragraph_ref}] is outside the block's rendered range",
                    paragraph_ref=paragraph_ref,
                )
                continue
            expected = known_paragraphs[paragraph_ref]
            actual = ref.get("paragraph_content_hash")
            if actual and actual != expected:
                report.add(
                    "INV-7",
                    f"evidence at [p:{paragraph_ref}] cites content that is no longer there",
                    paragraph_ref=paragraph_ref,
                )
        return report

    # ---------------------------------------------------------------- INV-8
    def validate_single_raw_read(self, importer_modules: Mapping[str, Iterable[str]]) -> InvariantReport:
        """Only the block extractor may import the snapshot text reader.

        The single-read property is what makes the cost model true; a second reader
        reintroduces whole-book prose into an upper layer without anyone deciding to.
        """
        report = InvariantReport()
        allowed = {"block_extractor", "extract"}
        for module, imports in importer_modules.items():
            if any("snapshot_text" in imp for imp in imports) and not any(
                token in module for token in allowed
            ):
                report.add("INV-8", f"{module} imports the snapshot text reader", module=module)
        return report

    # ---------------------------------------------------------------- INV-9
    def validate_derived_rebuildable(
        self, stored_rows: Sequence[Mapping[str, Any]], rebuilt_rows: Sequence[Mapping[str, Any]]
    ) -> InvariantReport:
        """Rebuilding the derived tables from blocks reproduces them byte-identically."""
        report = InvariantReport()

        def norm(rows: Sequence[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
            return sorted(tuple(sorted(row.items())) for row in rows)

        if norm(stored_rows) != norm(rebuilt_rows):
            report.add(
                "INV-9",
                "rebuilding the derived index from long_novel_blocks does not reproduce it",
                stored=len(stored_rows),
                rebuilt=len(rebuilt_rows),
            )
        return report

    # ---------------------------------------------------------------- INV-11
    def validate_claim_support(self, claims: Iterable[Mapping[str, Any]]) -> InvariantReport:
        """Every user-visible claim carries exactly one valid ``ClaimSupport``."""
        report = InvariantReport()
        legal = {"DIRECTLY_SUPPORTED", "INFERRED", "AGGREGATE", "UNSUPPORTED"}
        for claim in claims:
            support = claim.get("support")
            if support not in legal:
                report.add("INV-11", f"claim {claim.get('field')!r} has support {support!r}", field=claim.get("field"))
            elif support == "DIRECTLY_SUPPORTED" and not claim.get("evidence_ids"):
                report.add(
                    "INV-11",
                    f"claim {claim.get('field')!r} is DIRECTLY_SUPPORTED but cites no evidence",
                    field=claim.get("field"),
                )
        return report

    # ---------------------------------------------------------------- INV-12
    def validate_reference_integrity(
        self,
        live_references: Iterable[tuple[str, int]],
        existing_facts: Iterable[tuple[str, int]],
    ) -> InvariantReport:
        """No live asset holds a ``(fact_key, asset_revision)`` pair that no longer exists.

        Dangling deterministically is the *designed* behaviour: a changed fact gets a new
        key, so the stale reference fails loudly here rather than silently re-binding to a
        different fact that happens to have the same payload.
        """
        report = InvariantReport()
        existing = set(existing_facts)
        for ref in live_references:
            if ref not in existing:
                report.add("INV-12", f"live asset references missing fact {ref[0]}@rev{ref[1]}", fact=ref[0])
        return report

    # ---------------------------------------------------------------- INV-13
    def validate_projection_budget(
        self, *, topic: Topic, assembled_tokens: int, declared_budget: int, omitted: Mapping[str, Any]
    ) -> InvariantReport:
        """A projection fits its budget, and anything dropped is recorded."""
        report = InvariantReport()
        if assembled_tokens > declared_budget:
            report.add(
                "INV-13",
                f"{topic.value} projection assembled {assembled_tokens} tokens over its {declared_budget} budget",
                topic=topic.value,
            )
        if assembled_tokens < declared_budget and omitted.get("truncated") and not omitted.get("reason"):
            report.add("INV-13", f"{topic.value} dropped input without recording why", topic=topic.value)
        return report

    # ---------------------------------------------------------------- INV-14 / INV-21
    def validate_snapshot_retention(
        self,
        formal_result_snapshots: Iterable[int],
        retained_snapshots: Iterable[int],
        deleted_snapshots: Iterable[int] = (),
    ) -> InvariantReport:
        """A formal result's snapshot holds a lock, and a locked snapshot is never deleted."""
        report = InvariantReport()
        retained = set(retained_snapshots)
        for snapshot_id in formal_result_snapshots:
            if snapshot_id not in retained:
                report.add("INV-14", f"formal result on snapshot {snapshot_id} holds no retention lock", snapshot_id=snapshot_id)
        for snapshot_id in deleted_snapshots:
            if snapshot_id in retained:
                report.add("INV-21", f"snapshot {snapshot_id} was deleted while still retained", snapshot_id=snapshot_id)
        return report

    # ---------------------------------------------------------------- INV-15
    def validate_entity_layering(
        self,
        l1_asset_keys: Iterable[str],
        carry_keys: Iterable[str],
        entity_traces: Mapping[str, Sequence[str]],
    ) -> InvariantReport:
        """No ``CHR-*`` at L1, and every ``CHR-*`` traces to a mention with an anchor."""
        report = InvariantReport()
        for key in l1_asset_keys:
            if key.startswith("CHR-"):
                report.add("INV-15", f"canonical entity {key} appears in an L1 asset", key=key)
        for key in carry_keys:
            if key.startswith("CHR-"):
                report.add("INV-15", f"canonical entity {key} appears in carry state", key=key)
            if key.startswith("LENT-"):
                report.add(
                    "INV-15",
                    f"provisional entity {key} appears in carry state; carry must reference CENT-*, "
                    "which is block-scoped-free and therefore resolvable in the next block",
                    key=key,
                )
        for entity, trace in entity_traces.items():
            if not any(step.startswith("MEN-") for step in trace):
                report.add("INV-15", f"{entity} does not trace to any mention", entity=entity)
        return report

    # ---------------------------------------------------------------- INV-16
    def validate_positional_freshness(
        self, live_assets: Iterable[Mapping[str, Any]], current_snapshot_id: int
    ) -> InvariantReport:
        """No live asset carries positional binding from a stale snapshot."""
        report = InvariantReport()
        for asset in live_assets:
            snapshot_id = asset.get("snapshot_id")
            if snapshot_id != current_snapshot_id and not asset.get("rebased_from_snapshot_id"):
                report.add(
                    "INV-16",
                    f"asset bound to snapshot {snapshot_id} is live under snapshot "
                    f"{current_snapshot_id} without a recorded rebase",
                    snapshot_id=snapshot_id,
                )
        return report

    # ---------------------------------------------------------------- INV-17
    def validate_occurrence_uniqueness(
        self, blocks: Sequence[Mapping[str, Any]]
    ) -> InvariantReport:
        """``occurrence_key`` is unique per logical block, and identical text at two places
        in the book yields two different occurrence keys."""
        report = InvariantReport()
        by_occurrence: dict[str, set[str]] = {}
        for block in blocks:
            by_occurrence.setdefault(block["occurrence_key"], set()).add(block["block_key"])
        for occurrence_key, block_keys in by_occurrence.items():
            if len(block_keys) > 1:
                report.add(
                    "INV-17",
                    f"occurrence {occurrence_key[:12]} is claimed by {len(block_keys)} logical blocks",
                    block_keys=sorted(block_keys),
                )
        content_groups: dict[str, set[str]] = {}
        for block in blocks:
            content_groups.setdefault(block["content_key"], set()).add(block["occurrence_key"])
        for content_key, occurrences in content_groups.items():
            expected = sum(1 for b in blocks if b["content_key"] == content_key)
            if len(occurrences) != expected:
                report.add(
                    "INV-17",
                    f"{expected} blocks share content {content_key[:12]} but only "
                    f"{len(occurrences)} distinct occurrence keys — duplicate text collapsed",
                    content_key=content_key,
                )
        return report

    # ---------------------------------------------------------------- INV-18
    def validate_bounded_input(
        self, planned_units: Iterable[Mapping[str, Any]]
    ) -> InvariantReport:
        """Every provider unit was bounded *before* the request was sent, with a planner."""
        report = InvariantReport()
        for unit in planned_units:
            if not unit.get("planner"):
                report.add(
                    "INV-18",
                    f"{unit.get('unit_kind')} unit {unit.get('unit_key')} has no planner; "
                    "no provider unit may exist without one",
                    unit_key=unit.get("unit_key"),
                )
            assembled = unit.get("assembled_input_tokens")
            budget = unit.get("declared_budget")
            if assembled is None or budget is None:
                report.add(
                    "INV-18",
                    f"{unit.get('unit_key')} did not decide its budget before sending",
                    unit_key=unit.get("unit_key"),
                )
            elif assembled > budget:
                report.add(
                    "INV-18",
                    f"{unit.get('unit_key')} sent {assembled} tokens over its {budget} budget",
                    unit_key=unit.get("unit_key"),
                )
        return report

    # ---------------------------------------------------------------- INV-19
    def validate_pif_validity(
        self, assets: Iterable[Mapping[str, Any]], recompute: Any = None
    ) -> InvariantReport:
        """Every provider result records the fingerprint of the payload actually sent."""
        report = InvariantReport()
        for asset in assets:
            if asset.get("origin") != "real_provider":
                continue
            pif = asset.get("provider_input_fingerprint")
            if not pif:
                report.add(
                    "INV-19",
                    f"{asset.get('unit_key')} was produced by a provider but records no input fingerprint",
                    unit_key=asset.get("unit_key"),
                )
            elif recompute is not None:
                expected = recompute(asset)
                if expected != pif:
                    report.add(
                        "INV-19",
                        f"{asset.get('unit_key')} records a fingerprint that does not match its payload",
                        unit_key=asset.get("unit_key"),
                    )
        return report

    # ---------------------------------------------------------------- INV-20
    def validate_occurrence_lineage(
        self, reuses: Iterable[Mapping[str, Any]]
    ) -> InvariantReport:
        """Cross-snapshot reuse requires *verified* one-to-one lineage.

        ``duplicate_ordinal`` is never sufficient: it is an intra-snapshot diagnostic, and
        using it to match across snapshots is how two different chapters get treated as the
        same one.
        """
        report = InvariantReport()
        for reuse in reuses:
            if not reuse.get("cross_snapshot"):
                continue
            if not reuse.get("lineage_verified"):
                report.add(
                    "INV-20",
                    f"{reuse.get('block_key')} reused across snapshots without verified lineage",
                    block_key=reuse.get("block_key"),
                )
            if reuse.get("matched_on") == "duplicate_ordinal":
                report.add(
                    "INV-20",
                    f"{reuse.get('block_key')} matched on duplicate_ordinal, which is "
                    "intra-snapshot diagnostic only",
                    block_key=reuse.get("block_key"),
                )
        return report

    # ---------------------------------------------------------------- INV-22
    def validate_continuity_soundness(
        self, returned_continuity_keys: Iterable[str], carry_in_continuity_keys: Iterable[str]
    ) -> InvariantReport:
        """Every ``CENT-*`` a block returns was present in the slate it was given.

        A block cannot invent a continuity chain it was never told about; if it does, the
        chain has no anchor and the carry fingerprint stops being comparable.
        """
        report = InvariantReport()
        known = set(carry_in_continuity_keys)
        for key in returned_continuity_keys:
            if key not in known:
                report.add(
                    "INV-22",
                    f"block returned continuity {key} that was not in its carry-in slate",
                    continuity_key=key,
                )
        return report

    # ---------------------------------------------------------------- aggregate
    def validate_all(self, checks: Sequence[InvariantReport]) -> InvariantReport:
        combined = InvariantReport()
        for report in checks:
            combined.violations.extend(report.violations)
        return combined
