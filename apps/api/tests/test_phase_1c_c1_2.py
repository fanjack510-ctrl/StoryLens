"""Phase 1C-C.1.2 Reader Journey truncation fix tests — Fake Provider only."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import ModelInvocation, ReaderJourneyRun, SceneReaderJourneyProfile
from app.model_gateway.base import ModelRequest, ModelResponse
from app.model_gateway.gateway import ModelGateway
from app.schemas.reader_journey import SceneReaderJourneyProfileItem
from app.services.reader_journey_batch_planner import (
    estimate_batch_output_tokens,
    estimate_scene_profile_tokens,
    output_token_budget,
    plan_scene_batches,
)
from app.services.reader_journey_pipeline import execute_reader_journey
from tests.fakes import FakeProvider
from tests.test_phase_1c_c1 import _enable_cloud, _seed_run55_like


def _batch_scene_count(combined: str) -> int:
    marker = combined.find('"profiles_target"')
    if marker == -1:
        return 0
    slice_text = combined[marker:]
    bracket = slice_text.find("[")
    if bracket == -1:
        return 0
    depth = 0
    for index, char in enumerate(slice_text[bracket:], start=bracket):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                array_text = slice_text[bracket : index + 1]
                return len(re.findall(r'"scene_id"\s*:\s*(\d+)', array_text))
    return 0


class TruncatingOnMultiSceneFakeProvider(FakeProvider):
    """Truncate any multi-scene batch; single-scene calls succeed."""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        combined = "\n".join(item["content"] for item in request.messages)
        if _batch_scene_count(combined) >= 2:
            return ModelResponse(
                text='{"incomplete',
                model=self.default_model,
                finish_reason="length",
                http_status_code=200,
            )
        return await super().generate(request)


class AlwaysTruncatingFakeProvider(FakeProvider):
    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            text='{"incomplete',
            model=self.default_model,
            finish_reason="length",
            http_status_code=200,
        )


def _session_factory_from(testing_session):
    return sessionmaker(
        bind=testing_session.get_bind(), autoflush=False, expire_on_commit=False
    )


def test_planner_splits_old_four_scene_style_and_respects_budget():
    from app.db.models import Paragraph, Scene

    scenes = [
        Scene(
            id=i,
            ordinal=i,
            scene_key=f"s{i}",
            start_paragraph_id=f"P{i:04d}a",
            end_paragraph_id=f"P{i:04d}b",
        )
        for i in range(1, 5)
    ]
    paragraphs = [
        Paragraph(
            id=f"P{i:04d}a",
            book_id=1,
            chapter_id=1,
            paragraph_index=i * 2 - 1,
            raw_text="短",
            normalized_text="短",
            char_start=0,
            char_end=1,
        )
        for i in range(1, 5)
    ] + [
        Paragraph(
            id=f"P{i:04d}b",
            book_id=1,
            chapter_id=1,
            paragraph_index=i * 2,
            raw_text="短",
            normalized_text="短",
            char_start=0,
            char_end=1,
        )
        for i in range(1, 5)
    ]
    old_style = plan_scene_batches(scenes, batch_size=4, paragraphs=paragraphs)
    assert all(len(batch.scenes) <= 2 for batch in old_style)
    assert sum(len(batch.scenes) for batch in old_style) == 4

    paired = plan_scene_batches(
        scenes, batch_size=4, paragraphs=paragraphs, output_limit=8000
    )
    assert all(len(batch.scenes) <= 2 for batch in paired)
    assert sum(len(batch.scenes) for batch in paired) == 4

    fourteen = [
        Scene(id=i, ordinal=i, scene_key=f"s{i}", start_paragraph_id=f"P{i:04d}", end_paragraph_id=f"P{i:04d}")  # type: ignore[call-arg]
        for i in range(1, 15)
    ]
    default_batches = plan_scene_batches(fourteen)  # type: ignore[arg-type]
    assert all(len(batch.scenes) <= 2 for batch in default_batches)
    assert len(default_batches) >= 7

    long_paragraphs = [
        Paragraph(
            id="LONGa",
            book_id=1,
            chapter_id=1,
            paragraph_index=1,
            raw_text="长" * 2000,
            normalized_text="长" * 2000,
            char_start=0,
            char_end=2000,
        ),
        Paragraph(
            id="LONGb",
            book_id=1,
            chapter_id=1,
            paragraph_index=2,
            raw_text="长" * 2000,
            normalized_text="长" * 2000,
            char_start=2000,
            char_end=4000,
        ),
    ]
    long_scene = Scene(
        id=99,
        ordinal=1,
        scene_key="long",
        start_paragraph_id="LONGa",
        end_paragraph_id="LONGb",
    )
    long_batches = plan_scene_batches([long_scene], paragraphs=long_paragraphs)
    assert len(long_batches) == 1
    assert len(long_batches[0].scenes) == 1

    budget = output_token_budget()
    position = {item.id: index for index, item in enumerate(paragraphs)}
    pair_estimate = estimate_batch_output_tokens(
        [
            estimate_scene_profile_tokens(scenes[0], paragraphs=paragraphs, position=position),
            estimate_scene_profile_tokens(scenes[1], paragraphs=paragraphs, position=position),
        ]
    )
    if pair_estimate <= budget:
        assert any(len(batch.scenes) == 2 for batch in old_style)
    else:
        assert all(len(batch.scenes) == 1 for batch in old_style)
    for batch in old_style:
        if len(batch.scenes) > 1:
            estimates = [
                estimate_scene_profile_tokens(scene, paragraphs=paragraphs, position=position)
                for scene in batch.scenes
            ]
            assert estimate_batch_output_tokens(estimates) <= budget
            assert batch.estimated_output_tokens <= budget


@pytest.mark.asyncio
async def test_split_after_truncation_no_truncation_retry(testing_session, monkeypatch):
    from app.services import reader_journey_pipeline as pipeline_mod
    from app.services.reader_journey_batch_planner import PLANNER_VERSION, ReaderJourneySceneBatch

    _real_plan = plan_scene_batches

    def _pair_first_batches(scenes, **kwargs):
        batches = _real_plan(scenes, **kwargs)
        if len(batches) >= 2 and len(batches[0].scenes) == 1 and len(batches[1].scenes) == 1:
            merged_scenes = batches[0].scenes + batches[1].scenes
            merged = ReaderJourneySceneBatch(
                batch_index=1,
                scenes=merged_scenes,
                scene_ids=[item.id for item in merged_scenes],
                scene_ordinals=[item.ordinal for item in merged_scenes],
                estimated_output_tokens=(
                    batches[0].estimated_output_tokens + batches[1].estimated_output_tokens
                ),
                planner_version=PLANNER_VERSION,
                batch_count=len(batches) - 1,
            )
            tail = [
                batch.with_index(index, len(batches) - 1)
                for index, batch in enumerate(batches[2:], start=2)
            ]
            return [merged, *tail]
        return batches

    monkeypatch.setattr(pipeline_mod, "plan_scene_batches", _pair_first_batches)

    _enable_cloud(testing_session)
    book, chapter, run, _revision, scenes, _paragraphs = _seed_run55_like(testing_session)
    fake = TruncatingOnMultiSceneFakeProvider()
    gateway = ModelGateway([fake])
    session_factory = _session_factory_from(testing_session)
    journey_run = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="queued",
        provider_name="fake",
        model_name="fake-scene-model",
        total_scene_count=len(scenes),
        remaining_scene_count=len(scenes),
        remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
        cloud_consent=True,
        client_request_id="rj-split-1",
    )
    testing_session.add(journey_run)
    testing_session.commit()

    await execute_reader_journey(session_factory, gateway, journey_run.id)

    with session_factory() as session:
        journey_run = session.get(ReaderJourneyRun, journey_run.id)
        assert journey_run.status == "succeeded"
        invocations = list(
            session.scalars(
                select(ModelInvocation).where(
                    ModelInvocation.run_id == run.id,
                    ModelInvocation.task_type == "reader_journey_scene",
                )
            )
        )
        kinds = [row.invocation_kind for row in invocations]
        assert "truncation_retry" not in kinds
        assert "split_batch_request" in kinds
        profiles = list(
            session.scalars(
                select(SceneReaderJourneyProfile).where(
                    SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id
                )
            )
        )
        assert len(profiles) == 14
        scene_ids = [row.scene_id for row in profiles]
        assert len(scene_ids) == len(set(scene_ids))


@pytest.mark.asyncio
async def test_single_scene_truncation_fails_without_infinite_retries(testing_session):
    _enable_cloud(testing_session)
    book, chapter, run, _revision, scenes, _paragraphs = _seed_run55_like(testing_session)
    fake = AlwaysTruncatingFakeProvider()
    gateway = ModelGateway([fake])
    session_factory = _session_factory_from(testing_session)
    journey_run = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="queued",
        provider_name="fake",
        model_name="fake-scene-model",
        total_scene_count=len(scenes),
        remaining_scene_count=len(scenes),
        remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
        cloud_consent=True,
        client_request_id="rj-single-trunc-1",
    )
    testing_session.add(journey_run)
    testing_session.commit()

    await execute_reader_journey(session_factory, gateway, journey_run.id)

    with session_factory() as session:
        journey_run = session.get(ReaderJourneyRun, journey_run.id)
        assert journey_run.status == "failed"
        assert journey_run.root_error_code == "JOURNEY_SINGLE_PROFILE_OUTPUT_TRUNCATED"
        assert journey_run.completed_at is not None
        assert journey_run.retryable is False
        invocation_count = session.scalar(
            select(func.count())
            .select_from(ModelInvocation)
            .where(
                ModelInvocation.run_id == run.id,
                ModelInvocation.task_type == "reader_journey_scene",
            )
        )
        assert int(invocation_count or 0) <= 3
        assert fake.calls <= 3


def test_resume_same_run_preserves_invocations(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _enable_cloud(session)
        book, chapter, run, _revision, scenes, _paragraphs = _seed_run55_like(session)
        journey_run = ReaderJourneyRun(
            analysis_run_id=run.id,
            book_id=book.id,
            chapter_id=chapter.id,
            status="failed",
            planner_version="1.0",
            root_error_code="OUTPUT_TRUNCATED",
            root_error_message="truncated batch",
            retryable=True,
            provider_name="fake",
            model_name="fake-scene-model",
            total_scene_count=len(scenes),
            completed_scene_count=0,
            remaining_scene_count=len(scenes),
            remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
            completed_scene_ids_json="[]",
            cloud_consent=True,
            client_request_id="rj-resume-1",
            completed_at=datetime.now(timezone.utc),
        )
        session.add(journey_run)
        session.flush()
        session.add(
            ModelInvocation(
                run_id=run.id,
                task_type="reader_journey_scene",
                provider_name="fake",
                model_name="fake-scene-model",
                prompt_version="v1",
                schema_version="v1",
                attempt_no=1,
                invocation_kind="normal_batch_request",
                request_hash="h" * 64,
                input_snapshot_json="{}",
                raw_response_text='{"truncated": true}',
                status="failed",
                latency_ms=10,
                http_request_sent=True,
                error_code="OUTPUT_TRUNCATED",
            )
        )
        session.commit()
        journey_id = journey_run.id
        prior_invocation_ids = [
            row.id
            for row in session.scalars(
                select(ModelInvocation).where(ModelInvocation.run_id == run.id)
            )
        ]

    resume = client.post(
        f"/api/v1/reader-journey-runs/{journey_id}/resume",
        json={"client_request_id": "resume-c1-2", "cloud_consent": True},
    )
    assert resume.status_code == 202
    assert resume.json()["journey_run_id"] == journey_id

    with factory() as session:
        journey_run = session.get(ReaderJourneyRun, journey_id)
        assert journey_run.status == "succeeded"
        all_invocations = list(
            session.scalars(select(ModelInvocation).where(ModelInvocation.run_id == run.id))
        )
        preserved_ids = {row.id for row in all_invocations}
        for prior_id in prior_invocation_ids:
            assert prior_id in preserved_ids
        assert len(all_invocations) > len(prior_invocation_ids)
        profiles = session.scalar(
            select(func.count())
            .select_from(SceneReaderJourneyProfile)
            .where(SceneReaderJourneyProfile.reader_journey_run_id == journey_id)
        )
        assert int(profiles or 0) == 14


def test_duplicate_create_returns_existing_without_third_run(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _enable_cloud(session)
        book, chapter, run, _revision, scenes, _paragraphs = _seed_run55_like(session)
        existing = ReaderJourneyRun(
            analysis_run_id=run.id,
            book_id=book.id,
            chapter_id=chapter.id,
            status="failed",
            planner_version="1.0",
            root_error_code="OUTPUT_TRUNCATED",
            retryable=True,
            provider_name="fake",
            model_name="fake-scene-model",
            total_scene_count=len(scenes),
            completed_scene_count=0,
            remaining_scene_count=len(scenes),
            remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
            completed_scene_ids_json="[]",
            cloud_consent=True,
            client_request_id="existing-failed",
            completed_at=datetime.now(timezone.utc),
        )
        session.add(existing)
        session.commit()
        run_id = run.id
        first_id = existing.id

    second = client.post(
        f"/api/v1/analysis-runs/{run_id}/reader-journey",
        json={"client_request_id": "create-b", "cloud_consent": True, "confirmed": True},
    )
    assert second.status_code == 202
    body = second.json()
    assert body["journey_run_id"] == first_id
    assert body.get("idempotent_replay") is True
    assert body.get("creation_blocked_reason") == "ACTIVE_OR_RECOVERABLE_JOURNEY_EXISTS"

    with factory() as session:
        count = session.scalar(
            select(func.count())
            .select_from(ReaderJourneyRun)
            .where(ReaderJourneyRun.analysis_run_id == run_id)
        )
        assert int(count or 0) == 1


def test_schema_max_lengths_reject_oversized_fields():
    base = {
        "scene_id": 1,
        "scene_ordinal": 1,
        "scene_value_summary": "合法摘要",
        "reader_question_in": [
            {"question": "q", "source": "carried_from_previous", "confidence": 0.5}
        ],
        "reader_question_created": [
            {
                "question": "c",
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
    too_many_questions = {
        **base,
        "reader_question_created": [
            {
                "question": f"q{i}",
                "trigger_summary": "t",
                "strength": 50,
                "evidence_paragraph_ids": ["B0001-C0002-P0001"],
            }
            for i in range(3)
        ],
    }
    with pytest.raises(ValidationError):
        SceneReaderJourneyProfileItem.model_validate(too_many_questions)

    long_summary = {**base, "scene_value_summary": "x" * 161}
    with pytest.raises(ValidationError):
        SceneReaderJourneyProfileItem.model_validate(long_summary)


def test_preflight_scene_batch_count_at_least_seven(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _enable_cloud(session)
        _seed_run55_like(session)
        from app.db.models import AnalysisRun

        run_id = session.scalar(select(AnalysisRun)).id

    resp = client.post(f"/api/v1/analysis-runs/{run_id}/reader-journey/preflight", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_scenes"] == 14
    assert body["scene_batch_count"] >= 7


@pytest.mark.asyncio
async def test_execute_reader_journey_truncation_does_not_raise(testing_session):
    _enable_cloud(testing_session)
    book, chapter, run, _revision, scenes, _paragraphs = _seed_run55_like(testing_session)
    fake = AlwaysTruncatingFakeProvider()
    gateway = ModelGateway([fake])
    session_factory = _session_factory_from(testing_session)
    journey_run = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="queued",
        provider_name="fake",
        model_name="fake-scene-model",
        total_scene_count=len(scenes),
        remaining_scene_count=len(scenes),
        remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
        cloud_consent=True,
        client_request_id="rj-no-raise-1",
    )
    testing_session.add(journey_run)
    testing_session.commit()

    await execute_reader_journey(session_factory, gateway, journey_run.id)

    with session_factory() as session:
        row = session.get(ReaderJourneyRun, journey_run.id)
        assert row.status == "failed"
        assert row.completed_at is not None
