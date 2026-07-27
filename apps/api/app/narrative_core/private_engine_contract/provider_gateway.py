"""WholeBookProviderGateway Protocol + Fake provider (Phase 2B-P).

Credential NEVER enters request DTOs. Instruction and source_data are separated.
No tools/network from model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol, runtime_checkable

from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineErrorCode,
    private_engine_error,
)
from app.narrative_core.private_engine_contract.protocol import assert_mapping_has_no_forbidden_keys

PROVIDER_GATEWAY_PROTOCOL_METHODS: tuple[str, ...] = (
    "validate_policy",
    "estimate",
    "execute",
    "cancel",
    "health_check",
    "normalize_usage",
)

FORBIDDEN_PROVIDER_REQUEST_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "credential",
        "credentials",
        "authorization",
        "bearer",
        "secret",
        "token",  # raw auth token — not provider_request_id
    }
)


@dataclass(frozen=True, slots=True)
class ProviderInferenceRequest:
    request_id: str
    provider_kind: str
    model_route: str
    task_type: str
    system_instruction_ref: str
    prompt_pack_ref: str
    input_bundle_ref: str  # source_data only — never merged into instruction
    response_schema_ref: str
    temperature_policy: Mapping[str, Any]
    token_budget: int | None
    cost_budget: float | None
    timeout_policy: Mapping[str, Any]
    retry_policy: Mapping[str, Any]
    cancellation_ref: str | None
    data_handling_policy: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id is required")
        if not self.system_instruction_ref.strip():
            raise ValueError("system_instruction_ref is required")
        if not self.input_bundle_ref.strip():
            raise ValueError("input_bundle_ref (source_data) is required")
        if self.system_instruction_ref == self.input_bundle_ref:
            raise ValueError("instruction_ref and input_bundle_ref must stay isolated")
        for mapping in (
            self.temperature_policy,
            self.timeout_policy,
            self.retry_policy,
            self.data_handling_policy,
            self.metadata,
        ):
            _assert_no_credentials(mapping)
        # Explicit attribute absence of credential fields is part of the contract.


@dataclass(frozen=True, slots=True)
class ProviderInferenceResponse:
    request_id: str
    provider_kind: str
    model_id: str
    provider_request_id: str | None
    status: str
    structured_output: Mapping[str, Any] | None
    token_input: int
    token_output: int
    cost: float | None
    latency_ms: int
    finish_reason: str | None
    retry_count: int
    validation_status: str
    received_at: datetime

    def __post_init__(self) -> None:
        if self.token_input < 0 or self.token_output < 0:
            raise ValueError("token counts must be >= 0")
        if self.retry_count < 0:
            raise ValueError("retry_count must be >= 0")
        if self.status == "success" and self.structured_output is None:
            # Fake may return empty structured_output only when explicitly invalid.
            pass


@dataclass(frozen=True, slots=True)
class ProviderEstimate:
    request_id: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost: float | None
    within_budget: bool


@dataclass(frozen=True, slots=True)
class ProviderGatewayHealth:
    provider_kind: str
    healthy: bool
    status: str
    details: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NormalizedProviderUsage:
    provider_input_tokens: int
    provider_output_tokens: int
    cached_tokens: int
    provider_cost: float | None
    retries: int
    synthetic: bool = False


def _assert_no_credentials(mapping: Mapping[str, Any]) -> None:
    for key in mapping:
        lowered = str(key).lower()
        if lowered in FORBIDDEN_PROVIDER_REQUEST_KEYS or lowered.endswith("_api_key"):
            raise ValueError(f"credential-like key forbidden in provider DTO: {key}")
    assert_mapping_has_no_forbidden_keys(mapping, label="provider_mapping")


@runtime_checkable
class WholeBookProviderGateway(Protocol):
    def validate_policy(self, policy: Mapping[str, Any]) -> None: ...

    def estimate(self, request: ProviderInferenceRequest) -> ProviderEstimate: ...

    def execute(self, request: ProviderInferenceRequest) -> ProviderInferenceResponse: ...

    def cancel(self, cancellation_ref: str) -> bool: ...

    def health_check(self, provider_kind: str) -> ProviderGatewayHealth: ...

    def normalize_usage(self, response: ProviderInferenceResponse) -> NormalizedProviderUsage: ...


@dataclass
class FakeProviderGateway:
    """Deterministic Fake provider — no network, no credentials, no model calls."""

    cancelled: set[str] = field(default_factory=set)
    fail_next: bool = False
    allow_tools: bool = False  # contract: tools/network from model forbidden
    allow_network: bool = False

    def __post_init__(self) -> None:
        if self.allow_tools or self.allow_network:
            raise ValueError("FakeProviderGateway forbids tools/network from model")

    def validate_policy(self, policy: Mapping[str, Any]) -> None:
        _assert_no_credentials(policy)
        if not policy.get("provider_kind") and not policy.get("model_route"):
            # Minimal shape: at least one routing key.
            if "fake" not in str(policy).lower() and not policy:
                raise private_engine_error(PrivateEngineErrorCode.PROVIDER_POLICY_INVALID)

    def estimate(self, request: ProviderInferenceRequest) -> ProviderEstimate:
        _assert_no_credentials(request.metadata)
        return ProviderEstimate(
            request_id=request.request_id,
            estimated_input_tokens=16,
            estimated_output_tokens=32,
            estimated_cost=0.0,
            within_budget=True,
        )

    def execute(self, request: ProviderInferenceRequest) -> ProviderInferenceResponse:
        if request.cancellation_ref and request.cancellation_ref in self.cancelled:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)
        if self.fail_next:
            self.fail_next = False
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)
        return ProviderInferenceResponse(
            request_id=request.request_id,
            provider_kind=request.provider_kind,
            model_id="fake-model",
            provider_request_id=f"fake-{request.request_id}",
            status="success",
            structured_output={"fake": True, "schema_ref": request.response_schema_ref},
            token_input=16,
            token_output=32,
            cost=0.0,
            latency_ms=1,
            finish_reason="stop",
            retry_count=0,
            validation_status="pending_schema",
            received_at=datetime(2026, 7, 23, 0, 0, 0),
        )

    def cancel(self, cancellation_ref: str) -> bool:
        self.cancelled.add(cancellation_ref)
        return True

    def health_check(self, provider_kind: str) -> ProviderGatewayHealth:
        return ProviderGatewayHealth(
            provider_kind=provider_kind,
            healthy=True,
            status="ok",
            details=("fake", "no_network", "no_credentials"),
        )

    def normalize_usage(self, response: ProviderInferenceResponse) -> NormalizedProviderUsage:
        return NormalizedProviderUsage(
            provider_input_tokens=response.token_input,
            provider_output_tokens=response.token_output,
            cached_tokens=0,
            provider_cost=response.cost,
            retries=response.retry_count,
            synthetic=True,
        )
