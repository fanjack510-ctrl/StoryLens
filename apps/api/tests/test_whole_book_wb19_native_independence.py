"""WB-1.9 — native input independence tests."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models import AnalysisArtifact, AnalysisRun, ReaderJourneyRun
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_minimal_extraction_v1_service import (
    execute_minimal_entity_event_extraction_v1,
)
from app.narrative_core.services.whole_book_native_input_audit_v1 import (
    assert_native_input_independence_v1,
    compute_native_input_audit_v1,
    native_book_has_contamination_sources,
    persist_native_input_audit_v1,
)
from app.narrative_core.services.whole_book_run_v1_service import create_whole_book_run_v1
from tests.whole_book_minimal_test_helpers import ensure_consent, make_engine, prepare_sample_s_run, seed_sample_s_book


def test_native_audit_pass_without_chapter_analysis(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb19-clean.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, book_id = prepare_sample_s_run(session)
        audit = assert_native_input_independence_v1(session, run_id)
        assert audit.is_clean()
        row = persist_native_input_audit_v1(session, audit)
        assert row.audit_status == "pass"
    engine.dispose()


def test_chapter_analysis_present_but_not_loaded(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb19-chapter.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, book_id = prepare_sample_s_run(session)
        ar = AnalysisRun(
            task_type="scene_pipeline",
            subject_type="chapter",
            subject_id="1",
            provider="fixture",
            model="fixture",
            prompt_version="v1",
            schema_version="v1",
            input_hash="a" * 64,
            analysis_type="scene",
            book_id=book_id,
        )
        session.add(ar)
        session.flush()
        session.add(
            AnalysisArtifact(
                run_id=ar.id,
                artifact_type="scene_card",
                subject_type="chapter",
                subject_id="1",
                schema_version="v1",
                prompt_version="v1",
                payload_json="{}",
                confidence=0.9,
            )
        )
        session.flush()
        sources = native_book_has_contamination_sources(session, book_id)
        assert sources["chapter_analysis_asset_count"] >= 1
        audit = assert_native_input_independence_v1(session, run_id)
        assert audit.chapter_analysis_asset_count == 0
    engine.dispose()


def test_reader_journey_present_but_not_loaded(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb19-rj.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snapshot_id = seed_sample_s_book(session)
        run = create_whole_book_run_v1(
            session, book.id, snapshot_id, "whole_book_native", str(uuid.uuid4()), "fixture"
        )
        run.consent_id = ensure_consent(session, book.id)
        ar = AnalysisRun(
            task_type="reader_journey",
            subject_type="book",
            subject_id=str(book.id),
            provider="fixture",
            model="fixture",
            prompt_version="v1",
            schema_version="v1",
            input_hash="b" * 64,
            book_id=book.id,
        )
        session.add(ar)
        session.flush()
        from app.db.models import Chapter

        ch = session.query(Chapter).filter_by(book_id=book.id).first()
        session.add(
            ReaderJourneyRun(
                analysis_run_id=ar.id,
                book_id=book.id,
                chapter_id=ch.id,
                provider_name="fixture",
                model_name="fixture",
                client_request_id=str(uuid.uuid4()),
            )
        )
        session.flush()
        audit = assert_native_input_independence_v1(session, run.id)
        assert audit.reader_journey_asset_count == 0
    engine.dispose()


def test_contamination_blocks_execution(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb19-block.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        with pytest.raises(WholeBookFoundationError) as exc:
            assert_native_input_independence_v1(
                session,
                run_id,
                loaded_usage={"chapter_analysis_asset_count": 1, "full_text_snapshot_used": True},
            )
        assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_NATIVE_INPUT_CONTAMINATED.value
    engine.dispose()


def test_extraction_runs_audit_gate(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb19-extract.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        execute_minimal_entity_event_extraction_v1(session, run_id)
        session.commit()
        audit = compute_native_input_audit_v1(session, run_id)
        assert audit.is_clean()
    engine.dispose()
