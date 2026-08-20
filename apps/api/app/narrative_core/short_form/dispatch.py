"""Which pipeline a book gets, and why length alone cannot decide it.

The long-novel engine plans in blocks → partitions → narrative stages, and on a short piece
that skeleton degenerates: 《一梦如初》 (40,187 characters, 22 chapters) resolves to 3 blocks →
3 partitions → **2 stages**, and a four-beat 起承转合 then has to be carved out of two. That is
not a tuning problem — a partition cannot be finer than a block, so three blocks can never
carry four stages.

So short pieces get their own pipeline, and this is the rule that sends them there.

**The reader decides; the rule only suggests.** Inferring from length and chapter count has a
seam nothing can cross — 《一梦如初》 is two chapters over the limit, so a 40,000-character
novella went to the whole-book engine and came back with two stages and no timeline. The
person importing the file already knows whether they are holding a short story or a novel, and
asking costs one click. ``is_short_form`` still runs, but now as the default selection rather
than the decision; a stored ``analysis_form`` outranks it.

The choice is free below a hard ceiling and unavailable above it. Segmentation sends the whole
piece in one call, so the provider context is a wall rather than a budget: measured across the
local library it lands between 145,000 and 183,000 characters, the spread coming from paragraph
density. ``SHORT_FORM_HARD_MAX_CHARS`` sits at the bottom of that range, and above it 短篇 is
refused rather than attempted — the attempt would spend the run's most expensive call before
failing.

The ceiling binds wherever the answer is given: at import, at the later switch, and at
dispatch. A cap enforced only at import is not a cap, because the switch would walk straight
around it and land on the failure the cap exists to prevent.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

#: Below this, a piece is short whatever its chapter count. The human breakdown corpus runs
#: 9,143–19,199 characters (median 11,830); thirty thousand leaves room above the samples
#: without reaching for novellas.
SHORT_FORM_MAX_CHARS = 30_000

#: Between the two thresholds, chapter count decides. A book of this length with few chapters
#: reads as one continuous piece; with many, it is a serialised work and belongs to the
#: whole-book engine.
SHORT_FORM_SOFT_MAX_CHARS = 80_000
SHORT_FORM_MAX_CHAPTERS = 20


#: 短篇精读 is refused above this, whatever anyone chooses. Not a preference and not a quality
#: judgement: segmentation has to send the whole piece in one call, and past roughly this many
#: characters it does not fit a 128k context. The number is the *bottom* of the measured range
#: (145,968 for 《面馆的最后一天》 at 19 characters a paragraph, where the per-paragraph position
#: markers cost about a third of the call) rounded to something a person can hold in their head.
#:
#: Being the bottom of the range, it is necessary but not sufficient: a very dialogue-heavy
#: piece just under it can still overflow, which is why the per-book estimate is still shown.
SHORT_FORM_HARD_MAX_CHARS = 150_000


def short_form_allowed(character_count: int) -> bool:
    """Can this length be read as one piece at all, regardless of what anyone prefers?"""
    return 0 < int(character_count or 0) <= SHORT_FORM_HARD_MAX_CHARS


def is_short_form(*, character_count: int, chapter_count: int) -> bool:
    """Would this be read as one piece, or as a book?

    Length alone gets it wrong in the direction that matters. 《剩女遇见爱情》 is 194,004
    characters in **one** chapter — a novel whose split failed — and a pure word-count rule
    correctly calls it long, sends it to an engine that needs chapters, and it produces nothing.
    A pure chapter-count rule would call it short and read a whole novel as one sitting.

    Requiring *both* is what separates "one continuous piece" from "a book we failed to split":
    a genuinely short piece is short **and** shallowly divided. Anything else stays with the
    whole-book engine, where a bad split is now disclosed at import rather than hidden.
    """
    chars = max(0, int(character_count))
    chapters = max(0, int(chapter_count))
    if chars <= 0:
        return False
    if chars <= SHORT_FORM_MAX_CHARS:
        return chapters <= SHORT_FORM_MAX_CHAPTERS or chapters == 0
    if chars <= SHORT_FORM_SOFT_MAX_CHARS:
        return 0 < chapters <= SHORT_FORM_MAX_CHAPTERS
    return False


#: What a book's stored ``analysis_form`` may say. Anything else — including NULL — means the
#: question has not been answered for this book, and the inference stands in.
FORM_SHORT = "short"
FORM_LONG = "long"


def book_analysis_form(session: Session, book_id: int) -> str:
    """The reader's answer for this book, or "" if they have not given one."""
    value = session.execute(
        text("SELECT analysis_form FROM books WHERE id = :book_id"),
        {"book_id": int(book_id)},
    ).scalar()
    text_value = str(value or "").strip()
    return text_value if text_value in (FORM_SHORT, FORM_LONG) else ""


def book_is_short_form(session: Session, book_id: int) -> bool:
    """Does this book take 短篇精读?

    A stored answer wins outright, chapter count included: that is the whole point of asking.
    The length ceiling is the one thing it does not win against, and it is checked here rather
    than only where the answer is given — so a row that says ``short`` for a 2.3-million-character
    novel, however it got written, cannot route that book into a pipeline that cannot read it.
    """
    if not book_short_form_allowed(session, int(book_id)):
        return False
    stored = book_analysis_form(session, int(book_id))
    if stored:
        return stored == FORM_SHORT
    return suggested_form(session, int(book_id)) == FORM_SHORT


def book_character_count(session: Session, book_id: int) -> int:
    return int(
        session.execute(
            text("SELECT COALESCE(SUM(word_count), 0) FROM chapters WHERE book_id = :book_id"),
            {"book_id": int(book_id)},
        ).scalar()
        or 0
    )


def book_short_form_allowed(session: Session, book_id: int) -> bool:
    return short_form_allowed(book_character_count(session, int(book_id)))


def suggested_form(session: Session, book_id: int) -> str:
    """What the import panel should offer as the default, before anyone answers."""
    row = session.execute(
        text(
            "SELECT COUNT(*), COALESCE(SUM(word_count), 0) FROM chapters WHERE book_id = :book_id"
        ),
        {"book_id": int(book_id)},
    ).first()
    chapters, characters = (row or (0, 0))
    return (
        FORM_SHORT
        if is_short_form(
            character_count=int(characters or 0), chapter_count=int(chapters or 0)
        )
        else FORM_LONG
    )


# --------------------------------------------------------------------------- 切段的一次性开销
#: The provider context the segmentation call has to fit inside. Same number the long-novel
#: planner uses, for the same provider.
SEGMENT_CONTEXT_WINDOW = 128_000

#: Chinese prose per token — the ratio the planner already assumes.
CHARS_PER_TOKEN = 1.6

#: Each paragraph carries a ``[p:N]`` marker so the model can name boundaries. Cheap per
#: paragraph and anything but cheap in aggregate: 《面馆的最后一天》 averages 19 characters a
#: paragraph, so its markers cost about a third of the whole call.
MARKER_TOKENS_PER_PARAGRAPH = 4

#: Instruction, response and headroom.
SEGMENT_CALL_RESERVE_TOKENS = 6_000


def segmentation_estimate(session: Session, book_id: int) -> dict[str, int | bool]:
    """What the one segmentation call will cost, and whether it can fit.

    Segmentation sends the **whole piece** in a single call — it has to, because a scene break
    is a property of the text on both sides of it, and a batched pass would invent boundaries
    at its own batch edges. That makes the context window a real wall rather than a budget:
    measured across the local library it lands between 145,000 and 183,000 characters depending
    on how short the paragraphs are.

    This is reported, never enforced. A reader who asks for the short-form reading of a long
    work gets the estimate and their answer stands; refusing would substitute a threshold for
    the judgement this whole mechanism exists to hand back to them.
    """
    row = session.execute(
        text(
            "SELECT COUNT(*), COALESCE(SUM(LENGTH(raw_text)), 0) FROM paragraphs "
            "WHERE book_id = :book_id"
        ),
        {"book_id": int(book_id)},
    ).first()
    paragraphs, characters = int((row or (0, 0))[0] or 0), int((row or (0, 0))[1] or 0)
    tokens = int(characters / CHARS_PER_TOKEN) + paragraphs * MARKER_TOKENS_PER_PARAGRAPH
    return {
        "paragraphs": paragraphs,
        "characters": characters,
        "estimated_tokens": tokens,
        "context_window": SEGMENT_CONTEXT_WINDOW,
        "fits": tokens + SEGMENT_CALL_RESERVE_TOKENS <= SEGMENT_CONTEXT_WINDOW,
    }
