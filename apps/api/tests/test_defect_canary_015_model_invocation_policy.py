# -*- coding: utf-8 -*-
"""DEFECT-CANARY-015: Global model invocation policy unification (v1.1.0)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import AnalysisRun, ModelInvocation, ProviderConfiguration
from app.model_gateway.base import ProviderCapabilities, ProviderRequestError
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.provider_errors import TRANSPORT_REMOTE_DISCONNECT
from app.schemas.scene import SceneBoundaryResult
from app.services.model_invocation_broker import (
    ERROR_POLICY_VIOLATION,
    ERROR_PROVIDER_DISABLED_PRECHECK,
    ERROR_TYPE_UNREGISTERED,
    ERROR_UNAUTHORIZED_FALLBACK,
    ModelInvocationBroker,
    ModelInvocationPolicyError,
    REGISTERED_INVOCATION_TYPES,
    map_invocation_type,
    resolve_for_offline_graph,
)
from app.services.prompt_service import load_prompt
from app.services.scene_pipeline import classify_pipeline_error
from app.services.structured_output import StructuredOutputError, generate_validated
from tests.optional_gates import require_main_db_cert_counts, require_path
from tests.test_aliyun_provider import CloudFake
from tests.test_phase_2b1 import boundary_json

pytestmark = [
    pytest.mark.canary_offline,
    pytest.mark.requires_audit_assets,
]

ROOT = Path(__file__).resolve().parents[3]
MAIN_DB = ROOT / "data" / "storylens.db"
DEFECT_015 = (
    ROOT
    / "audits"
    / "single-chapter-pipeline"
    / "real-canary-v11"
    / "defects"
    / "DEFECT-CANARY-015.json"
)

PLUS = "aliyun_qwen_plus"
FLASH = "aliyun_qwen_flash"
MODEL = "qwen3.7-plus"
FLASH_MODEL = "qwen3.6-flash"

CANONICAL_TYPES = [
    "scene_boundary",
    "scene_boundary_schema_repair",
    "scene_analysis",
    "scene_analysis_provider_retry",
    "scene_analysis_provider_recovery",
    "reader_journey_scene_batch",
    "reader_journey_scene_schema_repair",
    "reader_journey_structural_repair",
    "reader_journey_targeted_evidence_patch",
    "reader_journey_chapter",
    "reader_journey_chapter_schema_repair",
    "repair_provider_retry",
    "generic_provider_retry",
]


def make_run(session, *, provider: str = PLUS, model: str = MODEL) -> AnalysisRun:
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id="1",
        provider=provider,
        model=model,
        prompt_version="v1",
        schema_version="v1",
        prompt_hash="x",
        input_hash="x",
        status="running",
    )
    session.add(run)
    session.commit()
    return run


def _seed_plus_config(session, *, allow_auto_route: bool = False, enabled: bool = True) -> None:
    session.merge(
        ProviderConfiguration(
            provider_name=PLUS,
            display_name="plus",
            region="cn-beijing",
            base_url="https://example.invalid/v1",
            plus_model=MODEL,
            enabled=enabled,
            disconnected=False,
            allow_auto_route=allow_auto_route,
            credential_reference="keyring:aliyun_qwen_plus",
        )
    )
    session.commit()


class PolicyCloudFake(CloudFake):
    def __init__(self, name: str, responses=None, *, enabled: bool = True, model: str | None = None):
        super().__init__(name, responses=responses)
        self.default_model = model or (MODEL if name == PLUS else FLASH_MODEL)
        self._enabled = enabled

    def capabilities(self) -> ProviderCapabilities:
        caps = super().capabilities()
        return caps.model_copy(update={"enabled": self._enabled})


def _disconnect() -> ProviderRequestError:
    return ProviderRequestError(
        "Server disconnected without sending a response.",
        http_request_sent=True,
        error_code="PROVIDER_REMOTE_DISCONNECT",
        transport_kind=TRANSPORT_REMOTE_DISCONNECT,
        retryable=True,
    )


@pytest.mark.asyncio
async def test_01_normal_journey_uses_plus(testing_session) -> None:
    _seed_plus_config(testing_session)
    run = make_run(testing_session)
    provider = PolicyCloudFake(PLUS, [boundary_json()])
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=PLUS,
        task_type="reader_journey_scene",
        prompt=load_prompt("scene_boundary", "v3.1"),
        schema=SceneBoundaryResult,
        input_snapshot={},
        user_content="fixture",
        business_validator=lambda _: None,
        initial_invocation_kind="normal_batch_request",
    )
    row = testing_session.scalars(select(ModelInvocation)).one()
    assert row.provider_name == PLUS
    assert row.model_name == MODEL


@pytest.mark.asyncio
async def test_02_journey_schema_repair_uses_plus(testing_session) -> None:
    _seed_plus_config(testing_session)
    run = make_run(testing_session)
    provider = PolicyCloudFake(
        PLUS, [json.dumps({"boundaries": []}), boundary_json()]
    )
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=PLUS,
        task_type="reader_journey_scene",
        prompt=load_prompt("scene_boundary", "v3.1"),
        schema=SceneBoundaryResult,
        input_snapshot={},
        user_content="fixture",
        business_validator=lambda _: None,
        initial_invocation_kind="normal_batch_request",
    )
    rows = list(
        testing_session.scalars(select(ModelInvocation).order_by(ModelInvocation.id))
    )
    assert rows[1].invocation_kind == "schema_repair"
    assert rows[1].provider_name == PLUS
    assert rows[1].model_name == MODEL


@pytest.mark.asyncio
async def test_03_structural_repair_type_maps_to_plus_policy() -> None:
    payload = resolve_for_offline_graph(
        invocation_type="reader_journey_structural_repair",
        authorized_provider=PLUS,
        authorized_model=MODEL,
        auto_route=False,
    )
    assert payload["resolved_provider"] == PLUS
    assert payload["resolved_model"] == MODEL
    assert payload["fallback_used"] is False
    assert payload["error_code"] is None


@pytest.mark.asyncio
async def test_04_targeted_evidence_patch_maps_to_plus_policy() -> None:
    assert (
        map_invocation_type(
            "reader_journey_scene",
            "structural_repair",
            targeted_evidence_repair=True,
        )
        == "reader_journey_targeted_evidence_patch"
    )
    payload = resolve_for_offline_graph(
        invocation_type="reader_journey_targeted_evidence_patch",
        authorized_provider=PLUS,
        authorized_model=MODEL,
        auto_route=False,
    )
    assert payload["resolved_provider"] == PLUS
    assert payload["resolved_model"] == MODEL


@pytest.mark.asyncio
async def test_05_chapter_schema_repair_uses_plus_policy() -> None:
    payload = resolve_for_offline_graph(
        invocation_type="reader_journey_chapter_schema_repair",
        authorized_provider=PLUS,
        authorized_model=MODEL,
        auto_route=False,
    )
    assert payload["resolved_provider"] == PLUS
    assert payload["fallback_used"] is False


@pytest.mark.asyncio
async def test_06_scene_analysis_recovery_uses_plus_policy() -> None:
    payload = resolve_for_offline_graph(
        invocation_type="scene_analysis_provider_recovery",
        authorized_provider=PLUS,
        authorized_model=MODEL,
        auto_route=False,
    )
    assert payload["resolved_provider"] == PLUS
    assert payload["resolved_model"] == MODEL


@pytest.mark.asyncio
async def test_07_transport_retry_keeps_provider_model(
    testing_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock

    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("STORYLENS_ALIYUN_MAX_RETRIES", "3")
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    _seed_plus_config(testing_session)
    run = make_run(testing_session)
    provider = PolicyCloudFake(PLUS, [_disconnect(), boundary_json()])
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=PLUS,
        task_type="scene_analysis",
        prompt=load_prompt("scene_boundary", "v3.1"),
        schema=SceneBoundaryResult,
        input_snapshot={},
        user_content="fixture",
        business_validator=lambda _: None,
    )
    rows = list(
        testing_session.scalars(select(ModelInvocation).order_by(ModelInvocation.id))
    )
    assert [r.invocation_kind for r in rows] == ["initial", "provider_retry"]
    assert all(r.provider_name == PLUS and r.model_name == MODEL for r in rows)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_08_repair_retry_keeps_provider_model() -> None:
    payload = resolve_for_offline_graph(
        invocation_type="repair_provider_retry",
        authorized_provider=PLUS,
        authorized_model=MODEL,
        auto_route=False,
        requested_provider=PLUS,
        requested_model=MODEL,
    )
    assert payload["resolved_provider"] == PLUS
    assert payload["resolved_model"] == MODEL
    assert payload["fallback_used"] is False


def test_09_auto_route_false_forbids_flash_fallback() -> None:
    broker = ModelInvocationBroker()
    with pytest.raises(ModelInvocationPolicyError) as exc:
        broker.resolve(
            run_id=1,
            invocation_type="reader_journey_scene_schema_repair",
            authorized_provider=PLUS,
            authorized_model=MODEL,
            auto_route=False,
            requested_provider=FLASH,
            requested_model=FLASH_MODEL,
            gateway=None,
            fallback_policy="none",
        )
    assert exc.value.error_code == ERROR_UNAUTHORIZED_FALLBACK


def test_10_disabled_provider_fails_before_send() -> None:
    broker = ModelInvocationBroker()
    disabled = PolicyCloudFake(PLUS, enabled=False)
    with pytest.raises(ModelInvocationPolicyError) as exc:
        broker.resolve(
            run_id=1,
            invocation_type="scene_analysis",
            authorized_provider=PLUS,
            authorized_model=MODEL,
            auto_route=False,
            requested_provider=PLUS,
            requested_model=MODEL,
            gateway=ModelGateway([disabled]),
            fallback_policy="none",
        )
    assert exc.value.error_code == ERROR_PROVIDER_DISABLED_PRECHECK
    assert exc.value.to_provider_error().http_request_sent is False


def test_11_repair_requesting_flash_policy_violation() -> None:
    payload = resolve_for_offline_graph(
        invocation_type="schema_repair",
        authorized_provider=PLUS,
        authorized_model=MODEL,
        auto_route=False,
        requested_provider=FLASH,
        requested_model=FLASH_MODEL,
    )
    assert payload["error_code"] in {ERROR_UNAUTHORIZED_FALLBACK, ERROR_POLICY_VIOLATION}


def test_12_unregistered_invocation_type_cannot_send() -> None:
    broker = ModelInvocationBroker()
    with pytest.raises(ModelInvocationPolicyError) as exc:
        broker.resolve(
            run_id=1,
            invocation_type="not_a_real_invocation_type",
            authorized_provider=PLUS,
            authorized_model=MODEL,
            auto_route=False,
            gateway=None,
        )
    assert exc.value.error_code == ERROR_TYPE_UNREGISTERED


def test_13_run_policy_propagates_to_nested_repair_types() -> None:
    for inv in (
        "reader_journey_scene_schema_repair",
        "reader_journey_structural_repair",
        "repair_provider_retry",
        "generic_provider_retry",
    ):
        payload = resolve_for_offline_graph(
            invocation_type=inv,
            authorized_provider=PLUS,
            authorized_model=MODEL,
            auto_route=False,
        )
        assert payload["resolved_provider"] == PLUS
        assert payload["resolved_model"] == MODEL
        assert payload["auto_route"] is False
        assert payload["fallback_used"] is False


def test_14_request_hash_policy_independent_of_model() -> None:
    a = resolve_for_offline_graph(
        invocation_type="reader_journey_scene_batch",
        authorized_provider=PLUS,
        authorized_model=MODEL,
        auto_route=False,
    )
    b = resolve_for_offline_graph(
        invocation_type="reader_journey_scene_schema_repair",
        authorized_provider=PLUS,
        authorized_model=MODEL,
        auto_route=False,
    )
    assert a["request_hash_policy"] == "independent_of_model_policy"
    assert b["request_hash_policy"] == "independent_of_model_policy"
    assert a["resolved_model"] == b["resolved_model"] == MODEL


def test_15_defect_015_historical_offline_replay() -> None:
    require_path(DEFECT_015)
    defect = json.loads(DEFECT_015.read_text(encoding="utf-8"))
    chain = defect["causal_chain"]
    assert chain[0]["provider"] == PLUS
    assert chain[1]["provider"] == FLASH
    assert chain[1]["error_code"] == "PROVIDER_DISABLED"
    # Historical (buggy) path would request Flash for schema_repair.
    historical = resolve_for_offline_graph(
        invocation_type="reader_journey_scene_schema_repair",
        authorized_provider=PLUS,
        authorized_model=MODEL,
        auto_route=False,
        requested_provider=FLASH,
        requested_model=FLASH_MODEL,
    )
    assert historical["error_code"] in {
        ERROR_UNAUTHORIZED_FALLBACK,
        ERROR_POLICY_VIOLATION,
    }


def test_16_remediated_historical_resolves_to_plus() -> None:
    fixed = resolve_for_offline_graph(
        invocation_type="reader_journey_scene_schema_repair",
        authorized_provider=PLUS,
        authorized_model=MODEL,
        auto_route=False,
        requested_provider=PLUS,
        requested_model=MODEL,
    )
    assert fixed["resolved_provider"] == PLUS
    assert fixed["resolved_model"] == MODEL
    assert fixed["fallback_used"] is False
    assert fixed["error_code"] is None


def test_17_canonical_types_registered_and_no_bypass_markers() -> None:
    for item in CANONICAL_TYPES:
        assert item in REGISTERED_INVOCATION_TYPES
    structured = (
        ROOT / "apps" / "api" / "app" / "services" / "structured_output.py"
    ).read_text(encoding="utf-8")
    assert 'next_provider_name = (\n                "aliyun_qwen_flash"' not in structured
    assert "aliyun_qwen_flash" not in structured
    assert "model_invocation_broker" in structured


def test_18_main_db_invariance_55_2() -> None:
    require_main_db_cert_counts()


def test_19_zero_real_model_requests_this_phase() -> None:
    # This remediation phase is offline-only; marker asserted by change package.
    change = json.loads(
        (
            ROOT
            / "audits"
            / "single-chapter-pipeline"
            / "changes"
            / "global-model-invocation-policy-change-v1.1.0.json"
        ).read_text(encoding="utf-8")
    )
    assert change["real_model_requests_this_phase"] == 0


def test_policy_errors_not_wrapped_as_pipeline_unexpected() -> None:
    exc = StructuredOutputError(
        "policy",
        ERROR_POLICY_VIOLATION,
        category="model_invocation_policy",
        retryable=False,
    )
    code, stage, retryable, _ = classify_pipeline_error(exc)
    assert code == ERROR_POLICY_VIOLATION
    assert stage == "model_invocation_policy"
    assert retryable is False
    assert code != "PIPELINE_UNEXPECTED_ERROR"
