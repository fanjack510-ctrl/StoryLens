"""L0-A / L0-C — the deterministic half of the profile layer (10_ADAPTIVE_PROFILE_LAYER §6).

Everything here is counted over 100% of the book and costs nothing. That is the whole point:
a statistic over the whole text beats a model's impression of a sample, and it beats it for
free.

The case that settled the design: 《深海余烬》 opens with one man alone on a ship and becomes
four parallel plotlines. Measured on the real 806-chapter text —

    whole book      share(1) = 0.393  ->  ensemble      (correct)
    first tenth     share(1) = 0.538  ->  single_lead   (wrong)

— so any viewpoint verdict drawn from the opening is wrong by construction, and the free
whole-book count is what makes it right.

**These functions produce priors, never verdicts.** The vocabulary hit rates in particular
are crude; nothing derived from them alone may reach the user-facing report. They exist to
give the sampled model read (L0-B) a starting point and to give the confirmation gate
something to show the user. The user's confirmation is what becomes authoritative (INV-P2).
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

__all__ = [
    "BookStatistics",
    "NameDistribution",
    "PROGRESSION_VOCAB",
    "ROMANCE_VOCAB",
    "MYSTERY_VOCAB",
    "book_statistics",
    "monetization_prior",
    "engine_prior",
    "name_distribution",
    "pov_from_distribution",
]

#: Paragraph-level dialogue is detected by quotation marks rather than by a model. Both the
#: straight and the corner forms appear in Chinese web fiction, often in the same book.
QUOTE_MARKS = ("「", "」", "“", "”", "‘", "’", "『", "』")

PROGRESSION_VOCAB = ("境界", "等级", "修为", "突破", "升级", "系统", "面板", "属性", "灵力", "丹药")
ROMANCE_VOCAB = ("心动", "脸红", "告白", "在意", "亲吻", "拥抱", "喜欢你", "心跳")
MYSTERY_VOCAB = ("线索", "真相", "凶手", "证据", "推理", "伏笔", "疑点", "调查")

#: Above this median chapter length a book reads as paid-subscription rather than the
#: 1500–2500 character chapters of the free ad-supported platforms. Provisional: it separates
#: 深海余烬 (median 3103) from the fast-food shape, but wants calibration on a labelled
#: corpus before it is treated as anything but a prior (§13, still open).
FAST_FOOD_CHAPTER_CHARS_MAX = 2_600

#: Viewpoint thresholds over the share of the top ten characters' mentions. Provisional for
#: the same reason; recorded here so a future calibration has one place to change.
SINGLE_LEAD_SHARE_MIN = 0.45
SINGLE_LEAD_RUNNER_UP_MAX = 0.20
DUAL_LEAD_COMBINED_MIN = 0.55
DUAL_LEAD_GAP_MAX = 0.15

DECILES = 10


@dataclass(frozen=True)
class BookStatistics:
    """Counted properties of the whole text. No judgement, no provider call."""

    chapters: int
    total_chars: int
    chapter_chars_p10: int
    chapter_chars_median: float
    chapter_chars_p90: int
    paragraphs_per_chapter_median: float
    dialogue_ratio: float
    tail_length_median: float
    tail_punctuation: dict[str, int] = field(default_factory=dict)
    vocabulary_per_10k: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class NameDistribution:
    """Where each candidate name appears across the book, in tenths."""

    per_name_total: dict[str, int]
    per_name_deciles: dict[str, list[int]]
    share_first: float
    share_second: float


def book_statistics(chapter_texts: Sequence[str]) -> BookStatistics:
    """Count the whole book. ``chapter_texts`` is every chapter's body, in reading order."""
    if not chapter_texts:
        raise ValueError("book_statistics needs at least one chapter")

    chars: list[int] = []
    paragraph_counts: list[int] = []
    dialogue_paragraphs = 0
    total_paragraphs = 0
    tail_lengths: list[int] = []
    tail_punctuation: Counter[str] = Counter()

    for body in chapter_texts:
        body = body or ""
        chars.append(len(body))
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        paragraph_counts.append(len(lines))
        total_paragraphs += len(lines)
        dialogue_paragraphs += sum(1 for line in lines if any(q in line for q in QUOTE_MARKS))
        if lines:
            tail_lengths.append(len(lines[-1]))
            tail_punctuation[lines[-1][-1]] += 1

    ordered = sorted(chars)
    whole = "".join(chapter_texts)
    per_10k = len(whole) / 10_000 or 1.0
    vocabulary = {
        name: round(sum(whole.count(word) for word in words) / per_10k, 2)
        for name, words in (
            ("progression", PROGRESSION_VOCAB),
            ("romance", ROMANCE_VOCAB),
            ("mystery", MYSTERY_VOCAB),
        )
    }

    return BookStatistics(
        chapters=len(chapter_texts),
        total_chars=len(whole),
        chapter_chars_p10=ordered[len(ordered) // 10],
        chapter_chars_median=statistics.median(ordered),
        chapter_chars_p90=ordered[len(ordered) * 9 // 10],
        paragraphs_per_chapter_median=statistics.median(paragraph_counts),
        dialogue_ratio=round(dialogue_paragraphs / max(1, total_paragraphs), 4),
        tail_length_median=statistics.median(tail_lengths) if tail_lengths else 0.0,
        tail_punctuation=dict(tail_punctuation.most_common(8)),
        vocabulary_per_10k=vocabulary,
    )


def monetization_prior(stats: BookStatistics) -> str:
    """Axis 1 prior from chapter length.

    Chapter length is a proxy: the platform a book was written for is metadata, not a text
    property. The user may override this at import, and their choice wins (§8.3).
    """
    return (
        "fast_food_free"
        if stats.chapter_chars_median <= FAST_FOOD_CHAPTER_CHARS_MAX
        else "paid_subscription"
    )


def engine_prior(stats: BookStatistics) -> str:
    """Axis 3 prior from vocabulary hit rates. The weakest signal here — a prior only."""
    hits = stats.vocabulary_per_10k
    if not hits or not any(hits.values()):
        return ""
    return max(hits, key=lambda key: hits[key])


def name_distribution(
    chapter_texts: Sequence[str], candidate_names: Sequence[str]
) -> NameDistribution:
    """Count each candidate name across the book and across its tenths.

    Candidates come from the sampled model read (L0-B); the counting is done here over the
    whole text. Naming is what a model is good at and counting is what it is bad at, so each
    does the half it can be trusted with.
    """
    names = [name for name in dict.fromkeys(candidate_names) if name]
    if not names:
        return NameDistribution({}, {}, 0.0, 0.0)

    chapters = len(chapter_texts)
    buckets = [""] * DECILES
    for index, body in enumerate(chapter_texts):
        buckets[min(DECILES - 1, index * DECILES // max(1, chapters))] += body or ""

    whole = "".join(buckets)
    totals = {name: whole.count(name) for name in names}
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    top_ten_total = sum(count for _, count in ranked[:10]) or 1

    return NameDistribution(
        per_name_total=dict(ranked),
        per_name_deciles={
            name: [bucket.count(name) for bucket in buckets] for name, _ in ranked[:10]
        },
        share_first=round(ranked[0][1] / top_ten_total, 4),
        share_second=round(ranked[1][1] / top_ten_total, 4) if len(ranked) > 1 else 0.0,
    )


def pov_from_distribution(distribution: NameDistribution) -> str:
    """Axis 4 from counted mentions.

    This is the one axis the deterministic layer decides on its own, because it is the one a
    sample gets wrong: measured on 深海余烬, the opening tenth says ``single_lead`` and the
    whole book says ``ensemble``.
    """
    first, second = distribution.share_first, distribution.share_second
    if not first:
        return ""
    if first >= SINGLE_LEAD_SHARE_MIN and second < SINGLE_LEAD_RUNNER_UP_MAX:
        return "single_lead"
    if first + second >= DUAL_LEAD_COMBINED_MIN and abs(first - second) < DUAL_LEAD_GAP_MAX:
        return "dual_lead"
    return "ensemble"


def draft_profile(
    chapter_texts: Sequence[str], candidate_names: Sequence[str] = ()
) -> dict[str, Any]:
    """The deterministic half of a draft profile, with the evidence behind each value.

    Every value carries what it was computed from, because the user has to confirm this and
    cannot confirm a bare verdict (§8.2).
    """
    stats = book_statistics(chapter_texts)
    distribution = name_distribution(chapter_texts, candidate_names)
    return {
        "monetization": {
            "value": monetization_prior(stats),
            "source": "L0-A",
            "evidence": {"chapter_chars_median": stats.chapter_chars_median},
        },
        "engine": {
            "value": engine_prior(stats),
            "source": "L0-A",
            "evidence": stats.vocabulary_per_10k,
        },
        "pov": {
            "value": pov_from_distribution(distribution),
            "source": "L0-C",
            "evidence": {
                "share_first": distribution.share_first,
                "share_second": distribution.share_second,
                "per_name_total": dict(list(distribution.per_name_total.items())[:10]),
            },
        },
        "statistics": stats.__dict__,
        "name_deciles": distribution.per_name_deciles,
    }


def merge_confirmed(draft: Mapping[str, Any], user_choice: Mapping[str, str]) -> dict[str, Any]:
    """Apply the user's dropdown selections over the draft.

    An axis the user touched is marked ``source: "user"`` and outranks every later inference,
    including L2's whole-book recomputation, which may only report a disagreement (INV-P2).
    """
    confirmed = {key: dict(value) for key, value in draft.items() if isinstance(value, Mapping)}
    for axis, value in user_choice.items():
        if not value:
            continue
        confirmed.setdefault(axis, {})
        confirmed[axis] = {**confirmed.get(axis, {}), "value": value, "source": "user"}
    return confirmed
