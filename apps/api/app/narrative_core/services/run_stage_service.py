"""AnalysisRun stage lifecycle service (Agent B).

Implements pause / resume / interrupted / retry against the frozen Phase 1P matrix.
Composes RunScopeService so AnalysisRunService Protocol is satisfied as one facade.
"""

from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun
from app.narrative_core.contracts.snapshot import SnapshotValidationGateway
from app.narrative_core.enums import AnalysisScopeType, AnalysisType, RunStatus, StageStatus
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.run_scope_service import RunScopeService
from app.narrative_core.services.run_stage_repository import RunStageRepository
from app.narrative_core.services.snapshot_service import SnapshotValidationGatewayImpl


class RunStageService:
    """Run + stage orchestration. Does not call models or build snapshots."""

    def __init__(
        self,
        session: Session,
        *,
        snapshot_gateway: SnapshotValidationGateway | None = None,
        scope_service: RunScopeService | None = None,
        stage_repository: RunStageRepository | None = None,
    ) -> None:
        self._session = session
        # Production default: real SnapshotValidationGatewayImpl (Agent A).
        # Tests may inject StubSnapshotValidationGateway explicitly.
        if scope_service is not None:
            self._scope = scope_service
        else:
            gateway = snapshot_gateway
            if gateway is None:
                gateway = SnapshotValidationGatewayImpl(session)
            self._scope = RunScopeService(session, snapshot_gateway=gateway)
        self._stages = stage_repository or RunStageRepository(session)

    # ----- Scope (AnalysisRunService) -----

    def create_scoped_run(
        self,
        *,
        scope_type: AnalysisScopeType | str,
        analysis_type: AnalysisType | str,
        book_id: int | None = None,
        start_chapter_id: int | None = None,
        end_chapter_id: int | None = None,
        book_snapshot_id: int | None = None,
        **fields: Any,
    ) -> AnalysisRun:
        run = self._scope.create_scoped_run(
            scope_type=scope_type,
            analysis_type=analysis_type,
            book_id=book_id,
            start_chapter_id=start_chapter_id,
            end_chapter_id=end_chapter_id,
            book_snapshot_id=book_snapshot_id,
            **fields,
        )
        self._session.commit()
        self._session.refresh(run)
        return run

    def validate_run_scope(self, run: Any) -> None:
        self._scope.validate_run_scope(run)

    def bind_run_snapshot(self, run_id: int, book_snapshot_id: int) -> AnalysisRun:
        run = self._scope.bind_run_snapshot(run_id, book_snapshot_id)
        self._session.commit()
        self._session.refresh(run)
        return run

    # ----- Stages -----

    def get_run_stages(self, run_id: int) -> Sequence[Any]:
        return self._stages.get_run_stages(run_id)

    def initialize_run_stages(self, run_id: int, stage_keys: Sequence[str]) -> Sequence[Any]:
        stages = self._stages.initialize_run_stages(run_id, stage_keys)
        self._session.commit()
        return list(stages)

    def transition_stage(
        self,
        run_id: int,
        stage_key: str,
        target_status: StageStatus | str,
        **fields: Any,
    ) -> Any:
        stage = self._stages.transition_stage(run_id, stage_key, target_status, **fields)
        self._session.commit()
        self._session.refresh(stage)
        return stage

    def write_checkpoint(
        self,
        run_id: int,
        stage_key: str,
        checkpoint: dict[str, Any] | str,
        *,
        replace: bool = False,
        append_provider_attempt: Any | None = None,
        **accumulate_fields: Any,
    ) -> Any:
        stage = self._stages.write_checkpoint(
            run_id,
            stage_key,
            checkpoint,
            replace=replace,
            append_provider_attempt=append_provider_attempt,
            **accumulate_fields,
        )
        self._session.commit()
        self._session.refresh(stage)
        return stage

    def pause_run(self, run_id: int) -> AnalysisRun:
        """Pause currently running stages. Does not mark the run as failed."""
        run = self._require_run(run_id)
        for stage in self._stages.get_run_stages(run_id):
            if StageStatus(stage.status) == StageStatus.RUNNING:
                self._stages.transition_stage(
                    run_id, stage.stage_key, StageStatus.PAUSED
                )
            # pending / completed / failed / interrupted unchanged
        if run.status not in (
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        ):
            run.status = RunStatus.PAUSED
            run.error_code = None
        self._session.commit()
        self._session.refresh(run)
        return run

    def resume_run(self, run_id: int) -> AnalysisRun:
        """Resume paused (and contract-allowed interrupted) stages; skip completed."""
        run = self._require_run(run_id)
        resumed_any = False
        for stage in self._stages.get_run_stages(run_id):
            status = StageStatus(stage.status)
            if status == StageStatus.COMPLETED:
                continue
            if status == StageStatus.FAILED:
                # Failed stages require explicit retry_failed_stage.
                continue
            if status == StageStatus.PENDING:
                continue
            if status in (StageStatus.PAUSED, StageStatus.INTERRUPTED):
                self._stages.transition_stage(
                    run_id, stage.stage_key, StageStatus.RUNNING
                )
                resumed_any = True
        if run.status == RunStatus.PAUSED or (
            resumed_any and run.status != RunStatus.FAILED
        ):
            run.status = RunStatus.RUNNING
            run.error_code = None
            run.error_message = None
        self._session.commit()
        self._session.refresh(run)
        return run

    def mark_interrupted(self, run_id: int) -> AnalysisRun:
        """Mark only running stages as interrupted. Do not permanently fail the run."""
        run = self._require_run(run_id)
        for stage in self._stages.get_run_stages(run_id):
            if StageStatus(stage.status) == StageStatus.RUNNING:
                self._stages.transition_stage(
                    run_id,
                    stage.stage_key,
                    StageStatus.INTERRUPTED,
                    error_code="PROCESS_INTERRUPTED",
                    error_message="run interrupted by environment stop",
                )
            # completed / pending / paused / failed unchanged
        if run.status not in (
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        ):
            run.status = RunStatus.INTERRUPTED
            if run.error_code != "PROCESS_INTERRUPTED":
                run.error_code = "PROCESS_INTERRUPTED"
                run.error_message = "run interrupted; stages may be resumed"
            run.completed_at = None
        self._session.commit()
        self._session.refresh(run)
        return run

    def retry_failed_stage(self, run_id: int, stage_key: str) -> Any:
        """FAILED → RUNNING only; increments attempt_count. Never retries COMPLETED."""
        stage = self._stages.get_stage(run_id, stage_key)
        if stage is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_STAGE_TRANSITION,
                f"stage {stage_key!r} not found for run_id={run_id}",
            )
        if StageStatus(stage.status) == StageStatus.COMPLETED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.COMPLETED_STAGE_CANNOT_RETRY,
                f"completed stage {stage_key!r} cannot be retried",
            )
        if StageStatus(stage.status) != StageStatus.FAILED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_STAGE_TRANSITION,
                f"retry requires failed stage; got {stage.status}",
            )
        updated = self._stages.transition_stage(
            run_id,
            stage_key,
            StageStatus.RUNNING,
            bump_attempt_count=True,
            error_code=None,
            error_message=None,
        )
        run = self._require_run(run_id)
        if run.status in (
            RunStatus.FAILED,
            RunStatus.INTERRUPTED,
            RunStatus.PAUSED,
            RunStatus.QUEUED,
        ):
            run.status = RunStatus.RUNNING
            run.error_code = None
            run.error_message = None
            run.completed_at = None
        self._session.commit()
        self._session.refresh(updated)
        return updated

    def _require_run(self, run_id: int) -> AnalysisRun:
        run = self._session.get(AnalysisRun, run_id)
        if run is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                f"run_id={run_id} not found",
            )
        return run


class SimulatedStageRunner:
    """Test-only stage runner. No model calls, no real assets/artifacts."""

    DEFAULT_STAGES: tuple[str, ...] = (
        "prepare",
        "analyze",
        "finalize",
    )

    def __init__(self, service: RunStageService) -> None:
        self._service = service

    def bootstrap(self, run_id: int, stage_keys: Sequence[str] | None = None) -> list[Any]:
        keys = list(stage_keys or self.DEFAULT_STAGES)
        return list(self._service.initialize_run_stages(run_id, keys))

    def start(self, run_id: int, stage_key: str, **fields: Any) -> Any:
        return self._service.transition_stage(
            run_id, stage_key, StageStatus.RUNNING, **fields
        )

    def checkpoint(self, run_id: int, stage_key: str, payload: dict[str, Any]) -> Any:
        """Persist checkpoint_json with schema/version; no model I/O."""
        return self._service.write_checkpoint(run_id, stage_key, payload)

    def pause(self, run_id: int) -> AnalysisRun:
        return self._service.pause_run(run_id)

    def resume(self, run_id: int) -> AnalysisRun:
        return self._service.resume_run(run_id)

    def complete(
        self,
        run_id: int,
        stage_key: str,
        *,
        token_input: int = 0,
        token_output: int = 0,
        cost: float = 0.0,
        checkpoint: dict[str, Any] | None = None,
    ) -> Any:
        fields: dict[str, Any] = {
            "token_input": token_input,
            "token_output": token_output,
            "cost": cost,
        }
        if checkpoint is not None:
            fields["checkpoint_json"] = checkpoint
        return self._service.transition_stage(
            run_id, stage_key, StageStatus.COMPLETED, **fields
        )

    def fail(self, run_id: int, stage_key: str, *, error_code: str, error_message: str) -> Any:
        return self._service.transition_stage(
            run_id,
            stage_key,
            StageStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
        )

    def interrupt(self, run_id: int) -> AnalysisRun:
        return self._service.mark_interrupted(run_id)

    def retry(self, run_id: int, stage_key: str) -> Any:
        return self._service.retry_failed_stage(run_id, stage_key)
