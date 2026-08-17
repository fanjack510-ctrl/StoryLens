"""Adapter: LongNovelAnalysisEngine results → the existing ``WholeBookAnalysisV2`` document.

The frozen design's first commitment is an **unchanged external contract**: the new engine
replaces how a novel is analysed, not what the product shows. So the last mile is a
translation, and the desktop UI needs no change at all.

Two things are genuinely better on this side of the translation and are worth knowing:

**The 0–100 pacing scores are computed by the engine, not guessed by a model.** They are
whole-book percentile ranks over counted signals, so the same book scores the same way twice.
The old shape asked a model for the numbers, which is why they moved between runs.

**Every claim can carry an evidence id that resolves to a real paragraph.** ``evidence_index``
is populated from rows that were validated against the rendered text at extraction time, so a
reader can be shown the sentence a claim came from rather than asked to trust it.

Where the new engine has nothing to say, the section is marked ``unavailable`` rather than
filled with plausible text. An empty section the user can see is honest; an invented one is
the failure mode this rebuild exists to end.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from pydantic import BaseModel

from app.narrative_core.long_novel.constants import CHARACTERS_MAX as C_CHARACTERS_MAX
from app.narrative_core.long_novel.topics import ChapterSignalRow, PacingCurve, spread as _sample
from app.narrative_core.whole_book_v2.contracts import (
    JourneyPoint,
    JourneyResult,
    LedgerEvent,
    LedgerMeeting,
    RevisionPriority,
    ScreenTimeBand,
    StageLedger,
    StoryBreakdownResult,
    TypeProfile,
)

__all__ = [
    "conform",
    "percentile_scores",
    "build_pacing_section",
    "build_chapters_section",
    "build_characters_section",
    "build_assessment_section",
    "evidence_in_range",
    "build_overview_section",
    "build_type_profile_section",
    "build_journey_section",
    "build_stage_ledger",
    "parse_rank",
    "to_whole_book_v2",
]


def str_list(value: Any) -> list[str]:
    """Model output for a list-of-strings field, coerced without shredding it.

    A model asked for a list sometimes answers with one string, and ``[str(x) for x in value]``
    then iterates its characters. That is not a hypothetical: the first revision priority of a
    real run reached the printed report as twenty-seven one-character bullets — 保 / 持 / 法 /
    律 / … — because its ``preserve`` note came back as prose. A string is one item.
    """
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, Mapping):
        return []
    if not isinstance(value, Sequence):
        text = str(value).strip()
        return [text] if text else []
    return [str(x).strip() for x in value if str(x).strip()]


def conform(model: type[BaseModel], values: Mapping[str, Any]) -> dict[str, Any]:
    """Fill every field the contract declares, taking what ``values`` supplies.

    Hand-writing these dicts produced the same defect three times — a section that looks
    complete, validates field by field, and fails as a whole because a sibling the author
    never saw is required. Reading the field list off the model makes that impossible: a
    field added to the contract later gets a typed empty here instead of a runtime failure
    at the end of a paid run.

    Empties are typed, never invented: a missing string is ``""`` and a missing list is
    ``[]``, both of which render as "nothing to say". Filling them with plausible prose is
    the failure this engine exists to prevent.
    """
    out: dict[str, Any] = {}
    for name, field in model.model_fields.items():
        if name in values and values[name] is not None:
            out[name] = values[name]
            continue
        annotation = field.annotation
        origin = getattr(annotation, "__origin__", None)
        # A field that may be None *is* filled by being None — that is what the contract says
        # the empty case looks like. Without this the union falls through to the string branch
        # below and an optional bool is written as `""`, which then fails validation at the last
        # step of a paid run. Found when a deprecated flag was made optional for backward
        # compatibility and every fresh row started carrying an empty string in its place.
        if type(None) in getattr(annotation, "__args__", ()):
            out[name] = None
        elif origin in (list, tuple) or annotation in (list, tuple):
            out[name] = []
        elif annotation is int:
            out[name] = 0
        elif annotation is float:
            out[name] = 0.0
        elif annotation is bool:
            out[name] = False
        else:
            out[name] = ""
    return out


def percentile_scores(values: Sequence[float]) -> list[int]:
    """Rank values to 0–100 by position in the whole-book distribution.

    Percentile rather than a raw scale because "tense" only means anything relative to the
    rest of *this* book: a quiet thriller and a loud romance both need their peaks to read as
    peaks. Ties share a rank, so a flat stretch does not manufacture variation.
    """
    if not values:
        return []
    ordered = sorted(values)
    n = len(ordered)
    scores: list[int] = []
    for value in values:
        below = sum(1 for v in ordered if v < value)
        equal = sum(1 for v in ordered if v == value)
        # midpoint of the tied band, so equal inputs get equal scores
        scores.append(round(100 * (below + equal / 2) / n))
    return scores


def reading_drive_ranks(curve: PacingCurve) -> list[int]:
    """"Would a reader keep going", per bin, as a within-book percentile.

    This composite used to be published as a fourth curve, which is why it had to go: it is
    ``2×hooks + beats``, so it sat on the chart between the two curves it is made of and moved
    with both. As a *signal* it is still the right one — a run of low values is what a reader
    experiences as a slow stretch, and the fatigue regions it finds are the assessment's most
    actionable output (第 43–45 章 on 《系统豪横》). So it is computed and used, not drawn.
    """
    return percentile_scores([b["hooks"] * 2 + b["beats"] for b in curve.bins])


def build_pacing_section(
    curve: PacingCurve, *, regions: Sequence[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """Turn the bounded curve into the UI's pacing points, with engine-computed scores.

    Three curves, not six. The six were five counters recombined: ``reading_drive`` was
    ``2×hooks + beats`` and therefore a weighted sum of two curves already on the chart —
    measured on 《系统豪横》 it correlated 0.73 with ``hook_density`` and 0.65 with
    ``plot_progress``; ``tension`` was ``action + hooks`` and ``pace_speed`` was
    ``action + dialogue``, correlating 0.54 with each other. Six lines that carry three lines'
    worth of information is not a richer chart, it is an unreadable one, and it invited the
    reasonable complaint that the measurement must be over-parameterised. What remains is one
    curve per independent counter: how much plot happens, how often a chapter ends on a hook,
    and how much of the page is interior.
    """
    if not curve.bins:
        return {"availability": "unavailable", "points": [], "event_markers": [], "pacing_regions": []}

    plot = percentile_scores([b["beats"] for b in curve.bins])
    emotion = percentile_scores([b["interiority"] for b in curve.bins])
    hook_density = percentile_scores([b["hooks"] for b in curve.bins])

    points = []
    for i, b in enumerate(curve.bins):
        points.append(
            {
                "chapter_start": int(b["from_chapter"]),
                "chapter_end": int(b["to_chapter"]),
                "plot_progress": plot[i],
                "emotion": emotion[i],
                "hook_density": hook_density[i],
                "dominant_events": [],
                "reason": "",
                "story_consequence": "",
            }
        )

    return {
        "availability": "available",
        "points": points,
        "event_markers": [],
        "pacing_regions": list(regions),
    }


def build_chapters_section(
    chapters_topic: Mapping[str, Any],
    *,
    chapter_titles: Mapping[int, str] | None = None,
    chapter_events: Mapping[int, Sequence[str]] | None = None,
    chapter_evidence: Mapping[int, Sequence[str]] | None = None,
    aggregation_size: int = 10,
) -> dict[str, Any]:
    """Per-chapter functions and the heatmap, both deterministic and free."""
    rows = chapters_topic.get("chapters", []) or []
    if not rows:
        return {"availability": "unavailable", "aggregation_size": aggregation_size,
                "functions": [], "heatmap": []}

    titles = chapter_titles or {}
    functions = []
    for row in rows:
        order = row["chapter_order"]
        # Primary function is derived from counted signals, not asserted: a chapter that is
        # mostly dialogue with a hook is doing something different from one that is mostly
        # action, and both are visible in the counts.
        if row.get("hook_present") and row.get("new_information_beats", 0) > 0:
            primary = "推进+悬念"
        elif row.get("action_paragraphs", 0) >= row.get("dialogue_paragraphs", 0):
            primary = "情节推进"
        elif row.get("interiority_paragraphs", 0) > 0:
            primary = "人物内在"
        else:
            primary = "对话铺陈"
        functions.append(
            {
                "chapter_id": order,
                "chapter_index": order,
                "title": titles.get(order, f"第 {order} 章"),
                "primary_function": primary,
                "secondary_functions": [],
                # The chapter list is the longest page in the product — 806 rows for this
                # book — and every summary on it was blank while the events for each chapter
                # sat extracted and unused. Joined rather than rewritten: these are the
                # model's own ≤50-character event summaries, so the line stays traceable.
                "summary": "；".join(chapter_events.get(order, ())[:3]) if chapter_events else "",
                # The UI contract declares importance as a 0–1 fraction, not a 0–10 score.
                # Filling the wrong scale would render every chapter as maximally important
                # while validating field-by-field, so it is normalised here.
                "importance": round(
                    min(
                        1.0,
                        (row.get("new_information_beats", 0) * 2
                         + (2 if row.get("hook_present") else 0)) / 10,
                    ),
                    2,
                ),
                "evidence": list((chapter_evidence or {}).get(order, ()))[:3],
            }
        )

    # Five columns, not seven. `foreshadow` and `payoff` were the literals 0.0 in every run
    # this engine has ever produced, because nothing measures them — and they name exactly what
    # the suspense module answers with real lifecycles, so filling them in would be a second,
    # worse copy of an existing page rather than a new finding.
    #
    # What remains is counted paragraphs per chapter, averaged. It is not a score out of
    # anything and the columns are on different scales by nature (a chapter has ~20 dialogue
    # paragraphs and either 0 or 1 hooks), which is why each column is labelled with its own
    # unit downstream instead of being presented as one comparable grid.
    heatmap = []
    for start in range(0, len(rows), aggregation_size):
        group = rows[start : start + aggregation_size]
        size = len(group)
        heatmap.append(
            {
                "chapter_start": group[0]["chapter_order"],
                "chapter_end": group[-1]["chapter_order"],
                "mainline_progress": round(sum(g.get("new_information_beats", 0) for g in group) / size, 2),
                "character_development": round(sum(g.get("interiority_paragraphs", 0) for g in group) / size, 2),
                "conflict": round(sum(g.get("action_paragraphs", 0) for g in group) / size, 2),
                "suspense": round(sum(1 for g in group if g.get("hook_present")) / size, 2),
                "transition": round(sum(g.get("dialogue_paragraphs", 0) for g in group) / size, 2),
            }
        )

    return {
        "availability": "available",
        "aggregation_size": aggregation_size,
        "functions": functions,
        "heatmap": heatmap,
    }


def build_characters_section(
    entities: Sequence[Mapping[str, Any]],
    *,
    relationships: Sequence[Mapping[str, Any]] = (),
    tracks: Mapping[str, Any] | None = None,
    character_facts: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Canonical entities and their relationships.

    The protagonist is the most central entity by count of appearances, not a model's
    opinion of who matters — the count is checkable and the opinion is not. Entities carry
    the evidence ids that produced them, so a reader can ask why someone is listed at all.
    """
    if not entities:
        return {
            "availability": "unavailable",
            "protagonist": {
                "initial_identity": "", "initial_goal": "", "final_goal": "",
                "final_identity": "", "stages": [], "external_status_track": [],
                "ability_track": [], "internal_belief_track": [], "relationship_track": [],
            },
            "major_characters": [],
            "relationships": [],
        }

    ranked = sorted(entities, key=lambda e: e.get("centrality", 0), reverse=True)
    lead = ranked[0]
    top_centrality = max(1, lead.get("centrality", 1))
    return {
        "availability": "available",
        "protagonist": {
            "initial_identity": str(lead.get("display_surface_norm", "")),
            "initial_goal": str((tracks or {}).get("initial_goal", "")),
            "final_goal": str((tracks or {}).get("final_goal", "")),
            "final_identity": str(lead.get("display_surface_norm", "")),
            "stages": list((tracks or {}).get("stages", [])),
            # The four tracks are where the 主角历程 page gets its content. Left empty they
            # render as 「邓肯 → 邓肯」, which is what a reader saw for an 806-chapter book.
            **{
                name: list((tracks or {}).get(name, []))
                for name in (
                    "external_status_track",
                    "ability_track",
                    "internal_belief_track",
                    "relationship_track",
                )
            },
        },
        # Every field the contract declares is filled. Partial entries validate field by
        # field and fail as a whole, and a section that half-exists is harder to diagnose
        # than one that is honestly empty. Fields this engine cannot yet derive from counted
        # facts are left blank rather than guessed.
        "major_characters": [
            _major_character(e, index, top_centrality, (character_facts or {}).get(
                str(e.get("display_surface_norm", "")), {}))
            for index, e in enumerate(ranked[:C_CHARACTERS_MAX])
        ],
        "relationships": list(relationships),
    }


def _major_character(
    entity: Mapping[str, Any], index: int, top_centrality: int, facts: Mapping[str, Any]
) -> dict[str, Any]:
    """One row of the character page, filled from facts rather than left declared-and-empty.

    Thirteen of this row's fields were blank in every character of every run while the
    events, goals, choices and relationship changes that answer them were extracted and
    stored. Nothing here is asserted: each value is a fact the model already returned with a
    paragraph citation behind it. Fields with no such fact stay empty.
    """
    events = sorted(facts.get("key_events", ()))
    goals = list(facts.get("goals", ()))
    choices = list(facts.get("choices", ()))
    to_lead = list(facts.get("to_lead", ()))
    costs = [c for _, cs, _ in choices for c in cs]
    gains = [g for _, _, gs in choices for g in gs]
    return {
        "character_id": str(entity.get("entity_key", "")),
        "name": str(entity.get("display_surface_norm", "")),
        "aliases": list(entity.get("aliases", [])),
        "importance": round(min(1.0, entity.get("centrality", 0) / max(1, top_centrality)), 2),
        "identity": "",
        "role": "protagonist" if index == 0 else "supporting",
        "initial_goal": goals[0] if goals else "",
        "final_goal": goals[-1] if goals else "",
        # An arc, stated as the distance the character's own goals travelled. Written only
        # when the two ends differ — "A → A" is not an arc, it is a repetition.
        "character_arc": (
            f"{goals[0]} → {goals[-1]}" if len(goals) > 1 and goals[0] != goals[-1] else ""
        ),
        # The chapter is carried inside the string rather than as its own field. The contract
        # forbids extras and the API a user is running was built before any addition to it,
        # so a new field would fail the whole document — and without the chapter these events
        # cannot be placed on a timeline at all. Sampled across the character's span rather
        # than truncated, so a late arrival is not represented only by their first scenes.
        "key_events": [
            f"第{chapter}章｜{summary}"
            for chapter, summary in (
                events
                if len(events) <= 8
                else [events[int(i * len(events) / 8)] for i in range(8)]
            )
        ],
        "relationship_to_protagonist": "" if index == 0 else (to_lead[-1] if to_lead else "unknown"),
        "relationship_changes": to_lead[:6],
        "major_choice": choices[0][0] if choices else "",
        "cost_paid": costs[:4],
        "gain_received": gains[:4],
        "ending": "",
        "evidence": list(dict.fromkeys(facts.get("evidence", ())))[:5]
        or list(entity.get("evidence_ids", []))[:5],
    }


def evidence_in_range(
    index: Mapping[str, Mapping[str, Any]], start: int, end: int, limit: int = 3
) -> list[str]:
    """Evidence ids from chapters ``start``–``end``, sampled across the span.

    Resolved rather than asked for. The assessor names a chapter range — 「第 43–45 章节奏偏缓」
    — and the index already knows which chapter every quotation came from, so the link is
    arithmetic. Asking the model to cite instead would invite it to invent an id, which is the
    failure the whole evidence design exists to prevent, and it would cost a bigger payload for
    a worse answer.

    This is the gap a professional reader named: every dimension and every issue carried an
    empty ``evidence`` list while 419 real quotations sat in the index beside them. The
    conclusions were right and could not be opened.
    """
    if end < start:
        start, end = end, start
    inside = sorted(
        (row for row in index.values() if start <= int(row.get("chapter_index", 0) or 0) <= end),
        key=lambda row: int(row.get("chapter_index", 0) or 0),
    )
    return [str(row["evidence_id"]) for row in _sample(inside, limit)]


def build_assessment_section(
    result: Mapping[str, Any] | None,
    evidence_index: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """The assessment, or an empty one that says so.

    An assessment section filled with generic praise is worse than an empty one: a reader
    cannot tell it apart from a real judgement, and it is the section they are most likely to
    act on. Which is also why every finding that names a range now carries the quotations from
    it: a judgement a reader cannot open is one they have to take on faith.
    """
    if not result:
        return {
            "overall_summary": "",
            "dimensions": [],
            "strengths": [],
            "issues": [],
            "issue_map": [],
            "revision_priorities": [],
            "preserve_list": [],
        }
    index = evidence_index or {}

    def cited(row: dict[str, Any]) -> dict[str, Any]:
        if index and not row.get("evidence"):
            row["evidence"] = evidence_in_range(
                index, int(row.get("chapter_start", 1) or 1), int(row.get("chapter_end", 1) or 1)
            )
        return row

    return {
        "overall_summary": str(result.get("overall_summary", result.get("summary", ""))),
        "dimensions": [d for d in (_as_dimension(x) for x in result.get("dimensions", [])) if d],
        "strengths": [cited(_as_strength(x)) for x in result.get("strengths", [])],
        "issues": [cited(_as_issue(i, x)) for i, x in enumerate(result.get("issues", []))],
        "issue_map": list(result.get("issue_map", [])),
        "revision_priorities": [
            p for p in (_as_priority(i, x) for i, x in enumerate(result.get("revision_priorities", [])))
            if p
        ],
        "preserve_list": str_list(result.get("preserve_list")),
    }


#: The contract admits exactly three ranks. A fourth item cannot be rendered, and inventing a
#: rank for it would misstate the model's own ordering, so the tail is dropped.
_PRIORITY_RANKS = ("first", "second", "third")


def _as_priority(index: int, value: Any) -> dict[str, Any] | None:
    """Normalise one revision priority, or drop it.

    The rank comes from position: a model asked for an ordered list expresses the ordering by
    the order it writes them in, and that is more reliable than the label it attaches.
    """
    if index >= len(_PRIORITY_RANKS):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return conform(RevisionPriority, {"priority": _PRIORITY_RANKS[index], "direction": text})
    if not isinstance(value, Mapping):
        return None
    ranges: list[list[int]] = []
    for item in value.get("chapter_ranges", []):
        if isinstance(item, Sequence) and not isinstance(item, str) and len(item) >= 2:
            try:
                ranges.append([int(item[0]), int(item[1])])
            except (TypeError, ValueError):
                continue
    return conform(RevisionPriority, {
        **value,
        "priority": _PRIORITY_RANKS[index],
        "chapter_ranges": ranges,
        "direction": str(value.get("direction") or value.get("recommended_direction", "")),
        "preserve": str_list(value.get("preserve")),
    })


def build_type_profile_section(
    result: Mapping[str, Any] | None, axes: Mapping[str, Any] | None = None
) -> dict[str, Any] | None:
    """The work's genre profile: the confirmed axes first, the synthesis call second.

    The report used to print whatever the final call guessed. Measured on 《系统豪横》: 「都市
    生活」 at a confidence of 0.0, on a page belonging to the user who had themselves confirmed
    the book as 升级流 — and the axes they confirmed were already steering the extraction and
    the journey, just not the one line at the top that names the book. INV-P2 is exactly this:
    human confirmation outranks inference, and contradicting the user's own answer back to them
    is the worst form of ignoring it.

    The model's guess is kept as a secondary genre rather than dropped. It is an observation
    about the text, and 「都市生活」 is not wrong about this book — it is just not the axis the
    user is reading it on.

    Returns ``None`` only when neither source has anything, so the caller falls back to the
    empty profile rather than publishing a confident-looking blank.
    """
    from app.narrative_core.long_novel.chapter_focus import genre_naming

    confirmed = genre_naming(axes or {})
    guessed = str((result or {}).get("primary_genre", "")).strip()
    if not confirmed and not guessed:
        return None

    secondary = str_list((result or {}).get("secondary_genres"))
    if confirmed and guessed and guessed != confirmed:
        secondary = [guessed] + [x for x in secondary if x != guessed]

    return conform(TypeProfile, {
        **(result or {}),
        "primary_genre": confirmed or guessed,
        "secondary_genres": secondary,
        "narrative_drivers": str_list((result or {}).get("narrative_drivers")),
        "narrative_traits": str_list((result or {}).get("narrative_traits")),
        # 1.0 when a person confirmed the axes — that is not the model being sure, it is the
        # question having been answered by someone entitled to answer it. Otherwise 0.0: the
        # engine does not measure genre agreement, so it claims no number for a guess.
        "genre_confidence": 1.0 if confirmed else 0.0,
    })


# A model asked for "issues" will sometimes return a list of sentences rather than a list of
# objects. Passing that straight through fails the whole document at the last step and loses
# an assessment that every call was already paid for. These coerce a bare string into the
# required shape with the text kept in its natural slot: the content is presentation, not a
# fact claim, so preserving it in a renderable form is better than discarding it. Facts and
# identity are never coerced — those fail closed.
#: The contract's closed vocabularies. A value outside them cannot be rendered, and there is
#: no "unknown" member to fall back to.
#: The closed vocabulary, and what a reader should see for each. The identifier reached the
#: screen untranslated — the assessment page listed `story_structure` and `suspense_payoff`
#: as its six headings. Keeping the label beside the value means the two cannot drift, and
#: means the client never has to hold a second copy of this table (INV-P4).
DIMENSION_LABELS = {
    "story_structure": "故事结构",
    "protagonist_growth": "主角成长",
    "character_relationships": "人物关系",
    "suspense_payoff": "悬念回收",
    "pacing": "节奏",
    "chapter_efficiency": "章节效率",
}
LEGAL_DIMENSIONS = set(DIMENSION_LABELS)
LEGAL_RATINGS = {"A", "A-", "B+", "B", "B-", "C", "D"}
#: Names a model naturally reaches for, mapped to the one legal member they can only mean.
_DIMENSION_ALIASES = {
    "story": "story_structure", "structure": "story_structure", "plot": "story_structure",
    "plot_progression": "story_structure",
    "characters": "character_relationships", "character": "character_relationships",
    "character_development": "protagonist_growth", "growth": "protagonist_growth",
    "suspense": "suspense_payoff",
    "chapters": "chapter_efficiency", "chapter": "chapter_efficiency",
}


def _as_dimension(value: Any) -> dict[str, Any] | None:
    """Normalise one assessment dimension, or drop it.

    A rating is a *judgement the model made*. If it did not make one, defaulting to a grade
    would put a verdict in front of the reader that nothing produced — the exact failure this
    engine exists to prevent. An unratable dimension is therefore dropped and counted, not
    filled in.
    """
    if not isinstance(value, Mapping):
        return None
    raw_dimension = str(value.get("dimension", "")).strip().lower().replace("-", "_").replace(" ", "_")
    dimension = raw_dimension if raw_dimension in LEGAL_DIMENSIONS else _DIMENSION_ALIASES.get(raw_dimension)
    rating = str(value.get("rating", "")).strip().upper()
    if dimension is None or rating not in LEGAL_RATINGS:
        return None
    # NOT emitting `dimension_label` here, deliberately. The field exists on the contract and
    # is optional, but the API a user is running was built before it did, and its model
    # forbids extras — a document carrying the field made the whole report page fail to load
    # with a 500. A contract addition only becomes safe to emit once the shipped backend
    # understands it, so the label is rendered client-side until then. `DIMENSION_LABELS`
    # below stays as the source of truth for what the six names mean.
    return {
        "dimension": dimension,
        "rating": rating,
        "conclusion": str(value.get("conclusion", "")),
        "supporting_metrics": [str(m) for m in value.get("supporting_metrics", [])],
        "evidence": list(value.get("evidence", [])),
    }


def _as_strength(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {
            "chapter_start": int(value.get("chapter_start", 1) or 1),
            "chapter_end": int(value.get("chapter_end", 1) or 1),
            "title": str(value.get("title", "")),
            "why_good": str(value.get("why_good", "")),
            "evidence": list(value.get("evidence", [])),
        }
    return {"chapter_start": 1, "chapter_end": 1, "title": str(value)[:40],
            "why_good": str(value), "evidence": []}


def _as_issue(index: int, value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        base = dict(value)
    else:
        base = {"symptom": str(value)}
    return {
        "issue_id": str(base.get("issue_id", f"ISS-{index + 1}")),
        "priority": str(base.get("priority", "P2")) if str(base.get("priority", "P2")) in {"P0", "P1", "P2"} else "P2",
        "category": str(base.get("category", "general")),
        "chapter_start": int(base.get("chapter_start", 1) or 1),
        "chapter_end": int(base.get("chapter_end", 1) or 1),
        "symptom": str(base.get("symptom", "")),
        "root_cause": str(base.get("root_cause", "")),
        "reader_impact": str(base.get("reader_impact", "")),
        "supporting_metrics": list(base.get("supporting_metrics", [])),
        "evidence": list(base.get("evidence", [])),
        "possible_direction": str(base.get("possible_direction", "")),
    }


def build_overview_section(
    result: Mapping[str, Any] | None,
    entities: Sequence[Mapping[str, Any]] = (),
    *,
    goal_evolution: Sequence[str] = (),
    conflict_evolution: Sequence[str] = (),
    turning_points: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """The whole-book overview, from the final synthesis call.

    This call was already being made and billed, and its return value was being discarded —
    which is why the overview screen showed em-dashes for every field while the run reported
    success. Fields the synthesis did not produce stay empty rather than being invented; the
    protagonist name is the one exception, because it is a *counted* fact (the most-mentioned
    entity) rather than a judgement.
    """
    base = dict(result or {})
    protagonist = str(base.get("protagonist", ""))
    if not protagonist and entities:
        protagonist = str(entities[0].get("display_surface_norm", ""))
    return {
        "one_sentence_story": str(base.get("one_sentence_story", "")),
        "full_summary": str(base.get("full_summary", base.get("summary", ""))),
        "protagonist": protagonist,
        "initial_state": str(base.get("initial_state", "")),
        "final_state": str(base.get("final_state", "")),
        "core_goal": str(base.get("core_goal", "")),
        # Prefer what the synthesis said; fall back to the changes L1 counted, so the field
        # reflects the book even when the summary call omitted it.
        "goal_evolution": str_list(base.get("goal_evolution") or goal_evolution),
        "core_conflict": str(base.get("core_conflict", "")),
        "conflict_evolution": str_list(base.get("conflict_evolution") or conflict_evolution),
        "core_question": str(base.get("core_question", "")),
        "major_storylines": str_list(base.get("major_storylines")),
        "major_turning_points": [
            x for x in base.get("major_turning_points", []) if isinstance(x, Mapping)
        ] or list(turning_points),
        "major_suspense": str_list(base.get("major_suspense")),
        "final_climax": str(base.get("final_climax", "")),
        "ending_resolution": str_list(base.get("ending_resolution")),
        "ending_open_questions": str_list(base.get("ending_open_questions")),
        "story_skeleton": str_list(base.get("story_skeleton")),
        "evidence": [],
    }


def _empty(availability: str = "unavailable") -> dict[str, Any]:
    return {"availability": availability}


#: Which axis each narrative engine's journey is measured on, and what the axis is called in
#: the report.  Absent from this table means "no axis this engine knows how to compute", which
#: renders as the stage list rather than as a line — see ``JourneyAxis`` on the contract for
#: why an ordinal staircase is not an acceptable fallback.
_JOURNEY_AXIS: dict[str, tuple[str, str]] = {
    "mystery": ("cognition", "认知度"),
    "progression": ("ladder", "阶位"),
}

#: How far each suspense action moves the cognition axis.  Reveals and answers add; a twist
#: subtracts, because what the reader believed has just been taken away.  Misdirection costs
#: less than a twist: it sends the reader the wrong way without overturning a settled belief.
_COGNITION_WEIGHT: dict[str, int] = {
    "partial": 1, "close": 2, "reveal": 3, "resolve": 4, "twist": -5, "misdirect": -1,
}

#: Every ranked reading of the lead is on the line.  This was briefly restricted to
#: ``promote``/``demote``, to work around an extraction prompt that filled ``level`` with the
#: rank of whatever the sentence mentioned — a 六阶 *skill* in the hands of a 二阶 character
#: read as a promotion to 六阶.  That prompt has been fixed and the fix measured on the same
#: 1299-chapter book: the lead's raw ladder went from 8 downward steps to 1, and the one that
#: remains is a real setback (第 1205 章，被核爆余波震伤).  Filtering now would throw away
#: two thirds of a correct series, so the rule is the plain one and the prompt carries the
#: burden — which is where it belongs.
_LADDER_UP = frozenset({"promote", "gain", "faceslap"})


#: Chinese numerals, for reading a rank out of a level name the book wrote itself.
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

#: Refinements *within* a rank — 「五阶巅峰」 is above 五阶 and below 六阶, not a rank of its own.
_RANK_REFINEMENTS = (("巅峰", 0.6), ("顶峰", 0.6), ("中段", 0.3), ("半神", 0.5))


def parse_rank(level: str) -> float | None:
    """Read an ordinal out of a level name, or ``None`` when it is not on the numbered ladder.

    Deliberately narrow. A book's ladder is named by the book — 「五阶」, 「第三阶」,
    「四阶中段」 — and this reads the number out of that name and nothing else. Titles like
    「执法官」 or 「名角儿」 return ``None``: 《我不是戏神》 carries eighteen of them alongside
    its numbered ladder, and forcing them onto the same axis would invent an ordering the
    book never states.
    """
    text = (level or "").strip()
    if "阶" not in text:
        return None
    arabic = re.search(r"\d+", text)
    if arabic:
        base = int(arabic.group(0))
    else:
        digits = [_CN_DIGITS[char] for char in text if char in _CN_DIGITS]
        if not digits:
            return None
        base = digits[0]
    if not 1 <= base <= 12:
        return None
    for word, bump in _RANK_REFINEMENTS:
        if word in text:
            return base + bump
    return float(base)


#: Words a projected trade-off starts with. A choice's ``costs``/``gains`` describe what an
#: option *might* bring, so 62% of the costs on a measured 806-chapter book began this way —
#: 「可能被识破」 is a risk that was considered, not a price that was paid. Dropping them is
#: what makes the 「失去」 column mean what it says; the count falls from 815 to 18, and the
#: 18 are real.
_HYPOTHETICAL = re.compile(r"^(可能|或许|也许|有可能|将会|可以|恐怕|或将|大概|说不定)")

#: How many rows of each kind a stage shows before the count carries the rest.
_LEDGER_SHOWN = 8


def _distinct(phrases: Sequence[str], limit: int = _LEDGER_SHOWN) -> list[str]:
    """Deduplicate, then drop phrases wholly contained in a longer kept one.

    Extraction repeats 「获取情报」 dozens of times across a book. Showing it eight times is
    not eight facts, so the more specific phrasing wins the slot.
    """
    kept: list[str] = []
    for phrase in phrases:
        if any(phrase != other and phrase in other for other in kept):
            continue
        kept = [other for other in kept if not (other != phrase and other in phrase)]
        if phrase not in kept:
            kept.append(phrase)
        if len(kept) >= limit:
            break
    return kept


def build_stage_ledger(
    stages: Sequence[Mapping[str, Any]],
    *,
    lead: str,
    meetings: Sequence[Mapping[str, Any]] = (),
    events: Sequence[Mapping[str, Any]] = (),
    choices: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Per-stage 遇见谁 / 做了什么 / 得到 / 失去, from signals that record an actual change.

    ``meetings`` come from relationship changes rather than from the cast list, because what a
    reader wants is *when* someone entered the story and what the relation became — a name in
    a table cannot say that. Each counterpart is credited once, at first appearance.
    """
    if not stages or not lead:
        return []
    spans = [
        (int(stage.get("chapter") or 1), int(stage.get("chapter_end") or stage.get("chapter") or 1))
        for stage in stages
    ]

    def index_of(chapter: int) -> int:
        for position, (start, end) in enumerate(spans):
            if start <= chapter <= end:
                return position
        return len(spans) - 1

    met: list[dict[str, list[Any]]] = [{"rows": []} for _ in stages]
    seen_people: set[str] = set()
    for row in sorted(meetings, key=lambda r: int(r.get("chapter") or 0)):
        other = str(row.get("other") or "").strip()
        if not other or other in seen_people or lead in other:
            continue
        seen_people.add(other)
        chapter = max(1, int(row.get("chapter") or 1))
        met[index_of(chapter)]["rows"].append(
            conform(LedgerMeeting, {"chapter": chapter, "name": other,
                                    "relation": str(row.get("relation") or "")})
        )

    did: list[list[dict[str, Any]]] = [[] for _ in stages]
    for row in sorted(events, key=lambda r: int(r.get("chapter") or 0)):
        chapter = max(1, int(row.get("chapter") or 1))
        did[index_of(chapter)].append(
            conform(LedgerEvent, {"chapter": chapter, "text": str(row.get("text") or "")})
        )

    gained: list[list[str]] = [[] for _ in stages]
    lost: list[list[str]] = [[] for _ in stages]
    for row in choices:
        if str(row.get("entity_ref") or "") != lead:
            continue
        position = index_of(max(1, int(row.get("chapter") or 1)))
        for phrase in row.get("gains") or []:
            text = str(phrase or "").strip()
            if text and not _HYPOTHETICAL.match(text):
                gained[position].append(text)
        for phrase in row.get("costs") or []:
            text = str(phrase or "").strip()
            if text and not _HYPOTHETICAL.match(text):
                lost[position].append(text)

    ledger = []
    for position, stage in enumerate(stages):
        rows = met[position]["rows"]
        events_here = did[position]
        # Events are sampled across the span rather than truncated at the front: a stage's
        # last act deserves the same chance of being shown as its first.
        #
        # ``events[::step][:N]`` did not do that, though the line above has always claimed it
        # did. With ``step = n // N`` the stride is rounded down, so the first N of the strided
        # list stop well short of the end — 22 events reached the 15th, and 15 events with a
        # stride of 1 degenerated to a plain prefix. Measured on 《系统豪横》: the 49–64 stage
        # ended at chapter 57 and the 65–84 stage at chapter 78, so every act silently lost its
        # closing chapters. Index arithmetic instead, which lands on the last element by
        # construction.
        ledger.append(conform(StageLedger, {
            "stage_name": str(stage.get("stage_name") or ""),
            "chapter_start": spans[position][0], "chapter_end": spans[position][1],
            "met": rows[:_LEDGER_SHOWN], "met_total": len(rows),
            "did": _sample(events_here, _LEDGER_SHOWN), "did_total": len(events_here),
            "gained": _distinct(gained[position]), "gained_total": len(gained[position]),
            "lost": _distinct(lost[position]), "lost_total": len(lost[position]),
        }))
    return ledger


def build_journey_section(
    *,
    axes: Mapping[str, Any] | None,
    ledger: Sequence[Mapping[str, Any]] = (),
    chapter_count: int,
    suspense_actions: Sequence[Mapping[str, Any]] = (),
    power_beats: Sequence[Mapping[str, Any]] = (),
    screen_time: Mapping[str, Sequence[int]] | None = None,
    screen_time_spans: Mapping[str, tuple[int, int, int]] | None = None,
    bins: int = 0,
) -> dict[str, Any]:
    """Build the journey the book's profile asks for, or an empty one.

    The axis is decided here, on the engine side, and the client renders what it is told
    (INV-P4).  ``pov`` outranks ``engine`` for the *shape*: an ensemble book has no single
    protagonist whose level or knowledge is the story, so its journey is the screen-time
    distribution — which is what §9 of the profile design already says replaces the
    protagonist-arc subview for ``ensemble``.
    """
    resolved: dict[str, str] = {}
    for axis, value in (axes or {}).items():
        resolved[axis] = value.get("value", "") if isinstance(value, Mapping) else str(value)

    if resolved.get("pov") == "ensemble" and screen_time:
        section = _screen_time_journey(screen_time, screen_time_spans or {}, bins)
    else:
        kind, label = _JOURNEY_AXIS.get(resolved.get("engine", ""), ("", ""))
        if kind == "cognition":
            section = _cognition_journey(label, suspense_actions, chapter_count)
        elif kind == "ladder":
            section = _ladder_journey(label, power_beats)
        else:
            section = conform(JourneyResult, {"availability": "unavailable", "axis": "none"})
    # The ledger is axis-independent: what a stage cost is worth showing even when no curve
    # could be drawn, which is the whole point of keeping it out of the chart.
    section["ledger"] = list(ledger)
    if ledger and section["availability"] == "unavailable":
        section["availability"] = "partial"
    return section


def _screen_time_journey(
    bands: Mapping[str, Sequence[int]],
    spans: Mapping[str, tuple[int, int, int]],
    bins: int,
) -> dict[str, Any]:
    width = bins or max((len(v) for v in bands.values()), default=0)
    totals = [sum(band[i] if i < len(band) else 0 for band in bands.values()) for i in range(width)]
    rows = []
    for name, counts in bands.items():
        first, last, chapters = spans.get(name, (1, 1, 0))
        rows.append(conform(ScreenTimeBand, {
            "name": name,
            # A bin with no recorded action is 0 for everyone rather than an even split: the
            # honest reading of "nothing was extracted here" is a gap, not a shared stage.
            "share": [round((counts[i] if i < len(counts) else 0) / totals[i], 4) if totals[i] else 0.0
                      for i in range(width)],
            "first_chapter": max(1, first), "last_chapter": max(1, last),
            "chapters": chapters, "total": sum(counts),
        }))
    return conform(JourneyResult, {
        "availability": "available" if rows else "unavailable",
        "axis": "screen_time", "axis_label": "戏份占比", "bins": width, "bands": rows,
        "caveat": "群像书没有单一主角的历程，这里看的是戏份带宽的此消彼长：谁在哪一段接过主线、谁中途淡出。",
    })


def _cognition_journey(
    label: str, actions: Sequence[Mapping[str, Any]], chapter_count: int
) -> dict[str, Any]:
    moves = sorted(
        (row for row in actions if str(row.get("action_kind", "")) in _COGNITION_WEIGHT),
        key=lambda row: int(row.get("chapter_ref") or 0),
    )
    running, points = 0.0, []
    for row in moves:
        kind = str(row.get("action_kind", ""))
        running += _COGNITION_WEIGHT[kind]
        points.append(conform(JourneyPoint, {
            "chapter": max(1, int(row.get("chapter_ref") or 1)),
            "value": running, "kind": kind, "load_bearing": True,
            "note": str(row.get("information_added") or "")[:40],
            "evidence": list(row.get("evidence_ids") or []),
        }))
    down = sum(1 for row in moves if _COGNITION_WEIGHT[str(row.get("action_kind", ""))] < 0)
    caveat = ""
    if points and not down:
        caveat = (f"全书 {chapter_count} 章没有抽到一次反转，所以这条线只涨不跌。"
                  "这通常是抽取时没有认真区分 twist，而不是书里真的没有反转。")
    return conform(JourneyResult, {
        "availability": "available" if points else "unavailable",
        "axis": "cognition", "axis_label": label or "认知度",
        "ticks": ["什么都不知道", "知道得最多"], "points": points, "caveat": caveat,
    })


def _ladder_journey(label: str, beats: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ranked = [row for row in beats if row.get("rank") is not None]
    if not ranked:
        return conform(JourneyResult, {"availability": "unavailable", "axis": "ladder"})
    tally: dict[str, int] = {}
    for row in beats:
        tally[str(row.get("entity_ref") or "")] = tally.get(str(row.get("entity_ref") or ""), 0) + 1
    lead = max(tally, key=lambda name: tally[name]) if tally else ""
    top = max(int(row["rank"]) for row in ranked)
    points = [
        conform(JourneyPoint, {
            "chapter": max(1, int(row.get("chapter_ref") or 1)),
            "value": float(row["rank"]) if row.get("rank") is not None else 0.0,
            "label": str(row.get("level") or ""), "kind": str(row.get("kind") or ""),
            "who": str(row.get("entity_ref") or ""), "note": str(row.get("why") or "")[:40],
            "load_bearing": str(row.get("entity_ref") or "") == lead and row.get("rank") is not None,
            "evidence": list(row.get("evidence_ids") or []),
        })
        for row in sorted(beats, key=lambda r: int(r.get("chapter_ref") or 0))
    ]
    connected = [point for point in points if point["load_bearing"]]
    falls = sum(1 for a, b in zip(connected, connected[1:]) if b["value"] < a["value"])
    return conform(JourneyResult, {
        "availability": "available",
        "axis": "ladder", "axis_label": label or "阶位", "lead": lead,
        "ticks": [f"{n}阶" for n in range(1, top + 1)], "points": points,
        # A ladder that only ever rises is the failure this axis exists to catch, so it is
        # named rather than left for the reader to notice.
        "caveat": (f"主线 {len(connected)} 个读数里一次下降都没有，"
                   "通常是抽取时把受挫记成了别的东西，而不是这本书真的只涨。"
                   if connected and not falls else ""),
    })


def to_whole_book_v2(
    *,
    book_id: int,
    snapshot_id: int,
    revision_hash: str,
    title: str,
    chapter_count: int,
    character_count: int,
    run_id: int,
    provider_name: str,
    model_name: str,
    real_provider_calls: int,
    pacing: Mapping[str, Any],
    chapters: Mapping[str, Any],
    story: Mapping[str, Any] | None = None,
    characters: Mapping[str, Any] | None = None,
    suspense: Mapping[str, Any] | None = None,
    assessment: Mapping[str, Any] | None = None,
    overview: Mapping[str, Any] | None = None,
    type_profile: Mapping[str, Any] | None = None,
    evidence_index: Mapping[str, Any] | None = None,
    journey: Mapping[str, Any] | None = None,
    story_breakdown: Mapping[str, Any] | None = None,
    coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the document the existing UI already knows how to render.

    Sections the run did not produce are marked ``unavailable`` and left empty. That is a
    deliberate choice: a section filled with confident text the engine cannot support is
    indistinguishable to a reader from one it can.
    """
    return {
        "schema_version": "whole-book-analysis-v2.0",
        "book_metadata": {
            "book_id": book_id,
            "snapshot_id": snapshot_id,
            "revision_hash": revision_hash,
            "title": title,
            "chapter_count": chapter_count,
            "character_count": character_count,
        },
        "type_profile": dict(type_profile) if type_profile else {
            "primary_genre": "",
            "secondary_genres": [],
            "narrative_drivers": [],
            "narrative_traits": [],
            "genre_confidence": 0.0,
            "analysis_focus": [],
            "evidence": [],
        },
        "overview": dict(overview) if overview else {
            "one_sentence_story": "",
            "full_summary": "",
            "protagonist": "",
            "initial_state": "",
            "final_state": "",
            "core_goal": "",
            "goal_evolution": [],
            "core_conflict": "",
            "conflict_evolution": [],
            "core_question": "",
            "major_storylines": [],
            "major_turning_points": [],
            "major_suspense": [],
            "final_climax": "",
            "ending_resolution": [],
            "ending_open_questions": [],
            "story_skeleton": [],
            "evidence": [],
        },
        "story": dict(story) if story else {
            **_empty(), "structure_stages": [], "storylines": [], "causal_chain": [], "chronology": []
        },
        "characters": dict(characters) if characters else {
            **_empty(), "protagonist": {
                "initial_identity": "", "initial_goal": "", "final_goal": "", "final_identity": "",
                "stages": [], "external_status_track": [], "ability_track": [],
                "internal_belief_track": [], "relationship_track": [],
            },
            "major_characters": [], "relationships": [],
        },
        "suspense": dict(suspense) if suspense else {**_empty(), "lifecycles": []},
        "pacing": dict(pacing),
        "chapters": dict(chapters),
        "assessment": dict(assessment) if assessment else {
            "overall_summary": "",
            "dimensions": [],
            "strengths": [],
            "issues": [],
            "issue_map": [],
            "revision_priorities": [],
            "preserve_list": [],
        },
        "evidence_index": dict(evidence_index or {}),
        # Defaults to "no axis computed", which the client renders as the stage list. It never
        # falls back to the ordinal staircase: that drew the same rising line for every book.
        "journey": dict(journey) if journey else conform(
            JourneyResult, {"availability": "unavailable", "axis": "none"}
        ),
        # Absent on a diagnostic run, and honestly absent: a 拆文 section left at
        # `unavailable` says the reading was not done, which is different from saying the
        # book had nothing worth quoting.
        "story_breakdown": dict(story_breakdown) if story_breakdown else conform(
            StoryBreakdownResult, {"availability": "unavailable"}
        ),
        "analysis_metadata": {
            "run_id": run_id,
            "provider_name": provider_name,
            "model_name": model_name,
            "module_availability": {
                "story": (story or {}).get("availability", "unavailable"),
                "characters": (characters or {}).get("availability", "unavailable"),
                "suspense": (suspense or {}).get("availability", "unavailable"),
                "pacing": pacing.get("availability", "unavailable"),
                "chapters": chapters.get("availability", "unavailable"),
            },
            "real_provider_calls": real_provider_calls,
            # What the analysis did not read. Carried on the document rather than left in the
            # run log, because the reader is the person who needs it: a hole in the pacing
            # curve is invisible, and an act structure that opens at chapter 9 reads as the
            # book's beginning unless something on the page says otherwise.
            "coverage": dict(coverage) if coverage else None,
            # Required by the contract, and load-bearing for the user: it is how a result
            # produced by this engine is told apart from one the old pipeline produced.
            "engine_version": "long-novel-engine-1.0",
            "result_origin": "real_provider" if real_provider_calls else "deterministic_local_merge",
            "pipeline_version": "long-novel-engine-1.0",
        },
    }
