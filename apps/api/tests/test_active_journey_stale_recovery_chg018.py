"""CHG-20260730-018: active journey must not surface paused recovery plan."""

from __future__ import annotations

from app.db.models import ReaderJourneyRun
from app.model_gateway.registry import get_model_gateway
from app.services.analysis_recovery_center import (
    build_recovery_plan,
    execute_unified_recover,
)
from app.services.credentials.service import get_credential_store
from app.schemas.analysis_recovery import AnalysisRecoverRequest
from tests.test_phase_1c_a10 import _enable_cloud, _seed_confirmed_run
from tests.test_unified_analysis_recovery_center import _complete_all_scenes, _set_budget


def _add_journey(session, run, book, chapter, *, status: str, **extra) -> ReaderJourneyRun:
    journey = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status=status,
        current_stage=status,
        provider_name=run.provider,
        model_name=run.model,
        formula_version="v1",
        scene_contract_version="2.0",
        client_request_id=extra.pop("client_request_id", f"chg018-{status}-{run.id}"),
        cloud_consent=True,
        **extra,
    )
    session.add(journey)
    session.flush()
    return journey


def test_recovery_plan_running_when_journey_starting(testing_session):
    _enable_cloud(testing_session)
    _set_budget(testing_session)
    book, chapter, run, _revw, _rev, _scenes, paragraphs = _seed_confirmed_run(
        testing_session
    )
    _complete_all_scenes(testing_session, run, paragraphs)
    _add_journey(
        testing_session, run, book, chapter, status="starting", client_request_id="chg018-start"
    )
    testing_session.commit()

    gateway = get_model_gateway()
    store = get_credential_store()
    plan = build_recovery_plan(testing_session, run, gateway, store)
    assert plan.user_status == "running"
    assert plan.recoverable is False
    assert plan.pause_reason is None
    assert plan.reader_journey_status == "starting"
    assert not any(b.code == "AWAITING_READER_JOURNEY" for b in plan.blockers)


def test_recovery_plan_prefers_active_over_old_interrupted(testing_session):
    _enable_cloud(testing_session)
    _set_budget(testing_session)
    book, chapter, run, _revw, _rev, _scenes, paragraphs = _seed_confirmed_run(
        testing_session
    )
    _complete_all_scenes(testing_session, run, paragraphs)
    _add_journey(
        testing_session,
        run,
        book,
        chapter,
        status="scene_profiles_partial",
        client_request_id="chg018-old",
        retryable=True,
        root_error_code="JOURNEY_INTERRUPTED",
    )
    active = _add_journey(
        testing_session,
        run,
        book,
        chapter,
        status="running",
        client_request_id="chg018-active",
    )
    testing_session.commit()

    gateway = get_model_gateway()
    store = get_credential_store()
    plan = build_recovery_plan(testing_session, run, gateway, store)
    assert plan.user_status == "running"
    assert plan.reader_journey_run_id == active.id
    assert plan.reader_journey_status == "running"


def test_recover_noop_when_journey_already_active(testing_session):
    _enable_cloud(testing_session)
    _set_budget(testing_session)
    book, chapter, run, _revw, _rev, _scenes, paragraphs = _seed_confirmed_run(
        testing_session
    )
    _complete_all_scenes(testing_session, run, paragraphs)
    _add_journey(
        testing_session,
        run,
        book,
        chapter,
        status="scene_profiles_running",
        client_request_id="chg018-running",
    )
    testing_session.commit()

    gateway = get_model_gateway()
    store = get_credential_store()
    result = execute_unified_recover(
        testing_session,
        run,
        AnalysisRecoverRequest(
            client_request_id="chg018-noop-1",
            cloud_consent=True,
            confirmed=True,
            recovery_mode="unified",
            resume=True,
        ),
        gateway,
        store,
    )
    assert result.user_status == "running"
    assert result.idempotent_replay is True
    assert "noop_journey_already_active" in result.actions_executed
    assert result.http_request_sent is False
