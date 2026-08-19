"""Find the wordings that come back, by comparing strings rather than by asking.

This exists because of one measured failure. 《面馆的最后一天》 says 「老规矩」 twice — two
different customers, six segments apart — and the reading missed it. It missed it *with* the
whole prior reading carried forward, and *with* the instruction naming recurrence as the first
thing to look for, and *with* the phrase sitting in both segments' beats. Recurring objects it
caught reliably: the chilli oil, the ten-yuan note, the blue notebook, the blank on the wall. A
recurring line it did not.

Comparing strings across segments is the one part of this whole pipeline a model is worse at
than a loop, so it is a loop.

**It reads the story, not the analysis.** The first version compared the model's own beats and
returned 「得知母亲去世」, 「发现母亲」, 「意识到母亲」 — phrases that appear nowhere in the story.
They recur because the summariser writes the same way each time, so scanning its output finds
the model's verbal tics and calls them the author's motifs. A motif lives in the prose or it does
not exist.

**The hard part is not finding repeats — it is telling a motif from a name.** 「母亲」 recurs in
almost every segment of this story and is not a motif; it is who the story is about. The
separation used here is coverage: something in nearly every segment is the furniture, something
in two or three is a callback. That is a heuristic and it is stated as one.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

#: Shorter than this and a match is an accident of the language rather than a repeated wording.
#: Two Chinese characters recur constantly — 「一个」, 「他们」, 「就是」 — and three is the point at
#: which a fragment starts to be a thing someone said on purpose.
MIN_PHRASE_CHARS = 3

#: Longer than this and it is a repeated sentence, which is either a quotation the analysis
#: already has or a sign the same beat was written twice.
MAX_PHRASE_CHARS = 12

#: Present in more than this share of segments and it is the story's furniture — the
#: protagonist, the setting, the recurring cast — not a wording that comes back.
MAX_SEGMENT_SHARE = 0.4

#: How many to hand on. The list is for a person to read, and a long one is a concordance.
MAX_RESULTS = 10

#: Split on anything that is not a Chinese character, so a "phrase" never spans a comma or a
#: number. A motif is said, and speech does not cross punctuation.
_RUN = re.compile(r"[一-鿿]+")


@dataclass(frozen=True)
class Recurrence:
    phrase: str
    segments: tuple[int, ...]


def _phrases(text: str) -> set[str]:
    """Every Chinese substring of a usable length, within one uninterrupted run."""
    found: set[str] = set()
    for run in _RUN.findall(text):
        limit = min(len(run), MAX_PHRASE_CHARS)
        for size in range(MIN_PHRASE_CHARS, limit + 1):
            for start in range(len(run) - size + 1):
                found.add(run[start : start + size])
    return found


def find_recurrences(
    segment_texts: dict[int, str], *, total_segments: int | None = None
) -> list[Recurrence]:
    """Wordings that appear in more than one segment but not in most of them.

    ``segment_texts`` maps segment index to that segment's **source prose**. Not to the beats:
    the beats are the model's words, and comparing them finds the model's habits rather than the
    story's motifs.

    Counted per *segment*, never per occurrence: a phrase used three times inside one scene is
    emphasis, and the thing being looked for is a return.
    """
    if not segment_texts:
        return []
    total = total_segments or len(segment_texts)
    ceiling = max(2, int(total * MAX_SEGMENT_SHARE))

    # How surprising each character is *within this piece*. There is no Chinese frequency
    # corpus here and none is needed: the story is its own baseline. Ranking by how often a
    # phrase recurs surfaces the language rather than the story — 「了很久」, 「在桌上」, 「没说话」
    # came back in a third of the segments of 《面馆的最后一天》 and are constructions, not motifs,
    # while 「老规矩」 came back twice and is the thing the story is doing. What separates them is
    # not how often they return but how unusual their characters are here: 「了」 is everywhere,
    # 「规」 and 「矩」 are not.
    whole = "".join(segment_texts.values())
    counts = Counter(whole)
    length = max(1, len(whole))

    def rarity(phrase: str) -> float:
        return sum(-math.log(counts[c] / length) for c in phrase) / len(phrase)

    where: dict[str, set[int]] = {}
    for index, text in segment_texts.items():
        for phrase in _phrases(text or ""):
            where.setdefault(phrase, set()).add(index)

    kept = {
        phrase: indices
        for phrase, indices in where.items()
        if 2 <= len(indices) <= ceiling
    }

    # A longer phrase subsumes a shorter one it contains when both come back in the same places:
    # 「说老规矩」 and 「老规矩」 are one finding, and the longer one is the one worth printing.
    by_length = sorted(kept, key=len, reverse=True)
    surviving: dict[str, set[int]] = {}
    for phrase in by_length:
        indices = kept[phrase]
        if any(
            phrase in longer and indices == longer_indices
            for longer, longer_indices in surviving.items()
        ):
            continue
        surviving[phrase] = indices

    results = [Recurrence(phrase, tuple(sorted(v))) for phrase, v in surviving.items()]
    # Rarest first. Frequency is deliberately not the primary key — ranking by it put 「老规矩」
    # below every common construction that happened to recur more often, which is the failure
    # this whole module exists to fix.
    results.sort(key=lambda r: (-rarity(r.phrase), -len(r.segments), r.phrase))
    return results[:MAX_RESULTS]


#: A character taking up less than this share of the piece carries enough signal to test a claim
#: against. Above it sits the language — 的, 了, 我, 她 — which appears in every segment and
#: therefore proves nothing about any of them.
#:
#: Stated as a share rather than a surprise value because it makes the one consequence visible:
#: in a piece under about 400 characters a character appearing once is still 0.25% of it, so
#: nothing qualifies and the check abstains. That is the right answer for a text too short to
#: have a vocabulary, and it is why this reads as a fraction.
RARE_CHARACTER_SHARE = 0.0025

#: The part of a callback that is *about* the reference rather than the content. Left in, these
#: characters are absent from the story, therefore score as maximally rare, therefore never
#: match — and every callback fails a check it should have passed.
_META = re.compile(r"呼应|对应|回应|照应|第\s*\d+\s*段|的")


def names_something_in(claim: str, target_text: str, *, whole_text: str) -> bool:
    """Does this claim mention anything actually present in that passage?

    Used to check a callback — 「呼应第 12 段夹克男欠账」 — against the segment it names. The
    check is the loosest one that still catches a fabrication: **not one** of the claim's
    distinctive characters appears in the passage it cites.

    Distinctive is the operative word, and it is the same insight the recurrence finder rests
    on. Matching whole phrases fails because the claim paraphrases: 「账本中李婶的赊账」 is a
    description, not a quotation, and demanding it appear verbatim rejects a correct callback.
    Matching common characters fails the other way: 的 and 母 are in every segment and match
    anything.

    Calibrated on one story, and deliberately at zero rather than at a fraction. Of sixteen
    callbacks on 《面馆的最后一天》 exactly one was fabricated — 第12段 is 寻找赵建军未果 and has
    no jacket, no debt — and it was the only one with no rare character in common. The next
    lowest scored 1 of 5 and was half right: the worn bowls are in that segment, the remittance
    stubs are not. A fractional threshold would have taken it too.
    """
    text = _META.sub("", str(claim or ""))
    if not text or not target_text:
        return True
    counts = Counter(whole_text)
    length = max(1, len(whole_text))
    distinctive = {
        c
        for c in "".join(_RUN.findall(text))
        # A character absent from the whole piece is evidence about the analyst's vocabulary,
        # not about the story: 「那句话」 and 「呼应」 describe the finding rather than name
        # anything in it. Scoring absent characters as maximally rare made every paraphrase
        # unmatchable and rejected callbacks that were sound.
        if 0 < counts.get(c, 0) / length < RARE_CHARACTER_SHARE
    }
    if not distinctive:
        # Nothing distinctive to test. Saying so is honest; guessing is not.
        return True
    return any(c in target_text for c in distinctive)
