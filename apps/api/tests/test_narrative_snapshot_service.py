"""Agent A: book snapshot directed tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Book, BookSnapshot, Chapter, Paragraph
from app.narrative_core.enums import SnapshotStatus
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.hash_canon import calculate_text_hash
from app.narrative_core.migrations.runner import apply_narrative_phase1p_migrations
from app.narrative_core.services.hash_backfill import ContentHashServiceImpl
from app.narrative_core.services.snapshot_repository import BookSnapshotRepositoryImpl
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl


def _factory(tmp_path, name: str = "snap.db"):
    engine = create_engine(
        f"sqlite:///{tmp_path / name}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False), engine


def _seed_book(session: Session, *, title_suffix: str = "") -> Book:
    book = Book(
        title=f"Snap Book{title_suffix}",
        source_file_name=f"snap{title_suffix}.txt",
        source_file_hash=f"file-hash{title_suffix}",
        created_at=datetime.now(timezone.utc),
    )
    session.add(book)
    session.flush()
    for chapter_index, body in enumerate(
        [("第一章", ["甲段\r\n行", "乙段"]), ("第二章", ["丙段"])],
        start=1,
    ):
        title, paragraphs = body
        chapter = Chapter(
            book_id=book.id,
            chapter_index=chapter_index,
            title=title,
            display_title=title,
            chapter_title=title,
            source_title_line=title,
            word_count=sum(len(p) for p in paragraphs),
        )
        session.add(chapter)
        session.flush()
        offset = 0
        for p_index, text_body in enumerate(paragraphs, start=1):
            session.add(
                Paragraph(
                    id=f"B{book.id:04d}-C{chapter_index:04d}-P{p_index:04d}",
                    book_id=book.id,
                    chapter_id=chapter.id,
                    paragraph_index=p_index,
                    raw_text=text_body,
                    normalized_text=text_body,
                    char_start=offset,
                    char_end=offset + len(text_body),
                )
            )
            offset += len(text_body) + 1
    session.commit()
    return book


def test_snapshot_create_validate_restore(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        service = BookSnapshotServiceImpl(session)
        snapshot = service.create_or_reuse_snapshot(book.id)
        session.commit()
        assert snapshot.snapshot_status == SnapshotStatus.COMPLETED
        assert snapshot.chapter_count == 2
        assert snapshot.paragraph_count == 3
        assert service.validate_snapshot(snapshot.id) is True

        chapters = sorted(snapshot.chapters, key=lambda c: c.chapter_order)
        assert chapters[0].content_text == "甲段\r\n行\n乙段"
        para = sorted(chapters[0].paragraphs, key=lambda p: p.paragraph_order)[0]
        restored = service.get_snapshot_paragraph_text(para.id)
        assert restored == "甲段\r\n行"
        assert calculate_text_hash(restored) == para.content_hash

        completed = service.get_completed_snapshot(snapshot.id)
        assert completed.id == snapshot.id
        assert service.validate_snapshot_for_book(snapshot.id, book.id) is True
    engine.dispose()


def test_offset_oob_and_hash_mismatch_detected(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        service = BookSnapshotServiceImpl(session)
        snapshot = service.create_or_reuse_snapshot(book.id)
        session.commit()
        chapter = sorted(snapshot.chapters, key=lambda c: c.chapter_order)[0]
        para = sorted(chapter.paragraphs, key=lambda p: p.paragraph_order)[0]

        para.end_offset = len(chapter.content_text) + 10
        session.flush()
        assert service.validate_snapshot(snapshot.id) is False
        session.refresh(snapshot)
        assert snapshot.snapshot_status == SnapshotStatus.INVALID

        # Rebuild a fresh completed snapshot for hash-mismatch path.
        session.delete(snapshot)
        session.commit()
        snapshot2 = service.create_or_reuse_snapshot(book.id)
        session.commit()
        chapter2 = sorted(snapshot2.chapters, key=lambda c: c.chapter_order)[0]
        para2 = sorted(chapter2.paragraphs, key=lambda p: p.paragraph_order)[0]
        para2.content_hash = "0" * 64
        session.flush()
        with pytest.raises(NarrativeCoreError) as exc_info:
            service.get_snapshot_paragraph_text(para2.id)
        assert exc_info.value.code == NarrativeCoreErrorCode.SNAPSHOT_INTEGRITY_FAILED
    engine.dispose()


def test_snapshot_reuse_and_content_change(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        service = BookSnapshotServiceImpl(session)
        first = service.create_or_reuse_snapshot(book.id)
        session.commit()
        second = service.create_or_reuse_snapshot(book.id)
        session.commit()
        assert first.id == second.id

        chapter = session.scalar(
            select(Chapter).where(Chapter.book_id == book.id, Chapter.chapter_index == 1)
        )
        assert chapter is not None
        para = session.scalar(
            select(Paragraph).where(
                Paragraph.chapter_id == chapter.id, Paragraph.paragraph_index == 1
            )
        )
        assert para is not None
        para.normalized_text = "正文已变更"
        para.raw_text = "正文已变更"
        session.commit()

        third = service.create_or_reuse_snapshot(book.id)
        session.commit()
        assert third.id != first.id
        assert third.content_hash != first.content_hash
        assert third.snapshot_status == SnapshotStatus.COMPLETED
    engine.dispose()


def test_building_and_failed_not_completed(tmp_path) -> None:
    factory, engine = _factory(tmp_path)
    with factory() as session:
        book = _seed_book(session)
        hashes = ContentHashServiceImpl(session)
        content_hash = hashes.compute_book_content_hash(book.id)
        repo = BookSnapshotRepositoryImpl(session)
        building = repo.create_snapshot_record(
            book.id,
            content_hash + "-building-unique",
            snapshot_status=SnapshotStatus.BUILDING,
        )
        failed = repo.create_snapshot_record(
            book.id,
            content_hash + "-failed-unique",
            snapshot_status=SnapshotStatus.FAILED,
        )
        session.commit()
        service = BookSnapshotServiceImpl(session)
        with pytest.raises(NarrativeCoreError) as building_exc:
            service.get_completed_snapshot(building.id)
        assert building_exc.value.code == NarrativeCoreErrorCode.SNAPSHOT_NOT_COMPLETED
        with pytest.raises(NarrativeCoreError) as failed_exc:
            service.get_completed_snapshot(failed.id)
        assert failed_exc.value.code == NarrativeCoreErrorCode.SNAPSHOT_NOT_COMPLETED
    engine.dispose()


def test_concurrent_unique_constraint_reuse(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "concurrent.db")
    with factory() as session:
        book = _seed_book(session, title_suffix="-c")
        book_id = book.id
        session.commit()

    results: list[int] = []
    errors: list[BaseException] = []

    def worker() -> None:
        with factory() as worker_session:
            try:
                service = BookSnapshotServiceImpl(worker_session)
                snap = service.create_or_reuse_snapshot(book_id)
                worker_session.commit()
                results.append(snap.id)
            except BaseException as exc:  # noqa: BLE001
                worker_session.rollback()
                errors.append(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        for future in futures:
            future.result()

    assert not errors
    assert len(results) == 2
    assert results[0] == results[1]
    with factory() as session:
        rows = list(
            session.scalars(
                select(BookSnapshot).where(
                    BookSnapshot.book_id == book_id,
                    BookSnapshot.snapshot_status == SnapshotStatus.COMPLETED,
                )
            )
        )
        assert len(rows) == 1
        assert rows[0].id == results[0]
    engine.dispose()


def test_sqlite_integrity_unique_book_content_hash(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "integrity.db")
    with factory() as session:
        book = _seed_book(session, title_suffix="-u")
        service = BookSnapshotServiceImpl(session)
        snap = service.create_or_reuse_snapshot(book.id)
        session.commit()
        with pytest.raises(Exception):
            with session.begin_nested():
                session.execute(
                    text(
                        "INSERT INTO book_snapshots "
                        "(book_id, content_hash, chapter_count, paragraph_count, "
                        "character_count, snapshot_status, source_fingerprint, created_at) "
                        "VALUES (:book_id, :content_hash, 0, 0, 0, 'building', '', :created)"
                    ),
                    {
                        "book_id": book.id,
                        "content_hash": snap.content_hash,
                        "created": "2026-01-01",
                    },
                )
    engine.dispose()


def test_live_book_text_unchanged_by_snapshot(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "immutable.db")
    with factory() as session:
        book = _seed_book(session, title_suffix="-i")
        before = [
            (p.id, p.normalized_text)
            for p in session.scalars(select(Paragraph).where(Paragraph.book_id == book.id))
        ]
        service = BookSnapshotServiceImpl(session)
        service.create_or_reuse_snapshot(book.id)
        session.commit()
        after = [
            (p.id, p.normalized_text)
            for p in session.scalars(select(Paragraph).where(Paragraph.book_id == book.id))
        ]
        assert before == after
    engine.dispose()
