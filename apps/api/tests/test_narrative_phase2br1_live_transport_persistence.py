"""Phase 2B-R1 CHG-051 — Live Transport, Persistence binding, completion gates.

All Live branches use FakeHttpProviderTransport — zero internet.
"""

from __future__ import annotations

import json

import pytest

from app.narrative_core.services.private_lab_run_executor import PrivateLabRunExecutor
from app.narrative_core.services.private_lab_service_adapters import (
    PrivateLabProviderExecutionServiceAdapter,
)
from app.narrative_core.services.private_whole_book_live_readiness_runtime import (
    create_live_readiness_runtime,
    reset_default_live_readiness_runtime_for_tests,
)
from app.narrative_core.services.provider_input_bundle_resolver import (
    FakeProviderInputBundleResolver,
)
from app.narrative_core.services.provider_transport_kind import (
    FakeHttpProviderTransport,
    ProviderTransportKind,
    is_capturing_transport,
    live_transport_allowed,
    transport_kind_of,
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
from app.narrative_core.run_shell_contract.private_engine_lab import (
    PrivateEngineLabDenyReason,
)
from app.narrative_core.services.private_engine_lab_run_service import (
    PrivateWholeBookLabRunError,
)


class _FakeKeyStore:
    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._map = dict(mapping or {})

    def available(self) -> bool:
        return True

    def get(self, provider_kind: str) -> str | None:
        return self._map.get(provider_kind)


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch):
    reset_default_live_readiness_runtime_for_tests()
    monkeypatch.delenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", raising=False)
    yield
    reset_default_live_readiness_runtime_for_tests()


def _cred(present: bool = True) -> ExistingCredentialServiceAdapter:
    store = _FakeKeyStore({"aliyun_qwen_plus": "sk-test-not-real"} if present else {})
    return ExistingCredentialServiceAdapter(store=store, enabled=True)


def _capturing() -> CapturingProviderTransport:
    return CapturingProviderTransport(
        stub=StubTransportResponse(
            text='{"synthetic":true,"partial":true,"items":[]}',
            model="qwen3.7-plus",
            request_id="cap-stub",
            input_tokens=24,
            output_tokens=12,
            transport_kind="CAPTURING_TEST",
        )
    )


def _fake_http(**kwargs) -> FakeHttpProviderTransport:
    defaults = dict(
        stub_text=json.dumps(
            {
                "overview": "test overview",
                "partial": False,
                "items": [{"id": "a1"}],
                "evidence_candidates": [
                    {
                        "claim_id": "overview-1",
                        "chapter_id": "1",
                        "stable_paragraph_id": "1",
                        "role": "support",
                    }
                ],
            }
        ),
        request_id="fake-http-1",
        input_tokens=1800,
        output_tokens=300,
        http_status=200,
    )
    defaults.update(kwargs)
    return FakeHttpProviderTransport(**defaults)


def test_transport_kind_capturing_vs_fake_vs_real() -> None:
    cap = _capturing()
    fake = _fake_http()
    assert transport_kind_of(cap) == ProviderTransportKind.CAPTURING_TEST
    assert is_capturing_transport(cap)
    assert transport_kind_of(fake) == ProviderTransportKind.FAKE_HTTP_TEST
    ok, deny, kind = live_transport_allowed(
        transport=cap, environment="development", explicit_test_override=False
    )
    assert not ok and deny == "capturing_transport_forbidden_on_live"
    ok, _, kind = live_transport_allowed(
        transport=None, environment="development"
    )
    assert ok and kind == ProviderTransportKind.REAL_HTTP
    ok, _, kind = live_transport_allowed(
        transport=fake, environment="test", explicit_test_override=False
    )
    assert ok and kind == ProviderTransportKind.FAKE_HTTP_TEST


def test_dry_estimate_uses_capturing_zero_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", raising=False)
    cap = _capturing()
    pe = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        allow_network=False,
        transport=cap,
        credential_resolver=_cred(True),
        environment="development",
        lab_enabled=True,
    )
    result = pe.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": True},
    )
    assert result.status == "success"
    assert pe.http_calls == 0
    assert result.usage.get("http") is False


def test_live_rejects_capturing_and_stub_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    cap = _capturing()
    pe = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        allow_network=True,
        transport=cap,
        # live_transport defaults None → REAL_HTTP path, but no real network in unit:
        # without live_transport Fake, Bailian would try REAL_HTTP and need endpoint.
        # Explicitly set capturing as live to prove rejection.
        live_transport=cap,
        credential_resolver=_cred(True),
        environment="development",
        lab_enabled=True,
    )
    result = pe.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False},
    )
    assert result.status == "security_denied"
    assert pe.http_calls == 0
    assert len(cap.calls) == 0
    assert result.usage.get("input_tokens") in (None, 0)


def test_live_fake_http_once_not_stub_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    cap = _capturing()
    fake = _fake_http(input_tokens=2222, output_tokens=333)
    pe = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        allow_network=True,
        transport=cap,
        live_transport=fake,
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
    assert pe.http_calls == 1
    assert len(fake.calls) == 1
    assert len(cap.calls) == 0
    assert result.usage.get("transport_kind") == "FAKE_HTTP_TEST"
    assert result.usage.get("provider_request_id") == "fake-http-1"
    assert result.usage.get("http_status") == 200
    assert result.usage.get("input_tokens") == 2222
    assert result.usage.get("output_tokens") == 333
    assert result.usage.get("usage_source") == "provider_response"
    assert result.usage.get("live_request_confirmed") is True


def test_provider_failure_does_not_fallback_capturing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    cap = _capturing()
    fake = _fake_http(raise_error=True)
    pe = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        allow_network=True,
        transport=cap,
        live_transport=fake,
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
    assert len(cap.calls) == 0


def test_production_and_probe_off_and_dry_and_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    fake = _fake_http()
    pe_prod = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        allow_network=True,
        transport=_capturing(),
        live_transport=fake,
        explicit_test_transport_override=True,
        credential_resolver=_cred(True),
        environment="production",
        lab_enabled=True,
    )
    # production auth should deny via environment gate
    r = pe_prod.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False},
    )
    assert r.status == "security_denied"
    assert pe_prod.http_calls == 0

    monkeypatch.delenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", raising=False)
    pe = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        allow_network=True,
        live_transport=fake,
        explicit_test_transport_override=True,
        credential_resolver=_cred(True),
        environment="test",
        lab_enabled=True,
    )
    r = pe.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False},
    )
    assert r.status == "security_denied"
    assert pe.http_calls == 0

    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    pe_dry = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        allow_network=True,
        live_transport=fake,
        explicit_test_transport_override=True,
        credential_resolver=_cred(True),
        environment="test",
        lab_enabled=True,
    )
    r = pe_dry.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": True},
    )
    assert pe_dry.http_calls == 0

    pe_cred = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        allow_network=True,
        live_transport=fake,
        explicit_test_transport_override=True,
        credential_resolver=_cred(False),
        environment="test",
        lab_enabled=True,
    )
    r = pe_cred.execute_module(
        module_key="book_overview",
        request={"book_id": 1, "book_snapshot_id": 1, "dry_run": False},
    )
    assert r.status == "security_denied"
    assert pe_cred.http_calls == 0


def test_live_completion_gates_require_usage_orm_evidence() -> None:
    ex = PrivateLabRunExecutor.__new__(PrivateLabRunExecutor)
    with pytest.raises(PrivateWholeBookLabRunError) as ei:
        PrivateLabRunExecutor._assert_live_module_success(
            ex,
            usage_status="success",
            usage={
                "transport_kind": "FAKE_HTTP_TEST",
                "provider_request_id": "x",
                "live_request_confirmed": True,
                "synthetic_success": False,
            },
            validation_summary={"accepted": True},
            evidence_summary={"count": 0, "validated": True},
            persistence_summary={"orm_written": True},
            pipeline_status="completed",
            run_id=1,
        )
    assert ei.value.detail_code == "LIVE_EVIDENCE_REQUIRED"

    with pytest.raises(PrivateWholeBookLabRunError) as ei2:
        PrivateLabRunExecutor._assert_live_module_success(
            ex,
            usage_status="success",
            usage={
                "transport_kind": "CAPTURING_TEST",
                "provider_request_id": "x",
                "live_request_confirmed": True,
            },
            validation_summary={"accepted": True},
            evidence_summary={"count": 1},
            persistence_summary={"orm_written": True},
            pipeline_status="completed",
            run_id=1,
        )
    assert ei2.value.detail_code == "LIVE_CAPTURING_TRANSPORT"

    with pytest.raises(PrivateWholeBookLabRunError) as ei3:
        PrivateLabRunExecutor._assert_live_module_success(
            ex,
            usage_status="success",
            usage={
                "transport_kind": "FAKE_HTTP_TEST",
                "provider_request_id": "x",
                "live_request_confirmed": True,
            },
            validation_summary={"accepted": True},
            evidence_summary={"count": 1},
            persistence_summary={"orm_written": False, "fallback": "port_only"},
            pipeline_status="completed",
            run_id=1,
        )
    assert ei3.value.detail_code == "LIVE_ORM_WRITTEN_REQUIRED"

    # Happy path does not raise
    PrivateLabRunExecutor._assert_live_module_success(
        ex,
        usage_status="success",
        usage={
            "transport_kind": "FAKE_HTTP_TEST",
            "provider_request_id": "x",
            "live_request_confirmed": True,
            "synthetic_success": False,
        },
        validation_summary={"accepted": True},
        evidence_summary={"count": 2, "coverage_incomplete": False},
        persistence_summary={"orm_written": True},
        pipeline_status="completed",
        run_id=1,
    )


def test_live_persistence_capability_checked_before_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recording/port_only runtime must fail closed before Provider HTTP."""

    class _Prov:
        http_calls = 0

        def execute_module(self, **kwargs):  # noqa: ANN003
            self.http_calls += 1
            raise AssertionError("provider must not be called")

        def cancel(self, ref: str) -> None:
            return None

    # Minimal executor with recording persistence and no session DB work.
    class _Sess:
        def get(self, *a, **k):
            return None

        def commit(self):
            return None

    ex = PrivateLabRunExecutor(
        _Sess(),  # type: ignore[arg-type]
        provider_port=_Prov(),  # type: ignore[arg-type]
        use_recording_persistence=True,
        runtime_factory=lambda **kwargs: object(),
    )
    # Fake run/meta/stage objects
    class _Run:
        id = 9
        book_id = 1
        book_snapshot_id = 1

    class _Stage:
        id = 3
        stage_key = "analyze_structure"
        attempt_count = 0

    with pytest.raises(PrivateWholeBookLabRunError) as ei:
        ex._execute_module(
            run=_Run(),  # type: ignore[arg-type]
            meta={"dry_run": False},
            stage=_Stage(),
            module_key="book_overview",
            cancellation_ref=None,
        )
    assert ei.value.detail_code == "LIVE_PERSISTENCE_CAPABILITY_MISSING"
    assert _Prov.http_calls == 0


def test_gates_unchanged() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED is False
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False


def test_runtime_wires_live_transport_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "true")
    fake = _fake_http()
    rt = create_live_readiness_runtime(
        environment="test",
        lab_enabled=True,
        transport=_capturing(),
        live_transport=fake,
        explicit_test_transport_override=True,
        credential_adapter=_cred(True),
        allow_fake_resolver=True,
        resolver=FakeProviderInputBundleResolver(),
    )
    pe = rt.provider_execution
    assert pe is not None
    assert pe.live_transport is fake
    assert pe.explicit_test_transport_override is True
