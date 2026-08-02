"""WB-1.6 — overview + full fixture pipeline tests."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import WholeBookOverviewResult, WholeBookProviderAttempt, WholeBookRunStageRow
from app.narrative_core.contracts.whole_book_contract_v1.constants import BOOK_OVERVIEW_CLAIM_KEYS_V1
from app.narrative_core.services.whole_book_fixture_pipeline_v1_service import (
    execute_fixture_minimal_pipeline_v1,
)
from app.narrative_core.services.whole_book_minimal_read_v1_service import count_provider_calls
from app.narrative_core.services.whole_book_run_v1_service import get_run
from tests.whole_book_minimal_test_helpers import make_engine, prepare_sample_s_run


def test_full_pipeline_completed(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb16-pipeline.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        first = execute_fixture_minimal_pipeline_v1(session, run_id)
        session.commit()
        run = get_run(session, run_id)
        assert run.status == "completed"
        assert run.current_stage_code == "finalize"
        assert first["extraction"]["provider_calls"] == 3
        assert first["overview"]["claims"] == 9
        assert first["structure"]["stage_count"] >= 1
        stages = list(
            session.scalars(select(WholeBookRunStageRow).where(WholeBookRunStageRow.run_id == run_id)).all()
        )
        completed = [s for s in stages if s.status == "completed"]
        assert len(completed) == 8
        assert any(s.stage_code == "synthesize_structure_stages" and s.status == "completed" for s in stages)
        overview = session.scalar(
            select(WholeBookOverviewResult).where(WholeBookOverviewResult.run_id == run_id)
        )
        assert overview is not None
        assert count_provider_calls(session, run_id) == 5
    engine.dispose()


def test_pipeline_rerun_zero_new_calls(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb16-rerun.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        execute_fixture_minimal_pipeline_v1(session, run_id)
        session.commit()
        calls_after_first = count_provider_calls(session, run_id)
        execute_fixture_minimal_pipeline_v1(session, run_id)
        session.commit()
        calls_after_second = count_provider_calls(session, run_id)
        assert calls_after_first == 5
        assert calls_after_second == 5
        attempts = session.query(WholeBookProviderAttempt).count()
        assert attempts == 5
    engine.dispose()


def test_overview_nine_claims(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb16-claims.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        execute_fixture_minimal_pipeline_v1(session, run_id)
        session.commit()
        import json

        row = session.scalar(
            select(WholeBookOverviewResult).where(WholeBookOverviewResult.run_id == run_id)
        )
        data = json.loads(row.result_json)
        keys = [c["claim_key"] for c in data["claims"]]
        assert keys == list(BOOK_OVERVIEW_CLAIM_KEYS_V1)
    engine.dispose()
