"""Unified Mock Run state transitions (Phase 2A Agent M).

All Lab run status changes go through this service.
Frontend-supplied status is never trusted as source of truth.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun
from app.narrative_core.enums import RunStatus
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.errors import MockRunErrorCode, mock_run_error
from app.narrative_core.run_shell_contract.run_state import (
    RunStateTransitionRequest,
    RunStateTransitionResult,
    is_allowed_run_transition,
    is_terminal_run_status,
    validate_transition_or_raise,
)


class MockRunStateError(Exception):
    def __init__(self, code: MockRunErrorCode, *, run_id: int | None = None) -> None:
        self.error = mock_run_error(code, run_id=run_id)
        super().__init__(self.error.message)


def map_db_status_to_view(status: str | RunStatus | WholeBookRunViewStatus) -> WholeBookRunViewStatus:
    value = status.value if isinstance(status, (RunStatus, WholeBookRunViewStatus)) else str(status)
    if value == RunStatus.QUEUED.value:
        return WholeBookRunViewStatus.PENDING
    return WholeBookRunViewStatus(value)


def map_view_status_to_db(status: WholeBookRunViewStatus | str) -> str:
    view = WholeBookRunViewStatus(status)
    if view == WholeBookRunViewStatus.PENDING:
        # Persist as pending (product view); create path may start as queued then normalize.
        return RunStatus.PENDING.value
    return view.value


class MockRunStateService:
    """Optimistic run transitions with expected_state or expected_version."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_view_status(self, run: AnalysisRun) -> WholeBookRunViewStatus:
        return map_db_status_to_view(str(run.status))

    def get_state_version(self, metadata: dict[str, Any]) -> int:
        raw = metadata.get("state_version", 0)
        try:
            return int(raw)
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
            raise MockRunStateError(MockRunErrorCode.MOCK_RUN_STATE_CONFLICT, run_id=int(run.id))

        current = self.get_view_status(run)
        meta = dict(metadata or {})
        version = self.get_state_version(meta)

        request = RunStateTransitionRequest(
            run_id=int(run.id),
            from_state=current,
            to_state=WholeBookRunViewStatus(to_state),
            expected_state=expected_state,
            expected_version=expected_version,
            actor=actor,
            operation_idempotency_key=operation_idempotency_key,
        )

        if expected_state is not None and current != expected_state:
            # Idempotent replay: already at target with matching expected current? handled below.
            if current == request.to_state and expected_state == request.to_state:
                return RunStateTransitionResult(
                    run_id=int(run.id),
                    previous_state=current,
                    new_state=current,
                    applied=False,
                    idempotent_replay=True,
                    version=version,
                )
            raise MockRunStateError(MockRunErrorCode.MOCK_RUN_STATE_CONFLICT, run_id=int(run.id))

        if expected_version is not None and int(expected_version) != int(version):
            if current == request.to_state:
                return RunStateTransitionResult(
                    run_id=int(run.id),
                    previous_state=current,
                    new_state=current,
                    applied=False,
                    idempotent_replay=True,
                    version=version,
                )
            raise MockRunStateError(MockRunErrorCode.MOCK_RUN_STATE_CONFLICT, run_id=int(run.id))

        if current == request.to_state:
            return RunStateTransitionResult(
                run_id=int(run.id),
                previous_state=current,
                new_state=current,
                applied=False,
                idempotent_replay=True,
                version=version,
            )

        if is_terminal_run_status(current):
            raise MockRunStateError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED, run_id=int(run.id)
            )

        if not is_allowed_run_transition(current, request.to_state):
            raise MockRunStateError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED, run_id=int(run.id)
            )

        validate_transition_or_raise(current, request.to_state)
        run.status = map_view_status_to_db(request.to_state)
        new_version = version + 1
        meta["state_version"] = new_version
        self._session.flush()
        return RunStateTransitionResult(
            run_id=int(run.id),
            previous_state=current,
            new_state=request.to_state,
            applied=True,
            idempotent_replay=False,
            version=new_version,
        )


def dump_metadata_json(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)


__all__ = [
    "MockRunStateError",
    "MockRunStateService",
    "dump_metadata_json",
    "map_db_status_to_view",
    "map_view_status_to_db",
]
