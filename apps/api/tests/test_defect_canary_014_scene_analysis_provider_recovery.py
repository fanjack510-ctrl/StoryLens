# -*- coding: utf-8 -*-
"""DEFECT-CANARY-014: Scene Analysis provider recovery + circuit breaker (v1.0.9)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    ApplicationSetting,
    CloudBudgetReservation,
    ModelInvocation,
    ProviderConfiguration,
    Scene,
)
from app.model_gateway.base import ProviderCapabilities, ProviderRequestError
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.provider_errors import TRANSPORT_AUTH, TRANSPORT_REMOTE_DISCONNECT
from app.schemas.settings import CloudBudgetUpdate
from app.services.boundary_review_service import analyze_confirmed_review
from app.services.reader_journey_progress import require_completed_scene_analysis
from app.services.scene_analysis_progress import is_scene_analysis_complete, scene_analysis_progress
from app.services.scene_analysis_provider_recovery import (
    STATUS_AWAITING_PROVIDER_RECOVERY,
    is_provider_transport_recoverable,
    load_recovery_state,
)
from app.services.staged_budget import STAGE_ANALYSIS
from app.services.structured_output import StructuredOutputError
from app.services.validation_errors import StructuralValidationError
from tests.optional_gates import require_main_db_cert_counts
from tests.test_aliyun_provider import CloudFake
from tests.test_phase_1c_a10 import _scene_payload, _seed_confirmed_run

pytestmark = [
    pytest.mark.canary_offline,
    pytest.mark.requires_audit_assets,
]

ROOT = Path(__file__).resolve().parents[3]
MAIN_DB = ROOT / "data" / "storylens.db"


class RecoveryCloudFake(CloudFake):
    """Cloud fake with scene_analysis capability + api_key for eligibility."""

    def __init__(self, name: str, responses=None):
        super().__init__(name, responses=responses)
        self.api_key = "test-key-not-secret"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            max_context_tokens=32768,
            default_timeout_seconds=300,
            enabled=True,
            profile_name=self.name,
            structured_output_mode="json_object",
            supports_json_object=True,
            supports_thinking_control=True,
            cloud=True,
            provider_family="aliyun_qwen",
            sends_content_to_cloud=True,
            region="cn-beijing",
            supports_scene_analysis=True,
            supports_boundary_candidates=True,
            requires_boundary_review=True,
        )


def _enable_cloud_runtime(session) -> None:
    session.merge(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True)))
    payload = CloudBudgetUpdate().model_dump()
    payload.update(
        {
            "daily_request_limit": 5000,
            "daily_token_limit": 20_000_000,
            "daily_cost_limit": 500.0,
        }
    )
    session.merge(
        ApplicationSetting(key="cloud_budget_settings", value_json=json.dumps(payload))
    )
    session.merge(
        ProviderConfiguration(
            provider_name="aliyun_qwen_plus",
            display_name="plus",
            region="cn-beijing",
            base_url="https://example.invalid/v1",
            plus_model="qwen3.7-plus",
            enabled=True,
            disconnected=False,
            allow_auto_route=False,
            credential_reference="keyring:aliyun_qwen_plus",
        )
    )
    session.commit()


def _disconnect() -> ProviderRequestError:
    return ProviderRequestError(
        "Server disconnected without sending a response.",
        http_request_sent=True,
        error_code="PROVIDER_REMOTE_DISCONNECT",
        transport_kind=TRANSPORT_REMOTE_DISCONNECT,
        retryable=True,
        exception_type="RemoteProtocolError",
    )


def _auth_error(status: int = 401) -> ProviderRequestError:
    return ProviderRequestError(
        f"HTTP {status}",
        status,
        http_request_sent=True,
        error_code="PROVIDER_AUTH_ERROR" if status in {401, 403} else f"PROVIDER_HTTP_{status}",
        transport_kind=TRANSPORT_AUTH,
        retryable=False,
        exception_type="HTTPStatusError",
    )


def _session_factory(testing_session):
    return sessionmaker(
        bind=testing_session.get_bind(), autoflush=False, expire_on_commit=False
    )


def _zero_transport_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_1_MIN", "0")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_1_MAX", "0")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_2_MIN", "0")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_2_MAX", "0")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("STORYLENS_ALIYUN_MAX_RETRIES", "3")
    monkeypatch.setenv("STORYLENS_SCENE_ANALYSIS_RECOVERY_COOLDOWN_SECONDS", "0.01")
    monkeypatch.setenv("STORYLENS_SCENE_ANALYSIS_RECOVERY_MAX_CYCLES", "3")
    get_settings.cache_clear()


def _seed_reservation(session, run_id: int) -> CloudBudgetReservation:
    row = CloudBudgetReservation(
        run_id=run_id,
        stage=STAGE_ANALYSIS,
        reserved_requests=10,
        reserved_tokens=100000,
        reserved_cost=1.0,
        remaining_requests=10,
        consumed_requests=0,
        released_requests=0,
        remaining_tokens=100000,
        consumed_tokens=0,
        released_tokens=0,
        remaining_cost=1.0,
        consumed_cost=0.0,
        released_cost=0.0,
        expected_requests=3,
        worst_case_requests=10,
        status="active",
        expires_at=datetime.now(timezone.utc).replace(year=2099),
    )
    session.add(row)
    session.commit()
    return row


def _main_db_fingerprint() -> tuple[int, int]:
    con = sqlite3.connect(f"file:{MAIN_DB.as_posix()}?mode=ro", uri=True)
    try:
        runs = con.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0]
        journeys = con.execute("SELECT COUNT(*) FROM reader_journey_runs").fetchone()[0]
        return int(runs), int(journeys)
    finally:
        con.close()


@pytest.fixture
def recovery_settings(monkeypatch: pytest.MonkeyPatch, verified_cloud_pricing):
    _zero_transport_delay(monkeypatch)
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_1_to_7_partial_disconnect_recovers_third_scene_only(
    testing_session, recovery_settings, monkeypatch
):
    """Scenes 1–2 succeed; scene 3 exhausts 3 disconnects → pause → recover → journey-ready."""
    _enable_cloud_runtime(testing_session)
    _book, _ch, run, review, _rev, scenes, paragraphs = _seed_confirmed_run(
        testing_session, scene_count=3
    )
    run.provider = "aliyun_qwen_plus"
    run.model = "qwen3.7-plus"
    run.sends_content_to_cloud = True
    testing_session.commit()
    _seed_reservation(testing_session, run.id)

    ok1 = _scene_payload(scenes[0], paragraphs)
    ok2 = _scene_payload(scenes[1], paragraphs)
    ok3 = _scene_payload(scenes[2], paragraphs)
    cloud = RecoveryCloudFake(
        "aliyun_qwen_plus",
        responses=[ok1, ok2, _disconnect(), _disconnect(), _disconnect(), ok3],
    )
    gateway = ModelGateway([cloud])
    factory = _session_factory(testing_session)

    paused_statuses: list[str] = []
    observed_pending_during_pause: list[list[int]] = []

    async def _sleep(delay: float) -> None:
        testing_session.expire_all()
        with factory() as snap:
            row = snap.get(AnalysisRun, run.id)
            paused_statuses.append(row.status)
            state = load_recovery_state(row)
            observed_pending_during_pause.append(list(state.get("pending_scene_ids") or []))
            assert row.status == STATUS_AWAITING_PROVIDER_RECOVERY
            assert row.root_error_code == "PROVIDER_REMOTE_DISCONNECT"
            assert row.status != "succeeded"
            progress = scene_analysis_progress(snap, row)
            assert progress.completed_scene_count == 2
            assert progress.remaining_scene_count == 1
            assert is_scene_analysis_complete(snap, run.id, scenes[0])
            assert is_scene_analysis_complete(snap, run.id, scenes[1])
            assert not is_scene_analysis_complete(snap, run.id, scenes[2])
            assert len(state.get("recovery_audits") or []) == 1

    monkeypatch.setattr("asyncio.sleep", _sleep)

    before_fp = _main_db_fingerprint()
    await analyze_confirmed_review(factory, gateway, review.id)
    testing_session.expire_all()

    run = testing_session.get(AnalysisRun, run.id)
    assert run.status == "succeeded"
    assert paused_statuses == [STATUS_AWAITING_PROVIDER_RECOVERY]
    assert observed_pending_during_pause == [[scenes[2].id]]

    # First two scenes produce no extra model requests after completion.
    assert cloud.calls == 6

    artifacts = list(
        testing_session.scalars(
            select(AnalysisArtifact).where(
                AnalysisArtifact.run_id == run.id,
                AnalysisArtifact.artifact_type == "scene_analysis",
                AnalysisArtifact.validation_status == "valid",
            )
        )
    )
    assert len(artifacts) == 3
    subject_ids = sorted(int(a.subject_id) for a in artifacts)
    assert subject_ids == sorted(s.id for s in scenes)

    scene3_inv = list(
        testing_session.scalars(
            select(ModelInvocation)
            .where(
                ModelInvocation.run_id == run.id,
                ModelInvocation.task_type == "scene_analysis",
                ModelInvocation.status == "failed",
            )
            .order_by(ModelInvocation.id)
        )
    )
    assert len(scene3_inv) == 3
    hashes = {i.request_hash for i in scene3_inv}
    assert len(hashes) == 1

    active = testing_session.scalar(
        select(func.count())
        .select_from(CloudBudgetReservation)
        .where(
            CloudBudgetReservation.run_id == run.id,
            CloudBudgetReservation.status == "active",
        )
    )
    assert int(active or 0) == 0
    released = list(
        testing_session.scalars(
            select(CloudBudgetReservation).where(CloudBudgetReservation.run_id == run.id)
        )
    )
    assert len(released) == 1
    assert released[0].status == "released"

    require_completed_scene_analysis(testing_session, run, list(scenes))
    # Recovery must not mutate the operator main DB; counts are environment-specific.
    assert _main_db_fingerprint() == before_fp


@pytest.mark.asyncio
async def test_8_recovery_exhausted_terminates_with_remote_disconnect(
    testing_session, recovery_settings, monkeypatch
):
    monkeypatch.setenv("STORYLENS_SCENE_ANALYSIS_RECOVERY_MAX_CYCLES", "2")
    get_settings.cache_clear()

    _enable_cloud_runtime(testing_session)
    _book, _ch, run, review, _rev, scenes, paragraphs = _seed_confirmed_run(
        testing_session, scene_count=2
    )
    run.provider = "aliyun_qwen_plus"
    run.model = "qwen3.7-plus"
    run.sends_content_to_cloud = True
    testing_session.commit()

    ok1 = _scene_payload(scenes[0], paragraphs)
    responses: list[object] = [ok1]
    for _ in range(9):
        responses.append(_disconnect())
    cloud = RecoveryCloudFake("aliyun_qwen_plus", responses=responses)
    gateway = ModelGateway([cloud])
    factory = _session_factory(testing_session)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    with pytest.raises(StructuredOutputError) as excinfo:
        await analyze_confirmed_review(factory, gateway, review.id)

    assert excinfo.value.provider_error is not None
    assert excinfo.value.provider_error.error_code == "PROVIDER_REMOTE_DISCONNECT"

    testing_session.expire_all()
    run = testing_session.get(AnalysisRun, run.id)
    assert run.status == "scene_analysis_partial"
    assert run.root_error_code == "PROVIDER_REMOTE_DISCONNECT"
    failure = json.loads(run.raw_output or "{}")
    assert failure.get("provider_recovery_exhausted") is True
    assert failure.get("provider_recovery_stop_reason") == "max_recovery_cycles"
    assert is_scene_analysis_complete(testing_session, run.id, scenes[0])
    assert not is_scene_analysis_complete(testing_session, run.id, scenes[1])


@pytest.mark.asyncio
async def test_9_auth_and_contract_errors_not_recoverable(
    testing_session, recovery_settings, monkeypatch
):
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    _enable_cloud_runtime(testing_session)
    _book, _ch, run, review, _rev, scenes, paragraphs = _seed_confirmed_run(
        testing_session, scene_count=2
    )
    run.provider = "aliyun_qwen_plus"
    run.model = "qwen3.7-plus"
    run.sends_content_to_cloud = True
    testing_session.commit()
    ok1 = _scene_payload(scenes[0], paragraphs)
    cloud = RecoveryCloudFake("aliyun_qwen_plus", responses=[ok1, _auth_error(401)])
    factory = _session_factory(testing_session)
    with pytest.raises(Exception):
        await analyze_confirmed_review(factory, ModelGateway([cloud]), review.id)
    testing_session.expire_all()
    run = testing_session.get(AnalysisRun, run.id)
    assert run.status != STATUS_AWAITING_PROVIDER_RECOVERY
    assert run.root_error_code in {"PROVIDER_AUTH_ERROR", "PROVIDER_HTTP_401"}
    assert "provider_recovery" not in (run.raw_output or "")

    assert (
        is_provider_transport_recoverable(
            StructuralValidationError("bad", "BUSINESS_VALIDATION_FAILED")
        )
        is False
    )
    assert is_provider_transport_recoverable(_auth_error(403)) is False
    assert is_provider_transport_recoverable(_disconnect()) is True


def test_10_main_database_unchanged_55_2():
    require_main_db_cert_counts()
    assert _main_db_fingerprint() == (55, 2)


@pytest.mark.asyncio
async def test_no_duplicate_run_or_scene_on_recovery(
    testing_session, recovery_settings, monkeypatch
):
    _enable_cloud_runtime(testing_session)
    _book, _ch, run, review, _rev, scenes, paragraphs = _seed_confirmed_run(
        testing_session, scene_count=3
    )
    run.provider = "aliyun_qwen_plus"
    run.model = "qwen3.7-plus"
    run.sends_content_to_cloud = True
    testing_session.commit()
    run_id = run.id
    scene_ids = [s.id for s in scenes]

    ok = [_scene_payload(s, paragraphs) for s in scenes]
    cloud = RecoveryCloudFake(
        "aliyun_qwen_plus",
        responses=[ok[0], ok[1], _disconnect(), _disconnect(), _disconnect(), ok[2]],
    )
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    await analyze_confirmed_review(
        _session_factory(testing_session), ModelGateway([cloud]), review.id
    )
    testing_session.expire_all()

    runs = list(
        testing_session.scalars(select(AnalysisRun).where(AnalysisRun.id == run_id))
    )
    assert len(runs) == 1
    scenes_after = list(
        testing_session.scalars(select(Scene).where(Scene.id.in_(scene_ids)))
    )
    assert len(scenes_after) == 3
    evidence_count = testing_session.scalar(
        select(func.count()).select_from(AnalysisEvidence)
    )
    assert int(evidence_count or 0) > 0
