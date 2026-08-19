"""The reader says whether a work is long or short; the inference only suggests.

Inferring from length and chapter count left a seam nothing could cross. 《一梦如初》 is 40,187
characters in 22 chapters — two chapters over the limit — so a novella went to the whole-book
engine, which resolved it into two narrative stages and could not draw a timeline. The person
importing the file already knows the answer.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.narrative_core.short_form.dispatch import (
    book_analysis_form,
    book_is_short_form,
    segmentation_estimate,
    suggested_form,
)


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, analysis_form VARCHAR(16))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE chapters (id INTEGER PRIMARY KEY, book_id INTEGER, word_count INTEGER)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE paragraphs (id INTEGER PRIMARY KEY, book_id INTEGER, raw_text TEXT)"
            )
        )
    maker = sessionmaker(bind=engine)
    with maker() as db:
        yield db


def _book(session, book_id: int, *, chapters: int, chars: int, form: str | None = None) -> None:
    session.execute(
        text("INSERT INTO books (id, title, analysis_form) VALUES (:i, 'x', :f)"),
        {"i": book_id, "f": form},
    )
    per = max(1, chars // max(1, chapters))
    for n in range(chapters):
        session.execute(
            text("INSERT INTO chapters (book_id, word_count) VALUES (:b, :w)"),
            {"b": book_id, "w": per},
        )
    session.commit()


def test_the_novella_that_was_two_chapters_over_can_now_be_read_as_one_piece(session) -> None:
    """The case this whole mechanism exists for.

    40,187 characters in 22 chapters: under every length threshold, over the chapter one. The
    inference still says 长篇 — it is not wrong about what it measures — and the reader's answer
    is what decides.
    """
    _book(session, 1, chapters=22, chars=40_187)
    assert suggested_form(session, 1) == "long"
    assert book_is_short_form(session, 1) is False

    session.execute(text("UPDATE books SET analysis_form = 'short' WHERE id = 1"))
    session.commit()

    assert book_is_short_form(session, 1) is True
    # The suggestion is unchanged: it is a measurement, not a verdict, and overwriting it
    # would destroy the only record of what the engine thought.
    assert suggested_form(session, 1) == "long"


def test_a_book_nobody_was_asked_about_behaves_exactly_as_before(session) -> None:
    """NULL is the whole compatibility story — every book imported before the question existed."""
    _book(session, 1, chapters=1, chars=8_577)
    _book(session, 2, chapters=806, chars=2_359_092)
    assert book_analysis_form(session, 1) == ""
    assert book_is_short_form(session, 1) is True
    assert book_is_short_form(session, 2) is False


def test_the_choice_is_honoured_in_both_directions(session) -> None:
    """Including the direction that costs more: a short piece read as a book."""
    _book(session, 1, chapters=1, chars=8_577, form="long")
    assert suggested_form(session, 1) == "short"
    assert book_is_short_form(session, 1) is False


def test_a_value_outside_the_two_is_not_treated_as_an_answer(session) -> None:
    """A stored value the engine cannot dispatch on must fall back, not decide.

    Anything else would let a bad write — a typo, an older client, a hand-edited row — silently
    route a book to a pipeline nobody chose.
    """
    _book(session, 1, chapters=22, chars=40_187, form="medium")
    assert book_analysis_form(session, 1) == ""
    assert book_is_short_form(session, 1) is False


def test_the_segmentation_estimate_reports_and_never_refuses(session) -> None:
    """Segmentation sends the whole piece in one call, so length is a wall — but a wall the
    reader is told about, not one they are stopped at.

    Measured across the local library the wall sits between 145,000 and 183,000 characters,
    the spread coming from paragraph density: each paragraph carries a ``[p:N]`` marker, and
    《面馆的最后一天》 averages 19 characters a paragraph so its markers cost about a third of
    the call.
    """
    _book(session, 1, chapters=1, chars=0, form="short")
    for _ in range(452):
        session.execute(
            text("INSERT INTO paragraphs (book_id, raw_text) VALUES (1, :t)"),
            {"t": "x" * 19},
        )
    session.commit()
    small = segmentation_estimate(session, 1)
    assert small["fits"] is True
    assert small["paragraphs"] == 452

    _book(session, 2, chapters=806, chars=0, form="short")
    session.execute(
        text("INSERT INTO paragraphs (book_id, raw_text) VALUES (2, :t)"),
        {"t": "x" * 2_359_092},
    )
    session.commit()
    huge = segmentation_estimate(session, 2)
    assert huge["fits"] is False
    # The book is still short-form: the estimate informs, it does not veto.
    assert book_is_short_form(session, 2) is True
