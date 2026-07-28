"""WB-1.4 — minimal window extraction tests."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models import WholeBookProviderAttempt, WholeBookWindowAnalysisResult
from app.narrative_core.contracts.whole_book_contract_v1 import (
    CandidateEntityV1,
    EntityType,
    WholeBookWindowAnalysisResponseV1,
)
from app.narrative_core.services.fixture_window_analysis_sample_s import (
    build_fixture_window_analysis_response_v1,
)
from app.narrative_core.services.whole_book_minimal_extraction_v1_service import (
    execute_minimal_entity_event_extraction_v1,
)
from app.narrative_core.services.whole_book_provider_orchestrator import CountingFakeWholeBookProvider
from app.narrative_core.services.whole_book_window_response_validation_v1 import (
    validate_window_response_against_snapshot_v1,
)
from app.narrative_core.services.whole_book_minimal_extraction_v1_service import _build_window_request
from app.narrative_core.services.whole_book_run_v1_service import get_run
from tests.whole_book_minimal_test_helpers import make_engine, prepare_sample_s_run


def test_valid_fixture_response_accepted(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb14-valid.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _book_id = prepare_sample_s_run(session)
        result = execute_minimal_entity_event_extraction_v1(session, run_id)
        session.commit()
        assert result["windows_failed"] == 0
        assert result["valid_results"] == 3
        rows = session.query(WholeBookWindowAnalysisResult).filter_by(run_id=run_id).all()
        assert len(rows) == 3
        assert all(r.validation_status == "valid" for r in rows)
    engine.dispose()


def test_invalid_response_not_partially_persisted(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb14-invalid.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        run = get_run(session, run_id)
        from app.db.models import BookSnapshot, WholeBookWindow

        snapshot = session.get(BookSnapshot, run.snapshot_id)
        window = session.query(WholeBookWindow).filter_by(run_id=run_id, window_index=0).one()
        request = _build_window_request(session, run, snapshot, window)
        response = build_fixture_window_analysis_response_v1(request)
        bad = response.model_copy(update={"run_id": run_id + 999})
        validation = validate_window_response_against_snapshot_v1(
            session, run, snapshot, window, request.paragraphs, bad
        )
        assert validation.valid is False
        assert any("run_id mismatch" in err for err in validation.errors)
    engine.dispose()


def test_extraction_idempotent_provider_calls(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb14-idem.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        first = execute_minimal_entity_event_extraction_v1(session, run_id)
        session.commit()
        assert first["provider_calls"] == 3
        second = execute_minimal_entity_event_extraction_v1(session, run_id)
        session.commit()
        assert second["provider_calls"] == 0
        attempts = session.query(WholeBookProviderAttempt).count()
        assert attempts == 3
    engine.dispose()


def test_migration_014_tables_exist(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb14-mig.db")
    from sqlalchemy import inspect

    names = set(inspect(engine).get_table_names())
    assert "whole_book_window_analysis_results" in names
    assert "whole_book_overview_results" in names
    engine.dispose()
