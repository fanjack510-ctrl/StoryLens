"""Which pipeline a book gets, and why length alone cannot decide it.

The long-novel engine plans in blocks → partitions → narrative stages, and on a short piece
that skeleton degenerates: 《一梦如初》 (40,187 characters, 22 chapters) resolves to 3 blocks →
3 partitions → **2 stages**, and a four-beat 起承转合 then has to be carved out of two. That is
not a tuning problem — a partition cannot be finer than a block, so three blocks can never
carry four stages.

So short pieces get their own pipeline, and this is the rule that sends them there.
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


def book_is_short_form(session: Session, book_id: int) -> bool:
    row = session.execute(
        text(
            "SELECT COUNT(*), COALESCE(SUM(word_count), 0) FROM chapters WHERE book_id = :book_id"
        ),
        {"book_id": int(book_id)},
    ).first()
    chapters, characters = (row or (0, 0))
    return is_short_form(character_count=int(characters or 0), chapter_count=int(chapters or 0))
