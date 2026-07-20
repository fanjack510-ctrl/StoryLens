# -*- coding: utf-8 -*-
"""DEFECT-CANARY-009: provider transport resilience (backoff/jitter, max 3 attempts)."""
from __future__ import annotations

import random
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text

from app.core.config import Settings, get_settings
from app.db.models import AnalysisRun, ModelInvocation
from app.model_gateway.base import ProviderRequestError
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.provider_errors import TRANSPORT_AUTH, TRANSPORT_REMOTE_DISCONNECT
from app.model_gateway.transport_retry import (
    TransportRetryPolicy,
    compute_provider_retry_delay_seconds,
    should_retry_provider_error,
)
from app.schemas.scene import SceneBoundaryResult
from app.services.prompt_service import load_prompt
from app.services.structured_output import StructuredOutputError, generate_validated
from tests.fakes import FakeProvider
from tests.optional_gates import require_main_db_cert_counts, require_path
from tests.test_aliyun_provider import CloudFake

pytestmark = [
    pytest.mark.canary_offline,
    pytest.mark.requires_audit_assets,
]

ROOT = Path(__file__).resolve().parents[3]
MAIN_DB = ROOT / "data" / "storylens.db"
CANARY_V5_DB = (
    ROOT
    / "artifacts"
    / "single-chapter-pipeline-certification"
    / "real-canary"
    / "canary-v5.sqlite3"
)
VALID = '{"chapter_id":"B0001-C0001","boundaries":[],"overall_confidence":0.9}'


def _disconnect() -> ProviderRequestError:
    return ProviderRequestError(
        "Server disconnected without sending a response.",
        http_request_sent=True,
        error_code="PROVIDER_REMOTE_DISCONNECT",
        transport_kind=TRANSPORT_REMOTE_DISCONNECT,
        retryable=True,
        exception_type="RemoteProtocolError",
    )


def _http_error(status: int, *, retryable: bool | None = None) -> ProviderRequestError:
    return ProviderRequestError(
        f"HTTP {status}",
        status,
        http_request_sent=True,
        transport_kind=TRANSPORT_AUTH if status in {401, 403} else "http_error",
        retryable=retryable,
        exception_type="HTTPStatusError",
    )


def make_run(session) -> AnalysisRun:
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id="1",
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="v1",
        schema_version="v1",
        prompt_hash="x",
        input_hash="x",
        status="running",
    )
    session.add(run)
    session.commit()
    return run


@pytest.fixture
def zero_delay_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_1_MIN", "0")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_1_MAX", "0")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_2_MIN", "0")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_2_MAX", "0")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("STORYLENS_ALIYUN_MAX_RETRIES", "3")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_1_first_disconnect_second_success(testing_session, zero_delay_settings, monkeypatch):
    sleeps: list[float] = []

    async def _sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", _sleep)
    # Restore non-zero delay ranges for assertion while keeping sleep mocked
    get_settings.cache_clear()
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_1_MIN", "2")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_1_MAX", "4")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_2_MIN", "8")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_2_MAX", "12")
    get_settings.cache_clear()

    provider = CloudFake("aliyun_qwen_plus", [_disconnect(), VALID])
    run = make_run(testing_session)
    result = await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary"),
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
        user_content="task",
        business_validator=lambda _: None,
    )
    assert result.boundaries == []
    rows = list(
        testing_session.scalars(
            select(ModelInvocation).where(ModelInvocation.run_id == run.id).order_by(ModelInvocation.id)
        )
    )
    assert len(rows) == 2
    assert rows[0].error_code == "PROVIDER_REMOTE_DISCONNECT"
    assert rows[0].status == "failed"
    assert rows[1].status == "succeeded"
    assert rows[0].request_hash == rows[1].request_hash
    assert len(sleeps) == 1
    assert 2.0 <= sleeps[0] <= 4.0


@pytest.mark.asyncio
async def test_2_two_disconnects_third_success(testing_session, monkeypatch):
    sleeps: list[float] = []

    async def _sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", _sleep)
    get_settings.cache_clear()
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_1_MIN", "2")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_1_MAX", "4")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_2_MIN", "8")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_2_MAX", "12")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("STORYLENS_ALIYUN_MAX_RETRIES", "3")
    get_settings.cache_clear()

    provider = CloudFake("aliyun_qwen_plus", [_disconnect(), _disconnect(), VALID])
    run = make_run(testing_session)
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary"),
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
        user_content="task",
        business_validator=lambda _: None,
    )
    rows = list(
        testing_session.scalars(
            select(ModelInvocation).where(ModelInvocation.run_id == run.id).order_by(ModelInvocation.id)
        )
    )
    assert [r.status for r in rows] == ["failed", "failed", "succeeded"]
    assert [r.attempt_no for r in rows] == [1, 2, 3]
    assert [r.invocation_kind for r in rows] == ["initial", "provider_retry", "provider_retry"]
    assert len({r.request_hash for r in rows}) == 1
    assert len(sleeps) == 2
    assert 2.0 <= sleeps[0] <= 4.0
    assert 8.0 <= sleeps[1] <= 12.0


@pytest.mark.asyncio
async def test_3_three_disconnects_final_failure(testing_session, zero_delay_settings, monkeypatch):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake("aliyun_qwen_plus", [_disconnect(), _disconnect(), _disconnect()])
    run = make_run(testing_session)
    with pytest.raises(StructuredOutputError) as exc:
        await generate_validated(
            session=testing_session,
            gateway=ModelGateway([provider]),
            run_id=run.id,
            provider_name=provider.name,
            task_type="scene_boundary",
            prompt=load_prompt("scene_boundary"),
            schema=SceneBoundaryResult,
            input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
            user_content="task",
            business_validator=lambda _: None,
        )
    assert exc.value.error_code == "PROVIDER_REMOTE_DISCONNECT"
    rows = list(
        testing_session.scalars(
            select(ModelInvocation).where(ModelInvocation.run_id == run.id).order_by(ModelInvocation.id)
        )
    )
    assert len(rows) == 3
    assert all(r.error_code == "PROVIDER_REMOTE_DISCONNECT" for r in rows)
    assert all(r.input_tokens is None and r.estimated_cost is None for r in rows)


def test_4_5_backoff_and_jitter_ranges():
    policy = TransportRetryPolicy()
    rng = random.Random(42)
    d1 = [compute_provider_retry_delay_seconds(1, policy, rng=rng) for _ in range(50)]
    d2 = [compute_provider_retry_delay_seconds(2, policy, rng=rng) for _ in range(50)]
    assert all(2.0 <= x <= 4.0 for x in d1)
    assert all(8.0 <= x <= 12.0 for x in d2)
    assert min(d1) < max(d1)  # jitter spreads
    assert min(d2) < max(d2)


@pytest.mark.asyncio
async def test_6_request_hash_three_consistent(testing_session, zero_delay_settings, monkeypatch):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake("aliyun_qwen_plus", [_disconnect(), _disconnect(), VALID])
    run = make_run(testing_session)
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary"),
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
        user_content="task",
        business_validator=lambda _: None,
    )
    hashes = list(
        testing_session.scalars(
            select(ModelInvocation.request_hash)
            .where(ModelInvocation.run_id == run.id)
            .order_by(ModelInvocation.id)
        )
    )
    assert len(hashes) == 3
    assert len(set(hashes)) == 1


@pytest.mark.asyncio
async def test_7_10_no_duplicate_entities(testing_session, zero_delay_settings, monkeypatch):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake("aliyun_qwen_plus", [_disconnect(), VALID])
    before_runs = testing_session.execute(text("SELECT COUNT(*) FROM analysis_runs")).scalar() or 0
    before_scenes = testing_session.execute(text("SELECT COUNT(*) FROM scenes")).scalar() or 0
    before_profiles = testing_session.execute(
        text("SELECT COUNT(*) FROM scene_reader_journey_profiles")
    ).scalar() or 0
    before_journeys = testing_session.execute(
        text("SELECT COUNT(*) FROM reader_journey_runs")
    ).scalar() or 0

    run = make_run(testing_session)
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary"),
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
        user_content="task",
        business_validator=lambda _: None,
    )
    run_count = testing_session.execute(text("SELECT COUNT(*) FROM analysis_runs")).scalar()
    scene_count = testing_session.execute(text("SELECT COUNT(*) FROM scenes")).scalar()
    profile_count = testing_session.execute(
        text("SELECT COUNT(*) FROM scene_reader_journey_profiles")
    ).scalar()
    journey_count = testing_session.execute(
        text("SELECT COUNT(*) FROM reader_journey_runs")
    ).scalar()
    assert run_count == before_runs + 1  # only the make_run we created
    assert scene_count == before_scenes
    assert profile_count == before_profiles
    assert journey_count == before_journeys
    inv_count = testing_session.execute(
        text("SELECT COUNT(*) FROM model_invocations WHERE run_id=:r"),
        {"r": run.id},
    ).scalar()
    assert inv_count == 2


@pytest.mark.asyncio
async def test_11_failed_attempt_zero_token_cost(testing_session, zero_delay_settings, monkeypatch):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake("aliyun_qwen_plus", [_disconnect(), VALID])
    run = make_run(testing_session)
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary"),
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
        user_content="task",
        business_validator=lambda _: None,
    )
    failed = testing_session.scalars(
        select(ModelInvocation).where(
            ModelInvocation.run_id == run.id, ModelInvocation.status == "failed"
        )
    ).one()
    assert failed.input_tokens is None
    assert failed.output_tokens is None
    assert failed.estimated_cost is None


def test_12_reservations_released_on_failed_canary_batch():
    db = require_path(CANARY_V5_DB)
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    active = con.execute(
        "SELECT COUNT(*) FROM cloud_budget_reservations WHERE status='active'"
    ).fetchone()[0]
    run3 = con.execute(
        "SELECT status FROM cloud_budget_reservations WHERE run_id=3"
    ).fetchall()
    con.close()
    assert active == 0
    assert run3 and all(r[0] == "released" for r in run3)


@pytest.mark.asyncio
async def test_13_validation_error_not_provider_retry(testing_session, zero_delay_settings, monkeypatch):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    # Local provider: JSON repair only — never provider_retry transport backoff
    provider = FakeProvider(["not-json", VALID])
    run = make_run(testing_session)
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary"),
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
        user_content="task",
        business_validator=lambda _: None,
    )
    kinds = list(
        testing_session.scalars(
            select(ModelInvocation.invocation_kind)
            .where(ModelInvocation.run_id == run.id)
            .order_by(ModelInvocation.id)
        )
    )
    assert kinds == ["initial", "json_repair"]
    assert "provider_retry" not in kinds


@pytest.mark.asyncio
async def test_14_business_validation_not_provider_retry(
    testing_session, zero_delay_settings, monkeypatch
):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = FakeProvider([VALID, VALID])
    run = make_run(testing_session)

    def _biz(result: SceneBoundaryResult) -> None:
        if not getattr(_biz, "once", False):
            _biz.once = True
            raise ValueError("business validation failed intentionally")

    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary"),
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
        user_content="task",
        business_validator=_biz,
    )
    kinds = list(
        testing_session.scalars(
            select(ModelInvocation.invocation_kind)
            .where(ModelInvocation.run_id == run.id)
            .order_by(ModelInvocation.id)
        )
    )
    assert kinds[0] == "initial"
    assert "provider_retry" not in kinds
    assert any(k == "business_repair" for k in kinds)


@pytest.mark.asyncio
async def test_15_401_403_no_retry(testing_session, zero_delay_settings, monkeypatch):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    for status in (401, 403):
        provider = CloudFake("aliyun_qwen_plus", [_http_error(status), VALID])
        run = make_run(testing_session)
        with pytest.raises(StructuredOutputError) as exc:
            await generate_validated(
                session=testing_session,
                gateway=ModelGateway([provider]),
                run_id=run.id,
                provider_name=provider.name,
                task_type="scene_boundary",
                prompt=load_prompt("scene_boundary"),
                schema=SceneBoundaryResult,
                input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
                user_content="task",
                business_validator=lambda _: None,
            )
        assert not should_retry_provider_error(exc.value.provider_error)
        rows = list(
            testing_session.scalars(
                select(ModelInvocation).where(ModelInvocation.run_id == run.id)
            )
        )
        assert len(rows) == 1
        assert provider.calls == 1


@pytest.mark.asyncio
async def test_16_17_429_and_5xx_retryable(testing_session, zero_delay_settings, monkeypatch):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    for status in (429, 502, 503, 504):
        provider = CloudFake("aliyun_qwen_plus", [_http_error(status, retryable=True), VALID])
        run = make_run(testing_session)
        await generate_validated(
            session=testing_session,
            gateway=ModelGateway([provider]),
            run_id=run.id,
            provider_name=provider.name,
            task_type="scene_boundary",
            prompt=load_prompt("scene_boundary"),
            schema=SceneBoundaryResult,
            input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
            user_content="task",
            business_validator=lambda _: None,
        )
        kinds = list(
            testing_session.scalars(
                select(ModelInvocation.invocation_kind)
                .where(ModelInvocation.run_id == run.id)
                .order_by(ModelInvocation.id)
            )
        )
        assert kinds == ["initial", "provider_retry"]


@pytest.mark.asyncio
async def test_18_final_error_code_preserved(testing_session, zero_delay_settings, monkeypatch):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake("aliyun_qwen_plus", [_disconnect(), _disconnect(), _disconnect()])
    run = make_run(testing_session)
    with pytest.raises(StructuredOutputError) as exc:
        await generate_validated(
            session=testing_session,
            gateway=ModelGateway([provider]),
            run_id=run.id,
            provider_name=provider.name,
            task_type="scene_boundary",
            prompt=load_prompt("scene_boundary"),
            schema=SceneBoundaryResult,
            input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
            user_content="task",
            business_validator=lambda _: None,
        )
    assert exc.value.error_code == "PROVIDER_REMOTE_DISCONNECT"


def test_19_main_db_55_2_unchanged():
    require_main_db_cert_counts()
    con = sqlite3.connect(f"file:{MAIN_DB.as_posix()}?mode=ro", uri=True)
    s55 = con.execute("SELECT status FROM analysis_runs WHERE id=55").fetchone()[0]
    j2 = con.execute("SELECT status FROM reader_journey_runs WHERE id=2").fetchone()[0]
    con.close()
    assert s55 == "succeeded" and j2 == "succeeded"


def test_20_transport_retry_policy_defaults():
    settings = Settings(_env_file=None)
    assert settings.aliyun_transport_max_attempts == 3
    assert settings.aliyun_transport_retry_delay_1_min == 2.0
    assert settings.aliyun_transport_retry_delay_1_max == 4.0
    assert settings.aliyun_transport_retry_delay_2_min == 8.0
    assert settings.aliyun_transport_retry_delay_2_max == 12.0
    assert settings.canary_inter_run_cooldown_seconds == 8.0
