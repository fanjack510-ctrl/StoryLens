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
from app.narrative_core.services.private_lab_run_executor import PrivateLabRunExecutor
from app.narrative_core.services.in_process_private_lab_task_registry import (
    get_default_private_lab_task_registry,
    reset_default_private_lab_task_registry,
)
from app.narrative_core.services.private_lab_service_adapters import (
    resolve_server_security_status,
)
from app.narrative_core.services.private_whole_book_analysis_runtime import (
    create_lab_private_whole_book_analysis_runtime,
)
from app.narrative_core.services.private_whole_book_live_readiness_runtime import (
    get_or_create_default_live_readiness_runtime,
    reset_default_live_readiness_runtime_for_tests,
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
    # Deprecated client self-attestation — live create ignores these; dry-run compat only.
    data_transfer_consented: bool = Field(
        default=True,
        description="DEPRECATED: server rebuilds consent; ignored for live create",
        json_schema_extra={"deprecated": True},
    )
    user_confirmed: bool = Field(
        default=True,
        description="User explicit confirm flag — still required; not a security proof alone",
    )
    credential_present: bool = Field(
        default=False,
        description="DEPRECATED: server resolves credential status",
        json_schema_extra={"deprecated": True},
    )
    budget_ok: bool = Field(
        default=True,
        description="DEPRECATED: server BudgetGuard decides",
        json_schema_extra={"deprecated": True},
    )
    capability_ok: bool = Field(
        default=True,
        description="DEPRECATED: server Capability Service decides",
        json_schema_extra={"deprecated": True},
    )
    configuration_fingerprint: str = Field(default="private-lab-cfg", min_length=1)
    idempotency_key: str = Field(default="private-lab", min_length=1, max_length=128)
    create_idempotency_key: str | None = Field(
        default=None,
        max_length=128,
        description="Alias for idempotency_key",
    )
    preflight_fingerprint: str = Field(min_length=1)
    estimate_fingerprint: str = Field(min_length=1)
    consent_fingerprint: str = Field(min_length=1)
    data_transfer_manifest_hash: str = Field(min_length=1)
    expected_manifest_hash: str | None = Field(
        default=None,
        description="Optional alias; compared to server-rebuilt manifest hash",
    )
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


def _lab_runtime():
    # Development/test Lab composition — formal resolver + credentials (CHG-049).
    from app.core.config import get_settings

    env = str(getattr(get_settings(), "app_env", None) or "development")
    if env not in {"development", "test", "dev"}:
        env = "development"
    return get_or_create_default_live_readiness_runtime(environment=env, lab_enabled=True)


def get_run_service(session: Session = Depends(get_db)) -> PrivateWholeBookLabRunService:
    runtime = _lab_runtime()
    return runtime.build_run_service(session)


def get_executor(session: Session = Depends(get_db)) -> PrivateLabRunExecutor:
    runtime = _lab_runtime()

    def _runtime_factory(**kwargs: Any) -> Any:
        live = not bool(kwargs.get("dry_run", True))
        return create_lab_private_whole_book_analysis_runtime(
            session=kwargs.get("session"),
            book_id=kwargs.get("book_id"),
            use_phase1b_persistence=bool(kwargs.get("use_phase1b_persistence", True)),
            lab_dry_run=not live,
            fallback_to_fake=not live,
            require_private_real=live,
        )

    if runtime.runtime_factory is None:
        runtime.runtime_factory = _runtime_factory
    return runtime.build_executor(session)


@router.post("/preflight", summary="Private Lab preflight (no Run)")
def private_lab_preflight(
    body: PrivateLabPreflightBody,
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_write_lab_gate(request, dry_run=True)
    runtime = _lab_runtime()
    assert runtime.preflight is not None
    runtime.bind_session(session)
    result = runtime.preflight.preflight(
        book_id=int(body.book_id),
        book_snapshot_id=int(body.book_snapshot_id),
        configuration_fingerprint=body.configuration_fingerprint,
        requested_modules=tuple(body.requested_modules),
    )
    details = dict(result.details)
    # Safety: never surface secrets; normalize credential to PRESENT/MISSING only.
    if "credential_present" in details:
        details["credential_status"] = (
            "PRESENT" if details.get("credential_present") else "MISSING"
        )
    return {
        "ok": result.ok,
        "fingerprint": result.fingerprint,
        "book_id": result.book_id,
        "book_snapshot_id": result.book_snapshot_id,
        "snapshot_content_hash": result.snapshot_content_hash,
        "reason_code": result.reason_code,
        "details": details,
        "private_lab": True,
        "non_production": True,
        "run_created": False,
        "can_enter_estimate": bool(result.ok and result.details.get("can_enter_estimate")),
        "resolver_is_fake": bool(runtime.uses_fake_resolver),
    }


@router.post("/estimate", summary="Private Lab estimate (no Run)")
def private_lab_estimate(
    body: PrivateLabEstimateBody,
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_write_lab_gate(request, dry_run=True)
    runtime = _lab_runtime()
    assert runtime.preflight is not None
    assert runtime.estimate is not None
    runtime.bind_session(session)
    pre = runtime.preflight.preflight(
        book_id=int(body.book_id),
        book_snapshot_id=int(body.book_snapshot_id),
        configuration_fingerprint=body.configuration_fingerprint,
        requested_modules=tuple(body.requested_modules),
    )
    if pre.snapshot_content_hash:
        runtime.estimate.snapshot_content_hash = str(pre.snapshot_content_hash)
    result = runtime.estimate.estimate(
        book_id=int(body.book_id),
        book_snapshot_id=int(body.book_snapshot_id),
        configuration_fingerprint=body.configuration_fingerprint,
        provider_key=body.provider_key,
        model_id=body.model_id,
        quality_profile=body.quality_profile,
        requested_modules=tuple(body.requested_modules),
        preflight_fingerprint=body.preflight_fingerprint or pre.fingerprint,
    )
    cached = runtime.estimate._cache.get(result.fingerprint) or {}
    consent_fp = str(cached.get("consent_fingerprint") or "")
    primary = cached.get("primary_manifest")
    module_estimates = list(cached.get("module_estimates") or [])
    selection: dict[str, Any] = {}
    if primary is not None and hasattr(primary, "safe_dict"):
        safe = primary.safe_dict()
        selection = {
            "selected_chapter_ids": safe.get("selected_chapter_ids"),
            "selected_paragraph_ids": safe.get("selected_paragraph_ids"),
            "selected_context_unit_ids": safe.get("selected_context_unit_ids"),
            "source_character_count": safe.get("source_character_count"),
            "context_bundle_hash": safe.get("context_bundle_hash"),
            "sends_source_text": safe.get("sends_source_text"),
            "sends_derived_text": safe.get("sends_derived_text"),
            "retention_policy": safe.get("retention_policy"),
        }
    # CHG-057: project repair budget from module estimate safe_dict (no prompts/bodies).
    primary_est: dict[str, Any] = {}
    for est in module_estimates:
        if isinstance(est, dict) and est.get("module_key") == "book_overview":
            primary_est = est
            break
    if not primary_est and module_estimates and isinstance(module_estimates[0], dict):
        primary_est = module_estimates[0]
    usage = dict(result.usage_summary)
    cost = dict(result.cost_summary)
    repair_policy = primary_est.get("repair_policy")
    repair_policy_version = primary_est.get("repair_policy_version")
    max_repair_count = primary_est.get("max_repair_count")
    expected_no_repair_cost = primary_est.get("expected_no_repair_cost")
    max_one_repair_cost = primary_est.get("max_one_repair_cost")
    max_total_authorized_cost = primary_est.get("max_total_authorized_cost")
    # Safe response — no bodies / prompts / credentials / messages / raw schema
    return {
        "fingerprint": result.fingerprint,
        "estimate_fingerprint": result.fingerprint,
        "consent_fingerprint": consent_fp,
        "configuration_fingerprint": result.configuration_fingerprint,
        "provider_key": result.provider_key,
        "model_id": result.model_id,
        "quality_profile": result.quality_profile,
        "module_keys": list(result.module_keys),
        "usage_summary": usage,
        "cost_summary": cost,
        "estimated_input_tokens": usage.get("estimated_input_tokens"),
        "estimated_output_tokens": usage.get("estimated_output_tokens"),
        "estimated_total_tokens": usage.get("estimated_total_tokens"),
        "pricing_version": cost.get("pricing_version"),
        "repair_policy": repair_policy,
        "repair_policy_version": repair_policy_version,
        "max_repair_count": max_repair_count,
        "expected_no_repair_cost": expected_no_repair_cost,
        "max_one_repair_cost": max_one_repair_cost,
        "max_total_authorized_cost": max_total_authorized_cost,
        "data_transfer_manifest_hash": result.data_transfer_manifest_hash,
        "selection_summary": selection,
        "execution_context_binding": (
            dict(cached.get("execution_context_binding") or {})
            if isinstance(cached.get("execution_context_binding"), dict)
            else None
        ),
        "private_lab": True,
        "non_production": True,
        "run_created": False,
        "tokens_hardcoded": False,
        "cost_hardcoded": False,
        "calls_provider": False,
        "resolver_is_fake": bool(runtime.uses_fake_resolver),
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
    runtime = _lab_runtime()
    # Server-side security — client booleans are not authoritative for live create.
    security = resolve_server_security_status(
        credential_resolver=runtime.credential_adapter,
        budget_guard=runtime.budget_guard,
        capability_ok=True,  # Lab path: capability gated by Lab flag + env, not client bool
        estimated_tokens=0,
        estimated_cost=None,
    )
    if body.dry_run:
        # Dry-run: credential not required; still do not trust client budget/capability lies
        # when server budget is force-denied.
        cred_present = False
        budget_ok = security.budget_ok
        capability_ok = security.capability_ok
    else:
        cred_present = security.credential_present
        budget_ok = security.budget_ok
        capability_ok = security.capability_ok

    _require_write_lab_gate(
        request,
        dry_run=bool(body.dry_run),
        credential_present=cred_present,
        data_transfer_consented=True,  # consent proven by fingerprint match below
        budget_ok=budget_ok,
        capability_ok=capability_ok,
        user_confirmed=bool(body.user_confirmed),
    )
    host = _client_host(request)
    idem = body.create_idempotency_key or body.idempotency_key
    manifest_hash = body.expected_manifest_hash or body.data_transfer_manifest_hash
    try:
        result = service.create_run(
            CreatePrivateLabRunRequest(
                book_id=int(body.book_id),
                book_snapshot_id=int(body.book_snapshot_id),
                analysis_mode=body.analysis_mode,
                requested_modules=tuple(body.requested_modules),
                configuration_fingerprint=body.configuration_fingerprint,
                idempotency_key=idem,
                preflight_fingerprint=body.preflight_fingerprint,
                estimate_fingerprint=body.estimate_fingerprint,
                consent_fingerprint=body.consent_fingerprint,
                data_transfer_manifest_hash=manifest_hash,
                context_bundle_hash=body.context_bundle_hash,
                prompt_pack_id=body.prompt_pack_id,
                prompt_pack_version=body.prompt_pack_version,
                provider_key=body.provider_key,
                model_id=body.model_id,
                quality_profile=body.quality_profile,
                output_locale=body.output_locale,
                source_language=body.source_language,
                dry_run=bool(body.dry_run),
                data_transfer_consented=True,
                user_confirmed=bool(body.user_confirmed),
                credential_present=cred_present,
                budget_ok=budget_ok,
                capability_ok=capability_ok,
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
        "server_security": {
            "credential_present": cred_present,
            "budget_ok": budget_ok,
            "capability_ok": capability_ok,
            "client_booleans_authoritative": False,
        },
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
    """Compat shim — reset task registry + live readiness runtime DI."""
    reset_default_private_lab_task_registry()
    reset_default_live_readiness_runtime_for_tests()


__all__ = [
    "INTEGRATION_ISSUE_MAIN_PY_ROUTER_REGISTRATION",
    "lab_contract_assertions",
    "reset_private_engine_lab_sessions_for_tests",
    "router",
]
