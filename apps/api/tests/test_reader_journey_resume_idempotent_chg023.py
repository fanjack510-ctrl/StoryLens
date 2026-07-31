"""CHG-20260731-023 — resume idempotency for already running / succeeded."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db.models import ReaderJourneyRun
from tests.test_phase_1c_c1 import _enable_cloud
from tests.test_reader_journey_startup_recovery_local import _seed_orphan_journey


def test_resume_succeeded_is_idempotent_no_new_task(client, monkeypatch):
    from app.db.session import get_session_factory
    from app.main import app

    calls: list[int] = []

    async def _track(session_factory, gateway, journey_run_id: int):
        calls.append(journey_run_id)

    monkeypatch.setattr(
        "app.api.v1.reader_journey.execute_reader_journey",
        _track,
    )

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _enable_cloud(session)
        *_rest, journey = _seed_orphan_journey(session)
        journey.status = "succeeded"
        journey.retryable = False
        session.commit()
        journey_id = journey.id
        before = session.scalar(select(func.count()).select_from(ReaderJourneyRun))

    for i in range(3):
        response = client.post(
            f"/api/v1/reader-journey-runs/{journey_id}/resume",
            json={
                "cloud_consent": True,
                "client_request_id": f"resume-succeeded-{i}",
            },
        )
        assert response.status_code == 202, response.text
        assert response.json()["journey_run_id"] == journey_id
        assert response.json()["status"] == "succeeded"

    with factory() as session:
        after = session.scalar(select(func.count()).select_from(ReaderJourneyRun))
        assert after == before
    assert calls == []


def test_resume_running_twice_does_not_reenqueue(client, monkeypatch):
    from app.db.session import get_session_factory
    from app.main import app

    calls: list[int] = []

    async def _track(session_factory, gateway, journey_run_id: int):
        calls.append(journey_run_id)

    monkeypatch.setattr(
        "app.api.v1.reader_journey.execute_reader_journey",
        _track,
    )

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _enable_cloud(session)
        *_rest, journey = _seed_orphan_journey(session)
        now = datetime.now(timezone.utc)
        journey.updated_at = now
        journey.started_at = now
        session.commit()
        journey_id = journey.id

    r1 = client.post(
        f"/api/v1/reader-journey-runs/{journey_id}/resume",
        json={"cloud_consent": True, "client_request_id": "resume-run-1"},
    )
    r2 = client.post(
        f"/api/v1/reader-journey-runs/{journey_id}/resume",
        json={"cloud_consent": True, "client_request_id": "resume-run-1"},
    )
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["journey_run_id"] == journey_id
    assert r2.json()["journey_run_id"] == journey_id
    assert calls == []
