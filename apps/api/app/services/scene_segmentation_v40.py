"""场景切分 v4.0 —— 整章一次，直接给出场景起点 (CHG-20260815-099).

Why the task shape changed, recorded because the old shape looked reasonable and was not:

v3.5 asked the model, for each adjacent paragraph pair, to fill six enum relations plus a
boundary flag and a confidence. On book 10 chapter 1445 — 68 paragraphs whose text says
「街道」→「家门前」→「走入屋中」→「走进厨房」→「向自己的卧室走去」, five location changes
in plain words — it returned the *first* value of every enum for all 67 transitions
(`same / continuous / continuous / same / same / none`, confidence 0.9 every time) and the
chapter came out as a single scene. Ten paid calls to learn nothing.

Measured against the same chapter and the same model, asking for the segmentation directly
returned six scenes in one call: 街道 / 家门口 / 客厅 / 厨房 / 卧室 / 客厅, matching a
hand reading to within one or two paragraphs. Input dropped from 27,679 to ~2,300 tokens.

The lesson worth keeping: a labelling task with a uniform schema invites uniform filling.
A segmentation task has one answer per scene rather than one per paragraph gap, and the
model has to have read the chapter to produce it at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.scene import (
    SceneBoundary,
    SceneBoundaryResult,
    SceneSegmentationResultV40,
)

__all__ = [
    "SegmentationInput",
    "build_segmentation_snapshot",
    "map_segments_to_boundaries",
    "validate_segmentation",
]


@dataclass(frozen=True)
class SegmentationInput:
    """Ordered paragraphs of one chapter, as the model sees them."""

    paragraph_ids: tuple[str, ...]
    texts: tuple[str, ...]


def build_segmentation_snapshot(
    *, chapter_id: str, title: str, paragraph_ids: list[str], texts: list[str]
) -> dict:
    """Numbered paragraphs. Numbers rather than ids: the ids are 20 characters each and the
    model has to echo one per scene — numbering is cheaper to emit and impossible to
    hallucinate into a valid-looking id that belongs to another chapter."""
    return {
        "chapter_id": chapter_id,
        "title": title,
        "paragraphs": [
            {"n": index, "text": text} for index, text in enumerate(texts, start=1)
        ],
    }


def map_segments_to_boundaries(
    result: SceneSegmentationResultV40,
    *,
    chapter_id: str,
    paragraph_ids: list[str],
) -> SceneBoundaryResult:
    """Turn scene starts **and markers** into boundaries (`after_paragraph_id` = the
    paragraph before each).

    Everything the model says is checked against the paragraphs that exist: a start outside
    the chapter, a duplicate, or a start of 1 (which is not a boundary, it is the chapter
    opening) is dropped rather than trusted. A model that returns nothing usable yields no
    boundaries, and the chapter stays one scene — the honest outcome, and the one the
    review UI lets a person fix by hand.

    Markers count as cuts, and that is the second measurement this file exists to record.
    《再也不见》第一章 is 45 paragraphs in one dorm room on one night: the event-driven half of
    the prompt («不要切分：同一空间内的连续对话») forbids cutting anywhere after P6, yet P35 —
    「我和齐沫分手了」 — is where the chapter turns. Run the identical payload three times at
    temperature 0 and the marker lands on P35 **3 times out of 3**, while the scene list
    keeps it only 2 out of 3. The first step of 先标记后切分 is reliable; the second step
    discards its own finding, and which run a reader gets is luck.

    So the program takes the union rather than asking twice. On 《我不是戏神》第一章 the two
    lists were already identical ([1, 29, 31, 42, 60, 63] both), so the union changes
    nothing where the model is already consistent — it only recovers what the second step
    dropped.
    """
    total = len(paragraph_ids)
    candidates = [int(segment.start) for segment in result.scenes]
    candidates += [int(marker.n) for marker in result.markers]
    starts: list[int] = []
    for start in candidates:
        if start <= 1 or start > total:
            continue
        if start in starts:
            continue
        starts.append(start)
    starts.sort()

    # A marker on the same paragraph is the model's stated evidence for that cut; carrying
    # it into the reason keeps the review screen able to say *why* a line was drawn.
    marker_by_n = {int(m.n): m for m in result.markers}
    reason_by_start = {int(s.start): s for s in result.scenes}

    boundaries: list[SceneBoundary] = []
    for start in starts:
        segment = reason_by_start.get(start)
        marker = marker_by_n.get(start)
        summary = ""
        if segment is not None:
            summary = (segment.why or segment.where or "").strip()
        if not summary and marker is not None:
            summary = (marker.what or marker.kind).strip()
        boundaries.append(
            SceneBoundary(
                after_paragraph_id=paragraph_ids[start - 2],
                reason_summary=summary[:200],
                confidence=0.8,
            )
        )

    return SceneBoundaryResult(
        chapter_id=chapter_id,
        boundaries=boundaries,
        overall_confidence=0.8 if boundaries else 1.0,
    )


def validate_segmentation(
    result: SceneSegmentationResultV40, *, expected_chapter_id: str, paragraph_ids: list[str]
) -> SceneSegmentationResultV40:
    """Reject a segmentation the chapter cannot support, so the repair prompt gets a chance.

    Only two things are worth failing over. A run of starts that all sit outside the chapter
    means the model numbered its own way and the mapping would silently discard everything;
    and a first scene that does not begin at 1 means it dropped the chapter opening. Both
    are recoverable by asking again, which is what raising here does. Anything else is
    handled by the mapper, which drops what it cannot use rather than inventing a cut.
    """
    total = len(paragraph_ids)
    starts = [int(item.start) for item in result.scenes]
    if starts:
        if starts[0] != 1:
            raise ValueError(
                f"第一个场景必须从第 1 段开始，收到 {starts[0]}（本章共 {total} 段）"
            )
        usable = [value for value in starts if 1 <= value <= total]
        if not usable:
            raise ValueError(f"没有一个 start 落在 1..{total} 之内：{starts}")
    return result
