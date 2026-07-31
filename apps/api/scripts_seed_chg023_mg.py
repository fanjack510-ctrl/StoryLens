"""Seed isolated MG DB for CHG-20260731-023 retest.

Fixture A (resume success): interrupted + checkpoint + can_resume; Fake Worker succeeds.
Fixture B (resume failure): interrupted + checkpoint; launcher injects deterministic fail.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent
REPO_ROOT = API_ROOT.parents[1]
sys.path.insert(0, str(API_ROOT))

mg_root = Path(
    os.environ.get("STORYLENS_MG_ROOT")
    or Path(os.environ["TEMP"]) / "storylens-mg-chg023"
)
mg_root.mkdir(parents=True, exist_ok=True)
db_path = mg_root / "storylens.db"
if db_path.exists():
    db_path.unlink()
for suffix in ("-wal", "-shm"):
    side = Path(str(db_path) + suffix)
    if side.exists():
        side.unlink()

os.environ["STORYLENS_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
os.environ.setdefault("STORYLENS_PROVIDER", "fake")
os.environ.setdefault("STORYLENS_ALLOW_FAKE_PROVIDER", "1")
os.environ.pop("STORYLENS_SETTINGS_CACHE", None)

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db.models import (  # noqa: E402
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    Book,
    BoundaryReviewSession,
    BoundaryRevision,
    Chapter,
    Paragraph,
    ReaderJourneyRun,
    Scene,
    SceneReaderJourneyProfile,
)
from app.db.session import create_db, get_session_factory  # noqa: E402
from tests.test_phase_1c_a10 import _enable_cloud, _scene_payload  # noqa: E402
from tests.test_unified_analysis_recovery_center import _set_budget  # noqa: E402


def _seed_confirmed(
    session,
    *,
    book_title: str,
    source_hash: str,
    book_code: str,
    input_hash: str,
    scene_count: int = 3,
):
    book = Book(
        title=book_title,
        source_file_name=f"{book_code}.txt",
        source_file_hash=source_hash,
    )
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
    paragraphs = []
    for index in range(1, scene_count * 2 + 1):
        row = Paragraph(
            id=f"{book_code}-C0001-P{index:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=index,
            raw_text=f"段落正文{index}" * 4,
            normalized_text=f"段落正文{index}" * 4,
            char_start=index * 10,
            char_end=index * 10 + 8,
        )
        session.add(row)
        paragraphs.append(row)
    run = AnalysisRun(
        task_type="scene_pipeline",
        provider="fake",
        model="fake-scene-model",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash=input_hash,
        status="succeeded",
        subject_type="chapter",
        subject_id=str(chapter.id),
        prompt_hash="c" * 64,
        progress_current=scene_count,
        progress_total=scene_count,
        analysis_mode="assisted_boundary_review",
        execution_mode="local",
        cloud_consent=True,
        cloud_consent_at=datetime.now(timezone.utc),
        sends_content_to_cloud=False,
        status_version=1,
        book_id=book.id,
        start_chapter_id=chapter.id,
        end_chapter_id=chapter.id,
    )
    session.add(run)
    session.flush()
    review = BoundaryReviewSession(
        book_id=book.id,
        chapter_id=chapter.id,
        analysis_run_id=run.id,
        prompt_version="v3.5",
        provider="fake",
        model="fake-scene-model",
        status="confirmed",
        candidate_count=0,
        accepted_count=0,
        rejected_count=0,
        manually_added_count=scene_count - 1,
        confirmed_by="tester",
        completed_at=datetime.now(timezone.utc),
    )
    session.add(review)
    session.flush()
    revision = BoundaryRevision(
        review_session_id=review.id,
        chapter_id=chapter.id,
        analysis_run_id=run.id,
        revision_number=1,
        final_boundaries_json=json.dumps(
            [
                {
                    "after_paragraph_id": paragraphs[index * 2 - 1].id,
                    "source": "user_added",
                }
                for index in range(1, scene_count)
            ],
            ensure_ascii=False,
        ),
        confirmed_by="tester",
        confirmed_at=datetime.now(timezone.utc),
        coverage_rate=1.0,
    )
    session.add(revision)
    session.flush()
    scenes = []
    for index in range(scene_count):
        start = paragraphs[index * 2]
        end = paragraphs[-1] if index == scene_count - 1 else paragraphs[index * 2 + 1]
        scene = Scene(
            scene_key=f"{book_code}-C0001-R0001-S{index + 1:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            ordinal=index + 1,
            start_paragraph_id=start.id,
            end_paragraph_id=end.id,
            content_hash="d" * 64,
            created_by_run_id=run.id,
            boundary_confidence=0.9,
            boundary_detected=True,
            boundary_revision_id=revision.id,
            boundary_source="user_added" if index < scene_count - 1 else None,
        )
        session.add(scene)
        scenes.append(scene)
    session.flush()
    for scene in scenes:
        art = AnalysisArtifact(
            run_id=run.id,
            artifact_type="scene_analysis",
            subject_type="scene",
            subject_id=str(scene.id),
            schema_version="v1",
            prompt_version="v1",
            payload_json=_scene_payload(scene, paragraphs),
            confidence=0.9,
            validation_status="valid",
        )
        session.add(art)
        session.flush()
        session.add(
            AnalysisEvidence(
                artifact_id=art.id,
                field_path="goal.evidence",
                paragraph_id=scene.start_paragraph_id,
                paragraph_hash="e" * 64,
            )
        )
    session.flush()
    return book, chapter, run, revision, scenes


def _checkpoint_profile(session, journey: ReaderJourneyRun, scene: Scene) -> None:
    payload = {
        "scene_id": scene.id,
        "scene_ordinal": scene.ordinal,
        "scene_value_summary": f"场景{scene.ordinal}检查点",
        "dominant_emotion": "紧张",
        "curiosity_score": 60,
        "tension_score": 55,
        "payoff_score": 40,
        "hook_score": 50,
        "information_gain_score": 45,
        "emotional_resonance_score": 40,
        "cognitive_load_score": 30,
        "dropoff_risk_score": 20,
        "confidence": 0.9,
        "evidence_paragraph_ids": [scene.start_paragraph_id],
    }
    session.add(
        SceneReaderJourneyProfile(
            reader_journey_run_id=journey.id,
            scene_id=scene.id,
            scene_ordinal=scene.ordinal,
            scene_value_summary=payload["scene_value_summary"],
            dominant_emotion="紧张",
            curiosity_score=60,
            tension_score=55,
            payoff_score=40,
            hook_score=50,
            information_gain_score=45,
            emotional_resonance_score=40,
            cognitive_load_score=30,
            dropoff_risk_score=20,
            engagement_score=58,
            confidence=0.9,
            payload_json=json.dumps(payload, ensure_ascii=False),
            validation_status="valid",
        )
    )


def _seed_interrupted(
    session,
    *,
    book_title: str,
    source_hash: str,
    book_code: str,
    input_hash: str,
    client_request_id: str,
):
    book, chapter, run, rev, scenes = _seed_confirmed(
        session,
        book_title=book_title,
        source_hash=source_hash,
        book_code=book_code,
        input_hash=input_hash,
    )
    done = scenes[:1]
    remain = scenes[1:]
    journey = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="scene_profiles_partial",
        current_stage="reader_journey_scene_profiles",
        provider_name=run.provider,
        model_name=run.model,
        formula_version="v1",
        scene_contract_version="2.0",
        client_request_id=client_request_id,
        cloud_consent=True,
        scene_revision_id=rev.id,
        scene_revision_no=rev.revision_number,
        retryable=True,
        root_error_code="JOURNEY_INTERRUPTED",
        root_error_message="fixture recoverable interrupt",
        completed_scene_count=len(done),
        total_scene_count=len(scenes),
        remaining_scene_count=len(remain),
        completed_scene_ids_json=json.dumps([s.id for s in done]),
        remaining_scene_ids_json=json.dumps([s.id for s in remain]),
        started_at=datetime.now(timezone.utc),
    )
    session.add(journey)
    session.flush()
    _checkpoint_profile(session, journey, done[0])
    return book, chapter, run, rev, journey


def main() -> None:
    assert "storylens-mg-chg023" in get_settings().database_url
    create_db()
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        _enable_cloud(session)
        _set_budget(session)

        book_a, chapter_a, run_a, rev_a, journey_a = _seed_interrupted(
            session,
            book_title="CHG023 Resume Success",
            source_hash="a" * 64,
            book_code="B0S23",
            input_hash="1" * 64,
            client_request_id="chg023-mg-success",
        )
        book_b, chapter_b, run_b, rev_b, journey_b = _seed_interrupted(
            session,
            book_title="CHG023 Resume Failure",
            source_hash="b" * 64,
            book_code="B0F23",
            input_hash="2" * 64,
            client_request_id="chg023-mg-fail",
        )
        session.commit()

        api = os.environ.get("STORYLENS_MG_API_URL", "http://127.0.0.1:18057")
        fe = os.environ.get("STORYLENS_MG_FE_URL", "http://127.0.0.1:1436")
        fixtures = {
            "database": str(db_path),
            "api_url": api,
            "frontend_url": fe,
            "resume_success": {
                "book_id": book_a.id,
                "chapter_id": chapter_a.id,
                "analysis_run_id": run_a.id,
                "journey_run_id": journey_a.id,
                "confirmed_revision_id": rev_a.id,
                "client_request_id": "chg023-mg-success",
                "url": (
                    f"{fe}/books/{book_a.id}?chapter={chapter_a.id}"
                    f"&analysisRun={run_a.id}&journeyRun={journey_a.id}"
                    f"&view=progress&tab=reader-journey"
                ),
            },
            "resume_failure": {
                "book_id": book_b.id,
                "chapter_id": chapter_b.id,
                "analysis_run_id": run_b.id,
                "journey_run_id": journey_b.id,
                "confirmed_revision_id": rev_b.id,
                "client_request_id": "chg023-mg-fail",
                "url": (
                    f"{fe}/books/{book_b.id}?chapter={chapter_b.id}"
                    f"&analysisRun={run_b.id}&journeyRun={journey_b.id}"
                    f"&view=progress&tab=reader-journey"
                ),
            },
            "real_provider_calls": 0,
            "formal_db_writes": 0,
        }

    out = (
        REPO_ROOT
        / "release/evidence/hotfix/1.1.2/CHG-20260731-023/MANUAL_FIXTURES.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(fixtures, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
