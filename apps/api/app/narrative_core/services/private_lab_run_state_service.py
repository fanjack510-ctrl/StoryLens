"""Private Lab run state transitions (Phase 2B-R1 Agent V).

Reuses shared run_state transition matrix. Distinct from MockRunStateService.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun
from app.narrative_core.enums import RunStatus
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.private_engine_lab import PrivateEngineLabDenyReason
from app.narrative_core.run_shell_contract.run_state import (
    RunStateTransitionRequest,
    RunStateTransitionResult,
    is_allowed_run_transition,
)


class PrivateLabRunStateError(Exception):
    def __init__(
        self,
        reason: PrivateEngineLabDenyReason,
        *,
        run_id: int | None = None,
        message: str | None = None,
    ) -> None:
        self.reason = reason
        self.run_id = run_id
        self.message = message or reason.value
        super().__init__(self.message)


def map_db_status_to_view(status: str | RunStatus | WholeBookRunViewStatus) -> WholeBookRunViewStatus:
    value = status.value if isinstance(status, (RunStatus, WholeBookRunViewStatus)) else str(status)
    if value == RunStatus.QUEUED.value:
        return WholeBookRunViewStatus.PENDING
    return WholeBookRunViewStatus(value)


def map_view_status_to_db(status: WholeBookRunViewStatus | str) -> str:
    view = WholeBookRunViewStatus(status)
    if view == WholeBookRunViewStatus.PENDING:
        return RunStatus.PENDING.value
    return view.value


class PrivateLabRunStateService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_view_status(self, run: AnalysisRun) -> WholeBookRunViewStatus:
        return map_db_status_to_view(str(run.status))

    def get_state_version(self, metadata: dict[str, Any]) -> int:
        try:
            return int(metadata.get("state_version", 0))
        except (TypeError, ValueError):
            return 0

    def transition(
        self,
        run: AnalysisRun,
        *,
        to_state: WholeBookRunViewStatus,
        expected_state: WholeBookRunViewStatus | None = None,
        expected_version: int | None = None,
        metadata: dict[str, Any] | None = None,
        actor: str = "system",
        operation_idempotency_key: str | None = None,
    ) -> RunStateTransitionResult:
        if expected_state is None and expected_version is None:
            raise PrivateLabRunStateError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_STATE_CONFLICT,
                run_id=int(run.id),
            )

        current = self.get_view_status(run)
        meta = dict(metadata or {})
        version = self.get_state_version(meta)
        target = WholeBookRunViewStatus(to_state)

        if expected_version is not None and expected_version != version:
            raise PrivateLabRunStateError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_STATE_CONFLICT,
                run_id=int(run.id),
            )
        if expected_state is not None and current != expected_state:
            if current == target and expected_state == target:
                return RunStateTransitionResult(
                    run_id=int(run.id),
                    previous_state=current,
                    new_state=current,
                    applied=False,
                    idempotent_replay=True,
                    version=version,
                )
            raise PrivateLabRunStateError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_STATE_CONFLICT,
                run_id=int(run.id),
            )

        if current == target:
            return RunStateTransitionResult(
                run_id=int(run.id),
                previous_state=current,
                new_state=current,
                applied=False,
                idempotent_replay=True,
                version=version,
            )

        if not is_allowed_run_transition(current, target):
            raise PrivateLabRunStateError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                run_id=int(run.id),
            )

        _ = RunStateTransitionRequest(
            run_id=int(run.id),
            from_state=current,
            to_state=target,
            expected_state=expected_state,
            expected_version=expected_version,
            actor=actor,
            operation_idempotency_key=operation_idempotency_key,
        )
        run.status = map_view_status_to_db(target)
        new_version = version + 1
        meta["state_version"] = new_version
        self._session.flush()
        return RunStateTransitionResult(
            run_id=int(run.id),
            previous_state=current,
            new_state=target,
            applied=True,
            idempotent_replay=False,
            version=new_version,
        )


__all__ = [
    "PrivateLabRunStateError",
    "PrivateLabRunStateService",
    "map_db_status_to_view",
    "map_view_status_to_db",
]
