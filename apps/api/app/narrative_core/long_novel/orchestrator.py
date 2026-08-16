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
    TurningPoint,
)

from app.narrative_core.long_novel.adapter import (
    build_assessment_section,
    conform,
    build_overview_section,
    build_chapters_section,
    build_characters_section,
    build_journey_section,
    build_pacing_section,
    reading_drive_ranks,
    build_stage_ledger,
    build_type_profile_section,
    parse_rank,
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
    refers_to_thread,
    resolve_entities,
)
from app.narrative_core.long_novel.topics import (
    ChapterSignalRow,
    build_assessment_input,
    build_chapters_topic,
    build_digest,
    build_final_input,
    build_stage_digest,
    project_topic,
    resample_pacing_curve,
    spread,
)

#: A timeline is read, not scrolled: past a couple of hundred rows it stops being a view of
#: the book. Events are sampled evenly across the span rather than truncated at the front, so
#: the last act is represented as well as the first.
_CHRONOLOGY_MAX = 200

#: One implementation, imported. The carry slate and the report assembly both have to decide
#: whether an action names a given thread, and two copies of that rule would drift.
_refers_to = refers_to_thread

#: Category words a model reaches for when it is describing the cast rather than naming
#: anyone in it. They arrive as ordinary surfaces and reach the character table looking like
#: people — a real run listed 「主要角色」 and 「主要人物」 among the 24 characters of a book.
_NOT_NAMES = frozenset({
    "主要角色", "主要人物", "次要人物", "配角", "众人", "所有人", "人物", "角色",
    "群众", "路人", "其他", "旁人", "大家",
})


def _is_not_a_name(surface: str) -> bool:
    """Reject surfaces that describe a category of character instead of naming one.

    A compound surface such as 「邓肯/周铭」 is rejected too: it is the model writing two
    names in one cell, and admitting it creates a third character who is neither.
    """
    text = surface.strip()
    if not text:
        return True
    if text in _NOT_NAMES:
        return True
    return "/" in text or "、" in text

def _is_contraction_of(short: str, full: str) -> bool:
    """Is ``short`` the same person as ``full``, written with the middle left out?

    Chinese prose contracts a name by dropping interior characters — 洪霞警官 is called 洪警官,
    王建国主任 becomes 王主任 — and the two surfaces then rank as two people. On 《系统豪横》
    the cast list carried 洪霞警官 and 洪警官 as separate rows, each with its own partial
    history.

    The test is deliberately narrow, because the obvious one is wrong: 李山木 is a substring of
    李山木父亲, and merging those would erase a character. What separates the two cases is
    *where* the extra characters sit. A contraction keeps both ends and loses the middle; a
    relative keeps the whole name and appends a role. So the rule is: same first character,
    same last character, ``short`` embeds in ``full`` in order, and at most two characters
    differ.
    """
    if not short or not full or short == full or len(full) <= len(short):
        return False
    if len(full) - len(short) > 2 or len(short) < 2:
        return False
    if short[0] != full[0] or short[-1] != full[-1]:
        return False
    position = 0
    for character in full:
        if position < len(short) and character == short[position]:
            position += 1
    return position == len(short)


def _fold_contracted_names(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge contracted forms into the fullest surface, keeping the short one as an alias.

    Ranked input, so the surviving row is the one the book uses most and its centrality gains
    the mentions that were being counted against a second, phantom character.
    """
    survivors: list[dict[str, Any]] = []
    for row in rows:
        surface = str(row.get("display_surface_norm", ""))
        for kept in survivors:
            other = str(kept.get("display_surface_norm", ""))
            if _is_contraction_of(surface, other) or _is_contraction_of(other, surface):
                kept["centrality"] += row.get("centrality", 0)
                kept["blocks"] += row.get("blocks", 0)
                aliases = kept.setdefault("aliases", [])
                if surface not in aliases:
                    aliases.append(surface)
                break
        else:
            survivors.append(row)
    return sorted(survivors, key=lambda r: (r["centrality"], r["blocks"]), reverse=True)


#: L1 names an action by what it *did* to a thread; the product contract names it by the
#: reader-facing beat. Both vocabularies are closed, so the mapping is explicit — an
#: unmapped kind becomes a neutral "clue" rather than failing the whole suspense tab.
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
    #: The block assets the run extracted, keyed by block. The report could previously say how
    #: many blocks succeeded but not what came back inside them, so anything asking "was this
    #: field actually filled" had to go re-parse provider responses. Profile delta fields have
    #: no report section consuming them yet, and this is how they are inspected.
    assets: dict[str, Any] = field(default_factory=dict)

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
        #: One bounded call that decides which reveals answer which questions. Injected like
        #: the others, so a run without it behaves exactly as before rather than failing.
        thread_pairer: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        #: One bounded call that names which beats overturned an earlier one. Injected like
        #: the others: a run without it produces a journey with no down-moves rather than
        #: failing, which is what every run did before this existed.
        reversal_finder: Callable[[list[dict[str, Any]]], dict[str, Any]] | None = None,
        max_provider_calls: int | None = None,
    ) -> None:
        self._extractor = extractor
        self._profile = profile
        self._interpret = stage_interpreter
        self._synthesize = topic_synthesizer
        self._assess = assessor
        self._finalise = finaliser
        self._pair_threads = thread_pairer
        self._find_reversals = reversal_finder
        self._max_calls = max_provider_calls
        #: evidence_id -> citable row, accumulated across blocks and deduplicated. Many facts
        #: legitimately cite the same paragraph, and the index is what makes every claim in
        #: the finished report followable back to a sentence.
        self._evidence: dict[str, dict[str, Any]] = {}
        #: block_key → {paragraph_ref: evidence_id}. Paragraph numbers are block-local, so a
        #: fact's citation can only be resolved against the block it came from.
        self._anchors: dict[str, dict[int, str]] = {}

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
        #: The book's confirmed profile axes. Decides which journey axis the report carries;
        #: absent means no journey is computed, and the report falls back to the stage list.
        profile_axes: Mapping[str, Any] | None = None,
    ) -> RunReport:
        report = RunReport(
            blocks_total=len(plan.blocks),
            partitions=len(plan.partitions),
            stages=len(plan.stages),
        )

        assets = self._extract_all(plan.blocks, chapters_by_order, report)
        report.assets = assets
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

        # From here up, "the stages" means the interpreted ones. The skeleton is four integers
        # per act; handing it to a layer whose job is to describe the book asks that layer to
        # describe a book it has not been shown.
        stages = build_stage_digest(stage_skeleton, interpretations)

        chapters_topic = build_chapters_topic(signals)
        report.topics_projected.append(Topic.CHAPTERS.value)

        digests = [build_digest(Topic.CHAPTERS, chapters_topic)]
        topic_results: dict[Topic, dict[str, Any]] = {}
        for topic in (Topic.STORY, Topic.CHARACTERS, Topic.SUSPENSE, Topic.PACING):
            if self._synthesize is None or self._budget_exhausted(report):
                continue
            projection = project_topic(
                topic,
                stages=stages,
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
            payload = build_assessment_input(
                digests, stages=stages, quality_metrics=self._metrics(report, signals)
            )
            # The engine has already measured where the book drags. Handing that over turns
            # "第 1–806 章，提升叙事密度" — which is what an assessor with no measurements
            # returns, and which no author can act on — into a range they can open.
            curve = resample_pacing_curve(signals)
            payload["pacing_regions"] = self._pacing_regions(
                build_pacing_section(curve)["points"], reading_drive_ranks(curve)
            )
            assessment = self._assess(payload)
            report.provider_calls += 1
            report.topics_projected.append(Topic.ASSESSMENT.value)

        overview: dict[str, Any] | None = None
        if self._finalise is not None and not self._budget_exhausted(report):
            overview = self._finalise(
                build_final_input(
                    digests,
                    stages=stages,
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
            profile_axes=profile_axes,
        )
        return report

    @staticmethod
    def _causal_chain(assets: dict[str, BlockAsset]) -> list[str]:
        """The causal spine, from the links L1 already extracted.

        These were being thrown away exactly like the stage interpretations were: the facts
        existed in every block asset and nothing read them, so the tab rendered empty. Then
        they were passed through untouched, which put two kinds of nonsense on the page.

        A link whose cause happens *after* its effect is not a cause. Both sides name an event
        the same block extracted, so where both can be found the chapters settle it — measured
        on 《系统豪横》: 「曾昭野报警抓获李山木 → 系统激活」, with the system activating in
        chapter 1 and the arrest following it. And a link whose two sides are the same event is
        a sentence restated with an arrow in the middle, not a finding.
        """
        chapter_of: dict[str, int] = {}
        for asset in assets.values():
            for event in asset.events:
                chapter_of.setdefault(event.summary.strip(), event.chapter_ref)

        chain: list[str] = []
        for asset in assets.values():
            for link in asset.causal_links:
                cause = str(link.cause_fact_ref or "").strip()
                effect = str(link.effect_fact_ref or "").strip()
                if not cause or not effect or cause == effect:
                    continue
                cause_at, effect_at = chapter_of.get(cause), chapter_of.get(effect)
                if cause_at is not None and effect_at is not None and cause_at > effect_at:
                    continue
                chain.append(f"{cause} → {effect}")
        return chain[:60]

    #: Bounds on the pairing call's input. The payload must not grow with book length, which
    #: is the property the whole design exists to keep; these caps hold it at roughly 15K
    #: tokens for any novel. Threads are ranked by how often the book returns to them and
    #: reveals are taken in chapter order, so what is dropped is the tail nobody revisits.
    PAIRING_THREADS_MAX = 60
    PAIRING_REVEALS_MAX = 200

    #: Which action kinds could plausibly answer a question. `advance` cannot — it is defined
    #: as movement without revelation — so feeding it in would only invite a false pairing.
    _REVEALING_KINDS = frozenset({"reveal", "partial", "twist", "resolve", "close"})

    #: Actions that state something the reader can later find out was wrong.
    _REVERSIBLE_KINDS = frozenset({"reveal", "partial", "resolve", "twist", "close"})

    def _reversal_input(self, assets: dict[str, BlockAsset]) -> list[dict[str, Any]]:
        """Every revealing beat in chapter order, for the one call that can see a reversal.

        A block sees eight chapters, so it cannot know that what it just read overturns
        something from chapter 76. Measured twice: block extraction chose ``twist`` once in
        806 chapters, and expanding the field's description made it worse — ``advance`` went
        from 58% to 77%, because a longer instruction pushes toward the default. Moving the
        judgement to one whole-book call found five valid reversals for ¥0.004.
        """
        rows: list[dict[str, Any]] = []
        for asset in assets.values():
            for action in asset.suspense_actions:
                if action.action_kind not in self._REVERSIBLE_KINDS:
                    continue
                text = (action.information_added or "").strip()
                if text:
                    rows.append({"chapter": action.chapter_ref, "text": text[:60]})
        rows.sort(key=lambda row: row["chapter"])
        if len(rows) > self.PAIRING_REVEALS_MAX:
            step = len(rows) / self.PAIRING_REVEALS_MAX
            rows = [rows[int(i * step)] for i in range(self.PAIRING_REVEALS_MAX)]
        return [
            {"id": f"R{index}", "chapter": row["chapter"], "text": row["text"]}
            for index, row in enumerate(rows, start=1)
        ]

    @staticmethod
    def _accept_reversals(
        reveals: Sequence[Mapping[str, Any]], result: Mapping[str, Any] | None
    ) -> list[dict[str, Any]]:
        """Keep the reversals that survive a check the engine can make on its own.

        A reversal must overturn something *earlier*. On a 90-row list two of seven answers
        pointed the wrong way; the chapter numbers are already in hand, so those are dropped
        here rather than shown. This is deterministic filtering of a model's answer, not a
        second opinion about it.
        """
        by_id = {str(row["id"]): row for row in reveals}
        kept: list[dict[str, Any]] = []
        for row in (result or {}).get("reversals") or []:
            later = by_id.get(str(row.get("id", "")))
            earlier = by_id.get(str(row.get("overturns", "")))
            if not later or not earlier:
                continue
            if int(later["chapter"]) <= int(earlier["chapter"]):
                continue
            kept.append({
                "chapter": int(later["chapter"]),
                "overturns_chapter": int(earlier["chapter"]),
                "text": str(later["text"]),
                "why": str(row.get("why") or "")[:60],
            })
        return kept

    def _pairing_input(self, assets: dict[str, BlockAsset]) -> dict[str, list[dict[str, Any]]]:
        """Every open question and every revealing beat, side by side, for one L2 call.

        A block sees eight chapters and cannot judge whether what it just read answers a
        question asked four hundred chapters earlier. That judgement needs the whole book at
        once, so it is made once, here, rather than block by block.
        """
        threads: dict[str, dict[str, Any]] = {}
        reveals: list[dict[str, Any]] = []
        for asset in assets.values():
            for thread in asset.suspense_threads:
                threads.setdefault(
                    thread.question,
                    {
                        "thread_id": f"T{len(threads) + 1}",
                        "question": thread.question,
                        "opened_chapter": thread.opened_chapter_ref,
                        "revisits": 0,
                    },
                )
            for action in asset.suspense_actions:
                if action.action_kind not in self._REVEALING_KINDS:
                    continue
                if not action.information_added:
                    continue
                reveals.append(
                    {
                        "reveal_id": f"R{len(reveals) + 1}",
                        "chapter": action.chapter_ref,
                        "kind": action.action_kind,
                        "text": action.information_added,
                    }
                )
        for asset in assets.values():
            for action in asset.suspense_actions:
                for entry in threads.values():
                    if action.thread_ref and _refers_to(action.thread_ref, entry["question"]):
                        entry["revisits"] += 1
                        break

        ranked = sorted(threads.values(), key=lambda t: t["revisits"], reverse=True)
        return {
            "threads": [
                {k: v for k, v in t.items() if k != "revisits"}
                for t in ranked[: self.PAIRING_THREADS_MAX]
            ],
            "reveals": sorted(reveals, key=lambda r: r["chapter"])[: self.PAIRING_REVEALS_MAX],
        }

    @staticmethod
    def _apply_pairs(
        lifecycles: list[dict[str, Any]],
        pairing_input: Mapping[str, list[dict[str, Any]]],
        result: Mapping[str, Any] | None,
    ) -> int:
        """Mark the threads the pairing call answered. Returns how many were closed.

        A pair naming a thread or reveal that was not sent is dropped rather than guessed at:
        an invented resolution is worse than an open thread, because 「已回收」 tells an
        author to stop looking for the hole.
        """
        pairs = (result or {}).get("pairs") or []
        by_question = {t["question"]: t["thread_id"] for t in pairing_input["threads"]}
        reveal_chapters = {r["reveal_id"]: r["chapter"] for r in pairing_input["reveals"]}
        answered: dict[str, tuple[str, int]] = {}
        for pair in pairs:
            if not isinstance(pair, Mapping):
                continue
            thread_id = str(pair.get("thread_id", ""))
            reveal_id = str(pair.get("reveal_id", ""))
            answer = str(pair.get("answer", "")).strip()
            if not answer or reveal_id not in reveal_chapters:
                continue
            answered[thread_id] = (answer, reveal_chapters[reveal_id])

        closed = 0
        for lifecycle in lifecycles:
            thread_id = by_question.get(lifecycle.get("question", ""))
            if thread_id not in answered:
                continue
            answer, chapter = answered[thread_id]
            lifecycle["status"] = "resolved"
            lifecycle["truth"] = answer
            lifecycle["payoff"] = answer
            lifecycle["chapter_end"] = max(int(lifecycle.get("chapter_end", 1) or 1), chapter)
            closed += 1
        return closed

    def _suspense_lifecycles(self, assets: dict[str, BlockAsset]) -> list[dict[str, Any]]:
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
        for block_key, asset in assets.items():
            for action in asset.suspense_actions:
                for entry in opened.values():
                    # A thread is opened as a question ("教堂中的低语声是否来自葛莫娜？") and
                    # returned to by a label ("教堂低语声"). Matching in one direction only
                    # dropped the actions whose label was not literally a substring, and a
                    # lifecycle with no actions is a question the UI shows as never revisited.
                    if action.thread_ref and _refers_to(action.thread_ref, entry["question"]):
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
                                    "evidence": self._cite(block_key, action),
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
            # The lifecycle columns are just the thread's own events sorted by what each one
            # did to the question. They stayed empty for as long as the extraction returned
            # every action as "advance".
            def _of(*kinds: str) -> list[str]:
                return [
                    str(event.get("description") or event.get("information_added") or "")
                    for event in entry["events"]
                    if event.get("type") in kinds
                ][:6]

            payoffs = _of("payoff")
            # "未收束" was being printed over questions the book had visibly answered in part,
            # because status only ever took two values and only a `resolve`/`close` action set
            # the second one. Extraction returns `advance` for almost everything — measured on
            # 《系统豪横》: 25 clues against a single payoff — so a thread that got a real reveal
            # was filed identically to one nobody ever returned to. The contract has always had
            # a third value; a thread that was revealed but never paid off is what it is for.
            status = entry["status"]
            if status != "resolved" and _of("reveal", "twist", "partial_reveal"):
                status = "partial"
            lifecycles.append(
                conform(
                    SuspenseLifecycle,
                    {
                        **entry,
                        "status": status,
                        "suspense_id": f"SUS-{index}",
                        "clues": _of("clue", "foreshadow"),
                        "misdirections": _of("misdirection"),
                        "partial_reveals": _of("partial_reveal", "reveal"),
                        "twist": next(iter(_of("twist")), ""),
                        "payoff": payoffs[0] if payoffs else "",
                        "truth": payoffs[-1] if payoffs else "",
                        # Importance is the count of times the story came back to it — a
                        # measured signal, not an opinion about what matters.
                        "importance": round(min(1.0, len(entry["events"]) / 10), 2),
                    },
                )
            )
        return lifecycles

    def _growth_tracks(self, assets: dict[str, BlockAsset], lead: str) -> dict[str, list[dict[str, Any]]]:
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

        # Two of the four tracks were nearly empty — 2 and 5 points against 40 — because
        # these lists were short enough that almost every state change fell through to the
        # status track by default. A lead who "掌握" something is the same growth beat as one
        # who 突破 or 精通; leaving those out did not mean the book lacked ability growth, it
        # meant the classifier could not see it.
        ABILITY = (
            "能力", "掌握", "学会", "力量", "技能", "获得", "突破", "精通", "熟练",
            "强大", "变强", "提升", "领悟", "觉醒", "解锁", "使用", "施展", "控制",
        )
        BELIEF = (
            "相信", "信念", "怀疑", "决心", "信仰", "认知", "以为", "明白", "意识到",
            "接受", "理解", "动摇", "释怀", "认清", "醒悟", "笃定", "犹豫", "确信",
        )

        # What the lead paid and got, indexed by the chapter it happened in, so a point on a
        # track can carry its own ledger instead of two permanently empty columns.
        ledger: dict[int, tuple[list[str], list[str]]] = {}
        for asset in assets.values():
            chapter = asset.chapter_signals[0].chapter_ref if asset.chapter_signals else 1
            for choice in asset.choices:
                if lead and lead not in choice.entity_ref:
                    continue
                costs, gains = ledger.setdefault(chapter, ([], []))
                costs.extend(c for c in choice.costs if c)
                gains.extend(g for g in choice.gains if g)
        for block_key, asset in assets.items():
            for change in asset.character_state_changes:
                if lead and lead not in change.entity_ref:
                    continue
                point = {
                    "chapter": change.chapter_ref,
                    "stage_name": "",
                    "state": f"{change.from_state} → {change.to_state}",
                    "cost_paid": ledger.get(change.chapter_ref, ([], []))[0][:3],
                    "gain_received": ledger.get(change.chapter_ref, ([], []))[1][:3],
                    # ``paragraph_content_hash`` was used here and is empty in every real
                    # response — the model is not asked for it. The resolved evidence id is.
                    "evidence": self._cite(block_key, change),
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

        def order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            """Chronological, and thinned by sampling across the span rather than truncating.

            Taking the first forty made a track stop dead partway through the book: the
            relationship lane ended at chapter 217 of 806, which reads as "nothing happened
            after that" instead of "we stopped looking". Sampling keeps the last act.
            """
            ordered = sorted(rows, key=lambda r: r["chapter"])
            if len(ordered) <= C.TRACK_POINTS_MAX:
                return ordered
            step = len(ordered) / C.TRACK_POINTS_MAX
            return [ordered[int(i * step)] for i in range(C.TRACK_POINTS_MAX)]

        return {
            "external_status_track": order(status),
            "ability_track": order(ability),
            "internal_belief_track": order(belief),
            "relationship_track": order(relations),
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
    def _lead_goals(assets: dict[str, BlockAsset], lead: str) -> tuple[str, str]:
        """The lead's first and last stated goal, in narrative order.

        The protagonist header was rendering 「邓肯 → 邓肯」 with no goal on either side,
        while every goal change the lead makes was sitting in the assets unread.
        """
        if not lead:
            return "", ""
        stated: list[tuple[int, str]] = []
        for asset in assets.values():
            for change in asset.goal_changes:
                if lead and lead in change.entity_ref:
                    chapter = asset.chapter_signals[0].chapter_ref if asset.chapter_signals else 1
                    stated.append((chapter, change.goal_text))
        if not stated:
            return "", ""
        stated.sort(key=lambda row: row[0])
        return stated[0][1], stated[-1][1]

    @staticmethod
    def _turning_points(interpretations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """The book's turning points, as the stage interpretations named them."""
        points: list[dict[str, Any]] = []
        for item in interpretations:
            if not isinstance(item, Mapping):
                continue
            text = str(item.get("turning_point", "")).strip()
            if not text:
                continue
            start = int(item.get("chapter_start_order", 1) or 1)
            points.append(conform(TurningPoint, {
                "chapter_start": start,
                "chapter_end": max(start, int(item.get("chapter_end_order", start) or start)),
                "title": str(item.get("title", "")) or "转折",
                "description": text,
            }))
        return points

    @staticmethod
    def _pacing_regions(
        points: Sequence[dict[str, Any]], drive: Sequence[int] = ()
    ) -> list[dict[str, Any]]:
        """Name the stretches a reader would actually feel, from the computed curve.

        Derived rather than asked for: the curve is already whole-book percentiles, so a run
        of low values *is* a slow stretch. Asking a model to label regions it cannot see
        would be inventing.

        ``drive`` is the composite that used to be published as a curve and is now an internal
        signal — see ``reading_drive_ranks``. Passed in rather than read off the point, because
        the point no longer carries it.
        """
        if not points or len(drive) < len(points):
            return []
        regions: list[dict[str, Any]] = []
        run_kind: str | None = None
        start = 0
        for index, point in enumerate(list(points) + [None]):  # sentinel closes the last run
            kind = None
            if point is not None:
                drive_here = drive[index]
                # ``type`` is a closed vocabulary in the contract. It reached the document in
                # Chinese and failed validation on a finished paid run — the label a reader
                # sees belongs in ``reason``, never in the enum.
                kind = (
                    "climax" if drive_here >= 75 else ("fatigue" if drive_here <= 25 else None)
                )
            if kind != run_kind:
                if run_kind and index - start >= 3:
                    slow = run_kind == "fatigue"
                    regions.append(
                        {
                            "chapter_start": points[start]["chapter_start"],
                            "chapter_end": points[index - 1]["chapter_end"],
                            "type": run_kind,
                            "reason": (
                                f"连续 {index - start} 个区间的阅读驱动力处于"
                                f"{'平缓' if slow else '高潮'}区"
                            ),
                            "related_events": [],
                            "diagnosis": (
                                "读者推进力持续偏低，可考虑压缩或加入转折"
                                if slow
                                else "高强度段落，注意前后的缓冲"
                            ),
                        }
                    )
                run_kind, start = kind, index
        return regions[:12]

    @staticmethod
    def _relationships(assets: dict[str, BlockAsset]) -> list[dict[str, Any]]:
        """Relationship changes, folded per pair into a start and end state.

        The chapter span is the range over which the pair actually changed. It used to be
        hardcoded to 1–1, so the relationship table showed 「1–1」 for all thirty pairs in an
        806-chapter book — a column that was present, sorted and completely uninformative.
        A relationship change carries no chapter of its own, so the block's first chapter
        signal stands in: it is the nearest true position available.
        """
        pairs: dict[tuple[str, str], dict[str, Any]] = {}
        for asset in assets.values():
            chapter = asset.chapter_signals[0].chapter_ref if asset.chapter_signals else 1
            for change in asset.relationship_changes:
                key = tuple(sorted((change.from_entity_ref, change.to_entity_ref)))
                entry = pairs.setdefault(
                    key,
                    {
                        "person_a": key[0],
                        "person_b": key[1],
                        "steps": [],
                        "chapter_start": chapter,
                        "chapter_end": chapter,
                    },
                )
                entry["chapter_start"] = min(entry["chapter_start"], chapter)
                entry["chapter_end"] = max(entry["chapter_end"], chapter)
                if not entry["steps"] or entry["steps"][-1] != change.relation:
                    entry["steps"].append(change.relation)

        # One string, four fields. `relationship_type`, `initial_state` and `evolution[0]` all
        # carried the first recorded relation, so a pair that changed once was printed three
        # times and the detail panel counted it as a step it had not taken. Each field now says
        # something the others do not: where the pair started, where it ended, and — only when
        # there is one — what it passed through between.
        rows: list[dict[str, Any]] = []
        for entry in sorted(pairs.values(), key=lambda e: len(e["steps"]), reverse=True)[:30]:
            steps: list[str] = entry.pop("steps")
            rows.append(
                conform(Relationship, {
                    **entry,
                    "initial_state": steps[0] if steps else "",
                    "final_state": steps[-1] if steps else "",
                    "evolution": steps[1:-1],
                    # No relationship taxonomy is extracted, so the honest label for the kind of
                    # bond is the state it settled into — stated once, here, and nowhere else.
                    "relationship_type": steps[-1] if steps else "",
                })
            )
        return rows

    def _character_facts(
        self, assets: dict[str, BlockAsset], names: Sequence[str], lead: str
    ) -> dict[str, dict[str, Any]]:
        """Everything the extraction already knows about each named character.

        The character page declared thirteen fields per person and filled two of them, while
        the events they act in, the goals they form, the choices they pay for and the
        relationships they change were all sitting in the assets. Matching is by surface
        containment against the resolved display name — the same rule the growth tracks use,
        so the page and the tracks agree about who did what.
        """
        facts: dict[str, dict[str, Any]] = {
            name: {"key_events": [], "goals": [], "choices": [], "to_lead": [], "evidence": []}
            for name in names if name
        }
        if not facts:
            return facts
        for block_key, asset in assets.items():
            for event in asset.events:
                for name, row in facts.items():
                    if any(name in actor for actor in event.actors):
                        row["key_events"].append((event.chapter_ref, event.summary))
                        row["evidence"].extend(self._cite(block_key, event))
            for change in asset.goal_changes:
                for name, row in facts.items():
                    if name in change.entity_ref:
                        row["goals"].append(change.goal_text)
            for choice in asset.choices:
                for name, row in facts.items():
                    if name in choice.entity_ref:
                        row["choices"].append((choice.decision, choice.costs, choice.gains))
            for rel in asset.relationship_changes:
                if not lead:
                    continue
                pair = (rel.from_entity_ref, rel.to_entity_ref)
                if not any(lead in side for side in pair):
                    continue
                other = pair[1] if lead in pair[0] else pair[0]
                for name, row in facts.items():
                    if name != lead and name in other:
                        row["to_lead"].append(rel.relation)
        return facts

    def _evidence_by_chapter(self, assets: dict[str, BlockAsset]) -> dict[int, list[str]]:
        """Each chapter's citable evidence ids, so a row on the chapter list can be opened."""
        by_chapter: dict[int, list[str]] = {}
        for block_key, asset in assets.items():
            for event in asset.events:
                row = by_chapter.setdefault(event.chapter_ref, [])
                for evidence_id in self._cite(block_key, event):
                    if evidence_id not in row:
                        row.append(evidence_id)
        return by_chapter

    @staticmethod
    def _events_by_chapter(assets: dict[str, BlockAsset]) -> dict[int, list[str]]:
        """Every chapter's event summaries, in the order they were extracted."""
        by_chapter: dict[int, list[str]] = {}
        for asset in assets.values():
            for event in asset.events:
                by_chapter.setdefault(event.chapter_ref, []).append(event.summary)
        return by_chapter

    @staticmethod
    def _annotate_pacing(
        points: Sequence[dict[str, Any]], assets: dict[str, BlockAsset]
    ) -> None:
        """Name what happens inside each band of the curve.

        The curve answers "how fast" but every point was rendering its ``dominant_events`` and
        ``reason`` empty, so the reader got a shape with nothing attached to it. Both come
        from events already extracted for those chapters — the curve and the events finally
        describe the same stretch of book.

        ``story_consequence`` is left alone: it is a judgement about what a stretch did to the
        story, and there is nothing measured to derive it from.
        """
        by_chapter = RunCoordinator._events_by_chapter(assets)
        if not by_chapter:
            return
        for point in points:
            start = int(point.get("chapter_start", 1) or 1)
            end = int(point.get("chapter_end", start) or start)
            summaries: list[str] = []
            for chapter in range(start, end + 1):
                summaries.extend(by_chapter.get(chapter, ()))
            if not summaries:
                continue
            point["dominant_events"] = summaries[:5]
            point["reason"] = f"第 {start}–{end} 章共记录 {len(summaries)} 个事件"

    @staticmethod
    def _stage_spans(
        assets: dict[str, BlockAsset], interpretations: Sequence[Mapping[str, Any]]
    ) -> dict[tuple[int, int], dict[str, Any]]:
        """Per-stage cast and ledger, counted from the facts inside each stage's chapters."""
        spans: dict[tuple[int, int], dict[str, Any]] = {}
        bounds = []
        for item in interpretations:
            if not isinstance(item, Mapping):
                continue
            start = int(item.get("chapter_start_order", 1) or 1)
            end = max(start, int(item.get("chapter_end_order", start) or start))
            spans[(start, end)] = {"characters": [], "costs": [], "gains": []}
            bounds.append((start, end))
        if not bounds:
            return spans

        def place(chapter: int) -> tuple[int, int] | None:
            for start, end in bounds:
                if start <= chapter <= end:
                    return (start, end)
            return None

        for asset in assets.values():
            for event in asset.events:
                key = place(event.chapter_ref)
                if key:
                    for actor in event.actors:
                        if actor and actor not in spans[key]["characters"]:
                            spans[key]["characters"].append(actor)
            for choice in asset.choices:
                chapter = asset.chapter_signals[0].chapter_ref if asset.chapter_signals else 1
                key = place(chapter)
                if key:
                    spans[key]["costs"].extend(c for c in choice.costs if c)
                    spans[key]["gains"].extend(g for g in choice.gains if g)
        return spans

    @staticmethod
    def _actors_by_chapter(assets: dict[str, BlockAsset]) -> dict[int, list[str]]:
        """Who acts in each chapter, from the events themselves."""
        by_chapter: dict[int, list[str]] = {}
        for asset in assets.values():
            for event in asset.events:
                seen = by_chapter.setdefault(event.chapter_ref, [])
                for actor in event.actors:
                    if actor and actor not in seen:
                        seen.append(actor)
        return by_chapter

    @staticmethod
    def _storylines(
        lifecycles: Sequence[Mapping[str, Any]],
        actors_by_chapter: Mapping[int, Sequence[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Project suspense lifecycles onto the storyline shape the UI renders.

        A thread that is opened, returned to and closed *is* a storyline; the two views
        differ in presentation, not in the underlying facts. Building both from one source
        keeps them from disagreeing about the same book.
        """
        # Ranked by how often the book returns to a thread, and only then by how far it
        # reaches. Ranking by span first put threads with a single node at the top of the
        # storyline page: a question asked once in chapter 266 and never revisited is not the
        # main storyline, however late the book stops mentioning it.
        ranked = sorted(
            lifecycles,
            key=lambda e: (len(e.get("events", [])),
                           int(e.get("chapter_end", 1)) - int(e.get("chapter_start", 1))),
            reverse=True,
        )[:24]
        # The mainline's chapters, so a subplot can be described by where it touches them
        # rather than by an adjective. Computed from the same ranking, before the loop.
        main_span: set[int] = set()
        for entry in ranked[:3]:
            main_span.update(
                range(int(entry.get("chapter_start", 1) or 1),
                      int(entry.get("chapter_end", 1) or 1) + 1)
            )

        lines: list[dict[str, Any]] = []
        for index, entry in enumerate(ranked, start=1):
            events = list(entry.get("events", []))
            start = int(entry.get("chapter_start", 1) or 1)
            end = max(start, int(entry.get("chapter_end", 1) or 1))
            participants: list[str] = []
            for chapter in range(start, end + 1):
                for actor in (actors_by_chapter or {}).get(chapter, ()):
                    if actor not in participants:
                        participants.append(actor)
            overlap = sorted(main_span.intersection(range(start, end + 1)))
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
                # A main storyline is one the book comes back to at least once and carries
                # furthest. The bar is "revisited", not "revisited three times": on a real
                # 806-chapter novel the most-returned-to thread had two nodes, so a
                # three-node rule labelled all 24 storylines subplots and the page claimed
                # the book has no mainline. A one-node thread is still never promoted — that
                # is a question asked once, whatever its span.
                "type": "main" if index <= 3 and len(nodes) >= 2 else "subplot",
                "importance": float(entry.get("importance", 0.0) or 0.0),
                "chapter_start": start,
                "chapter_end": end,
                "nodes": nodes,
                "participants": participants[:8],
                # A turning point in a thread is the moment it stops meaning what it meant.
                "turning_points": [
                    str(event.get("description", ""))
                    for event in events
                    if event.get("type") in ("twist", "reveal")
                ][:4],
                "relationship_to_mainline": (
                    "" if index <= 3 else
                    (f"与主线在第 {overlap[0]}–{overlap[-1]} 章重叠" if overlap else "独立于主线推进")
                ),
                "status": "resolved" if resolved else "open",
                "resolution": str(events[-1].get("description", "")) if resolved and events else "",
                "evidence": [e for event in events for e in event.get("evidence", ())][:5],
            }))
        return lines

    def _cite(self, block_key: str, fact: Any) -> list[str]:
        """Resolve a fact's paragraph citations to evidence ids a reader can follow.

        The index was being published with 3,362 real quotes in it and not one claim
        pointing at any of them, because the paragraph numbers a fact cites are block-local
        and nothing carried the block's mapping this far. Unresolvable anchors are dropped
        rather than passed through: an id that resolves to nothing is worse than no id, since
        the UI offers the reader a link that goes nowhere.
        """
        anchors = self._anchors.get(block_key, {})
        found: list[str] = []
        for ref in getattr(fact, "evidence", ()) or ():
            evidence_id = anchors.get(getattr(ref, "paragraph_ref", 0))
            if evidence_id and evidence_id not in found:
                found.append(evidence_id)
        return found[:3]

    def _chronology(self, assets: dict[str, BlockAsset]) -> list[dict[str, Any]]:
        """Events in the order the book tells them.

        ``story_order`` is set equal to ``narrative_order``: nothing in the L1 contract marks
        a flashback, so any difference between the two would be invented. Equal orders say
        "not detected", which is the truth here — they do not say "no flashbacks exist".
        """
        rows: list[tuple[int, str, list[str]]] = []
        for block_key, asset in assets.items():
            for event in asset.events:
                rows.append((event.chapter_ref, event.summary, self._cite(block_key, event)))
        rows.sort(key=lambda r: r[0])
        rows = spread(rows, _CHRONOLOGY_MAX)
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
        """Points worth naming on the pacing curve: turning points, and answered questions.

        Stage openings used to be marked too, one per act, which made ten of this book's twelve
        markers a second printing of the stage list — the chart sat directly beneath that list,
        so the marks added nothing a reader had not just read, and buried the two that did. A
        stage boundary is a division of the book; a marker should be a thing that happened in
        it.
        """
        markers: list[dict[str, Any]] = []
        for item in interpretations:
            if not isinstance(item, Mapping):
                continue
            start = int(item.get("chapter_start_order", 1) or 1)
            turn = str(item.get("turning_point", "")).strip()
            if turn:
                markers.append(conform(PacingMarker, {
                    "chapter": max(start, int(item.get("chapter_end_order", start) or start)),
                    "title": str(item.get("title", "")) or "转折",
                    "event": turn[:120],
                    "importance": 1.0,
                    "marker_type": "turning_point",
                    "effect_on_pacing": "推动进入下一阶段",
                }))
        for entry in list(lifecycles)[:8]:
            if str(entry.get("status")) in {"resolved", "partial"} and entry.get("events"):
                answered = str(entry.get("status")) == "resolved"
                markers.append(conform(PacingMarker, {
                    "chapter": int(entry.get("chapter_end", 1) or 1),
                    "title": "悬念收束" if answered else "悬念揭示",
                    "event": str(entry.get("question", ""))[:120],
                    "importance": 0.6 if answered else 0.4,
                    "marker_type": "major_event",
                    "effect_on_pacing": "张力释放" if answered else "张力部分释放",
                }))
        markers.sort(key=lambda m: m["chapter"])
        return markers[:40]

    @staticmethod
    def _name_stages(
        tracks: Mapping[str, Any], interpretations: Sequence[Mapping[str, Any]]
    ) -> None:
        """Label each point on a track with the stage its chapter falls in.

        Without it a track is a list of chapter numbers, and the reader has to hold the act
        structure in their head to know where 「对掌舵抵触 → 成为船长」 sits in the book.
        """
        spans = [
            (int(item.get("chapter_start_order", 1) or 1),
             int(item.get("chapter_end_order", 1) or 1),
             str(item.get("title", "")))
            for item in interpretations
            if isinstance(item, Mapping)
        ]
        if not spans:
            return
        for name in ("external_status_track", "ability_track",
                     "internal_belief_track", "relationship_track"):
            for point in tracks.get(name, []):
                chapter = int(point.get("chapter", 0) or 0)
                for start, end, title in spans:
                    if start <= chapter <= end:
                        point["stage_name"] = title
                        break

    @staticmethod
    def _protagonist_stages(
        interpretations: Sequence[Mapping[str, Any]],
        tracks: Mapping[str, Any] | None = None,
        spans: Mapping[tuple[int, int], Mapping[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """The lead's journey, told stage by stage out of the interpretations already paid for.

        The four tracks already say how the lead's status, ability, belief and relationships
        moved, chapter by chapter. Slicing them per stage answers the arc columns from the
        same facts, instead of leaving eleven of this row's fields declared and empty.
        """
        def moved(track: str, start: int, end: int) -> str:
            points = [
                point for point in (tracks or {}).get(track, [])
                if start <= int(point.get("chapter", 0) or 0) <= end
            ]
            if not points:
                return ""
            return str(points[-1].get("state", ""))

        stages: list[dict[str, Any]] = []
        for index, item in enumerate(interpretations, start=1):
            if not isinstance(item, Mapping):
                continue
            start = int(item.get("chapter_start_order", 1) or 1)
            end = max(start, int(item.get("chapter_end_order", start) or start))
            ledger = (spans or {}).get((start, end), {})
            stages.append(conform(ArcStage, {
                "status_change": moved("external_status_track", start, end),
                "ability_change": moved("ability_track", start, end),
                "internal_belief_change": moved("internal_belief_track", start, end),
                "relationship_change": moved("relationship_track", start, end),
                "cost_paid": list(ledger.get("costs", ()))[:4],
                "gain_received": list(ledger.get("gains", ()))[:4],
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
        spans: Mapping[tuple[int, int], Mapping[str, Any]] | None = None,
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
            start = int(item.get("chapter_start_order", 1) or 1)
            end = int(item.get("chapter_end_order", 1) or 1)
            span = spans.get((start, end), {}) if spans else {}
            stages.append(
                conform(
                    StoryStage,
                    {
                        **item,
                        "stage_id": item.get("stage_id") or f"STG-{index + 1}",
                        "chapter_start": start,
                        "chapter_end": end,
                        "title": item.get("title") or f"第{index + 1}幕",
                        # What the stage cost and who was in it are counted facts about its
                        # chapters, not things to ask an interpreter to remember.
                        "major_characters": list(span.get("characters", ()))[:8],
                        "cost_paid": list(span.get("costs", ()))[:6],
                        "gain_received": list(span.get("gains", ()))[:6],
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
            # a longer book would eventually blow the window (INV-18). Events, questions and
            # state changes are sampled evenly across the stage rather than truncated at the
            # front: they arrive in block order, so a prefix is the stage's opening and the
            # interpreter would describe that instead of the stage. The cast keeps its prefix
            # on purpose — order of appearance is a ranking there, not a position.
            seen: set[str] = set()
            unique_people = [p for p in people if not (p in seen or seen.add(p))]
            enriched.append(
                {
                    **entry,
                    "events": spread(events, 40),
                    "open_questions": spread(threads, 15),
                    "characters": unique_people[:20],
                    "state_changes": spread(state_changes, 20),
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

        # Centrality counted in mentions, not in clusters. Counting clusters gives every
        # character who appears anywhere in a block the same score of one, so in a five-block
        # extract the whole cast ties at five and the "protagonist" is whoever the sort
        # happened to leave first — which is how 山羊头 was named the lead of a book about
        # 邓肯, and how the growth tracks ended up following the wrong character.
        sizes = {cluster_key: len(members) for cluster_key, members, _ in clusters}
        folded: dict[str, dict[str, Any]] = {}
        for entity in resolve_entities(clusters):
            if _is_not_a_name(entity.display_surface_norm):
                continue
            row = folded.setdefault(
                entity.display_surface_norm,
                {
                    "entity_key": entity.entity_key,
                    "display_surface_norm": entity.display_surface_norm,
                    "centrality": 0,
                    "blocks": 0,
                    "evidence_ids": [],
                },
            )
            row["centrality"] += sum(
                sizes.get(member, 1) for member in entity.member_provisional_keys
            ) or 1
            row["blocks"] += 1
        # Appearing across many blocks breaks ties between characters with similar mention
        # counts: presence through the whole book beats a crowd scene.
        ranked = sorted(
            folded.values(), key=lambda r: (r["centrality"], r["blocks"]), reverse=True
        )
        return _fold_contracted_names(ranked)

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
            self._anchors[block.block_key] = result.evidence_by_anchor
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
        profile_axes: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        suspense_lifecycles = self._suspense_lifecycles(assets)
        # Which beats overturned an earlier one. Asked once over the whole book, because no
        # block can answer it — see ``_reversal_input``.
        reversals: list[dict[str, Any]] = []
        if self._find_reversals is not None:
            reveals = self._reversal_input(assets)
            if len(reveals) >= 2:
                reversals = self._accept_reversals(reveals, self._find_reversals(reveals))
        # The one judgement a block structurally cannot make: does this reveal answer that
        # question. Carrying the slate forward got threads recognised across blocks; whether
        # a thread is *answered* needs the whole book at once, so it is asked once here.
        if self._pair_threads is not None and suspense_lifecycles:
            pairing = self._pairing_input(assets)
            if pairing["threads"] and pairing["reveals"]:
                self._apply_pairs(suspense_lifecycles, pairing, self._pair_threads(pairing))
                report.provider_calls += 1
        relationships = self._relationships(assets)
        lead = entities[0]["display_surface_norm"] if entities else ""
        tracks = self._growth_tracks(assets, lead)
        goal_evolution, conflict_evolution = self._goal_and_conflict_evolution(assets)
        curve = resample_pacing_curve(signals)
        pacing = build_pacing_section(curve)
        pacing["pacing_regions"] = self._pacing_regions(
            pacing["points"], reading_drive_ranks(curve)
        )
        pacing["event_markers"] = self._event_markers(interpretations, suspense_lifecycles)
        self._annotate_pacing(pacing["points"], assets)
        chapters = build_chapters_section(
            chapters_topic,
            chapter_events=self._events_by_chapter(assets),
            chapter_evidence=self._evidence_by_chapter(assets),
        )
        tracks["initial_goal"], tracks["final_goal"] = self._lead_goals(assets, lead)
        self._name_stages(tracks, interpretations)
        # After the tracks are named, so the arc stages can slice them.
        tracks["stages"] = self._protagonist_stages(
            interpretations, tracks, self._stage_spans(assets, interpretations)
        )

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
                storylines=self._storylines(
                    suspense_lifecycles, self._actors_by_chapter(assets)
                ),
                chronology=self._chronology(assets),
                spans=self._stage_spans(assets, interpretations),
            ),
            suspense={
                "availability": "available" if suspense_lifecycles else "unavailable",
                "lifecycles": suspense_lifecycles,
            },
            characters=build_characters_section(
                entities,
                relationships=relationships,
                tracks=tracks,
                character_facts=self._character_facts(
                    assets,
                    [str(e.get("display_surface_norm", "")) for e in entities[:C.CHARACTERS_MAX]],
                    lead,
                ),
            ),
            overview=build_overview_section(
                overview,
                entities,
                goal_evolution=goal_evolution,
                conflict_evolution=conflict_evolution,
                turning_points=self._turning_points(interpretations),
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
            journey=self._journey(
                assets, profile_axes, len(signals),
                stages=tracks.get("stages") or [], lead=lead, reversals=reversals,
            ),
        )

    def _ledger(
        self, assets: dict[str, BlockAsset], stages: Sequence[Mapping[str, Any]], lead: str
    ) -> list[dict[str, Any]]:
        """Gather the per-stage ledger inputs. All three come from facts already extracted.

        A relationship change is dated by the block it came from rather than by a field: the
        L1 shape carries no ``chapter_ref`` on relationship or choice rows, so the block's own
        first chapter is the tightest honest bound available.
        """
        meetings: list[dict[str, Any]] = []
        choices: list[dict[str, Any]] = []
        for asset in assets.values():
            first = min((signal.chapter_ref for signal in asset.chapter_signals), default=1)
            for change in asset.relationship_changes:
                left, right = change.from_entity_ref, change.to_entity_ref
                if lead not in (left, right):
                    continue
                meetings.append({
                    "chapter": first,
                    "other": right if left == lead else left,
                    "relation": change.relation,
                })
            for choice in asset.choices:
                choices.append({
                    "entity_ref": choice.entity_ref, "chapter": first,
                    "gains": list(choice.gains), "costs": list(choice.costs),
                })
        events = [
            {"chapter": event.chapter_ref, "text": event.summary}
            for asset in assets.values()
            for event in asset.events
            if lead in event.actors
        ]
        return build_stage_ledger(
            stages, lead=lead, meetings=meetings, events=events, choices=choices
        )

    def _journey(
        self,
        assets: dict[str, BlockAsset],
        profile_axes: Mapping[str, Any] | None,
        chapter_count: int,
        *,
        stages: Sequence[Mapping[str, Any]] = (),
        lead: str = "",
        reversals: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        """Feed the journey builder from the assets; it decides the axis from the profile.

        Everything here is already in hand — the book was read once, and screen time, ladder
        readings and suspense actions all come out of the same block assets. No extra call.
        """
        actors = self._actors_by_chapter(assets)
        bins = min(C.PACING_CURVE_BINS_MAX, max(1, chapter_count))
        width = max(1, chapter_count) / bins
        counts: dict[str, list[int]] = {}
        spans: dict[str, tuple[int, int, int]] = {}
        appearances: dict[str, set[int]] = {}
        for chapter, names in actors.items():
            index = min(bins - 1, int((max(1, chapter) - 1) / width))
            for name in names:
                if _is_not_a_name(name):
                    continue
                counts.setdefault(name, [0] * bins)[index] += 1
                appearances.setdefault(name, set()).add(chapter)
        for name, chapters in appearances.items():
            spans[name] = (min(chapters), max(chapters), len(chapters))
        # Only the leading cast gets a band; the rest would be a hairline nobody can read.
        top = sorted(counts, key=lambda name: -sum(counts[name]))[: C.CHARACTERS_MAX // 3 or 8]

        return build_journey_section(
            axes=profile_axes,
            chapter_count=chapter_count,
            ledger=self._ledger(assets, stages, lead),
            # The confirmed reversals are appended as `twist` actions. They are the only
            # source of downward movement on the cognition axis: block extraction produced
            # one twist in 806 chapters, so a curve built from its output alone can only rise.
            suspense_actions=[
                {"action_kind": action.action_kind, "chapter_ref": action.chapter_ref,
                 "information_added": action.information_added,
                 "evidence_ids": self._cite(key, action.evidence)}
                for key, asset in assets.items()
                for action in asset.suspense_actions
                if action.action_kind != "twist"
            ] + [
                {"action_kind": "twist", "chapter_ref": row["chapter"],
                 "information_added": row["why"] or row["text"], "evidence_ids": []}
                for row in reversals
            ],
            power_beats=[
                {"entity_ref": beat.entity_ref, "chapter_ref": beat.chapter_ref,
                 "kind": beat.kind, "level": beat.level, "why": beat.why,
                 "rank": parse_rank(beat.level),
                 "evidence_ids": self._cite(key, beat.evidence)}
                for key, asset in assets.items()
                for beat in getattr(asset, "power_beats", [])
            ],
            screen_time={name: counts[name] for name in top},
            screen_time_spans={name: spans[name] for name in top},
            bins=bins,
        )
