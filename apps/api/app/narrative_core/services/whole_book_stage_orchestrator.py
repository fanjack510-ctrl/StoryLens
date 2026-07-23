"""Test-level WholeBook stage orchestrator (Phase 1C Agent G).

Validates Request → plan → initialize AnalysisRunStages → execute / pause /
resume / interrupt / retry / cancel against Phase 1A RunStageService.
Not a production WholeBook run entry point.
"""

from __future__ import annotations

from typing import Any, Sequence

from app.narrative_core.contracts.stage import WholeBookStageContext, WholeBookStageResult
from app.narrative_core.contracts.whole_book_dto import WholeBookAnalysisRequest
from app.narrative_core.enums import StageStatus, WholeBookStageKey
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.mock_whole_book_engine import MockWholeBookAnalysisEngine
from app.narrative_core.services.run_stage_service import RunStageService
from app.narrative_core.services.whole_book_stage_plan import stage_definitions_to_run_stage_keys


class WholeBookStageOrchestrator:
    """Simulated orchestrator for Mock engine + RunStageService."""

    def __init__(
        self,
        *,
        engine: MockWholeBookAnalysisEngine,
        run_stage_service: RunStageService,
        snapshot_reader: Any | None = None,
        asset_writer: Any | None = None,
        relation_writer: Any | None = None,
        artifact_writer: Any | None = None,
        conflict_sink: Any | None = None,
        budget_guard: Any | None = None,
        cancellation_token: Any | None = None,
    ) -> None:
        self.engine = engine
        self.stages = run_stage_service
        self.snapshot_reader = snapshot_reader
        self.asset_writer = asset_writer
        self.relation_writer = relation_writer
        self.artifact_writer = artifact_writer
        self.conflict_sink = conflict_sink
        self.budget_guard = budget_guard
        self.cancellation_token = cancellation_token
        self.last_plan_keys: list[str] = []
        self.results: list[WholeBookStageResult] = []
        self.cancelled = False

    def validate_and_plan(self, request: WholeBookAnalysisRequest) -> list[str]:
        self.engine.validate_request(request)
        plan = self.engine.build_stage_plan(request)
        keys = stage_definitions_to_run_stage_keys(plan.stages)
        self.last_plan_keys = keys
        return keys

    def initialize_stages(self, request: WholeBookAnalysisRequest) -> Sequence[Any]:
        keys = self.validate_and_plan(request)
        assert request.run_id is not None
        return self.stages.initialize_run_stages(int(request.run_id), keys)

    def _stage_row(self, run_id: int, stage_key: str) -> Any:
        row = self.stages._stages.get_stage(run_id, stage_key)  # noqa: SLF001
        if row is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                f"stage {stage_key} not initialized for run {run_id}",
            )
        return row

    def _build_context(
        self,
        request: WholeBookAnalysisRequest,
        stage_key: str,
        *,
        checkpoint: dict[str, Any] | None = None,
    ) -> WholeBookStageContext:
        row = self._stage_row(int(request.run_id), stage_key)
        extra = dict(request.extra)
        if self.relation_writer is not None:
            extra["relation_writer"] = self.relation_writer
        if self.asset_writer is not None and getattr(self.asset_writer, "created_asset_ids", None):
            ids = list(self.asset_writer.created_asset_ids)
            if len(ids) >= 2:
                extra.setdefault("mock_source_asset_id", ids[0])
                extra.setdefault("mock_target_asset_id", ids[1])
        return WholeBookStageContext(
            run_id=int(request.run_id),
            book_id=int(request.book_id),
            book_snapshot_id=int(request.book_snapshot_id),
            analysis_mode=request.analysis_mode,
            stage_key=WholeBookStageKey(stage_key),
            capability_context=request.capability_context,
            run_stage_id=int(row.id),
            checkpoint=dict(checkpoint or {}),
            configuration_fingerprint=request.configuration_fingerprint,
            snapshot_reader=self.snapshot_reader,
            asset_writer=self.asset_writer,
            artifact_writer=self.artifact_writer,
            conflict_sink=self.conflict_sink,
            cancellation_token=self.cancellation_token,
            budget_guard=self.budget_guard,
            extra=extra,
        )

    def execute_current_stage(
        self,
        request: WholeBookAnalysisRequest,
        stage_key: str,
    ) -> WholeBookStageResult:
        if self.cancelled:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_STAGE_CANCELLED,
                "orchestrator cancelled; refusing further execution",
            )
        if self.cancellation_token is not None:
            self.cancellation_token.raise_if_cancelled()

        run_id = int(request.run_id)
        row = self._stage_row(run_id, stage_key)
        status = StageStatus(row.status)
        if status == StageStatus.COMPLETED:
            return WholeBookStageResult(
                stage_key=WholeBookStageKey(stage_key),
                status=StageStatus.COMPLETED,
                message="completed stage not re-run",
                metrics={"skipped_rerun": True, "mock": True},
            )
        if status == StageStatus.CANCELLED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_STAGE_CANCELLED,
                f"stage already cancelled: {stage_key}",
            )

        if status == StageStatus.PENDING:
            self.stages.transition_stage(run_id, stage_key, StageStatus.RUNNING)

        context = self._build_context(request, stage_key)
        try:
            result = self.engine.execute_stage(context)
        except NarrativeCoreError as exc:
            if exc.code == NarrativeCoreErrorCode.WHOLE_BOOK_BUDGET_DENIED:
                self.stages.transition_stage(
                    run_id,
                    stage_key,
                    StageStatus.FAILED,
                    error_code=exc.code.value,
                    error_message=str(exc),
                )
                raise
            if exc.code == NarrativeCoreErrorCode.WHOLE_BOOK_STAGE_CANCELLED:
                self.stages.transition_stage(
                    run_id,
                    stage_key,
                    StageStatus.CANCELLED,
                    error_code=exc.code.value,
                    error_message=str(exc),
                )
                raise
            self.stages.transition_stage(
                run_id,
                stage_key,
                StageStatus.FAILED,
                error_code=getattr(exc.code, "value", str(exc.code)),
                error_message=str(exc),
            )
            raise

        if result.status == StageStatus.PAUSED:
            self.stages.transition_stage(run_id, stage_key, StageStatus.PAUSED)
            self.stages.write_checkpoint(run_id, stage_key, dict(result.checkpoint))
            self.results.append(result)
            return result

        if result.status != StageStatus.COMPLETED:
            self.stages.transition_stage(
                run_id,
                stage_key,
                result.status,
                error_code=result.message or None,
            )
            self.results.append(result)
            return result

        # Write checkpoint then complete with token/cost.
        self.stages.write_checkpoint(run_id, stage_key, dict(result.checkpoint))
        self.stages.transition_stage(
            run_id,
            stage_key,
            StageStatus.COMPLETED,
            token_input=int(result.token_usage),
            token_output=0,
            cost=float(result.cost),
        )
        if result.stage_key.value != stage_key:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                f"stage result key {result.stage_key} != {stage_key}",
            )
        self.results.append(result)
        return result

    def run_until(
        self,
        request: WholeBookAnalysisRequest,
        *,
        stop_before: str | None = None,
        max_stages: int | None = None,
    ) -> list[WholeBookStageResult]:
        keys = self.last_plan_keys or self.validate_and_plan(request)
        if not self.stages.get_run_stages(int(request.run_id)):
            self.stages.initialize_run_stages(int(request.run_id), keys)
        out: list[WholeBookStageResult] = []
        for index, key in enumerate(keys):
            if stop_before is not None and key == stop_before:
                break
            if max_stages is not None and index >= max_stages:
                break
            out.append(self.execute_current_stage(request, key))
        return out

    def pause(self, request: WholeBookAnalysisRequest, stage_key: str) -> Any:
        run_id = int(request.run_id)
        self.engine.pause_stage(run_id, stage_key)
        return self.stages.pause_run(run_id)

    def resume(self, request: WholeBookAnalysisRequest, stage_key: str) -> WholeBookStageResult:
        run_id = int(request.run_id)
        self.stages.resume_run(run_id)
        row = self._stage_row(run_id, stage_key)
        checkpoint: dict[str, Any] = {}
        raw = getattr(row, "checkpoint_json", "{}") or "{}"
        if isinstance(raw, str) and raw.strip():
            import json

            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    checkpoint = parsed
            except json.JSONDecodeError:
                checkpoint = {}
        context = self._build_context(request, stage_key, checkpoint=checkpoint)
        result = self.engine.resume_stage(context)
        if result.status == StageStatus.COMPLETED:
            self.stages.write_checkpoint(run_id, stage_key, dict(result.checkpoint))
            self.stages.transition_stage(
                run_id,
                stage_key,
                StageStatus.COMPLETED,
                token_input=int(result.token_usage),
                token_output=0,
                cost=float(result.cost),
            )
        self.results.append(result)
        return result

    def interrupt(self, request: WholeBookAnalysisRequest) -> Any:
        return self.stages.mark_interrupted(int(request.run_id))

    def retry(self, request: WholeBookAnalysisRequest, stage_key: str) -> WholeBookStageResult:
        self.stages.retry_failed_stage(int(request.run_id), stage_key)
        return self.execute_current_stage(request, stage_key)

    def cancel(self, request: WholeBookAnalysisRequest, stage_key: str | None = None) -> None:
        self.cancelled = True
        if self.cancellation_token is not None:
            self.cancellation_token.cancel()
        run_id = int(request.run_id)
        if stage_key is not None:
            self.engine.cancel_stage(run_id, stage_key)
            row = self._stage_row(run_id, stage_key)
            if StageStatus(row.status) in {
                StageStatus.PENDING,
                StageStatus.RUNNING,
                StageStatus.PAUSED,
                StageStatus.INTERRUPTED,
            }:
                self.stages.transition_stage(
                    run_id,
                    stage_key,
                    StageStatus.CANCELLED,
                    error_code=NarrativeCoreErrorCode.WHOLE_BOOK_STAGE_CANCELLED.value,
                    error_message="cancelled by orchestrator",
                )


__all__ = ["WholeBookStageOrchestrator"]
