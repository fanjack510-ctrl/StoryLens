"""WholeBook Provider Gateway foundation (Phase 2B / 2B-R).

Fake Provider remains default. Bailian OpenAI-compatible adapter is available
under Private Engine Lab authorization only. Credentials resolve only at
execute boundary; never enter Request DTOs or logs.
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
from app.narrative_core.run_shell_contract.private_engine_lab import (
    PRIVATE_LAB_FIRST_MODEL_ID,
    PRIVATE_LAB_FIRST_PROVIDER_KEY,
    PRIVATE_PROVIDER_LIVE_PROBE_ENV,
)
from app.services.credentials.base import CredentialStore

logger = logging.getLogger(__name__)

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
    """

    provider_kind: str = PRIVATE_LAB_FIRST_PROVIDER_KEY
    model_id: str = PRIVATE_LAB_FIRST_MODEL_ID
    dry_run: bool = True
    allow_network: bool = False
    cancelled: set[str] = field(default_factory=set)
    calls: int = 0
    _ephemeral_credential: str | None = field(default=None, repr=False)

    def estimate(self, request: ProviderInferenceRequest) -> ProviderEstimate:
        _assert_request_safe(request)
        # Conservative dry estimate; pricing bridge may refine later.
        return ProviderEstimate(
            request_id=request.request_id,
            estimated_input_tokens=int(request.token_budget or 512),
            estimated_output_tokens=256,
            estimated_cost=0.0,
            within_budget=True,
        )

    def execute(self, request: ProviderInferenceRequest) -> ProviderInferenceResponse:
        _assert_request_safe(request)
        self.calls += 1
        if request.cancellation_ref and request.cancellation_ref in self.cancelled:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)

        if self.dry_run or not self.allow_network or not _live_probe_enabled():
            structured = {
                "dry_run": True,
                "provider_kind": self.provider_kind,
                "model_id": self.model_id,
                "schema_ref": request.response_schema_ref,
                "task_type": request.task_type,
                "synthetic": False,
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
    ) -> ProviderInferenceResponse:
        self._ephemeral_credential = credential
        try:
            return self.execute(request)
        finally:
            self._ephemeral_credential = None

    def _execute_live(
        self,
        request: ProviderInferenceRequest,
        *,
        api_key: str,
    ) -> ProviderInferenceResponse:
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
        # Instruction / source isolation: refs only — never merge credentials.
        messages = [
            {
                "role": "system",
                "content": f"instruction_ref={request.system_instruction_ref}",
            },
            {
                "role": "user",
                "content": f"input_bundle_ref={request.input_bundle_ref}",
            },
        ]
        model_req = ModelRequest(
            messages=messages,
            model=self.model_id,
            response_format_mode="json_object",
            max_tokens=request.token_budget,
        )
        response = _run_async(provider.generate(model_req))
        structured = _parse_structured_text(response.text)
        if structured is None:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)
        _validate_structured_output(structured, require_synthetic=False)
        return ProviderInferenceResponse(
            request_id=request.request_id,
            provider_kind=self.provider_kind,
            model_id=response.model or self.model_id,
            provider_request_id=response.request_id,
            status="success",
            structured_output=structured,
            token_input=int(response.input_tokens or 0),
            token_output=int(response.output_tokens or 0),
            cost=None,
            latency_ms=0,
            finish_reason=response.finish_reason,
            retry_count=0,
            validation_status="schema_ok",
            received_at=datetime(2026, 7, 24, 0, 0, 0),
        )

    def cancel(self, cancellation_ref: str) -> bool:
        self.cancelled.add(cancellation_ref)
        return True

    def health_check(self) -> ProviderGatewayHealth:
        details = ["bailian_adapter", f"model={self.model_id}"]
        if self.dry_run or not self.allow_network or not _live_probe_enabled():
            details.extend(["dry_run", "no_live_http"])
        else:
            details.append("live_probe_enabled")
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
                    )
                )

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
        try:
            assert self.registry is not None
            adapter = self.registry.get(request.provider_kind)
            retry_limit = int(request.retry_policy.get("max_retries") or 0)
            retry_count = 0
            last_error: Exception | None = None
            while retry_count <= retry_limit:
                if request.cancellation_ref and request.cancellation_ref in self._cancelled:
                    raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)
                if self.budget_guard is not None:
                    ok = self.budget_guard.check_budget(
                        stage_key=request.task_type, estimated_tokens=16
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
                    if self.budget_guard is not None:
                        ok = self.budget_guard.check_budget(
                            stage_key=request.task_type, estimated_tokens=16
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

    registry = ProviderAdapterRegistry()
    registry.register(FakeProviderAdapter())
    registry.register(
        BailianOpenAICompatibleProviderAdapter(
            dry_run=dry_run,
            allow_network=bool(allow_network) and not dry_run,
        )
    )
    return DefaultWholeBookProviderGateway(
        credential_resolver=resolver,
        budget_guard=budget_guard,
        registry=registry,
        allow_network=bool(allow_network) and not dry_run,
        lab_network_authorized=True,
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
