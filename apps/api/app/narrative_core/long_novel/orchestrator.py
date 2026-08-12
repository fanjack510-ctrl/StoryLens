"""``RunCoordinator`` — one book, end to end.

Ties the layers together in the only order they can run: plan → extract → reduce →
interpret → project → assess → synthesise → adapt. Everything provider-facing is injected,
so the whole pipeline runs at full scale against a fake for nothing. That is deliberate: a
542-chapter book is roughly 49 paid calls, and finding a structural bug on call 40 is the
most expensive way to find it.

Three properties the coordinator is responsible for, which no individual layer can hold:

**Carry continuity across the whole book.** Each block's outgoing slate becomes the next
block's incoming one, so a thread opened in chapter 12 is still known about at chapter 400.

**The call budget is respected, not merely reported.** ``max_provider_calls`` stops the run
rather than discovering the overrun in the invoice.

**A failed block does not lose the book.** Blocks that fail are recorded and skipped; the run
continues and reports reduced fidelity, because 38 good blocks out of 39 is worth far more to
a reader than nothing at all — provided they are told which one is missing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from app.narrative_core.long_novel import constants as C
from app.narrative_core.long_novel.adapter import (
    build_assessment_section,
    build_chapters_section,
    build_characters_section,
    build_pacing_section,
    to_whole_book_v2,
)
from app.narrative_core.long_novel.contracts.density import DensityProfile
from app.narrative_core.long_novel.contracts.enums import Topic
from app.narrative_core.long_novel.contracts.l1 import BlockAsset, CarryForwardState
from app.narrative_core.long_novel.errors import LongNovelError
from app.narrative_core.long_novel.extractor import BlockExtractor, SourceChapter
from app.narrative_core.long_novel.planner import BookPlan, PlannedBlock
from app.narrative_core.long_novel.reducer import (
    build_carry_out,
    reduce_partition,
    resolve_entities,
)
from app.narrative_core.long_novel.topics import (
    ChapterSignalRow,
    build_assessment_input,
    build_chapters_topic,
    build_digest,
    build_final_input,
    project_topic,
    resample_pacing_curve,
)

__all__ = ["RunReport", "RunCoordinator"]


@dataclass
class RunReport:
    blocks_total: int = 0
    blocks_extracted: int = 0
    blocks_failed: list[tuple[str, str]] = field(default_factory=list)
    partitions: int = 0
    stages: int = 0
    provider_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    topics_projected: list[str] = field(default_factory=list)
    chapters_lost: list[int] = field(default_factory=list)
    document: dict[str, Any] | None = None

    @property
    def complete(self) -> bool:
        return not self.blocks_failed

    @property
    def coverage(self) -> float:
        return self.blocks_extracted / self.blocks_total if self.blocks_total else 0.0

    def chapter_coverage(self, total_chapters: int) -> float:
        """Fraction of the book that actually reached the analysis.

        Block coverage flatters the result: one lost block of 19 chapters is 2 % of the
        blocks and 2 % of the book, but a reader looking at a continuous pacing curve has no
        way to see the hole. This is the number that belongs in front of them.
        """
        if not total_chapters:
            return 0.0
        return max(0.0, (total_chapters - len(self.chapters_lost)) / total_chapters)


class RunCoordinator:
    def __init__(
        self,
        *,
        extractor: BlockExtractor,
        profile: DensityProfile,
        stage_interpreter: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        topic_synthesizer: Callable[[Topic, dict[str, Any]], dict[str, Any]] | None = None,
        assessor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        finaliser: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        max_provider_calls: int | None = None,
    ) -> None:
        self._extractor = extractor
        self._profile = profile
        self._interpret = stage_interpreter
        self._synthesize = topic_synthesizer
        self._assess = assessor
        self._finalise = finaliser
        self._max_calls = max_provider_calls

    def run(
        self,
        *,
        plan: BookPlan,
        chapters_by_order: dict[int, SourceChapter],
        book_id: int,
        snapshot_id: int,
        revision_hash: str,
        title: str,
        run_id: int,
        provider_name: str,
        model_name: str,
    ) -> RunReport:
        report = RunReport(
            blocks_total=len(plan.blocks),
            partitions=len(plan.partitions),
            stages=len(plan.stages),
        )

        assets = self._extract_all(plan.blocks, chapters_by_order, report)
        signals = self._collect_signals(assets)
        stage_skeleton = self._build_stage_skeleton(plan, assets)

        # Reductions are deterministic and free; running them even when blocks failed keeps
        # the partial result coherent rather than half-built.
        for partition in plan.partitions:
            members = [assets[k] for k in partition.block_keys if k in assets]
            if members:
                reduce_partition(partition_key=partition.partition_key, assets=members)

        # L2 interpretation: one bounded call per narrative stage. The reduction above was
        # free; this is the first paid step that works over facts rather than prose.
        interpretations = self._interpret_stages(stage_skeleton, report)
        entities = self._resolve_entities(assets)

        chapters_topic = build_chapters_topic(signals)
        report.topics_projected.append(Topic.CHAPTERS.value)

        digests = [build_digest(Topic.CHAPTERS, chapters_topic)]
        topic_results: dict[Topic, dict[str, Any]] = {}
        for topic in (Topic.STORY, Topic.CHARACTERS, Topic.SUSPENSE, Topic.PACING):
            if self._synthesize is None or self._budget_exhausted(report):
                continue
            projection = project_topic(
                topic,
                stage_skeleton=stage_skeleton,
                entities=entities,
                threads=[],
                events=self._collect_events(assets),
                signals=signals,
            )
            result = self._synthesize(topic, projection.payload)
            report.provider_calls += 1
            report.topics_projected.append(topic.value)
            topic_results[topic] = result
            digests.append(build_digest(topic, result))

        # Assessment reads the five digests, never the full topic results: six results at
        # their output target would exceed a 32K window on their own, which is how the
        # original contract made the final input unbounded in book length.
        assessment: dict[str, Any] | None = None
        if self._assess is not None and not self._budget_exhausted(report):
            assessment = self._assess(
                build_assessment_input(
                    digests, stage_skeleton=stage_skeleton, quality_metrics=self._metrics(report)
                )
            )
            report.provider_calls += 1
            report.topics_projected.append(Topic.ASSESSMENT.value)

        if self._finalise is not None and not self._budget_exhausted(report):
            self._finalise(
                build_final_input(
                    digests,
                    stage_skeleton=stage_skeleton,
                    assessment_digest=assessment or {},
                    selected_evidence_ids=[],
                    quality_metrics=self._metrics(report),
                )
            )
            report.provider_calls += 1

        report.document = self._assemble(
            report=report,
            signals=signals,
            entities=entities,
            assessment=assessment,
            chapters_topic=chapters_topic,
            topic_results=topic_results,
            book_id=book_id,
            snapshot_id=snapshot_id,
            revision_hash=revision_hash,
            title=title,
            run_id=run_id,
            provider_name=provider_name,
            model_name=model_name,
        )
        return report

    def _metrics(self, report: RunReport) -> dict[str, Any]:
        return {
            "blocks_extracted": report.blocks_extracted,
            "blocks_total": report.blocks_total,
            "coverage": round(report.coverage, 3),
            "blocks_failed": len(report.blocks_failed),
        }

    def _interpret_stages(
        self, stage_skeleton: Sequence[dict[str, Any]], report: RunReport
    ) -> list[dict[str, Any]]:
        """One bounded interpretive call per narrative stage.

        Stage count is clamped by ``MAX_STAGES``, so this term does not grow with the book:
        a 30,000-chapter novel costs the same here as a 3,000-chapter one.
        """
        if self._interpret is None:
            return []
        out: list[dict[str, Any]] = []
        for stage in stage_skeleton:
            if self._budget_exhausted(report):
                break
            out.append(self._interpret(dict(stage)))
            report.provider_calls += 1
        return out

    @staticmethod
    def _resolve_entities(assets: dict[str, BlockAsset]) -> list[dict[str, Any]]:
        """Resolve block-local clusters into canonical entities, ranked by appearances.

        Centrality is a *count*, not an opinion: how many blocks a person appears in is
        checkable, so two runs over the same book rank the cast identically. Clusters that
        share a display surface are folded together — the cross-block continuity that a
        single block cannot see on its own.
        """
        clusters: list[tuple[str, list[tuple[int, int, int, str]], str]] = []
        for block_key, asset in assets.items():
            for index, cluster in enumerate(asset.provisional_entities):
                members: list[tuple[int, int, int, str]] = []
                for order, mention_index in enumerate(cluster.member_mention_indexes):
                    if mention_index >= len(asset.mentions):
                        continue
                    mention = asset.mentions[mention_index]
                    members.append(
                        (
                            mention.paragraph_ref,
                            mention.paragraph_ref,
                            order,
                            f"MEN-{block_key[-8:]}-{mention_index}",
                        )
                    )
                if members:
                    clusters.append(
                        (
                            f"LENT-{block_key[-8:]}-{index}",
                            members,
                            cluster.display_surface_norm or "",
                        )
                    )

        folded: dict[str, dict[str, Any]] = {}
        for entity in resolve_entities(clusters):
            row = folded.setdefault(
                entity.display_surface_norm,
                {
                    "entity_key": entity.entity_key,
                    "display_surface_norm": entity.display_surface_norm,
                    "centrality": 0,
                    "evidence_ids": [],
                },
            )
            row["centrality"] += 1
        return sorted(folded.values(), key=lambda r: r["centrality"], reverse=True)

    # ------------------------------------------------------------------ stages
    def _extract_all(
        self,
        blocks: Sequence[PlannedBlock],
        chapters_by_order: dict[int, SourceChapter],
        report: RunReport,
    ) -> dict[str, BlockAsset]:
        """Extract every block, threading the carry slate forward.

        A block that fails is recorded and skipped rather than aborting: the carry slate is
        left unchanged so the next block still sees the last known-good continuity state,
        which keeps one bad response from corrupting everything downstream of it.
        """
        assets: dict[str, BlockAsset] = {}
        carry = CarryForwardState()

        for block in blocks:
            if self._budget_exhausted(report):
                report.blocks_failed.append((block.block_key, "MAX_PROVIDER_CALLS_REACHED"))
                continue
            chapters = [chapters_by_order[o] for o in block.chapter_orders if o in chapters_by_order]
            if not chapters:
                report.blocks_failed.append((block.block_key, "SOURCE_CHAPTERS_MISSING"))
                continue
            try:
                result = self._extractor.extract(
                    block_key=block.block_key, chapters=chapters, carry_in=carry
                )
            except LongNovelError as exc:
                # The message, not just the code. A run that records only "SCHEMA_MISMATCH"
                # cannot be diagnosed afterwards without paying to reproduce it — which is
                # exactly what happened the first time eight blocks failed this way.
                detail = exc.message.strip().splitlines()[0][:300] if exc.message else ""
                report.blocks_failed.append((block.block_key, f"{exc.code.value}: {detail}"))
                report.chapters_lost.extend(block.chapter_orders)
                report.provider_calls += 1
                continue
            assets[block.block_key] = result.asset
            report.blocks_extracted += 1
            report.provider_calls += result.provider_calls
            carry = build_carry_out(result.asset, carry)
        return assets

    def _budget_exhausted(self, report: RunReport) -> bool:
        return self._max_calls is not None and report.provider_calls >= self._max_calls

    @staticmethod
    def _collect_signals(assets: dict[str, BlockAsset]) -> list[ChapterSignalRow]:
        rows: list[ChapterSignalRow] = []
        for asset in assets.values():
            for signal in asset.chapter_signals:
                rows.append(
                    ChapterSignalRow(
                        chapter_order=signal.chapter_ref,
                        dialogue_paragraphs=signal.dialogue_paragraphs,
                        action_paragraphs=signal.action_paragraphs,
                        interiority_paragraphs=signal.interiority_paragraphs,
                        scene_breaks=signal.scene_breaks,
                        new_information_beats=signal.new_information_beats,
                        hook_present=signal.hook_present,
                        cap_saturated=signal.cap_saturated,
                    )
                )
        return sorted(rows, key=lambda r: r.chapter_order)

    @staticmethod
    def _collect_events(assets: dict[str, BlockAsset]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for asset in assets.values():
            for event in asset.events:
                events.append(
                    {
                        "summary": event.summary,
                        "actors": list(event.actors),
                        "chapter_ref": event.chapter_ref,
                        "weight": len(event.evidence),
                    }
                )
        return events

    @staticmethod
    def _build_stage_skeleton(
        plan: BookPlan, assets: dict[str, BlockAsset]
    ) -> list[dict[str, Any]]:
        return [
            {
                "stage_seq": stage.stage_seq,
                "stage_key": stage.stage_key,
                "chapter_start_order": stage.chapter_start_order,
                "chapter_end_order": stage.chapter_end_order,
            }
            for stage in plan.stages
        ]

    # ------------------------------------------------------------------ output
    def _assemble(
        self,
        *,
        report: RunReport,
        signals: Sequence[ChapterSignalRow],
        entities: Sequence[dict[str, Any]],
        assessment: dict[str, Any] | None,
        chapters_topic: dict[str, Any],
        topic_results: dict[Topic, dict[str, Any]],
        book_id: int,
        snapshot_id: int,
        revision_hash: str,
        title: str,
        run_id: int,
        provider_name: str,
        model_name: str,
    ) -> dict[str, Any]:
        pacing = build_pacing_section(resample_pacing_curve(signals))
        chapters = build_chapters_section(chapters_topic)

        # Each UI section has required sibling fields. Filling only the one this engine
        # produced yields a dict that looks right and fails validation, so the full shape is
        # built and the produced field is merged into it.
        SECTION_SHAPES: dict[Topic, dict[str, Any]] = {
            Topic.STORY: {
                "structure_stages": [], "storylines": [], "causal_chain": [], "chronology": []
            },
            Topic.SUSPENSE: {"lifecycles": []},
        }

        def section(topic: Topic, key: str) -> dict[str, Any] | None:
            result = topic_results.get(topic)
            if not result:
                return None
            shape = dict(SECTION_SHAPES.get(topic, {}))
            shape[key] = result.get(key, shape.get(key, []))
            return {"availability": "available", **shape}

        return to_whole_book_v2(
            book_id=book_id,
            snapshot_id=snapshot_id,
            revision_hash=revision_hash,
            title=title,
            chapter_count=len(signals),
            character_count=0,
            run_id=run_id,
            provider_name=provider_name,
            model_name=model_name,
            real_provider_calls=report.provider_calls,
            pacing=pacing,
            chapters=chapters,
            story=section(Topic.STORY, "structure_stages"),
            suspense=section(Topic.SUSPENSE, "lifecycles"),
            characters=build_characters_section(entities),
            assessment=build_assessment_section(assessment),
        )
