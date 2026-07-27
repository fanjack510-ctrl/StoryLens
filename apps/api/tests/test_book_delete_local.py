"""Local tests for transactional book delete (CHG-20260721-014)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisRun,
    Base,
    Book,
    Chapter,
    Paragraph,
    ReaderJourneyRun,
    Scene,
)
from app.services.book_delete import (
    BookHasActiveTasksError,
    BookNotFoundError,
    delete_book,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    # Mirror production FK pragma
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _make_book(session: Session, title: str = "测试书", *, source_name: str = "a.txt") -> Book:
    content = f"第一章\n\n正文内容 {title}".encode("utf-8")
    book = Book(
        title=title,
        source_file_name=source_name,
        source_file_hash=hashlib.sha256(content).hexdigest(),
        import_status="imported",
        source_content=content,
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title="第一章",
        word_count=10,
    )
    session.add(chapter)
    session.flush()
    pid = f"B{book.id:04d}-C0001-P0001"
    session.add(
        Paragraph(
            id=pid,
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=1,
            raw_text="正文",
            normalized_text="正文",
            char_start=0,
            char_end=2,
        )
    )
    chapter.start_paragraph_id = pid
    chapter.end_paragraph_id = pid
    session.commit()
    session.refresh(book)
    return book


def test_delete_missing_book():
    session = _session()
    with pytest.raises(BookNotFoundError):
        delete_book(session, 999)


def test_delete_book_and_chapters_paragraphs():
    session = _session()
    book = _make_book(session)
    book_id = book.id
    delete_book(session, book_id)
    assert session.get(Book, book_id) is None
    assert session.scalar(select(func.count()).select_from(Chapter).where(Chapter.book_id == book_id)) == 0
    assert (
        session.scalar(select(func.count()).select_from(Paragraph).where(Paragraph.book_id == book_id))
        == 0
    )


def test_delete_scenes_and_analysis_runs():
    session = _session()
    book = _make_book(session)
    chapter = session.scalar(select(Chapter).where(Chapter.book_id == book.id))
    assert chapter is not None
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="v1",
        schema_version="1",
        input_hash="abc",
        status="succeeded",
    )
    session.add(run)
    session.flush()
    session.add(
        Scene(
            book_id=book.id,
            chapter_id=chapter.id,
            scene_key="s1",
            ordinal=1,
            start_paragraph_id=chapter.start_paragraph_id,
            end_paragraph_id=chapter.end_paragraph_id,
            content_hash="hash",
            created_by_run_id=run.id,
            boundary_confidence=1.0,
        )
    )
    session.commit()
    delete_book(session, book.id)
    assert session.scalar(select(func.count()).select_from(Scene)) == 0
    assert session.scalar(select(func.count()).select_from(AnalysisRun)) == 0


def test_delete_reader_journey():
    session = _session()
    book = _make_book(session)
    chapter = session.scalar(select(Chapter).where(Chapter.book_id == book.id))
    assert chapter is not None
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="v1",
        schema_version="1",
        input_hash="abc",
        status="succeeded",
    )
    session.add(run)
    session.flush()
    session.add(
        ReaderJourneyRun(
            analysis_run_id=run.id,
            book_id=book.id,
            chapter_id=chapter.id,
            status="succeeded",
            provider_name="aliyun_qwen_plus",
            model_name="qwen3.7-plus",
            client_request_id="req-1",
        )
    )
    session.commit()
    delete_book(session, book.id)
    assert session.scalar(select(func.count()).select_from(ReaderJourneyRun)) == 0


def test_does_not_delete_other_books():
    session = _session()
    a = _make_book(session, "A", source_name="a.txt")
    b = _make_book(session, "B", source_name="b.txt")
    delete_book(session, a.id)
    assert session.get(Book, a.id) is None
    assert session.get(Book, b.id) is not None
    assert session.scalar(select(func.count()).select_from(Chapter).where(Chapter.book_id == b.id)) == 1


def test_does_not_delete_original_filesystem_files(tmp_path: Path):
    session = _session()
    original = tmp_path / "novel.txt"
    original.write_text("第一章\n\n用户原文件", encoding="utf-8")
    book = _make_book(session, source_name=str(original))
    delete_book(session, book.id)
    assert original.exists()
    assert original.read_text(encoding="utf-8") == "第一章\n\n用户原文件"


def test_docx_epub_paths_untouched(tmp_path: Path):
    session = _session()
    docx = tmp_path / "n.docx"
    epub = tmp_path / "n.epub"
    docx.write_bytes(b"PK\x03\x04fake-docx")
    epub.write_bytes(b"PK\x03\x04fake-epub")
    b1 = _make_book(session, "D", source_name=str(docx))
    b2 = _make_book(session, "E", source_name=str(epub))
    # unique hashes — _make_book uses title in content so OK
    delete_book(session, b1.id)
    delete_book(session, b2.id)
    assert docx.exists()
    assert epub.exists()


def test_active_task_blocks_delete():
    session = _session()
    book = _make_book(session)
    chapter = session.scalar(select(Chapter).where(Chapter.book_id == book.id))
    assert chapter is not None
    session.add(
        AnalysisRun(
            task_type="scene_pipeline",
            subject_type="chapter",
            subject_id=str(chapter.id),
            provider="aliyun_qwen_plus",
            model="qwen3.7-plus",
            prompt_version="v1",
            schema_version="1",
            input_hash="abc",
            status="running",
        )
    )
    session.commit()
    with pytest.raises(BookHasActiveTasksError):
        delete_book(session, book.id)
    assert session.get(Book, book.id) is not None
    assert session.scalar(select(func.count()).select_from(AnalysisRun)) == 1


def test_active_whole_book_native_run_blocks_delete():
    session = _session()
    book = _make_book(session)
    session.add(
        AnalysisRun(
            task_type="whole_book_overview",
            subject_type="book",
            subject_id=str(book.id),
            provider="private-native-overview-v1",
            model="native-overview-1",
            prompt_version="native-overview-window-v1",
            schema_version="1.0",
            input_hash="abc",
            status="analyzing",
        )
    )
    session.commit()
    with pytest.raises(BookHasActiveTasksError):
        delete_book(session, book.id)
    assert session.get(Book, book.id) is not None
    assert session.scalar(select(func.count()).select_from(AnalysisRun)) == 1


def test_completed_whole_book_native_run_allows_delete():
    session = _session()
    book = _make_book(session)
    book_id = int(book.id)
    session.add(
        AnalysisRun(
            task_type="whole_book_overview",
            subject_type="book",
            subject_id=str(book.id),
            provider="private-native-overview-v1",
            model="native-overview-1",
            prompt_version="native-overview-window-v1",
            schema_version="1.0",
            input_hash="abc",
            status="completed",
        )
    )
    session.commit()
    delete_book(session, book_id)
    assert session.get(Book, book_id) is None


def test_failed_delete_rolls_back_on_active_after_child():
    """Active task leaves all rows intact (no partial delete)."""
    session = _session()
    book = _make_book(session)
    chapter = session.scalar(select(Chapter).where(Chapter.book_id == book.id))
    assert chapter is not None
    session.add(
        AnalysisRun(
            task_type="scene_pipeline",
            subject_type="chapter",
            subject_id=str(chapter.id),
            provider="aliyun_qwen_plus",
            model="qwen3.7-plus",
            prompt_version="v1",
            schema_version="1",
            input_hash="abc",
            status="queued",
        )
    )
    session.commit()
    with pytest.raises(BookHasActiveTasksError):
        delete_book(session, book.id)
    assert session.scalar(select(func.count()).select_from(Chapter).where(Chapter.book_id == book.id)) == 1
    assert session.scalar(select(func.count()).select_from(Paragraph).where(Paragraph.book_id == book.id)) == 1


def test_no_orphan_rows_after_delete():
    session = _session()
    book = _make_book(session)
    chapter = session.scalar(select(Chapter).where(Chapter.book_id == book.id))
    assert chapter is not None
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="v1",
        schema_version="1",
        input_hash="abc",
        status="failed",
    )
    session.add(run)
    session.flush()
    session.add(
        Scene(
            book_id=book.id,
            chapter_id=chapter.id,
            scene_key="s1",
            ordinal=1,
            start_paragraph_id=chapter.start_paragraph_id,
            end_paragraph_id=chapter.end_paragraph_id,
            content_hash="hash",
            created_by_run_id=run.id,
            boundary_confidence=1.0,
        )
    )
    session.commit()
    book_id = book.id
    delete_book(session, book_id)
    assert session.scalar(select(func.count()).select_from(Book).where(Book.id == book_id)) == 0
    assert session.scalar(select(func.count()).select_from(Chapter).where(Chapter.book_id == book_id)) == 0
    assert session.scalar(select(func.count()).select_from(Paragraph).where(Paragraph.book_id == book_id)) == 0
    assert session.scalar(select(func.count()).select_from(Scene).where(Scene.book_id == book_id)) == 0
    assert session.scalar(select(func.count()).select_from(AnalysisRun)) == 0


def test_idempotent_second_delete_is_not_found():
    session = _session()
    book = _make_book(session)
    book_id = book.id
    delete_book(session, book_id)
    with pytest.raises(BookNotFoundError):
        delete_book(session, book_id)
