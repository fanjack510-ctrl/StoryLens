"""WB-1.2 — immutable book snapshot tests."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Book, BookSnapshot, Chapter, Paragraph
from app.narrative_core.migrations.runner import apply_narrative_migrations
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_snapshot_v1_service import (
    UPDATE_COMPLETED_FORBIDDEN,
    _assert_snapshot_mutable,
    create_or_reuse_book_snapshot_v1,
    get_snapshot_paragraph_text,
    list_paragraphs,
)
from app.services.whole_book_source_fingerprint import compute_book_revision_hash_v1, sha256_utf8


def _engine(tmp_path):
    db_path = tmp_path / "snap.db"
    engine = create_engine(f"sqlite:///{db_path}")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record) -> None:
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    apply_narrative_migrations(engine)
    return engine, db_path


def _seed_book(session, *, chapters: int = 2, text: str = "段落") -> Book:
    book = Book(title="书", source_file_name="a.txt", source_file_hash="b" * 64)
    session.add(book)
    session.flush()
    for idx in range(chapters):
        ch = Chapter(book_id=book.id, chapter_index=idx, title=f"第{idx}章")
        session.add(ch)
        session.flush()
        body = f"{text}{idx}"
        session.add(
            Paragraph(
                id=f"p-{book.id}-{idx}",
                book_id=book.id,
                chapter_id=ch.id,
                paragraph_index=0,
                raw_text=body,
                normalized_text=body,
                char_start=0,
                char_end=len(body),
            )
        )
    session.flush()
    return book


def test_create_reuse_and_version(tmp_path) -> None:
    engine, _ = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book = _seed_book(session)
        first = create_or_reuse_book_snapshot_v1(session, book.id)
        assert first["reused"] is False
        assert first["snapshot"].snapshot_version == 1
        assert first["snapshot"].snapshot_status == "completed"
        assert first["snapshot"].completed_at is not None

        second = create_or_reuse_book_snapshot_v1(session, book.id)
        assert second["reused"] is True
        assert second["snapshot"].id == first["snapshot"].id

        para = session.query(Paragraph).filter_by(book_id=book.id, paragraph_index=0).first()
        para.normalized_text = "改"
        para.raw_text = "改"
        session.flush()
        third = create_or_reuse_book_snapshot_v1(session, book.id)
        assert third["reused"] is False
        assert third["snapshot"].snapshot_version == 2
    engine.dispose()


def test_global_paragraph_index_and_hashes(tmp_path) -> None:
    engine, _ = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book = _seed_book(session, chapters=2)
        result = create_or_reuse_book_snapshot_v1(session, book.id)
        snap = result["snapshot"]
        assert snap.content_hash == compute_book_revision_hash_v1(session, book.id)
        items, total = list_paragraphs(session, snap.id, limit=100)
        assert total == 2
        assert [p["global_paragraph_index"] for p in items] == [0, 1]
        for item in items:
            assert item["character_count"] == len(item["text"])
            assert item["text_hash"] == sha256_utf8(item["text"])
        restored = get_snapshot_paragraph_text(session, items[0]["snapshot_paragraph_id"])
        assert restored == items[0]["text"]
    engine.dispose()


def test_empty_book_snapshot(tmp_path) -> None:
    engine, _ = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book = Book(title="空", source_file_name="e.txt", source_file_hash="c" * 64)
        session.add(book)
        session.flush()
        result = create_or_reuse_book_snapshot_v1(session, book.id)
        snap = result["snapshot"]
        assert snap.chapter_count == 0
        assert snap.paragraph_count == 0
        assert snap.snapshot_status == "completed"
    engine.dispose()


def test_service_rejects_completed_update(tmp_path) -> None:
    engine, _ = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book = _seed_book(session, chapters=1)
        result = create_or_reuse_book_snapshot_v1(session, book.id)
        snap = result["snapshot"]
        with pytest.raises(WholeBookFoundationError) as exc:
            _assert_snapshot_mutable(snap)
        assert exc.value.code == UPDATE_COMPLETED_FORBIDDEN
    engine.dispose()


def test_db_trigger_blocks_completed_update(tmp_path) -> None:
    engine, db_path = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book = _seed_book(session, chapters=1)
        result = create_or_reuse_book_snapshot_v1(session, book.id)
        snap_id = result["snapshot"].id
        session.commit()
    with factory() as session:
        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE book_snapshots SET chapter_count = 99 WHERE id = :id"),
                {"id": snap_id},
            )
            session.commit()
    engine.dispose()
    assert db_path.exists()
