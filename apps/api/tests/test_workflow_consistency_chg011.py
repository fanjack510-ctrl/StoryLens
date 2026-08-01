"""CHG-20260729-011: confirmed-revision scene binding for results and listings."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    BoundaryReviewSession,
    BoundaryRevision,
    Book,
    Chapter,
    Paragraph,
    ReaderJourneyRun,
    Scene,
)
from app.services.scene_analysis_progress import scene_analysis_progress
from app.services.scene_results_service import build_run_results


def _paragraph_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _scene_content_hash(start: Paragraph, end: Paragraph, paragraphs: list[Paragraph]) -> str:
    start_i = next(i for i, p in enumerate(paragraphs) if p.id == start.id)
    end_i = next(i for i, p in enumerate(paragraphs) if p.id == end.id)
    content = "\n".join(p.normalized_text for p in paragraphs[start_i : end_i + 1])
    return hashlib.sha256(content.encode()).hexdigest()


def _attach_scene_analysis(session, run: AnalysisRun, scenes: list[Scene]) -> None:
    for scene in scenes:
        artifact = AnalysisArtifact(
            run_id=run.id,
            artifact_type="scene_analysis",
            subject_type="scene",
            subject_id=str(scene.id),
            schema_version="v1",
            prompt_version="v1",
            payload_json=json.dumps({"scene_id": scene.scene_key}, ensure_ascii=False),
            confidence=0.9,
            validation_status="valid",
        )
        session.add(artifact)
        session.flush()
        session.add(
            AnalysisEvidence(
                artifact_id=artifact.id,
                field_path="summary",
                paragraph_id=scene.start_paragraph_id,
                paragraph_hash="c" * 64,
            )
        )


def _add_scenes(
    session,
    *,
    book: Book,
    chapter: Chapter,
    paragraphs: list[Paragraph],
    run: AnalysisRun,
    revision: BoundaryRevision,
    scene_count: int,
    scene_key_prefix: str,
) -> list[Scene]:
    per_scene = max(1, len(paragraphs) // scene_count)
    scenes: list[Scene] = []
    start_idx = 0
    for ordinal in range(1, scene_count + 1):
        end_idx = start_idx + per_scene - 1 if ordinal < scene_count else len(paragraphs) - 1
        start_p = paragraphs[start_idx]
        end_p = paragraphs[end_idx]
        scene = Scene(
            scene_key=f"{scene_key_prefix}-S{ordinal:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            ordinal=ordinal,
            start_paragraph_id=start_p.id,
            end_paragraph_id=end_p.id,
            content_hash=_scene_content_hash(start_p, end_p, paragraphs),
            created_by_run_id=run.id,
            boundary_detected=True,
            boundary_confidence=0.9,
            boundary_reason_json="[]",
            boundary_revision_id=revision.id,
            included_in_journey=True,
        )
        session.add(scene)
        scenes.append(scene)
        start_idx = end_idx + 1
    session.flush()
    return scenes


def _seed_revision_binding_fixture(session):
    """One chapter, superseded 22-scene run A, confirmed 6-scene run B (+16 stale on B)."""
    book = Book(
        title="CHG-011 修订绑定验收",
        source_file_name="chg011-fixture.txt",
        source_file_hash="a" * 64,
    )
    session.add(book)
    session.flush()

    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title="第一章 修订绑定",
        section_type="chapter",
    )
    session.add(chapter)
    session.flush()

    paragraph_count = 24
    paragraphs: list[Paragraph] = []
    for index in range(1, paragraph_count + 1):
        body = f"第{index}段：修订绑定探针，场景边界与结果列表应只暴露确认修订。"
        paragraph = Paragraph(
            id=f"B0001-C0001-P{index:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=index,
            raw_text=body,
            normalized_text=body,
            char_start=index * 10,
            char_end=index * 10 + len(body),
        )
        session.add(paragraph)
        paragraphs.append(paragraph)
    session.flush()

    now = datetime.now(timezone.utc)

    run_a = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="fake",
        model="fake",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash="b" * 64,
        status="succeeded",
        execution_mode="local",
        cloud_consent=False,
        sends_content_to_cloud=False,
        completed_at=now,
    )
    session.add(run_a)
    session.flush()

    review_a = BoundaryReviewSession(
        book_id=book.id,
        chapter_id=chapter.id,
        analysis_run_id=run_a.id,
        prompt_version="v3.5",
        provider="fake",
        model="fake",
        status="confirmed",
        confirmed_by="test",
        completed_at=now,
    )
    session.add(review_a)
    session.flush()

    revision_a = BoundaryRevision(
        review_session_id=review_a.id,
        chapter_id=chapter.id,
        analysis_run_id=run_a.id,
        revision_number=1,
        final_boundaries_json="[]",
        confirmed_by="test",
        confirmed_at=now,
        coverage_rate=1.0,
        status="superseded",
        source="model",
        superseded_at=now,
    )
    session.add(revision_a)
    session.flush()

    scenes_a = _add_scenes(
        session,
        book=book,
        chapter=chapter,
        paragraphs=paragraphs,
        run=run_a,
        revision=revision_a,
        scene_count=22,
        scene_key_prefix="B0001-C0001-R0001",
    )
    _attach_scene_analysis(session, run_a, scenes_a)

    run_b = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="fake",
        model="fake",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash="c" * 64,
        status="succeeded",
        execution_mode="local",
        cloud_consent=False,
        sends_content_to_cloud=False,
        completed_at=now,
    )
    session.add(run_b)
    session.flush()

    review_b = BoundaryReviewSession(
        book_id=book.id,
        chapter_id=chapter.id,
        analysis_run_id=run_b.id,
        prompt_version="v3.5",
        provider="fake",
        model="fake",
        status="confirmed",
        confirmed_by="test",
        completed_at=now,
    )
    session.add(review_b)
    session.flush()

    revision_b_stale = BoundaryRevision(
        review_session_id=review_b.id,
        chapter_id=chapter.id,
        analysis_run_id=run_b.id,
        revision_number=2,
        final_boundaries_json="[]",
        confirmed_by="test",
        confirmed_at=now,
        coverage_rate=1.0,
        status="superseded",
        source="user",
        based_on_revision_id=revision_a.id,
        superseded_at=now,
    )
    session.add(revision_b_stale)
    session.flush()

    scenes_b_stale = _add_scenes(
        session,
        book=book,
        chapter=chapter,
        paragraphs=paragraphs,
        run=run_b,
        revision=revision_b_stale,
        scene_count=16,
        scene_key_prefix="B0001-C0001-R0002",
    )

    revision_b = BoundaryRevision(
        review_session_id=review_b.id,
        chapter_id=chapter.id,
        analysis_run_id=run_b.id,
        revision_number=3,
        final_boundaries_json="[]",
        confirmed_by="test",
        confirmed_at=now,
        coverage_rate=1.0,
        status="confirmed",
        source="user",
        based_on_revision_id=revision_b_stale.id,
    )
    session.add(revision_b)
    session.flush()

    scenes_b = _add_scenes(
        session,
        book=book,
        chapter=chapter,
        paragraphs=paragraphs,
        run=run_b,
        revision=revision_b,
        scene_count=6,
        scene_key_prefix="B0001-C0001-R0003",
    )
    _attach_scene_analysis(session, run_b, scenes_b)

    confirmed_ids = [scene.id for scene in scenes_b]
    journey = ReaderJourneyRun(
        analysis_run_id=run_b.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="succeeded",
        provider_name="fake",
        model_name="fake",
        total_scene_count=6,
        completed_scene_count=6,
        remaining_scene_count=0,
        completed_scene_ids_json=json.dumps(confirmed_ids),
        remaining_scene_ids_json="[]",
        cloud_consent=False,
        client_request_id="chg011-journey",
        failure_details_json="{}",
        scene_revision_id=revision_b.id,
        scene_revision_no=revision_b.revision_number,
        included_scene_ids_json=json.dumps(confirmed_ids),
        started_at=now,
        completed_at=now,
    )
    session.add(journey)
    session.commit()

    assert len(scenes_a) == 22
    assert len(scenes_b_stale) == 16
    assert len(scenes_b) == 6
    assert len(scenes_a) + len(scenes_b_stale) + len(scenes_b) == 44

    return {
        "book": book,
        "chapter": chapter,
        "run_a": run_a,
        "run_b": run_b,
        "revision_b": revision_b,
        "scenes_a": scenes_a,
        "scenes_b": scenes_b,
        "journey": journey,
    }


def _seed_ids(session_factory):
    with session_factory() as session:
        data = _seed_revision_binding_fixture(session)
        return {
            "chapter_id": data["chapter"].id,
            "run_a_id": data["run_a"].id,
            "run_b_id": data["run_b"].id,
        }


def test_run_b_scenes_endpoint_returns_confirmed_six_only(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    ids = _seed_ids(factory)

    resp = client.get(f"/api/v1/analysis-runs/{ids['run_b_id']}/scenes")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 6
    ordinals = [item["ordinal"] for item in body]
    assert ordinals == list(range(1, 7))


def test_chapter_scenes_endpoint_uses_current_run_revision(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    ids = _seed_ids(factory)

    resp = client.get(f"/api/v1/chapters/{ids['chapter_id']}/scenes")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 6
    assert [item["ordinal"] for item in body] == list(range(1, 7))


def test_build_run_results_binds_confirmed_revision_scenes(testing_session):
    data = _seed_revision_binding_fixture(testing_session)
    bundle = build_run_results(testing_session, data["run_b"])
    assert len(bundle.scenes) == 6
    assert bundle.boundary_revision is not None
    assert bundle.boundary_revision.id == data["revision_b"].id
    assert [item.scene.ordinal for item in bundle.scenes] == list(range(1, 7))


def test_run_a_historical_scenes_preserved(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    ids = _seed_ids(factory)

    resp = client.get(f"/api/v1/analysis-runs/{ids['run_a_id']}/scenes")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 22
    assert [item["ordinal"] for item in body] == list(range(1, 23))


def test_run_b_no_duplicate_ordinals(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    ids = _seed_ids(factory)

    body = client.get(f"/api/v1/analysis-runs/{ids['run_b_id']}/scenes").json()
    ordinals = [item["ordinal"] for item in body]
    assert len(ordinals) == len(set(ordinals)) == 6


def test_run_b_scene_progress_total_is_six(testing_session):
    data = _seed_revision_binding_fixture(testing_session)
    progress = scene_analysis_progress(testing_session, data["run_b"])
    assert progress.total_scene_count == 6
    assert progress.boundary_revision_id == data["revision_b"].id
    assert progress.completed_scene_count == 6
    assert progress.remaining_scene_count == 0
