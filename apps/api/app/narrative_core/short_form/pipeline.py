"""短篇精读 pipeline: segment by scene, read each segment, then judge the whole.

Three calls' worth of work, not three calls exactly — the middle step is batched, because a
12,000-character piece cuts into 15–30 segments and asking for all of their six columns in one
response overruns the output ceiling long before it overruns the input one.

Ordering is deliberate. Segmentation happens first and alone, so that every later claim is
attached to a span the reader can turn to; the whole-piece judgement happens last and is given
the segments rather than the prose, so 起承转合 is a reading of the structure that was found
rather than a second, disagreeing pass over the text.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

from app.narrative_core.short_form.contracts import (
    ShortFormBeat,
    ShortFormResult,
    ShortFormSegment,
)
from app.narrative_core.short_form.prompts import (
    READ_INSTRUCTION,
    SEGMENT_INSTRUCTION,
    SHAPE_INSTRUCTION,
    genre_lens,
)

#: Segments per reading call. Six columns each, so a dozen is already a long response; this
#: keeps each call inside the output ceiling with room for the model to write full craft notes
#: rather than truncated ones.
SEGMENTS_PER_READ_CALL = 6

#: A segment shorter than this is a fragment, not a scene — usually a one-line reply the model
#: cut away from the exchange it belongs to. Merged into its neighbour rather than analysed.
MIN_SEGMENT_CHARS = 120


class Provider(Protocol):
    def complete(self, *, payload: dict[str, Any], max_output_tokens: int) -> str: ...


@dataclass
class ShortFormReport:
    segments_planned: int = 0
    provider_calls: int = 0
    result: ShortFormResult | None = None
    failures: list[str] = field(default_factory=list)


def render(paragraphs: Sequence[str]) -> str:
    """The piece as the model sees it: every paragraph numbered, so a boundary can be cited."""
    return "\n".join(f"[p:{i}] {text}" for i, text in enumerate(paragraphs, start=1))


def _json(raw: str) -> dict[str, Any]:
    """Model output as JSON, tolerating the fence it sometimes arrives in."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def plan_segments(raw: dict[str, Any], *, total_paragraphs: int) -> list[tuple[int, int]]:
    """Turn the model's boundaries into a partition of the piece.

    The boundaries are repaired rather than trusted, because a gap or an overlap is silent: a
    paragraph claimed by two segments is analysed twice and one skipped entirely is analysed
    never, and neither shows on the finished page. Each segment starts where the last ended,
    the last reaches the final paragraph, and anything degenerate is dropped — the same rule
    the whole-book 起承转合 needed, for the same reason.
    """
    rows = [r for r in (raw.get("segments") or []) if isinstance(r, dict)]
    spans: list[tuple[int, int]] = []
    cursor = 1
    for row in rows:
        if cursor > total_paragraphs:
            break
        # The start is *always* the cursor, never the model's number. Honouring a start that
        # skips ahead is how paragraphs disappear: if the model says one segment ends at 4 and
        # the next begins at 8, taking it at its word drops 5–7 out of the analysis entirely and
        # nothing downstream can tell. Only the ends are the model's to choose; contiguity is
        # not negotiated, it is constructed.
        start = cursor
        try:
            end = int(row.get("paragraph_end") or start)
        except (TypeError, ValueError):
            continue
        end = max(start, min(end, total_paragraphs))
        spans.append((start, end))
        cursor = end + 1
    if not spans:
        return [(1, total_paragraphs)] if total_paragraphs else []
    # Whatever the model left off the end still belongs to the piece.
    if spans[-1][1] < total_paragraphs:
        spans[-1] = (spans[-1][0], total_paragraphs)
    return spans


def _merge_short(spans: list[tuple[int, int]], paragraphs: Sequence[str]) -> list[tuple[int, int]]:
    """Fold fragments into the scene they were cut from."""

    def size(span: tuple[int, int]) -> int:
        return sum(len(paragraphs[i - 1]) for i in range(span[0], span[1] + 1))

    merged: list[tuple[int, int]] = []
    for span in spans:
        if merged and size(span) < MIN_SEGMENT_CHARS:
            merged[-1] = (merged[-1][0], span[1])
        else:
            merged.append(span)
    # A short *first* segment has no predecessor to join, so it takes its successor instead.
    if len(merged) > 1 and size(merged[0]) < MIN_SEGMENT_CHARS:
        merged[1] = (merged[0][0], merged[1][1])
        merged.pop(0)
    return merged


def _abutting_beats(rows: list[dict[str, Any]], *, last_segment: int) -> list[ShortFormBeat]:
    """起承转合 as a partition of the segments — same repair as the whole-book breakdown."""
    names = ("起", "承", "转", "合")
    beats: list[ShortFormBeat] = []
    cursor = 1
    usable = [r for r in rows if isinstance(r, dict)][:4]
    for index, row in enumerate(usable):
        # Same rule as `plan_segments`: the start is the cursor. A beat that begins after the
        # previous one ended leaves segments belonging to no act, and 「第 11 段属于哪一幕」 then
        # has no answer — which is the whole reason these four are repaired rather than trusted.
        remaining = len(usable) - index - 1
        start = min(cursor, max(1, last_segment - remaining))
        if index == len(usable) - 1:
            end = max(start, last_segment)
        else:
            try:
                end = max(start, int(row.get("segment_end") or start))
            except (TypeError, ValueError):
                end = start
            # Leave one segment for each beat still to come.
            end = min(end, max(start, last_segment - remaining))
        beat = str(row.get("beat") or "").strip()
        beats.append(
            ShortFormBeat(
                beat=beat if beat in names else names[index],
                segment_start=start,
                segment_end=end,
                title=str(row.get("title") or ""),
                summary=str(row.get("summary") or ""),
            )
        )
        cursor = end + 1
    return beats


def run_short_form(
    *,
    provider: Provider,
    paragraphs: Sequence[str],
    title: str = "",
    genre: str = "",
    max_output_tokens: int = 6_000,
    on_call: Callable[[str, int], None] | None = None,
) -> ShortFormReport:
    """Read a short piece end to end. Pure: the caller owns persistence and the provider."""
    report = ShortFormReport()
    body = [p for p in (t.strip() for t in paragraphs) if p]
    if not body:
        report.failures.append("EMPTY_TEXT")
        report.result = ShortFormResult(title=title, genre=genre)
        return report

    rendered = render(body)
    lens = genre_lens(genre)

    def call(kind: str, instruction: str, extra: dict[str, Any]) -> dict[str, Any]:
        payload = {"instruction": instruction, "lens": lens, **extra}
        raw = provider.complete(payload=payload, max_output_tokens=max_output_tokens)
        report.provider_calls += 1
        if on_call is not None:
            on_call(kind, report.provider_calls)
        return _json(raw)

    spans = _merge_short(
        plan_segments(
            call("segment", SEGMENT_INSTRUCTION, {"text": rendered}),
            total_paragraphs=len(body),
        ),
        body,
    )
    report.segments_planned = len(spans)

    segments: list[ShortFormSegment] = []
    for offset in range(0, len(spans), SEGMENTS_PER_READ_CALL):
        batch = spans[offset : offset + SEGMENTS_PER_READ_CALL]
        answer = call(
            "read",
            READ_INSTRUCTION,
            {
                "segments": [
                    {"index": offset + i + 1, "text": "\n".join(body[s - 1 : e])}
                    for i, (s, e) in enumerate(batch)
                ]
            },
        )
        by_index = {
            int(r.get("index") or 0): r
            for r in (answer.get("segments") or [])
            if isinstance(r, dict)
        }
        for i, (start, end) in enumerate(batch):
            index = offset + i + 1
            row = by_index.get(index, {})
            direction = str(row.get("emotion_direction") or "flat")
            segments.append(
                ShortFormSegment(
                    index=index,
                    paragraph_start=start,
                    paragraph_end=end,
                    characters=sum(len(body[p - 1]) for p in range(start, end + 1)),
                    phase=str(row.get("phase") or ""),
                    setting=str(row.get("setting") or ""),
                    beats=[str(x) for x in (row.get("beats") or []) if str(x).strip()],
                    craft=str(row.get("craft") or ""),
                    emotion_note=str(row.get("emotion_note") or ""),
                    emotion_direction=direction if direction in ("up", "down", "flat") else "flat",
                )
            )

    shape = call(
        "shape",
        SHAPE_INSTRUCTION,
        {
            "segments": [
                {
                    "index": s.index,
                    "phase": s.phase,
                    "beats": s.beats,
                    "emotion_note": s.emotion_note,
                    "emotion_direction": s.emotion_direction,
                }
                for s in segments
            ]
        },
    )

    report.result = ShortFormResult(
        availability="available" if segments else "unavailable",
        title=title,
        genre=genre,
        character_count=sum(len(p) for p in body),
        one_line=str(shape.get("one_line") or ""),
        beats=_abutting_beats(list(shape.get("beats") or []), last_segment=len(segments)),
        segments=segments,
        emotion_up=[str(x) for x in (shape.get("emotion_up") or []) if str(x).strip()],
        emotion_down=[str(x) for x in (shape.get("emotion_down") or []) if str(x).strip()],
    )
    return report
