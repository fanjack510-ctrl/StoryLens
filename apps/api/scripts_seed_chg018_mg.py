"""Seed isolated MG DB for CHG-20260730-018 with Active + Interrupted fixtures."""

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
    or Path(os.environ["TEMP"]) / "storylens-mg-chg018"
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
# Clear settings cache if any.
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
        progress_current=1,
        progress_total=1,
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
    return book, chapter, run, revision


def main() -> None:
    assert get_settings().database_url.endswith("storylens-mg-chg018/storylens.db".replace("\\", "/")) or "storylens-mg-chg018" in get_settings().database_url

    create_db()
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        _enable_cloud(session)
        _set_budget(session)

        book_a, chapter_a, run_a, rev_a = _seed_confirmed(
            session,
            book_title="CHG018 Active Journey",
            source_hash="a" * 64,
            book_code="B0A18",
            input_hash="1" * 64,
        )
        journey_a = ReaderJourneyRun(
            analysis_run_id=run_a.id,
            book_id=book_a.id,
            chapter_id=chapter_a.id,
            status="running",
            current_stage="running",
            provider_name=run_a.provider,
            model_name=run_a.model,
            formula_version="v1",
            scene_contract_version="2.0",
            client_request_id="chg018-mg-active",
            cloud_consent=True,
            scene_revision_id=rev_a.id,
            scene_revision_no=rev_a.revision_number,
        )
        session.add(journey_a)
        session.flush()
        # Do NOT claim worker before API start — startup reconcile marks orphaned
        # claims as interrupted (JOURNEY_INTERRUPTED). Active MG fixture stays running.

        book_c, chapter_c, run_c, rev_c = _seed_confirmed(
            session,
            book_title="CHG018 Interrupted Journey",
            source_hash="b" * 64,
            book_code="B0C18",
            input_hash="2" * 64,
        )
        journey_c = ReaderJourneyRun(
            analysis_run_id=run_c.id,
            book_id=book_c.id,
            chapter_id=chapter_c.id,
            status="interrupted",
            current_stage="interrupted",
            provider_name=run_c.provider,
            model_name=run_c.model,
            formula_version="v1",
            scene_contract_version="2.0",
            client_request_id="chg018-mg-interrupted",
            cloud_consent=True,
            retryable=True,
            root_error_code="JOURNEY_INTERRUPTED",
            scene_revision_id=rev_c.id,
            scene_revision_no=rev_c.revision_number,
            completed_scene_count=1,
            total_scene_count=3,
            remaining_scene_count=2,
        )
        session.add(journey_c)
        session.commit()

        fe = "http://127.0.0.1:1420"
        api = "http://127.0.0.1:18080"
        fixtures = {
            "database": str(db_path),
            "api_url": api,
            "frontend_url": fe,
            "active": {
                "book_id": book_a.id,
                "chapter_id": chapter_a.id,
                "analysis_run_id": run_a.id,
                "journey_run_id": journey_a.id,
                "confirmed_revision_id": rev_a.id,
                "url": (
                    f"{fe}/books/{book_a.id}?chapter={chapter_a.id}"
                    f"&analysisRun={run_a.id}&view=progress&journeyRun={journey_a.id}"
                ),
            },
            "interrupted": {
                "book_id": book_c.id,
                "chapter_id": chapter_c.id,
                "analysis_run_id": run_c.id,
                "journey_run_id": journey_c.id,
                "confirmed_revision_id": rev_c.id,
                "url": (
                    f"{fe}/books/{book_c.id}?chapter={chapter_c.id}"
                    f"&analysisRun={run_c.id}&view=progress&journeyRun={journey_c.id}"
                ),
            },
            "real_provider_calls": 0,
            "formal_db_writes": 0,
        }

    out = (
        REPO_ROOT
        / "release/evidence/hotfix/1.1.2/CHG-20260730-018/MANUAL_FIXTURES.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(fixtures, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
