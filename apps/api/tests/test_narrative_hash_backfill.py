"""Agent A: content hash backfill directed tests."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Book, Chapter, Paragraph
from app.narrative_core.hash_canon import calculate_text_hash
from app.narrative_core.services.hash_backfill import (
    ContentHashServiceImpl,
    encode_chapter_aggregate_record,
)


def _session(tmp_path) -> tuple[Session, object]:
    engine = create_engine(f"sqlite:///{tmp_path / 'hash.db'}")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return factory(), engine


def _seed_book(session: Session) -> Book:
    book = Book(
        title="Hash Book",
        source_file_name="hash.txt",
        source_file_hash="source-hash-1",
        created_at=datetime.now(timezone.utc),
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title="第一章",
        display_title="第一章",
        chapter_title="第一章",
        source_title_line="第一章",
        word_count=10,
    )
    session.add(chapter)
    session.flush()
    session.add(
        Paragraph(
            id=f"B{book.id:04d}-C0001-P0001",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=1,
            raw_text="hello\r\nworld",
            normalized_text="hello\r\nworld",
            char_start=0,
            char_end=12,
        )
    )
    session.add(
        Paragraph(
            id=f"B{book.id:04d}-C0001-P0002",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=2,
            raw_text="second",
            normalized_text="second",
            char_start=13,
            char_end=19,
        )
    )
    session.commit()
    return book


def test_hash_backfill_and_idempotent(tmp_path) -> None:
    session, engine = _session(tmp_path)
    book = _seed_book(session)
    service = ContentHashServiceImpl(session)
    first = service.backfill_content_hashes(book_id=book.id)
    assert first["paragraph_updated"] == 2
    assert first["chapter_updated"] == 1
    second = service.backfill_content_hashes(book_id=book.id)
    assert second["paragraph_updated"] == 0
    assert second["paragraph_unchanged"] == 2
    assert second["chapter_unchanged"] == 1
    chapter = session.scalar(select(Chapter).where(Chapter.book_id == book.id))
    assert chapter is not None
    assert chapter.content_hash == calculate_text_hash("hello\nworld\nsecond")
    session.close()
    engine.dispose()


def test_crlf_lf_hash_consistent() -> None:
    assert calculate_text_hash("a\r\nb") == calculate_text_hash("a\nb")
    from app.narrative_core.hash_canon import canonicalize_text

    assert canonicalize_text("a\rb\r\nc") == "a\nb\nc"


def test_book_aggregate_hash_stable_and_unambiguous(tmp_path) -> None:
    session, engine = _session(tmp_path)
    service = ContentHashServiceImpl(session)
    h1 = calculate_text_hash("body-a")
    h2 = calculate_text_hash("body-b")
    chapters = [(1, "Title A", h1), (2, "Title B", h2)]
    digest = service.calculate_book_aggregate_hash(chapters)
    assert digest == service.calculate_book_aggregate_hash(list(reversed(chapters)))
    # Boundary ambiguity avoided for Protocol method.
    assert service.calculate_book_content_hash(["ab", "c"]) != service.calculate_book_content_hash(
        ["a", "bc"]
    )
    # Title participates in aggregate.
    alt = service.calculate_book_aggregate_hash([(1, "Other", h1), (2, "Title B", h2)])
    assert alt != digest
    # Length-prefixed record is deterministic.
    assert encode_chapter_aggregate_record(1, "Title A", h1).startswith("1:")
    session.close()
    engine.dispose()

def test_refresh_after_import_or_reparse(tmp_path) -> None:
    session, engine = _session(tmp_path)
    book = _seed_book(session)
    service = ContentHashServiceImpl(session)
    summary = service.refresh_hashes_after_import_or_reparse(book.id)
    assert "book_content_hash" in summary
    assert len(summary["book_content_hash"]) == 64
    again = service.compute_book_content_hash(book.id)
    assert again == summary["book_content_hash"]
    session.close()
    engine.dispose()
