"""Startup stale-run recovery (CHG-20260726-010 / FIX-RUN-01)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import AnalysisRun, CloudBudgetReservation
from app.services.scene_pipeline import mark_interrupted_runs_failed


def _make_run(session, status: str, *, subject_id: str = "1") -> AnalysisRun:
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=subject_id,
        provider="fake",
        model="fake",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash="a" * 64,
        status=status,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _make_reservation(
    session,
    *,
    run_id: int | None,
    status: str = "active",
    remaining_cost: float = 0.1,
    expires_in_minutes: int = 30,
) -> CloudBudgetReservation:
    now = datetime.now(timezone.utc)
    reserved = remaining_cost
    row = CloudBudgetReservation(
        run_id=run_id,
        stage="boundary_review_generation",
        reserved_requests=10,
        reserved_tokens=1000,
        reserved_cost=reserved,
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
        expires_at=now + timedelta(minutes=expires_in_minutes),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_boundary_candidates_running_recovers_and_releases_reservation(testing_session) -> None:
    run = _make_run(testing_session, "boundary_candidates_running")
    reservation = _make_reservation(testing_session, run_id=run.id, remaining_cost=0.05)

    stats = mark_interrupted_runs_failed(testing_session)
    testing_session.refresh(run)
    testing_session.refresh(reservation)

    assert stats["failed_runs"] == 1
    assert run.status == "failed"
    assert run.error_code == "PROCESS_INTERRUPTED"
    assert run.completed_at is not None
    assert reservation.status == "released"
    assert reservation.remaining_cost == 0.0
    assert reservation.released_cost == 0.05


def test_recovery_idempotent_second_pass(testing_session) -> None:
    run = _make_run(testing_session, "boundary_candidates_running")
    reservation = _make_reservation(testing_session, run_id=run.id)

    first = mark_interrupted_runs_failed(testing_session)
    testing_session.refresh(run)
    testing_session.refresh(reservation)
    completed_at = run.completed_at
    released_at = reservation.released_at
    assert first["failed_runs"] == 1
    assert first["released_reservations"] == 1

    second = mark_interrupted_runs_failed(testing_session)
    testing_session.refresh(run)
    testing_session.refresh(reservation)
    assert second["failed_runs"] == 0
    assert second["released_reservations"] == 0
    assert run.status == "failed"
    assert run.completed_at == completed_at
    assert reservation.status == "released"
    assert reservation.released_at == released_at
    assert testing_session.scalar(select(AnalysisRun.id).order_by(AnalysisRun.id.desc())) == run.id


def test_terminal_statuses_untouched(testing_session) -> None:
    rows = [
        _make_run(testing_session, status, subject_id=str(i))
        for i, status in enumerate(
            ("succeeded", "failed", "failed_provider", "cancelled"), start=1
        )
    ]
    for row in rows:
        row.error_code = "KEEP_ME"
        row.error_message = "stable"
    testing_session.commit()

    stats = mark_interrupted_runs_failed(testing_session)
    assert stats["failed_runs"] == 0
    for row in rows:
        testing_session.refresh(row)
        assert row.error_code == "KEEP_ME"
        assert row.status in {"succeeded", "failed", "failed_provider", "cancelled"}


def test_user_wait_status_not_killed(testing_session) -> None:
    """awaiting_boundary_review has no worker — must survive startup recovery."""
    run = _make_run(testing_session, "awaiting_boundary_review")
    reservation = _make_reservation(testing_session, run_id=run.id)

    stats = mark_interrupted_runs_failed(testing_session)
    testing_session.refresh(run)
    testing_session.refresh(reservation)
    assert stats["failed_runs"] == 0
    assert run.status == "awaiting_boundary_review"
    assert run.error_code is None
    assert reservation.status == "active"


def test_orphan_and_expired_reservations_released(testing_session) -> None:
    orphan = _make_reservation(testing_session, run_id=None)
    expired = _make_reservation(testing_session, run_id=None, expires_in_minutes=-10)
    expired.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    testing_session.commit()

    stats = mark_interrupted_runs_failed(testing_session)
    testing_session.refresh(orphan)
    testing_session.refresh(expired)
    assert stats["released_reservations"] >= 2
    assert orphan.status == "released"
    assert expired.status == "released"


def test_create_run_after_recovery_with_fake(client) -> None:
    """Fake Create Run returns run_id quickly (real Provider calls = 0)."""
    content = "第一章\n\n第一段内容足够长用于导入。\n\n第二段内容继续。"
    imported = client.post(
        "/api/v1/books/import",
        files={"file": ("recover.txt", content.encode("utf-8"), "text/plain")},
    )
    assert imported.status_code in {200, 201}, imported.text
    book_id = imported.json()["book_id"]
    chapters = client.get(f"/api/v1/books/{book_id}/chapters").json()
    chapter_id = chapters[0]["id"]

    created = client.post(
        f"/api/v1/chapters/{chapter_id}/analysis-runs",
        json={"provider_name": "fake", "force": True},
    )
    assert created.status_code in {200, 201, 202}, created.text
    body = created.json()
    assert "run_id" in body
    assert body["run_id"] > 0
