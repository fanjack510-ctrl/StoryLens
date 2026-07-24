"""Private Lab recovery (Phase 2B-R1 Agent V).

Startup only marks leftover running → interrupted.
Never auto-resume, auto Provider, auto budget, auto Candidate, or auto Task.
Does not change Mock Lab or non-Private recovery semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun
from app.narrative_core.enums import RunStatus, StageStatus
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.private_engine_lab import PRIVATE_LAB_TASK_TYPE
from app.narrative_core.services.private_lab_run_metadata import is_private_lab_run_metadata
from app.narrative_core.services.private_lab_run_state_service import map_db_status_to_view
from app.narrative_core.services.run_stage_service import RunStageService


@dataclass(frozen=True, slots=True)
class PrivateLabRecoveryScanResult:
    scanned: int
    interrupted_run_ids: tuple[int, ...]
    skipped_non_private: int
    auto_resumed: int = 0  # always 0 by contract


class PrivateLabRecoveryService:
    def __init__(
        self,
        session: Session,
        *,
        stage_service: RunStageService | None = None,
    ) -> None:
        self._session = session
        self._stages = stage_service or RunStageService(session)

    def scan_recoverable_runs(self) -> list[AnalysisRun]:
        rows = self._session.scalars(
            select(AnalysisRun).where(AnalysisRun.task_type == PRIVATE_LAB_TASK_TYPE)
        ).all()
        out: list[AnalysisRun] = []
        for run in rows:
            if not is_private_lab_run_metadata(run.validated_output):
                continue
            view = map_db_status_to_view(str(run.status))
            if view == WholeBookRunViewStatus.RUNNING:
                out.append(run)
            else:
                # Also interrupt stages still running under pending mismatch
                for stage in self._stages.get_run_stages(int(run.id)):
                    if StageStatus(stage.status) == StageStatus.RUNNING:
                        out.append(run)
                        break
        return out

    def mark_process_interrupted(self, run_id: int) -> AnalysisRun:
        """Interrupt only — never auto-resume or start Provider."""

        run = self._session.get(AnalysisRun, int(run_id))
        if run is None or not is_private_lab_run_metadata(run.validated_output):
            raise ValueError("not a private lab run")
        self._stages.mark_interrupted(int(run_id))
        self._session.refresh(run)
        return run

    def startup_reconcile(self) -> PrivateLabRecoveryScanResult:
        """Startup hook: mark leftover running as interrupted. auto_resumed always 0."""

        candidates = self.scan_recoverable_runs()
        interrupted: list[int] = []
        for run in candidates:
            self.mark_process_interrupted(int(run.id))
            interrupted.append(int(run.id))
        # Count non-private running left untouched
        all_running = self._session.scalars(
            select(AnalysisRun).where(AnalysisRun.status == RunStatus.RUNNING.value)
        ).all()
        skipped = sum(
            1
            for r in all_running
            if not is_private_lab_run_metadata(r.validated_output)
        )
        self._session.commit()
        return PrivateLabRecoveryScanResult(
            scanned=len(candidates),
            interrupted_run_ids=tuple(interrupted),
            skipped_non_private=skipped,
            auto_resumed=0,
        )


__all__ = [
    "PrivateLabRecoveryScanResult",
    "PrivateLabRecoveryService",
]
