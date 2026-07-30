"""Seed isolated MG DB for CHG-20260730-017 (Fixtures A/B/C)."""

from __future__ import annotations

import asyncio
import hashlib
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
    or Path(os.environ["TEMP"]) / "storylens-mg-chg017"
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

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db.models import (  # noqa: E402
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    Book,
    Chapter,
    ChapterReaderJourneySummary,
    Paragraph,
    ReaderJourneyPhase,
    ReaderJourneyRun,
    Scene,
    SceneReaderJourneyProfile,
)
from app.db.session import create_db, get_session_factory  # noqa: E402
from app.services.chapter_analysis_completion import (  # noqa: E402
    mark_scenes_complete_awaiting_boundary_confirmation,
)
from app.services.scene_boundary_manual_review import (  # noqa: E402
    confirm_scene_revision_and_start_journey_v1,
    create_or_get_scene_boundary_draft_v1,
    save_scene_boundary_draft_v1,
)
from tests.test_phase_1c_c1 import _enable_cloud  # noqa: E402
from tests.test_unified_analysis_recovery_center import _set_budget  # noqa: E402


def _seed_book(
    session,
    *,
    title: str,
    source_hash: str,
    book_code: str,
    input_hash: str,
    paragraph_count: int,
    scene_count: int,
    run_status: str = "succeeded",
):
    book = Book(
        title=title,
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
    paragraphs: list[Paragraph] = []
    for index in range(1, paragraph_count + 1):
        body = f"第{index}段：雨打青瓦，巷口灯影摇晃，案情线索逐渐浮现。"
        row = Paragraph(
            id=f"{book_code}-C0001-P{index:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=index,
            raw_text=body,
            normalized_text=body,
            char_start=index * 10,
            char_end=index * 10 + len(body),
        )
        session.add(row)
        paragraphs.append(row)
    session.flush()
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="fake",
        model="fake-scene-model",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash=input_hash,
        status=run_status,
        execution_mode="local",
        cloud_consent=True,
        cloud_consent_at=datetime.now(timezone.utc),
        sends_content_to_cloud=False,
        status_version=1,
        book_id=book.id,
        start_chapter_id=chapter.id,
        end_chapter_id=chapter.id,
        progress_current=0,
        progress_total=scene_count,
    )
    session.add(run)
    session.flush()
    per_scene = paragraph_count // scene_count
    scenes: list[Scene] = []
    start_idx = 0
    for ordinal in range(1, scene_count + 1):
        end_idx = (
            start_idx + per_scene - 1 if ordinal < scene_count else paragraph_count - 1
        )
        start_p = paragraphs[start_idx]
        end_p = paragraphs[end_idx]
        content = "\n".join(
            p.normalized_text for p in paragraphs[start_idx : end_idx + 1]
        )
        scene = Scene(
            scene_key=f"{book_code}-C0001-S{ordinal:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            ordinal=ordinal,
            start_paragraph_id=start_p.id,
            end_paragraph_id=end_p.id,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            created_by_run_id=run.id,
            boundary_detected=True,
            boundary_confidence=0.9,
            boundary_reason_json="[]",
            included_in_journey=True,
        )
        session.add(scene)
        scenes.append(scene)
        start_idx = end_idx + 1
    session.flush()
    return book, chapter, paragraphs, run, scenes


def _attach_scene_analysis(session, run: AnalysisRun, scenes: list[Scene]) -> None:
    for scene in scenes:
        artifact = AnalysisArtifact(
            run_id=run.id,
            artifact_type="scene_analysis",
            subject_type="scene",
            subject_id=str(scene.id),
            schema_version="v1",
            prompt_version="v1",
            payload_json='{"scene_id": "x"}',
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
    session.flush()


def _shrink_draft(session, draft, paragraphs, scene_count: int):
    span = max(1, len(paragraphs) // scene_count)
    partition = []
    for i in range(scene_count):
        start = paragraphs[i * span]
        end = paragraphs[min((i + 1) * span - 1, len(paragraphs) - 1)]
        partition.append(
            {
                "scene_order": i + 1,
                "start_paragraph_id": start.id,
                "end_paragraph_id": end.id,
                "included_in_journey": True,
            }
        )
    return save_scene_boundary_draft_v1(
        session, draft.id, partition, expected_etag=draft.revision_etag
    )


async def _seed_fixture_a(session):
    """Scene analysis running; journey waiting; hide journey nav."""
    book, chapter, paragraphs, run, scenes = _seed_book(
        session,
        title="CHG017 Fixture A Scene Analysis",
        source_hash="a" * 64,
        book_code="B0A17",
        input_hash="1" * 64,
        paragraph_count=12,
        scene_count=2,
    )
    _attach_scene_analysis(session, run, scenes)
    draft = create_or_get_scene_boundary_draft_v1(session, chapter.id)
    session.commit()
    session.refresh(draft)
    draft = _shrink_draft(session, draft, paragraphs, scene_count=3)
    session.commit()
    session.refresh(draft)
    revision, journey, _, _ = await confirm_scene_revision_and_start_journey_v1(
        session,
        draft.id,
        expected_etag=draft.revision_etag,
        start_journey=True,
    )
    session.commit()
    session.refresh(run)
    if journey is not None:
        session.refresh(journey)
    return {
        "book_id": book.id,
        "chapter_id": chapter.id,
        "analysis_run_id": run.id,
        "journey_run_id": journey.id if journey else None,
        "revision_id": revision.id if revision else None,
        "run_status": run.status,
        "journey_status": journey.status if journey else None,
        "journey_error": journey.root_error_code if journey else None,
    }


async def _seed_fixture_b(session):
    """Awaiting scene confirmation; hide journey nav; deep link → confirm."""
    book, chapter, paragraphs, run, scenes = _seed_book(
        session,
        title="CHG017 Fixture B Awaiting Confirm",
        source_hash="b" * 64,
        book_code="B0B17",
        input_hash="2" * 64,
        paragraph_count=12,
        scene_count=3,
    )
    _attach_scene_analysis(session, run, scenes)
    mark_scenes_complete_awaiting_boundary_confirmation(session, run)
    draft = create_or_get_scene_boundary_draft_v1(session, chapter.id)
    session.commit()
    session.refresh(draft)
    draft = _shrink_draft(session, draft, paragraphs, scene_count=3)
    session.commit()
    session.refresh(run)
    return {
        "book_id": book.id,
        "chapter_id": chapter.id,
        "analysis_run_id": run.id,
        "journey_run_id": None,
        "draft_revision_id": draft.id,
        "run_status": run.status,
        "effective_hint": "awaiting_scene_boundary_confirmation",
    }


async def _seed_fixture_c(session):
    """Scenes complete; journey starting/running; show journey nav."""
    book, chapter, paragraphs, run, scenes = _seed_book(
        session,
        title="CHG017 Fixture C Journey Running",
        source_hash="c" * 64,
        book_code="B0C17",
        input_hash="3" * 64,
        paragraph_count=12,
        scene_count=3,
    )
    _attach_scene_analysis(session, run, scenes)
    draft = create_or_get_scene_boundary_draft_v1(session, chapter.id)
    session.commit()
    session.refresh(draft)
    draft = _shrink_draft(session, draft, paragraphs, scene_count=3)
    session.commit()
    session.refresh(draft)
    revision, journey, _, _ = await confirm_scene_revision_and_start_journey_v1(
        session,
        draft.id,
        expected_etag=draft.revision_etag,
        start_journey=True,
    )
    session.commit()
    session.refresh(run)
    if journey is not None:
        # Prefer durable starting (unclaimed) so API boot requeues rather than
        # treating running as orphaned claim.
        if journey.root_error_code == "WAITING_SCENE_ANALYSIS":
            journey.root_error_code = None
            journey.root_error_message = None
        journey.status = "starting"
        journey.current_stage = "starting"
        session.commit()
        session.refresh(journey)
    return {
        "book_id": book.id,
        "chapter_id": chapter.id,
        "analysis_run_id": run.id,
        "journey_run_id": journey.id if journey else None,
        "revision_id": revision.id if revision else None,
        "run_status": run.status,
        "journey_status": journey.status if journey else None,
        "journey_error": journey.root_error_code if journey else None,
    }


async def _seed_fixture_d(session):
    """Scenes complete; journey succeeded with result rows (Fixture D)."""
    book, chapter, paragraphs, run, scenes = _seed_book(
        session,
        title="CHG017 Fixture D Journey Succeeded",
        source_hash="d" * 64,
        book_code="B0D17",
        input_hash="4" * 64,
        paragraph_count=12,
        scene_count=3,
    )
    _attach_scene_analysis(session, run, scenes)
    draft = create_or_get_scene_boundary_draft_v1(session, chapter.id)
    session.commit()
    session.refresh(draft)
    draft = _shrink_draft(session, draft, paragraphs, scene_count=3)
    session.commit()
    session.refresh(draft)
    revision, journey, _, _ = await confirm_scene_revision_and_start_journey_v1(
        session,
        draft.id,
        expected_etag=draft.revision_etag,
        start_journey=True,
    )
    session.commit()
    session.refresh(run)
    assert journey is not None
    if journey.root_error_code == "WAITING_SCENE_ANALYSIS":
        journey.root_error_code = None
        journey.root_error_message = None

    from app.services.scene_boundary_manual_review import revision_scenes

    rev_scenes = revision_scenes(session, revision.id)
    included_ids = [int(s.id) for s in rev_scenes]
    journey.status = "succeeded"
    journey.current_stage = "succeeded"
    journey.result_status = "current"
    journey.completed_scene_count = len(rev_scenes)
    journey.total_scene_count = len(rev_scenes)
    journey.remaining_scene_count = 0
    journey.included_scene_ids_json = json.dumps(included_ids)
    journey.completed_scene_ids_json = json.dumps(included_ids)
    journey.completed_at = datetime.now(timezone.utc)
    session.flush()

    for ordinal, scene in enumerate(rev_scenes, start=1):
        profile_payload = {
            "scene_id": scene.id,
            "scene_ordinal": ordinal,
            "scene_value_summary": f"Fixture D scene {ordinal}",
            "dominant_emotion": "好奇",
            "curiosity_score": 70,
            "tension_score": 55,
            "payoff_score": 60,
            "hook_score": 65,
            "information_gain_score": 50,
            "emotional_resonance_score": 48,
            "cognitive_load_score": 40,
            "dropoff_risk_score": 30,
            "confidence": 0.9,
        }
        session.add(
            SceneReaderJourneyProfile(
                reader_journey_run_id=journey.id,
                scene_id=scene.id,
                scene_ordinal=ordinal,
                scene_value_summary=profile_payload["scene_value_summary"],
                dominant_emotion="好奇",
                curiosity_score=70,
                tension_score=55,
                payoff_score=60,
                hook_score=65,
                information_gain_score=50,
                emotional_resonance_score=48,
                cognitive_load_score=40,
                dropoff_risk_score=30,
                engagement_score=68,
                confidence=0.9,
                payload_json=json.dumps(profile_payload, ensure_ascii=False),
                validation_status="valid",
            )
        )
    session.add(
        ReaderJourneyPhase(
            reader_journey_run_id=journey.id,
            ordinal=1,
            title="开篇牵引",
            start_scene_ordinal=1,
            end_scene_ordinal=max(1, len(rev_scenes)),
            primary_reader_question="接下来会发生什么",
            dominant_emotion="好奇",
            reading_payoff="建立期待",
            continuation_motivation="继续阅读",
            summary="Fixture D phase",
            confidence=0.9,
            payload_json="{}",
        )
    )
    session.add(
        ChapterReaderJourneySummary(
            reader_journey_run_id=journey.id,
            chapter_value_summary="Fixture D 阅读旅程已生成",
            chapter_reader_question_chain_json='["接下来会发生什么"]',
            overall_engagement_score=70,
            one_sentence_diagnosis="Fixture D 旅程结果可用于 CTA 验收。",
            pacing_diagnosis_json='["节奏正常"]',
            deterministic_statistics_json="{}",
            payload_json="{}",
            validation_status="valid",
        )
    )
    session.commit()
    session.refresh(journey)
    return {
        "book_id": book.id,
        "chapter_id": chapter.id,
        "analysis_run_id": run.id,
        "journey_run_id": journey.id,
        "revision_id": revision.id if revision else None,
        "run_status": run.status,
        "journey_status": journey.status,
        "journey_error": journey.root_error_code,
        "has_result": True,
    }


def _url(fe: str, book_id: int, chapter_id: int, run_id: int, **extra: object) -> str:
    q = [f"chapter={chapter_id}", f"analysisRun={run_id}"]
    for k, v in extra.items():
        if v is None:
            continue
        q.append(f"{k}={v}")
    return f"{fe}/books/{book_id}?{'&'.join(q)}"


async def _amain() -> dict:
    assert "storylens-mg-chg017" in get_settings().database_url
    create_db()
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        _enable_cloud(session)
        _set_budget(session)
        fixture_a = await _seed_fixture_a(session)
        fixture_b = await _seed_fixture_b(session)
        fixture_c = await _seed_fixture_c(session)
        fixture_d = await _seed_fixture_d(session)
        session.commit()

    fe = "http://127.0.0.1:1420"
    api = "http://127.0.0.1:18080"
    fixtures = {
        "database": str(db_path),
        "api_url": api,
        "frontend_url": fe,
        "provider": "fake",
        "real_provider_calls": 0,
        "formal_db_writes": 0,
        "a_scene_analysis_running": {
            **fixture_a,
            "url": _url(
                fe,
                fixture_a["book_id"],
                fixture_a["chapter_id"],
                fixture_a["analysis_run_id"],
                view="progress",
            ),
            "journey_deep_link": _url(
                fe,
                fixture_a["book_id"],
                fixture_a["chapter_id"],
                fixture_a["analysis_run_id"],
                view="result",
                tab="reader-journey",
                journeyRun=fixture_a.get("journey_run_id"),
            ),
        },
        "b_awaiting_confirmation": {
            **fixture_b,
            "url": _url(
                fe,
                fixture_b["book_id"],
                fixture_b["chapter_id"],
                fixture_b["analysis_run_id"],
                view="scene-boundary-review",
            ),
            "journey_deep_link": _url(
                fe,
                fixture_b["book_id"],
                fixture_b["chapter_id"],
                fixture_b["analysis_run_id"],
                view="result",
                tab="reader-journey",
            ),
        },
        "c_journey_running": {
            **fixture_c,
            "url": _url(
                fe,
                fixture_c["book_id"],
                fixture_c["chapter_id"],
                fixture_c["analysis_run_id"],
                view="progress",
                journeyRun=fixture_c.get("journey_run_id"),
            ),
        },
        "d_journey_succeeded": {
            **fixture_d,
            "progress_url": _url(
                fe,
                fixture_d["book_id"],
                fixture_d["chapter_id"],
                fixture_d["analysis_run_id"],
                view="progress",
                journeyRun=fixture_d.get("journey_run_id"),
            ),
            "result_url": _url(
                fe,
                fixture_d["book_id"],
                fixture_d["chapter_id"],
                fixture_d["analysis_run_id"],
                view="result",
                tab="reader-journey",
                journeyRun=fixture_d.get("journey_run_id"),
            ),
        },
    }
    out = (
        REPO_ROOT
        / "release/evidence/hotfix/1.1.2/CHG-20260730-017/MANUAL_FIXTURES.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(fixtures, ensure_ascii=False, indent=2))
    return fixtures


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
