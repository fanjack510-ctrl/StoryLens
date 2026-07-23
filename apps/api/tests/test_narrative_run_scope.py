"""Agent B: AnalysisRun scope validation tests (Phase 1A)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AnalysisRun, Base, Book, Chapter
from app.narrative_core.enums import AnalysisScopeType, AnalysisType, SnapshotStatus
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.migrations.runner import apply_narrative_phase1p_migrations
from app.narrative_core.services.run_scope_service import (
    StubSnapshotValidationGateway,
    make_stub_completed_snapshot,
)
from app.narrative_core.services.run_stage_service import RunStageService


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'scope.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    return engine


def _session(engine) -> Session:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return factory()


def _seed_book_with_chapters(session: Session, *, n_chapters: int = 3) -> tuple[Book, list[Chapter]]:
    book = Book(
        title="Scope Test Book",
        source_file_name="scope.txt",
        source_file_hash="b" * 64,
    )
    session.add(book)
    session.flush()
    chapters: list[Chapter] = []
    for i in range(n_chapters):
        chapter = Chapter(
            book_id=book.id,
            chapter_index=i,
            title=f"Chapter {i + 1}",
            chapter_title=f"Chapter {i + 1}",
            display_title=f"Chapter {i + 1}",
            source_title_line=f"第{i + 1}章",
        )
        session.add(chapter)
        chapters.append(chapter)
    session.flush()
    return book, chapters


@pytest.fixture
def scope_env(tmp_path):
    engine = _engine(tmp_path)
    session = _session(engine)
    gateway = StubSnapshotValidationGateway(session)
    service = RunStageService(session, snapshot_gateway=gateway)
    book, chapters = _seed_book_with_chapters(session)
    session.commit()
    yield {
        "engine": engine,
        "session": session,
        "service": service,
        "gateway": gateway,
        "book": book,
        "chapters": chapters,
    }
    session.close()
    engine.dispose()


def test_legacy_chapter_run_readable_after_migration(tmp_path) -> None:
    """Old chapter runs remain readable via subject_type/subject_id (no chapter_id column)."""
    engine = _engine(tmp_path)
    session = _session(engine)
    book = Book(
        title="Legacy Book",
        source_file_name="legacy.txt",
        source_file_hash="a" * 64,
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=0,
        title="L1",
        chapter_title="L1",
        display_title="L1",
        source_title_line="第1章",
    )
    session.add(chapter)
    session.flush()
    # Simulate a pre-Phase-1 row: scope fields NULL, binding via subject_*.
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="local",
        model="m",
        prompt_version="v1",
        schema_version="v1",
        input_hash="h" * 64,
        status="completed",
        analysis_type=None,
        scope_type=None,
        book_id=None,
        start_chapter_id=None,
        end_chapter_id=None,
        book_snapshot_id=None,
    )
    session.add(run)
    session.commit()

    assert "chapter_id" not in AnalysisRun.__table__.c
    loaded = session.get(AnalysisRun, run.id)
    assert loaded is not None
    assert loaded.subject_type == "chapter"
    assert loaded.subject_id == str(chapter.id)
    assert loaded.scope_type is None
    assert loaded.analysis_type is None
    service = RunStageService(
        session, snapshot_gateway=StubSnapshotValidationGateway(session)
    )
    service.validate_run_scope(loaded)
    # Raw SQL path also preserves legacy subject binding after migrations.
    row = session.execute(
        text(
            "SELECT subject_type, subject_id, scope_type, analysis_type, book_snapshot_id "
            "FROM analysis_runs WHERE id = :rid"
        ),
        {"rid": run.id},
    ).fetchone()
    assert row is not None
    assert row[0] == "chapter"
    assert row[1] == str(chapter.id)
    assert row[2] is None
    session.close()
    engine.dispose()


def test_legacy_subject_type_subject_id_compat(scope_env) -> None:
    service: RunStageService = scope_env["service"]
    chapter = scope_env["chapters"][0]
    run = service.create_scoped_run(
        scope_type=AnalysisScopeType.CHAPTER,
        analysis_type=AnalysisType.SCENE_PIPELINE,
        chapter_id=chapter.id,
    )
    assert run.subject_type == "chapter"
    assert run.subject_id == str(chapter.id)
    assert run.scope_type == "chapter"
    assert run.start_chapter_id is None
    assert run.end_chapter_id is None
    assert run.book_snapshot_id is None


def test_chapter_scope_rejects_range_bounds(scope_env) -> None:
    service: RunStageService = scope_env["service"]
    chapters = scope_env["chapters"]
    with pytest.raises(NarrativeCoreError) as exc:
        service.create_scoped_run(
            scope_type=AnalysisScopeType.CHAPTER,
            analysis_type=AnalysisType.SCENE_PIPELINE,
            chapter_id=chapters[0].id,
            start_chapter_id=chapters[0].id,
            end_chapter_id=chapters[1].id,
        )
    assert exc.value.code == NarrativeCoreErrorCode.INVALID_RUN_SCOPE


def test_range_scope_missing_bounds_fails(scope_env) -> None:
    service: RunStageService = scope_env["service"]
    book = scope_env["book"]
    with pytest.raises(NarrativeCoreError) as exc:
        service.create_scoped_run(
            scope_type=AnalysisScopeType.CHAPTER_RANGE,
            analysis_type=AnalysisType.SCENE_PIPELINE,
            book_id=book.id,
            start_chapter_id=None,
            end_chapter_id=None,
        )
    assert exc.value.code == NarrativeCoreErrorCode.RANGE_SCOPE_REQUIRES_BOUNDS


def test_range_scope_invalid_order_fails(scope_env) -> None:
    service: RunStageService = scope_env["service"]
    book = scope_env["book"]
    chapters = scope_env["chapters"]
    with pytest.raises(NarrativeCoreError) as exc:
        service.create_scoped_run(
            scope_type=AnalysisScopeType.CHAPTER_RANGE,
            analysis_type=AnalysisType.SCENE_PIPELINE,
            book_id=book.id,
            start_chapter_id=chapters[2].id,
            end_chapter_id=chapters[0].id,
        )
    assert exc.value.code == NarrativeCoreErrorCode.RANGE_SCOPE_INVALID_ORDER


def test_range_scope_chapters_must_same_book(scope_env) -> None:
    service: RunStageService = scope_env["service"]
    session: Session = scope_env["session"]
    book = scope_env["book"]
    chapters = scope_env["chapters"]
    other = Book(
        title="Other",
        source_file_name="other.txt",
        source_file_hash="c" * 64,
    )
    session.add(other)
    session.flush()
    foreign = Chapter(
        book_id=other.id,
        chapter_index=0,
        title="Foreign",
        chapter_title="Foreign",
        display_title="Foreign",
        source_title_line="第1章",
    )
    session.add(foreign)
    session.commit()
    with pytest.raises(NarrativeCoreError) as exc:
        service.create_scoped_run(
            scope_type=AnalysisScopeType.CHAPTER_RANGE,
            analysis_type=AnalysisType.SCENE_PIPELINE,
            book_id=book.id,
            start_chapter_id=chapters[0].id,
            end_chapter_id=foreign.id,
        )
    assert exc.value.code == NarrativeCoreErrorCode.INVALID_RUN_SCOPE


def test_book_scope_requires_snapshot(scope_env) -> None:
    service: RunStageService = scope_env["service"]
    book = scope_env["book"]
    with pytest.raises(NarrativeCoreError) as exc:
        service.create_scoped_run(
            scope_type=AnalysisScopeType.BOOK,
            analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
            book_id=book.id,
            book_snapshot_id=None,
        )
    assert exc.value.code == NarrativeCoreErrorCode.BOOK_SCOPE_REQUIRES_SNAPSHOT


def test_book_scope_snapshot_not_completed_fails(scope_env) -> None:
    service: RunStageService = scope_env["service"]
    session: Session = scope_env["session"]
    book = scope_env["book"]
    snapshot = make_stub_completed_snapshot(
        session,
        book_id=book.id,
        content_hash="d" * 64,
        snapshot_status=SnapshotStatus.BUILDING.value,
    )
    session.commit()
    with pytest.raises(NarrativeCoreError) as exc:
        service.create_scoped_run(
            scope_type=AnalysisScopeType.BOOK,
            analysis_type=AnalysisType.WHOLE_BOOK_ENHANCED,
            book_id=book.id,
            book_snapshot_id=snapshot.id,
        )
    assert exc.value.code == NarrativeCoreErrorCode.SNAPSHOT_NOT_COMPLETED


def test_book_scope_snapshot_book_mismatch_fails(scope_env) -> None:
    service: RunStageService = scope_env["service"]
    session: Session = scope_env["session"]
    book = scope_env["book"]
    other = Book(
        title="Other Book",
        source_file_name="ob.txt",
        source_file_hash="e" * 64,
    )
    session.add(other)
    session.flush()
    snapshot = make_stub_completed_snapshot(
        session, book_id=other.id, content_hash="f" * 64
    )
    session.commit()
    with pytest.raises(NarrativeCoreError) as exc:
        service.create_scoped_run(
            scope_type=AnalysisScopeType.BOOK,
            analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
            book_id=book.id,
            book_snapshot_id=snapshot.id,
        )
    assert exc.value.code == NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH


def test_book_scope_simulated_run_with_completed_snapshot(scope_env) -> None:
    service: RunStageService = scope_env["service"]
    session: Session = scope_env["session"]
    book = scope_env["book"]
    snapshot = make_stub_completed_snapshot(session, book_id=book.id, content_hash="1" * 64)
    session.commit()
    run = service.create_scoped_run(
        scope_type=AnalysisScopeType.BOOK,
        analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
        book_id=book.id,
        book_snapshot_id=snapshot.id,
    )
    assert run.scope_type == "book"
    assert run.book_snapshot_id == snapshot.id
    assert run.subject_type == "book"
    assert run.task_type == "whole_book_simulated"
    assert run.status == "queued"


def test_bind_run_snapshot(scope_env) -> None:
    service: RunStageService = scope_env["service"]
    session: Session = scope_env["session"]
    book = scope_env["book"]
    first = make_stub_completed_snapshot(session, book_id=book.id, content_hash="2" * 64)
    second = make_stub_completed_snapshot(session, book_id=book.id, content_hash="3" * 64)
    session.commit()
    run = service.create_scoped_run(
        scope_type=AnalysisScopeType.BOOK,
        analysis_type=AnalysisType.WHOLE_BOOK_ENHANCED,
        book_id=book.id,
        book_snapshot_id=first.id,
    )
    bound = service.bind_run_snapshot(run.id, second.id)
    assert bound.book_snapshot_id == second.id


def test_range_scope_happy_path(scope_env) -> None:
    service: RunStageService = scope_env["service"]
    book = scope_env["book"]
    chapters = scope_env["chapters"]
    run = service.create_scoped_run(
        scope_type=AnalysisScopeType.CHAPTER_RANGE,
        analysis_type=AnalysisType.SCENE_PIPELINE,
        book_id=book.id,
        start_chapter_id=chapters[0].id,
        end_chapter_id=chapters[2].id,
    )
    assert run.scope_type == "chapter_range"
    assert run.start_chapter_id == chapters[0].id
    assert run.end_chapter_id == chapters[2].id
