"""Local tests for analysis execution plan + cached_failure override (CHG-20260722-007)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AnalysisRun,
    ApplicationSetting,
    Base,
    ModelInvocation,
    ProviderConfiguration,
)
from app.model_gateway.base import ProviderCapabilities
from app.model_gateway.gateway import ModelGateway
from app.services.analysis_execution_plan import build_analysis_execution_plan
from app.services.ai_validation_snapshot import (
    build_current_fingerprints,
    record_validation_outcome,
)
from app.services.provider_eligibility import evaluate_manual_boundary_candidate
from tests.fakes import FakeProvider
from tests.optional_gates import CLOUD_PRICING_PATH, install_verified_cloud_pricing, restore_cloud_pricing


class Store:
    def __init__(self, secret: str | None = "sk-test"):
        self.secret = secret

    def available(self):
        return True

    def get(self, _name):
        return self.secret

    def set(self, *_a, **_k):
        pass

    def delete(self, *_a, **_k):
        pass


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'plan.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        yield s
    engine.dispose()


@pytest.fixture
def pricing(tmp_path):
    path, previous = install_verified_cloud_pricing(CLOUD_PRICING_PATH)
    try:
        yield path
    finally:
        restore_cloud_pricing(path, previous)


def _caps(**extra) -> ProviderCapabilities:
    base = dict(
        max_context_tokens=32000,
        default_timeout_seconds=10,
        enabled=True,
        cloud=True,
        supports_json_object=True,
        supports_structured_output=True,
        supports_scene_analysis=True,
        supports_boundary_candidates=True,
        automatic_boundary_routing=False,
        requires_boundary_review=True,
    )
    base.update(extra)
    return ProviderCapabilities(**base)


def _configure_plus(session, *, cloud: bool = True) -> None:
    session.add(
        ProviderConfiguration(
            provider_name="aliyun_qwen_plus",
            enabled=True,
            disconnected=False,
            allow_auto_route=False,
            base_url="https://example.invalid/compatible-mode/v1",
            plus_model="qwen3.7-plus",
            credential_reference="keyring:aliyun_qwen_plus",
        )
    )
    session.add(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(cloud)))
    session.add(
        ApplicationSetting(
            key="cloud_budget_settings",
            value_json=json.dumps(
                {
                    "cloud_request_budget_enabled": True,
                    "cloud_daily_request_limit": 500,
                    "cloud_daily_token_limit": 500000,
                    "cloud_daily_estimated_cost_limit": 50,
                }
            ),
        )
    )
    session.commit()


def _add_cached_failure(session) -> None:
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id="1",
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="v1",
        schema_version="v1",
        input_hash="a" * 64,
        status="failed",
        execution_mode="cloud",
        cloud_consent=True,
        sends_content_to_cloud=True,
    )
    session.add(run)
    session.flush()
    session.add(
        ModelInvocation(
            run_id=run.id,
            task_type="scene_boundary",
            provider_name="aliyun_qwen_plus",
            model_name="qwen3.7-plus",
            prompt_version="v1",
            schema_version="v1",
            attempt_no=1,
            invocation_kind="boundary_candidate_detection",
            request_hash="b" * 64,
            input_snapshot_json="{}",
            raw_response_text="",
            parsed_response_json="{}",
            status="failed",
            latency_ms=1,
            http_request_sent=True,
            http_status_code=429,
            error_code="PROVIDER_HTTP_ERROR",
            error_message="rate limited",
        )
    )
    session.commit()


def test_cached_failure_blocks_without_validation_snapshot(session, pricing):
    _configure_plus(session)
    _add_cached_failure(session)
    result = evaluate_manual_boundary_candidate(
        session,
        provider_name="aliyun_qwen_plus",
        capabilities=_caps(),
        store=Store(),
        pricing_path=Path(pricing),
    )
    assert result["manual_boundary_candidate_eligible"] is False
    assert "provider_unhealthy" in result["manual_selection_blockers"]
    assert result["health_source"] == "cached_failure"


def test_validation_snapshot_overrides_cached_failure(session, pricing):
    _configure_plus(session)
    _add_cached_failure(session)
    store = Store()
    record_validation_outcome(
        session,
        store,
        provider_id="aliyun_qwen_plus",
        ok=True,
        model_name="qwen3.7-plus",
    )
    result = evaluate_manual_boundary_candidate(
        session,
        provider_name="aliyun_qwen_plus",
        capabilities=_caps(),
        store=store,
        pricing_path=Path(pricing),
    )
    assert result["manual_boundary_candidate_eligible"] is True
    assert "provider_unhealthy" not in result["manual_selection_blockers"]
    assert result["health_source"] == "validation_snapshot"


def test_execution_plan_balanced_can_start_after_snapshot(session, pricing):
    _configure_plus(session)
    _add_cached_failure(session)
    store = Store()
    record_validation_outcome(
        session,
        store,
        provider_id="aliyun_qwen_plus",
        ok=True,
        model_name="qwen3.7-plus",
    )
    gateway = ModelGateway([FakeProvider()])
    gateway.providers_list = None  # type: ignore[attr-defined]
    # FakeProvider name is "fake"; patch get
    provider = FakeProvider()
    provider.name = "aliyun_qwen_plus"
    provider.default_model = "qwen3.7-plus"
    provider.capabilities = lambda: _caps()  # type: ignore[method-assign]
    gateway = ModelGateway([provider])
    plan = build_analysis_execution_plan(
        session, gateway=gateway, store=store, mode="BALANCED", pricing_path=Path(pricing)
    )
    assert plan.can_start is True
    assert plan.selected_provider == "aliyun_qwen_plus"
    assert "scene_boundary_detection" in plan.supported_stages
    assert "reader_journey_generation" in plan.supported_stages
    assert plan.missing_stages == []


@pytest.mark.parametrize("mode", ["FAST", "BALANCED", "QUALITY", "CUSTOM"])
def test_execution_plan_modes_resolve(session, pricing, mode):
    _configure_plus(session)
    store = Store()
    record_validation_outcome(
        session,
        store,
        provider_id="aliyun_qwen_plus",
        ok=True,
        model_name="qwen3.7-plus",
    )
    provider = FakeProvider()
    provider.name = "aliyun_qwen_plus"
    provider.capabilities = lambda: _caps()  # type: ignore[method-assign]
    gateway = ModelGateway([provider])
    plan = build_analysis_execution_plan(
        session, gateway=gateway, store=store, mode=mode, pricing_path=Path(pricing)
    )
    assert plan.mode == mode
    assert plan.can_start is True
    assert plan.credential_available is True


def test_execution_plan_no_secret_leak(session, pricing):
    _configure_plus(session)
    store = Store("sk-super-secret-key")
    provider = FakeProvider()
    provider.name = "aliyun_qwen_plus"
    provider.capabilities = lambda: _caps()  # type: ignore[method-assign]
    plan = build_analysis_execution_plan(
        session,
        gateway=ModelGateway([provider]),
        store=store,
        mode="BALANCED",
        pricing_path=Path(pricing),
    )
    blob = json.dumps(plan.as_dict())
    assert "sk-super-secret" not in blob
    assert "api_key" not in blob.lower()
