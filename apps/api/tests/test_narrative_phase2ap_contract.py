"""Phase 2A-P Mock Run Shell contract verification (directed tests only)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey, WholeBookStageKey
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.actions import (
    MockRunAction,
    MockRunActionRequest,
    action_allowed_for_state,
)
from app.narrative_core.run_shell_contract.api_routes import (
    DEFAULT_LAB_API_ROUTE_POLICY,
    LAB_API_ROUTES,
    PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH,
)
from app.narrative_core.run_shell_contract.audit import MockRunAuditEvent, MockRunAuditEventType
from app.narrative_core.run_shell_contract.create_run import (
    CREATE_MOCK_RUN_SEQUENCE,
    CreateMockRunValidationContext,
    CreateMockWholeBookRunRequest,
    CreateMockWholeBookRunResult,
    MockProfile,
    MockRunPersistenceMetadata,
    first_failed_create_precheck,
)
from app.narrative_core.run_shell_contract.errors import (
    MockRunErrorCode,
    all_mock_run_error_codes,
    mock_run_error,
)
from app.narrative_core.run_shell_contract.executor import (
    EXECUTOR_PROTOCOL_METHODS,
    FORMAL_ENGINE_FORBIDDEN_HOOK_ATTRS,
    MockExecutorTestHooks,
    MockWholeBookRunExecutor,
    ProtocolShapeFixture,
)
from app.narrative_core.run_shell_contract.idempotency import (
    DEFAULT_MOCK_RUN_CONCURRENCY_POLICY,
    occupies_active_slot,
)
from app.narrative_core.run_shell_contract.mock_lab import (
    WHOLE_BOOK_MOCK_LAB_ENABLED,
    MockLabAuthorizationInput,
    evaluate_mock_lab_authorization,
)
from app.narrative_core.run_shell_contract.partial_result import (
    PartialResultAvailability,
    PartialResultGate,
    is_partial_result_readable,
)
from app.narrative_core.run_shell_contract.polling import (
    DEFAULT_MOCK_RUN_POLLING_POLICY,
    MockRunPollingPolicy,
    PollingBackoffPolicy,
    interval_for_status,
)
from app.narrative_core.run_shell_contract.quota import (
    DEFAULT_MOCK_EXECUTION_QUOTA_POLICY,
    deny_budget_at_stage,
)
from app.narrative_core.run_shell_contract.recovery import (
    CHECKPOINT_SCHEMA,
    CHECKPOINT_VERSION,
    DEFAULT_RECOVERY_SCAN_POLICY,
    MockCheckpointRef,
    MockResumePlan,
    decide_lab_disabled_recovery,
    engine_version_mismatch_decision,
)
from app.narrative_core.run_shell_contract.run_state import (
    ALLOWED_RUN_TRANSITIONS,
    RunStateTransitionRequest,
    can_resume,
    is_allowed_run_transition,
    validate_transition_or_raise,
)
from app.narrative_core.run_shell_contract.stage_lifecycle import (
    ORDERED_MOCK_STAGE_KEYS,
    STAGE_LIFECYCLE_RULES,
    build_stage_retry_impact,
)
from app.narrative_core.run_shell_contract.task_registry import (
    TASK_REGISTRY_PROTOCOL_METHODS,
    InMemoryMockRunTaskRegistryFixture,
    InProcessMockRunTaskRegistry,
)
REPO_ROOT = Path(__file__).resolve().parents[3]
FE_CONTRACTS = (
    REPO_ROOT
    / "apps"
    / "desktop"
    / "src"
    / "features"
    / "wholeBook"
    / "runShell"
    / "contracts"
)
PRODUCT_EDITION = REPO_ROOT / "apps" / "desktop" / "src" / "services" / "productEdition.ts"
DOCS = REPO_ROOT / "docs" / "architecture" / "narrative-intelligence-core"
ENGINE_REGISTRY_SRC = (
    REPO_ROOT
    / "apps"
    / "api"
    / "app"
    / "narrative_core"
    / "services"
    / "whole_book_engine_registry.py"
)


def _ts_string_array(name: str, text: str) -> list[str]:
    pattern = rf"export const {name} = \[([\s\S]*?)\] as const"
    match = re.search(pattern, text)
    assert match, f"missing {name}"
    return re.findall(r'"([^"]+)"', match.group(1))


def _lab_input(**overrides: object) -> MockLabAuthorizationInput:
    base = {
        "environment": "development",
        "loopback": True,
        "lab_enabled": True,
        "request_marker_present": True,
        "requested_engine_id": "mock_whole_book_v0",
        "engine_is_mock": True,
        "engine_non_production": True,
        "capability_context_is_lab": True,
    }
    base.update(overrides)
    return MockLabAuthorizationInput(**base)  # type: ignore[arg-type]


def test_mock_lab_default_disabled() -> None:
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False
    decision = evaluate_mock_lab_authorization(_lab_input(lab_enabled=False))
    assert decision.allowed is False
    assert decision.reason_code == "MOCK_LAB_DISABLED"


def test_production_environment_rejected() -> None:
    decision = evaluate_mock_lab_authorization(_lab_input(environment="production"))
    assert decision.allowed is False
    assert decision.reason_code == "MOCK_LAB_ENVIRONMENT_NOT_ALLOWED"


def test_non_loopback_rejected() -> None:
    decision = evaluate_mock_lab_authorization(_lab_input(loopback=False))
    assert decision.allowed is False
    assert decision.reason_code == "MOCK_LAB_LOOPBACK_REQUIRED"


def test_missing_marker_rejected() -> None:
    decision = evaluate_mock_lab_authorization(_lab_input(request_marker_present=False))
    assert decision.allowed is False
    assert decision.reason_code == "MOCK_LAB_REQUEST_MARKER_REQUIRED"


def test_non_mock_engine_rejected() -> None:
    decision = evaluate_mock_lab_authorization(
        _lab_input(requested_engine_id="real_engine", engine_is_mock=False)
    )
    assert decision.allowed is False
    assert decision.reason_code == "MOCK_LAB_ENGINE_REQUIRED"


def test_engine_not_non_production_rejected() -> None:
    decision = evaluate_mock_lab_authorization(_lab_input(engine_non_production=False))
    assert decision.allowed is False
    assert decision.reason_code == "MOCK_LAB_ENGINE_NOT_PRODUCTION_SAFE"


def test_lab_allowed_when_all_gates_pass() -> None:
    decision = evaluate_mock_lab_authorization(_lab_input())
    assert decision.allowed is True
    assert decision.reason_code is None


def test_create_request_dto() -> None:
    req = CreateMockWholeBookRunRequest(
        book_id=1,
        book_snapshot_id=2,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        requested_modules=(WholeBookModuleKey.BOOK_OVERVIEW,),
        configuration_fingerprint="cfg-1",
        idempotency_key="idem-1",
        mock_profile=MockProfile.DETERMINISTIC_MINIMAL,
        requested_by="tester",
        preflight_fingerprint="pf-1",
    )
    assert req.book_id == 1
    with pytest.raises(ValueError, match="full body"):
        CreateMockWholeBookRunRequest(
            book_id=1,
            book_snapshot_id=2,
            analysis_mode=WholeBookAnalysisMode.NATIVE,
            requested_modules=(WholeBookModuleKey.BOOK_OVERVIEW,),
            configuration_fingerprint="cfg-1",
            idempotency_key="idem-1",
            mock_profile=MockProfile.DETERMINISTIC_MINIMAL,
            requested_by="tester",
            preflight_fingerprint="pf-1",
            extra_payload_keys=("full_text",),
        )


def test_idempotency_result_shape() -> None:
    created = CreateMockWholeBookRunResult(
        run_id=10,
        book_id=1,
        book_snapshot_id=2,
        status=WholeBookRunViewStatus.PENDING,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        requested_modules=(WholeBookModuleKey.BOOK_OVERVIEW,),
        resolved_modules=(WholeBookModuleKey.BOOK_OVERVIEW,),
        stage_plan=("build_fulltext_index",),
        mock=True,
        non_production=True,
        created=True,
        duplicate_of_run_id=None,
        created_at="2026-07-23T00:00:00Z",
    )
    assert created.created is True
    replay = CreateMockWholeBookRunResult(
        run_id=10,
        book_id=1,
        book_snapshot_id=2,
        status=WholeBookRunViewStatus.PENDING,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        requested_modules=(WholeBookModuleKey.BOOK_OVERVIEW,),
        resolved_modules=(WholeBookModuleKey.BOOK_OVERVIEW,),
        stage_plan=("build_fulltext_index",),
        mock=True,
        non_production=True,
        created=False,
        duplicate_of_run_id=10,
        created_at="2026-07-23T00:00:00Z",
    )
    assert replay.duplicate_of_run_id == 10


def test_snapshot_completed_precheck() -> None:
    ctx = CreateMockRunValidationContext(
        lab_allowed=True,
        book_exists=True,
        snapshot_exists=True,
        snapshot_belongs_to_book=True,
        snapshot_completed=False,
        preflight_fresh=True,
        mode_valid=True,
        modules_valid=True,
        dependencies_resolvable=True,
        mock_engine_available=True,
        concurrency_ok=True,
        no_active_conflict=True,
    )
    assert first_failed_create_precheck(ctx) == "snapshot_completed"
    assert CREATE_MOCK_RUN_SEQUENCE[0] == "authorize"


def test_run_metadata_schema() -> None:
    meta = MockRunPersistenceMetadata(
        book_id=1,
        book_snapshot_id=2,
        analysis_mode=WholeBookAnalysisMode.NATIVE.value,
        requested_modules=("book_overview",),
        resolved_modules=("book_overview",),
        engine_version="0.1.0-mock",
        configuration_fingerprint="cfg",
    )
    assert meta.schema == "mock_whole_book_run_metadata"
    assert meta.version == "1.0.0"
    assert meta.mock is True
    assert meta.source == "mock_lab"


def test_run_state_transitions_legal() -> None:
    assert is_allowed_run_transition("pending", "running")
    assert is_allowed_run_transition("running", "paused")
    assert is_allowed_run_transition("paused", "running")
    assert is_allowed_run_transition("interrupted", "running")
    assert is_allowed_run_transition("failed", "running")
    assert is_allowed_run_transition("running", "running")  # idempotent


def test_illegal_run_transitions() -> None:
    assert not is_allowed_run_transition("completed", "running")
    assert not is_allowed_run_transition("cancelled", "running")
    assert not is_allowed_run_transition("pending", "completed")
    with pytest.raises(ValueError, match="illegal"):
        validate_transition_or_raise("completed", "running")
    assert can_resume("completed") is False
    assert can_resume("cancelled") is False
    assert can_resume("paused") is True
    assert can_resume("failed") is False  # retry, not resume


def test_expected_state_required() -> None:
    with pytest.raises(ValueError, match="expected_state or expected_version"):
        RunStateTransitionRequest(
            run_id=1,
            from_state=WholeBookRunViewStatus.PENDING,
            to_state=WholeBookRunViewStatus.RUNNING,
        )
    req = RunStateTransitionRequest(
        run_id=1,
        from_state=WholeBookRunViewStatus.PENDING,
        to_state=WholeBookRunViewStatus.RUNNING,
        expected_state=WholeBookRunViewStatus.PENDING,
    )
    assert req.expected_state == WholeBookRunViewStatus.PENDING


def test_stage_lifecycle_catalog() -> None:
    assert len(ORDERED_MOCK_STAGE_KEYS) == 10
    assert ORDERED_MOCK_STAGE_KEYS[0] == WholeBookStageKey.BUILD_FULLTEXT_INDEX
    assert ORDERED_MOCK_STAGE_KEYS[-1] == WholeBookStageKey.PERSIST_NARRATIVE_ASSETS
    assert "completed_stages_do_not_rerun" in STAGE_LIFECYCLE_RULES


def test_retry_attempt_impact_and_cancel() -> None:
    impact = build_stage_retry_impact(WholeBookStageKey.ANALYZE_STRUCTURE.value)
    assert WholeBookStageKey.ANALYZE_STORYLINES.value in impact.reset_downstream_stage_keys
    assert impact.preserve_historical_artifacts is True
    assert action_allowed_for_state(MockRunAction.CANCEL, "running")
    with pytest.raises(ValueError, match="confirm_cancel"):
        MockRunActionRequest(
            run_id=1,
            action=MockRunAction.CANCEL,
            operation_idempotency_key="op-1",
            expected_state=WholeBookRunViewStatus.RUNNING,
            confirm_cancel=False,
        )


def test_executor_protocol() -> None:
    fixture = ProtocolShapeFixture()
    assert isinstance(fixture, MockWholeBookRunExecutor)
    for name in EXECUTOR_PROTOCOL_METHODS:
        assert hasattr(fixture, name)
    hooks = MockExecutorTestHooks(fail_at_stage=WholeBookStageKey.ANALYZE_HOOKS)
    assert hooks.fail_at_stage == WholeBookStageKey.ANALYZE_HOOKS
    assert "fail_at_stage" in FORMAL_ENGINE_FORBIDDEN_HOOK_ATTRS


def test_task_registry_single_run_single_task() -> None:
    reg = InMemoryMockRunTaskRegistryFixture()
    assert isinstance(reg, InProcessMockRunTaskRegistry)
    for name in TASK_REGISTRY_PROTOCOL_METHODS:
        assert hasattr(reg, name)
    a = reg.register(7)
    b = reg.register(7)
    assert a.run_id == b.run_id == 7
    assert len([h for h in reg.list() if h.run_id == 7]) == 1


def test_polling_policy() -> None:
    policy = DEFAULT_MOCK_RUN_POLLING_POLICY
    assert policy.running_interval_ms >= 1000
    assert policy.paused_interval_ms >= 3000
    assert policy.terminal_stop is True
    assert interval_for_status(policy, "completed") is None
    assert interval_for_status(policy, "running") == 1500
    with pytest.raises(ValueError, match="safety floor"):
        MockRunPollingPolicy(
            initial_interval_ms=100,
            running_interval_ms=100,
            paused_interval_ms=100,
            terminal_stop=True,
            max_consecutive_errors=3,
            backoff_policy=PollingBackoffPolicy.EXPONENTIAL,
        )


def test_partial_results() -> None:
    gate = PartialResultGate(
        at_least_one_module_stage_completed=True,
        projection_status=PartialResultAvailability.PARTIAL,
        artifact_schema_valid=True,
        snapshot_consistent=True,
    )
    assert is_partial_result_readable(gate)
    bad = PartialResultGate(
        at_least_one_module_stage_completed=False,
        projection_status=PartialResultAvailability.PARTIAL,
        artifact_schema_valid=True,
        snapshot_consistent=True,
    )
    assert not is_partial_result_readable(bad)


def test_recovery_plan_and_checkpoint_version() -> None:
    plan = MockResumePlan(
        run_id=1,
        resume_from_stage_key="analyze_structure",
        skip_completed_stages=("build_fulltext_index", "resolve_entities"),
        reset_downstream_stage_keys=(),
    )
    assert plan.requires_explicit_resume is True
    assert DEFAULT_RECOVERY_SCAN_POLICY.on_startup_auto_resume is False
    cp = MockCheckpointRef(
        schema=CHECKPOINT_SCHEMA,
        version=CHECKPOINT_VERSION,
        stage_key="analyze_structure",
        attempt=1,
        compatible=True,
    )
    assert cp.version == "1.0.0"
    disabled = decide_lab_disabled_recovery(9)
    assert disabled.marked_interrupted is True
    assert disabled.resume_plan is None


def test_engine_version_mismatch() -> None:
    decision = engine_version_mismatch_decision(3)
    assert decision.reason_code == MockRunErrorCode.MOCK_RUN_ENGINE_VERSION_MISMATCH
    assert decision.recoverable is False


def test_quota_budget_distinct() -> None:
    q = DEFAULT_MOCK_EXECUTION_QUOTA_POLICY
    assert q.non_production is True
    assert q.writes_commercial_usage is False
    assert q.separate_from_cloud_budget is True
    assert q.persist_across_restart is False
    deny = deny_budget_at_stage("analyze_hooks")
    assert deny.allowed is False
    assert deny.write_assets_on_deny is False
    assert deny.release_execution_slot_on_deny is True


def test_error_codes_unique() -> None:
    codes = all_mock_run_error_codes()
    assert len(codes) == len(set(codes))
    assert "MOCK_LAB_DISABLED" in codes
    assert "MOCK_RUN_NON_MOCK_TARGET" in codes
    err = mock_run_error(MockRunErrorCode.MOCK_RUN_NOT_FOUND)
    assert "not found" in err.message.lower()


def test_audit_event() -> None:
    event = MockRunAuditEvent(
        event_id="evt-1",
        run_id=1,
        event_type=MockRunAuditEventType.RUN_STATE_CHANGED,
        previous_state="pending",
        new_state="running",
        stage_key=None,
        attempt=None,
        actor="lab",
        mock=True,
        non_production=True,
        idempotency_key="idem-1",
        occurred_at="2026-07-23T00:00:00Z",
        detail_code="started",
    )
    assert event.mock is True
    with pytest.raises(ValueError, match="forbidden"):
        MockRunAuditEvent(
            event_id="evt-2",
            run_id=1,
            event_type=MockRunAuditEventType.RUN_CREATED,
            previous_state=None,
            new_state="pending",
            stage_key=None,
            attempt=None,
            actor="lab",
            mock=True,
            non_production=True,
            idempotency_key=None,
            occurred_at="2026-07-23T00:00:00Z",
            detail_message="contains api_key leak",
        )


def test_frontend_backend_status_parity() -> None:
    text = (FE_CONTRACTS / "runState.ts").read_text(encoding="utf-8")
    # Parse ALLOWED_RUN_TRANSITIONS keys from backend enum
    be_statuses = {s.value for s in WholeBookRunViewStatus}
    fe_active = _ts_string_array("ACTIVE_RUN_STATUSES", text)
    assert set(fe_active) <= be_statuses
    for status, targets in ALLOWED_RUN_TRANSITIONS.items():
        assert status.value in be_statuses
        assert isinstance(targets, frozenset)


def test_frontend_backend_error_code_parity() -> None:
    text = (FE_CONTRACTS / "errors.ts").read_text(encoding="utf-8")
    fe_codes = _ts_string_array("MOCK_RUN_ERROR_CODES", text)
    be_codes = list(all_mock_run_error_codes())
    assert sorted(fe_codes) == sorted(be_codes)


def test_lab_api_and_production_create_disabled() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert DEFAULT_LAB_API_ROUTE_POLICY.production_create_disabled is True
    assert PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH.startswith("/api/v1/books/")
    assert any(path.endswith("/pause") for _, path in LAB_API_ROUTES)
    assert occupies_active_slot("running")
    assert not occupies_active_slot("failed")
    assert DEFAULT_MOCK_RUN_CONCURRENCY_POLICY.max_active_mock_runs_per_book == 1


def test_pro_capabilities_shipped_false() -> None:
    text = PRODUCT_EDITION.read_text(encoding="utf-8")
    assert re.search(r"PRO_CAPABILITIES_SHIPPED\s*=\s*false", text)


def test_production_default_engine_none() -> None:
    # Read source directly to avoid importing services package (SQLAlchemy side effects).
    text = ENGINE_REGISTRY_SRC.read_text(encoding="utf-8")
    assert re.search(
        r"^PRODUCTION_DEFAULT_ENGINE_ID:\s*str\s*\|\s*None\s*=\s*None\s*$",
        text,
        re.MULTILINE,
    )


def test_no_new_migration_for_phase2a() -> None:
    ownership = (DOCS / "phase2a-parallel-file-ownership.json").read_text(encoding="utf-8")
    assert "migrations / new DB tables" in ownership
    # Phase 2A-P change set must not introduce migration modules.
    run_shell = REPO_ROOT / "apps" / "api" / "app" / "narrative_core" / "run_shell_contract"
    assert run_shell.is_dir()
    assert not list(run_shell.rglob("*migration*"))
    assert not list((REPO_ROOT / "apps" / "api").rglob("alembic/versions/*.py"))


def test_ownership_and_docs_exist() -> None:
    required = [
        "phase2a-run-shell-overview.md",
        "phase2a-mock-lab-security.md",
        "phase2a-run-creation-contract.md",
        "phase2a-run-state-machine.md",
        "phase2a-stage-lifecycle.md",
        "phase2a-mock-executor-contract.md",
        "phase2a-task-registry-contract.md",
        "phase2a-mock-run-api.md",
        "phase2a-frontend-lab-contract.md",
        "phase2a-polling-contract.md",
        "phase2a-partial-result-contract.md",
        "phase2a-run-actions-contract.md",
        "phase2a-idempotency-concurrency.md",
        "phase2a-recovery-contract.md",
        "phase2a-mock-quota-budget.md",
        "phase2a-error-contract.md",
        "phase2a-audit-contract.md",
        "phase2a-parallel-file-ownership.md",
        "phase2a-parallel-file-ownership.json",
        "phase2a-contract-verification.md",
    ]
    for name in required:
        assert (DOCS / name).is_file(), name
    assert (FE_CONTRACTS / "index.ts").is_file()
    assert (FE_CONTRACTS / "mockLab.ts").is_file()


def test_fe_lab_flag_default_false() -> None:
    text = (FE_CONTRACTS / "mockLab.ts").read_text(encoding="utf-8")
    assert "WHOLE_BOOK_MOCK_LAB_ENABLED = false" in text
