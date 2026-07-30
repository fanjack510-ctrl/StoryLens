"""CHG-20260727-019: Reader Journey orphan recovery + worker isolation (Fake Provider)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import ModelInvocation, ReaderJourneyRun
from app.model_gateway.gateway import ModelGateway
from app.services.reader_journey_pipeline import execute_reader_journey
from app.services.reader_journey_recovery import (
    JOURNEY_INTERRUPTED,
    reclaim_stale_journey_if_needed,
    recover_orphaned_reader_journeys,
)
from app.services.scene_pipeline import mark_interrupted_runs_failed
from tests.fakes import FakeProvider
from tests.test_phase_1c_c1 import _enable_cloud, _seed_run55_like
from tests.test_phase_1c_c1_2 import AlwaysTruncatingFakeProvider


def _session_factory_from(testing_session):
    return sessionmaker(
        bind=testing_session.get_bind(), autoflush=False, expire_on_commit=False
    )


def _seed_orphan_journey(session, *, status: str = "scene_profiles_running"):
    book, chapter, run, _revision, scenes, _paragraphs = _seed_run55_like(
        session, scene_count=3
    )
    run.status = "succeeded"
    session.commit()
    stale = datetime.now(timezone.utc) - timedelta(hours=1)
    journey = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status=status,
        current_stage="reader_journey_scene_profiles",
        provider_name="fake",
        model_name="fake",
        scene_prompt_version="v2.0",
        chapter_prompt_version="v2.0",
        scene_contract_version="2.0",
        chapter_contract_version="2.0",
        formula_version="1.0",
        genre="suspense",
        planner_version="1.1",
        total_scene_count=len(scenes),
        completed_scene_count=0,
        remaining_scene_count=len(scenes),
        completed_scene_ids_json="[]",
        remaining_scene_ids_json="[]",
        started_at=stale,
        created_at=stale,
        updated_at=stale,
        client_request_id="orphan-journey-test",
        cloud_consent=True,
        retryable=False,
    )
    session.add(journey)
    session.commit()
    session.refresh(journey)
    return book, chapter, run, scenes, journey


def test_startup_recovery_marks_orphan_journey_interrupted(testing_session):
    *_rest, journey = _seed_orphan_journey(testing_session)
    inv_before = testing_session.scalar(select(func.count()).select_from(ModelInvocation)) or 0

    stats = mark_interrupted_runs_failed(testing_session)
    testing_session.refresh(journey)

    assert stats["interrupted_journeys"] == 1
    assert journey.status == "failed"
    assert journey.root_error_code == JOURNEY_INTERRUPTED
    assert journey.retryable is True
    assert journey.status != "scene_profiles_running"
    assert (
        testing_session.scalar(select(func.count()).select_from(ModelInvocation)) or 0
    ) == inv_before
    assert testing_session.scalar(select(func.count()).select_from(ReaderJourneyRun)) == 1


def test_startup_recovery_idempotent(testing_session):
    *_rest, journey = _seed_orphan_journey(testing_session)
    first = mark_interrupted_runs_failed(testing_session)
    testing_session.refresh(journey)
    status = journey.status
    code = journey.root_error_code
    completed_at = journey.completed_at

    second = mark_interrupted_runs_failed(testing_session)
    testing_session.refresh(journey)
    assert first["interrupted_journeys"] == 1
    assert second["interrupted_journeys"] == 0
    assert journey.status == status
    assert journey.root_error_code == code
    assert journey.completed_at == completed_at


def test_healthy_running_preserved_when_not_stale(testing_session):
    *_rest, journey = _seed_orphan_journey(testing_session)
    now = datetime.now(timezone.utc)
    journey.updated_at = now
    journey.started_at = now
    testing_session.commit()

    stats = recover_orphaned_reader_journeys(testing_session, force_startup=False)
    testing_session.refresh(journey)
    assert stats["interrupted_journeys"] == 0
    assert journey.status == "scene_profiles_running"


def test_resume_accepts_interrupted_and_reuses_task(client, monkeypatch):
    from app.db.session import get_session_factory
    from app.main import app

    async def _no_provider(*_a, **_k):
        return None

    monkeypatch.setattr(
        "app.api.v1.reader_journey.execute_reader_journey",
        _no_provider,
    )

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _enable_cloud(session)
        _book, _chapter, _run, _scenes, journey = _seed_orphan_journey(session)
        mark_interrupted_runs_failed(session)
        session.refresh(journey)
        journey_id = journey.id
        assert journey.retryable is True

    response = client.post(
        f"/api/v1/reader-journey-runs/{journey_id}/resume",
        json={"cloud_consent": True, "client_request_id": "resume-orphan-001"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["journey_run_id"] == journey_id
    assert body["status"] in {"queued", "starting"}
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ReaderJourneyRun)) == 1
        row = session.get(ReaderJourneyRun, journey_id)
        assert row is not None
        assert row.id == journey_id
        assert row.status in {"queued", "starting"}


def test_resume_healthy_running_returns_409(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _enable_cloud(session)
        *_rest, journey = _seed_orphan_journey(session)
        now = datetime.now(timezone.utc)
        journey.updated_at = now
        journey.started_at = now
        session.commit()
        journey_id = journey.id

    response = client.post(
        f"/api/v1/reader-journey-runs/{journey_id}/resume",
        json={"cloud_consent": True, "client_request_id": "resume-healthy-001"},
    )
    assert response.status_code == 409, response.text
    payload = response.json()
    code = payload.get("error_code") or (payload.get("detail") or {}).get("error_code")
    assert code == "READER_JOURNEY_ALREADY_RUNNING"


@pytest.mark.asyncio
async def test_output_truncated_persists_failed(testing_session):
    _enable_cloud(testing_session)
    book, chapter, run, _revision, scenes, _paragraphs = _seed_run55_like(
        testing_session, scene_count=1
    )
    journey = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="queued",
        provider_name="fake",
        model_name="fake",
        scene_prompt_version="v2.0",
        chapter_prompt_version="v2.0",
        scene_contract_version="2.0",
        chapter_contract_version="2.0",
        formula_version="1.0",
        genre="suspense",
        planner_version="1.1",
        total_scene_count=1,
        completed_scene_count=0,
        remaining_scene_count=1,
        completed_scene_ids_json="[]",
        remaining_scene_ids_json=f"[{scenes[0].id}]",
        client_request_id="trunc-journey",
        cloud_consent=True,
    )
    testing_session.add(journey)
    testing_session.commit()
    testing_session.refresh(journey)

    gateway = ModelGateway([AlwaysTruncatingFakeProvider()])
    factory = _session_factory_from(testing_session)
    await execute_reader_journey(factory, gateway, journey.id)

    testing_session.refresh(journey)
    assert journey.status not in {
        "scene_profiles_running",
        "chapter_synthesis_running",
        "queued",
        "running",
    }
    assert journey.root_error_code in {
        "OUTPUT_TRUNCATED",
        "JOURNEY_SINGLE_PROFILE_OUTPUT_TRUNCATED",
    }


@pytest.mark.asyncio
async def test_worker_unknown_exception_persists(testing_session, monkeypatch):
    _enable_cloud(testing_session)
    book, chapter, run, _revision, scenes, _paragraphs = _seed_run55_like(
        testing_session, scene_count=1
    )
    journey = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="queued",
        provider_name="fake",
        model_name="fake",
        scene_prompt_version="v2.0",
        chapter_prompt_version="v2.0",
        scene_contract_version="2.0",
        chapter_contract_version="2.0",
        formula_version="1.0",
        genre="suspense",
        planner_version="1.1",
        total_scene_count=1,
        completed_scene_count=0,
        remaining_scene_count=1,
        completed_scene_ids_json="[]",
        remaining_scene_ids_json=f"[{scenes[0].id}]",
        client_request_id="boom-journey",
        cloud_consent=True,
    )
    testing_session.add(journey)
    testing_session.commit()
    testing_session.refresh(journey)
    journey_id = journey.id

    async def _boom(*_a, **_k):
        raise RuntimeError("synthetic_worker_boom")

    monkeypatch.setattr(
        "app.services.reader_journey_v2_execution.execute_reader_journey_v2",
        _boom,
    )
    monkeypatch.setattr(
        "app.services.reader_journey_version.is_v2_journey_run",
        lambda _j: True,
    )

    gateway = ModelGateway([FakeProvider()])
    factory = _session_factory_from(testing_session)
    await execute_reader_journey(factory, gateway, journey_id)

    testing_session.expire_all()
    row = testing_session.get(ReaderJourneyRun, journey_id)
    assert row is not None
    assert row.status == "failed"
    assert row.root_error_code is not None


def test_reclaim_stale_on_resume_entry(testing_session):
    *_rest, journey = _seed_orphan_journey(testing_session)
    changed = reclaim_stale_journey_if_needed(testing_session, journey)
    testing_session.refresh(journey)
    assert changed is True
    assert journey.root_error_code == JOURNEY_INTERRUPTED
    assert journey.retryable is True


def test_sidecar_health_after_recovery(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json().get("status") == "ok"
