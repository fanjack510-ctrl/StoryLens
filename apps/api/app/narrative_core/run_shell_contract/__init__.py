"""Phase 2A-P Mock Whole-Book Run Shell contracts.

Types, Protocols, Guards, and Fixtures only.
No real WholeBook Engine, no model calls, no real prompts.
"""

from __future__ import annotations

from app.narrative_core.run_shell_contract.actions import (
    ACTION_RULES,
    MockRunAction,
    MockRunActionRequest,
    MockRunActionResult,
    action_allowed_for_state,
)
from app.narrative_core.run_shell_contract.api_routes import (
    DEFAULT_LAB_API_ROUTE_POLICY,
    LAB_API_ROUTES,
    OPENAPI_LAB_TAGS,
    PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH,
)
from app.narrative_core.run_shell_contract.audit import MockRunAuditEvent, MockRunAuditEventType
from app.narrative_core.run_shell_contract.create_run import (
    CREATE_MOCK_RUN_SEQUENCE,
    CreateMockWholeBookRunRequest,
    CreateMockWholeBookRunResult,
    MockRunPersistenceMetadata,
    first_failed_create_precheck,
)
from app.narrative_core.run_shell_contract.errors import (
    MOCK_RUN_ERROR_MESSAGES,
    MockRunErrorCode,
    all_mock_run_error_codes,
)
from app.narrative_core.run_shell_contract.executor import (
    EXECUTOR_PROTOCOL_METHODS,
    MockWholeBookRunExecutor,
    ProtocolShapeFixture,
)
from app.narrative_core.run_shell_contract.idempotency import (
    DEFAULT_MOCK_RUN_CONCURRENCY_POLICY,
    occupies_active_slot,
)
from app.narrative_core.run_shell_contract.mock_lab import (
    WHOLE_BOOK_MOCK_LAB_ENABLED,
    MockLabAuthorizationDecision,
    MockLabAuthorizationInput,
    evaluate_mock_lab_authorization,
)
from app.narrative_core.run_shell_contract.partial_result import (
    PartialResultGate,
    is_partial_result_readable,
)
from app.narrative_core.run_shell_contract.polling import (
    DEFAULT_MOCK_RUN_POLLING_POLICY,
    MockRunPollingPolicy,
    interval_for_status,
)
from app.narrative_core.run_shell_contract.quota import (
    DEFAULT_MOCK_EXECUTION_QUOTA_POLICY,
    MockExecutionQuotaPolicy,
)
from app.narrative_core.run_shell_contract.recovery import (
    CHECKPOINT_SCHEMA,
    CHECKPOINT_VERSION,
    MockRunRecoveryService,
    DEFAULT_RECOVERY_SCAN_POLICY,
)
from app.narrative_core.run_shell_contract.run_state import (
    ALLOWED_RUN_TRANSITIONS,
    is_allowed_run_transition,
    validate_transition_or_raise,
)
from app.narrative_core.run_shell_contract.stage_lifecycle import ORDERED_MOCK_STAGE_KEYS
from app.narrative_core.run_shell_contract.task_registry import (
    TASK_REGISTRY_PROTOCOL_METHODS,
    InMemoryMockRunTaskRegistryFixture,
    InProcessMockRunTaskRegistry,
)

__all__ = [
    "ACTION_RULES",
    "ALLOWED_RUN_TRANSITIONS",
    "CHECKPOINT_SCHEMA",
    "CHECKPOINT_VERSION",
    "CREATE_MOCK_RUN_SEQUENCE",
    "DEFAULT_LAB_API_ROUTE_POLICY",
    "DEFAULT_MOCK_EXECUTION_QUOTA_POLICY",
    "DEFAULT_MOCK_RUN_CONCURRENCY_POLICY",
    "DEFAULT_MOCK_RUN_POLLING_POLICY",
    "DEFAULT_RECOVERY_SCAN_POLICY",
    "EXECUTOR_PROTOCOL_METHODS",
    "LAB_API_ROUTES",
    "MOCK_RUN_ERROR_MESSAGES",
    "OPENAPI_LAB_TAGS",
    "ORDERED_MOCK_STAGE_KEYS",
    "PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH",
    "TASK_REGISTRY_PROTOCOL_METHODS",
    "WHOLE_BOOK_MOCK_LAB_ENABLED",
    "CreateMockWholeBookRunRequest",
    "CreateMockWholeBookRunResult",
    "InMemoryMockRunTaskRegistryFixture",
    "InProcessMockRunTaskRegistry",
    "MockExecutionQuotaPolicy",
    "MockLabAuthorizationDecision",
    "MockLabAuthorizationInput",
    "MockRunAction",
    "MockRunActionRequest",
    "MockRunActionResult",
    "MockRunAuditEvent",
    "MockRunAuditEventType",
    "MockRunErrorCode",
    "MockRunPersistenceMetadata",
    "MockRunPollingPolicy",
    "MockRunRecoveryService",
    "MockWholeBookRunExecutor",
    "PartialResultGate",
    "ProtocolShapeFixture",
    "action_allowed_for_state",
    "all_mock_run_error_codes",
    "evaluate_mock_lab_authorization",
    "first_failed_create_precheck",
    "interval_for_status",
    "is_allowed_run_transition",
    "is_partial_result_readable",
    "occupies_active_slot",
    "validate_transition_or_raise",
]
