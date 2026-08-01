"""CHG-015: recoverable journey must stay the current run; no parallel auto-journey."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.models import (
    AnalysisRun,
    Book,
    BoundaryRevision,
    Chapter,
    Paragraph,
    ReaderJourneyRun,
    Scene,
)
from app.services import chapter_analysis_completion as cac
from app.services.reader_journey_progress import find_recoverable_journey_run
from app.services.reader_journey_recovery import JOURNEY_INTERRUPTED


def _book_chapter(session):
    book = Book(title="CHG-015 recoverable", source_file_name="t.txt", source_file_hash="h")
    session.add(book)
    session.flush()
    chapter = Chapter(book_id=book.id, chapter_index=1, title="C1", section_type="chapter")
    session.add(chapter)
    session.flush()
    for i in range(1, 4):
        text = f"para {i}"
        session.add(
            Paragraph(
                id=f"P{i:04d}",
                book_id=book.id,
                chapter_id=chapter.id,
                paragraph_index=i,
                raw_text=text,
                normalized_text=text,
                char_start=(i - 1) * 10,
                char_end=i * 10,
                content_hash=f"h{i}",
            )
        )
    session.flush()
    return book, chapter


def _run(session, chapter: Chapter) -> AnalysisRun:
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="aliyun_qwen_plus",
        model="qwen-plus",
        prompt_version="v1",
        schema_version="v1",
        input_hash="inp",
        prompt_hash="",
        status="succeeded",
        progress_current=0,
        progress_total=0,
        execution_mode="cloud",
        analysis_mode="automatic",
        cloud_consent=True,
        sends_content_to_cloud=True,
    )
    session.add(run)
    session.flush()
    return run


def _interrupted_journey(session, run: AnalysisRun, book: Book, chapter: Chapter, *, rev_id: int | None):
    journey = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="scene_profiles_partial",
        current_stage="reader_journey_scene_profiles",
        provider_name=run.provider,
        model_name=run.model,
        scene_prompt_version="v2.0",
        chapter_prompt_version="v2.0",
        scene_contract_version="2.0",
        chapter_contract_version="2.0",
        formula_version="1.0",
        genre="suspense",
        planner_version="1.1",
        total_scene_count=3,
        completed_scene_count=1,
        remaining_scene_count=2,
        completed_scene_ids_json="[1]",
        remaining_scene_ids_json="[2,3]",
        cloud_consent=True,
        retryable=True,
        root_error_code=JOURNEY_INTERRUPTED,
        client_request_id=f"recoverable-{run.id}",
        scene_revision_id=rev_id,
        result_status="current",
        failure_details_json=json.dumps(
            {"interrupt": {"code": JOURNEY_INTERRUPTED, "had_worker_claim": True}},
            ensure_ascii=False,
        ),
    )
    session.add(journey)
    session.flush()
    return journey


def test_find_recoverable_accepts_contract_major_2(testing_session):
    book, chapter = _book_chapter(testing_session)
    run = _run(testing_session, chapter)
    interrupted = _interrupted_journey(testing_session, run, book, chapter, rev_id=None)
    found = find_recoverable_journey_run(testing_session, run.id)
    assert found is not None
    assert found.id == interrupted.id


def test_ensure_auto_reuses_recoverable_for_revision_bind(testing_session, monkeypatch):
    book, chapter = _book_chapter(testing_session)
    run = _run(testing_session, chapter)
    revision = BoundaryRevision(
        chapter_id=chapter.id,
        analysis_run_id=run.id,
        revision_number=1,
        status="confirmed",
        source="manual",
        final_boundaries_json="[]",
        confirmed_by="test",
        confirmed_at=datetime.now(timezone.utc),
        coverage_rate=1.0,
        boundary_hash="bh",
        chapter_text_hash="cth",
    )
    testing_session.add(revision)
    testing_session.flush()
    interrupted = _interrupted_journey(
        testing_session, run, book, chapter, rev_id=revision.id
    )

    progress = type(
        "P",
        (),
        {
            "total_scene_count": 3,
            "completed_scene_count": 3,
            "remaining_scene_count": 0,
            "completed_scene_ids": [1, 2, 3],
            "pending_scene_ids": [],
            "failed_scene_ids": [],
            "boundary_revision_id": revision.id,
            "coverage_rate": 1.0,
        },
    )()
    monkeypatch.setattr(cac, "scene_analysis_progress", lambda *_a, **_k: progress)
    monkeypatch.setattr(
        "app.services.scene_boundary_manual_review.revision_scenes",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "app.services.scene_boundary_manual_review.bind_journey_to_revision",
        lambda *_a, **_k: None,
    )

    again = cac.ensure_auto_reader_journey_row(
        testing_session, run, scene_revision_id=revision.id
    )
    assert again is not None
    assert again.id == interrupted.id
    rows = list(
        testing_session.scalars(
            select(ReaderJourneyRun).where(ReaderJourneyRun.analysis_run_id == run.id)
        )
    )
    assert len(rows) == 1


def test_latest_journey_prefers_recoverable_over_noncurrent_succeeded(testing_session):
    book, chapter = _book_chapter(testing_session)
    run = _run(testing_session, chapter)
    interrupted = _interrupted_journey(testing_session, run, book, chapter, rev_id=None)
    interrupted.result_status = "superseded"
    succeeded = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="succeeded",
        current_stage="succeeded",
        provider_name=run.provider,
        model_name=run.model,
        scene_prompt_version="v2.0",
        chapter_prompt_version="v2.0",
        scene_contract_version="2.0",
        chapter_contract_version="2.0",
        formula_version="1.0",
        genre="suspense",
        planner_version="1.1",
        total_scene_count=3,
        completed_scene_count=3,
        remaining_scene_count=0,
        completed_scene_ids_json="[1,2,3]",
        remaining_scene_ids_json="[]",
        cloud_consent=True,
        client_request_id=f"auto-chapter-journey:{run.id}:rev:1",
        result_status="legacy_revision_unresolved",
        failure_details_json="{}",
    )
    testing_session.add(succeeded)
    testing_session.flush()

    latest = cac.latest_journey(testing_session, run.id)
    assert latest is not None
    assert latest.id == interrupted.id
    assert cac.is_chapter_analysis_complete(testing_session, run) is False


def test_latest_journey_prefers_current_succeeded(testing_session):
    book, chapter = _book_chapter(testing_session)
    run = _run(testing_session, chapter)
    interrupted = _interrupted_journey(testing_session, run, book, chapter, rev_id=None)
    interrupted.result_status = "superseded"
    succeeded = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="succeeded",
        current_stage="succeeded",
        provider_name=run.provider,
        model_name=run.model,
        scene_prompt_version="v2.0",
        chapter_prompt_version="v2.0",
        scene_contract_version="2.0",
        chapter_contract_version="2.0",
        formula_version="1.0",
        genre="suspense",
        planner_version="1.1",
        total_scene_count=3,
        completed_scene_count=3,
        remaining_scene_count=0,
        completed_scene_ids_json="[1,2,3]",
        remaining_scene_ids_json="[]",
        cloud_consent=True,
        client_request_id=f"auto-chapter-journey:{run.id}:rev:1",
        result_status="current",
        failure_details_json="{}",
    )
    testing_session.add(succeeded)
    testing_session.flush()

    latest = cac.latest_journey(testing_session, run.id)
    assert latest is not None
    assert latest.id == succeeded.id
    # Scene artifacts are not seeded here; only assert journey selection.
    assert latest.status == "succeeded"
    assert latest.result_status == "current"
