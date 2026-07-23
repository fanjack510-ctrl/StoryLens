"""Mock Lab whole-book run HTTP API (Phase 2A Agent M).

Routes under /api/v1/labs/whole-book-runs.
Not registered in main.py here — Integration owns app wiring (report Integration Issue).
Production POST /api/v1/books/{book_id}/whole-book-runs remains disabled.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.api_routes import (
    LAB_API_PREFIX,
    OPENAPI_LAB_TAGS,
    PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH,
)
from app.narrative_core.run_shell_contract.create_run import (
    CreateMockWholeBookRunRequest,
    MockProfile,
)
from app.narrative_core.run_shell_contract.errors import MockRunErrorCode
from app.narrative_core.run_shell_contract.mock_lab import (
    MOCK_LAB_REQUEST_MARKER_HEADER,
    WHOLE_BOOK_MOCK_LAB_ENABLED,
)
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.services.mock_lab_authorization_service import (
    MockLabAuthorizationService,
    is_loopback_host,
    request_marker_present,
)
from app.narrative_core.services.mock_whole_book_run_executor import (
    DefaultMockWholeBookRunExecutor,
    MockExecutorError,
)
from app.narrative_core.services.mock_whole_book_run_service import (
    MockWholeBookRunError,
    MockWholeBookRunService,
)

router = APIRouter(
    prefix=LAB_API_PREFIX,
    tags=list(OPENAPI_LAB_TAGS),
)

# Integration Issue: router exists but is not included in apps/api/app/main.py
# (main.py is Integration ownership). Tests mount this router directly.
INTEGRATION_ISSUE_MAIN_PY_ROUTER_REGISTRATION = (
    "Lab router whole_book_mock_lab_runs is implemented but not registered in "
    "apps/api/app/main.py (Integration ownership CHG-20260723-035)."
)


class CreateMockLabRunBody(BaseModel):
    book_id: int
    book_snapshot_id: int
    analysis_mode: WholeBookAnalysisMode
    requested_modules: list[WholeBookModuleKey] = Field(min_length=1)
    configuration_fingerprint: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    mock_profile: MockProfile = MockProfile.DETERMINISTIC_MINIMAL
    requested_by: str = Field(default="lab", min_length=1)
    preflight_fingerprint: str = Field(min_length=1)
    declare_mock_lab: bool = True

    model_config = {
        "json_schema_extra": {
            "description": "Mock Lab create — non-production; never includes novel body",
        }
    }


class MockRunActionBody(BaseModel):
    expected_state: WholeBookRunViewStatus | None = None
    expected_version: int | None = None
    operation_idempotency_key: str = Field(default="lab-action", min_length=1)
    confirm_cancel: bool = False


def _error_response(exc: MockWholeBookRunError | MockExecutorError) -> HTTPException:
    err = exc.error
    return HTTPException(
        status_code=_status_for(err.code),
        detail={
            "error_code": err.code.value,
            "message": err.message,
            "run_id": err.run_id,
            "stage_key": err.stage_key,
            "detail_code": err.detail_code,
        },
    )


def _status_for(code: MockRunErrorCode) -> int:
    if code in {
        MockRunErrorCode.MOCK_LAB_DISABLED,
        MockRunErrorCode.MOCK_LAB_ENVIRONMENT_NOT_ALLOWED,
        MockRunErrorCode.MOCK_LAB_LOOPBACK_REQUIRED,
        MockRunErrorCode.MOCK_LAB_REQUEST_MARKER_REQUIRED,
        MockRunErrorCode.MOCK_LAB_ENGINE_REQUIRED,
        MockRunErrorCode.MOCK_LAB_ENGINE_NOT_PRODUCTION_SAFE,
        MockRunErrorCode.MOCK_ENGINE_REQUIRED,
        MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET,
    }:
        return 403
    if code == MockRunErrorCode.MOCK_RUN_NOT_FOUND:
        return 404
    if code in {
        MockRunErrorCode.MOCK_RUN_ALREADY_ACTIVE,
        MockRunErrorCode.MOCK_RUN_IDEMPOTENCY_CONFLICT,
        MockRunErrorCode.MOCK_RUN_STATE_CONFLICT,
    }:
        return 409
    if code in {
        MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED,
        MockRunErrorCode.MOCK_RUN_SNAPSHOT_INVALID,
        MockRunErrorCode.MOCK_RUN_CHECKPOINT_INVALID,
        MockRunErrorCode.MOCK_RUN_ENGINE_VERSION_MISMATCH,
        MockRunErrorCode.MOCK_RUN_BUDGET_EXCEEDED,
        MockRunErrorCode.MOCK_RUN_CANCELLED,
        MockRunErrorCode.MOCK_RUN_NOT_RECOVERABLE,
    }:
        return 400
    return 400


def _client_host(request: Request) -> str:
    if request.client is not None and request.client.host:
        return str(request.client.host)
    return ""


def _require_write_lab_gate(request: Request) -> None:
    host = _client_host(request)
    if not is_loopback_host(host):
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": MockRunErrorCode.MOCK_LAB_LOOPBACK_REQUIRED.value,
                "message": "Mock Lab write requests must originate from loopback.",
            },
        )
    if not request_marker_present(request.headers):
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": MockRunErrorCode.MOCK_LAB_REQUEST_MARKER_REQUIRED.value,
                "message": "Mock Lab request marker is required.",
            },
        )


def get_run_service(session: Session = Depends(get_db)) -> MockWholeBookRunService:
    return MockWholeBookRunService(session)


def get_executor(session: Session = Depends(get_db)) -> DefaultMockWholeBookRunExecutor:
    return DefaultMockWholeBookRunExecutor(session, lab_hooks_allowed=True)


@router.post(
    "",
    summary="Create Mock Whole-Book Lab Run (non-production)",
    response_description="Mock run view — no novel body",
)
def create_mock_whole_book_run(
    body: CreateMockLabRunBody,
    request: Request,
    service: MockWholeBookRunService = Depends(get_run_service),
) -> dict[str, Any]:
    _require_write_lab_gate(request)
    req = CreateMockWholeBookRunRequest(
        book_id=int(body.book_id),
        book_snapshot_id=int(body.book_snapshot_id),
        analysis_mode=body.analysis_mode,
        requested_modules=tuple(body.requested_modules),
        configuration_fingerprint=body.configuration_fingerprint,
        idempotency_key=body.idempotency_key,
        mock_profile=body.mock_profile,
        requested_by=body.requested_by,
        preflight_fingerprint=body.preflight_fingerprint,
    )
    try:
        result = service.create_run(
            req,
            loopback=is_loopback_host(_client_host(request)),
            request_marker_present=request_marker_present(request.headers),
            declare_mock_lab=bool(body.declare_mock_lab),
        )
        return {
            "run_id": result.run_id,
            "book_id": result.book_id,
            "book_snapshot_id": result.book_snapshot_id,
            "status": result.status.value,
            "analysis_mode": result.analysis_mode.value,
            "requested_modules": [m.value for m in result.requested_modules],
            "resolved_modules": [m.value for m in result.resolved_modules],
            "stage_plan": list(result.stage_plan),
            "mock": True,
            "non_production": True,
            "created": result.created,
            "duplicate_of_run_id": result.duplicate_of_run_id,
            "created_at": result.created_at,
        }
    except MockWholeBookRunError as exc:
        raise _error_response(exc) from exc


@router.get("/{run_id}")
def get_mock_whole_book_run(
    run_id: int,
    request: Request,
    service: MockWholeBookRunService = Depends(get_run_service),
) -> dict[str, Any]:
    # Reads still require Lab enabled + marker for isolation.
    _require_write_lab_gate(request)
    try:
        service.authorize(
            loopback=is_loopback_host(_client_host(request)),
            request_marker_present=True,
        )
        return service.get_run(int(run_id))
    except MockWholeBookRunError as exc:
        raise _error_response(exc) from exc


@router.get("/{run_id}/stages")
def get_mock_whole_book_run_stages(
    run_id: int,
    request: Request,
    service: MockWholeBookRunService = Depends(get_run_service),
) -> dict[str, Any]:
    _require_write_lab_gate(request)
    try:
        service.authorize(
            loopback=is_loopback_host(_client_host(request)),
            request_marker_present=True,
        )
        return {"run_id": int(run_id), "stages": service.get_run_stages(int(run_id))}
    except MockWholeBookRunError as exc:
        raise _error_response(exc) from exc


@router.post("/{run_id}/pause")
def pause_mock_whole_book_run(
    run_id: int,
    request: Request,
    body: MockRunActionBody | None = None,
    service: MockWholeBookRunService = Depends(get_run_service),
) -> dict[str, Any]:
    _require_write_lab_gate(request)
    payload = body or MockRunActionBody()
    try:
        service.authorize(
            loopback=True,
            request_marker_present=True,
        )
        return service.pause_run(
            int(run_id),
            expected_state=payload.expected_state,
            expected_version=payload.expected_version,
            operation_idempotency_key=payload.operation_idempotency_key,
        )
    except MockWholeBookRunError as exc:
        raise _error_response(exc) from exc


@router.post("/{run_id}/resume")
def resume_mock_whole_book_run(
    run_id: int,
    request: Request,
    body: MockRunActionBody | None = None,
    service: MockWholeBookRunService = Depends(get_run_service),
    executor: DefaultMockWholeBookRunExecutor = Depends(get_executor),
) -> dict[str, Any]:
    _require_write_lab_gate(request)
    payload = body or MockRunActionBody()
    try:
        service.authorize(loopback=True, request_marker_present=True)
        result = service.resume_run(
            int(run_id),
            expected_state=payload.expected_state,
            expected_version=payload.expected_version,
            operation_idempotency_key=payload.operation_idempotency_key,
        )
        executor.resume(int(run_id))
        return result
    except (MockWholeBookRunError, MockExecutorError) as exc:
        raise _error_response(exc) from exc


@router.post("/{run_id}/cancel")
def cancel_mock_whole_book_run(
    run_id: int,
    request: Request,
    body: MockRunActionBody | None = None,
    service: MockWholeBookRunService = Depends(get_run_service),
) -> dict[str, Any]:
    _require_write_lab_gate(request)
    payload = body or MockRunActionBody(confirm_cancel=True)
    try:
        service.authorize(loopback=True, request_marker_present=True)
        return service.cancel_run(
            int(run_id),
            expected_state=payload.expected_state,
            expected_version=payload.expected_version,
            confirm_cancel=True if body is None else bool(payload.confirm_cancel),
            operation_idempotency_key=payload.operation_idempotency_key,
        )
    except MockWholeBookRunError as exc:
        raise _error_response(exc) from exc


@router.post("/{run_id}/stages/{stage_key}/retry")
def retry_mock_whole_book_stage(
    run_id: int,
    stage_key: str,
    request: Request,
    body: MockRunActionBody | None = None,
    service: MockWholeBookRunService = Depends(get_run_service),
    executor: DefaultMockWholeBookRunExecutor = Depends(get_executor),
) -> dict[str, Any]:
    _require_write_lab_gate(request)
    payload = body or MockRunActionBody()
    try:
        service.authorize(loopback=True, request_marker_present=True)
        result = service.retry_stage(
            int(run_id),
            stage_key,
            expected_state=payload.expected_state,
            expected_version=payload.expected_version,
            operation_idempotency_key=payload.operation_idempotency_key,
        )
        # Execute the retried stage once via executor.
        executor.execute_next_stage(int(run_id))
        return result
    except (MockWholeBookRunError, MockExecutorError) as exc:
        raise _error_response(exc) from exc


def lab_contract_assertions() -> dict[str, Any]:
    """Static assertions for tests — production gates untouched."""
    return {
        "WHOLE_BOOK_RUNS_ENDPOINT_DISABLED": WHOLE_BOOK_RUNS_ENDPOINT_DISABLED,
        "WHOLE_BOOK_MOCK_LAB_ENABLED_DEFAULT": WHOLE_BOOK_MOCK_LAB_ENABLED,
        "PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH": PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH,
        "MOCK_LAB_REQUEST_MARKER_HEADER": MOCK_LAB_REQUEST_MARKER_HEADER,
        "integration_issue_main_py": INTEGRATION_ISSUE_MAIN_PY_ROUTER_REGISTRATION,
        "lab_api_prefix": LAB_API_PREFIX,
    }


__all__ = [
    "INTEGRATION_ISSUE_MAIN_PY_ROUTER_REGISTRATION",
    "lab_contract_assertions",
    "router",
]
