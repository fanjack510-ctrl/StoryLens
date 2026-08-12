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

from app.narrative_core.long_novel.topics import ChapterSignalRow, PacingCurve

__all__ = ["percentile_scores", "build_pacing_section", "build_chapters_section", "to_whole_book_v2"]


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
                "summary": "",
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
