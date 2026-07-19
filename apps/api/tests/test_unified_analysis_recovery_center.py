# -*- coding: utf-8 -*-
"""Phase 1D-C1-UAT-12: Unified Analysis Recovery Center."""

from __future__ import annotations

import json

from sqlalchemy import func, select

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    ApplicationSetting,
    Book,
    Chapter,
    ModelInvocation,
    Paragraph,
    ProviderConfiguration,
    ReaderJourneyRun,
)
from app.db.session import get_db
from app.model_gateway.registry import get_model_gateway
from app.schemas.settings import CloudBudgetUpdate
from app.services.provider_eligibility import evaluate_manual_boundary_candidate
from app.services.credentials.service import get_credential_store
from app.services.run_scoped_budget_auth import load_run_budget_auth
from app.services.scene_analysis_progress import load_revision_scenes
from pathlib import Path
from tests.test_phase_1c_a10 import _enable_cloud, _scene_payload, _seed_confirmed_run


def _set_budget(session, *, requests: int = 50, tokens: int = 2_000_000, cost: float = 50.0):
    payload = CloudBudgetUpdate().model_dump()
    payload["cloud_daily_request_limit"] = requests
    payload["cloud_daily_token_limit"] = tokens
    payload["cloud_daily_estimated_cost_limit"] = cost
    session.merge(
        ApplicationSetting(key="cloud_budget_settings", value_json=json.dumps(payload))
    )
    session.merge(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True)))
    session.commit()


def _complete_all_scenes(session, run: AnalysisRun, paragraphs) -> None:
    _rev, scenes = load_revision_scenes(session, run)
    for scene in scenes:
        art = AnalysisArtifact(
            run_id=run.id,
            artifact_type="scene_analysis",
            subject_type="scene",
            subject_id=str(scene.id),
            schema_version="v1",
            prompt_version="v1",
            payload_json=_scene_payload(scene, paragraphs),
            confidence=0.9,
            validation_status="valid",
        )
        session.add(art)
        session.flush()
        session.add(
            AnalysisEvidence(
                artifact_id=art.id,
                field_path="goal.evidence",
                paragraph_id=scene.start_paragraph_id,
                paragraph_hash="e" * 64,
            )
        )
    run.status = "succeeded"
    run.error_code = None
    run.failed_stage = None
    session.commit()


def _disconnect_provider(session, name: str = "fake") -> None:
    row = session.scalar(
        select(ProviderConfiguration).where(ProviderConfiguration.provider_name == name)
    )
    if row is None:
        row = ProviderConfiguration(provider_name=name, enabled=True, disconnected=True)
        session.add(row)
    else:
        row.disconnected = True
        row.enabled = True
    session.commit()


def _db(client):
    gen = client.app.dependency_overrides[get_db]()
    session = next(gen)
    return gen, session


def _close(gen):
    try:
        next(gen)
    except StopIteration:
        pass


def test_recovery_plan_returns_budget_and_provider_blockers_together(client):
    gen, session = _db(client)
    try:
        _enable_cloud(session)
        _set_budget(session, requests=2)
        _book, _ch, run, _revw, _rev, _scenes, _paras = _seed_confirmed_run(
            session, scene_count=5
        )
        run.status = "boundary_confirmed_budget_blocked"
        run.error_code = "INSUFFICIENT_BUDGET_RESERVATION"
        run.failed_stage = "scene_analysis_budget"
        run.provider = "fake"
        session.commit()
        _disconnect_provider(session, "fake")
        run_id = run.id
    finally:
        _close(gen)

    plan = client.get(f"/api/v1/analysis-runs/{run_id}/recovery-plan").json()
    reasons = {b["reason"] for b in plan["blockers"]}
    assert "request_budget_insufficient" in reasons
    assert "provider_disconnected" in reasons
    assert plan["user_status"] == "paused_recoverable"
    assert plan["recoverable"] is True
    assert len(plan["blockers"]) >= 2
    check_ids = {c["id"] for c in plan["checks"]}
    assert "request_budget" in check_ids
    assert "provider_connection" in check_ids


def test_recover_reconnect_and_run_temp_budget_idempotent(client):
    gen, session = _db(client)
    try:
        _enable_cloud(session)
        _set_budget(session, requests=5)
        _book, _ch, run, _revw, _rev, _scenes, _paras = _seed_confirmed_run(
            session, scene_count=3
        )
        run.status = "boundary_confirmed_budget_blocked"
        run.error_code = "INSUFFICIENT_BUDGET_RESERVATION"
        run.failed_stage = "scene_analysis_budget"
        run.retryable = True
        session.commit()
        _disconnect_provider(session, "fake")
        run_id = run.id
        before_runs = session.scalar(select(func.count()).select_from(AnalysisRun))
    finally:
        _close(gen)

    body = {
        "recovery_mode": "unified",
        "client_request_id": "recover-uat12-0001",
        "cloud_consent": True,
        "confirmed": True,
        "resume": False,
        "authorize_budget": {
            "scope": "run_temporary",
            "extra_requests": 40,
            "extra_tokens": 0,
            "extra_cost": 0,
        },
    }
    gen, session = _db(client)
    try:
        before_limit = json.loads(
            session.get(ApplicationSetting, "cloud_budget_settings").value_json
        )["cloud_daily_request_limit"]
    finally:
        _close(gen)

    r1 = client.post(f"/api/v1/analysis-runs/{run_id}/recover", json=body)
    assert r1.status_code == 202, r1.text
    data1 = r1.json()
    assert "provider_reconnect" in data1["actions_executed"]
    assert "run_temporary_request_allowance" in data1["actions_executed"]
    assert "run_temporary_budget_authorization" in data1["actions_executed"]
    assert data1["http_request_sent"] is False
    assert data1["model_invocations_started"] is False

    r2 = client.post(f"/api/v1/analysis-runs/{run_id}/recover", json=body)
    assert r2.status_code == 202
    assert r2.json()["idempotent_replay"] is True

    gen, session = _db(client)
    try:
        after_runs = session.scalar(select(func.count()).select_from(AnalysisRun))
        assert after_runs == before_runs
        fresh = session.get(AnalysisRun, run_id)
        auth = load_run_budget_auth(fresh)
        assert auth is not None
        assert int(auth["extra_requests"]) >= 40
        assert auth.get("mutates_daily_request_limit") is False
        after_limit = json.loads(
            session.get(ApplicationSetting, "cloud_budget_settings").value_json
        )["cloud_daily_request_limit"]
        assert after_limit == before_limit
        row = session.scalar(
            select(ProviderConfiguration).where(
                ProviderConfiguration.provider_name == "fake"
            )
        )
        assert row is not None and row.disconnected is False
        plan = client.get(f"/api/v1/analysis-runs/{run_id}/recovery-plan").json()
        reasons = {b["reason"] for b in plan["blockers"]}
        assert "provider_disconnected" not in reasons
        assert "request_budget_insufficient" not in reasons
    finally:
        _close(gen)


def test_full_pipeline_preflight_advisory_surfaces_shortfall(client):
    gen, session = _db(client)
    try:
        _enable_cloud(session)
        _set_budget(session, requests=3)
        book = Book(title="PF", source_file_name="pf.txt", source_file_hash="d" * 64)
        session.add(book)
        session.flush()
        chapter = Chapter(
            book_id=book.id, chapter_index=1, title="第一章", section_type="chapter"
        )
        session.add(chapter)
        session.flush()
        for index in range(1, 21):
            session.add(
                Paragraph(
                    id=f"B0002-C0001-P{index:04d}",
                    book_id=book.id,
                    chapter_id=chapter.id,
                    paragraph_index=index,
                    raw_text=f"段落{index}" * 8,
                    normalized_text=f"段落{index}" * 8,
                    char_start=index * 10,
                    char_end=index * 10 + 8,
                )
            )
        session.merge(
            ProviderConfiguration(
                provider_name="fake", enabled=True, disconnected=False
            )
        )
        session.commit()
        chapter_id = chapter.id
        gateway = client.app.dependency_overrides[get_model_gateway]()
        provider = gateway.get("fake")
        evaluation = evaluate_manual_boundary_candidate(
            session,
            provider_name=provider.name,
            capabilities=provider.capabilities(),
            store=get_credential_store(),
            pricing_path=Path("config/cloud_pricing.json"),
        )
        state_version = evaluation["provider_state_version"]
    finally:
        _close(gen)

    resp = client.post(
        "/api/v1/analysis-runs/full-pipeline-preflight",
        json={
            "chapter_id": chapter_id,
            "provider": "fake",
            "execution_mode": "local",
            "analysis_mode": "assisted_boundary_review",
            "cloud_consent": True,
            "capability_schema_version": "1c-a-2",
            "provider_state_version": state_version,
        },
    )
    assert resp.status_code == 200, resp.text
    advisory = resp.json()
    assert advisory["full_worst_requests"] > advisory["remaining_requests"]
    assert advisory["within_budget"] is False


def test_succeeded_scenes_plan_awaiting_reader_journey_no_new_run(client):
    gen, session = _db(client)
    try:
        _enable_cloud(session)
        _set_budget(session, requests=500)
        _book, _ch, run, _revw, _rev, _scenes, paragraphs = _seed_confirmed_run(
            session, scene_count=2
        )
        _complete_all_scenes(session, run, paragraphs)
        run_id = run.id
        before = session.scalar(select(func.count()).select_from(AnalysisRun))
    finally:
        _close(gen)

    plan = client.get(f"/api/v1/analysis-runs/{run_id}/recovery-plan").json()
    assert plan["resume_stage"] == "reader_journey"
    assert "AnalysisRun" in plan["will_reuse_artifacts"]
    assert "SceneArtifacts" in plan["will_reuse_artifacts"]
    reasons = {b["reason"] for b in plan["blockers"]}
    assert "awaiting_reader_journey" in reasons

    body = {
        "recovery_mode": "unified",
        "client_request_id": "recover-uat12-journey-01",
        "cloud_consent": True,
        "confirmed": True,
        "resume": False,
    }
    r = client.post(f"/api/v1/analysis-runs/{run_id}/recover", json=body)
    assert r.status_code == 202
    assert r.json()["model_invocations_started"] is False
    assert r.json()["http_request_sent"] is False

    gen, session = _db(client)
    try:
        after = session.scalar(select(func.count()).select_from(AnalysisRun))
        assert after == before
        journeys = session.scalar(select(func.count()).select_from(ReaderJourneyRun))
        assert int(journeys or 0) == 0
        inv = session.scalar(select(func.count()).select_from(ModelInvocation))
        assert int(inv or 0) == 0
    finally:
        _close(gen)


def test_legacy_boundary_recover_still_works_without_recovery_mode(client):
    resp = client.post(
        "/api/v1/analysis-runs/999999/recover",
        json={
            "client_request_id": "legacy-recover-0001",
            "cloud_consent": True,
            "confirmed": True,
        },
    )
    assert resp.status_code == 404
