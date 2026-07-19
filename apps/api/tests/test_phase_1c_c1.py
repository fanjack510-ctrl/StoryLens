"""Phase 1C-C.1 Reader Journey Engine tests — Fake Provider only."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    ApplicationSetting,
    BoundaryRevision,
    BoundaryReviewSession,
    Book,
    Chapter,
    ChapterReaderJourneySummary,
    Paragraph,
    ReaderJourneyPhase,
    ReaderJourneyRun,
    Scene,
    SceneReaderJourneyProfile,
)
from app.model_gateway.gateway import ModelGateway
from app.schemas.reader_journey import SceneReaderJourneyProfileItem
from app.schemas.settings import CloudBudgetUpdate
from app.services.reader_journey_batch_planner import plan_scene_batches
from app.services.reader_journey_engagement import compute_engagement, load_formula_config
from app.services.reader_journey_pipeline import execute_reader_journey
from app.services.reader_journey_validation import (
    validate_chapter_synthesis,
    validate_score_distribution,
)
from app.schemas.reader_journey import ChapterReaderJourneySynthesisResult
from app.services.validation_errors import StructuralValidationError
from tests.fakes import FakeProvider


def _enable_cloud(session):
    session.merge(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True)))
    payload = CloudBudgetUpdate().model_dump()
    payload.update(
        {
            "cloud_daily_request_limit": 500,
            "cloud_daily_token_limit": 2_000_000,
            "cloud_daily_estimated_cost_limit": 50.0,
            "cloud_max_requests_per_run": 200,
        }
    )
    session.merge(
        ApplicationSetting(key="cloud_budget_settings", value_json=json.dumps(payload))
    )
    session.commit()


def _seed_run55_like(session, *, scene_count: int = 14):
    book = Book(title="Run55", source_file_name="r55.txt", source_file_hash="r" * 64)
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=2,
        title="第1章 戏鬼回家",
        display_title="第1章 戏鬼回家",
        section_type="chapter",
    )
    session.add(chapter)
    session.flush()
    paragraphs = []
    for index in range(1, 69):
        row = Paragraph(
            id=f"B0001-C0002-P{index:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=index,
            raw_text=f"段落{index}" * 3,
            normalized_text=f"段落{index}" * 3,
            char_start=index * 10,
            char_end=index * 10 + 5,
        )
        session.add(row)
        paragraphs.append(row)
    run = AnalysisRun(
        task_type="scene_pipeline",
        provider="fake",
        model="fake-scene-model",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash="s" * 64,
        status="succeeded",
        subject_type="chapter",
        subject_id=str(chapter.id),
        prompt_hash="t" * 64,
        progress_current=scene_count,
        progress_total=scene_count,
        analysis_mode="assisted_boundary_review",
        execution_mode="local",
        cloud_consent=True,
        cloud_consent_at=datetime.now(timezone.utc),
        sends_content_to_cloud=False,
        completed_at=datetime.now(timezone.utc),
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
        final_boundaries_json="[]",
        confirmed_by="tester",
        confirmed_at=datetime.now(timezone.utc),
        coverage_rate=1.0,
    )
    session.add(revision)
    session.flush()
    # Scene ranges mimicking Run #55 ordinals
    ranges = [
        (1, 12),
        (13, 14),
        (15, 15),
        (16, 17),
        (18, 18),
        (19, 19),
        (20, 28),
        (29, 32),
        (33, 48),
        (49, 56),
        (57, 59),
        (60, 62),
        (63, 63),
        (64, 68),
    ]
    sources = [
        "user_added",
        "model_accepted",
        "user_added",
        "user_accepted_model_conflict",
        "user_added",
        "model_accepted",
        "model_accepted",
        "user_accepted_model_conflict",
        "model_accepted",
        "model_accepted",
        "model_accepted",
        "model_accepted",
        "user_accepted_model_conflict",
        None,
    ]
    scenes = []
    for ordinal, ((start_idx, end_idx), source) in enumerate(zip(ranges, sources), 1):
        start = paragraphs[start_idx - 1]
        end = paragraphs[end_idx - 1]
        scene = Scene(
            scene_key=f"B0001-C0002-R0001-S{ordinal:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            ordinal=ordinal,
            start_paragraph_id=start.id,
            end_paragraph_id=end.id,
            content_hash="u" * 64,
            created_by_run_id=run.id,
            boundary_confidence=0.9,
            boundary_detected=True,
            boundary_revision_id=revision.id,
            boundary_source=source,
        )
        session.add(scene)
        scenes.append(scene)
    session.flush()
    for scene in scenes:
        payload = {
            "scene_id": scene.scene_key,
            "entry_state": {"summary": f"进入-{scene.ordinal}", "evidence_paragraph_ids": [scene.start_paragraph_id]},
            "goal": {"summary": f"目标-{scene.ordinal}", "evidence_paragraph_ids": [scene.start_paragraph_id]},
            "obstacle": {"summary": "", "evidence_paragraph_ids": []},
            "key_actions": [{"summary": f"行动-{scene.ordinal}", "evidence_paragraph_ids": [scene.start_paragraph_id]}],
            "turning_point": {"summary": "", "evidence_paragraph_ids": []},
            "outcome": {"summary": f"结果-{scene.ordinal}", "evidence_paragraph_ids": [scene.end_paragraph_id]},
            "unresolved_question": {"summary": "", "evidence_paragraph_ids": []},
            "function_tags": ["事件推进"],
            "confidence": 0.8,
        }
        artifact = AnalysisArtifact(
            run_id=run.id,
            artifact_type="scene_analysis",
            subject_type="scene",
            subject_id=str(scene.id),
            schema_version="v1",
            prompt_version="v3.1",
            payload_json=json.dumps(payload, ensure_ascii=False),
            confidence=0.8,
            validation_status="valid",
        )
        session.add(artifact)
        session.flush()
        session.add(
            AnalysisEvidence(
                artifact_id=artifact.id,
                field_path="goal.evidence",
                paragraph_id=scene.start_paragraph_id,
                paragraph_hash="v" * 64,
            )
        )
    session.commit()
    return book, chapter, run, revision, scenes, paragraphs


def test_formula_version_and_engagement():
    config = load_formula_config()
    assert config["version"] == "1.0"
    profile = SceneReaderJourneyProfileItem.model_validate(
        {
            "scene_id": 1,
            "scene_ordinal": 1,
            "scene_value_summary": "测试价值",
            "reader_question_in": [],
            "reader_question_created": [
                {
                    "question": "q",
                    "trigger_summary": "触发",
                    "strength": 50,
                    "evidence_paragraph_ids": ["B0001-C0002-P0001"],
                }
            ],
            "reader_question_out": [
                {
                    "question": "q2",
                    "origin": "created_here",
                    "hook_type": "information",
                    "strength": 50,
                    "evidence_paragraph_ids": ["B0001-C0002-P0001"],
                }
            ],
            "dominant_emotion": "好奇",
            "curiosity_score": 60,
            "tension_score": 50,
            "payoff_score": 40,
            "hook_score": 55,
            "information_gain_score": 45,
            "emotional_resonance_score": 40,
            "cognitive_load_score": 20,
            "dropoff_risk_score": 15,
            "confidence": 0.7,
        }
    )
    result = compute_engagement(profile)
    assert 0 <= result.engagement_score <= 100
    assert result.formula_version == "1.0"


def test_scene_batch_planner_max_two_and_splits_fourteen():
    scenes = [Scene(id=i, ordinal=i, scene_key=f"s{i}") for i in range(1, 15)]  # type: ignore[call-arg]
    batches = plan_scene_batches(scenes)  # type: ignore[arg-type]
    assert all(len(batch.scenes) <= 2 for batch in batches)
    assert sum(len(b.scenes) for b in batches) == 14
    assert len(batches) >= 7


def test_preflight_zero_cost(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _seed_run55_like(session)
        run = session.scalar(select(AnalysisRun))
        run_id = run.id

    resp = client.post(f"/api/v1/analysis-runs/{run_id}/reader-journey/preflight", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_scenes"] == 14
    assert body["scene_batch_count"] >= 4


@pytest.mark.asyncio
async def test_full_reader_journey_fake_provider(testing_session):
    _enable_cloud(testing_session)
    _book, chapter, run, _revision, scenes, _paragraphs = _seed_run55_like(testing_session)
    fake = FakeProvider()
    gateway = ModelGateway([fake])
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(
        bind=testing_session.get_bind(), autoflush=False, expire_on_commit=False
    )
    journey_run = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=_book.id,
        chapter_id=chapter.id,
        status="queued",
        provider_name="fake",
        model_name="fake-scene-model",
        total_scene_count=len(scenes),
        remaining_scene_count=len(scenes),
        remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
        cloud_consent=True,
        client_request_id="rj-full-1",
    )
    testing_session.add(journey_run)
    testing_session.commit()
    await execute_reader_journey(session_factory, gateway, journey_run.id)
    with session_factory() as session:
        journey_run = session.get(ReaderJourneyRun, journey_run.id)
        assert journey_run.status == "succeeded"
        profiles = list(
            session.scalars(
                select(SceneReaderJourneyProfile).where(
                    SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id
                )
            )
        )
        phases = list(
            session.scalars(
                select(ReaderJourneyPhase).where(
                    ReaderJourneyPhase.reader_journey_run_id == journey_run.id
                )
            )
        )
        summary = session.scalar(
            select(ChapterReaderJourneySummary).where(
                ChapterReaderJourneySummary.reader_journey_run_id == journey_run.id
            )
        )
        assert len(profiles) == 14
        assert len(phases) == 5
        assert summary is not None
    assert fake.calls >= 5


def test_create_idempotent(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _seed_run55_like(session)
        run = session.scalar(select(AnalysisRun))
        run_id = run.id

    payload = {
        "client_request_id": "idem-1",
        "cloud_consent": True,
        "confirmed": True,
    }
    first = client.post(f"/api/v1/analysis-runs/{run_id}/reader-journey", json=payload)
    second = client.post(f"/api/v1/analysis-runs/{run_id}/reader-journey", json=payload)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["journey_run_id"] == second.json()["journey_run_id"]


def test_score_distribution_validation():
    def _profile(i: int) -> SceneReaderJourneyProfileItem:
        return SceneReaderJourneyProfileItem.model_validate(
            {
                "scene_id": i,
                "scene_ordinal": i,
                "scene_value_summary": f"价值{i}",
                "reader_question_in": [
                    {"question": "q", "source": "carried_from_previous", "confidence": 0.5}
                ],
                "reader_question_out": [
                    {
                        "question": "q2",
                        "origin": "carried",
                        "hook_type": "information",
                        "strength": 90,
                        "evidence_paragraph_ids": ["B0001-C0002-P0001"],
                    }
                ],
                "hooks": [
                    {
                        "type": "danger",
                        "summary": f"Scene{i}留下未闭合悬念",
                        "strength": 85,
                        "evidence_paragraph_ids": ["B0001-C0002-P0001"],
                    }
                ],
                "payoffs": [
                    {
                        "type": "information",
                        "summary": f"Scene{i}提供可验证信息",
                        "strength": 50,
                        "evidence_paragraph_ids": ["B0001-C0002-P0001"],
                    }
                ],
                "dominant_emotion": "紧张",
                "hook_score": 90,
                "curiosity_score": 50,
                "tension_score": 50,
                "payoff_score": 50,
                "information_gain_score": 50,
                "emotional_resonance_score": 50,
                "cognitive_load_score": 20,
                "dropoff_risk_score": 20 + i,
                "confidence": 0.7,
            }
        )

    profiles = [_profile(i) for i in range(1, 5)]
    assessment = validate_score_distribution(profiles)
    assert assessment["requires_review"] is True
    assert any(
        w["code"] in {"JOURNEY_ALL_HOOK_SCORES_HIGH", "JOURNEY_SMALL_SAMPLE_ALL_HIGH"}
        for w in assessment["warnings"]
    )


def test_phase_overlap_rejected():
    result = ChapterReaderJourneySynthesisResult.model_validate(
        {
            "contract_version": "1.0",
            "phases": [
                {
                    "ordinal": 1,
                    "title": "a",
                    "start_scene_ordinal": 1,
                    "end_scene_ordinal": 2,
                    "primary_reader_question": "q",
                    "dominant_emotion": "好奇",
                    "reading_payoff": "p",
                    "continuation_motivation": "m",
                    "summary": "s",
                    "confidence": 0.5,
                },
                {
                    "ordinal": 2,
                    "title": "b",
                    "start_scene_ordinal": 3,
                    "end_scene_ordinal": 4,
                    "primary_reader_question": "q2",
                    "dominant_emotion": "紧张",
                    "reading_payoff": "p2",
                    "continuation_motivation": "m2",
                    "summary": "s2",
                    "confidence": 0.5,
                },
                {
                    "ordinal": 3,
                    "title": "c",
                    "start_scene_ordinal": 3,
                    "end_scene_ordinal": 5,
                    "primary_reader_question": "q3",
                    "dominant_emotion": "压迫",
                    "reading_payoff": "p3",
                    "continuation_motivation": "m3",
                    "summary": "s3",
                    "confidence": 0.5,
                },
            ],
            "one_sentence_diagnosis": "诊断",
        }
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_chapter_synthesis(result, total_scene_count=5)
    assert exc.value.error_code == "JOURNEY_PHASE_SCENE_OVERLAP"
