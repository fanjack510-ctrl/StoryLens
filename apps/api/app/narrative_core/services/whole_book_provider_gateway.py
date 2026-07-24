"""WholeBook Provider Gateway foundation (Phase 2B Agent P).

Fake Provider only — no Bailian/OpenAI/llama-server/DeepSeek/Qwen HTTP.
Credentials resolve only at execute boundary; never enter Request DTOs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol, runtime_checkable

from app.narrative_core.contracts.engine_io import BudgetGuard
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineErrorCode,
    private_engine_error,
)
from app.narrative_core.private_engine_contract.provider_gateway import (
    FORBIDDEN_PROVIDER_REQUEST_KEYS,
    NormalizedProviderUsage,
    ProviderEstimate,
    ProviderGatewayHealth,
    ProviderInferenceRequest,
    ProviderInferenceResponse,
)
from app.services.credentials.base import CredentialStore

logger = logging.getLogger(__name__)

_NETWORK_FORBIDDEN = True  # Phase 2B: gateway must not emit network requests.


@runtime_checkable
class ProviderCredentialResolver(Protocol):
    """Resolve credentials only inside Gateway execute boundary."""

    def resolve(self, provider_kind: str) -> str | None: ...


@dataclass
class NoCredentialFakeResolver:
    """Fake path: never calls real Credential Service."""

    def resolve(self, provider_kind: str) -> str | None:
        _ = provider_kind
        return None


@dataclass
class ExistingCredentialServiceAdapter:
    """Skeleton adapter over existing CredentialStore — does not alter key storage."""

    store: CredentialStore | None = None
    enabled: bool = False  # Phase 2B Fake gateway keeps this off by default

    def resolve(self, provider_kind: str) -> str | None:
        if not self.enabled or self.store is None:
            return None
        if not self.store.available():
            return None
        # Never log or return into DTO; caller must keep secret ephemeral.
        return self.store.get(provider_kind)


@runtime_checkable
class ProviderAdapter(Protocol):
    provider_kind: str

    def estimate(self, request: ProviderInferenceRequest) -> ProviderEstimate: ...

    def execute(self, request: ProviderInferenceRequest) -> ProviderInferenceResponse: ...

    def cancel(self, cancellation_ref: str) -> bool: ...

    def health_check(self) -> ProviderGatewayHealth: ...


@dataclass
class FakeProviderAdapter:
    """Deterministic Fake provider adapter — no network, no real credentials."""

    provider_kind: str = "fake"
    cancelled: set[str] = field(default_factory=set)
    fail_next: bool = False
    allow_network: bool = False
    calls: int = 0

    def __post_init__(self) -> None:
        if self.allow_network:
            raise ValueError("FakeProviderAdapter forbids network")

    def estimate(self, request: ProviderInferenceRequest) -> ProviderEstimate:
        _assert_request_safe(request)
        return ProviderEstimate(
            request_id=request.request_id,
            estimated_input_tokens=16,
            estimated_output_tokens=32,
            estimated_cost=0.0,
            within_budget=True,
        )

    def execute(self, request: ProviderInferenceRequest) -> ProviderInferenceResponse:
        _assert_request_safe(request)
        self.calls += 1
        if request.cancellation_ref and request.cancellation_ref in self.cancelled:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)
        if self.fail_next:
            self.fail_next = False
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)
        structured = {
            "fake": True,
            "synthetic": True,
            "schema_ref": request.response_schema_ref,
            "task_type": request.task_type,
        }
        _validate_structured_output(structured)
        return ProviderInferenceResponse(
            request_id=request.request_id,
            provider_kind=self.provider_kind,
            model_id="fake-model",
            provider_request_id=f"fake-{request.request_id}",
            status="success",
            structured_output=structured,
            token_input=16,
            token_output=32,
            cost=0.0,
            latency_ms=1,
            finish_reason="stop",
            retry_count=0,
            validation_status="schema_ok",
            received_at=datetime(2026, 7, 23, 0, 0, 0),
        )

    def cancel(self, cancellation_ref: str) -> bool:
        self.cancelled.add(cancellation_ref)
        return True

    def health_check(self) -> ProviderGatewayHealth:
        return ProviderGatewayHealth(
            provider_kind=self.provider_kind,
            healthy=True,
            status="ok",
            details=("fake", "no_network", "no_model_call", "synthetic"),
        )


@dataclass
class ProviderAdapterRegistry:
    _adapters: dict[str, ProviderAdapter] = field(default_factory=dict)

    def register(self, adapter: ProviderAdapter) -> None:
        self._adapters[adapter.provider_kind] = adapter

    def get(self, provider_kind: str) -> ProviderAdapter:
        adapter = self._adapters.get(provider_kind)
        if adapter is None:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_UNAVAILABLE)
        return adapter

    def list_kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))


@dataclass
class DefaultWholeBookProviderGateway:
    """Default gateway: Fake adapters only in Phase 2B."""

    credential_resolver: ProviderCredentialResolver = field(default_factory=NoCredentialFakeResolver)
    budget_guard: BudgetGuard | None = None
    registry: ProviderAdapterRegistry | None = None
    allow_network: bool = False
    _cancelled: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.allow_network or not _NETWORK_FORBIDDEN:
            raise ValueError("Phase 2B Provider Gateway forbids network requests")
        if self.registry is None:
            self.registry = ProviderAdapterRegistry()
            self.registry.register(FakeProviderAdapter())

    def validate_policy(self, policy: Mapping[str, Any]) -> None:
        _assert_no_credentials(policy)
        kind = str(policy.get("provider_kind") or "").strip()
        route = str(policy.get("model_route") or "").strip()
        if not kind and not route:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_POLICY_INVALID)
        if kind and kind not in {"fake", "test"} and "fake" not in kind:
            # Real provider kinds are not implemented in this phase.
            raise private_engine_error(
                PrivateEngineErrorCode.PROVIDER_UNAVAILABLE,
                detail_code="real_provider_not_implemented",
            )

    def estimate(self, request: ProviderInferenceRequest) -> ProviderEstimate:
        _assert_request_safe(request)
        self.validate_policy(
            {
                "provider_kind": request.provider_kind,
                "model_route": request.model_route,
                **dict(request.metadata),
            }
        )
        assert self.registry is not None
        adapter = self.registry.get(request.provider_kind)
        estimate = adapter.estimate(request)
        if self.budget_guard is not None:
            ok = self.budget_guard.check_budget(
                stage_key=str(request.task_type),
                estimated_tokens=estimate.estimated_input_tokens + estimate.estimated_output_tokens,
            )
            if not ok:
                return ProviderEstimate(
                    request_id=request.request_id,
                    estimated_input_tokens=estimate.estimated_input_tokens,
                    estimated_output_tokens=estimate.estimated_output_tokens,
                    estimated_cost=estimate.estimated_cost,
                    within_budget=False,
                )
        return estimate

    def execute(self, request: ProviderInferenceRequest) -> ProviderInferenceResponse:
        _assert_request_safe(request)
        self.validate_policy(
            {
                "provider_kind": request.provider_kind,
                "model_route": request.model_route,
            }
        )
        if request.cancellation_ref and request.cancellation_ref in self._cancelled:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)

        # Credential resolve at boundary only — never inject into request DTO.
        secret = self.credential_resolver.resolve(request.provider_kind)
        if secret is not None:
            # Fake path should not need secrets; ensure we never log them.
            _ = bool(secret)
            secret = None

        assert self.registry is not None
        adapter = self.registry.get(request.provider_kind)
        retry_limit = int(request.retry_policy.get("max_retries") or 0)
        retry_count = 0
        last_error: Exception | None = None
        while retry_count <= retry_limit:
            if request.cancellation_ref and request.cancellation_ref in self._cancelled:
                raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)
            if self.budget_guard is not None:
                ok = self.budget_guard.check_budget(stage_key=request.task_type, estimated_tokens=16)
                if not ok:
                    raise private_engine_error(PrivateEngineErrorCode.PROVIDER_BUDGET_EXCEEDED)
            try:
                response = adapter.execute(request)
                if response.status != "success":
                    # Never forge success.
                    raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)
                if response.structured_output is None:
                    raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)
                _validate_structured_output(response.structured_output)
                if self.budget_guard is not None:
                    self.budget_guard.record_spend(
                        stage_key=request.task_type,
                        tokens=response.token_input + response.token_output,
                        cost_usd=float(response.cost or 0.0),
                    )
                if retry_count:
                    return ProviderInferenceResponse(
                        request_id=response.request_id,
                        provider_kind=response.provider_kind,
                        model_id=response.model_id,
                        provider_request_id=response.provider_request_id,
                        status=response.status,
                        structured_output=response.structured_output,
                        token_input=response.token_input,
                        token_output=response.token_output,
                        cost=response.cost,
                        latency_ms=response.latency_ms,
                        finish_reason=response.finish_reason,
                        retry_count=retry_count,
                        validation_status=response.validation_status,
                        received_at=response.received_at,
                    )
                return response
            except Exception as exc:
                last_error = exc
                retry_count += 1
                if retry_count > retry_limit:
                    break
                if self.budget_guard is not None:
                    ok = self.budget_guard.check_budget(stage_key=request.task_type, estimated_tokens=16)
                    if not ok:
                        raise private_engine_error(PrivateEngineErrorCode.PROVIDER_BUDGET_EXCEEDED) from exc
        if last_error is not None:
            raise last_error
        raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)

    def cancel(self, cancellation_ref: str) -> bool:
        self._cancelled.add(cancellation_ref)
        assert self.registry is not None
        ok = False
        for kind in self.registry.list_kinds():
            ok = self.registry.get(kind).cancel(cancellation_ref) or ok
        return ok

    def health_check(self, provider_kind: str) -> ProviderGatewayHealth:
        assert self.registry is not None
        return self.registry.get(provider_kind).health_check()

    def normalize_usage(self, response: ProviderInferenceResponse) -> NormalizedProviderUsage:
        return NormalizedProviderUsage(
            provider_input_tokens=response.token_input,
            provider_output_tokens=response.token_output,
            cached_tokens=0,
            provider_cost=response.cost,
            retries=response.retry_count,
            synthetic=True,
        )


def _assert_no_credentials(mapping: Mapping[str, Any]) -> None:
    for key in mapping:
        lowered = str(key).lower()
        if lowered in FORBIDDEN_PROVIDER_REQUEST_KEYS or lowered.endswith("_api_key"):
            raise ValueError(f"credential-like key forbidden in provider DTO: {key}")


def _assert_request_safe(request: ProviderInferenceRequest) -> None:
    # Dataclass construction already blocks credential fields; re-check mappings.
    for mapping in (
        request.temperature_policy,
        request.timeout_policy,
        request.retry_policy,
        request.data_handling_policy,
        request.metadata,
    ):
        _assert_no_credentials(mapping)
    serialized = repr(request)
    for token in ("api_key", "sk-", "authorization:", "bearer "):
        if token in serialized.lower():
            raise ValueError("credential leak detected in provider request serialization")


def _validate_structured_output(output: Mapping[str, Any]) -> None:
    if not isinstance(output, Mapping):
        raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)
    _assert_no_credentials(output)
    # Minimal schema: Fake responses must mark synthetic/fake.
    if not (output.get("fake") is True or output.get("synthetic") is True):
        # Still accept schema_ref-only for extensibility, but require mapping.
        if "schema_ref" not in output:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)


def assert_no_credential_in_logs(log_text: str) -> None:
    lower = log_text.lower()
    for token in ("api_key", "sk-", "authorization:", "bearer ", "credential="):
        if token in lower:
            raise AssertionError("credential must not appear in logs")
