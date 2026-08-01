"""CHG-023 final: resume uses request.client_request_id; duplicate resume is idempotent."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db.models import ReaderJourneyRun
from tests.test_phase_1c_c1 import _enable_cloud
from tests.test_reader_journey_startup_recovery_local import _seed_orphan_journey


def test_resume_uses_request_client_request_id_in_startup_intent(client, monkeypatch):
    from app.db.session import get_session_factory
    from app.main import app

    calls: list[int] = []

    async def _track(session_factory, gateway, journey_run_id: int):
        calls.append(journey_run_id)

    monkeypatch.setattr("app.api.v1.reader_journey.execute_reader_journey", _track)

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _enable_cloud(session)
        *_rest, journey = _seed_orphan_journey(session, status="scene_profiles_partial")
        journey.retryable = True
        journey.root_error_code = "JOURNEY_INTERRUPTED"
        journey.client_request_id = "seeded-journey-client-id"
        session.commit()
        journey_id = journey.id

    r = client.post(
        f"/api/v1/reader-journey-runs/{journey_id}/resume",
        json={"cloud_consent": True, "client_request_id": "request-resume-cid-1"},
    )
    assert r.status_code == 202, r.text

    with factory() as session:
        row = session.get(ReaderJourneyRun, journey_id)
        import json

        details = json.loads(row.failure_details_json or "{}")
        startup = details.get("startup_intent") or {}
        assert startup.get("client_request_id") == "request-resume-cid-1"
        assert row.client_request_id == "seeded-journey-client-id"

    assert calls == [journey_id]


def test_duplicate_resume_same_client_request_id_does_not_reenqueue(client, monkeypatch):
    from app.db.session import get_session_factory
    from app.main import app

    calls: list[int] = []

    async def _track(session_factory, gateway, journey_run_id: int):
        calls.append(journey_run_id)

    monkeypatch.setattr("app.api.v1.reader_journey.execute_reader_journey", _track)

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _enable_cloud(session)
        *_rest, journey = _seed_orphan_journey(session, status="scene_profiles_partial")
        journey.retryable = True
        journey.root_error_code = "JOURNEY_INTERRUPTED"
        session.commit()
        journey_id = journey.id

    body = {"cloud_consent": True, "client_request_id": "same-resume-cid"}
    r1 = client.post(f"/api/v1/reader-journey-runs/{journey_id}/resume", json=body)
    r2 = client.post(f"/api/v1/reader-journey-runs/{journey_id}/resume", json=body)
    assert r1.status_code == 202
    assert r2.status_code == 202
    # First resume enqueues once; second while starting with same cid must not re-enqueue.
    assert calls == [journey_id]

    with factory() as session:
        count = session.scalar(select(func.count()).select_from(ReaderJourneyRun))
        assert count == 1
