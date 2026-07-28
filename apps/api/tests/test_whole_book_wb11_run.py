"""WB-1.1 — whole-book run state machine tests."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Book, Chapter, Paragraph, WholeBookRun
from app.narrative_core.contracts.whole_book_contract_v1 import WHOLE_BOOK_STAGE_CODES_V1
from app.narrative_core.migrations.runner import apply_narrative_migrations
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_run_v1_service import (
    DIAGNOSTIC_ENGINE_ID,
    cancel_whole_book_run_v1,
    create_whole_book_run_v1,
    get_run,
    list_stages,
    pause_whole_book_run_v1,
    resume_whole_book_run_v1,
    start_whole_book_run_v1,
)
from app.narrative_core.services.whole_book_snapshot_v1_service import create_or_reuse_book_snapshot_v1


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'run.db'}")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record) -> None:
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    apply_narrative_migrations(engine)
    return engine


def _seed(session) -> tuple[Book, int]:
    book = Book(title="书", source_file_name="a.txt", source_file_hash="d" * 64)
    session.add(book)
    session.flush()
    ch = Chapter(book_id=book.id, chapter_index=0, title="章")
    session.add(ch)
    session.flush()
    text = "内容"
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
    snap = create_or_reuse_book_snapshot_v1(session, book.id)["snapshot"]
    return book, snap.id


def test_create_idempotency_and_stages(tmp_path) -> None:
    engine = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snapshot_id = _seed(session)
        client_id = str(uuid.uuid4())
        run1 = create_whole_book_run_v1(
            session,
            book.id,
            snapshot_id,
            "whole_book_native",
            client_id,
            "fixture",
        )
        run2 = create_whole_book_run_v1(
            session,
            book.id,
            snapshot_id,
            "whole_book_native",
            client_id,
            "fixture",
        )
        assert run1.id == run2.id
        run3 = create_whole_book_run_v1(
            session,
            book.id,
            snapshot_id,
            "whole_book_native",
            str(uuid.uuid4()),
            "fixture",
        )
        assert run3.id != run1.id
        assert run1.engine_id == DIAGNOSTIC_ENGINE_ID
        assert run1.result_origin == "fixture"
        assert run1.consent_id is None
        stages = list_stages(session, run1.id)
        assert [s.stage_code for s in stages] == list(WHOLE_BOOK_STAGE_CODES_V1)
        snap_stage = stages[0]
        assert snap_stage.stage_code == "snapshot"
        assert snap_stage.status == "completed"
        assert snap_stage.progress_current == 1
    engine.dispose()


def test_snapshot_validation_errors(tmp_path) -> None:
    engine = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snapshot_id = _seed(session)
        with pytest.raises(WholeBookFoundationError) as exc:
            create_whole_book_run_v1(
                session,
                book.id,
                99999,
                "whole_book_native",
                str(uuid.uuid4()),
                "fixture",
            )
        assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND.value
    engine.dispose()


def test_transitions_and_terminal(tmp_path) -> None:
    engine = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snapshot_id = _seed(session)
        run = create_whole_book_run_v1(
            session,
            book.id,
            snapshot_id,
            "whole_book_native",
            str(uuid.uuid4()),
            "fixture",
        )
        started = start_whole_book_run_v1(session, run.id)
        assert started.status == "running"
        paused = pause_whole_book_run_v1(session, run.id)
        assert paused.status == "paused"
        resumed = resume_whole_book_run_v1(session, run.id)
        assert resumed.status == "pending"
        cancelled = cancel_whole_book_run_v1(session, run.id)
        assert cancelled.status == "cancelled"
        with pytest.raises(WholeBookFoundationError) as exc:
            start_whole_book_run_v1(session, run.id)
        assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_TERMINAL.value
    engine.dispose()


def test_no_provider_units_created(tmp_path) -> None:
    engine = _engine(tmp_path)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snapshot_id = _seed(session)
        run = create_whole_book_run_v1(
            session,
            book.id,
            snapshot_id,
            "whole_book_native",
            str(uuid.uuid4()),
            "fixture",
        )
        start_whole_book_run_v1(session, run.id)
        pause_whole_book_run_v1(session, run.id)
        resume_whole_book_run_v1(session, run.id)
        from app.db.models import WholeBookProviderUnit

        count = session.query(WholeBookProviderUnit).filter_by(run_id=run.id).count()
        assert count == 0
    engine.dispose()
