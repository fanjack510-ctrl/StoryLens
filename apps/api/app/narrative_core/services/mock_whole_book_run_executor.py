"""Default Mock Whole-Book Run Executor (Phase 2A Agent M).

Single-process, local, deterministic, non-production.
Wires Phase 1C MockWholeBookAnalysisEngine + WholeBookStageOrchestrator.
Lab-only test hooks never appear on formal Engine Protocol.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun
from app.narrative_core.capability_registry import get_capability_metadata
from app.narrative_core.contracts.capability import CapabilityDecision
from app.narrative_core.contracts.whole_book_dto import WholeBookAnalysisRequest
from app.narrative_core.enums import (
    CapabilityAvailability,
    CapabilityKey,
    CapabilityReasonCode,
    RunStatus,
    SnapshotStatus,
    StageStatus,
    WholeBookAnalysisMode,
    WholeBookStageKey,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.errors import MockRunErrorCode, mock_run_error
from app.narrative_core.run_shell_contract.executor import (
    MockExecutionState,
    MockExecutorActionResult,
    MockExecutorTestHooks,
)
from app.narrative_core.run_shell_contract.recovery import CHECKPOINT_SCHEMA, CHECKPOINT_VERSION
from app.narrative_core.services.in_process_mock_run_task_registry import (
    InProcessMockRunTaskRegistry,
    get_default_mock_run_task_registry,
)
from app.narrative_core.services.mock_run_metadata import (
    MockRunMetadataError,
    parse_metadata_json,
    serialize_metadata,
)
from app.narrative_core.services.mock_run_state_service import (
    MockRunStateError,
    MockRunStateService,
    map_db_status_to_view,
)
from app.narrative_core.services.mock_whole_book_engine import MockWholeBookAnalysisEngine
from app.narrative_core.services.run_stage_service import RunStageService
from app.narrative_core.services.whole_book_engine_adapters import (
    AnalysisConflictSinkAdapter,
    ArtifactWriterAdapter,
    BudgetGuardAdapter,
    CancellationTokenImpl,
    NarrativeAssetWriterAdapter,
    NarrativeRelationWriterAdapter,
    RunBindingResolver,
    SnapshotReaderAdapter,
)
from app.narrative_core.services.whole_book_stage_orchestrator import WholeBookStageOrchestrator


class MockExecutorError(Exception):
    def __init__(
        self,
        code: MockRunErrorCode,
        *,
        run_id: int | None = None,
        stage_key: str | None = None,
    ) -> None:
        self.error = mock_run_error(code, run_id=run_id, stage_key=stage_key)
        super().__init__(self.error.message)


def _lab_capability() -> CapabilityDecision:
    meta = get_capability_metadata(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    return CapabilityDecision(
        capability_key=CapabilityKey.WHOLE_BOOK_ANALYSIS,
        allowed=True,
        reason_code=CapabilityReasonCode.CAPABILITY_AVAILABLE,
        availability=CapabilityAvailability.AVAILABLE,
        display_message="mock lab override",
        metadata=meta,
        preview_only=True,
    )


class DefaultMockWholeBookRunExecutor:
    """Implements MockWholeBookRunExecutor Protocol for Lab only."""

    def __init__(
        self,
        session: Session,
        *,
        stage_service: RunStageService | None = None,
        state_service: MockRunStateService | None = None,
        task_registry: InProcessMockRunTaskRegistry | None = None,
        engine: MockWholeBookAnalysisEngine | None = None,
        hooks: MockExecutorTestHooks | None = None,
        lab_hooks_allowed: bool = True,
        idempotency: Any | None = None,
        concurrency: Any | None = None,
        budget_guard: Any | None = None,
        audit: Any | None = None,
        fault_injection: Any | None = None,
    ) -> None:
        self._session = session
        self._stages = stage_service or RunStageService(session)
        self._state = state_service or MockRunStateService(session)
        self._registry = task_registry or get_default_mock_run_task_registry()
        self._snapshot_reader = SnapshotReaderAdapter(session)
        self._binding = RunBindingResolver(session)
        self._asset_writer = NarrativeAssetWriterAdapter(session)
        self._relation_writer = NarrativeRelationWriterAdapter(session)
        self._artifact_writer = ArtifactWriterAdapter(session)
        self._conflict_sink = AnalysisConflictSinkAdapter(session)
        self._budget = BudgetGuardAdapter()
        self._cancel = CancellationTokenImpl()
        self._engine = engine or MockWholeBookAnalysisEngine(
            snapshot_reader=self._snapshot_reader,
            binding_resolver=self._binding,
        )
        self._orch = WholeBookStageOrchestrator(
            engine=self._engine,
            run_stage_service=self._stages,
            snapshot_reader=self._snapshot_reader,
            asset_writer=self._asset_writer,
            relation_writer=self._relation_writer,
            artifact_writer=self._artifact_writer,
            conflict_sink=self._conflict_sink,
            budget_guard=self._budget,
            cancellation_token=self._cancel,
        )
        if hooks is not None and not lab_hooks_allowed:
            raise MockExecutorError(MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED)
        self._hooks = hooks or MockExecutorTestHooks()
        self._lab_hooks_allowed = bool(lab_hooks_allowed)
        self._started: set[int] = set()
        # Optional Agent O wiring (Integration composition root).
        self._idempotency = idempotency
        self._concurrency = concurrency
        self._mock_budget = budget_guard
        self._audit = audit
        self._fault = fault_injection

    # ----- Protocol -----

    def start(self, run_id: int) -> MockExecutorActionResult:
        run, meta = self._require_mock_run(run_id)
        current = map_db_status_to_view(str(run.status))
        if current == WholeBookRunViewStatus.RUNNING:
            self._registry.register(int(run.id))
            self._registry.mark_running(int(run.id))
            self._started.add(int(run.id))
            return MockExecutorActionResult(
                run_id=int(run.id),
                accepted=True,
                requested=True,
                current_state=current,
            )
        if current not in {
            WholeBookRunViewStatus.PENDING,
            WholeBookRunViewStatus.PAUSED,
            WholeBookRunViewStatus.INTERRUPTED,
            WholeBookRunViewStatus.FAILED,
        }:
            raise MockExecutorError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED, run_id=int(run.id)
            )
        try:
            result = self._state.transition(
                run,
                to_state=WholeBookRunViewStatus.RUNNING,
                expected_state=current,
                metadata=meta,
            )
        except MockRunStateError as exc:
            raise MockExecutorError(exc.error.code, run_id=int(run.id)) from exc
        meta["state_version"] = result.version
        run.validated_output = serialize_metadata(meta, existing_validated_output=run.validated_output)
        run.status = RunStatus.RUNNING.value
        self._registry.register(int(run.id))
        self._registry.mark_running(int(run.id))
        self._started.add(int(run.id))
        self._cancel = CancellationTokenImpl()
        self._orch.cancellation_token = self._cancel
        self._orch.cancelled = False
        self._session.commit()
        return MockExecutorActionResult(
            run_id=int(run.id),
            accepted=True,
            requested=True,
            current_state=WholeBookRunViewStatus.RUNNING,
        )

    def execute_next_stage(self, run_id: int) -> MockExecutorActionResult:
        run, meta = self._require_mock_run(run_id)
        if map_db_status_to_view(str(run.status)) != WholeBookRunViewStatus.RUNNING:
            # Auto-start pending runs for Lab convenience.
            if map_db_status_to_view(str(run.status)) == WholeBookRunViewStatus.PENDING:
                self.start(run_id)
                run, meta = self._require_mock_run(run_id)
            else:
                raise MockExecutorError(
                    MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED, run_id=int(run_id)
                )

        self._check_cancel_before(run_id)
        stage_key = self._next_executable_stage(run_id)
        if stage_key is None:
            self._mark_completed(run, meta)
            return MockExecutorActionResult(
                run_id=int(run_id),
                accepted=True,
                requested=True,
                current_state=WholeBookRunViewStatus.COMPLETED,
            )

        blocked = self._apply_hooks_before_stage(run, meta, stage_key)
        if blocked is not None:
            return blocked

        request = self._build_request(run, meta)
        if not self._orch.last_plan_keys:
            self._orch.validate_and_plan(request)

        try:
            result = self._orch.execute_current_stage(request, stage_key)
        except NarrativeCoreError as exc:
            return self._handle_stage_error(run, meta, stage_key, exc)

        self._check_cancel_after(run_id)
        self._session.commit()

        if result.status == StageStatus.PAUSED:
            self._transition_run(run, meta, WholeBookRunViewStatus.PAUSED)
            return MockExecutorActionResult(
                run_id=int(run_id),
                accepted=True,
                requested=True,
                current_state=WholeBookRunViewStatus.PAUSED,
                stage_key=stage_key,
            )
        if result.status == StageStatus.FAILED:
            self._transition_run(run, meta, WholeBookRunViewStatus.FAILED)
            return MockExecutorActionResult(
                run_id=int(run_id),
                accepted=True,
                requested=True,
                current_state=WholeBookRunViewStatus.FAILED,
                stage_key=stage_key,
                detail_code=result.message,
            )

        # If all stages completed, mark run completed.
        if self._next_executable_stage(run_id) is None:
            self._mark_completed(run, meta)
            return MockExecutorActionResult(
                run_id=int(run_id),
                accepted=True,
                requested=True,
                current_state=WholeBookRunViewStatus.COMPLETED,
                stage_key=stage_key,
            )

        return MockExecutorActionResult(
            run_id=int(run_id),
            accepted=True,
            requested=True,
            current_state=WholeBookRunViewStatus.RUNNING,
            stage_key=stage_key,
        )

    def execute_until_blocked(self, run_id: int) -> MockExecutorActionResult:
        last = self.execute_next_stage(run_id)
        while last.current_state == WholeBookRunViewStatus.RUNNING:
            if self._registry.is_pause_requested(run_id) or self._registry.is_cancel_requested(
                run_id
            ):
                break
            nxt = self._next_executable_stage(run_id)
            if nxt is None:
                break
            last = self.execute_next_stage(run_id)
            if last.current_state != WholeBookRunViewStatus.RUNNING:
                break
        return last

    def pause(self, run_id: int) -> MockExecutorActionResult:
        run, meta = self._require_mock_run(run_id)
        current = map_db_status_to_view(str(run.status))
        if current == WholeBookRunViewStatus.PAUSED:
            return MockExecutorActionResult(
                run_id=int(run_id),
                accepted=True,
                requested=True,
                current_state=current,
            )
        self._registry.request_pause(run_id)
        # Cooperative: pause currently running stages + checkpoint.
        self._stages.pause_run(int(run_id))
        self._transition_run(run, meta, WholeBookRunViewStatus.PAUSED, expected=current)
        return MockExecutorActionResult(
            run_id=int(run_id),
            accepted=True,
            requested=True,
            current_state=WholeBookRunViewStatus.PAUSED,
        )

    def resume(self, run_id: int) -> MockExecutorActionResult:
        run, meta = self._require_mock_run(run_id)
        current = map_db_status_to_view(str(run.status))
        if current == WholeBookRunViewStatus.RUNNING:
            return MockExecutorActionResult(
                run_id=int(run_id),
                accepted=True,
                requested=True,
                current_state=current,
            )
        if current not in {
            WholeBookRunViewStatus.PAUSED,
            WholeBookRunViewStatus.INTERRUPTED,
        }:
            raise MockExecutorError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED, run_id=int(run_id)
            )
        self._registry.clear_pause_request(run_id)
        self._stages.resume_run(int(run_id))
        self._transition_run(run, meta, WholeBookRunViewStatus.RUNNING, expected=current)
        self._registry.mark_running(run_id)
        return MockExecutorActionResult(
            run_id=int(run_id),
            accepted=True,
            requested=True,
            current_state=WholeBookRunViewStatus.RUNNING,
        )

    def retry_stage(self, run_id: int, stage_key: str) -> MockExecutorActionResult:
        run, meta = self._require_mock_run(run_id)
        stage = self._stages._stages.get_stage(int(run_id), stage_key)  # noqa: SLF001
        if stage is None:
            raise MockExecutorError(
                MockRunErrorCode.MOCK_RUN_NOT_FOUND, run_id=int(run_id), stage_key=stage_key
            )
        if StageStatus(stage.status) == StageStatus.COMPLETED:
            raise MockExecutorError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED,
                run_id=int(run_id),
                stage_key=stage_key,
            )
        if StageStatus(stage.status) != StageStatus.FAILED:
            raise MockExecutorError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED,
                run_id=int(run_id),
                stage_key=stage_key,
            )
        request = self._build_request(run, meta)
        current = map_db_status_to_view(str(run.status))
        if current != WholeBookRunViewStatus.RUNNING:
            self._transition_run(
                run, meta, WholeBookRunViewStatus.RUNNING, expected=current
            )
        self._orch.retry(request, stage_key)
        self._session.commit()
        return MockExecutorActionResult(
            run_id=int(run_id),
            accepted=True,
            requested=True,
            current_state=WholeBookRunViewStatus.RUNNING,
            stage_key=stage_key,
        )

    def cancel(self, run_id: int) -> MockExecutorActionResult:
        run, meta = self._require_mock_run(run_id)
        current = map_db_status_to_view(str(run.status))
        if current == WholeBookRunViewStatus.CANCELLED:
            return MockExecutorActionResult(
                run_id=int(run_id),
                accepted=True,
                requested=True,
                current_state=current,
            )
        self._check_cancel_before(run_id)
        self._registry.request_cancel(run_id)
        self._cancel.cancel()
        self._orch.cancelled = True
        stage_key = self._current_or_next_stage(run_id)
        request = self._build_request(run, meta)
        self._orch.cancel(request, stage_key)
        for stage in self._stages.get_run_stages(int(run_id)):
            st = StageStatus(stage.status)
            if st in {
                StageStatus.PENDING,
                StageStatus.RUNNING,
                StageStatus.PAUSED,
                StageStatus.INTERRUPTED,
                StageStatus.FAILED,
            }:
                try:
                    self._stages.transition_stage(
                        int(run_id),
                        stage.stage_key,
                        StageStatus.CANCELLED,
                        error_code=MockRunErrorCode.MOCK_RUN_CANCELLED.value,
                        error_message="cancelled by mock executor",
                    )
                except NarrativeCoreError:
                    pass
        self._transition_run(run, meta, WholeBookRunViewStatus.CANCELLED, expected=current)
        self._registry.mark_finished(run_id)
        self._check_cancel_after(run_id)
        return MockExecutorActionResult(
            run_id=int(run_id),
            accepted=True,
            requested=True,
            current_state=WholeBookRunViewStatus.CANCELLED,
            detail_code=MockRunErrorCode.MOCK_RUN_CANCELLED.value,
        )

    def recover(self, run_id: int) -> MockExecutorActionResult:
        """Mark interrupted only ??no silent auto-continue (Agent O owns recovery core)."""
        run, meta = self._require_mock_run(run_id)
        current = map_db_status_to_view(str(run.status))
        if current in {
            WholeBookRunViewStatus.COMPLETED,
            WholeBookRunViewStatus.CANCELLED,
        }:
            raise MockExecutorError(
                MockRunErrorCode.MOCK_RUN_NOT_RECOVERABLE, run_id=int(run_id)
            )
        if current == WholeBookRunViewStatus.INTERRUPTED:
            return MockExecutorActionResult(
                run_id=int(run_id),
                accepted=True,
                requested=True,
                current_state=current,
            )
        self._stages.mark_interrupted(int(run_id))
        if current != WholeBookRunViewStatus.INTERRUPTED:
            try:
                self._transition_run(
                    run, meta, WholeBookRunViewStatus.INTERRUPTED, expected=current
                )
            except MockExecutorError:
                run.status = RunStatus.INTERRUPTED.value
                self._session.commit()
        return MockExecutorActionResult(
            run_id=int(run_id),
            accepted=True,
            requested=True,
            current_state=WholeBookRunViewStatus.INTERRUPTED,
        )

    def get_execution_state(self, run_id: int) -> MockExecutionState:
        run, meta = self._require_mock_run(run_id)
        stage_key = self._current_or_next_stage(run_id)
        checkpoint_schema = None
        checkpoint_version = None
        if stage_key is not None:
            stage = self._stages._stages.get_stage(int(run_id), stage_key)  # noqa: SLF001
            if stage is not None and stage.checkpoint_json:
                try:
                    import json

                    data = json.loads(stage.checkpoint_json)
                    checkpoint_schema = data.get("schema") or CHECKPOINT_SCHEMA
                    checkpoint_version = str(data.get("version") or CHECKPOINT_VERSION)
                except Exception:  # noqa: BLE001
                    checkpoint_schema = CHECKPOINT_SCHEMA
                    checkpoint_version = CHECKPOINT_VERSION
        handle = self._registry.get(int(run_id))
        return MockExecutionState(
            run_id=int(run_id),
            status=map_db_status_to_view(str(run.status)),
            current_stage_key=stage_key,
            checkpoint_schema=checkpoint_schema,
            checkpoint_version=checkpoint_version,
            mock=True,
            non_production=True,
            single_executor=True,
            task_registered=handle is not None,
        )

    # ----- Hooks / helpers -----

    def set_test_hooks(self, hooks: MockExecutorTestHooks) -> None:
        if not self._lab_hooks_allowed:
            raise MockExecutorError(MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED)
        self._hooks = hooks

    def _apply_hooks_before_stage(
        self,
        run: AnalysisRun,
        meta: dict[str, Any],
        stage_key: str,
    ) -> MockExecutorActionResult | None:
        hooks = self._hooks
        if hooks.stage_delay_ms > 0:
            time.sleep(hooks.stage_delay_ms / 1000.0)

        key_enum = WholeBookStageKey(stage_key)
        if hooks.budget_denied_at_stage == key_enum:
            self._budget.deny()
            row = self._stages._stages.get_stage(int(run.id), stage_key)  # noqa: SLF001
            assert row is not None
            if StageStatus(row.status) == StageStatus.PENDING:
                self._stages.transition_stage(int(run.id), stage_key, StageStatus.RUNNING)
            if StageStatus(
                self._stages._stages.get_stage(int(run.id), stage_key).status  # noqa: SLF001
            ) != StageStatus.FAILED:
                self._stages.transition_stage(
                    int(run.id),
                    stage_key,
                    StageStatus.FAILED,
                    error_code=MockRunErrorCode.MOCK_RUN_BUDGET_EXCEEDED.value,
                    error_message="mock lab budget denied hook",
                )
            self._transition_run(run, meta, WholeBookRunViewStatus.FAILED)
            return MockExecutorActionResult(
                run_id=int(run.id),
                accepted=True,
                requested=True,
                current_state=WholeBookRunViewStatus.FAILED,
                stage_key=stage_key,
                detail_code=MockRunErrorCode.MOCK_RUN_BUDGET_EXCEEDED.value,
            )

        if hooks.fail_at_stage == key_enum:
            row = self._stages._stages.get_stage(int(run.id), stage_key)  # noqa: SLF001
            assert row is not None
            if StageStatus(row.status) == StageStatus.PENDING:
                self._stages.transition_stage(int(run.id), stage_key, StageStatus.RUNNING)
            self._stages.transition_stage(
                int(run.id),
                stage_key,
                StageStatus.FAILED,
                error_code="MOCK_HOOK_FAIL",
                error_message="mock lab fail_at_stage hook",
            )
            self._transition_run(run, meta, WholeBookRunViewStatus.FAILED)
            return MockExecutorActionResult(
                run_id=int(run.id),
                accepted=True,
                requested=True,
                current_state=WholeBookRunViewStatus.FAILED,
                stage_key=stage_key,
                detail_code="MOCK_HOOK_FAIL",
            )

        if hooks.interrupt_at_stage == key_enum:
            self._stages.mark_interrupted(int(run.id))
            self._transition_run(run, meta, WholeBookRunViewStatus.INTERRUPTED)
            return MockExecutorActionResult(
                run_id=int(run.id),
                accepted=True,
                requested=True,
                current_state=WholeBookRunViewStatus.INTERRUPTED,
                stage_key=stage_key,
            )

        if hooks.pause_at_stage == key_enum:
            if StageStatus(
                self._stages._stages.get_stage(int(run.id), stage_key).status  # noqa: SLF001
            ) == StageStatus.PENDING:
                self._stages.transition_stage(int(run.id), stage_key, StageStatus.RUNNING)
            self._stages.write_checkpoint(
                int(run.id),
                stage_key,
                {
                    "schema": CHECKPOINT_SCHEMA,
                    "version": CHECKPOINT_VERSION,
                    "stage_key": stage_key,
                    "mock": True,
                    "reason": "pause_at_stage hook",
                },
            )
            self._stages.pause_run(int(run.id))
            self._transition_run(run, meta, WholeBookRunViewStatus.PAUSED)
            return MockExecutorActionResult(
                run_id=int(run.id),
                accepted=True,
                requested=True,
                current_state=WholeBookRunViewStatus.PAUSED,
                stage_key=stage_key,
            )
        return None

    def _handle_stage_error(
        self,
        run: AnalysisRun,
        meta: dict[str, Any],
        stage_key: str,
        exc: NarrativeCoreError,
    ) -> MockExecutorActionResult:
        if exc.code == NarrativeCoreErrorCode.WHOLE_BOOK_BUDGET_DENIED:
            self._transition_run(run, meta, WholeBookRunViewStatus.FAILED)
            return MockExecutorActionResult(
                run_id=int(run.id),
                accepted=True,
                requested=True,
                current_state=WholeBookRunViewStatus.FAILED,
                stage_key=stage_key,
                detail_code=MockRunErrorCode.MOCK_RUN_BUDGET_EXCEEDED.value,
            )
        if exc.code == NarrativeCoreErrorCode.WHOLE_BOOK_STAGE_CANCELLED:
            self._transition_run(run, meta, WholeBookRunViewStatus.CANCELLED)
            self._registry.mark_finished(int(run.id))
            return MockExecutorActionResult(
                run_id=int(run.id),
                accepted=True,
                requested=True,
                current_state=WholeBookRunViewStatus.CANCELLED,
                stage_key=stage_key,
                detail_code=MockRunErrorCode.MOCK_RUN_CANCELLED.value,
            )
        self._transition_run(run, meta, WholeBookRunViewStatus.FAILED)
        return MockExecutorActionResult(
            run_id=int(run.id),
            accepted=True,
            requested=True,
            current_state=WholeBookRunViewStatus.FAILED,
            stage_key=stage_key,
            detail_code=getattr(exc.code, "value", str(exc.code)),
        )

    def _require_mock_run(self, run_id: int) -> tuple[AnalysisRun, dict[str, Any]]:
        run = self._session.get(AnalysisRun, int(run_id))
        if run is None:
            raise MockExecutorError(MockRunErrorCode.MOCK_RUN_NOT_FOUND, run_id=int(run_id))
        try:
            meta = parse_metadata_json(run.validated_output)
        except MockRunMetadataError as exc:
            raise MockExecutorError(
                MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET, run_id=int(run_id)
            ) from exc
        return run, meta

    def _build_request(
        self, run: AnalysisRun, meta: dict[str, Any]
    ) -> WholeBookAnalysisRequest:
        return WholeBookAnalysisRequest(
            run_id=int(run.id),
            book_id=int(meta["book_id"]),
            book_snapshot_id=int(meta["book_snapshot_id"]),
            analysis_mode=WholeBookAnalysisMode(str(meta["analysis_mode"])),
            capability_context=_lab_capability(),
            configuration_fingerprint=str(meta["configuration_fingerprint"]),
            snapshot_status=SnapshotStatus.COMPLETED,
            extra={
                "bound_book_id": int(meta["book_id"]),
                "bound_snapshot_id": int(meta["book_snapshot_id"]),
                "mock_lab": True,
                "synthetic_output_profile": self._hooks.synthetic_output_profile,
            },
        )

    def _next_executable_stage(self, run_id: int) -> str | None:
        for stage in self._stages.get_run_stages(int(run_id)):
            st = StageStatus(stage.status)
            if st == StageStatus.COMPLETED:
                continue
            if st == StageStatus.SKIPPED:
                continue
            if st == StageStatus.CANCELLED:
                continue
            if st in {
                StageStatus.PENDING,
                StageStatus.RUNNING,
                StageStatus.PAUSED,
                StageStatus.INTERRUPTED,
                StageStatus.FAILED,
            }:
                # Do not auto-execute FAILED here ??requires retry.
                if st == StageStatus.FAILED:
                    return None
                return str(stage.stage_key)
        return None

    def _current_or_next_stage(self, run_id: int) -> str | None:
        stages = list(self._stages.get_run_stages(int(run_id)))
        for stage in stages:
            if StageStatus(stage.status) in {
                StageStatus.RUNNING,
                StageStatus.PAUSED,
                StageStatus.INTERRUPTED,
            }:
                return str(stage.stage_key)
        return self._next_executable_stage(run_id)

    def _transition_run(
        self,
        run: AnalysisRun,
        meta: dict[str, Any],
        to_state: WholeBookRunViewStatus,
        *,
        expected: WholeBookRunViewStatus | None = None,
    ) -> None:
        current = map_db_status_to_view(str(run.status))
        if current == to_state:
            return
        try:
            result = self._state.transition(
                run,
                to_state=to_state,
                expected_state=expected or current,
                metadata=meta,
            )
            meta["state_version"] = result.version
            run.validated_output = serialize_metadata(meta, existing_validated_output=run.validated_output)
            run.status = to_state.value if to_state != WholeBookRunViewStatus.PENDING else RunStatus.PENDING.value
            self._session.commit()
        except MockRunStateError as exc:
            raise MockExecutorError(exc.error.code, run_id=int(run.id)) from exc

    def _mark_completed(self, run: AnalysisRun, meta: dict[str, Any]) -> None:
        self._transition_run(run, meta, WholeBookRunViewStatus.COMPLETED)
        self._registry.mark_finished(int(run.id))

    def _check_cancel_before(self, run_id: int) -> None:
        if self._registry.is_cancel_requested(run_id) or self._cancel.is_cancelled():
            raise MockExecutorError(MockRunErrorCode.MOCK_RUN_CANCELLED, run_id=int(run_id))

    def _check_cancel_after(self, run_id: int) -> None:
        if self._registry.is_cancel_requested(run_id):
            # Soft signal ??cancel() applies terminal transition.
            self._cancel.cancel()


__all__ = ["DefaultMockWholeBookRunExecutor", "MockExecutorError"]
