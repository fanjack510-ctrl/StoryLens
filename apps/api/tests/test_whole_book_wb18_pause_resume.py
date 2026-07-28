"""WB-1.8 — pause/resume/cancel soft semantics tests."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models import WholeBookProviderAttempt, WholeBookWindow
from app.narrative_core.services.whole_book_minimal_extraction_v1_service import (
    FixtureWindowAnalysisTransport,
    execute_minimal_entity_event_extraction_v1,
)
from app.narrative_core.services.whole_book_minimal_materialization_v1_service import (
    materialize_minimal_narrative_assets_v1,
)
from app.narrative_core.services.whole_book_minimal_overview_v1_service import (
    synthesize_minimal_book_overview_v1,
)
from app.narrative_core.services.whole_book_run_v1_service import (
    create_whole_book_run_v1,
    get_run,
    start_whole_book_run_v1,
)
from app.narrative_core.services.whole_book_runtime_control_v1_service import (
    aggregate_run_progress_v1,
    request_pause_whole_book_run_v1,
    request_cancel_whole_book_run_v1,
    resume_whole_book_run_v1,
)
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_windowing_v1_service import generate_whole_book_windows_v1
from tests.whole_book_minimal_test_helpers import ensure_consent, make_engine, prepare_sample_s_run, seed_sample_s_book


def _seed_twenty_windows(session, run_id: int, snapshot_id: int) -> None:
    from app.db.models import BookSnapshotParagraph
    from sqlalchemy import select

    from app.services.whole_book_source_fingerprint import sha256_utf8

    paragraphs = list(
        session.scalars(
            select(BookSnapshotParagraph)
            .where(BookSnapshotParagraph.snapshot_id == snapshot_id)
            .order_by(BookSnapshotParagraph.global_paragraph_index.asc())
        ).all()
    )
    assert paragraphs, "snapshot paragraphs required"
    for idx in range(20):
        para = paragraphs[idx % len(paragraphs)]
        session.add(
            WholeBookWindow(
                run_id=run_id,
                snapshot_id=snapshot_id,
                window_index=idx,
                first_global_paragraph_index=para.global_paragraph_index,
                last_global_paragraph_index=para.global_paragraph_index,
                chapter_start_index=0,
                chapter_end_index=0,
                paragraph_count=1,
                character_count=10,
                token_estimate=50,
                window_hash=sha256_utf8(f"win-{run_id}-{idx}"),
                idempotency_key=sha256_utf8(f"idem-{run_id}-{idx}"),
                status="pending",
            )
        )
    session.flush()


class PauseAfterSevenTransport:
    def __init__(self, session, run_id: int) -> None:
        self.session = session
        self.run_id = run_id
        self.inner = FixtureWindowAnalysisTransport()
        self.completed_invokes = 0
        self.pause_after = 7

    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]):
        result = self.inner.invoke(unit_key=unit_key, unit_type=unit_type, request_payload=request_payload)
        if result.ok:
            self.completed_invokes += 1
            if self.completed_invokes == self.pause_after:
                request_pause_whole_book_run_v1(self.session, self.run_id)
                self.session.flush()
        return result


def _prepare_windowed_run(session, *, window_count_target: int = 20):
    from app.db.models import Book, BookSnapshotParagraph, Chapter, Paragraph
    from app.services.whole_book_source_fingerprint import sha256_utf8

    book = Book(title="Pause Book", source_file_name="pause.txt", source_file_hash=sha256_utf8("pause"))
    session.add(book)
    session.flush()
    ch = Chapter(book_id=book.id, chapter_index=0, title="章")
    session.add(ch)
    session.flush()
    for idx in range(max(window_count_target, 25)):
        text = f"段落内容{idx}。" * 20
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
                content_hash=sha256_utf8(text),
            )
        )
    session.flush()
    from app.narrative_core.services.whole_book_snapshot_v1_service import create_or_reuse_book_snapshot_v1

    snap = create_or_reuse_book_snapshot_v1(session, book.id)["snapshot"]
    run = create_whole_book_run_v1(
        session,
        book.id,
        snap.id,
        "whole_book_native",
        str(uuid.uuid4()),
        "fixture",
    )
    run.consent_id = ensure_consent(session, book.id)
    generate_whole_book_windows_v1(session, run.id)
    from app.narrative_core.services.whole_book_windowing_v1_service import list_windows

    windows = list_windows(session, run.id)
    start_whole_book_run_v1(session, run.id)
    session.flush()
    return run.id, book.id, len(windows)


def test_pending_cannot_pause(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb18-pending.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snapshot_id = seed_sample_s_book(session)
        run = create_whole_book_run_v1(
            session, book.id, snapshot_id, "whole_book_native", str(uuid.uuid4()), "fixture"
        )
        with pytest.raises(WholeBookFoundationError) as exc:
            request_pause_whole_book_run_v1(session, run.id)
        assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION.value
    engine.dispose()


def test_pause_after_seven_resume_total_calls(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb18-pause-resume.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _book_id = prepare_sample_s_run(session)
        from app.narrative_core.services.whole_book_windowing_v1_service import list_windows

        window_count = len(list_windows(session, run_id))
        assert window_count >= 3
        start_whole_book_run_v1(session, run_id)
        pause_after = 1
        transport = PauseAfterSevenTransport(session, run_id)
        transport.pause_after = pause_after
        first = execute_minimal_entity_event_extraction_v1(session, run_id, transport=transport)
        session.commit()
        assert first["windows_completed"] == pause_after
        assert first.get("paused") is True
        run = get_run(session, run_id)
        assert run.status == "paused"
        assert run.pause_requested_at is not None

        resumed = resume_whole_book_run_v1(session, run_id)
        assert resumed.status == "pending"
        assert resumed.resume_count == 1

        start_whole_book_run_v1(session, run_id)
        second = execute_minimal_entity_event_extraction_v1(session, run_id)
        session.commit()
        assert second["windows_completed"] == window_count

        materialize_minimal_narrative_assets_v1(session, run_id)
        overview = synthesize_minimal_book_overview_v1(session, run_id)
        session.commit()

        attempts = session.query(WholeBookProviderAttempt).count()
        logical_calls = attempts
        assert logical_calls <= window_count + 1
        assert overview["provider_calls"] <= 1
    engine.dispose()


def test_cancel_blocks_resume(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb18-cancel.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _, _ = _prepare_windowed_run(session)
        request_cancel_whole_book_run_v1(session, run_id)
        session.commit()
        run = get_run(session, run_id)
        assert run.status == "cancelled"
        with pytest.raises(WholeBookFoundationError):
            resume_whole_book_run_v1(session, run_id)
    engine.dispose()


def test_progress_aggregator_shape(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb18-progress.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _, _ = _prepare_windowed_run(session)
        progress = aggregate_run_progress_v1(session, run_id)
        for key in (
            "run_id",
            "status",
            "overall_progress",
            "completed_windows",
            "total_windows",
            "provider_calls_used",
            "pause_requested",
            "can_pause",
            "can_resume",
            "can_cancel",
        ):
            assert key in progress
    engine.dispose()
