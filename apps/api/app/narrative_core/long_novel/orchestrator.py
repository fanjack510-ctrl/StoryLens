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
from typing import Any, Callable, Mapping, Sequence

from app.narrative_core.long_novel import constants as C
from app.narrative_core.whole_book_v2.contracts import (
    ArcStage,
    ChronologyEvent,
    PacingMarker,
    Relationship,
    Storyline,
    StorylineNode,
    SuspenseEvent,
    StoryStage,
    SuspenseLifecycle,
)

from app.narrative_core.long_novel.adapter import (
    build_assessment_section,
    conform,
    build_overview_section,
    build_chapters_section,
    build_characters_section,
    build_pacing_section,
    build_type_profile_section,
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

#: L1 names an action by what it *did* to a thread; the product contract names it by the
#: reader-facing beat. Both vocabularies are closed, so the mapping is explicit — an
#: unmapped kind becomes a neutral "clue" rather than failing the whole suspense tab.
# A timeline is read, not scrolled: past a couple of hundred rows it stops being a view of
# the book. Events are sampled evenly across the span rather than truncated at the front, so
# the last act is represented as well as the first.
_CHRONOLOGY_MAX = 200

_SUSPENSE_EVENT_TYPES = {
    "open": "hook",
    "advance": "clue",
    "foreshadow": "foreshadow",
    "misdirect": "misdirection",
    "partial": "partial_reveal",
    "reveal": "reveal",
    "twist": "twist",
    "resolve": "payoff",
    "close": "payoff",
}

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
        #: evidence_id -> citable row, accumulated across blocks and deduplicated. Many facts
        #: legitimately cite the same paragraph, and the index is what makes every claim in
        #: the finished report followable back to a sentence.
        self._evidence: dict[str, dict[str, Any]] = {}

    def run(
        self,
        *,
        plan: BookPlan,
        chapters_by_order: dict[int, SourceChapter],
        character_count: int = 0,
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
        stage_skeleton = self._build_stage_skeleton(plan, assets)  # facts added below

        # Reductions are deterministic and free; running them even when blocks failed keeps
        # the partial result coherent rather than half-built.
        reductions: dict[str, Any] = {}
        for partition in plan.partitions:
            members = [assets[k] for k in partition.block_keys if k in assets]
            if members:
                reductions[partition.partition_key] = reduce_partition(
                    partition_key=partition.partition_key, assets=members
                )

        # L2 interpretation: one bounded call per narrative stage. The reduction above was
        # free; this is the first paid step that works over facts rather than prose.
        stage_inputs = self._stage_inputs(plan, assets, stage_skeleton)
        interpretations = self._interpret_stages(stage_inputs, report)
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
                    digests, stage_skeleton=stage_skeleton, quality_metrics=self._metrics(report, signals)
                )
            )
            report.provider_calls += 1
            report.topics_projected.append(Topic.ASSESSMENT.value)

        overview: dict[str, Any] | None = None
        if self._finalise is not None and not self._budget_exhausted(report):
            overview = self._finalise(
                build_final_input(
                    digests,
                    stage_skeleton=stage_skeleton,
                    assessment_digest=assessment or {},
                    selected_evidence_ids=[],
                    quality_metrics=self._metrics(report, signals),
                )
            )
            report.provider_calls += 1

        report.document = self._assemble(
            report=report,
            signals=signals,
            entities=entities,
            assets=assets,
            assessment=assessment,
            overview=overview,
            interpretations=interpretations,
            character_count=character_count,
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

    @staticmethod
    def _causal_chain(assets: dict[str, BlockAsset]) -> list[str]:
        """The causal spine, from the links L1 already extracted.

        These were being thrown away exactly like the stage interpretations were: the facts
        existed in every block asset and nothing read them, so the tab rendered empty.
        """
        chain: list[str] = []
        for asset in assets.values():
            for link in asset.causal_links:
                chain.append(f"{link.cause_fact_ref} → {link.effect_fact_ref}")
        return chain[:60]

    @staticmethod
    def _suspense_lifecycles(assets: dict[str, BlockAsset]) -> list[dict[str, Any]]:
        """Assemble each thread's life from the actions that touched it.

        A thread is opened once and then advanced, misdirected or resolved by later actions.
        Following those actions is what turns a list of questions into a lifecycle, and it is
        the whole point of the suspense tab.
        """
        opened: dict[str, dict[str, Any]] = {}
        for asset in assets.values():
            for thread in asset.suspense_threads:
                opened.setdefault(
                    thread.question,
                    {
                        "question": thread.question,
                        "chapter_start": thread.opened_chapter_ref,
                        "chapter_end": thread.opened_chapter_ref,
                        "events": [],
                        "status": "unresolved",
                    },
                )
        for asset in assets.values():
            for action in asset.suspense_actions:
                for entry in opened.values():
                    if action.thread_ref and action.thread_ref in entry["question"]:
                        entry["events"].append(
                            conform(
                                SuspenseEvent,
                                {
                                    "chapter": action.chapter_ref,
                                    "type": _SUSPENSE_EVENT_TYPES.get(
                                        action.action_kind, "clue"
                                    ),
                                    "description": action.information_added,
                                    "information_added": action.information_added,
                                },
                            )
                        )
                        entry["chapter_end"] = max(entry["chapter_end"], action.chapter_ref)
                        if action.action_kind in {"resolve", "close"}:
                            entry["status"] = "resolved"
                        break

        lifecycles: list[dict[str, Any]] = []
        for index, entry in enumerate(
            sorted(opened.values(), key=lambda e: len(e["events"]), reverse=True)[:40], start=1
        ):
            lifecycles.append(
                conform(
                    SuspenseLifecycle,
                    {
                        **entry,
                        "suspense_id": f"SUS-{index}",
                        # Importance is the count of times the story came back to it — a
                        # measured signal, not an opinion about what matters.
                        "importance": round(min(1.0, len(entry["events"]) / 10), 2),
                    },
                )
            )
        return lifecycles

    @staticmethod
    def _growth_tracks(assets: dict[str, BlockAsset], lead: str) -> dict[str, list[dict[str, Any]]]:
        """The protagonist's four tracks, from the state changes L1 already recorded.

        The whole 主角历程 page rendered as 「邓肯 → 邓肯」 because none of this was ever
        assembled — the facts were extracted, stored, and read by nothing. Each track is a
        chronological list of states, so a reader can see where the character actually moved
        rather than being told that they did.
        """
        status: list[dict[str, Any]] = []
        ability: list[dict[str, Any]] = []
        belief: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []

        ABILITY = ("能力", "掌握", "学会", "力量", "技能", "获得")
        BELIEF = ("相信", "信念", "怀疑", "决心", "信仰", "认知")
        for asset in assets.values():
            for change in asset.character_state_changes:
                if lead and lead not in change.entity_ref:
                    continue
                point = {
                    "chapter": change.chapter_ref,
                    "stage_name": "",
                    "state": f"{change.from_state} → {change.to_state}",
                    "cost_paid": [],
                    "gain_received": [],
                    "evidence": [e.paragraph_content_hash for e in change.evidence if e.paragraph_content_hash][:2],
                }
                blob = change.from_state + change.to_state
                if any(k in blob for k in ABILITY):
                    ability.append(point)
                elif any(k in blob for k in BELIEF):
                    belief.append(point)
                else:
                    status.append(point)
            for change in asset.relationship_changes:
                if lead and lead not in (change.from_entity_ref + change.to_entity_ref):
                    continue
                # A relationship change carries no chapter of its own — it is a per-block
                # fact. The chapter comes from the block's first chapter signal, which is
                # the nearest true position available; inventing one would be worse than
                # approximating from data that is actually there.
                chapter = asset.chapter_signals[0].chapter_ref if asset.chapter_signals else 1
                relations.append(
                    {
                        "chapter": max(1, chapter),
                        "stage_name": "",
                        "state": f"{change.from_entity_ref}–{change.to_entity_ref}: {change.relation}",
                        "cost_paid": [],
                        "gain_received": [],
                        "evidence": [],
                    }
                )

        order = lambda rows: sorted(rows, key=lambda r: r["chapter"])[:40]
        return {
            "external_status_track": order(status),
            "ability_track": order(ability),
            "internal_belief_track": order(belief),
            "relationship_track": relations[:40],
        }

    @staticmethod
    def _goal_and_conflict_evolution(assets: dict[str, BlockAsset]) -> tuple[list[str], list[str]]:
        """Goal and conflict evolution, from goal changes and choices.

        Both were empty on screen while ``goal_changes`` and ``choices`` sat unread in every
        block asset — the same omission as the stage interpretations and the suspense tab.
        """
        goals: list[str] = []
        conflicts: list[str] = []
        for asset in assets.values():
            for change in asset.goal_changes:
                goals.append(f"{change.entity_ref}: {change.goal_text} ({change.change_kind})")
            for choice in asset.choices:
                if choice.costs or choice.gains:
                    conflicts.append(
                        f"{choice.entity_ref}: {choice.decision}"
                        + (f"，代价 {'、'.join(choice.costs)}" if choice.costs else "")
                    )
        return goals[:20], conflicts[:20]

    @staticmethod
    def _pacing_regions(points: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """Name the stretches a reader would actually feel, from the computed curve.

        Derived rather than asked for: the curve is already whole-book percentiles, so a run
        of low values *is* a slow stretch. Asking a model to label regions it cannot see
        would be inventing.
        """
        if not points:
            return []
        regions: list[dict[str, Any]] = []
        run_kind: str | None = None
        start = 0
        for index, point in enumerate(points + [None]):  # sentinel closes the last run
            kind = None
            if point is not None:
                drive = point["reading_drive"]
                kind = "高潮" if drive >= 75 else ("平缓" if drive <= 25 else None)
            if kind != run_kind:
                if run_kind and index - start >= 3:
                    regions.append(
                        {
                            "chapter_start": points[start]["chapter_start"],
                            "chapter_end": points[index - 1]["chapter_end"],
                            "type": run_kind,
                            "reason": f"连续 {index - start} 个区间的阅读驱动力处于{run_kind}区",
                            "related_events": [],
                            "diagnosis": (
                                "读者推进力持续偏低，可考虑压缩或加入转折"
                                if run_kind == "平缓"
                                else "高强度段落，注意前后的缓冲"
                            ),
                        }
                    )
                run_kind, start = kind, index
        return regions[:12]

    @staticmethod
    def _relationships(assets: dict[str, BlockAsset]) -> list[dict[str, Any]]:
        """Relationship changes, folded per pair into a start and end state."""
        pairs: dict[tuple[str, str], dict[str, Any]] = {}
        for asset in assets.values():
            for change in asset.relationship_changes:
                key = tuple(sorted((change.from_entity_ref, change.to_entity_ref)))
                entry = pairs.setdefault(
                    key,
                    {
                        "person_a": key[0],
                        "person_b": key[1],
                        "relationship_type": change.relation,
                        "initial_state": change.relation,
                        "evolution": [],
                        "chapter_start": 1,
                        "chapter_end": 1,
                    },
                )
                entry["evolution"].append(change.relation)
                entry["final_state"] = change.relation
        return [
            conform(Relationship, entry)
            for entry in sorted(pairs.values(), key=lambda e: len(e["evolution"]), reverse=True)[:30]
        ]

    @staticmethod
    def _storylines(lifecycles: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Project suspense lifecycles onto the storyline shape the UI renders.

        A thread that is opened, returned to and closed *is* a storyline; the two views
        differ in presentation, not in the underlying facts. Building both from one source
        keeps them from disagreeing about the same book.
        """
        ranked = sorted(
            lifecycles,
            key=lambda e: (int(e.get("chapter_end", 1)) - int(e.get("chapter_start", 1)),
                           len(e.get("events", []))),
            reverse=True,
        )[:24]
        lines: list[dict[str, Any]] = []
        for index, entry in enumerate(ranked, start=1):
            events = list(entry.get("events", []))
            nodes = [
                conform(StorylineNode, {
                    "chapter": int(ev.get("chapter", 1) or 1),
                    "event": str(ev.get("description") or ev.get("information_added") or ""),
                    "evidence": list(ev.get("evidence", [])),
                })
                for ev in events[:20]
            ]
            resolved = str(entry.get("status", "")) == "resolved"
            lines.append(conform(Storyline, {
                "storyline_id": f"SL-{index}",
                "name": str(entry.get("question", "")),
                # The longest-running threads carry the book; the rest are subplots. This is a
                # measured span, not a judgement about which thread the author cared about.
                "type": "main" if index <= 3 else "subplot",
                "importance": float(entry.get("importance", 0.0) or 0.0),
                "chapter_start": int(entry.get("chapter_start", 1) or 1),
                "chapter_end": int(entry.get("chapter_end", 1) or 1),
                "nodes": nodes,
                "status": "resolved" if resolved else "open",
                "resolution": str(events[-1].get("description", "")) if resolved and events else "",
            }))
        return lines

    @staticmethod
    def _chronology(assets: dict[str, BlockAsset]) -> list[dict[str, Any]]:
        """Events in the order the book tells them.

        ``story_order`` is set equal to ``narrative_order``: nothing in the L1 contract marks
        a flashback, so any difference between the two would be invented. Equal orders say
        "not detected", which is the truth here — they do not say "no flashbacks exist".
        """
        rows: list[tuple[int, str, list[str]]] = []
        for asset in assets.values():
            for event in asset.events:
                rows.append((
                    event.chapter_ref,
                    event.summary,
                    [ref.evidence_id for ref in event.evidence if getattr(ref, "evidence_id", "")],
                ))
        rows.sort(key=lambda r: r[0])
        if len(rows) > _CHRONOLOGY_MAX:
            step = len(rows) / _CHRONOLOGY_MAX
            rows = [rows[int(i * step)] for i in range(_CHRONOLOGY_MAX)]
        return [
            conform(ChronologyEvent, {
                "event_id": f"CHR-{index}",
                "story_order": index,
                "narrative_order": index,
                "chapter": chapter,
                "description": summary,
                "evidence": evidence,
            })
            for index, (chapter, summary, evidence) in enumerate(rows, start=1)
        ]

    @staticmethod
    def _event_markers(
        interpretations: Sequence[Mapping[str, Any]],
        lifecycles: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Points worth naming on the pacing curve: stage openings and their turning points."""
        markers: list[dict[str, Any]] = []
        for item in interpretations:
            if not isinstance(item, Mapping):
                continue
            start = int(item.get("chapter_start_order", 1) or 1)
            markers.append(conform(PacingMarker, {
                "chapter": start,
                "title": str(item.get("title", "")),
                "event": str(item.get("stage_goal") or item.get("summary", ""))[:120],
                "importance": 0.8,
                "marker_type": "story_stage",
                "effect_on_pacing": "阶段开启",
            }))
            turn = str(item.get("turning_point", "")).strip()
            if turn:
                markers.append(conform(PacingMarker, {
                    "chapter": max(start, int(item.get("chapter_end_order", start) or start)),
                    "title": "转折",
                    "event": turn[:120],
                    "importance": 1.0,
                    "marker_type": "turning_point",
                    "effect_on_pacing": "推动进入下一阶段",
                }))
        for entry in list(lifecycles)[:8]:
            if str(entry.get("status")) == "resolved" and entry.get("events"):
                markers.append(conform(PacingMarker, {
                    "chapter": int(entry.get("chapter_end", 1) or 1),
                    "title": "悬念收束",
                    "event": str(entry.get("question", ""))[:120],
                    "importance": 0.6,
                    "marker_type": "major_event",
                    "effect_on_pacing": "张力释放",
                }))
        markers.sort(key=lambda m: m["chapter"])
        return markers[:40]

    @staticmethod
    def _protagonist_stages(interpretations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """The lead's journey, told stage by stage out of the interpretations already paid for."""
        stages: list[dict[str, Any]] = []
        for index, item in enumerate(interpretations, start=1):
            if not isinstance(item, Mapping):
                continue
            start = int(item.get("chapter_start_order", 1) or 1)
            stages.append(conform(ArcStage, {
                "stage_name": str(item.get("title", "")) or f"第{index}幕",
                "chapter": start,
                "chapter_end": max(start, int(item.get("chapter_end_order", start) or start)),
                "entry_state": str(item.get("protagonist_state", "")),
                "goal": str(item.get("stage_goal", "")),
                "major_events": [str(x) for x in item.get("key_events", []) if str(x).strip()][:8],
                "conflict": str(item.get("core_conflict", "")),
                "choice": str(item.get("major_choice", "")),
                "exit_state": str(item.get("ending_state", "")),
                "turning_point": str(item.get("turning_point", "")),
                "next_stage_trigger": str(item.get("next_question", "")),
            }))
        return stages

    @staticmethod
    def _story_section(
        interpretations: Sequence[dict[str, Any]],
        story_result: dict[str, Any] | None,
        causal_chain: Sequence[str],
        storylines: Sequence[dict[str, Any]] = (),
        chronology: Sequence[dict[str, Any]] = (),
    ) -> dict[str, Any] | None:
        """Build the story section from the stage interpretations that were paid for.

        These calls were being made, billed, and then dropped on the floor: the section read
        ``structure_stages`` out of the topic result, which never carried them, so four paid
        interpretations produced an empty screen.
        """
        stages = []
        for index, item in enumerate(interpretations):
            if not isinstance(item, dict):
                continue
            stages.append(
                conform(
                    StoryStage,
                    {
                        **item,
                        "stage_id": item.get("stage_id") or f"STG-{index + 1}",
                        "chapter_start": int(item.get("chapter_start_order", 1) or 1),
                        "chapter_end": int(item.get("chapter_end_order", 1) or 1),
                        "title": item.get("title") or f"第{index + 1}幕",
                    },
                )
            )
        if not stages and not story_result:
            return None
        return {
            "availability": "available" if stages else "partial",
            "structure_stages": stages,
            "storylines": list(storylines),
            "causal_chain": list(causal_chain),
            "chronology": list(chronology),
        }

    def _metrics(self, report: RunReport, signals: Sequence[ChapterSignalRow] = ()) -> dict[str, Any]:
        """Run metrics, including how much signal was actually extracted.

        The density figure is here because an assessor that cannot see it will explain the
        emptiness with the only hypothesis available to it: that the novel is empty. A real
        run graded a 2.4M-character book "约90%的章节无叙事内容 / chapter_efficiency D" when
        the truth was that extraction had produced counters for 4.7 % of chapters. Reporting
        a data gap as an authorial flaw is worse than reporting nothing.
        """
        signalled = sum(
            1
            for s in signals
            if s.dialogue_paragraphs or s.action_paragraphs or s.interiority_paragraphs
            or s.new_information_beats
        )
        total = len(signals)
        density = round(signalled / total, 3) if total else 0.0
        return {
            "blocks_extracted": report.blocks_extracted,
            "blocks_total": report.blocks_total,
            "coverage": round(report.coverage, 3),
            "blocks_failed": len(report.blocks_failed),
            "chapters_with_signal": signalled,
            "chapters_total": total,
            "signal_density": density,
            "signal_warning": (
                "抽取信号稀疏：只有 %d/%d 章有可用的逐章统计。"
                "章节空白很可能是抽取不足，不是作品缺陷；"
                "在证据不足时不要给出节奏或章节效率的负面评级。" % (signalled, total)
                if density < 0.6
                else ""
            ),
        }

    @staticmethod
    def _stage_inputs(
        plan: BookPlan,
        assets: dict[str, BlockAsset],
        skeleton: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Give each stage the facts that happened inside it.

        Without this the interpreter received four numbers — a sequence number, a key and a
        chapter range — and was asked what the stage was about. A model handed no material
        does not decline; it reaches for the most common shape for the genre, which is how a
        steampunk mystery came back as 「初入异世」「获得系统」「初入江湖」 and how the last
        stage came back in English. That is not the model hallucinating, it is being made to.

        Everything below was already computed and paid for at L1. It was simply not being
        passed on.
        """
        by_key = {b.block_key: b for b in plan.blocks}
        partition_of_stage: dict[int, list[str]] = {}
        for stage in plan.stages:
            partition_of_stage[stage.stage_seq] = list(stage.partition_keys)
        blocks_of_partition = {p.partition_key: list(p.block_keys) for p in plan.partitions}

        enriched: list[dict[str, Any]] = []
        for entry in skeleton:
            seq = int(entry.get("stage_seq", 0))
            block_keys: list[str] = []
            for partition_key in partition_of_stage.get(seq, []):
                block_keys.extend(blocks_of_partition.get(partition_key, []))

            events: list[str] = []
            threads: list[str] = []
            people: list[str] = []
            state_changes: list[str] = []
            for key in block_keys:
                asset = assets.get(key)
                if asset is None:
                    continue
                events.extend(e.summary for e in asset.events)
                threads.extend(t.question for t in asset.suspense_threads)
                people.extend(
                    c.display_surface_norm for c in asset.provisional_entities
                    if c.display_surface_norm
                )
                state_changes.extend(
                    f"{c.entity_ref}: {c.from_state} -> {c.to_state}"
                    for c in asset.character_state_changes
                )

            # Bounded: the interpreter's input must not grow with the size of the stage, or
            # a longer book would eventually blow the window (INV-18).
            seen: set[str] = set()
            unique_people = [p for p in people if not (p in seen or seen.add(p))]
            enriched.append(
                {
                    **entry,
                    "events": events[:40],
                    "open_questions": threads[:15],
                    "characters": unique_people[:20],
                    "state_changes": state_changes[:20],
                    "event_count": len(events),
                }
            )
        return enriched

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
            interpreted = self._interpret(dict(stage)) or {}
            # Carry the stage's own chapter range through: the interpreter is given a skeleton
            # entry and may not echo it back, and a stage rendered without a range shows as
            # "1-1" on screen.
            merged = {
                "chapter_start_order": stage.get("chapter_start_order", 1),
                "chapter_end_order": stage.get("chapter_end_order", 1),
                **interpreted,
            }
            out.append(merged)
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
            for row in result.evidence:
                self._evidence.setdefault(row["evidence_id"], row)
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
        assets: dict[str, BlockAsset],
        assessment: dict[str, Any] | None,
        overview: dict[str, Any] | None,
        interpretations: Sequence[dict[str, Any]],
        character_count: int,
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
        suspense_lifecycles = self._suspense_lifecycles(assets)
        relationships = self._relationships(assets)
        lead = entities[0]["display_surface_norm"] if entities else ""
        tracks = self._growth_tracks(assets, lead)
        goal_evolution, conflict_evolution = self._goal_and_conflict_evolution(assets)
        pacing = build_pacing_section(resample_pacing_curve(signals))
        pacing["pacing_regions"] = self._pacing_regions(pacing["points"])
        pacing["event_markers"] = self._event_markers(interpretations, suspense_lifecycles)
        chapters = build_chapters_section(chapters_topic)
        tracks["stages"] = self._protagonist_stages(interpretations)

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
            character_count=character_count,
            run_id=run_id,
            provider_name=provider_name,
            model_name=model_name,
            real_provider_calls=report.provider_calls,
            pacing=pacing,
            chapters=chapters,
            story=self._story_section(
                interpretations,
                topic_results.get(Topic.STORY),
                self._causal_chain(assets),
                storylines=self._storylines(suspense_lifecycles),
                chronology=self._chronology(assets),
            ),
            suspense={
                "availability": "available" if suspense_lifecycles else "unavailable",
                "lifecycles": suspense_lifecycles,
            },
            characters=build_characters_section(
                entities, relationships=relationships, tracks=tracks
            ),
            overview=build_overview_section(
                overview,
                entities,
                goal_evolution=goal_evolution,
                conflict_evolution=conflict_evolution,
            ),
            # The extractor knows the paragraph but not which snapshot the run is pinned to;
            # that belongs to the run, so it is stamped here rather than threaded down.
            evidence_index={
                key: {**row, "snapshot_id": snapshot_id, "revision_hash": revision_hash}
                for key, row in self._evidence.items()
            },
            assessment=build_assessment_section(assessment),
            # The genre profile comes from the same synthesis call as the overview — it is a
            # judgement about the whole book, and that is the only unit that has seen it.
            type_profile=build_type_profile_section(overview),
        )
