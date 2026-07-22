"""Local unit tests: chapter pipeline completion (scenes → journey → finalize)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models import AnalysisRun, Book, Chapter, ReaderJourneyRun
from app.services import chapter_analysis_completion as cac


def _run(**kwargs) -> AnalysisRun:
    defaults = dict(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id="1",
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="v1",
        input_hash="a" * 64,
        status="succeeded",
        execution_mode="local",
        cloud_consent=False,
        sends_content_to_cloud=False,
    )
    defaults.update(kwargs)
    return AnalysisRun(**defaults)


def test_mark_scenes_complete_clears_completed_at(testing_session):
    book = Book(title="t", source_file_name="t.txt", source_file_hash="b" * 64)
    testing_session.add(book)
    testing_session.flush()
    chapter = Chapter(book_id=book.id, chapter_index=1, title="一", section_type="chapter")
    testing_session.add(chapter)
    testing_session.flush()
    run = _run(subject_id=str(chapter.id), completed_at=cac._now())
    testing_session.add(run)
    testing_session.flush()

    cac.mark_scenes_complete_awaiting_journey(testing_session, run)
    assert run.status == "succeeded"
    assert run.completed_at is None
    marker = json.loads(run.raw_output or "{}")
    assert marker["checkpoint_stage"] == "reader_journey_generation"
    assert marker["chapter_pipeline"] == "awaiting_reader_journey"


def test_effective_status_partial_when_scenes_done_without_journey(testing_session):
    book = Book(title="t", source_file_name="t.txt", source_file_hash="b" * 64)
    testing_session.add(book)
    testing_session.flush()
    chapter = Chapter(book_id=book.id, chapter_index=1, title="一", section_type="chapter")
    testing_session.add(chapter)
    testing_session.flush()
    run = _run(subject_id=str(chapter.id))
    testing_session.add(run)
    testing_session.flush()

    progress = SimpleNamespace(
        total_scene_count=2,
        completed_scene_count=2,
        remaining_scene_count=0,
        completed_scene_ids=[1, 2],
        pending_scene_ids=[],
        failed_scene_ids=[],
        boundary_revision_id=1,
        coverage_rate=1.0,
    )
    with patch.object(cac, "scene_analysis_progress", return_value=progress):
        assert cac.is_scene_pipeline_complete(testing_session, run) is True
        assert cac.is_chapter_analysis_complete(testing_session, run) is False
        assert cac.effective_chapter_status(testing_session, run) == "partial_complete"
        assert cac.checkpoint_stage(testing_session, run) == "reader_journey_generation"
        payload = cac.chapter_completion_payload(testing_session, run)
        assert payload["chapter_complete"] is False
        assert payload["resume_stage"] == "reader_journey_generation"


def test_finalize_only_when_journey_succeeded(testing_session):
    book = Book(title="t", source_file_name="t.txt", source_file_hash="b" * 64)
    testing_session.add(book)
    testing_session.flush()
    chapter = Chapter(book_id=book.id, chapter_index=1, title="一", section_type="chapter")
    testing_session.add(chapter)
    testing_session.flush()
    run = _run(subject_id=str(chapter.id), completed_at=None)
    testing_session.add(run)
    testing_session.flush()
    journey = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="succeeded",
        provider_name="fake",
        model_name="fake",
        scene_prompt_version="v1",
        chapter_prompt_version="v1",
        scene_contract_version="1.0",
        chapter_contract_version="1.0",
        planner_version="1",
        formula_version="1.0",
        genre="general",
        total_scene_count=2,
        completed_scene_count=2,
        remaining_scene_count=0,
        completed_scene_ids_json="[1,2]",
        remaining_scene_ids_json="[]",
        cloud_consent=False,
        client_request_id=cac.auto_journey_client_request_id(run.id),
        failure_details_json="{}",
    )
    testing_session.add(journey)
    testing_session.flush()

    progress = SimpleNamespace(
        total_scene_count=2,
        completed_scene_count=2,
        remaining_scene_count=0,
        completed_scene_ids=[1, 2],
        pending_scene_ids=[],
        failed_scene_ids=[],
        boundary_revision_id=1,
        coverage_rate=1.0,
    )
    with patch.object(cac, "scene_analysis_progress", return_value=progress):
        assert cac.is_chapter_analysis_complete(testing_session, run) is True
        cac.finalize_chapter_analysis(testing_session, run)
        assert run.completed_at is not None
        assert cac.effective_chapter_status(testing_session, run) == "completed"


@pytest.mark.asyncio
async def test_continue_chapter_reuses_same_run_and_skips_duplicate_active(testing_session):
    book = Book(title="t", source_file_name="t.txt", source_file_hash="b" * 64)
    testing_session.add(book)
    testing_session.flush()
    chapter = Chapter(book_id=book.id, chapter_index=1, title="一", section_type="chapter")
    testing_session.add(chapter)
    testing_session.flush()
    run = _run(subject_id=str(chapter.id))
    testing_session.add(run)
    testing_session.flush()
    journey = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="scene_profiles_running",
        provider_name="fake",
        model_name="fake",
        scene_prompt_version="v1",
        chapter_prompt_version="v1",
        scene_contract_version="1.0",
        chapter_contract_version="1.0",
        planner_version="1",
        formula_version="1.0",
        genre="general",
        total_scene_count=2,
        completed_scene_count=0,
        remaining_scene_count=2,
        completed_scene_ids_json="[]",
        remaining_scene_ids_json="[1,2]",
        cloud_consent=False,
        client_request_id=cac.auto_journey_client_request_id(run.id),
        failure_details_json="{}",
    )
    testing_session.add(journey)
    testing_session.commit()
    run_id = run.id

    factory = MagicMock()
    factory.return_value.__enter__ = MagicMock(return_value=testing_session)
    factory.return_value.__exit__ = MagicMock(return_value=False)

    progress = SimpleNamespace(
        total_scene_count=2,
        completed_scene_count=2,
        remaining_scene_count=0,
        completed_scene_ids=[1, 2],
        pending_scene_ids=[],
        failed_scene_ids=[],
        boundary_revision_id=1,
        coverage_rate=1.0,
    )
    execute = AsyncMock()
    with (
        patch.object(cac, "scene_analysis_progress", return_value=progress),
        patch(
            "app.services.reader_journey_pipeline.execute_reader_journey",
            execute,
        ),
    ):
        # session_factory needs to yield the same session for get
        class _CM:
            def __enter__(self_inner):
                return testing_session

            def __exit__(self_inner, *args):
                return False

        session_factory = MagicMock(side_effect=lambda: _CM())
        await cac.continue_chapter_after_scenes(session_factory, MagicMock(), run_id)
        execute.assert_not_called()
        testing_session.refresh(run)
        assert run.completed_at is None


def test_ensure_auto_journey_idempotent_client_key(testing_session):
    book = Book(title="t", source_file_name="t.txt", source_file_hash="b" * 64)
    testing_session.add(book)
    testing_session.flush()
    chapter = Chapter(book_id=book.id, chapter_index=1, title="一", section_type="chapter")
    testing_session.add(chapter)
    testing_session.flush()
    run = _run(subject_id=str(chapter.id))
    testing_session.add(run)
    testing_session.flush()
    existing = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="queued",
        provider_name="fake",
        model_name="fake",
        scene_prompt_version="v1",
        chapter_prompt_version="v1",
        scene_contract_version="1.0",
        chapter_contract_version="1.0",
        planner_version="1",
        formula_version="1.0",
        genre="general",
        total_scene_count=1,
        completed_scene_count=0,
        remaining_scene_count=1,
        completed_scene_ids_json="[]",
        remaining_scene_ids_json="[1]",
        cloud_consent=False,
        client_request_id=cac.auto_journey_client_request_id(run.id),
        failure_details_json="{}",
    )
    testing_session.add(existing)
    testing_session.flush()

    progress = SimpleNamespace(
        total_scene_count=1,
        completed_scene_count=1,
        remaining_scene_count=0,
        completed_scene_ids=[1],
        pending_scene_ids=[],
        failed_scene_ids=[],
        boundary_revision_id=1,
        coverage_rate=1.0,
    )
    with patch.object(cac, "scene_analysis_progress", return_value=progress):
        again = cac.ensure_auto_reader_journey_row(testing_session, run)
        assert again is not None
        assert again.id == existing.id
