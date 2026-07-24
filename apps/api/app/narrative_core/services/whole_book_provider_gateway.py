"""WholeBook Provider Gateway foundation (Phase 2B / 2B-R / 2B-R1).

Fake Provider remains default. Bailian OpenAI-compatible adapter is available
under Private Engine Lab authorization only. Credentials resolve only at
execute boundary; never enter Request DTOs or logs.

Phase 2B-R1: live path consumes ResolvedProviderPayload messages (not ref-only).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

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
from app.narrative_core.private_engine_contract.provider_input import (
    ProviderInputBundle,
    ResolvedProviderPayload,
)
from app.narrative_core.run_shell_contract.private_engine_lab import (
    PRIVATE_LAB_FIRST_MODEL_ID,
    PRIVATE_LAB_FIRST_PROVIDER_KEY,
    PRIVATE_PROVIDER_LIVE_PROBE_ENV,
)
from app.services.credentials.base import CredentialStore

logger = logging.getLogger(__name__)


@dataclass
class ProviderPayloadRegistry:
    """Process-local binding of resolved payloads — never persisted / logged."""

    _bindings: dict[str, ResolvedProviderPayload] = field(default_factory=dict)

    def bind(self, request_id: str, payload: ResolvedProviderPayload) -> None:
        if not request_id.strip():
            raise ValueError("request_id is required")
        self._bindings[request_id] = payload

    def take(self, request_id: str) -> ResolvedProviderPayload | None:
        return self._bindings.pop(request_id, None)

    def get(self, request_id: str) -> ResolvedProviderPayload | None:
        return self._bindings.get(request_id)

    def clear(self) -> None:
        self._bindings.clear()


PAYLOAD_REGISTRY = ProviderPayloadRegistry()


@dataclass
class StubTransportResponse:
    text: str
    model: str | None = None
    request_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str | None = "stop"
    http_status: int | None = None
    transport_kind: str | None = None
    latency_ms: int | None = None
    host: str | None = None


@dataclass
class CapturingProviderTransport:
    """Test/dry transport: captures messages, returns stub — never opens HTTP.

    Forbidden on authorized Live (CHG-051).
    """

    stub: StubTransportResponse | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    raise_timeout: bool = False
    cancelled_refs: set[str] = field(default_factory=set)
    transport_kind: str = "CAPTURING_TEST"
    test_only: bool = True
    network_capable: bool = False

    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        response_format_mode: str,
        max_tokens: int | None,
        timeout_seconds: int,
        cancellation_ref: str | None = None,
    ) -> StubTransportResponse:
        # Capture structure only — do not store full message bodies in long-lived logs.
        self.calls.append(
            {
                "message_count": len(messages),
                "roles": [m.get("role") for m in messages],
                "model": model,
                "response_format_mode": response_format_mode,
                "max_tokens": max_tokens,
                "timeout_seconds": timeout_seconds,
                "has_system": any(m.get("role") == "system" for m in messages),
                "has_user": any(m.get("role") == "user" for m in messages),
                "total_chars": sum(len(m.get("content") or "") for m in messages),
            }
        )
        if cancellation_ref and cancellation_ref in self.cancelled_refs:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)
        if self.raise_timeout:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_TIMEOUT)
        if self.stub is None:
            raise private_engine_error(
                PrivateEngineErrorCode.PROVIDER_UNAVAILABLE,
                detail_code="transport_stub_missing",
            )
        return self.stub


@runtime_checkable
class ProviderTransport(Protocol):
    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        response_format_mode: str,
        max_tokens: int | None,
        timeout_seconds: int,
        cancellation_ref: str | None = None,
    ) -> Any: ...

# Default gateway path forbids network. Lab factory may authorize explicitly.
_NETWORK_FORBIDDEN_DEFAULT = True

_REAL_PROVIDER_KINDS: frozenset[str] = frozenset(
    {
        "aliyun_qwen_plus",
        "aliyun_qwen_max",
        "aliyun_qwen_flash",
    }
)


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
    """Adapter over existing CredentialStore — does not alter key storage.

    Enable only at Lab/real execute boundary. Never put secrets into Request DTOs.
    """

    store: CredentialStore | None = None
    enabled: bool = False  # Default off; Lab enables when authorized

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
        _validate_structured_output(structured, require_synthetic=True)
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
class CloudBudgetGuardBridge:
    """Bridge BudgetGuard Protocol to existing cloud_budget / daily limits.

    Stops immediately on deny. Never logs credentials or novel body.
    """

    session_factory: Callable[[], Any] | None = None
    cloud_enabled: bool = True
    budget: dict[str, Any] | None = None
    pricing: dict[str, Any] | None = None
    force_deny: bool = False
    spent_tokens: int = 0
    spent_cost: float = 0.0
    checks: list[dict[str, Any]] = field(default_factory=list)

    def check_budget(self, *, stage_key: str, estimated_tokens: int = 0) -> bool:
        if self.force_deny:
            self.checks.append(
                {
                    "stage_key": stage_key,
                    "estimated_tokens": int(estimated_tokens),
                    "allowed": False,
                    "reason": "force_deny",
                }
            )
            return False
        if self.session_factory is None:
            ok = True
            self.checks.append(
                {
                    "stage_key": stage_key,
                    "estimated_tokens": int(estimated_tokens),
                    "allowed": ok,
                    "reason": "no_session_pass",
                }
            )
            return ok
        try:
            from app.services.cloud_budget import cloud_block_reasons, daily_usage
            from app.services.cloud_pricing import pricing_status

            budget = self.budget or {
                "cloud_request_budget_enabled": True,
                "cloud_stop_on_unknown_pricing": False,
                "cloud_daily_request_limit": 50,
                "cloud_daily_token_limit": 200000,
                "cloud_daily_estimated_cost_limit": 1.0,
                "currency": "CNY",
            }
            pricing = self.pricing
            if pricing is None:
                pricing = pricing_status(Path("config/cloud_pricing.json"))
            session = self.session_factory()
            try:
                usage = daily_usage(session, budget, self.cloud_enabled, pricing)
                reasons = list(usage.get("blocked_reasons") or [])
                if not reasons:
                    reasons = cloud_block_reasons(
                        self.cloud_enabled,
                        budget,
                        pricing,
                        int(usage.get("request_count") or 0),
                        int(usage.get("total_tokens") or 0),
                        float(usage.get("estimated_cost") or 0.0),
                    )
                ok = not reasons
                self.checks.append(
                    {
                        "stage_key": stage_key,
                        "estimated_tokens": int(estimated_tokens),
                        "allowed": ok,
                        "blocked_reasons_count": len(reasons),
                    }
                )
                return ok
            finally:
                close = getattr(session, "close", None)
                if callable(close):
                    close()
        except Exception as exc:  # noqa: BLE001 — fail closed on budget bridge errors
            logger.warning("cloud budget bridge check failed (denied): %s", type(exc).__name__)
            self.checks.append(
                {
                    "stage_key": stage_key,
                    "estimated_tokens": int(estimated_tokens),
                    "allowed": False,
                    "reason": "bridge_error",
                }
            )
            return False

    def record_spend(self, *, stage_key: str, tokens: int = 0, cost_usd: float = 0.0) -> None:
        _ = stage_key
        self.spent_tokens += int(tokens)
        self.spent_cost += float(cost_usd)

    def deny(self) -> None:
        self.force_deny = True


@dataclass
class BailianOpenAICompatibleProviderAdapter:
    """Bailian / Aliyun OpenAI-compatible ProviderAdapter.

    Wraps existing OpenAICompatibleProvider. Default dry_run=True (no live HTTP).
    Live calls require allow_network + live probe env + credential at gateway boundary.
    Adapter does not read Snapshot ORM or Prompt files — only ResolvedProviderPayload.
    """

    provider_kind: str = PRIVATE_LAB_FIRST_PROVIDER_KEY
    model_id: str = PRIVATE_LAB_FIRST_MODEL_ID
    dry_run: bool = True
    allow_network: bool = False
    cancelled: set[str] = field(default_factory=set)
    calls: int = 0
    transport: Any | None = None
    pricing_resolver: Any | None = None
    output_repairer: Any | None = None
    payload_registry: ProviderPayloadRegistry = field(default_factory=lambda: PAYLOAD_REGISTRY)
    _ephemeral_credential: str | None = field(default=None, repr=False)
    last_raw_response_retained: bool = False

    def estimate(self, request: ProviderInferenceRequest) -> ProviderEstimate:
        _assert_request_safe(request)
        payload = self.payload_registry.get(request.request_id)
        if payload is not None and payload.input_bundle is not None:
            from app.narrative_core.services.whole_book_provider_estimate_service import (
                ProviderPricingResolver,
                WholeBookProviderEstimateService,
            )

            pricing = self.pricing_resolver or ProviderPricingResolver()
            result = WholeBookProviderEstimateService(pricing=pricing).estimate(payload.input_bundle)
            return ProviderEstimate(
                request_id=request.request_id,
                estimated_input_tokens=result.estimated_input_tokens,
                estimated_output_tokens=result.estimated_output_tokens,
                estimated_cost=result.cost.cost_expected,
                within_budget=result.context_limit_ok,
            )
        # Without resolved payload, refuse classic 512/256 Live placeholder.
        approx_in = max(64, int(request.token_budget or 0) or 64)
        return ProviderEstimate(
            request_id=request.request_id,
            estimated_input_tokens=approx_in,
            estimated_output_tokens=1024,
            estimated_cost=None,
            within_budget=True,
        )

    def execute(self, request: ProviderInferenceRequest) -> ProviderInferenceResponse:
        _assert_request_safe(request)
        self.calls += 1
        if request.cancellation_ref and request.cancellation_ref in self.cancelled:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)

        if self.dry_run or not self.allow_network or not _live_probe_enabled():
            # Dry path may still validate resolved payload shape when bound.
            payload = self.payload_registry.get(request.request_id)
            structured = {
                "dry_run": True,
                "provider_kind": self.provider_kind,
                "model_id": self.model_id,
                "schema_ref": request.response_schema_ref,
                "task_type": request.task_type,
                "synthetic": False,
                "resolved_payload_bound": payload is not None,
            }
            _validate_structured_output(structured, require_synthetic=False)
            return ProviderInferenceResponse(
                request_id=request.request_id,
                provider_kind=self.provider_kind,
                model_id=self.model_id,
                provider_request_id=f"dry-{request.request_id}",
                status="success",
                structured_output=structured,
                token_input=16,
                token_output=32,
                cost=0.0,
                latency_ms=1,
                finish_reason="stop",
                retry_count=0,
                validation_status="schema_ok",
                received_at=datetime(2026, 7, 24, 0, 0, 0),
            )

        secret = self._ephemeral_credential
        if not secret:
            raise private_engine_error(
                PrivateEngineErrorCode.PROVIDER_UNAVAILABLE,
                detail_code="credential_missing_at_execute_boundary",
            )
        try:
            return self._execute_live(request, api_key=secret)
        finally:
            # Ensure secret does not linger on adapter.
            self._ephemeral_credential = None

    def execute_with_credential(
        self,
        request: ProviderInferenceRequest,
        credential: str | None,
        *,
        resolved_payload: ResolvedProviderPayload | None = None,
    ) -> ProviderInferenceResponse:
        if resolved_payload is not None:
            self.payload_registry.bind(request.request_id, resolved_payload)
        self._ephemeral_credential = credential
        try:
            return self.execute(request)
        finally:
            self._ephemeral_credential = None

    def execute_with_resolved_payload(
        self,
        request: ProviderInferenceRequest,
        payload: ResolvedProviderPayload,
        *,
        credential: str | None = None,
    ) -> ProviderInferenceResponse:
        return self.execute_with_credential(request, credential, resolved_payload=payload)

    def _execute_live(
        self,
        request: ProviderInferenceRequest,
        *,
        api_key: str,
    ) -> ProviderInferenceResponse:
        if request.cancellation_ref and request.cancellation_ref in self.cancelled:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)

        payload = self.payload_registry.get(request.request_id)
        if payload is None:
            raise private_engine_error(
                PrivateEngineErrorCode.PROVIDER_POLICY_INVALID,
                detail_code="resolved_payload_required",
            )
        messages = [dict(m) for m in payload.messages]
        if not messages or messages[0].get("role") != "system":
            raise private_engine_error(
                PrivateEngineErrorCode.PROVIDER_POLICY_INVALID,
                detail_code="system_instruction_required",
            )
        timeout_seconds = int(request.timeout_policy.get("timeout_seconds") or 0)
        if timeout_seconds <= 0:
            try:
                from app.core.config import get_settings

                timeout_seconds = int(get_settings().aliyun_timeout_seconds)
            except Exception:  # noqa: BLE001
                timeout_seconds = 60
        response_format = payload.response_format_mode or "json_object"

        from app.narrative_core.services.provider_transport_kind import (
            ProviderTransportKind,
            is_capturing_transport,
            live_transport_allowed,
            transport_kind_of,
        )

        transport = self.transport
        if is_capturing_transport(transport):
            raise private_engine_error(
                PrivateEngineErrorCode.PROVIDER_POLICY_INVALID,
                detail_code="capturing_transport_forbidden_on_live",
            )
        ok, deny, effective_kind = live_transport_allowed(
            transport=transport,
            environment=str((request.metadata or {}).get("environment") or "development"),
            explicit_test_override=bool(
                (request.metadata or {}).get("explicit_test_transport_override")
            ),
        )
        if not ok:
            raise private_engine_error(
                PrivateEngineErrorCode.PROVIDER_POLICY_INVALID,
                detail_code=str(deny or "live_transport_rejected"),
            )
        if transport is None or transport_kind_of(transport) is None:
            transport = self._build_live_http_transport(api_key=api_key)
            effective_kind = ProviderTransportKind.REAL_HTTP

        try:
            response = transport.generate(
                messages=messages,
                model=self.model_id,
                response_format_mode=response_format,
                max_tokens=request.token_budget,
                timeout_seconds=timeout_seconds,
                cancellation_ref=request.cancellation_ref,
            )
        except Exception as exc:
            # Never include messages / credentials / body in error surfaces.
            if isinstance(exc, type(private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED))):
                raise
            from app.narrative_core.private_engine_contract.errors import PrivateEngineError

            if isinstance(exc, PrivateEngineError):
                raise
            raise private_engine_error(
                PrivateEngineErrorCode.PROVIDER_UNAVAILABLE,
                detail_code=type(exc).__name__,
            ) from None

        raw_text = getattr(response, "text", None) or ""
        structured = _parse_structured_text(raw_text)
        repaired = False
        if structured is None and self.output_repairer is not None:
            repair_result = self.output_repairer.repair(raw_text)
            if getattr(repair_result, "ok", False) and getattr(repair_result, "payload", None):
                structured = dict(repair_result.payload)
                repaired = True
            else:
                # repair failure — hard reject, never forge success
                self.last_raw_response_retained = False
                raise private_engine_error(
                    PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID,
                    detail_code="repair_rejected",
                )
        if structured is None:
            self.last_raw_response_retained = False
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)

        _validate_structured_output(structured, require_synthetic=False)
        # Raw response must not enter Artifact / FE — drop immediately.
        self.last_raw_response_retained = False
        del raw_text
        # Consume binding after successful parse so body does not linger.
        self.payload_registry.take(request.request_id)

        token_in = int(getattr(response, "input_tokens", 0) or 0)
        token_out = int(getattr(response, "output_tokens", 0) or 0)
        provider_request_id = getattr(response, "request_id", None)
        http_status = getattr(response, "http_status", None)
        if not provider_request_id:
            raise private_engine_error(
                PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID,
                detail_code="provider_request_id_missing",
            )
        cost = self._resolve_cost(token_in, token_out)
        structured_out = {**structured, "repaired": repaired} if repaired else dict(structured)
        # Safe audit markers — never credentials / messages / prompt body.
        structured_out["_provider_audit"] = {
            "transport_kind": getattr(response, "transport_kind", None)
            or effective_kind.value,
            "provider_request_id": provider_request_id,
            "http_status": http_status if http_status is not None else 200,
            "host": getattr(response, "host", None) or "dashscope.aliyuncs.com",
            "usage_source": "provider_response",
            "live_request_confirmed": True,
        }
        return ProviderInferenceResponse(
            request_id=request.request_id,
            provider_kind=self.provider_kind,
            model_id=getattr(response, "model", None) or self.model_id,
            provider_request_id=provider_request_id,
            status="success",
            structured_output=structured_out,
            token_input=token_in,
            token_output=token_out,
            cost=cost,
            latency_ms=int(getattr(response, "latency_ms", 0) or 0),
            finish_reason=getattr(response, "finish_reason", None),
            retry_count=0,
            validation_status="schema_ok_repaired" if repaired else "schema_ok",
            received_at=datetime(2026, 7, 24, 0, 0, 0),
        )

    def _resolve_cost(self, token_in: int, token_out: int) -> float | None:
        resolver = self.pricing_resolver
        if resolver is None:
            from app.narrative_core.services.whole_book_provider_estimate_service import (
                ProviderPricingResolver,
            )

            resolver = ProviderPricingResolver()
        return resolver.cost_from_usage(
            model_id=self.model_id,
            input_tokens=token_in,
            output_tokens=token_out,
        )

    def _build_live_http_transport(self, *, api_key: str) -> Any:
        """Real HTTP transport — only used when live probe + network authorized."""
        from app.core.config import get_settings
        from app.model_gateway.base import ModelRequest
        from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
        from app.services.aliyun_endpoint import resolve_aliyun_compatible_base_url

        settings = get_settings()
        base_url = resolve_aliyun_compatible_base_url(settings=settings)
        if not base_url:
            raise private_engine_error(
                PrivateEngineErrorCode.PROVIDER_UNAVAILABLE,
                detail_code="aliyun_endpoint_unresolved",
            )
        provider = OpenAICompatibleProvider(
            name=self.provider_kind,
            base_url=base_url,
            api_key=api_key,
            default_model=self.model_id,
            timeout_seconds=int(settings.aliyun_timeout_seconds),
            max_context_tokens=32768,
            enabled=True,
            profile_name=self.provider_kind,
            structured_output_mode=settings.aliyun_structured_output_mode,
            supports_json_object=True,
            cloud=True,
            provider_family="aliyun_qwen",
            sends_content_to_cloud=True,
            region="cn-beijing",
            supports_scene_analysis=True,
        )

        class _HttpTransport:
            transport_kind = "REAL_HTTP"
            test_only = False
            network_capable = True
            host = "dashscope.aliyuncs.com"

            def generate(
                self,
                *,
                messages: list[dict[str, str]],
                model: str,
                response_format_mode: str,
                max_tokens: int | None,
                timeout_seconds: int,
                cancellation_ref: str | None = None,
            ) -> StubTransportResponse:
                _ = timeout_seconds, cancellation_ref
                model_req = ModelRequest(
                    messages=messages,
                    model=model,
                    response_format_mode=response_format_mode or "json_object",
                    max_tokens=max_tokens,
                )
                response = _run_async(provider.generate(model_req))
                return StubTransportResponse(
                    text=response.text or "",
                    model=response.model or model,
                    request_id=response.request_id,
                    input_tokens=int(response.input_tokens or 0),
                    output_tokens=int(response.output_tokens or 0),
                    finish_reason=response.finish_reason,
                    http_status=200,
                    transport_kind="REAL_HTTP",
                    host="dashscope.aliyuncs.com",
                )

        return _HttpTransport()

    def cancel(self, cancellation_ref: str) -> bool:
        self.cancelled.add(cancellation_ref)
        if self.transport is not None and hasattr(self.transport, "cancelled_refs"):
            self.transport.cancelled_refs.add(cancellation_ref)
        return True

    def health_check(self) -> ProviderGatewayHealth:
        details = ["bailian_adapter", f"model={self.model_id}", "resolved_payload_required"]
        if self.dry_run or not self.allow_network or not _live_probe_enabled():
            details.extend(["dry_run", "no_live_http"])
        else:
            details.append("live_probe_enabled")
        if self.transport is not None:
            details.append("custom_transport")
        return ProviderGatewayHealth(
            provider_kind=self.provider_kind,
            healthy=True,
            status="ok",
            details=tuple(details),
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
    """Default gateway: Fake adapters only unless Private Lab authorizes network."""

    credential_resolver: ProviderCredentialResolver = field(default_factory=NoCredentialFakeResolver)
    budget_guard: BudgetGuard | None = None
    registry: ProviderAdapterRegistry | None = None
    allow_network: bool = False
    lab_network_authorized: bool = False
    payload_registry: ProviderPayloadRegistry = field(default_factory=lambda: PAYLOAD_REGISTRY)
    _cancelled: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.allow_network and not self.lab_network_authorized:
            raise ValueError("Phase 2B Provider Gateway forbids network requests")
        if self.lab_network_authorized and not self.allow_network:
            # Lab authorization without allow_network still stays dry-only.
            pass
        if self.registry is None:
            self.registry = ProviderAdapterRegistry()
            self.registry.register(FakeProviderAdapter())
            if self.lab_network_authorized:
                self.registry.register(
                    BailianOpenAICompatibleProviderAdapter(
                        dry_run=True,
                        allow_network=bool(self.allow_network),
                        payload_registry=self.payload_registry,
                    )
                )

    def bind_resolved_payload(
        self,
        request_id: str,
        payload: ResolvedProviderPayload,
    ) -> None:
        self.payload_registry.bind(request_id, payload)

    def validate_policy(self, policy: Mapping[str, Any]) -> None:
        _assert_no_credentials(policy)
        kind = str(policy.get("provider_kind") or "").strip()
        route = str(policy.get("model_route") or "").strip()
        if not kind and not route:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_POLICY_INVALID)
        if kind in {"fake", "test"} or "fake" in kind:
            return
        if kind in _REAL_PROVIDER_KINDS:
            if not self.lab_network_authorized:
                raise private_engine_error(
                    PrivateEngineErrorCode.PROVIDER_UNAVAILABLE,
                    detail_code="real_provider_requires_private_lab",
                )
            return
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

    def execute(
        self,
        request: ProviderInferenceRequest,
        *,
        resolved_payload: ResolvedProviderPayload | None = None,
    ) -> ProviderInferenceResponse:
        _assert_request_safe(request)
        self.validate_policy(
            {
                "provider_kind": request.provider_kind,
                "model_route": request.model_route,
            }
        )
        if request.cancellation_ref and request.cancellation_ref in self._cancelled:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)
        if resolved_payload is not None:
            self.bind_resolved_payload(request.request_id, resolved_payload)

        # Credential resolve at boundary only — never inject into request DTO.
        secret = self.credential_resolver.resolve(request.provider_kind)
        try:
            assert self.registry is not None
            adapter = self.registry.get(request.provider_kind)
            retry_limit = int(request.retry_policy.get("max_retries") or 0)
            retry_count = 0
            last_error: Exception | None = None
            estimated_tokens = 16
            bound = self.payload_registry.get(request.request_id)
            if bound is not None and bound.input_bundle is not None:
                estimated_tokens = max(16, bound.input_bundle.source_character_count() // 2)
            while retry_count <= retry_limit:
                if request.cancellation_ref and request.cancellation_ref in self._cancelled:
                    raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)
                if self.budget_guard is not None:
                    ok = self.budget_guard.check_budget(
                        stage_key=request.task_type, estimated_tokens=estimated_tokens
                    )
                    if not ok:
                        raise private_engine_error(PrivateEngineErrorCode.PROVIDER_BUDGET_EXCEEDED)
                try:
                    if isinstance(adapter, BailianOpenAICompatibleProviderAdapter):
                        response = adapter.execute_with_credential(request, secret)
                    else:
                        # Fake path should not need secrets; ensure we never log them.
                        _ = bool(secret) if secret is not None else False
                        response = adapter.execute(request)
                    if response.status != "success":
                        raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)
                    if response.structured_output is None:
                        raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)
                    require_synth = isinstance(adapter, FakeProviderAdapter)
                    _validate_structured_output(
                        response.structured_output,
                        require_synthetic=require_synth,
                    )
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
                    # Cancel after failure must block retry.
                    if request.cancellation_ref and request.cancellation_ref in self._cancelled:
                        raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED) from exc
                    if self.budget_guard is not None:
                        ok = self.budget_guard.check_budget(
                            stage_key=request.task_type, estimated_tokens=estimated_tokens
                        )
                        if not ok:
                            raise private_engine_error(
                                PrivateEngineErrorCode.PROVIDER_BUDGET_EXCEEDED
                            ) from exc
            if last_error is not None:
                raise last_error
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)
        finally:
            secret = None

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
        synthetic = response.provider_kind in {"fake", "test"} or "fake" in response.provider_kind
        if isinstance(response.structured_output, Mapping):
            synthetic = synthetic or bool(response.structured_output.get("synthetic"))
        return NormalizedProviderUsage(
            provider_input_tokens=response.token_input,
            provider_output_tokens=response.token_output,
            cached_tokens=0,
            provider_cost=response.cost,
            retries=response.retry_count,
            synthetic=synthetic,
        )


def create_lab_provider_gateway(
    *,
    dry_run: bool = True,
    allow_network: bool = False,
    credential_resolver: ProviderCredentialResolver | None = None,
    budget_guard: BudgetGuard | None = None,
    enable_credential_adapter: bool = False,
    credential_store: CredentialStore | None = None,
    transport: Any | None = None,
    payload_registry: ProviderPayloadRegistry | None = None,
) -> DefaultWholeBookProviderGateway:
    """Factory for Private Engine Lab — keeps default Fake gateway network-closed."""

    resolver: ProviderCredentialResolver
    if credential_resolver is not None:
        resolver = credential_resolver
    elif enable_credential_adapter:
        resolver = ExistingCredentialServiceAdapter(
            store=credential_store,
            enabled=True,
        )
    else:
        resolver = NoCredentialFakeResolver()

    registry_obj = payload_registry or ProviderPayloadRegistry()
    registry = ProviderAdapterRegistry()
    registry.register(FakeProviderAdapter())
    registry.register(
        BailianOpenAICompatibleProviderAdapter(
            dry_run=dry_run,
            allow_network=bool(allow_network) and not dry_run,
            transport=transport,
            payload_registry=registry_obj,
        )
    )
    return DefaultWholeBookProviderGateway(
        credential_resolver=resolver,
        budget_guard=budget_guard,
        registry=registry,
        allow_network=bool(allow_network) and not dry_run,
        lab_network_authorized=True,
        payload_registry=registry_obj,
    )


def _live_probe_enabled() -> bool:
    raw = str(os.environ.get(PRIVATE_PROVIDER_LIVE_PROBE_ENV, "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already in an event loop — run in a dedicated thread-less path via nest-safe runner.
    # Lab live path is opt-in; prefer asyncio.run in dedicated threads if needed later.
    new_loop = asyncio.new_event_loop()
    try:
        return new_loop.run_until_complete(coro)
    finally:
        new_loop.close()


def _parse_structured_text(text: str) -> dict[str, Any] | None:
    if not text or not str(text).strip():
        return None
    raw = str(text).strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


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


def _validate_structured_output(
    output: Mapping[str, Any],
    *,
    require_synthetic: bool = True,
) -> None:
    if not isinstance(output, Mapping):
        raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)
    _assert_no_credentials(output)
    if require_synthetic:
        if not (output.get("fake") is True or output.get("synthetic") is True):
            if "schema_ref" not in output:
                raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)


def assert_no_credential_in_logs(log_text: str) -> None:
    lower = log_text.lower()
    for token in ("api_key", "sk-", "authorization:", "bearer ", "credential="):
        if token in lower:
            raise AssertionError("credential must not appear in logs")
