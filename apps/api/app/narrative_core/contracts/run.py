"""AnalysisRun scope / stage Protocols (Agent B implements)."""

from __future__ import annotations

from typing import Any, Protocol, Sequence

from app.narrative_core.enums import AnalysisScopeType, AnalysisType, StageStatus


class AnalysisRunStageRepository(Protocol):
    def get_run_stages(self, run_id: int) -> Sequence[Any]:
        ...

    def initialize_run_stages(self, run_id: int, stage_keys: Sequence[str]) -> Sequence[Any]:
        ...

    def transition_stage(
        self,
        run_id: int,
        stage_key: str,
        target_status: StageStatus,
        **fields: Any,
    ) -> Any:
        ...


class AnalysisRunService(Protocol):
    def create_scoped_run(
        self,
        *,
        scope_type: AnalysisScopeType,
        analysis_type: AnalysisType | str,
        book_id: int | None = None,
        start_chapter_id: int | None = None,
        end_chapter_id: int | None = None,
        book_snapshot_id: int | None = None,
        **fields: Any,
    ) -> Any:
        ...

    def validate_run_scope(self, run: Any) -> None:
        ...

    def bind_run_snapshot(self, run_id: int, book_snapshot_id: int) -> Any:
        ...

    def get_run_stages(self, run_id: int) -> Sequence[Any]:
        ...

    def initialize_run_stages(self, run_id: int, stage_keys: Sequence[str]) -> Sequence[Any]:
        ...

    def transition_stage(
        self,
        run_id: int,
        stage_key: str,
        target_status: StageStatus,
        **fields: Any,
    ) -> Any:
        ...

    def pause_run(self, run_id: int) -> Any:
        ...

    def resume_run(self, run_id: int) -> Any:
        ...

    def mark_interrupted(self, run_id: int) -> Any:
        ...

    def retry_failed_stage(self, run_id: int, stage_key: str) -> Any:
        """Retry FAILED→RUNNING only; increments attempt_count. Never retries COMPLETED."""
