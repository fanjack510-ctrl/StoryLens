"""Phase 2B-R Agent S — Private Runtime and Provider Lab foundation tests.

Fake + dry only. No live Provider calls required for CI.
Live probes remain opt-in via WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app, mount_private_engine_lab_if_enabled
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey, WholeBookStageKey
from app.narrative_core.private_engine_contract.errors import PrivateEngineError, PrivateEngineErrorCode
from app.narrative_core.private_engine_contract.provider_gateway import ProviderInferenceRequest
from app.narrative_core.private_engine_contract.protocol import PrivateEngineExecutionRequest
from app.narrative_core.run_shell_contract.mock_lab import WHOLE_BOOK_MOCK_LAB_ENABLED
from app.narrative_core.run_shell_contract.private_engine_lab import (
    PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER,
    PRIVATE_LAB_FIRST_MODEL_ID,
    PRIVATE_LAB_FIRST_PROVIDER_KEY,
    PRIVATE_LAB_FIRST_QUALITY_PROFILE,
    WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
    evaluate_private_engine_lab_authorization,
    PrivateEngineLabAuthorizationInput,
)
from app.narrative_core.services.private_engine_lab_authorization_service import (
    PrivateEngineLabAuthorizationDenied,
    PrivateEngineLabAuthorizationService,
    is_private_engine_lab_enabled_from_env,
    should_register_private_engine_lab_router,
)
from app.narrative_core.services.private_engine_manifest_loader import try_import_private_engine_entry
from app.narrative_core.services.private_engine_runtime_adapter import (
    PrivateWholeBookEngineRuntimeAdapter,
)
from app.narrative_core.services.private_engine_signature import (
    DevLabSignaturePolicy,
    evaluate_dev_lab_signature,
)
from app.narrative_core.services.whole_book_engine_registry import PRODUCTION_DEFAULT_ENGINE_ID
from app.narrative_core.services.whole_book_provider_gateway import (
    BailianOpenAICompatibleProviderAdapter,
    CloudBudgetGuardBridge,
    DefaultWholeBookProviderGateway,
    ExistingCredentialServiceAdapter,
    FakeProviderAdapter,
    assert_no_credential_in_logs,
    create_lab_provider_gateway,
)
from app.routers.whole_book_private_engine_lab_runs import (
    lab_contract_assertions,
    reset_private_engine_lab_sessions_for_tests,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def _provider_request(*, provider_kind: str = "fake") -> ProviderInferenceRequest:
    return ProviderInferenceRequest(
        request_id="req-1",
        provider_kind=provider_kind,
        model_route=f"{provider_kind}/default",
        task_type="module_execution",
        system_instruction_ref="instr://a",
        prompt_pack_ref="pack://a",
        input_bundle_ref="bundle://a",
        response_schema_ref="schema://a",
        temperature_policy={},
        token_budget=128,
        cost_budget=None,
        timeout_policy={},
        retry_policy={},
        cancellation_ref=None,
        data_handling_policy={},
        metadata={},
    )


def test_gates_remain_closed() -> None:
    assert Path(REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip() == "1.2.0"
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert PRODUCTION_DEFAULT_ENGINE_ID is None
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False
    assert WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED is False
    assert is_private_engine_lab_enabled_from_env(environ={}) is False


def test_private_lab_distinct_from_mock_lab() -> None:
    assert PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER != "X-StoryLens-Mock-Lab"
    meta = lab_contract_assertions()
    assert meta["WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED_DEFAULT"] is False
    assert meta["WHOLE_BOOK_MOCK_LAB_ENABLED_DEFAULT"] is False
    assert meta["FIRST_PROVIDER_KEY"] == PRIVATE_LAB_FIRST_PROVIDER_KEY
    assert meta["FIRST_MODEL_ID"] == PRIVATE_LAB_FIRST_MODEL_ID
    assert meta["FIRST_QUALITY_PROFILE"] == PRIVATE_LAB_FIRST_QUALITY_PROFILE


def test_fake_provider_still_default() -> None:
    gw = DefaultWholeBookProviderGateway()
    assert gw.allow_network is False
    assert gw.lab_network_authorized is False
    response = gw.execute(_provider_request())
    assert response.structured_output is not None
    assert response.structured_output.get("fake") is True


def test_default_gateway_still_forbids_bare_network_flag() -> None:
    with pytest.raises(ValueError):
        DefaultWholeBookProviderGateway(allow_network=True)


def test_bailian_adapter_dry_run_no_live_http() -> None:
    adapter = BailianOpenAICompatibleProviderAdapter(dry_run=True, allow_network=False)
    response = adapter.execute(
        _provider_request(provider_kind=PRIVATE_LAB_FIRST_PROVIDER_KEY)
    )
    assert response.status == "success"
    assert response.model_id == PRIVATE_LAB_FIRST_MODEL_ID
    assert response.structured_output is not None
    assert response.structured_output.get("dry_run") is True
    health = adapter.health_check()
    assert "dry_run" in health.details
    assert "no_live_http" in health.details


def test_lab_gateway_registers_bailian_and_fake() -> None:
    gw = create_lab_provider_gateway(dry_run=True)
    assert "fake" in gw.registry.list_kinds()
    assert PRIVATE_LAB_FIRST_PROVIDER_KEY in gw.registry.list_kinds()
    gw.validate_policy(
        {
            "provider_kind": PRIVATE_LAB_FIRST_PROVIDER_KEY,
            "model_route": f"{PRIVATE_LAB_FIRST_PROVIDER_KEY}/{PRIVATE_LAB_FIRST_MODEL_ID}",
        }
    )
    response = gw.execute(_provider_request(provider_kind=PRIVATE_LAB_FIRST_PROVIDER_KEY))
    assert response.status == "success"
    assert response.structured_output is not None
    assert response.structured_output.get("dry_run") is True


def test_budget_bridge_stops_on_deny() -> None:
    guard = CloudBudgetGuardBridge(force_deny=True)
    gw = create_lab_provider_gateway(dry_run=True, budget_guard=guard)
    with pytest.raises(PrivateEngineError) as exc:
        gw.execute(_provider_request(provider_kind=PRIVATE_LAB_FIRST_PROVIDER_KEY))
    assert exc.value.code == PrivateEngineErrorCode.PROVIDER_BUDGET_EXCEEDED


def test_credential_boundary_never_in_dto() -> None:
    class _Store:
        def available(self) -> bool:
            return True

        def get(self, name: str) -> str | None:
            return "sk-test-should-not-enter-dto"

        def set(self, name: str, value: str) -> None:
            raise NotImplementedError

        def delete(self, name: str) -> None:
            raise NotImplementedError

    adapter = ExistingCredentialServiceAdapter(store=_Store(), enabled=True)
    secret = adapter.resolve(PRIVATE_LAB_FIRST_PROVIDER_KEY)
    assert secret == "sk-test-should-not-enter-dto"
    req = _provider_request(provider_kind=PRIVATE_LAB_FIRST_PROVIDER_KEY)
    blob = json.dumps(asdict(req), default=str)
    assert "sk-test" not in blob
    assert_no_credential_in_logs("provider execute ok")
    with pytest.raises(AssertionError):
        assert_no_credential_in_logs(f"authorization: Bearer {secret}")


def test_private_lab_authorization_fail_closed() -> None:
    decision = evaluate_private_engine_lab_authorization(
        PrivateEngineLabAuthorizationInput(
            environment="production",
            loopback=True,
            lab_enabled=True,
            request_marker_present=True,
            credential_present=True,
            data_transfer_consented=True,
            budget_ok=True,
            capability_ok=True,
            user_confirmed=True,
            dry_run=False,
        )
    )
    assert decision.allowed is False

    svc = PrivateEngineLabAuthorizationService(
        environment="development",
        lab_enabled=True,
    )
    ok = svc.evaluate(
        loopback=True,
        request_marker_present=True,
        dry_run=True,
    )
    assert ok.allowed is True
    with pytest.raises(PrivateEngineLabAuthorizationDenied):
        svc.require(loopback=False, request_marker_present=True, dry_run=True)


def test_should_register_private_lab_router() -> None:
    assert should_register_private_engine_lab_router(environment="development", lab_enabled=True)
    assert not should_register_private_engine_lab_router(environment="development", lab_enabled=False)
    assert not should_register_private_engine_lab_router(environment="production", lab_enabled=True)


def test_private_lab_router_mount_and_dry_create() -> None:
    """Phase 2B-R1: Lab mount + auth gate; AnalysisRun create needs DB (see CHG-047 tests)."""

    reset_private_engine_lab_sessions_for_tests()
    app = create_app(
        environment="development",
        lab_enabled=False,
        private_engine_lab_enabled=True,
    )
    client = TestClient(app)
    headers = {PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER: "1"}
    denied = client.post(
        "/api/v1/labs/private-whole-book-runs",
        json={
            "book_id": 1,
            "book_snapshot_id": 1,
            "dry_run": True,
            "auto_start": False,
        },
    )
    # Without marker → 403
    assert denied.status_code == 403

    contract = client.get("/api/v1/labs/private-whole-book-runs/_meta/contract", headers=headers)
    assert contract.status_code == 200
    meta = contract.json()
    assert meta["WHOLE_BOOK_RUNS_ENDPOINT_DISABLED"] is True
    assert meta["shell_only"] is False
    assert meta["modules_implemented"] is True
    assert meta["FIRST_PROVIDER_KEY"] == PRIVATE_LAB_FIRST_PROVIDER_KEY
    assert meta["WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED_DEFAULT"] is False


def test_private_lab_not_mounted_when_disabled() -> None:
    app = create_app(
        environment="development",
        lab_enabled=False,
        private_engine_lab_enabled=False,
    )
    # Mount helper returns False; routes absent.
    assert mount_private_engine_lab_if_enabled(app, environment="development", lab_enabled=False) is False
    client = TestClient(app)
    response = client.post(
        "/api/v1/labs/private-whole-book-runs",
        headers={PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER: "1"},
        json={"book_id": 1, "book_snapshot_id": 1, "dry_run": True},
    )
    assert response.status_code == 404


def test_dev_lab_signature_hooks() -> None:
    assert evaluate_dev_lab_signature(
        signed=False,
        non_production=True,
        lab_authorized=True,
        production=False,
    )
    assert not evaluate_dev_lab_signature(
        signed=False,
        non_production=True,
        lab_authorized=False,
        production=False,
    )
    with pytest.raises(ValueError):
        DevLabSignaturePolicy(
            allow_unsigned_non_production=True,
            production=True,
            lab_authorized=False,
        )


def test_runtime_adapter_accepts_private_shell_or_fake() -> None:
    adapter = PrivateWholeBookEngineRuntimeAdapter.for_lab_private_package()
    health = adapter.health_check()
    assert health.healthy is True
    req = PrivateEngineExecutionRequest(
        run_id=1,
        stage_key=WholeBookStageKey.ANALYZE_STRUCTURE,
        attempt=0,
        book_id=1,
        book_snapshot_id=1,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        requested_module_keys=(WholeBookModuleKey.BOOK_OVERVIEW,),
        resolved_module_keys=(WholeBookModuleKey.BOOK_OVERVIEW,),
        context_bundle_ref="ctx://1",
        provider_policy={"quality_profile": "balanced"},
        budget_policy={"estimated_tokens": 10},
        output_locale="zh",
        source_language="zh",
        configuration_fingerprint="fp-1",
        prompt_pack_ref="pack://empty",
        cancellation_ref=None,
        checkpoint_ref=None,
        mock=False,
        requested_at=datetime(2026, 7, 23),
    )
    # Without prompt pack repository, missing pack is allowed (shell path).
    result = adapter.execute(req)
    assert result.validation_summary.get("canonical") is False
    assert result.asset_candidates == ()


def test_no_formal_prompt_bodies_in_public_tree() -> None:
    banned = re.compile(
        r"(\"prompt_body\"|system_prompt\s*=\s*[\"']You are|\"instruction_text\")"
    )
    roots = [
        REPO_ROOT / "apps" / "api" / "app" / "narrative_core" / "private_engine_contract",
        REPO_ROOT / "apps" / "api" / "app" / "narrative_core" / "services",
        REPO_ROOT / "apps" / "api" / "app" / "routers",
    ]
    offenders: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "FORBIDDEN" in text and "prompt_body" in text:
                continue
            if banned.search(text) and "prompt_body_forbidden" not in text:
                # Allow mentions in deny-lists / comments about absence.
                if "must not" in text or "forbidden" in text.lower() or "Agent T" in text:
                    continue
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_live_probe_env_default_off() -> None:
    assert os.environ.get("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "") == ""
    adapter = BailianOpenAICompatibleProviderAdapter(dry_run=False, allow_network=True)
    # Without live probe env, execute stays dry.
    response = adapter.execute(_provider_request(provider_kind=PRIVATE_LAB_FIRST_PROVIDER_KEY))
    assert response.structured_output is not None
    assert response.structured_output.get("dry_run") is True


def test_try_import_private_engine_entry_optional() -> None:
    # May be None if private package not on PYTHONPATH — both outcomes are valid.
    entry = try_import_private_engine_entry()
    if entry is not None:
        health = entry.health_check()
        assert health["healthy"] is True
        assert "modules_not_implemented" in health["details"]
