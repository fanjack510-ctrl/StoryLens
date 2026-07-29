"""CHG-20260729-006 — cooperative AnalysisRun cancellation tests.

Isolated temp SQLite only (conftest client / testing_session). No real providers,
no AppData DB, no process kill.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, inspect, select, text

from app.db.models import AnalysisRun, Base, CloudBudgetReservation, ModelInvocation
from app.db.session import get_session_factory, migrate_phase_task_cancellation_v1
from app.main import app
from app.services.scene_pipeline import mark_interrupted_runs_failed
from app.services.task_cancellation import (
    AnalysisCancellationRequested,
    finalize_cancelled,
    raise_if_cancel_requested,
    request_cancel,
    try_finalize_if_cancel_requested,
)
from tests.fakes import FakeProvider


def _factory():
    override = app.dependency_overrides.get(get_session_factory)
    assert override is not None, "client fixture must override get_session_factory"
    return override()


def _make_run(
    session,
    status: str = "queued",
    *,
    subject_id: str = "1",
    started_at: datetime | None = None,
    status_version: int = 0,
    set_started: bool | None = None,
) -> AnalysisRun:
    """Create a minimal AnalysisRun.

    set_started=True forces run_started_at; set_started=False clears it.
    Default: started for non-queued worker-like statuses when started_at omitted.
    """
    if set_started is True and started_at is None:
        started_at = datetime.now(timezone.utc)
    elif set_started is False:
        started_at = None
    elif set_started is None and started_at is None and status not in {
        "queued",
        "pending",
        "paused",
        "awaiting_provider_recovery",
        "awaiting_boundary_review",
    }:
        # Leave started_at as provided (None) unless caller wants worker path.
        pass

    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=subject_id,
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="v1",
        prompt_hash="p" * 64,
        input_hash="i" * 64,
        status=status,
        status_version=status_version,
        started_at=started_at,
        execution_mode="local",
        cloud_consent=False,
        sends_content_to_cloud=False,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _make_reservation(
    session,
    *,
    run_id: int,
    remaining_cost: float = 0.1,
    status: str = "active",
) -> CloudBudgetReservation:
    now = datetime.now(timezone.utc)
    row = CloudBudgetReservation(
        run_id=run_id,
        stage="scene_analysis",
        reserved_requests=10,
        reserved_tokens=1000,
        reserved_cost=remaining_cost,
        remaining_requests=10,
        consumed_requests=0,
        released_requests=0,
        remaining_tokens=1000,
        consumed_tokens=0,
        released_tokens=0,
        remaining_cost=remaining_cost,
        consumed_cost=0.0,
        released_cost=0.0,
        expected_requests=10,
        worst_case_requests=20,
        status=status,
        expires_at=now + timedelta(minutes=30),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _cancel(client, run_id: int, **body):
    payload = body if body else None
    if payload is None:
        return client.post(f"/api/v1/analysis-runs/{run_id}/cancel")
    return client.post(f"/api/v1/analysis-runs/{run_id}/cancel", json=payload)


def _assert_no_raw_stack(body: object) -> None:
    text_blob = json.dumps(body, default=str).lower()
    assert "traceback" not in text_blob
    assert 'file "' not in text_blob
    assert "stacktrace" not in text_blob


# ---------------------------------------------------------------------------
# API cancel paths
# ---------------------------------------------------------------------------


def test_queued_cancel_becomes_cancelled_without_provider_calls(client, fake_provider: FakeProvider):
    with _factory()() as session:
        run = _make_run(session, "queued", set_started=False)
        run_id = run.id

    resp = _cancel(client, run_id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_status"] == "cancelled"
    assert body["already_cancelled"] is True
    assert body["cannot_cancel"] is False
    assert body["previous_status"] == "queued"
    _assert_no_raw_stack(body)

    with _factory()() as session:
        refreshed = session.get(AnalysisRun, run_id)
        assert refreshed is not None
        assert refreshed.status == "cancelled"
        assert refreshed.cancelled_at is not None
        assert refreshed.cancellation_reason == "user_requested"
        inv_count = session.scalar(
            select(func.count()).select_from(ModelInvocation).where(
                ModelInvocation.run_id == run_id
            )
        )
        assert inv_count == 0

    assert fake_provider.calls == 0


def test_running_with_started_at_cancel_requests_cooperative_stop(client):
    now = datetime.now(timezone.utc)
    with _factory()() as session:
        run = _make_run(session, "running", started_at=now, status_version=3)
        run_id = run.id
        version = run.status_version

    resp = _cancel(client, run_id, expected_version=version)
    assert resp.status_code == 200
    body = resp.json()
    assert body["previous_status"] == "running"
    assert body["current_status"] == "cancellation_requested"
    assert body["already_cancelled"] is False
    assert body["already_requested"] is False
    assert body["cannot_cancel"] is False
    assert "停止" in body["message"]

    with _factory()() as session:
        refreshed = session.get(AnalysisRun, run_id)
        assert refreshed is not None
        assert refreshed.status == "cancellation_requested"
        assert refreshed.cancellation_requested_at is not None
        assert refreshed.cancelled_at is None
        assert refreshed.status_version == version + 1


def test_awaiting_provider_recovery_cancel_finalizes_immediately(client):
    with _factory()() as session:
        run = _make_run(
            session,
            "awaiting_provider_recovery",
            started_at=datetime.now(timezone.utc),
        )
        run_id = run.id

    resp = _cancel(client, run_id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_status"] == "cancelled"
    assert body["already_cancelled"] is True
    assert body["previous_status"] == "awaiting_provider_recovery"

    with _factory()() as session:
        refreshed = session.get(AnalysisRun, run_id)
        assert refreshed is not None
        assert refreshed.status == "cancelled"
        assert refreshed.cancelled_at is not None


def test_succeeded_cannot_cancel(client):
    with _factory()() as session:
        run = _make_run(session, "succeeded", started_at=datetime.now(timezone.utc))
        run.completed_at = datetime.now(timezone.utc)
        session.commit()
        run_id = run.id

    resp = _cancel(client, run_id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["cannot_cancel"] is True
    assert body["already_completed"] is True
    assert body["current_status"] == "succeeded"

    with _factory()() as session:
        refreshed = session.get(AnalysisRun, run_id)
        assert refreshed is not None
        assert refreshed.status == "succeeded"


def test_failed_cannot_cancel(client):
    with _factory()() as session:
        run = _make_run(session, "failed", started_at=datetime.now(timezone.utc))
        run.error_code = "PROVIDER_ERROR"
        session.commit()
        run_id = run.id

    resp = _cancel(client, run_id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["cannot_cancel"] is True
    assert body["already_completed"] is False
    assert body["current_status"] == "failed"

    with _factory()() as session:
        refreshed = session.get(AnalysisRun, run_id)
        assert refreshed is not None
        assert refreshed.status == "failed"
        assert refreshed.error_code == "PROVIDER_ERROR"


def test_cancelled_repeat_is_idempotent(client):
    with _factory()() as session:
        run = _make_run(session, "queued", set_started=False)
        run_id = run.id

    first = _cancel(client, run_id)
    assert first.status_code == 200
    assert first.json()["current_status"] == "cancelled"

    with _factory()() as session:
        refreshed = session.get(AnalysisRun, run_id)
        assert refreshed is not None
        cancelled_at = refreshed.cancelled_at
        status_version = refreshed.status_version

    second = _cancel(client, run_id)
    assert second.status_code == 200
    body = second.json()
    assert body["already_cancelled"] is True
    assert body["already_requested"] is True
    assert body["current_status"] == "cancelled"

    with _factory()() as session:
        refreshed = session.get(AnalysisRun, run_id)
        assert refreshed is not None
        assert refreshed.status == "cancelled"
        assert refreshed.cancelled_at == cancelled_at
        assert refreshed.status_version == status_version


def test_missing_run_returns_404(client):
    resp = _cancel(client, 9_999_999)
    assert resp.status_code == 404
    body = resp.json()
    detail = body.get("detail", body)
    assert detail.get("error_code") == "ANALYSIS_RUN_NOT_FOUND"
    _assert_no_raw_stack(body)


def test_version_conflict_returns_409(client):
    with _factory()() as session:
        run = _make_run(session, "queued", status_version=5, set_started=False)
        run_id = run.id

    resp = _cancel(client, run_id, expected_version=1)
    assert resp.status_code == 409
    body = resp.json()
    detail = body.get("detail", body)
    assert detail.get("error_code") == "ANALYSIS_RUN_VERSION_CONFLICT"
    _assert_no_raw_stack(body)

    with _factory()() as session:
        refreshed = session.get(AnalysisRun, run_id)
        assert refreshed is not None
        assert refreshed.status == "queued"
        assert refreshed.status_version == 5


def test_cancel_error_response_has_no_raw_stack(client):
    resp = _cancel(client, 42_424_242, expected_version=0)
    assert resp.status_code == 404
    _assert_no_raw_stack(resp.json())

    with _factory()() as session:
        run = _make_run(session, "running", started_at=datetime.now(timezone.utc), status_version=2)
        run_id = run.id

    conflict = _cancel(client, run_id, expected_version=99)
    assert conflict.status_code == 409
    _assert_no_raw_stack(conflict.json())


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_migration_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cancel_migrate.db'}")
    Base.metadata.create_all(engine)
    migrate_phase_task_cancellation_v1(engine)
    migrate_phase_task_cancellation_v1(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("analysis_runs")}
    assert "status_version" in cols
    assert "cancellation_requested_at" in cols
    assert "cancelled_at" in cols
    assert "cancellation_reason" in cols
    assert "cancelled_by" in cols
    engine.dispose()


def test_migration_adds_columns_on_legacy_table(tmp_path):
    """Simulate pre-CHG-006 schema: analysis_runs without cancel columns."""
    db_path = tmp_path / "legacy_cancel.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE analysis_runs (
                    id INTEGER PRIMARY KEY,
                    task_type VARCHAR(100),
                    subject_type VARCHAR(50),
                    subject_id VARCHAR(100),
                    provider VARCHAR(100),
                    model VARCHAR(255),
                    prompt_version VARCHAR(50),
                    schema_version VARCHAR(50),
                    input_hash VARCHAR(64),
                    status VARCHAR(32)
                )
                """
            )
        )
    migrate_phase_task_cancellation_v1(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("analysis_runs")}
    for name in (
        "status_version",
        "cancellation_requested_at",
        "cancelled_at",
        "cancellation_reason",
        "cancelled_by",
    ):
        assert name in cols
    migrate_phase_task_cancellation_v1(engine)  # second pass no-op
    engine.dispose()


# ---------------------------------------------------------------------------
# Worker checkpoints / service-level
# ---------------------------------------------------------------------------


def test_raise_if_cancel_requested_after_request(testing_session):
    run = _make_run(
        testing_session,
        "running",
        started_at=datetime.now(timezone.utc),
        status_version=0,
    )
    result = request_cancel(testing_session, run.id)
    assert result.current_status == "cancellation_requested"

    with pytest.raises(AnalysisCancellationRequested) as exc:
        raise_if_cancel_requested(testing_session, run.id)
    assert exc.value.run_id == run.id


def test_try_finalize_if_cancel_requested_ends_cancelled(testing_session):
    run = _make_run(
        testing_session,
        "running",
        started_at=datetime.now(timezone.utc),
    )
    request_cancel(testing_session, run.id)
    testing_session.refresh(run)
    assert run.status == "cancellation_requested"

    asserted = try_finalize_if_cancel_requested(testing_session, run.id)
    assert asserted is True
    testing_session.refresh(run)
    assert run.status == "cancelled"
    assert run.cancelled_at is not None
    assert run.error_code == "USER_CANCELLED"


def test_raise_if_cancel_requested_skips_terminal_success(testing_session):
    run = _make_run(testing_session, "succeeded", started_at=datetime.now(timezone.utc))
    raise_if_cancel_requested(testing_session, run.id)  # must not raise


def test_in_flight_checkpoint_before_provider_style(testing_session, fake_provider: FakeProvider):
    """Service-level: cancel flag observed before any provider invoke."""
    run = _make_run(
        testing_session,
        "running",
        started_at=datetime.now(timezone.utc),
    )
    request_cancel(testing_session, run.id)
    assert fake_provider.calls == 0
    with pytest.raises(AnalysisCancellationRequested):
        raise_if_cancel_requested(testing_session, run.id)
    assert fake_provider.calls == 0
    assert try_finalize_if_cancel_requested(testing_session, run.id) is True
    testing_session.refresh(run)
    assert run.status == "cancelled"
    assert fake_provider.calls == 0


# ---------------------------------------------------------------------------
# Reservation release
# ---------------------------------------------------------------------------


def test_cancel_releases_active_reservation_without_double_release(client):
    with _factory()() as session:
        run = _make_run(session, "queued", set_started=False)
        reservation = _make_reservation(session, run_id=run.id, remaining_cost=0.25)
        run_id = run.id
        reservation_id = reservation.id

    resp = _cancel(client, run_id)
    assert resp.status_code == 200
    assert resp.json()["current_status"] == "cancelled"

    with _factory()() as session:
        reservation = session.get(CloudBudgetReservation, reservation_id)
        assert reservation is not None
        assert reservation.status == "released"
        assert reservation.remaining_cost == 0.0
        assert reservation.released_cost == 0.25
        released_cost = reservation.released_cost
        released_at = reservation.released_at

    # Second cancel must not bump released ledger again.
    second = _cancel(client, run_id)
    assert second.status_code == 200
    assert second.json()["already_cancelled"] is True

    with _factory()() as session:
        reservation = session.get(CloudBudgetReservation, reservation_id)
        assert reservation is not None
        assert reservation.status == "released"
        assert reservation.remaining_cost == 0.0
        assert reservation.released_cost == released_cost
        assert reservation.released_at == released_at


def test_running_cancel_then_finalize_releases_reservation(testing_session):
    run = _make_run(
        testing_session,
        "running",
        started_at=datetime.now(timezone.utc),
    )
    reservation = _make_reservation(testing_session, run_id=run.id, remaining_cost=0.08)
    request_cancel(testing_session, run.id)
    testing_session.refresh(reservation)
    # Cooperative request path does not release until finalize.
    assert reservation.status == "active"

    finalize_cancelled(testing_session, run, commit=True)
    testing_session.refresh(reservation)
    testing_session.refresh(run)
    assert run.status == "cancelled"
    assert reservation.status == "released"
    assert reservation.remaining_cost == 0.0
    assert reservation.released_cost == 0.08

    # Idempotent finalize must not double-release.
    finalize_cancelled(testing_session, run, commit=True)
    testing_session.refresh(reservation)
    assert reservation.released_cost == 0.08
    assert reservation.remaining_cost == 0.0


# ---------------------------------------------------------------------------
# Race with success
# ---------------------------------------------------------------------------


def test_race_succeed_then_cancel_stays_succeeded(client):
    with _factory()() as session:
        run = _make_run(session, "running", started_at=datetime.now(timezone.utc))
        run.status = "succeeded"
        run.completed_at = datetime.now(timezone.utc)
        session.commit()
        run_id = run.id

    resp = _cancel(client, run_id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["already_completed"] is True
    assert body["cannot_cancel"] is True
    assert body["current_status"] == "succeeded"

    with _factory()() as session:
        refreshed = session.get(AnalysisRun, run_id)
        assert refreshed is not None
        assert refreshed.status == "succeeded"
        assert refreshed.cancelled_at is None


# ---------------------------------------------------------------------------
# Startup recovery
# ---------------------------------------------------------------------------


def test_startup_finalizes_cancellation_requested_and_stopping(testing_session):
    req = _make_run(
        testing_session,
        "cancellation_requested",
        subject_id="10",
        started_at=datetime.now(timezone.utc),
    )
    req.cancellation_requested_at = datetime.now(timezone.utc)
    req.cancellation_reason = "user_requested"
    stopping = _make_run(
        testing_session,
        "stopping",
        subject_id="11",
        started_at=datetime.now(timezone.utc),
    )
    stopping.cancellation_requested_at = datetime.now(timezone.utc)
    reservation = _make_reservation(testing_session, run_id=req.id, remaining_cost=0.03)
    testing_session.commit()

    stats = mark_interrupted_runs_failed(testing_session)
    testing_session.refresh(req)
    testing_session.refresh(stopping)
    testing_session.refresh(reservation)

    assert req.status == "cancelled"
    assert stopping.status == "cancelled"
    assert req.cancelled_at is not None
    assert stopping.cancelled_at is not None
    assert reservation.status == "released"
    assert stats["failed_runs"] >= 2

    # Idempotent second pass — already cancelled runs are not re-mutated.
    second = mark_interrupted_runs_failed(testing_session)
    testing_session.refresh(req)
    testing_session.refresh(stopping)
    assert req.status == "cancelled"
    assert stopping.status == "cancelled"
    assert second["failed_runs"] == 0
