"""Unique Live Readiness Runtime composition (Phase 2B-R1 Integration / CHG-049).

Wires Agent U (provider/context/cost) + Agent V (Lab run/persistence) behind Protocols.
Formal HTTP Lab defaults to PrivateProviderInputBundleResolver + Credential Adapter.
Fake resolver is opt-in for explicit tests only — never a silent fallback.
Production must not construct an enabled instance.
"""

from __future__ import annotations

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
    allow_network: bool = False,
    session: Session | None = None,
    credential_adapter: ExistingCredentialServiceAdapter | None = None,
    transport: Any | None = None,
    capability_ok_fn: Callable[[], bool] | None = None,
    runtime_factory: Callable[..., Any] | None = None,
    force_deny_budget: bool = False,
    allow_fake_resolver: bool = False,
    resolver: Any | None = None,
    auto_wire_credentials: bool | None = None,
) -> PrivateWholeBookLiveReadinessRuntime:
    """Factory for Integration / HTTP Lab / tests.

    Formal defaults (allow_fake_resolver=False):
    - PrivateProviderInputBundleResolver via Formal adapter
    - Credential adapter auto-wired unless explicitly disabled
    Tests may pass allow_fake_resolver=True or an explicit Fake resolver.
    """

    enabled = WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED if lab_enabled is None else bool(lab_enabled)
    if environment == "production":
        enabled = False

    if auto_wire_credentials is None:
        # Formal Lab always wires credentials; Fake-test paths opt out unless provided.
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
        )
    )

    preflight = PrivateLabPreflightServiceAdapter(
        session=session,
        environment=environment,
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
        dry_run=dry_run,
        allow_network=bool(allow_network) and not dry_run,
        transport=capture,
        credential_resolver=cred,
    )

    return PrivateWholeBookLiveReadinessRuntime(
        environment=environment,
        lab_enabled=enabled,
        dry_run=dry_run,
        allow_network=bool(allow_network) and not dry_run,
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
    )


# Process-local default for router DI — constructed lazily; never production-enabled.
_default_runtime: PrivateWholeBookLiveReadinessRuntime | None = None


def get_or_create_default_live_readiness_runtime(
    *,
    environment: str = "development",
    lab_enabled: bool = True,
) -> PrivateWholeBookLiveReadinessRuntime:
    """Lazy Lab DI helper for HTTP router — formal resolver + credentials, no Fake."""

    global _default_runtime
    if _default_runtime is None:
        _default_runtime = create_live_readiness_runtime(
            environment=environment,
            lab_enabled=lab_enabled,
            dry_run=True,
            allow_network=False,
            allow_fake_resolver=False,
            auto_wire_credentials=True,
        )
        if _default_runtime.uses_fake_resolver:
            raise FormalPrivateResolverUnavailable(
                "default Lab runtime must not use FakeProviderInputBundleResolver"
            )
    return _default_runtime


def reset_default_live_readiness_runtime_for_tests() -> None:
    global _default_runtime
    _default_runtime = None


__all__ = [
    "PrivateWholeBookLiveReadinessRuntime",
    "create_live_readiness_runtime",
    "get_or_create_default_live_readiness_runtime",
    "reset_default_live_readiness_runtime_for_tests",
]
