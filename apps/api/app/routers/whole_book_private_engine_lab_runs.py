"""Private Engine Lab whole-book HTTP API (Phase 2B-R1 Agent V).

Routes under /api/v1/labs/private-whole-book-runs.
Conditionally registered in apps/api/app/main.py when environment is
development/test AND WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED=true.

Development-level AnalysisRun-backed Lab. Distinct from Mock Lab.
Production POST /api/v1/books/{book_id}/whole-book-runs remains disabled.
Router final Settings composition left to Integration — this module is self-contained.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.enums import WholeBookAnalysisMode
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.api_routes import PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH
from app.narrative_core.run_shell_contract.mock_lab import WHOLE_BOOK_MOCK_LAB_ENABLED
from app.narrative_core.run_shell_contract.private_engine_lab import (
    OPENAPI_PRIVATE_ENGINE_LAB_TAGS,
    PRIVATE_ENGINE_LAB_API_PREFIX,
    PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER,
    PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER,
    PRIVATE_LAB_FIRST_MODEL_ID,
    PRIVATE_LAB_FIRST_PROVIDER_KEY,
    PRIVATE_LAB_FIRST_QUALITY_PROFILE,
    WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
    PrivateEngineLabDenyReason,
)
from app.narrative_core.services.private_engine_lab_authorization_service import (
    PrivateEngineLabAuthorizationDenied,
    PrivateEngineLabAuthorizationService,
    is_loopback_host,
    private_engine_lab_request_marker_present,
)
from app.narrative_core.services.private_engine_lab_run_service import (
    CreatePrivateLabRunRequest,
    PrivateWholeBookLabRunError,
    PrivateWholeBookLabRunService,
)
from app.narrative_core.services.private_lab_ports import (
    FakePrivateLabConsentValidationPort,
    FakePrivateLabEstimatePort,
    FakePrivateLabPreflightPort,
    FakePrivateLabProviderExecutionPort,
)
from app.narrative_core.services.private_lab_run_executor import PrivateLabRunExecutor
from app.narrative_core.services.in_process_private_lab_task_registry import (
    get_default_private_lab_task_registry,
    reset_default_private_lab_task_registry,
)

router = APIRouter(
    prefix=PRIVATE_ENGINE_LAB_API_PREFIX,
    tags=list(OPENAPI_PRIVATE_ENGINE_LAB_TAGS),
)

# Integration Issue: shared main.py mount + Settings composition deferred to CHG-048.
INTEGRATION_ISSUE_MAIN_PY_ROUTER_REGISTRATION = (
    "Private Lab router is conditionally registered in apps/api/app/main.py; "
    "Agent V must not modify shared main.py. Integration wires Ports to U services."
)


class CreatePrivateEngineLabRunBody(BaseModel):
    book_id: int = Field(ge=1)
    book_snapshot_id: int = Field(ge=1)
    analysis_mode: WholeBookAnalysisMode = WholeBookAnalysisMode.NATIVE
    requested_modules: list[str] = Field(
        default_factory=lambda: list(PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER)
    )
    dry_run: bool = True
    data_transfer_consented: bool = True
    user_confirmed: bool = True
    credential_present: bool = False
    budget_ok: bool = True
    capability_ok: bool = True
    configuration_fingerprint: str = Field(default="private-lab-cfg", min_length=1)
    idempotency_key: str = Field(default="private-lab", min_length=1, max_length=128)
    preflight_fingerprint: str = Field(default="preflight-fp-ok", min_length=1)
    estimate_fingerprint: str = Field(default="estimate-fp-ok", min_length=1)
    consent_fingerprint: str = Field(default="consent-fp-ok", min_length=1)
    data_transfer_manifest_hash: str = Field(default="manifest-hash-ok", min_length=1)
    context_bundle_hash: str = Field(default="context-hash-ok", min_length=1)
    prompt_pack_id: str = "private.lab.pack"
    prompt_pack_version: str = "1.0.0"
    provider_key: str = PRIVATE_LAB_FIRST_PROVIDER_KEY
    model_id: str = PRIVATE_LAB_FIRST_MODEL_ID
    quality_profile: str = PRIVATE_LAB_FIRST_QUALITY_PROFILE
    output_locale: str = "zh-CN"
    source_language: str = "zh"
    auto_start: bool = True

    model_config = {
        "json_schema_extra": {
            "description": (
                "Private Engine Lab create — non-production; never includes novel body "
                "or credentials"
            ),
        }
    }


class PrivateLabPreflightBody(BaseModel):
    book_id: int = Field(ge=1)
    book_snapshot_id: int = Field(ge=1)
    configuration_fingerprint: str = Field(min_length=1)
    requested_modules: list[str] = Field(
        default_factory=lambda: list(PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER)
    )


class PrivateLabEstimateBody(BaseModel):
    book_id: int = Field(ge=1)
    book_snapshot_id: int = Field(ge=1)
    configuration_fingerprint: str = Field(min_length=1)
    preflight_fingerprint: str = Field(min_length=1)
    requested_modules: list[str] = Field(
        default_factory=lambda: list(PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER)
    )
    provider_key: str = PRIVATE_LAB_FIRST_PROVIDER_KEY
    model_id: str = PRIVATE_LAB_FIRST_MODEL_ID
    quality_profile: str = PRIVATE_LAB_FIRST_QUALITY_PROFILE


class PrivateEngineLabActionBody(BaseModel):
    expected_state: WholeBookRunViewStatus | None = None
    expected_version: int | None = None
    operation_idempotency_key: str = Field(default="lab-action", min_length=1)
    confirm_cancel: bool = False
    estimate_fingerprint: str | None = None
    consent_fingerprint: str | None = None
    context_bundle_hash: str | None = None


def _client_host(request: Request) -> str:
    if request.client is not None and request.client.host:
        return str(request.client.host)
    return ""


def _auth_service() -> PrivateEngineLabAuthorizationService:
    return PrivateEngineLabAuthorizationService(lab_enabled=True)


def _require_write_lab_gate(
    request: Request,
    *,
    dry_run: bool = True,
    credential_present: bool = False,
    data_transfer_consented: bool = False,
    budget_ok: bool = True,
    capability_ok: bool = True,
    user_confirmed: bool = False,
) -> None:
    host = _client_host(request)
    try:
        _auth_service().require(
            loopback=is_loopback_host(host),
            request_marker_present=private_engine_lab_request_marker_present(request.headers),
            credential_present=credential_present,
            data_transfer_consented=data_transfer_consented,
            budget_ok=budget_ok,
            capability_ok=capability_ok,
            user_confirmed=user_confirmed,
            dry_run=dry_run,
        )
    except PrivateEngineLabAuthorizationDenied as exc:
        raise HTTPException(
            status_code=403,
            detail={"error_code": exc.reason.value, "message": exc.message},
        ) from exc


def _status_for(reason: PrivateEngineLabDenyReason) -> int:
    if reason in {
        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_RUN_NOT_FOUND,
    }:
        return 404
    if reason in {
        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONCURRENCY_LIMIT,
        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_IDEMPOTENCY_CONFLICT,
        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_STATE_CONFLICT,
    }:
        return 409
    if reason in {
        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONFIRM_REQUIRED,
        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CHECKPOINT_INVALID,
        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_SNAPSHOT_INVALID,
        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_PREFLIGHT_REJECTED,
        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_ESTIMATE_FINGERPRINT_MISMATCH,
        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONSENT_FINGERPRINT_MISMATCH,
    }:
        return 400
    return 403


def _error_response(exc: PrivateWholeBookLabRunError) -> HTTPException:
    return HTTPException(
        status_code=_status_for(exc.reason),
        detail={
            "error_code": exc.reason.value,
            "message": exc.message,
            "run_id": exc.run_id,
            "stage_key": exc.stage_key,
            "detail_code": exc.detail_code,
        },
    )


def get_run_service(session: Session = Depends(get_db)) -> PrivateWholeBookLabRunService:
    return PrivateWholeBookLabRunService(
        session,
        auth=PrivateEngineLabAuthorizationService(lab_enabled=True),
        task_registry=get_default_private_lab_task_registry(),
        preflight_port=FakePrivateLabPreflightPort(),
        estimate_port=FakePrivateLabEstimatePort(),
        consent_port=FakePrivateLabConsentValidationPort(),
    )


def get_executor(session: Session = Depends(get_db)) -> PrivateLabRunExecutor:
    return PrivateLabRunExecutor(
        session,
        task_registry=get_default_private_lab_task_registry(),
        provider_port=FakePrivateLabProviderExecutionPort(),
    )


@router.post("/preflight", summary="Private Lab preflight (no Run)")
def private_lab_preflight(
    body: PrivateLabPreflightBody,
    request: Request,
) -> dict[str, Any]:
    _require_write_lab_gate(request, dry_run=True)
    port = FakePrivateLabPreflightPort()
    result = port.preflight(
        book_id=int(body.book_id),
        book_snapshot_id=int(body.book_snapshot_id),
        configuration_fingerprint=body.configuration_fingerprint,
        requested_modules=tuple(body.requested_modules),
    )
    return {
        "ok": result.ok,
        "fingerprint": result.fingerprint,
        "book_id": result.book_id,
        "book_snapshot_id": result.book_snapshot_id,
        "snapshot_content_hash": result.snapshot_content_hash,
        "reason_code": result.reason_code,
        "private_lab": True,
        "non_production": True,
        "run_created": False,
    }


@router.post("/estimate", summary="Private Lab estimate (no Run)")
def private_lab_estimate(
    body: PrivateLabEstimateBody,
    request: Request,
) -> dict[str, Any]:
    _require_write_lab_gate(request, dry_run=True)
    port = FakePrivateLabEstimatePort()
    result = port.estimate(
        book_id=int(body.book_id),
        book_snapshot_id=int(body.book_snapshot_id),
        configuration_fingerprint=body.configuration_fingerprint,
        provider_key=body.provider_key,
        model_id=body.model_id,
        quality_profile=body.quality_profile,
        requested_modules=tuple(body.requested_modules),
        preflight_fingerprint=body.preflight_fingerprint,
    )
    return {
        "fingerprint": result.fingerprint,
        "configuration_fingerprint": result.configuration_fingerprint,
        "provider_key": result.provider_key,
        "model_id": result.model_id,
        "quality_profile": result.quality_profile,
        "module_keys": list(result.module_keys),
        "usage_summary": dict(result.usage_summary),
        "cost_summary": dict(result.cost_summary),
        "data_transfer_manifest_hash": result.data_transfer_manifest_hash,
        "private_lab": True,
        "non_production": True,
        "run_created": False,
        "tokens_hardcoded": False,
        "cost_hardcoded": False,
    }


@router.post(
    "",
    summary="Create Private Engine Lab Run (AnalysisRun-backed)",
)
def create_private_engine_lab_run(
    body: CreatePrivateEngineLabRunBody,
    request: Request,
    service: PrivateWholeBookLabRunService = Depends(get_run_service),
    executor: PrivateLabRunExecutor = Depends(get_executor),
) -> dict[str, Any]:
    _require_write_lab_gate(
        request,
        dry_run=bool(body.dry_run),
        credential_present=bool(body.credential_present),
        data_transfer_consented=bool(body.data_transfer_consented),
        budget_ok=bool(body.budget_ok),
        capability_ok=bool(body.capability_ok),
        user_confirmed=bool(body.user_confirmed),
    )
    host = _client_host(request)
    try:
        result = service.create_run(
            CreatePrivateLabRunRequest(
                book_id=int(body.book_id),
                book_snapshot_id=int(body.book_snapshot_id),
                analysis_mode=body.analysis_mode,
                requested_modules=tuple(body.requested_modules),
                configuration_fingerprint=body.configuration_fingerprint,
                idempotency_key=body.idempotency_key,
                preflight_fingerprint=body.preflight_fingerprint,
                estimate_fingerprint=body.estimate_fingerprint,
                consent_fingerprint=body.consent_fingerprint,
                data_transfer_manifest_hash=body.data_transfer_manifest_hash,
                context_bundle_hash=body.context_bundle_hash,
                prompt_pack_id=body.prompt_pack_id,
                prompt_pack_version=body.prompt_pack_version,
                provider_key=body.provider_key,
                model_id=body.model_id,
                quality_profile=body.quality_profile,
                output_locale=body.output_locale,
                source_language=body.source_language,
                dry_run=bool(body.dry_run),
                data_transfer_consented=bool(body.data_transfer_consented),
                user_confirmed=bool(body.user_confirmed),
                credential_present=bool(body.credential_present),
                budget_ok=bool(body.budget_ok),
                capability_ok=bool(body.capability_ok),
            ),
            loopback=is_loopback_host(host),
            request_marker_present=private_engine_lab_request_marker_present(request.headers),
            auto_start=bool(body.auto_start),
        )
    except PrivateWholeBookLabRunError as exc:
        raise _error_response(exc) from exc

    exec_detail: dict[str, Any] = {}
    if body.auto_start and result.created:
        try:
            exec_result = executor.start(int(result.run_id))
            exec_detail = {
                "executor_status": exec_result.status,
                "executor_detail": dict(exec_result.detail),
            }
        except PrivateWholeBookLabRunError as exc:
            raise _error_response(exc) from exc

    view = service.get_run(int(result.run_id))
    return {
        **view,
        "lab_run_id": str(result.run_id),
        "created": result.created,
        "duplicate_of_run_id": result.duplicate_of_run_id,
        "formal_run_disabled": WHOLE_BOOK_RUNS_ENDPOINT_DISABLED,
        "shell_only": False,
        "private_engine_lab": True,
        "dry_run": bool(body.dry_run),
        **exec_detail,
    }


@router.get("/_meta/contract")
def private_engine_lab_contract(request: Request) -> dict[str, Any]:
    _require_write_lab_gate(request, dry_run=True)
    return lab_contract_assertions()


@router.get("/{run_id}")
def get_private_engine_lab_run(
    run_id: int,
    request: Request,
    service: PrivateWholeBookLabRunService = Depends(get_run_service),
) -> dict[str, Any]:
    _require_write_lab_gate(request, dry_run=True)
    try:
        view = service.get_run(int(run_id))
    except PrivateWholeBookLabRunError as exc:
        raise _error_response(exc) from exc
    return {**view, "lab_run_id": str(run_id)}


@router.get("/{run_id}/stages")
def get_private_engine_lab_run_stages(
    run_id: int,
    request: Request,
    service: PrivateWholeBookLabRunService = Depends(get_run_service),
) -> dict[str, Any]:
    _require_write_lab_gate(request, dry_run=True)
    try:
        stages = service.get_run_stages(int(run_id))
    except PrivateWholeBookLabRunError as exc:
        raise _error_response(exc) from exc
    return {
        "run_id": int(run_id),
        "stages": stages,
        "private_lab": True,
        "non_production": True,
    }


@router.post("/{run_id}/cancel")
def cancel_private_engine_lab_run(
    run_id: int,
    request: Request,
    body: PrivateEngineLabActionBody | None = None,
    service: PrivateWholeBookLabRunService = Depends(get_run_service),
    executor: PrivateLabRunExecutor = Depends(get_executor),
) -> dict[str, Any]:
    _require_write_lab_gate(request, dry_run=True)
    payload = body or PrivateEngineLabActionBody(confirm_cancel=True)
    if body is not None and not payload.confirm_cancel:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "PRIVATE_ENGINE_LAB_CANCEL_CONFIRM_REQUIRED",
                "message": "confirm_cancel must be true.",
            },
        )
    try:
        executor.cancel(int(run_id))
        result = service.cancel_run(
            int(run_id),
            expected_state=payload.expected_state,
            expected_version=payload.expected_version,
            confirm_cancel=True,
            operation_idempotency_key=payload.operation_idempotency_key,
        )
    except PrivateWholeBookLabRunError as exc:
        raise _error_response(exc) from exc
    return result


@router.post("/{run_id}/resume")
def resume_private_engine_lab_run(
    run_id: int,
    request: Request,
    body: PrivateEngineLabActionBody | None = None,
    service: PrivateWholeBookLabRunService = Depends(get_run_service),
    executor: PrivateLabRunExecutor = Depends(get_executor),
) -> dict[str, Any]:
    _require_write_lab_gate(request, dry_run=True)
    payload = body or PrivateEngineLabActionBody()
    try:
        result = service.resume_run(
            int(run_id),
            expected_state=payload.expected_state,
            expected_version=payload.expected_version,
            estimate_fingerprint=payload.estimate_fingerprint,
            consent_fingerprint=payload.consent_fingerprint,
            context_bundle_hash=payload.context_bundle_hash,
            operation_idempotency_key=payload.operation_idempotency_key,
        )
        exec_result = executor.resume(int(run_id))
    except PrivateWholeBookLabRunError as exc:
        raise _error_response(exc) from exc
    return {**result, "executor_status": exec_result.status}


@router.post("/{run_id}/stages/{stage_key}/retry")
def retry_private_engine_lab_stage(
    run_id: int,
    stage_key: str,
    request: Request,
    body: PrivateEngineLabActionBody | None = None,
    service: PrivateWholeBookLabRunService = Depends(get_run_service),
    executor: PrivateLabRunExecutor = Depends(get_executor),
) -> dict[str, Any]:
    _require_write_lab_gate(request, dry_run=True)
    payload = body or PrivateEngineLabActionBody()
    try:
        result = service.retry_stage(
            int(run_id),
            stage_key,
            expected_state=payload.expected_state,
            expected_version=payload.expected_version,
            operation_idempotency_key=payload.operation_idempotency_key,
        )
        exec_result = executor.retry_stage(int(run_id), stage_key)
    except PrivateWholeBookLabRunError as exc:
        raise _error_response(exc) from exc
    return {**result, "executor_status": exec_result.status}


def lab_contract_assertions() -> dict[str, Any]:
    return {
        "WHOLE_BOOK_RUNS_ENDPOINT_DISABLED": WHOLE_BOOK_RUNS_ENDPOINT_DISABLED,
        "WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED_DEFAULT": WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
        "WHOLE_BOOK_MOCK_LAB_ENABLED_DEFAULT": WHOLE_BOOK_MOCK_LAB_ENABLED,
        "PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH": PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH,
        "PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER": PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER,
        "PRIVATE_ENGINE_LAB_API_PREFIX": PRIVATE_ENGINE_LAB_API_PREFIX,
        "FIRST_PROVIDER_KEY": PRIVATE_LAB_FIRST_PROVIDER_KEY,
        "FIRST_MODEL_ID": PRIVATE_LAB_FIRST_MODEL_ID,
        "FIRST_QUALITY_PROFILE": PRIVATE_LAB_FIRST_QUALITY_PROFILE,
        "shell_only": False,
        "modules_implemented": True,
        "integration_issue_main_py": INTEGRATION_ISSUE_MAIN_PY_ROUTER_REGISTRATION,
    }


def reset_private_engine_lab_sessions_for_tests() -> None:
    """Compat shim — AnalysisRun-backed Lab no longer uses in-memory sessions."""
    reset_default_private_lab_task_registry()


__all__ = [
    "INTEGRATION_ISSUE_MAIN_PY_ROUTER_REGISTRATION",
    "lab_contract_assertions",
    "reset_private_engine_lab_sessions_for_tests",
    "router",
]
