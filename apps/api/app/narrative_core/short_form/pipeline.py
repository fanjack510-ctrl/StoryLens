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
    RecurringPhrase,
    ShortFormBeat,
    ShortFormResult,
    ShortFormSegment,
)
from app.narrative_core.short_form.recurrence import find_recurrences
from app.narrative_core.short_form.prompts import (
    READ_INSTRUCTION,
    RESPLIT_INSTRUCTION,
    SEGMENT_INSTRUCTION,
    SHAPE_INSTRUCTION,
    genre_lens,
)

#: Segments per reading call. Six columns each, so a dozen is already a long response; this
#: keeps each call inside the output ceiling with room for the model to write full craft notes
#: rather than truncated ones.
SEGMENTS_PER_READ_CALL = 6

#: A segment longer than this holds more than one scene. Measured on the first real run:
#: four of twenty segments exceeded it and between them held **54.6% of the whole piece** — so
#: more than half the text was getting one craft note each. The columns were filled and looked
#: right, which is what makes this a quality failure rather than a visible one.
MAX_SEGMENT_CHARS = 2_000

#: A segment shorter than this is a fragment, not a scene — usually a one-line reply the model
#: cut away from the exchange it belongs to. Merged into its neighbour rather than analysed.
MIN_SEGMENT_CHARS = 120

#: How many earlier segments travel with each reading call.
#:
#: The whole piece, in practice, rather than a window: a motif that recurs is as likely to reach
#: back twenty segments as two, and a window of six would have missed 《面馆的最后一天》's 「老规矩」
#: by exactly that margin — it is said in segment 10 and again in segment 16. What travels is a
#: digest, not the prose, so forty segments of it cost a few hundred tokens.
CARRY_MAX_SEGMENTS = 40


class Provider(Protocol):
    def complete(self, *, payload: dict[str, Any], max_output_tokens: int) -> str: ...


@dataclass
class ShortFormReport:
    segments_planned: int = 0
    #: How many spans came back too long for one scene and were sent back to be cut.
    segments_resplit: int = 0
    #: True when the boundaries came from an earlier reading instead of being asked for.
    spans_reused: bool = False
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


def apply_resplits(
    spans: list[tuple[int, int]],
    raw: dict[str, Any],
    paragraphs: Sequence[str],
) -> list[tuple[int, int]]:
    """Cut the oversized spans at the boundaries the model came back with.

    Deterministic bisection was the cheaper option and is the wrong one: the segments are
    supposed to be *scenes*, and halving one by paragraph count puts the boundary wherever the
    arithmetic lands. Asking again costs one call for all of them at once.

    The answer is repaired the same way the first pass is — ends only, clamped inside the span,
    sorted, deduplicated — so a careless number can shorten a subsegment but can never drop a
    paragraph or reorder the piece.
    """
    by_index = {}
    for row in raw.get("splits") or ():
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("index") or 0)
        except (TypeError, ValueError):
            continue
        ends = []
        for value in row.get("ends") or ():
            try:
                ends.append(int(value))
            except (TypeError, ValueError):
                continue
        by_index[index] = ends

    out: list[tuple[int, int]] = []
    for position, (start, end) in enumerate(spans, start=1):
        cuts = sorted({e for e in by_index.get(position, []) if start <= e < end})
        cursor = start
        for cut in cuts:
            if cut < cursor:
                continue
            out.append((cursor, cut))
            cursor = cut + 1
        out.append((cursor, end))
    return _merge_short(out, paragraphs)


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


def _emotion_lines(rows: Any) -> list[str]:
    """The emotion stages as sentences, whatever shape the model chose to send them in.

    Asked for a list of strings, the model returned a list of objects — `{"segment": "第7段",
    "note": "..."}` — and `str(x)` turned each into a Python repr, so the report carried
    `"{'segment': '第7段', 'note': '发布会高潮…'}"` on the page. Same family as the revision note
    that arrived as prose and was iterated into one-character bullets: a coercion that never
    asks what shape it was handed.

    Both shapes are legitimate answers to the instruction, so both are accepted and rendered
    the way the corpus writes them — 「第 6–7 段：面对逼婚，她当众撕掉了合同」.
    """
    out: list[str] = []
    for row in rows or ():
        if row is None:
            # The fallback below would render this as the string "None" and print it.
            continue
        if isinstance(row, str):
            text = row.strip()
        elif isinstance(row, dict):
            where = str(row.get("segment") or row.get("stage") or "").strip()
            note = str(row.get("note") or row.get("text") or row.get("why") or "").strip()
            text = f"{where}：{note}" if where and note else (note or where)
        else:
            text = str(row).strip()
        if text:
            out.append(text)
    return out


def carry_digest(segments: list[ShortFormSegment]) -> list[dict[str, Any]]:
    """What the next batch needs to know about the batches before it.

    Carries the **beats**, not a summary of them. A digest of labels — 「陷入危机」, 「至暗时刻」 —
    is enough to show the shape of the arc and useless for the thing this exists to fix: a phrase
    said twice is only visible if the actual phrase is present both times. 《面馆的最后一天》 says
    「老规矩」 in segment 10 and again in segment 16, and no summary of segment 10 would have
    carried those three characters forward.
    """
    return [
        {
            "index": s.index,
            "phase": s.phase,
            "beats": [b[:40] for b in s.beats[:4]],
            "emotion": s.emotion_note,
            "direction": s.emotion_direction,
        }
        for s in segments[-CARRY_MAX_SEGMENTS:]
    ]


_CALLBACK_TARGET = re.compile(r"第\s*(\d+)\s*段")


def _checked_callback(text: str, *, index: int, known: int) -> str:
    """Keep a callback only when the segment it names is one that exists, and is earlier.

    The model writes 「呼应第 4 段的十块钱」 and nothing checked that segment 4 existed or came
    first. A callback pointing forward is not a callback, and one pointing at a segment the
    piece does not have is a citation to nothing — both look exactly like a real finding on the
    page, which is why they have to be caught here rather than read past.

    A callback naming no segment at all is kept: 「呼应开头的价目表」 is a legitimate way to say
    it and there is nothing to verify.
    """
    note = str(text or "").strip()
    if not note:
        return ""
    targets = [int(m) for m in _CALLBACK_TARGET.findall(note)]
    if not targets:
        return note
    if all(1 <= t < index and t <= known for t in targets):
        return note
    return ""


def _covers(spans: Sequence[tuple[int, int]], total: int) -> bool:
    """Are these boundaries a partition of exactly this many paragraphs?

    The guard on reuse. Boundaries from an earlier reading describe the text as it was then; if
    the book has been re-imported or re-split since, they cite paragraphs that have moved, and
    every segment would be a window onto the wrong prose while looking entirely normal.
    """
    if not spans:
        return False
    cursor = 1
    for start, end in spans:
        if int(start) != cursor or int(end) < int(start):
            return False
        cursor = int(end) + 1
    return cursor == total + 1


def run_short_form(
    *,
    provider: Provider,
    paragraphs: Sequence[str],
    title: str = "",
    genre: str = "",
    max_output_tokens: int = 6_000,
    on_call: Callable[[str, int], None] | None = None,
    #: Boundaries from an earlier reading of this same text, to be used instead of asking again.
    #:
    #: Measured on 《面馆的最后一天》 across three runs: thirteen of the boundaries were identical
    #: every time and the disagreement sat entirely in one stretch of the story where the prose
    #: genuinely has no clean scene break. That is not unreliability — it is the text — but a
    #: single boundary moving renumbers every segment after it, and the callbacks cite segment
    #: numbers. Re-reading a piece keeps its structure so the numbers keep meaning the same
    #: thing; it also saves the two calls the segmentation would have cost.
    reuse_spans: Sequence[tuple[int, int]] | None = None,
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

    if reuse_spans and _covers(reuse_spans, len(body)):
        spans = [(int(a), int(b)) for a, b in reuse_spans]
        report.spans_reused = True
    else:
        spans = _merge_short(
            plan_segments(
                call("segment", SEGMENT_INSTRUCTION, {"text": rendered}),
                total_paragraphs=len(body),
            ),
            body,
        )

    def span_chars(span: tuple[int, int]) -> int:
        return sum(len(body[i - 1]) for i in range(span[0], span[1] + 1))

    # One extra call for all of the oversized spans together, or none at all when the first
    # pass already cut cleanly. Charging per oversized segment would make a badly-segmented
    # piece cost several times a well-segmented one for the same reading.
    oversized = [] if report.spans_reused else [
        {
            "index": i,
            "text": "\n".join(f"[p:{p}] {body[p - 1]}" for p in range(start, end + 1)),
        }
        for i, (start, end) in enumerate(spans, start=1)
        if span_chars((start, end)) > MAX_SEGMENT_CHARS
    ]
    if oversized:
        report.segments_resplit = len(oversized)
        spans = apply_resplits(
            spans, call("resplit", RESPLIT_INSTRUCTION, {"segments": oversized}), body
        )
    report.segments_planned = len(spans)

    segments: list[ShortFormSegment] = []
    for offset in range(0, len(spans), SEGMENTS_PER_READ_CALL):
        batch = spans[offset : offset + SEGMENTS_PER_READ_CALL]
        answer = call(
            "read",
            READ_INSTRUCTION,
            {
                # Everything read so far. Without it each batch was blind to the ones before,
                # so nothing could recur, nothing could be overturned, and a silence could not
                # be recognised as the answer to something said earlier.
                "前文": carry_digest(segments),
                "segments": [
                    {"index": offset + i + 1, "text": "\n".join(body[s - 1 : e])}
                    for i, (s, e) in enumerate(batch)
                ],
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
                    callback=_checked_callback(
                        row.get("callback") or "", index=index, known=len(spans)
                    ),
                )
            )

    # Found by comparing the prose, not by asking. The model reads six segments at a time and
    # cannot see a wording return across the whole piece; a loop can, and does it exactly.
    recurring = [
        RecurringPhrase(phrase=r.phrase, segments=list(r.segments))
        for r in find_recurrences(
            {
                s.index: "".join(body[s.paragraph_start - 1 : s.paragraph_end])
                for s in segments
            }
        )
    ]

    shape = call(
        "shape",
        SHAPE_INSTRUCTION,
        {
            "反复出现": [
                {"说法": r.phrase, "出现在": r.segments} for r in recurring
            ],
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
        emotion_up=_emotion_lines(shape.get("emotion_up")),
        emotion_down=_emotion_lines(shape.get("emotion_down")),
        recurring=recurring,
    )
    return report
