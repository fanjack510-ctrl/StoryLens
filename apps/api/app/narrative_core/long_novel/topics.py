"""L3 topic projections, assessment and L4 final synthesis (03 §5–§6).

Every projection here is bounded by a **fixed cap**, not by the book. That is the property
the whole rebuild exists for: the old shape fed growing inputs upward, so a long novel either
blew the context window mid-run — after most of the money was spent — or was silently
trimmed. Here the size of what goes to a provider is decided by constants and top-K
selections, and anything dropped is recorded in ``projection_omitted_json`` rather than
quietly discarded.

The pacing projection deserves its own note. It used to send one aggregated row per
Reduction Partition, and partitions grow linearly with chapter count — so it was `O(book
length)` while sitting under a heading that claimed every projection was bounded. It only
looked safe because the largest book anyone tested still fit. The curve is now resampled to
``PACING_CURVE_BINS_MAX`` bins, so the payload is the same size for a 500-chapter novel and a
30,000-chapter one, and the binning is disclosed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from app.narrative_core.long_novel import constants as C
from app.narrative_core.long_novel import ids
from app.narrative_core.long_novel.contracts.enums import Topic, UnitKind

__all__ = [
    "ChapterSignalRow",
    "PacingCurve",
    "resample_pacing_curve",
    "build_chapters_topic",
    "TopicProjection",
    "project_topic",
    "TopicDigest",
    "build_digest",
    "build_stage_digest",
    "build_assessment_input",
    "build_final_input",
]


def spread(items: Sequence[Any], k: int) -> list[Any]:
    """``k`` items taken evenly across ``items``, order preserved.

    A prefix — ``items[:k]`` — is the cheap way to bound a list and the wrong one whenever the
    list is in book order, because it hands the reader the beginning of the range and nothing
    else. That is how a layer that has the whole book available ends up describing its opening.
    """
    if k <= 0:
        return []
    if len(items) <= k:
        return list(items)
    return [items[(i * len(items)) // k] for i in range(k)]


@dataclass(frozen=True)
class ChapterSignalRow:
    """One chapter's countable signals, as L1 recorded them."""

    chapter_order: int
    dialogue_paragraphs: int = 0
    action_paragraphs: int = 0
    interiority_paragraphs: int = 0
    scene_breaks: int = 0
    new_information_beats: int = 0
    hook_present: bool = False
    cap_saturated: bool = False


@dataclass
class PacingCurve:
    """A fixed-size curve plus the disclosure of how it was produced."""

    bins: list[dict[str, float]]
    resampled: bool
    chapters_per_bin: float
    n_chapters: int

    def omitted(self) -> dict[str, Any]:
        return {
            "resampled": self.resampled,
            "chapters_per_bin": round(self.chapters_per_bin, 2),
            "n_chapters": self.n_chapters,
            "bins": len(self.bins),
        }


def resample_pacing_curve(
    signals: Sequence[ChapterSignalRow], *, bins_max: int = C.PACING_CURVE_BINS_MAX
) -> PacingCurve:
    """Reduce a whole-book curve to at most ``bins_max`` bins, deterministically.

    Bin edges are ``floor(i * n_chapters / bins)``, so the same book always produces the same
    bins and therefore the same provider input fingerprint. When the book has fewer chapters
    than bins there is one bin per chapter and nothing is lost.

    The engine keeps the full per-chapter curve for storage, display and metrics; only what
    is *sent* is capped.
    """
    ordered = sorted(signals, key=lambda s: s.chapter_order)
    n = len(ordered)
    if n == 0:
        return PacingCurve(bins=[], resampled=False, chapters_per_bin=0.0, n_chapters=0)

    bins_count = min(bins_max, n)
    edges = [(i * n) // bins_count for i in range(bins_count + 1)]
    bins: list[dict[str, float]] = []
    for i in range(bins_count):
        group = ordered[edges[i] : edges[i + 1]] or [ordered[min(edges[i], n - 1)]]
        size = len(group)
        bins.append(
            {
                "bin": i,
                "from_chapter": group[0].chapter_order,
                "to_chapter": group[-1].chapter_order,
                "dialogue": round(sum(g.dialogue_paragraphs for g in group) / size, 2),
                "action": round(sum(g.action_paragraphs for g in group) / size, 2),
                "interiority": round(sum(g.interiority_paragraphs for g in group) / size, 2),
                "beats": round(sum(g.new_information_beats for g in group) / size, 2),
                "hooks": round(sum(1 for g in group if g.hook_present) / size, 2),
            }
        )
    return PacingCurve(
        bins=bins,
        resampled=n > bins_max,
        chapters_per_bin=n / bins_count,
        n_chapters=n,
    )


def build_chapters_topic(signals: Sequence[ChapterSignalRow]) -> dict[str, Any]:
    """The ``chapters`` topic: a deterministic merge, **zero provider calls**.

    It is the full per-chapter table, which is exactly why it must never be sent anywhere:
    its size grows with the book. It is computed locally and its *digest* — aggregate
    counters only — is what any upper layer sees.
    """
    ordered = sorted(signals, key=lambda s: s.chapter_order)
    return {
        "chapters": [
            {
                "chapter_order": s.chapter_order,
                "dialogue_paragraphs": s.dialogue_paragraphs,
                "action_paragraphs": s.action_paragraphs,
                "interiority_paragraphs": s.interiority_paragraphs,
                "new_information_beats": s.new_information_beats,
                "hook_present": s.hook_present,
                "cap_saturated": s.cap_saturated,
            }
            for s in ordered
        ],
        "chapter_count": len(ordered),
        "saturated_chapter_count": sum(1 for s in ordered if s.cap_saturated),
    }


@dataclass
class TopicProjection:
    """What one topic will send, plus what it left out."""

    topic: Topic
    payload: dict[str, Any]
    omitted: dict[str, Any] = field(default_factory=dict)
    projection_fingerprint: str = ""
    provider_input_fingerprint: str | None = None

    @property
    def is_provider_backed(self) -> bool:
        return self.topic.is_provider_backed


def _top_k(items: Sequence[Any], k: int, key: Callable[[Any], float]) -> tuple[list[Any], int]:
    ranked = sorted(items, key=key, reverse=True)
    return ranked[:k], max(0, len(ranked) - k)


def _weight(event: Mapping[str, Any]) -> float:
    return float(event.get("weight", 0) or 0)


def _cover_stages(
    events: Sequence[Mapping[str, Any]], stages: Sequence[Mapping[str, Any]], budget: int
) -> tuple[list[Any], int]:
    """The event budget, allocated across the stages so every act is represented.

    A plain top-K over the whole book ranks by evidence count, and evidence counts tie
    constantly — one or two citations is the norm. ``sorted`` is stable, so the ties resolve in
    extraction order and the survivors are the earliest blocks. On 《系统豪横》 that handed the
    story topic eight events, all from the first act, and the topic's summary said as much.

    Stage chapter ranges are disjoint (a stage groups whole partitions, and a block belongs to
    exactly one), so no event is picked twice. Within a stage the same tie problem recurs at a
    smaller scale, so events on the cut line are spread across the stage rather than taken in
    order — otherwise each act would be represented by its own first few chapters.
    """
    if not stages:
        return _top_k(events, budget, _weight)
    per_stage = max(1, budget // len(stages))
    picked: list[Any] = []
    for stage in stages:
        start = int(stage.get("chapter_start_order", 1) or 1)
        end = int(stage.get("chapter_end_order", start) or start)
        inside = sorted(
            (e for e in events if start <= int(e.get("chapter_ref", 0) or 0) <= end),
            key=_weight,
            reverse=True,
        )
        if len(inside) > per_stage:
            cutoff = _weight(inside[per_stage - 1])
            above = [e for e in inside if _weight(e) > cutoff]
            on_the_line = sorted(
                (e for e in inside if _weight(e) == cutoff),
                key=lambda e: int(e.get("chapter_ref", 0) or 0),
            )
            inside = above + spread(on_the_line, per_stage - len(above))
        picked.extend(inside)
    picked.sort(key=lambda e: int(e.get("chapter_ref", 0) or 0))
    return picked, max(0, len(events) - len(picked))


def project_topic(
    topic: Topic,
    *,
    stages: Sequence[Mapping[str, Any]],
    entities: Sequence[Mapping[str, Any]] = (),
    threads: Sequence[Mapping[str, Any]] = (),
    events: Sequence[Mapping[str, Any]] = (),
    signals: Sequence[ChapterSignalRow] = (),
) -> TopicProjection:
    """Build one topic's bounded input.

    Every branch selects a fixed top-K and records the remainder. A projection that silently
    dropped its tail would look identical to one that had nothing more to say.
    """
    omitted: dict[str, Any] = {}
    selected_keys: list[str] = []

    if topic is Topic.CHAPTERS:
        # Deterministic: no payload is ever sent, so there is no fingerprint and no cost.
        return TopicProjection(
            topic=topic,
            payload=build_chapters_topic(signals),
            omitted={},
            projection_fingerprint=ids.projection_fingerprint(
                [str(s.chapter_order) for s in signals], C.PROJECTION_ALGORITHM_VERSION
            ),
            provider_input_fingerprint=None,
        )

    if topic is Topic.STORY:
        picked, dropped = _cover_stages(events, stages, 8 * max(1, len(stages)))
        omitted = {"events_dropped": dropped}
        payload = {"stages": list(stages), "events": picked}
        selected_keys = [str(e.get("fact_key", "")) for e in picked]

    elif topic is Topic.CHARACTERS:
        picked, dropped = _top_k(entities, C.CHARACTERS_MAX, lambda e: e.get("centrality", 0))
        omitted = {"entities_dropped": dropped, "cap": C.CHARACTERS_MAX}
        payload = {"stages": list(stages), "entities": picked}
        selected_keys = [str(e.get("entity_key", "")) for e in picked]

    elif topic is Topic.SUSPENSE:
        picked, dropped = _top_k(threads, 40, lambda t: t.get("salience", 0))
        omitted = {"threads_dropped": dropped}
        payload = {"stages": list(stages), "threads": picked}
        selected_keys = [str(t.get("thread_key", "")) for t in picked]

    elif topic is Topic.PACING:
        curve = resample_pacing_curve(signals)
        omitted = curve.omitted()
        payload = {
            "curve": curve.bins,
            "stage_boundaries": [
                {"stage_seq": s.get("stage_seq"), "from_chapter": s.get("chapter_start_order")}
                for s in stages
            ],
        }
        selected_keys = [f"bin{b['bin']}" for b in curve.bins]

    else:  # assessment is assembled separately from digests
        raise ValueError(f"{topic} is not a primary projection; use build_assessment_input")

    projection = TopicProjection(
        topic=topic,
        payload=payload,
        omitted=omitted,
        projection_fingerprint=ids.projection_fingerprint(
            selected_keys, C.PROJECTION_ALGORITHM_VERSION
        ),
    )
    projection.provider_input_fingerprint = ids.provider_input_fingerprint(
        UnitKind.TOPIC.value, C.SEMANTIC_CONTRACT_VERSION, payload
    )
    return projection


@dataclass(frozen=True)
class TopicDigest:
    """A topic's result compressed to a fixed budget, for the layers above it.

    Assessment and Final read digests, never full topic results. A ``TopicResult`` can be up
    to its whole output target, and six of them would exceed a 32K window on their own — the
    original contract did exactly that, which made Final's input unbounded in book length.
    """

    topic: Topic
    digest: dict[str, Any]
    fingerprint: str

    @property
    def approx_tokens(self) -> int:
        return len(ids.canonical_json(self.digest)) // 3


def build_digest(topic: Topic, result: Mapping[str, Any]) -> TopicDigest:
    """Compress one topic result to at most ``TOPIC_DIGEST_MAX_TOKENS``.

    For ``chapters`` the digest is **aggregate-only** — distribution counters, never one row
    per chapter. That single rule is what removes the last book-length term from the layers
    above.
    """
    if topic is Topic.CHAPTERS:
        chapters = result.get("chapters", []) or []
        digest: dict[str, Any] = {
            "chapter_count": result.get("chapter_count", len(chapters)),
            "saturated_chapter_count": result.get("saturated_chapter_count", 0),
            "hook_rate": round(
                sum(1 for c in chapters if c.get("hook_present")) / max(1, len(chapters)), 3
            ),
        }
    else:
        digest = {
            k: v
            for k, v in result.items()
            if k in {"summary", "headline", "claims", "top_findings", "regions", "arcs"}
        }
        # Hard trim rather than hope: a digest that overruns is a budget violation upstream.
        while len(ids.canonical_json(digest)) // 3 > C.TOPIC_DIGEST_MAX_TOKENS and digest:
            longest = max(digest, key=lambda k: len(ids.canonical_json(digest[k])))
            if isinstance(digest[longest], list) and digest[longest]:
                digest[longest] = digest[longest][:-1]
            else:
                digest.pop(longest)

    return TopicDigest(
        topic=topic, digest=digest, fingerprint=ids.digest_fingerprint(digest)
    )


#: What a stage interpretation contributes to the layers above it. The rest of what the
#: interpreter returns stays at L2: the cost/gain ledger and the cast list belong to the stage
#: card, not to a judgement about the whole book.
_STAGE_DIGEST_FIELDS: tuple[str, ...] = ("title", "summary", "turning_point", "next_question")


def build_stage_digest(
    stage_skeleton: Sequence[Mapping[str, Any]],
    interpretations: Sequence[Mapping[str, Any]] = (),
    *,
    key_events_per_stage: int = 6,
) -> list[dict[str, Any]]:
    """The stage list as the layers above it should see it: ranges **and what happened in them**.

    Assessment and Final were handed ``stage_skeleton`` — a sequence number, a key and a chapter
    range. The stage interpretations sitting beside it had already been paid for, already
    covered the whole book, and were passed only to the renderer. So the one call that writes
    全书总览 was asked to summarise a novel from four integers per act plus whatever plot had
    survived into the topic digests, and what survives there is the opening: measured on
    《系统豪横》, an 84-chapter book whose ``full_summary`` ended at chapter 11.

    Bounded by construction — at most ``MAX_STAGES`` rows, each a fixed field set — so this
    stays O(1) in book length, which is the property the whole layer exists to hold.
    """
    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(list(stage_skeleton)[: C.MAX_STAGES]):
        row: dict[str, Any] = {
            "stage_seq": entry.get("stage_seq", index),
            "chapter_start_order": entry.get("chapter_start_order", 1),
            "chapter_end_order": entry.get("chapter_end_order", 1),
        }
        interpreted = interpretations[index] if index < len(interpretations) else {}
        if not isinstance(interpreted, Mapping):
            interpreted = {}
        for field_name in _STAGE_DIGEST_FIELDS:
            value = str(interpreted.get(field_name, "") or "").strip()
            if value:
                row[field_name] = value
        events = [str(e).strip() for e in (interpreted.get("key_events") or ()) if str(e).strip()]
        if events:
            row["key_events"] = spread(events, key_events_per_stage)
        rows.append(row)
    return rows


def build_assessment_input(
    digests: Sequence[TopicDigest],
    *,
    stages: Sequence[Mapping[str, Any]],
    quality_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    """Assessment reads the five ``TopicDigest``s — four provider topics plus ``chapters``."""
    return {
        "digests": {d.topic.value: d.digest for d in digests},
        "stages": list(stages),
        "quality_metrics": dict(quality_metrics),
    }


def build_final_input(
    digests: Sequence[TopicDigest],
    *,
    stages: Sequence[Mapping[str, Any]],
    assessment_digest: Mapping[str, Any],
    selected_evidence_ids: Sequence[str],
    quality_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    """Final reads six digests plus a bounded evidence selection — never a topic result."""
    return {
        "digests": {d.topic.value: d.digest for d in digests},
        "assessment": dict(assessment_digest),
        "stages": list(stages),
        "evidence_ids": list(selected_evidence_ids)[:200],
        "quality_metrics": dict(quality_metrics),
    }
