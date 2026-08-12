"""``BlockPlanner`` and the deterministic structure above it (01 §4.2, 03 §4.1b).

Planning is a **monotone accumulation against a moving bound**, not a division. The bound
moves because the paragraph-anchor cost ``E_anch`` grows as chapters are admitted: a block of
paragraph-dense chapters carries more anchor tokens than the same word count in long
paragraphs, so a fixed chapters-per-block figure silently overshoots on exactly the material
that needs care. A chapter is admitted only while *both* the recomputed input bound and the
output-derived chapter cap still hold.

Everything in this module is deterministic and free: no provider is involved in deciding
where blocks, partitions or stages fall. That is what makes the whole structure rebuildable
after an edit without paying for it again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from app.narrative_core.long_novel import constants as C
from app.narrative_core.long_novel import ids
from app.narrative_core.long_novel.budget import ContextCosts, safety_margin
from app.narrative_core.long_novel.contracts.density import DensityProfile, max_chapters_per_block
from app.narrative_core.long_novel.errors import LongNovelError, LongNovelErrorCode

__all__ = [
    "PlannedChapter",
    "PlannedBlock",
    "PlannedPartition",
    "PlannedStage",
    "BookPlan",
    "BlockPlanner",
]


@dataclass(frozen=True)
class PlannedChapter:
    """One snapshot chapter as the planner sees it."""

    chapter_order: int
    source_chapter_id: int | None
    content_hash: str
    text_tokens: int
    n_paragraphs: int
    #: Per-paragraph content hashes, needed only when a chapter must be split across blocks.
    paragraph_hashes: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class PlannedBlock:
    block_seq: int
    block_key: str
    content_key: str
    occurrence_key: str
    chapter_orders: tuple[int, ...]
    source_chapter_ids: tuple[int | str, ...]
    estimated_input_tokens: int
    estimated_output_tokens: int
    n_paragraphs: int
    #: True when any member chapter had no ``source_chapter_id``. Such a block is addressable
    #: inside its snapshot and resumes normally there, but is never reused across snapshots.
    oid_provisional: bool = False
    partial_chapter: bool = False
    part_index: int | None = None
    part_count: int | None = None


@dataclass(frozen=True)
class PlannedPartition:
    partition_seq: int
    partition_key: str
    block_keys: tuple[str, ...]
    chapter_start_order: int
    chapter_end_order: int


@dataclass(frozen=True)
class PlannedStage:
    stage_seq: int
    stage_key: str
    partition_keys: tuple[str, ...]
    chapter_start_order: int
    chapter_end_order: int


@dataclass(frozen=True)
class BookPlan:
    blocks: tuple[PlannedBlock, ...]
    partitions: tuple[PlannedPartition, ...]
    stages: tuple[PlannedStage, ...]

    @property
    def provider_calls(self) -> int:
        """Total provider calls this plan implies, before any repair."""
        return C.full_run_provider_calls(len(self.blocks), len(self.stages))


class BlockPlanner:
    """Turns a chapter list into blocks, partitions and stages.

    The planner never calls a provider and never reads chapter *text* — it works from the
    token and paragraph counts the snapshot already carries. Keeping it text-free is what
    makes INV-8 ("only the extractor reads prose") checkable rather than aspirational.
    """

    def __init__(
        self,
        *,
        profile: DensityProfile,
        output_budget: int,
        context_window: int,
        costs: ContextCosts,
    ) -> None:
        self._profile = profile
        self._output_budget = output_budget
        self._context_window = context_window
        self._costs = costs
        self._chapter_cap = min(
            max_chapters_per_block(profile, output_budget),
            C.MAX_CHAPTERS_FOR_SIGNAL_FIDELITY,
        )
        if self._chapter_cap < C.MIN_VIABLE_CHAPTERS_PER_BLOCK:
            raise LongNovelError(
                LongNovelErrorCode.OUTPUT_BUDGET_TOO_LOW,
                f"{profile.name} at O={output_budget} yields {self._chapter_cap} chapters per "
                f"block, below the {C.MIN_VIABLE_CHAPTERS_PER_BLOCK} minimum",
            )

    # ------------------------------------------------------------------ bounds
    def _fixed_overhead(self) -> int:
        return (
            self._output_budget
            + self._costs.fixed_total()
            + self._profile.carry_forward_max_tokens
            + safety_margin(self._context_window)
        )

    def _fits(self, text_tokens: int, n_paragraphs: int) -> bool:
        """Does this much text plus its anchors still fit the input side?"""
        available = self._context_window - self._fixed_overhead()
        return text_tokens + n_paragraphs * C.ANCHOR_TOKENS <= available

    def max_text_tokens_for(self, n_paragraphs: int) -> int:
        return self._context_window - self._fixed_overhead() - n_paragraphs * C.ANCHOR_TOKENS

    # ------------------------------------------------------------------ blocks
    def plan_blocks(self, chapters: Sequence[PlannedChapter]) -> tuple[PlannedBlock, ...]:
        if not chapters:
            return ()

        blocks: list[PlannedBlock] = []
        current: list[PlannedChapter] = []

        def close() -> None:
            if current:
                blocks.append(self._materialise(len(blocks), current))
                current.clear()

        for chapter in chapters:
            # A chapter that cannot fit a block even on its own must be split, or the plan
            # is a lie: admitting it whole would produce a request that cannot be sent.
            if not self._fits(chapter.text_tokens, chapter.n_paragraphs):
                close()
                blocks.extend(self._split_chapter(len(blocks), chapter))
                continue

            candidate = current + [chapter]
            tokens = sum(c.text_tokens for c in candidate)
            paragraphs = sum(c.n_paragraphs for c in candidate)
            # The retry-unit ceiling is enforced here as well as in the joint search: the
            # search works from book *means*, and a run of unusually long chapters would
            # otherwise sail past the absolute ceiling one chapter at a time.
            if (
                len(candidate) > self._chapter_cap
                or tokens > C.HARD_BLOCK_TOKENS
                or not self._fits(tokens, paragraphs)
            ):
                close()
                current.append(chapter)
            else:
                current.append(chapter)
        close()
        return tuple(blocks)

    def _materialise(self, block_seq: int, chapters: Sequence[PlannedChapter]) -> PlannedBlock:
        content_key = ids.block_content_key([c.content_hash for c in chapters])
        source_ids: list[int | str] = []
        oid_provisional = False
        for chapter in chapters:
            if chapter.source_chapter_id is None:
                # Fail *open* for addressing but closed for cross-snapshot reuse: the block
                # is still usable now, and is simply never adopted into a later snapshot.
                oid_provisional = True
                source_ids.append(f"prov:{chapter.chapter_order}")
            else:
                source_ids.append(chapter.source_chapter_id)
        occurrence_key = ids.block_occurrence_key(content_key, source_ids)
        text_tokens = sum(c.text_tokens for c in chapters)
        paragraphs = sum(c.n_paragraphs for c in chapters)
        return PlannedBlock(
            block_seq=block_seq,
            block_key=ids.block_key(occurrence_key),
            content_key=content_key,
            occurrence_key=occurrence_key,
            chapter_orders=tuple(c.chapter_order for c in chapters),
            source_chapter_ids=tuple(source_ids),
            estimated_input_tokens=text_tokens + paragraphs * C.ANCHOR_TOKENS,
            estimated_output_tokens=self._estimated_output(len(chapters)),
            n_paragraphs=paragraphs,
            oid_provisional=oid_provisional,
        )

    def _estimated_output(self, n_chapters: int) -> int:
        return (
            self._profile.per_block_fixed_output_tokens
            + n_chapters * self._profile.per_chapter_output_tokens
            + C.JSON_ENVELOPE_TOKENS
        )

    def _split_chapter(self, first_seq: int, chapter: PlannedChapter) -> list[PlannedBlock]:
        """Cut one oversized chapter into parts at paragraph boundaries.

        Split blocks carry ``part_index``/``part_count`` and their boundary paragraph hashes
        into ``content_key``: without them two parts of one chapter would be indistinguishable
        and would collide on identity.
        """
        if not chapter.paragraph_hashes:
            raise LongNovelError(
                LongNovelErrorCode.PLAN_NOT_FEASIBLE,
                f"chapter {chapter.chapter_order} exceeds a whole block but carries no "
                "paragraph hashes, so it cannot be split — the snapshot is incomplete",
                detail={"chapter_order": chapter.chapter_order},
            )

        n_paragraphs = len(chapter.paragraph_hashes)
        tokens_per_paragraph = max(1, chapter.text_tokens // max(1, n_paragraphs))
        # Solve for the paragraph count whose text *and* anchors fit together.
        per_paragraph_cost = tokens_per_paragraph + C.ANCHOR_TOKENS
        room = self._context_window - self._fixed_overhead()
        paragraphs_per_part = max(1, room // per_paragraph_cost)
        part_count = -(-n_paragraphs // paragraphs_per_part)

        parts: list[PlannedBlock] = []
        for part_index in range(part_count):
            start = part_index * paragraphs_per_part
            slice_hashes = chapter.paragraph_hashes[start : start + paragraphs_per_part]
            if not slice_hashes:
                continue
            content_key = ids.block_content_key(
                [chapter.content_hash],
                part_index=part_index,
                part_count=part_count,
                first_paragraph_hash=slice_hashes[0],
                last_paragraph_hash=slice_hashes[-1],
                paragraph_count_in_part=len(slice_hashes),
            )
            source_id = (
                chapter.source_chapter_id
                if chapter.source_chapter_id is not None
                else f"prov:{chapter.chapter_order}"
            )
            occurrence_key = ids.block_occurrence_key(
                content_key, [source_id], part_index=part_index
            )
            parts.append(
                PlannedBlock(
                    block_seq=first_seq + part_index,
                    block_key=ids.block_key(occurrence_key),
                    content_key=content_key,
                    occurrence_key=occurrence_key,
                    chapter_orders=(chapter.chapter_order,),
                    source_chapter_ids=(source_id,),
                    estimated_input_tokens=len(slice_hashes) * per_paragraph_cost,
                    estimated_output_tokens=self._estimated_output(1),
                    n_paragraphs=len(slice_hashes),
                    oid_provisional=chapter.source_chapter_id is None,
                    partial_chapter=True,
                    part_index=part_index,
                    part_count=part_count,
                )
            )
        return parts

    # ------------------------------------------------------------------ structure
    @staticmethod
    def plan_partitions(blocks: Sequence[PlannedBlock]) -> tuple[PlannedPartition, ...]:
        """Group blocks into Reduction Partitions. Feasible for every block count ≥ 1."""
        partitions: list[PlannedPartition] = []
        for index in range(0, len(blocks), C.PARTITION_TARGET_BLOCKS):
            members = blocks[index : index + C.PARTITION_TARGET_BLOCKS]
            occurrence_key = ids.partition_occurrence_key([b.occurrence_key for b in members])
            partitions.append(
                PlannedPartition(
                    partition_seq=len(partitions),
                    partition_key=ids.partition_key(occurrence_key),
                    block_keys=tuple(b.block_key for b in members),
                    chapter_start_order=min(o for b in members for o in b.chapter_orders),
                    chapter_end_order=max(o for b in members for o in b.chapter_orders),
                )
            )
        return tuple(partitions)

    @staticmethod
    def plan_stages(
        partitions: Sequence[PlannedPartition],
        partition_occurrence_keys: dict[str, str] | None = None,
    ) -> tuple[PlannedStage, ...]:
        """Group whole partitions into Narrative Stages.

        Boundaries fall **only** on partition edges (Scheme A). Chapter-level refinement was
        removed because it cannot coexist with strict nesting: a straddling block would have
        to belong to two stages while every block belongs to exactly one.
        """
        if not partitions:
            return ()
        n_stages = max(1, min(C.MAX_STAGES, round(len(partitions) / C.PARTITIONS_PER_STAGE_TARGET)))
        per_stage = -(-len(partitions) // n_stages)
        keys = partition_occurrence_keys or {}
        stages: list[PlannedStage] = []
        for index in range(0, len(partitions), per_stage):
            members = partitions[index : index + per_stage]
            if not members:
                continue
            occurrence_key = ids.stage_occurrence_key(
                [keys.get(p.partition_key, p.partition_key) for p in members]
            )
            stages.append(
                PlannedStage(
                    stage_seq=len(stages),
                    stage_key=ids.stage_key(occurrence_key),
                    partition_keys=tuple(p.partition_key for p in members),
                    chapter_start_order=members[0].chapter_start_order,
                    chapter_end_order=members[-1].chapter_end_order,
                )
            )
        return tuple(stages)

    def plan(self, chapters: Sequence[PlannedChapter]) -> BookPlan:
        blocks = self.plan_blocks(chapters)
        partitions = self.plan_partitions(blocks)
        stages = self.plan_stages(partitions)
        return BookPlan(blocks=blocks, partitions=partitions, stages=stages)
