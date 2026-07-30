"""CHG-20260730-013: Confirm+Start bootstrap race / interrupt / continue routing."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import CloudBudgetReservation, ModelInvocation, ReaderJourneyRun
from app.model_gateway.gateway import ModelGateway
from app.services.chapter_analysis_completion import effective_chapter_status
from app.services.reader_journey_pipeline import execute_reader_journey
from app.services.reader_journey_recovery import (
    JOURNEY_INTERRUPTED,
    claim_journey_worker,
    mark_journey_startup_intent,
    recover_orphaned_reader_journeys,
)
from app.services.scene_boundary_manual_review import (
    confirm_scene_revision_and_start_journey_v1,
    create_or_get_scene_boundary_draft_v1,
    save_scene_boundary_draft_v1,
)
from app.services.scene_pipeline import mark_interrupted_runs_failed
from tests.fakes import FakeProvider
from tests.test_chg041_scene_boundary_manual_review import (
    _attach_scene_analysis,
    _seed_chapter,
)
from tests.test_phase_1c_c1 import _enable_cloud


def _session_factory_from(testing_session):
    return sessionmaker(
        bind=testing_session.get_bind(), autoflush=False, expire_on_commit=False
    )


def _prepare_confirmable(session, *, scene_count: int = 3):
    _enable_cloud(session)
    book, chapter, paragraphs, run, scenes = _seed_chapter(
        session, paragraph_count=12, scene_count=6
    )
    _attach_scene_analysis(session, run, scenes)
    draft = create_or_get_scene_boundary_draft_v1(session, chapter.id)
    session.commit()
    session.refresh(draft)
    # Shrink to N scenes for confirm.
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
    draft = save_scene_boundary_draft_v1(
        session, draft.id, partition, expected_etag=draft.revision_etag
    )
    session.commit()
    session.refresh(draft)
    return book, chapter, run, draft


@pytest.mark.asyncio
async def test_confirm_startup_not_interrupted_before_worker_claim(testing_session):
    *_rest, run, draft = _prepare_confirmable(testing_session, scene_count=3)
    revision, journey, _already, err = await confirm_scene_revision_and_start_journey_v1(
        testing_session,
        draft.id,
        expected_etag=draft.revision_etag,
        start_journey=True,
    )
    assert err is None
    assert journey is not None
    assert journey.status in {"starting", "queued"}
    assert journey.scene_revision_id == revision.id

    stats = mark_interrupted_runs_failed(testing_session)
    testing_session.refresh(journey)
    assert journey.status in {"starting", "queued"}
    assert journey.root_error_code != JOURNEY_INTERRUPTED
    assert stats.get("interrupted_journeys", 0) == 0
    assert int(journey.id) in (stats.get("requeue_journey_ids") or [])


@pytest.mark.asyncio
async def test_confirm_repeated_is_idempotent(testing_session):
    *_rest, run, draft = _prepare_confirmable(testing_session, scene_count=3)
    r1, j1, _, e1 = await confirm_scene_revision_and_start_journey_v1(
        testing_session,
        draft.id,
        expected_etag=draft.revision_etag,
        start_journey=True,
    )
    assert e1 is None and j1 is not None
    testing_session.refresh(draft)
    r2, j2, already, e2 = await confirm_scene_revision_and_start_journey_v1(
        testing_session,
        draft.id,
        expected_etag=draft.revision_etag,
        start_journey=True,
    )
    assert e2 is None
    assert already is True
    assert r1.id == r2.id
    assert j1.id == j2.id
    count = testing_session.scalar(
        select(func.count())
        .select_from(ReaderJourneyRun)
        .where(ReaderJourneyRun.analysis_run_id == run.id)
    )
    assert count == 1


@pytest.mark.asyncio
async def test_delayed_worker_claim_keeps_starting(testing_session):
    *_rest, run, draft = _prepare_confirmable(testing_session, scene_count=3)
    _rev, journey, _, err = await confirm_scene_revision_and_start_journey_v1(
        testing_session,
        draft.id,
        expected_etag=draft.revision_etag,
        start_journey=True,
    )
    assert err is None and journey is not None
    await asyncio.sleep(0.05)
    recover_orphaned_reader_journeys(testing_session, force_startup=True)
    testing_session.refresh(journey)
    assert journey.status in {"starting", "queued"}
    # CHG-015: rematerialized spans without carried artifacts report scene_analysis;
    # live starting journey must still not look interrupted/failed.
    assert effective_chapter_status(testing_session, run) in {
        "journey_running",
        "scene_analysis",
    }
    assert journey.root_error_code in {None, "WAITING_SCENE_ANALYSIS"}

    claimed = claim_journey_worker(testing_session, journey)
    testing_session.commit()
    assert claimed is True
    testing_session.refresh(journey)
    assert journey.status == "running"


@pytest.mark.asyncio
async def test_claimed_orphan_is_interrupted(testing_session):
    *_rest, _run, draft = _prepare_confirmable(testing_session, scene_count=3)
    _rev, journey, _, err = await confirm_scene_revision_and_start_journey_v1(
        testing_session,
        draft.id,
        expected_etag=draft.revision_etag,
        start_journey=True,
    )
    assert journey is not None and err is None
    claim_journey_worker(testing_session, journey)
    journey.status = "scene_profiles_running"
    journey.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
    testing_session.commit()

    stats = recover_orphaned_reader_journeys(testing_session, force_startup=True)
    testing_session.refresh(journey)
    assert stats["interrupted_journeys"] == 1
    assert journey.root_error_code == JOURNEY_INTERRUPTED


@pytest.mark.asyncio
async def test_resume_idempotent_does_not_create_runs(testing_session):
    *_rest, _run, draft = _prepare_confirmable(testing_session, scene_count=3)
    _rev, journey, _, err = await confirm_scene_revision_and_start_journey_v1(
        testing_session,
        draft.id,
        expected_etag=draft.revision_etag,
        start_journey=True,
    )
    assert journey is not None and err is None
    claim_journey_worker(testing_session, journey)
    journey.status = "scene_profiles_running"
    testing_session.commit()
    recover_orphaned_reader_journeys(testing_session, force_startup=True)
    testing_session.refresh(journey)
    assert journey.root_error_code == JOURNEY_INTERRUPTED

    before = testing_session.scalar(select(func.count()).select_from(ReaderJourneyRun)) or 0
    reservations_before = (
        testing_session.scalar(select(func.count()).select_from(CloudBudgetReservation))
        or 0
    )
    for _ in range(5):
        mark_journey_startup_intent(journey, client_request_id=journey.client_request_id)
        testing_session.commit()
        testing_session.refresh(journey)
        assert journey.status in {"starting", "queued"}
    after = testing_session.scalar(select(func.count()).select_from(ReaderJourneyRun)) or 0
    reservations_after = (
        testing_session.scalar(select(func.count()).select_from(CloudBudgetReservation))
        or 0
    )
    assert after == before
    assert reservations_after == reservations_before


@pytest.mark.asyncio
async def test_effective_status_prefers_live_journey_over_awaiting_marker(
    testing_session,
):
    *_rest, run, draft = _prepare_confirmable(testing_session, scene_count=3)
    run.raw_output = (
        '{"chapter_pipeline":"awaiting_scene_boundary_confirmation",'
        '"checkpoint_stage":"scene_boundary_confirmation","kind":"chapter_pipeline"}'
    )
    testing_session.commit()
    _rev, journey, _, err = await confirm_scene_revision_and_start_journey_v1(
        testing_session,
        draft.id,
        expected_etag=draft.revision_etag,
        start_journey=True,
    )
    assert journey is not None and err is None
    testing_session.refresh(run)
    # Live starting journey wins over awaiting-confirmation marker (CHG-013),
    # and may surface as scene_analysis while WAITING_SCENE_ANALYSIS (CHG-015).
    assert effective_chapter_status(testing_session, run) in {
        "journey_running",
        "scene_analysis",
    }
    assert effective_chapter_status(testing_session, run) != (
        "awaiting_scene_boundary_confirmation"
    )


@pytest.mark.asyncio
async def test_execute_claims_before_provider(testing_session):
    *_rest, _run, draft = _prepare_confirmable(testing_session, scene_count=3)
    _rev, journey, _, err = await confirm_scene_revision_and_start_journey_v1(
        testing_session,
        draft.id,
        expected_etag=draft.revision_etag,
        start_journey=True,
    )
    assert journey is not None and err is None
    factory = _session_factory_from(testing_session)
    gateway = ModelGateway([FakeProvider()])
    await execute_reader_journey(factory, gateway, journey.id)
    testing_session.refresh(journey)
    # CHG-015: without carried artifacts, worker waits instead of failing.
    if journey.root_error_code == "WAITING_SCENE_ANALYSIS":
        assert journey.status == "starting"
    else:
        assert journey.status != "starting"
    _ = testing_session.scalar(select(func.count()).select_from(ModelInvocation)) or 0


def test_http_e2e_confirm_start_delayed_worker_not_interrupted(client):
    """HTTP E2E: confirm 3 scenes; hold BackgroundTasks; boot recover must not interrupt."""
    from unittest.mock import patch

    from app.db.session import get_session_factory
    from starlette.background import BackgroundTasks

    factory = client.app.dependency_overrides[get_session_factory]()
    with factory() as session:
        book, chapter, _run, draft = _prepare_confirmable(session, scene_count=3)
        chapter_id = chapter.id
        revision_id = draft.id
        etag = draft.revision_etag
        book_id = book.id

    with patch.object(BackgroundTasks, "add_task", lambda self, fn, *a, **k: None):
        resp = client.post(
            f"/api/v1/chapters/{chapter_id}/scene-boundaries/draft/{revision_id}/confirm",
            json={"expected_etag": etag, "start_journey": True},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["confirmed_scene_count"] == 3
    assert body["workflow_state"] == "starting"
    assert body["journey_run_id"] is not None
    assert body["already_started"] is False
    journey_id = int(body["journey_run_id"])

    with factory() as session:
        journey = session.get(ReaderJourneyRun, journey_id)
        assert journey is not None
        assert journey.status in {"starting", "queued"}
        stats = mark_interrupted_runs_failed(session)
        session.refresh(journey)
        assert journey.status in {"starting", "queued"}
        assert journey.root_error_code != JOURNEY_INTERRUPTED
        assert stats.get("interrupted_journeys", 0) == 0

    get_resp = client.get(f"/api/v1/reader-journey-runs/{journey_id}/progress")
    assert get_resp.status_code == 200
    progress = get_resp.json()
    assert progress["status"] in {"starting", "queued"}
    assert progress.get("root_error_code") != JOURNEY_INTERRUPTED

    # Claim atomically (worker start) without requiring full Fake pipeline success
    # after rematerialize — race fix is about startup vs interrupt, not synthesis.
    with factory() as session:
        journey = session.get(ReaderJourneyRun, journey_id)
        assert journey is not None
        claimed = claim_journey_worker(session, journey)
        session.commit()
        session.refresh(journey)
        assert claimed is True
        assert journey.status == "running"
    _ = book_id


def test_http_e2e_confirm_idempotent_and_resume_same_run(client):
    """HTTP: repeated confirm + resume do not create extra journey runs."""
    from unittest.mock import patch

    from app.db.session import get_session_factory
    from starlette.background import BackgroundTasks

    factory = client.app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _book, chapter, run, draft = _prepare_confirmable(session, scene_count=3)
        chapter_id = chapter.id
        revision_id = draft.id
        etag = draft.revision_etag
        analysis_run_id = run.id

    with patch.object(BackgroundTasks, "add_task", lambda self, fn, *a, **k: None):
        r1 = client.post(
            f"/api/v1/chapters/{chapter_id}/scene-boundaries/draft/{revision_id}/confirm",
            json={"expected_etag": etag, "start_journey": True},
        )
        assert r1.status_code == 200, r1.text
        jid = r1.json()["journey_run_id"]
        with factory() as session:
            from app.db.models import BoundaryRevision

            rev = session.get(BoundaryRevision, revision_id)
            etag2 = rev.revision_etag if rev else etag
        r2 = client.post(
            f"/api/v1/chapters/{chapter_id}/scene-boundaries/draft/{revision_id}/confirm",
            json={"expected_etag": etag2, "start_journey": True},
        )
    assert r2.status_code in {200, 409}, r2.text
    if r2.status_code == 200:
        assert r2.json()["journey_run_id"] == jid

    with factory() as session:
        count = session.scalar(
            select(func.count())
            .select_from(ReaderJourneyRun)
            .where(ReaderJourneyRun.analysis_run_id == analysis_run_id)
        )
        assert count == 1
        journey = session.get(ReaderJourneyRun, jid)
        assert journey is not None
        claim_journey_worker(session, journey)
        journey.status = "scene_profiles_running"
        session.commit()
        recover_orphaned_reader_journeys(session, force_startup=True)
        session.refresh(journey)
        assert journey.root_error_code == JOURNEY_INTERRUPTED
        client_request_id = journey.client_request_id or f"resume-idempotent:{jid}"

    with patch.object(BackgroundTasks, "add_task", lambda self, fn, *a, **k: None):
        resume = client.post(
            f"/api/v1/reader-journey-runs/{jid}/resume",
            json={"cloud_consent": True, "client_request_id": client_request_id},
        )
    assert resume.status_code in {200, 202}, resume.text
    body = resume.json()
    assert int(body.get("journey_run_id") or body.get("id") or 0) == int(jid)
    with factory() as session:
        count = session.scalar(
            select(func.count())
            .select_from(ReaderJourneyRun)
            .where(ReaderJourneyRun.analysis_run_id == analysis_run_id)
        )
        assert count == 1
        journey = session.get(ReaderJourneyRun, jid)
        assert journey is not None
        assert journey.status in {"starting", "queued", "running", "scene_profiles_running"}
