"""One-shot paid provider connection test.

This service never reads Book/Chapter/Paragraph and never retries or repairs.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisRun,
    ModelInvocation,
    ProviderConfiguration,
    RequestGateDecision,
)
from app.model_gateway.base import ModelProvider, ModelRequest, ProviderRequestError
from app.model_gateway.structured_constraints import schema_hash
from app.schemas.settings import (
    CloudBudgetUpdate,
    ProviderConnectionTestPreflight,
    ProviderConnectionTestResponse,
)
from app.services.cloud_budget import daily_usage
from app.services.cloud_pricing import estimate_cost, pricing_status, resolve_cloud_pricing_path
from app.services.credentials.base import CredentialStore
from app.services.provider_runtime import apply_provider_runtime, cloud_master_enabled
from app.services.structured_output import extract_json_object

# Prefer resolved path so packaged installs fall back to cloud_pricing.default.json.
def _pricing_path() -> Path:
    return resolve_cloud_pricing_path(Path("config/cloud_pricing.json"))


PROMPT_VERSION = "connection-test-v1"
SCHEMA_VERSION = "v1"
ESTIMATED_INPUT_TOKENS = 96
MINIMAL_SYSTEM = (
    "You are a connection-test endpoint. Return exactly one JSON object matching "
    'the schema. Do not add prose: {"status":"ok"}'
)
MINIMAL_USER = (
    'This is an original synthetic connectivity test. Return exactly {"status":"ok"}. '
    "No user document or novel content is included."
)


class MinimalConnectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]


class ConnectionTestFailure(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        error_code: str,
        message: str,
        retryable: bool,
        user_action_hint: str,
        invocation_id: int | None = None,
        request_id: str | None = None,
        http_status: int | None = None,
        exception_type: str | None = None,
        transport_kind: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.retryable = retryable
        self.user_action_hint = user_action_hint
        self.invocation_id = invocation_id
        self.request_id = request_id
        self.http_status = http_status
        self.exception_type = exception_type
        self.transport_kind = transport_kind

    def as_detail(self) -> dict[str, object]:
        return {
            "error_code": self.error_code,
            "message": str(self),
            "retryable": self.retryable,
            "user_action_hint": self.user_action_hint,
            "invocation_id": self.invocation_id,
            "request_id": redact_request_id(self.request_id),
            "http_status": self.http_status,
            "exception_type": self.exception_type,
            "transport_kind": self.transport_kind,
            "stage": "connection_test",
        }


def redact_request_id(request_id: str | None) -> str | None:
    if not request_id:
        return None
    return f"rid#{hashlib.sha256(request_id.encode()).hexdigest()[:12]}"


def _provider_row(session: Session, provider_name: str) -> ProviderConfiguration | None:
    return (
        session.query(ProviderConfiguration)
        .filter_by(provider_name=provider_name)
        .one_or_none()
    )


def _budget_value(session: Session) -> dict:
    from app.db.models import ApplicationSetting

    row = session.get(ApplicationSetting, "cloud_budget_settings")
    return CloudBudgetUpdate.model_validate_json(row.value_json if row else "{}").model_dump()


def connection_test_preflight(
    *,
    session: Session,
    provider: ModelProvider,
    provider_name: str,
    store: CredentialStore,
    max_output_tokens: int = 32,
) -> ProviderConnectionTestPreflight:
    apply_provider_runtime(provider, session, store)
    capabilities = provider.capabilities()
    row = _provider_row(session, provider_name)
    configured = bool(row and (row.base_url or row.workspace_id)) if capabilities.cloud else True
    connected = bool(row and not row.disconnected) if capabilities.cloud else True
    credential = (
        bool(store.available() and store.get(provider_name))
        if capabilities.cloud
        else True
    )
    master_enabled = cloud_master_enabled(session) if capabilities.cloud else True
    pricing_path = _pricing_path()
    pricing = pricing_status(pricing_path)
    budget = _budget_value(session)
    usage = daily_usage(session, budget, master_enabled, pricing)
    estimated_cost, currency, pricing_version = estimate_cost(
        provider.default_model,
        ESTIMATED_INPUT_TOKENS,
        max_output_tokens,
        pricing_path,
    )

    blockers: list[str] = []
    if not capabilities.enabled:
        blockers.append("PROVIDER_DISABLED")
    if not configured:
        blockers.append("PROVIDER_NOT_CONFIGURED")
    if not connected:
        blockers.append("PROVIDER_NOT_CONNECTED")
    if not credential:
        blockers.append("CREDENTIAL_MISSING")
    if not master_enabled:
        blockers.append("CLOUD_MASTER_SWITCH_OFF")
    if not pricing.get("enabled"):
        blockers.append("BUDGET_NOT_AVAILABLE")
    elif estimated_cost is None:
        # Pricing file enabled but this model has no row — distinct from daily budget.
        blockers.append("MODEL_PRICING_NOT_FOUND")
    else:
        # Only evaluate reservation dimensions when cost is known.
        if usage["available_requests"] < 1:
            blockers.append("INSUFFICIENT_BUDGET_RESERVATION")
        if usage["available_tokens"] < ESTIMATED_INPUT_TOKENS + max_output_tokens:
            blockers.append("INSUFFICIENT_BUDGET_RESERVATION")
        if usage["available_estimated_cost"] < float(estimated_cost):
            blockers.append("INSUFFICIENT_BUDGET_RESERVATION")

    return ProviderConnectionTestPreflight(
        provider=provider_name,
        configured_model=provider.default_model,
        max_output_tokens=max_output_tokens,
        estimated_cost=estimated_cost,
        currency=currency or str(budget["currency"]),
        pricing_version=pricing_version,
        remaining_requests=int(usage["available_requests"]),
        remaining_tokens=int(usage["available_tokens"]),
        remaining_estimated_cost=float(usage["available_estimated_cost"]),
        within_budget=not blockers,
        blockers=list(dict.fromkeys(blockers)),
        sends_user_content=False,
    )


def _gate(
    session: Session,
    preflight: ProviderConnectionTestPreflight,
    *,
    allowed: bool,
) -> None:
    session.add(
        RequestGateDecision(
            run_id=None,
            allowed=allowed,
            reason_code=(
                "CONNECTION_TEST_ALLOWED"
                if allowed
                else preflight.blockers[0] if preflight.blockers else "BUDGET_NOT_AVAILABLE"
            ),
            budget_snapshot_json=json.dumps(
                {
                    "stage": "connection_test",
                    "required_requests": 1,
                    "required_tokens": ESTIMATED_INPUT_TOKENS
                    + preflight.max_output_tokens,
                    "required_cost": preflight.estimated_cost,
                    "remaining_requests": preflight.remaining_requests,
                    "remaining_tokens": preflight.remaining_tokens,
                    "remaining_cost": preflight.remaining_estimated_cost,
                },
                sort_keys=True,
            ),
            estimated_request_cost=preflight.estimated_cost,
        )
    )
    session.commit()


def _create_run(
    session: Session,
    *,
    provider_name: str,
    model: str,
) -> AnalysisRun:
    content_hash = hashlib.sha256(MINIMAL_USER.encode()).hexdigest()
    run = AnalysisRun(
        task_type="connection_test",
        subject_type="provider",
        subject_id=provider_name,
        provider=provider_name,
        model=model,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        input_hash=content_hash,
        prompt_hash=hashlib.sha256(MINIMAL_SYSTEM.encode()).hexdigest(),
        status="running",
        started_at=datetime.now(timezone.utc),
        execution_mode="cloud",
        analysis_mode="connection_test",
        cloud_consent=True,
        cloud_consent_at=datetime.now(timezone.utc),
        sends_content_to_cloud=True,
        content_hash=content_hash,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _invocation(
    *,
    run_id: int,
    provider_name: str,
    configured_model: str,
    request: ModelRequest,
    latency_ms: int,
    status: str,
    http_status: int | None,
    response_model: str | None,
    parsed_response: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    request_id: str | None,
    estimated_cost: float | None,
    currency: str | None,
    pricing_version: str | None,
    error_code: str | None,
    error_message: str | None,
    http_request_sent: bool,
    requested_output_tokens: int,
    finish_reason: str | None = None,
) -> ModelInvocation:
    request_json = request.model_dump_json()
    snapshot = json.dumps(
        {
            "test_type": "minimal_json",
            "contains_user_content": False,
            "expected_schema": {"status": "ok"},
        },
        sort_keys=True,
    )
    return ModelInvocation(
        run_id=run_id,
        task_type="connection_test",
        provider_name=provider_name,
        model_name=response_model or configured_model,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        attempt_no=1,
        invocation_kind="connection_test",
        request_hash=hashlib.sha256(request_json.encode()).hexdigest(),
        input_snapshot_json=snapshot,
        raw_response_text="",
        parsed_response_json=parsed_response,
        status=status,
        latency_ms=latency_ms,
        http_status_code=http_status,
        response_model_name=response_model,
        structured_output_mode="json_object",
        schema_hash=schema_hash(MinimalConnectionPayload.model_json_schema()),
        thinking_enabled=False,
        thinking_control_method="chat_template_kwargs.enable_thinking",
        request_parameters_json=json.dumps(
            {
                "temperature": 0,
                "max_output_tokens": requested_output_tokens,
                "provider_parameter_name": "max_tokens",
                "response_format_mode": "json_object",
                "enable_thinking": False,
                "max_real_requests": 1,
                "repair_enabled": False,
            },
            sort_keys=True,
        ),
        is_cloud=True,
        cloud_provider="aliyun_qwen",
        sends_content_to_cloud=True,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        request_id=request_id,
        estimated_cost=estimated_cost,
        currency=currency,
        pricing_version=pricing_version,
        raw_logging_enabled=False,
        content_hash=hashlib.sha256(snapshot.encode()).hexdigest(),
        error_code=error_code,
        error_message=error_message,
        http_request_sent=http_request_sent,
        audit_type="provider_invocation" if http_request_sent else "pre_send_failure",
        sent_at=datetime.now(timezone.utc) if http_request_sent else None,
        requested_output_tokens=requested_output_tokens,
        actual_output_tokens=output_tokens,
        provider_parameter_name="max_tokens",
        finish_reason=finish_reason,
    )


async def run_connection_test(
    *,
    session: Session,
    provider: ModelProvider,
    provider_name: str,
    store: CredentialStore,
    confirmed: bool,
    max_output_tokens: int,
) -> ProviderConnectionTestResponse:
    if not confirmed:
        raise ConnectionTestFailure(
            status_code=422,
            error_code="PAID_TEST_CONFIRMATION_REQUIRED",
            message="真实连接测试必须明确确认可能产生少量费用",
            retryable=False,
            user_action_hint="请在确认框中选择“确认并测试”",
        )

    preflight = connection_test_preflight(
        session=session,
        provider=provider,
        provider_name=provider_name,
        store=store,
        max_output_tokens=max_output_tokens,
    )
    if not preflight.within_budget:
        _gate(session, preflight, allowed=False)
        code = preflight.blockers[0] if preflight.blockers else "BUDGET_NOT_AVAILABLE"
        status = 422 if code in {
            "PROVIDER_DISABLED",
            "PROVIDER_NOT_CONFIGURED",
            "PROVIDER_NOT_CONNECTED",
            "CREDENTIAL_MISSING",
            "CLOUD_MASTER_SWITCH_OFF",
        } else 409
        raise ConnectionTestFailure(
            status_code=status,
            error_code=code,
            message="真实连接测试门禁未通过",
            retryable=code in {"PROVIDER_NOT_CONNECTED"},
            user_action_hint="请修复Provider配置、连接或预算后再试",
        )

    _gate(session, preflight, allowed=True)
    run = _create_run(
        session,
        provider_name=provider_name,
        model=preflight.configured_model,
    )
    request = ModelRequest(
        messages=[
            {"role": "system", "content": MINIMAL_SYSTEM},
            {"role": "user", "content": MINIMAL_USER},
        ],
        model=preflight.configured_model,
        temperature=0,
        max_output_tokens=max_output_tokens,
        response_schema=MinimalConnectionPayload.model_json_schema(),
        response_format_mode="json_object",
        enable_thinking=False,
    )
    started = time.perf_counter()
    try:
        # Exactly one call. No generate_validated, repair, retry, Flash or Max.
        response = await provider.generate(request)
        latency_ms = int((time.perf_counter() - started) * 1000)
        parsed_json = extract_json_object(response.text)
        payload = MinimalConnectionPayload.model_validate_json(parsed_json)
        normalized = payload.model_dump_json()
        cost, currency, pricing_version = estimate_cost(
            response.model,
            response.input_tokens,
            response.output_tokens,
            _pricing_path(),
        )
        if cost is None:
            cost, currency, pricing_version = estimate_cost(
                preflight.configured_model,
                response.input_tokens,
                response.output_tokens,
                _pricing_path(),
            )
        invocation = _invocation(
            run_id=run.id,
            provider_name=provider_name,
            configured_model=preflight.configured_model,
            request=request,
            latency_ms=latency_ms,
            status="succeeded",
            http_status=response.http_status_code,
            response_model=response.model,
            parsed_response=normalized,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            total_tokens=response.total_tokens,
            request_id=response.request_id,
            estimated_cost=cost,
            currency=currency,
            pricing_version=pricing_version,
            error_code=None,
            error_message=None,
            http_request_sent=True,
            requested_output_tokens=max_output_tokens,
            finish_reason=response.finish_reason,
        )
        session.add(invocation)
        session.flush()
        run.status = "succeeded"
        run.completed_at = datetime.now(timezone.utc)
        run.validated_output = normalized
        session.commit()
        session.refresh(invocation)
        try:
            from app.services.ai_validation_snapshot import record_validation_outcome

            record_validation_outcome(
                session,
                store,
                provider_id=provider_name,
                ok=True,
                model_name=response.model or preflight.configured_model,
                provider_request_id=redact_request_id(response.request_id),
                validation_latency_ms=latency_ms,
            )
        except Exception:  # noqa: BLE001
            # Snapshot persistence must not fail a successful connection probe.
            pass
        return ProviderConnectionTestResponse(
            status="healthy",
            http_status=response.http_status_code or 200,
            provider=provider_name,
            configured_model=preflight.configured_model,
            response_model=response.model,
            json_valid=True,
            schema_valid=True,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            total_tokens=response.total_tokens,
            latency_ms=latency_ms,
            invocation_id=invocation.id,
            estimated_cost=cost,
            currency=currency,
            pricing_version=pricing_version,
            request_id=redact_request_id(response.request_id),
            retryable=False,
        )
    except (ProviderRequestError, ValidationError, ValueError, json.JSONDecodeError) as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        provider_error = exc if isinstance(exc, ProviderRequestError) else None
        error_code = (
            provider_error.error_code
            if provider_error is not None
            else "REQUEST_VALIDATION_ERROR"
        )
        message = str(exc).strip() or error_code
        invocation = _invocation(
            run_id=run.id,
            provider_name=provider_name,
            configured_model=preflight.configured_model,
            request=request,
            latency_ms=latency_ms,
            status="failed",
            http_status=provider_error.http_status_code if provider_error else None,
            response_model=None,
            parsed_response=None,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            request_id=provider_error.request_id if provider_error else None,
            estimated_cost=None,
            currency=preflight.currency,
            pricing_version=preflight.pricing_version,
            error_code=error_code,
            error_message=message[:500],
            http_request_sent=provider_error.http_request_sent if provider_error else True,
            requested_output_tokens=max_output_tokens,
        )
        session.add(invocation)
        session.flush()
        run.status = "failed"
        run.error_code = "CONNECTION_TEST_FAILED"
        run.error_message = "真实连接测试失败"
        run.root_error_code = error_code
        run.root_error_message = message[:500]
        run.failed_stage = "connection_test"
        run.failed_invocation_id = invocation.id
        run.retryable = bool(provider_error.retryable) if provider_error else False
        run.user_action_hint = (
            provider_error.user_action_hint
            if provider_error
            else "Provider已返回内容，但最小JSON或Schema校验失败"
        )
        run.completed_at = datetime.now(timezone.utc)
        session.commit()
        raise ConnectionTestFailure(
            status_code=provider_error.http_status_code or 502 if provider_error else 422,
            error_code=error_code,
            message=message,
            retryable=bool(provider_error.retryable) if provider_error else False,
            user_action_hint=run.user_action_hint,
            invocation_id=invocation.id,
            request_id=provider_error.request_id if provider_error else None,
            http_status=provider_error.http_status_code if provider_error else None,
            exception_type=type(exc).__name__,
            transport_kind=provider_error.transport_kind if provider_error else None,
        ) from exc
