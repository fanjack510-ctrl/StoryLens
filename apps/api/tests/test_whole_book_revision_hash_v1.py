"""WB-1.2 / Wave B — unified book_revision_hash_v1 tests."""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Book, Chapter, Paragraph, ProviderConfiguration
from app.narrative_core.services.whole_book_cost_estimate_service import (
    compute_book_revision_hash,
    estimate_whole_book_analysis,
)
from app.narrative_core.services.whole_book_snapshot_v1_service import create_or_reuse_book_snapshot_v1
from app.services.whole_book_source_fingerprint import compute_book_revision_hash_v1


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'hash.db'}")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record) -> None:
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    return engine


def _seed(session, *, title: str = "章", text: str = "正文一段") -> Book:
    book = Book(title="书", source_file_name="a.txt", source_file_hash="a" * 64)
    session.add(book)
    session.flush()
    ch = Chapter(book_id=book.id, chapter_index=0, title=title)
    session.add(ch)
    session.flush()
    session.add(
        Paragraph(
            id=f"p-{book.id}",
            book_id=book.id,
            chapter_id=ch.id,
            paragraph_index=0,
            raw_text=text,
            normalized_text=text,
            char_start=0,
            char_end=len(text),
        )
    )
    session.flush()
    return book


def test_same_content_same_hash(tmp_path) -> None:
    engine = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book = _seed(session)
        h1 = compute_book_revision_hash_v1(session, book.id)
        h2 = compute_book_revision_hash(session, book.id)
        assert h1 == h2
    engine.dispose()


def test_title_change_changes_hash(tmp_path) -> None:
    engine = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book = _seed(session, title="甲")
        h1 = compute_book_revision_hash_v1(session, book.id)
        ch = session.query(Chapter).filter_by(book_id=book.id).one()
        ch.title = "乙"
        session.flush()
        h2 = compute_book_revision_hash_v1(session, book.id)
        assert h1 != h2
    engine.dispose()


def test_body_change_changes_hash(tmp_path) -> None:
    engine = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book = _seed(session, text="旧")
        h1 = compute_book_revision_hash_v1(session, book.id)
        para = session.query(Paragraph).filter_by(book_id=book.id).one()
        para.normalized_text = "新"
        para.raw_text = "新"
        session.flush()
        h2 = compute_book_revision_hash_v1(session, book.id)
        assert h1 != h2
    engine.dispose()


def test_crlf_normalized_stable_hash(tmp_path) -> None:
    engine = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book = _seed(session, text="行1\r\n行2")
        h_crlf = compute_book_revision_hash_v1(session, book.id)
        para = session.query(Paragraph).filter_by(book_id=book.id).one()
        para.normalized_text = "行1\n行2"
        para.raw_text = "行1\n行2"
        session.flush()
        h_lf = compute_book_revision_hash_v1(session, book.id)
        assert h_crlf == h_lf
    engine.dispose()


def test_cost_estimate_matches_snapshot_hash(tmp_path) -> None:
    engine = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book = _seed(session)
        provider = ProviderConfiguration(
            provider_name="fake",
            plus_model="qwen3.7-plus",
            enabled=True,
            disconnected=True,
        )
        session.add(provider)
        session.flush()
        estimate = estimate_whole_book_analysis(
            session, book.id, "whole_book_native", provider.id
        )
        snap = create_or_reuse_book_snapshot_v1(session, book.id)
        assert estimate.book_revision_hash == snap["snapshot"].content_hash
    engine.dispose()
