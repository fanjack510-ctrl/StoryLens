"""WB-1.3 — cross-chapter windowing tests."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Book, Chapter, Paragraph, WholeBookWindow
from app.narrative_core.migrations.runner import apply_narrative_migrations
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_run_v1_service import create_whole_book_run_v1
from app.narrative_core.services.whole_book_snapshot_v1_service import create_or_reuse_book_snapshot_v1
from app.narrative_core.services.whole_book_windowing_v1_service import (
    WINDOWING_VERSION,
    generate_whole_book_windows_v1,
    list_checkpoints,
)


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'win.db'}")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record) -> None:
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    apply_narrative_migrations(engine)
    return engine


def _seed(session, paragraphs: list[str]) -> tuple[Book, int]:
    book = Book(title="书", source_file_name="a.txt", source_file_hash="e" * 64)
    session.add(book)
    session.flush()
    ch = Chapter(book_id=book.id, chapter_index=0, title="章")
    session.add(ch)
    session.flush()
    for idx, text in enumerate(paragraphs):
        session.add(
            Paragraph(
                id=f"p-{book.id}-{idx}",
                book_id=book.id,
                chapter_id=ch.id,
                paragraph_index=idx,
                raw_text=text,
                normalized_text=text,
                char_start=0,
                char_end=len(text),
            )
        )
    session.flush()
    snap = create_or_reuse_book_snapshot_v1(session, book.id)["snapshot"]
    return book, snap.id


def _run(session, book_id: int, snapshot_id: int):
    return create_whole_book_run_v1(
        session,
        book_id,
        snapshot_id,
        "whole_book_native",
        str(uuid.uuid4()),
        "fixture",
    )


def test_coverage_full_and_reuse(tmp_path) -> None:
    engine = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snapshot_id = _seed(session, ["甲", "乙", "丙"])
        run = _run(session, book.id, snapshot_id)
        first = generate_whole_book_windows_v1(session, run.id)
        assert first["reused"] is False
        assert first["windowing_version"] == WINDOWING_VERSION
        coverage = first["coverage"]
        assert coverage["coverage_ratio"] == 1.0
        assert coverage["uncovered_paragraphs"] == 0
        assert coverage["order_valid"] is True
        second = generate_whole_book_windows_v1(session, run.id)
        assert second["reused"] is True
        checkpoints = list_checkpoints(session, run.id)
        manifest = checkpoints[0]["checkpoint_payload"]
        assert "windowing_version" in manifest
        assert "snapshot_content_hash" in manifest
        blob = json.dumps(manifest)
        assert "甲" not in blob
        assert "乙" not in blob
    engine.dispose()


def test_empty_book_windowing(tmp_path) -> None:
    engine = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book = Book(title="空", source_file_name="e.txt", source_file_hash="f" * 64)
        session.add(book)
        session.flush()
        snap = create_or_reuse_book_snapshot_v1(session, book.id)["snapshot"]
        run = _run(session, book.id, snap.id)
        result = generate_whole_book_windows_v1(session, run.id)
        assert result["windows"] == []
        assert result["coverage"]["coverage_ratio"] == 1.0
    engine.dispose()


def test_window_set_conflict(tmp_path) -> None:
    engine = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snapshot_id = _seed(session, ["一", "二"])
        run = _run(session, book.id, snapshot_id)
        generate_whole_book_windows_v1(session, run.id)
        row = session.query(WholeBookWindow).filter_by(run_id=run.id).first()
        assert row is not None
        row.window_hash = "0" * 64
        session.flush()
        with pytest.raises(WholeBookFoundationError) as exc:
            generate_whole_book_windows_v1(session, run.id)
        assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_WINDOW_SET_CONFLICT.value
    engine.dispose()


def test_run_stage_advances_after_windowing(tmp_path) -> None:
    engine = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snapshot_id = _seed(session, ["段"])
        run = _run(session, book.id, snapshot_id)
        generate_whole_book_windows_v1(session, run.id)
        session.refresh(run)
        assert run.current_stage_code == "extract_entities_events"
        assert run.status == "pending"
    engine.dispose()
