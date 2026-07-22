"""Scoped Reader Journey GET: book/chapter/run must match (CHG-20260722-003 UI follow-up)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import AnalysisRun, Book, Chapter, ReaderJourneyRun
from app.db.session import get_session_factory
from app.main import app


def _factory():
    override = app.dependency_overrides.get(get_session_factory)
    assert override is not None, "client fixture must override get_session_factory"
    return override()


def _seed_book_run_journey(session, *, book_title: str = "ScopeBook", with_journey: bool = True):
    book = Book(title=book_title, source_file_name="s.txt", source_file_hash="a" * 64)
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title="第一章",
        display_title="第一章",
        section_type="chapter",
    )
    session.add(chapter)
    session.flush()
    run = AnalysisRun(
        subject_type="chapter",
        subject_id=str(chapter.id),
        task_type="scene_pipeline",
        provider="fake",
        model="fake",
        status="succeeded",
        progress_current=1,
        progress_total=1,
        execution_mode="local",
        cloud_consent=False,
        sends_content_to_cloud=False,
        client_request_id=f"scope-test-run-{book_title}",
        prompt_version="v1",
        schema_version="v1",
        input_hash="i" * 64,
        prompt_hash="p" * 64,
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()
    journey = None
    if with_journey:
        journey = ReaderJourneyRun(
            analysis_run_id=run.id,
            book_id=book.id,
            chapter_id=chapter.id,
            status="succeeded",
            provider_name="fake",
            model_name="fake",
            total_scene_count=0,
            completed_scene_count=0,
            remaining_scene_count=0,
            completed_scene_ids_json="[]",
            remaining_scene_ids_json="[]",
            cloud_consent=False,
            client_request_id=f"scope-test-journey-{book_title}",
            failure_details_json="{}",
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        session.add(journey)
    session.commit()
    return book, chapter, run, journey


def test_get_reader_journey_requires_matching_book_chapter(client):
    factory = _factory()
    with factory() as session:
        book, chapter, run, journey = _seed_book_run_journey(session)
        run_id = run.id
        book_id = book.id
        chapter_id = chapter.id
        journey_id = journey.id
        status_before = run.status

    ok = client.get(
        f"/api/v1/analysis-runs/{run_id}/reader-journey",
        params={"book_id": book_id, "chapter_id": chapter_id},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["status"] == "succeeded"
    assert body["journey_run_id"] == journey_id

    wrong_book = client.get(
        f"/api/v1/analysis-runs/{run_id}/reader-journey",
        params={"book_id": book_id + 99, "chapter_id": chapter_id},
    )
    assert wrong_book.status_code == 409
    assert wrong_book.json()["error_code"] == "ANALYSIS_RUN_SCOPE_MISMATCH"

    wrong_chapter = client.get(
        f"/api/v1/analysis-runs/{run_id}/reader-journey",
        params={"book_id": book_id, "chapter_id": chapter_id + 99},
    )
    assert wrong_chapter.status_code == 409
    assert wrong_chapter.json()["error_code"] == "ANALYSIS_RUN_SCOPE_MISMATCH"

    with factory() as session:
        unchanged = session.get(AnalysisRun, run_id)
        assert unchanged is not None
        assert unchanged.status == status_before


def test_get_reader_journey_missing_returns_null_not_other_run(client):
    factory = _factory()
    with factory() as session:
        book, chapter, with_j_run, with_j = _seed_book_run_journey(session, book_title="HasJourney")
        orphan = AnalysisRun(
            subject_type="chapter",
            subject_id=str(chapter.id),
            task_type="scene_pipeline",
            provider="fake",
            model="fake",
            status="succeeded",
            progress_current=1,
            progress_total=1,
            execution_mode="local",
            cloud_consent=False,
            sends_content_to_cloud=False,
            client_request_id="orphan-run",
            prompt_version="v1",
            schema_version="v1",
            input_hash="o" * 64,
            prompt_hash="q" * 64,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        session.add(orphan)
        session.commit()
        orphan_id = orphan.id
        book_id = book.id
        chapter_id = chapter.id
        has_journey_run_id = with_j_run.id

    # Must not fall back to latest journey on another run.
    resp = client.get(
        f"/api/v1/analysis-runs/{orphan_id}/reader-journey",
        params={"book_id": book_id, "chapter_id": chapter_id},
    )
    assert resp.status_code == 200
    assert resp.json() is None

    other = client.get(
        f"/api/v1/analysis-runs/{has_journey_run_id}/reader-journey",
        params={"book_id": book_id, "chapter_id": chapter_id},
    )
    assert other.status_code == 200
    assert other.json()["journey_run_id"] == with_j.id
