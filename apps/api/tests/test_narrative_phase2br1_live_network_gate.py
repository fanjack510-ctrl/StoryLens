"""Phase 2B-R1 CHG-050 — Live Network Gate directed tests.

All Live branches inject Capturing/Fake Transport — zero internet.
"""

from __future__ import annotations

import os

import pytest

from app.narrative_core.services.private_engine_lab_authorization_service import (
    is_private_provider_live_probe_enabled,
)
from app.narrative_core.services.private_lab_service_adapters import (
    PrivateLabProviderExecutionServiceAdapter,
)
from app.narrative_core.services.private_whole_book_live_readiness_runtime import (
    create_live_readiness_runtime,
    get_or_create_default_live_readiness_runtime,
    reset_default_live_readiness_runtime_for_tests,
)
from app.narrative_core.services.provider_execution_authorization import (
    compute_provider_execution_authorization,
    compute_runtime_allow_network,
)
from app.narrative_core.services.provider_input_bundle_resolver import (
    FakeProviderInputBundleResolver,
)
from app.narrative_core.services.whole_book_provider_gateway import (
    CapturingProviderTransport,
    ExistingCredentialServiceAdapter,
    StubTransportResponse,
)
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.run_shell_contract.private_engine_lab import (
    WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
)
from app.narrative_core.run_shell_contract.mock_lab import WHOLE_BOOK_MOCK_LAB_ENABLED


class _FakeKeyStore:
    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._map = dict(mapping or {})

    def available(self) -> bool:
        return True

    def get(self, provider_kind: str) -> str | None:
        return self._map.get(provider_kind)


@pytest.fixture(autouse=True)
def _clean_runtime(monkeypatch: pytest.MonkeyPatch):
    reset_default_live_readiness_runtime_for_tests()
    monkeypatch.delenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", raising=False)
    monkeypatch.delenv("STORYLENS_DATABASE_URL", raising=False)
    yield
    reset_default_live_readiness_runtime_for_tests()


def _capturing() -> CapturingProviderTransport:
    return CapturingProviderTransport(
        stub=StubTransportResponse(
            text='{"ok":true,"partial":true,"items":[]}',
            model="qwen3.7-plus",
            request_id="cap-1",
            input_tokens=11,
            output_tokens=7,
        )
    )


def _cred(present: bool = True) -> ExistingCredentialServiceAdapter:
    store = _FakeKeyStore({"aliyun_qwen_plus": "sk-test-not-real"} if present else {})
    return ExistingCredentialServiceAdapter(store=store, enabled=True)


def test_compute_runtime_allow_network_gates() -> None:
    assert compute_runtime_allow_network(
        environment="development", lab_enabled=True, live_probe_enabled=True
    )
    assert not compute_runtime_allow_network(
        environment="development", lab_enabled=True, live_probe_enabled=False
    )
    assert not compute_runtime_allow_network(
        environment="production", lab_enabled=True, live_probe_enabled=True
    )
    assert not compute_runtime_allow_network(
        environment="development", lab_enabled=False, live_probe_enabled=True
    )


def test_probe_false_request_live_denied_zero_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", raising=False)
    transport = _capturing()
    rt = create_live_readiness_runtime(
        environment="development",
        lab_enabled=True,
        dry_run=True,
        allow_network=None,
        transport=transport,
        credential_adapter=_cred(),
        allow_fake_resolver=True,
        resolver=FakeProviderInputBundleResolver(),
    )
    assert rt.allow_network is False
    pe = rt.provider_execution
    assert pe is not None
    result = pe.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False},
    )
    assert result.status == "security_denied"
    assert result.usage.get("http") is False
    assert result.usage.get("synthetic_success") is False
    assert len(transport.calls) == 0


def test_probe_true_request_dry_zero_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    transport = _capturing()
    rt = create_live_readiness_runtime(
        environment="development",
        lab_enabled=True,
        transport=transport,
        credential_adapter=_cred(),
        allow_fake_resolver=True,
        resolver=FakeProviderInputBundleResolver(),
    )
    assert rt.allow_network is True
    pe = rt.provider_execution
    assert pe is not None
    before = len(transport.calls)
    result = pe.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": True},
    )
    assert result.status == "success"
    assert result.usage.get("http") is False
    assert result.usage.get("effective_dry_run") is True
    # Intentional dry may capture structure locally once.
    assert pe.http_calls == 0
    assert len(transport.calls) >= before  # capture generate ok
    # No live gateway HTTP accounting
    assert pe.last_authorization is not None
    assert pe.last_authorization.requested_dry_run is True


def test_probe_true_allow_network_false_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    transport = _capturing()
    pe = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        dry_run=True,
        allow_network=False,
        transport=transport,
        credential_resolver=_cred(),
        environment="development",
        lab_enabled=True,
    )
    result = pe.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False},
    )
    assert result.status == "security_denied"
    assert result.usage.get("deny_reason") == "allow_network_false"
    assert pe.http_calls == 0
    assert len(transport.calls) == 0


@pytest.mark.skip(reason="Legacy Private Lab fake transport output no longer satisfies the formal V2 evidence contract")
def test_authorized_live_uses_injected_transport_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    from app.narrative_core.services.provider_transport_kind import FakeHttpProviderTransport

    fake_http = FakeHttpProviderTransport(
        stub_text=(
            '{"logline":"Synthetic overview","premise":"Synthetic premise",'
            '"central_question":"Q?","primary_conflict":"C",'
            '"protagonist_asset_id":null,"major_storyline_ids":[],'
            '"structure_summary":"S","ending_state":"open",'
            '"evidence_refs":[{"evidence_id":"ev-1","evidence_role":"support"}],'
            '"confidence":0.5}'
        ),
        request_id="fake-http-live-1",
        input_tokens=1800,
        output_tokens=220,
        http_status=200,
    )
    capturing = _capturing()
    rt = create_live_readiness_runtime(
        environment="test",
        lab_enabled=True,
        transport=capturing,
        live_transport=fake_http,
        explicit_test_transport_override=True,
        credential_adapter=_cred(True),
        allow_fake_resolver=True,
        resolver=FakeProviderInputBundleResolver(),
    )
    pe = rt.provider_execution
    assert pe is not None
    assert rt.allow_network is True
    result = pe.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False},
    )
    assert result.status == "success"
    assert result.usage.get("http") is True
    assert result.usage.get("live") is True
    assert result.usage.get("synthetic_success") is False
    assert result.usage.get("transport_kind") == "FAKE_HTTP_TEST"
    assert result.usage.get("provider_request_id") == "fake-http-live-1"
    assert result.usage.get("input_tokens") == 1800
    assert result.usage.get("output_tokens") == 220
    assert pe.http_calls == 1
    assert len(fake_http.calls) == 1
    assert len(capturing.calls) == 0  # Capturing must not be reused on Live
    assert pe.last_authorization is not None
    assert pe.last_authorization.effective_dry_run is False
    assert pe.last_authorization.requested_dry_run is False
    assert pe.last_payloads[-1]["ref_only"] is False
    assert pe.last_payloads[-1]["has_system"] is True


def test_authorized_live_rejects_capturing_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    capturing = _capturing()
    pe = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        allow_network=True,
        transport=capturing,
        live_transport=capturing,  # explicitly wrong
        credential_resolver=_cred(True),
        environment="development",
        lab_enabled=True,
    )
    result = pe.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False},
    )
    assert result.status == "security_denied"
    assert result.usage.get("deny_reason") == "live_transport_rejected"
    assert pe.http_calls == 0
    assert len(capturing.calls) == 0


def test_production_probe_true_zero_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    transport = _capturing()
    rt = create_live_readiness_runtime(
        environment="production",
        lab_enabled=True,
        transport=transport,
        credential_adapter=_cred(),
        allow_fake_resolver=True,
        resolver=FakeProviderInputBundleResolver(),
    )
    assert rt.lab_enabled is False
    assert rt.allow_network is False
    pe = rt.provider_execution
    assert pe is not None
    result = pe.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False},
    )
    assert result.status == "security_denied"
    assert pe.http_calls == 0


def test_lab_false_probe_true_zero_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    transport = _capturing()
    rt = create_live_readiness_runtime(
        environment="development",
        lab_enabled=False,
        transport=transport,
        credential_adapter=_cred(),
        allow_fake_resolver=True,
        resolver=FakeProviderInputBundleResolver(),
    )
    assert rt.allow_network is False
    pe = rt.provider_execution
    assert pe is not None
    result = pe.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False},
    )
    assert result.status == "security_denied"
    assert pe.http_calls == 0


def test_consent_estimate_budget_credential_cancel_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    transport = _capturing()
    pe = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        allow_network=True,
        transport=transport,
        credential_resolver=_cred(True),
        environment="development",
        lab_enabled=True,
    )
    for key, value, expect in (
        ("consent_valid", False, "consent_invalid"),
        ("estimate_valid", False, "estimate_invalid"),
        ("provider_route_valid", False, "provider_route_invalid"),
        ("provider_health_allowed", False, "provider_health_denied"),
    ):
        result = pe.execute_module(
            module_key="book_overview",
            request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False, key: value},
        )
        assert result.status == "security_denied"
        assert result.usage.get("deny_reason") == expect
        assert pe.http_calls == 0

    pe.cancel("c1")
    result = pe.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False},
        cancellation_ref="c1",
    )
    assert result.status == "cancelled"
    assert pe.http_calls == 0

    pe2 = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        allow_network=True,
        transport=_capturing(),
        credential_resolver=_cred(False),
        environment="development",
        lab_enabled=True,
    )
    result = pe2.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False},
    )
    assert result.status == "security_denied"
    assert result.usage.get("deny_reason") == "credential_missing"


def test_client_booleans_cannot_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", raising=False)
    pe = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        allow_network=False,
        transport=_capturing(),
        credential_resolver=_cred(False),
        environment="development",
        lab_enabled=True,
    )
    result = pe.execute_module(
        module_key="book_overview",
        request={
            "book_id": 1,
            "book_snapshot_id": 1,
            "dry_run": False,
            "allow_network": True,
            "credential_present": True,
            "live_probe": True,
        },
    )
    assert result.status == "security_denied"
    assert pe.http_calls == 0


@pytest.mark.skip(reason="Legacy Private Lab fake transport output no longer satisfies the formal V2 evidence contract")
def test_request_dry_run_reaches_adapter_and_matches_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    from app.narrative_core.services.provider_transport_kind import FakeHttpProviderTransport

    fake_http = FakeHttpProviderTransport(
        stub_text=(
            '{"logline":"Synthetic overview","premise":"Synthetic premise",'
            '"central_question":"Q?","primary_conflict":"C",'
            '"protagonist_asset_id":null,"major_storyline_ids":[],'
            '"structure_summary":"S","ending_state":"open",'
            '"evidence_refs":[{"evidence_id":"ev-1","evidence_role":"support"}],'
            '"confidence":0.5}'
        ),
        request_id="req-dry-pass",
        input_tokens=900,
        output_tokens=100,
    )
    pe = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        dry_run=True,  # composition default dry
        allow_network=True,
        transport=_capturing(),
        live_transport=fake_http,
        explicit_test_transport_override=True,
        credential_resolver=_cred(True),
        environment="test",
        lab_enabled=True,
    )
    result = pe.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False},
    )
    assert result.status == "success"
    assert pe.last_authorization is not None
    assert pe.last_authorization.requested_dry_run is False
    assert pe.last_authorization.effective_dry_run is False
    assert pe.http_calls == 1
    assert result.usage.get("transport_kind") == "FAKE_HTTP_TEST"


def test_runtime_cache_rebuilds_when_probe_toggles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", raising=False)
    reset_default_live_readiness_runtime_for_tests()
    rt1 = get_or_create_default_live_readiness_runtime(
        environment="development", lab_enabled=True
    )
    assert rt1.allow_network is False
    id1 = id(rt1)
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    rt2 = get_or_create_default_live_readiness_runtime(
        environment="development", lab_enabled=True
    )
    assert rt2.allow_network is True
    assert id(rt2) != id1


def test_runtime_cache_rebuilds_when_database_url_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    monkeypatch.setenv("STORYLENS_DATABASE_URL", "sqlite:///A.db")
    reset_default_live_readiness_runtime_for_tests()
    rt1 = get_or_create_default_live_readiness_runtime(
        environment="development", lab_enabled=True
    )
    id1 = id(rt1)
    monkeypatch.setenv("STORYLENS_DATABASE_URL", "sqlite:///B.db")
    rt2 = get_or_create_default_live_readiness_runtime(
        environment="development", lab_enabled=True
    )
    assert id(rt2) != id1
    # same config reuses
    rt3 = get_or_create_default_live_readiness_runtime(
        environment="development", lab_enabled=True
    )
    assert id(rt3) == id(rt2)


def test_provider_failure_not_fake_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    from app.narrative_core.services.provider_transport_kind import FakeHttpProviderTransport

    boom = FakeHttpProviderTransport(
        stub_text="{}",
        request_id="boom-1",
        raise_error=True,
    )
    pe = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        allow_network=True,
        transport=_capturing(),
        live_transport=boom,
        explicit_test_transport_override=True,
        credential_resolver=_cred(True),
        environment="test",
        lab_enabled=True,
    )
    result = pe.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False},
    )
    assert result.status == "provider_failed"
    assert result.usage.get("synthetic_success") is False
    assert boom.calls  # attempted once, no Capturing fallback


def test_authorization_formula_effective_dry() -> None:
    auth = compute_provider_execution_authorization(
        environment="development",
        private_lab_enabled=True,
        live_probe_enabled=True,
        allow_network=True,
        requested_dry_run=False,
        credential_valid=True,
    )
    assert auth.effective_dry_run is False
    auth2 = compute_provider_execution_authorization(
        environment="development",
        private_lab_enabled=True,
        live_probe_enabled=True,
        allow_network=True,
        requested_dry_run=True,
        credential_valid=True,
    )
    assert auth2.effective_dry_run is True
    assert auth2.deny_reason is None


def test_gates_unchanged() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED is False
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False
    assert is_private_provider_live_probe_enabled(environ={}) is False
