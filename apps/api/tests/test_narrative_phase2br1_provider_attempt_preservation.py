"""CHG-058 — provider_attempts append-only across pipeline checkpoint writes."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AnalysisRun, Base, Book, Chapter
from app.narrative_core.enums import AnalysisScopeType, AnalysisType, StageStatus
from app.narrative_core.migrations.runner import apply_narrative_phase1p_migrations
from app.narrative_core.services.run_scope_service import StubSnapshotValidationGateway
from app.narrative_core.services.run_stage_repository import merge_checkpoint_namespaces
from app.narrative_core.services.run_stage_service import RunStageService


@pytest.fixture()
def stage_env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'attempt.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    book = Book(
        title="Attempt Book",
        source_file_name="attempt.txt",
        source_file_hash="a" * 64,
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=0,
        title="Ch1",
        chapter_title="Ch1",
        display_title="Ch1",
        source_title_line="第1章",
    )
    session.add(chapter)
    session.commit()
    service = RunStageService(
        session, snapshot_gateway=StubSnapshotValidationGateway(session)
    )
    run = service.create_scoped_run(
        scope_type=AnalysisScopeType.CHAPTER,
        analysis_type=AnalysisType.SCENE_PIPELINE,
        chapter_id=chapter.id,
        book_id=book.id,
    )
    yield {"session": session, "service": service, "run": run}
    session.close()
    engine.dispose()


def test_merge_checkpoint_namespaces_appends_provider_attempts() -> None:
    existing = {
        "schema": "narrative_run_stage_checkpoint",
        "version": "1",
        "provider_attempts": [{"attempt_index": 0, "provider_request_id": "a"}],
        "pipeline_diagnostics": {"claim_count": 1},
    }
    incoming = {
        "schema": "narrative_run_stage_checkpoint",
        "version": "1",
        "checkpoint_kind": "pipeline_diagnostics",
        "pipeline_diagnostics": {"evidence_valid_count": 2},
        "persistence_summary": {"orm_written": True},
    }
    merged = merge_checkpoint_namespaces(existing, incoming)
    assert len(merged["provider_attempts"]) == 1
    assert merged["provider_attempts"][0]["provider_request_id"] == "a"
    assert merged["pipeline_diagnostics"]["claim_count"] == 1
    assert merged["pipeline_diagnostics"]["evidence_valid_count"] == 2
    assert merged["persistence_summary"]["orm_written"] is True
    assert merged["checkpoint_kind"] == "pipeline_diagnostics"

    merged2 = merge_checkpoint_namespaces(
        merged,
        {"schema": "narrative_run_stage_checkpoint", "version": "1"},
        append_provider_attempt={
            "attempt_index": 1,
            "attempt_kind": "repair",
            "provider_request_id": "b",
        },
    )
    assert [a["provider_request_id"] for a in merged2["provider_attempts"]] == ["a", "b"]


def test_write_checkpoint_preserves_provider_attempts(stage_env) -> None:
    service: RunStageService = stage_env["service"]
    run: AnalysisRun = stage_env["run"]
    service.initialize_run_stages(run.id, ["analyze_structure"])
    service.transition_stage(run.id, "analyze_structure", StageStatus.RUNNING)

    service.write_checkpoint(
        run.id,
        "analyze_structure",
        {
            "schema": "narrative_run_stage_checkpoint",
            "version": "1",
            "stage_key": "analyze_structure",
            "checkpoint_kind": "provider_attempt",
            "provider_attempted": True,
        },
        append_provider_attempt={
            "attempt_index": 0,
            "attempt_kind": "initial",
            "provider_request_id": "req-1",
            "transport_kind": "FAKE_HTTP_TEST",
            "http_status": 200,
            "input_tokens": 10,
            "output_tokens": 20,
        },
    )
    service.write_checkpoint(
        run.id,
        "analyze_structure",
        {
            "schema": "narrative_run_stage_checkpoint",
            "version": "1",
            "stage_key": "analyze_structure",
            "checkpoint_kind": "pipeline_diagnostics",
            "pipeline_diagnostics": {
                "failure_boundary": None,
                "claim_count": 6,
            },
            "persistence_summary": {"persistence_complete": True},
        },
    )

    stage = service.get_run_stages(run.id)[0]
    payload = json.loads(stage.checkpoint_json)
    assert payload["checkpoint_kind"] == "pipeline_diagnostics"
    attempts = payload.get("provider_attempts") or []
    assert len(attempts) == 1
    assert attempts[0]["provider_request_id"] == "req-1"
    assert attempts[0]["input_tokens"] == 10
    assert payload["pipeline_diagnostics"]["claim_count"] == 6
    assert payload["persistence_summary"]["persistence_complete"] is True
