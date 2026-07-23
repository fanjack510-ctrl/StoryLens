"""Mock Whole-Book Lab runtime composition root (Phase 2A Integration).

Unique wiring for Agent M service/executor + Agent O reliability stack.
No global mutable production singleton that enables Lab by default.
Tests inject isolated runtimes via create_mock_lab_runtime(...).
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.narrative_core.run_shell_contract.mock_lab import (
    ALLOWED_MOCK_LAB_ENVIRONMENTS,
    WHOLE_BOOK_MOCK_LAB_ENABLED,
)
from app.narrative_core.services.in_process_mock_run_task_registry import (
    InProcessMockRunTaskRegistry,
    get_default_mock_run_task_registry,
)
from app.narrative_core.services.mock_execution_quota import (
    MockExecutionBudgetGuard,
    MockExecutionQuotaService,
)
from app.narrative_core.services.mock_lab_authorization_service import (
    MockLabAuthorizationService,
    is_mock_lab_enabled_from_env,
)
from app.narrative_core.services.mock_run_audit import MockRunAuditSink
from app.narrative_core.services.mock_run_fault_injection import FaultInjectionController
from app.narrative_core.services.mock_run_idempotency import (
    MockRunConcurrencyGuard,
    MockRunIdempotencyService,
)
from app.narrative_core.services.mock_run_recovery_service import (
    MockRunRecoveryService,
    MockRunStartupRecoveryAdapter,
)
from app.narrative_core.services.mock_whole_book_engine import MockWholeBookAnalysisEngine
from app.narrative_core.services.mock_whole_book_run_executor import (
    DefaultMockWholeBookRunExecutor,
)
from app.narrative_core.services.mock_whole_book_run_service import MockWholeBookRunService

logger = logging.getLogger("storylens.mock_lab_runtime")

_lock = threading.RLock()
_default_runtime: "MockWholeBookRunRuntime | None" = None


def should_register_mock_lab_router(
    *,
    environment: str,
    lab_enabled: bool,
) -> bool:
    """Lab router mounts only when env is development/test AND Lab is enabled."""
    env = str(environment or "").strip().lower()
    if env == "production":
        return False
    if env not in ALLOWED_MOCK_LAB_ENVIRONMENTS:
        return False
    return bool(lab_enabled)


@dataclass
class MockWholeBookRunRuntime:
    """Process-scoped composition root for Mock Lab (injectable in tests)."""

    environment: str
    lab_enabled: bool
    idempotency_service: MockRunIdempotencyService = field(
        default_factory=MockRunIdempotencyService
    )
    concurrency_guard: MockRunConcurrencyGuard = field(
        default_factory=MockRunConcurrencyGuard
    )
    audit_sink: MockRunAuditSink = field(
        default_factory=lambda: MockRunAuditSink(emit_logs=False)
    )
    quota_service: MockExecutionQuotaService | None = None
    budget_guard: MockExecutionBudgetGuard | None = None
    fault_injection: FaultInjectionController | None = None
    task_registry: InProcessMockRunTaskRegistry | None = None
    session_factory: Callable[[], Session] | None = None
    _auth: MockLabAuthorizationService | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.quota_service is None:
            self.quota_service = MockExecutionQuotaService(
                concurrency_guard=self.concurrency_guard
            )
        if self.budget_guard is None:
            self.budget_guard = MockExecutionBudgetGuard(
                self.quota_service,
                concurrency_guard=self.concurrency_guard,
            )
        if self.task_registry is None:
            self.task_registry = get_default_mock_run_task_registry()
        if self._auth is None:
            self._auth = MockLabAuthorizationService(
                environment=self.environment,
                lab_enabled=self.lab_enabled,
            )
        # Fault injection is forbidden in production — never construct there.
        if self.fault_injection is None and self.lab_enabled and self.environment != "production":
            self.fault_injection = FaultInjectionController(environment=self.environment)

    @property
    def auth(self) -> MockLabAuthorizationService:
        assert self._auth is not None
        return self._auth

    def build_run_service(self, session: Session) -> MockWholeBookRunService:
        return MockWholeBookRunService(
            session,
            auth=self.auth,
            task_registry=self.task_registry,
            idempotency=self.idempotency_service,
            concurrency=self.concurrency_guard,
            quota=self.quota_service,
            audit=self.audit_sink,
            fault_injection=self.fault_injection,
        )

    def build_executor(
        self,
        session: Session,
        *,
        hooks: Any | None = None,
        lab_hooks_allowed: bool = True,
        engine: MockWholeBookAnalysisEngine | None = None,
    ) -> DefaultMockWholeBookRunExecutor:
        return DefaultMockWholeBookRunExecutor(
            session,
            task_registry=self.task_registry,
            engine=engine,
            hooks=hooks,
            lab_hooks_allowed=lab_hooks_allowed,
            idempotency=self.idempotency_service,
            concurrency=self.concurrency_guard,
            budget_guard=self.budget_guard,
            audit=self.audit_sink,
            fault_injection=self.fault_injection,
        )

    def build_recovery(
        self,
        session: Session,
        *,
        explicit_resume_allowed: bool = False,
    ) -> MockRunRecoveryService:
        return MockRunRecoveryService(
            session,
            lab_enabled=self.lab_enabled,
            audit_sink=self.audit_sink,
            explicit_resume_allowed=explicit_resume_allowed,
        )

    def build_startup_adapter(self) -> MockRunStartupRecoveryAdapter | None:
        if self.session_factory is None:
            return None
        return MockRunStartupRecoveryAdapter(
            self.session_factory,
            lab_enabled=self.lab_enabled,
            audit_sink=self.audit_sink,
        )

    def clear_process_local(self) -> None:
        """Test helper: clear in-memory stores without touching DB."""
        self.idempotency_service.clear()
        self.concurrency_guard.clear()
        if self.quota_service is not None:
            self.quota_service.clear()
        if self.fault_injection is not None:
            self.fault_injection.stage_completion_counts.clear()
            self.fault_injection.asset_write_counts.clear()
            self.fault_injection.task_registry.clear()
            self.fault_injection.restart_seen = False
        self.audit_sink.clear()


def create_mock_lab_runtime(
    *,
    environment: str = "test",
    lab_enabled: bool = True,
    session_factory: Callable[[], Session] | None = None,
    task_registry: InProcessMockRunTaskRegistry | None = None,
    set_as_default: bool = False,
) -> MockWholeBookRunRuntime:
    runtime = MockWholeBookRunRuntime(
        environment=str(environment).strip().lower(),
        lab_enabled=bool(lab_enabled),
        session_factory=session_factory,
        task_registry=task_registry,
    )
    if set_as_default:
        with _lock:
            global _default_runtime
            _default_runtime = runtime
    return runtime


def get_default_mock_lab_runtime() -> MockWholeBookRunRuntime | None:
    """Return process default. Production / Lab-disabled yields disabled or None."""
    with _lock:
        global _default_runtime
        if _default_runtime is not None:
            return _default_runtime
        env = str(
            os.environ.get("STORYLENS_APP_ENV")
            or os.environ.get("APP_ENV")
            or os.environ.get("ENVIRONMENT")
            or "development"
        ).strip().lower()
        lab_enabled = is_mock_lab_enabled_from_env(default=WHOLE_BOOK_MOCK_LAB_ENABLED)
        if env == "production" or not lab_enabled:
            # Do not construct an enabled Lab runtime for production defaults.
            _default_runtime = MockWholeBookRunRuntime(
                environment=env,
                lab_enabled=False,
            )
            return _default_runtime
        _default_runtime = MockWholeBookRunRuntime(
            environment=env,
            lab_enabled=True,
        )
        return _default_runtime


def reset_default_mock_lab_runtime() -> None:
    with _lock:
        global _default_runtime
        if _default_runtime is not None:
            try:
                _default_runtime.clear_process_local()
            except Exception:  # noqa: BLE001
                pass
        _default_runtime = None


def log_lab_startup_status(*, environment: str, lab_enabled: bool) -> None:
    """Startup log: Lab enabled/disabled only — never credentials."""
    registered = should_register_mock_lab_router(
        environment=environment, lab_enabled=lab_enabled
    )
    logger.info(
        "whole_book_mock_lab status=enabled=%s environment=%s router_registered=%s",
        bool(lab_enabled),
        environment,
        registered,
    )


__all__ = [
    "MockWholeBookRunRuntime",
    "create_mock_lab_runtime",
    "get_default_mock_lab_runtime",
    "log_lab_startup_status",
    "reset_default_mock_lab_runtime",
    "should_register_mock_lab_router",
]
