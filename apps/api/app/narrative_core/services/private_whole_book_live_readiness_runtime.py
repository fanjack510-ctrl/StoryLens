"""Unique Live Readiness Runtime composition (Phase 2B-R1 / CHG-049+050).

Wires Agent U (provider/context/cost) + Agent V (Lab run/persistence) behind Protocols.
Formal HTTP Lab defaults to PrivateProviderInputBundleResolver + Credential Adapter.
Fake resolver is opt-in for explicit tests only — never a silent fallback.
Production must not construct an enabled instance.

CHG-050: allow_network follows Live Probe + Lab + non-prod; Runtime cache keyed by
security config so Probe toggles do not reuse stale allow_network=false instances.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.narrative_core.run_shell_contract.private_engine_lab import (
    WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
)
from app.narrative_core.services.data_transfer_consent_guard import (
    PrivateEngineDataTransferConsentGuard,
    PrivateEngineProviderBudgetGuard,
)
from app.narrative_core.services.formal_private_provider_input_resolver import (
    FormalPrivateProviderInputBundleResolverAdapter,
    FormalPrivateResolverUnavailable,
)
from app.narrative_core.services.in_process_private_lab_task_registry import (
    InProcessPrivateLabTaskRegistry,
    get_default_private_lab_task_registry,
)
from app.narrative_core.services.private_engine_lab_authorization_service import (
    PrivateEngineLabAuthorizationService,
    is_private_provider_live_probe_enabled,
)
from app.narrative_core.services.private_engine_lab_run_service import (
    PrivateWholeBookLabRunService,
)
from app.narrative_core.services.private_lab_idempotency import (
    PrivateLabConcurrencyGuard,
    PrivateLabCreateIdempotency,
)
from app.narrative_core.services.private_lab_recovery_service import PrivateLabRecoveryService
from app.narrative_core.services.private_lab_run_executor import PrivateLabRunExecutor
from app.narrative_core.services.private_lab_service_adapters import (
    PrivateLabConsentServiceAdapter,
    PrivateLabEstimateServiceAdapter,
    PrivateLabPreflightServiceAdapter,
    PrivateLabProviderExecutionServiceAdapter,
)
from app.narrative_core.services.provider_execution_authorization import (
    compute_runtime_allow_network,
)
from app.narrative_core.services.provider_input_bundle_resolver import (
    FakeProviderInputBundleResolver,
)
from app.narrative_core.services.whole_book_provider_estimate_service import (
    WholeBookProviderEstimateService,
)
from app.narrative_core.services.whole_book_provider_gateway import (
    CapturingProviderTransport,
    ExistingCredentialServiceAdapter,
    StubTransportResponse,
)


@dataclass(frozen=True, slots=True)
class LiveReadinessRuntimeCacheKey:
    """Security-sensitive cache key — mismatch forces Runtime rebuild."""

    environment: str
    lab_enabled: bool
    live_probe_enabled: bool
    database_identity: str
    allow_network: bool


def _database_identity() -> str:
    url = str(os.environ.get("STORYLENS_DATABASE_URL") or "").strip()
    if not url:
        return "db:unset"
    return "db:" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def build_live_readiness_cache_key(
    *,
    environment: str,
    lab_enabled: bool,
    live_probe_enabled: bool | None = None,
) -> LiveReadinessRuntimeCacheKey:
    probe = (
        is_private_provider_live_probe_enabled()
        if live_probe_enabled is None
        else bool(live_probe_enabled)
    )
    env = str(environment or "development").strip().lower()
    enabled = bool(lab_enabled)
    if env == "production":
        enabled = False
    allow_net = compute_runtime_allow_network(
        environment=env,
        lab_enabled=enabled,
        live_probe_enabled=probe,
    )
    return LiveReadinessRuntimeCacheKey(
        environment=env,
        lab_enabled=enabled,
        live_probe_enabled=probe,
        database_identity=_database_identity(),
        allow_network=allow_net,
    )


@dataclass
class PrivateWholeBookLiveReadinessRuntime:
    """Composition root — isolated, Protocol-backed, no circular imports."""

    environment: str = "test"
    lab_enabled: bool = False
    dry_run: bool = True
    allow_network: bool = False
    preflight: PrivateLabPreflightServiceAdapter | None = None
    estimate: PrivateLabEstimateServiceAdapter | None = None
    consent: PrivateLabConsentServiceAdapter | None = None
    provider_execution: PrivateLabProviderExecutionServiceAdapter | None = None
    budget_guard: PrivateEngineProviderBudgetGuard = field(
        default_factory=PrivateEngineProviderBudgetGuard
    )
    consent_guard: PrivateEngineDataTransferConsentGuard = field(
        default_factory=PrivateEngineDataTransferConsentGuard
    )
    resolver: Any = None
    estimate_service: WholeBookProviderEstimateService = field(
        default_factory=WholeBookProviderEstimateService
    )
    credential_adapter: ExistingCredentialServiceAdapter | None = None
    transport: Any | None = None
    task_registry: InProcessPrivateLabTaskRegistry | None = None
    concurrency: PrivateLabConcurrencyGuard = field(default_factory=PrivateLabConcurrencyGuard)
    idempotency: PrivateLabCreateIdempotency = field(default_factory=PrivateLabCreateIdempotency)
    runtime_factory: Callable[..., Any] | None = None
    allow_fake_resolver: bool = False
    security_cache_key: LiveReadinessRuntimeCacheKey | None = None
    _production_forbidden: bool = field(default=True, init=False, repr=False)

    def assert_not_production_enabled(self) -> None:
        if self.environment == "production" and self.lab_enabled:
            raise RuntimeError("LiveReadinessRuntime must not be enabled in production")

    def bind_session(self, session: Session) -> None:
        """Bind DB session onto preflight + formal resolver (required for Snapshot context)."""

        if self.preflight is not None:
            self.preflight.session = session
        resolver = self.resolver
        bind = getattr(resolver, "bind_session", None)
        if callable(bind):
            bind(session)

    def build_run_service(self, session: Session) -> PrivateWholeBookLabRunService:
        self.assert_not_production_enabled()
        assert self.preflight is not None
        assert self.estimate is not None
        assert self.consent is not None
        self.bind_session(session)
        return PrivateWholeBookLabRunService(
            session,
            auth=PrivateEngineLabAuthorizationService(
                environment=self.environment, lab_enabled=True
            ),
            task_registry=self.task_registry or get_default_private_lab_task_registry(),
            idempotency=self.idempotency,
            concurrency=self.concurrency,
            preflight_port=self.preflight,
            estimate_port=self.estimate,
            consent_port=self.consent,
        )

    def build_executor(self, session: Session) -> PrivateLabRunExecutor:
        self.assert_not_production_enabled()
        assert self.provider_execution is not None
        self.bind_session(session)
        return PrivateLabRunExecutor(
            session,
            task_registry=self.task_registry or get_default_private_lab_task_registry(),
            concurrency=self.concurrency,
            provider_port=self.provider_execution,
            runtime_factory=self.runtime_factory,
        )

    def build_recovery(self, session: Session) -> PrivateLabRecoveryService:
        return PrivateLabRecoveryService(session)

    @property
    def uses_fake_resolver(self) -> bool:
        return isinstance(self.resolver, FakeProviderInputBundleResolver) or bool(
            getattr(self.resolver, "is_fake", False)
        )


def _resolve_lab_resolver(
    *,
    allow_fake_resolver: bool,
    resolver: Any | None,
    session: Session | None,
) -> Any:
    if resolver is not None:
        if isinstance(resolver, FakeProviderInputBundleResolver) and not allow_fake_resolver:
            raise FormalPrivateResolverUnavailable(
                "FakeProviderInputBundleResolver refused without allow_fake_resolver=True"
            )
        if session is not None and hasattr(resolver, "bind_session"):
            resolver.bind_session(session)
        return resolver
    if allow_fake_resolver:
        return FakeProviderInputBundleResolver()
    # Formal path — fail closed if private package missing.
    return FormalPrivateProviderInputBundleResolverAdapter(session=session)


def _resolve_credential_adapter(
    *,
    credential_adapter: ExistingCredentialServiceAdapter | None,
    auto_wire_credentials: bool,
) -> ExistingCredentialServiceAdapter | None:
    if credential_adapter is not None:
        return credential_adapter
    if not auto_wire_credentials:
        return None
    from app.services.credentials.service import get_credential_store

    return ExistingCredentialServiceAdapter(store=get_credential_store(), enabled=True)


def create_live_readiness_runtime(
    *,
    environment: str = "test",
    lab_enabled: bool | None = None,
    dry_run: bool = True,
    allow_network: bool | None = None,
    session: Session | None = None,
    credential_adapter: ExistingCredentialServiceAdapter | None = None,
    transport: Any | None = None,
    live_transport: Any | None = None,
    explicit_test_transport_override: bool = False,
    capability_ok_fn: Callable[[], bool] | None = None,
    runtime_factory: Callable[..., Any] | None = None,
    force_deny_budget: bool = False,
    allow_fake_resolver: bool = False,
    resolver: Any | None = None,
    auto_wire_credentials: bool | None = None,
    live_probe_enabled: bool | None = None,
) -> PrivateWholeBookLiveReadinessRuntime:
    """Factory for Integration / HTTP Lab / tests.

    Formal defaults (allow_fake_resolver=False):
    - PrivateProviderInputBundleResolver via Formal adapter
    - Credential adapter auto-wired unless explicitly disabled
    allow_network is independent of default dry_run (request dry_run gates Live).
    """

    env = str(environment or "test").strip().lower()
    enabled = WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED if lab_enabled is None else bool(lab_enabled)
    if env == "production":
        enabled = False

    probe = (
        is_private_provider_live_probe_enabled()
        if live_probe_enabled is None
        else bool(live_probe_enabled)
    )
    if allow_network is None:
        allow_net = compute_runtime_allow_network(
            environment=env, lab_enabled=enabled, live_probe_enabled=probe
        )
    else:
        # Explicit override still cannot open network in production / lab-off / probe-off.
        allow_net = bool(allow_network)
        if env == "production" or env not in {"development", "test", "dev"}:
            allow_net = False
        if not enabled or not probe:
            allow_net = False

    if auto_wire_credentials is None:
        auto_wire_credentials = not allow_fake_resolver

    resolved_resolver = _resolve_lab_resolver(
        allow_fake_resolver=allow_fake_resolver,
        resolver=resolver,
        session=session,
    )
    cred = _resolve_credential_adapter(
        credential_adapter=credential_adapter,
        auto_wire_credentials=bool(auto_wire_credentials),
    )

    estimate_service = WholeBookProviderEstimateService()
    budget = PrivateEngineProviderBudgetGuard(force_deny=force_deny_budget)
    consent_guard = PrivateEngineDataTransferConsentGuard()

    capture = transport or CapturingProviderTransport(
        stub=StubTransportResponse(
            text='{"synthetic":true,"partial":true,"items":[]}',
            model="qwen3.7-plus",
            request_id="live-readiness-stub",
            input_tokens=24,
            output_tokens=12,
            transport_kind="CAPTURING_TEST",
        )
    )

    preflight = PrivateLabPreflightServiceAdapter(
        session=session,
        environment=env,
        lab_enabled=enabled,
        capability_ok_fn=capability_ok_fn,
        credential_status_fn=(
            (lambda pk: bool(cred and cred.enabled and cred.resolve(pk))) if cred is not None else None
        ),
    )
    estimate = PrivateLabEstimateServiceAdapter(
        resolver=resolved_resolver,
        estimate_service=estimate_service,
    )
    consent = PrivateLabConsentServiceAdapter(
        consent_guard=consent_guard,
        budget_guard=budget,
        estimate_adapter=estimate,
        ignore_client_consent_boolean=True,
    )
    provider_exec = PrivateLabProviderExecutionServiceAdapter(
        resolver=resolved_resolver,
        budget_guard=budget,
        dry_run=bool(dry_run),
        allow_network=bool(allow_net),
        transport=capture,
        live_transport=live_transport,
        explicit_test_transport_override=bool(explicit_test_transport_override),
        credential_resolver=cred,
        environment=env,
        lab_enabled=enabled,
    )

    cache_key = LiveReadinessRuntimeCacheKey(
        environment=env,
        lab_enabled=enabled,
        live_probe_enabled=probe,
        database_identity=_database_identity(),
        allow_network=bool(allow_net),
    )

    return PrivateWholeBookLiveReadinessRuntime(
        environment=env,
        lab_enabled=enabled,
        dry_run=bool(dry_run),
        allow_network=bool(allow_net),
        preflight=preflight,
        estimate=estimate,
        consent=consent,
        provider_execution=provider_exec,
        budget_guard=budget,
        consent_guard=consent_guard,
        resolver=resolved_resolver,
        estimate_service=estimate_service,
        credential_adapter=cred,
        transport=capture,
        runtime_factory=runtime_factory,
        allow_fake_resolver=allow_fake_resolver,
        security_cache_key=cache_key,
    )


# Process-local default for router DI — reconstructed when security config changes.
_default_runtime: PrivateWholeBookLiveReadinessRuntime | None = None
_default_cache_key: LiveReadinessRuntimeCacheKey | None = None


def get_or_create_default_live_readiness_runtime(
    *,
    environment: str = "development",
    lab_enabled: bool = True,
) -> PrivateWholeBookLiveReadinessRuntime:
    """Lazy Lab DI helper — rebuilds when Probe/Lab/DB/env security config changes."""

    global _default_runtime, _default_cache_key
    # Explicit test injection sets runtime without cache key — honor until reset.
    if _default_runtime is not None and _default_cache_key is None:
        return _default_runtime

    key = build_live_readiness_cache_key(environment=environment, lab_enabled=lab_enabled)
    if _default_runtime is None or _default_cache_key != key:
        _default_runtime = create_live_readiness_runtime(
            environment=key.environment,
            lab_enabled=key.lab_enabled,
            dry_run=True,
            allow_network=key.allow_network,
            allow_fake_resolver=False,
            auto_wire_credentials=True,
            live_probe_enabled=key.live_probe_enabled,
        )
        _default_cache_key = key
        if _default_runtime.uses_fake_resolver:
            raise FormalPrivateResolverUnavailable(
                "default Lab runtime must not use FakeProviderInputBundleResolver"
            )
    return _default_runtime


def reset_default_live_readiness_runtime_for_tests() -> None:
    global _default_runtime, _default_cache_key
    _default_runtime = None
    _default_cache_key = None


__all__ = [
    "LiveReadinessRuntimeCacheKey",
    "PrivateWholeBookLiveReadinessRuntime",
    "build_live_readiness_cache_key",
    "create_live_readiness_runtime",
    "get_or_create_default_live_readiness_runtime",
    "reset_default_live_readiness_runtime_for_tests",
]
