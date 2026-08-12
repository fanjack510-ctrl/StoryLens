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

from typing import Any, Mapping, Sequence

from pydantic import BaseModel

from app.narrative_core.long_novel.constants import CHARACTERS_MAX as C_CHARACTERS_MAX
from app.narrative_core.long_novel.topics import ChapterSignalRow, PacingCurve
from app.narrative_core.whole_book_v2.contracts import RevisionPriority, TypeProfile

__all__ = [
    "conform",
    "percentile_scores",
    "build_pacing_section",
    "build_chapters_section",
    "build_characters_section",
    "build_assessment_section",
    "build_overview_section",
    "build_type_profile_section",
    "to_whole_book_v2",
]


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
        if origin in (list, tuple) or annotation in (list, tuple):
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


def build_pacing_section(
    curve: PacingCurve, *, regions: Sequence[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """Turn the bounded curve into the UI's pacing points, with engine-computed scores."""
    if not curve.bins:
        return {"availability": "unavailable", "points": [], "event_markers": [], "pacing_regions": []}

    beats = [b["beats"] for b in curve.bins]
    action = [b["action"] for b in curve.bins]
    interiority = [b["interiority"] for b in curve.bins]
    dialogue = [b["dialogue"] for b in curve.bins]
    hooks = [b["hooks"] for b in curve.bins]

    plot = percentile_scores(beats)
    tension = percentile_scores([a + h for a, h in zip(action, hooks)])
    emotion = percentile_scores(interiority)
    drive = percentile_scores([h * 2 + b for h, b in zip(hooks, beats)])
    hook_density = percentile_scores(hooks)
    speed = percentile_scores([a + d for a, d in zip(action, dialogue)])

    points = []
    for i, b in enumerate(curve.bins):
        points.append(
            {
                "chapter_start": int(b["from_chapter"]),
                "chapter_end": int(b["to_chapter"]),
                "plot_progress": plot[i],
                "tension": tension[i],
                "emotion": emotion[i],
                "reading_drive": drive[i],
                "hook_density": hook_density[i],
                "pace_speed": speed[i],
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
                "evidence": [],
            }
        )

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
                "foreshadow": 0.0,
                "payoff": 0.0,
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
            {
                "character_id": str(e.get("entity_key", "")),
                "name": str(e.get("display_surface_norm", "")),
                "aliases": list(e.get("aliases", [])),
                "importance": round(min(1.0, e.get("centrality", 0) / max(1, top_centrality)), 2),
                "identity": "",
                "role": "protagonist" if i == 0 else "supporting",
                "initial_goal": "",
                "final_goal": "",
                "character_arc": "",
                "key_events": [],
                "relationship_to_protagonist": "" if i == 0 else "unknown",
                "relationship_changes": [],
                "major_choice": "",
                "cost_paid": [],
                "gain_received": [],
                "ending": "",
                "evidence": list(e.get("evidence_ids", []))[:5],
            }
            for i, e in enumerate(ranked[:C_CHARACTERS_MAX])
        ],
        "relationships": list(relationships),
    }


def build_assessment_section(result: Mapping[str, Any] | None) -> dict[str, Any]:
    """The assessment, or an empty one that says so.

    An assessment section filled with generic praise is worse than an empty one: a reader
    cannot tell it apart from a real judgement, and it is the section they are most likely to
    act on.
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
    return {
        "overall_summary": str(result.get("overall_summary", result.get("summary", ""))),
        "dimensions": [d for d in (_as_dimension(x) for x in result.get("dimensions", [])) if d],
        "strengths": [_as_strength(x) for x in result.get("strengths", [])],
        "issues": [_as_issue(i, x) for i, x in enumerate(result.get("issues", []))],
        "issue_map": list(result.get("issue_map", [])),
        "revision_priorities": [
            p for p in (_as_priority(i, x) for i, x in enumerate(result.get("revision_priorities", [])))
            if p
        ],
        "preserve_list": [str(x) for x in result.get("preserve_list", []) if str(x).strip()],
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
        "preserve": [str(x) for x in value.get("preserve", []) if str(x).strip()],
    })


def build_type_profile_section(result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The work's genre profile, out of the final synthesis call.

    Returns ``None`` when the synthesis did not name a genre, so the caller falls back to the
    empty profile rather than publishing a confident-looking blank.
    """
    if not result or not str(result.get("primary_genre", "")).strip():
        return None
    return conform(TypeProfile, {
        **result,
        "primary_genre": str(result.get("primary_genre", "")),
        "secondary_genres": [str(x) for x in result.get("secondary_genres", []) if str(x).strip()],
        "narrative_drivers": [str(x) for x in result.get("narrative_drivers", []) if str(x).strip()],
        "narrative_traits": [str(x) for x in result.get("narrative_traits", []) if str(x).strip()],
        # The engine does not measure genre agreement, so it does not claim a number for it.
        "genre_confidence": 0.0,
    })


# A model asked for "issues" will sometimes return a list of sentences rather than a list of
# objects. Passing that straight through fails the whole document at the last step and loses
# an assessment that every call was already paid for. These coerce a bare string into the
# required shape with the text kept in its natural slot: the content is presentation, not a
# fact claim, so preserving it in a renderable form is better than discarding it. Facts and
# identity are never coerced — those fail closed.
#: The contract's closed vocabularies. A value outside them cannot be rendered, and there is
#: no "unknown" member to fall back to.
LEGAL_DIMENSIONS = {
    "story_structure", "protagonist_growth", "character_relationships",
    "suspense_payoff", "pacing", "chapter_efficiency",
}
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
        "goal_evolution": [str(x) for x in (base.get("goal_evolution") or goal_evolution)],
        "core_conflict": str(base.get("core_conflict", "")),
        "conflict_evolution": [
            str(x) for x in (base.get("conflict_evolution") or conflict_evolution)
        ],
        "core_question": str(base.get("core_question", "")),
        "major_storylines": [str(x) for x in base.get("major_storylines", [])],
        "major_turning_points": [
            x for x in base.get("major_turning_points", []) if isinstance(x, Mapping)
        ] or list(turning_points),
        "major_suspense": [str(x) for x in base.get("major_suspense", [])],
        "final_climax": str(base.get("final_climax", "")),
        "ending_resolution": [str(x) for x in base.get("ending_resolution", [])],
        "ending_open_questions": [str(x) for x in base.get("ending_open_questions", [])],
        "story_skeleton": [str(x) for x in base.get("story_skeleton", [])],
        "evidence": [],
    }


def _empty(availability: str = "unavailable") -> dict[str, Any]:
    return {"availability": availability}


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
            # Required by the contract, and load-bearing for the user: it is how a result
            # produced by this engine is told apart from one the old pipeline produced.
            "engine_version": "long-novel-engine-1.0",
            "result_origin": "real_provider" if real_provider_calls else "deterministic_local_merge",
            "pipeline_version": "long-novel-engine-1.0",
        },
    }
