"""Atomic recommended Aliyun Bailian (Qwen) setup for ordinary users.

Wizard and Settings must share this path so credentials, ProviderConfiguration,
cloud master switch, and eligibility stay consistent.

Validation layers (must not be conflated):
1. Transport diagnostic — network only (DNS/TCP/TLS); used by advanced UI.
2. Model service validation — minimal original JSON request (API Key + model).
3. Analysis readiness — same eligibility / pricing / budget gates as real analysis.
"""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ApplicationSetting, ProviderConfiguration
from app.model_gateway.base import ModelRequest, ProviderRequestError
from app.model_gateway.gateway import ModelGateway
from app.schemas.settings import CloudBudgetUpdate
from app.services.aliyun_endpoint import CN_BEIJING, resolve_aliyun_compatible_base_url
from app.services.ai_validation_snapshot import (
    build_current_fingerprints,
    derive_connection_ui_state,
    format_validated_at_local,
    load_validation_snapshot,
    public_snapshot_view,
    record_validation_outcome,
)
from app.services.cloud_pricing import model_pricing_available, resolve_cloud_pricing_path
from app.services.credentials.base import CredentialStore
from app.services.provider_bootstrap import (
    ensure_aliyun_provider_configuration,
    is_aliyun_cloud_provider,
)
from app.services.provider_eligibility import evaluate_manual_boundary_candidate
from app.services.provider_runtime import apply_provider_runtime
from app.services.setup_readiness_copy import blocker_guidance, blocker_label
from app.services.structured_output import extract_json_object
from app.services.transport_diagnostic import run_transport_diagnostic

CANONICAL_PROVIDER_ID = "aliyun_qwen_plus"
ANALYSIS_MODE_KEY = "recommended_analysis_mode"
CLOUD_KEY = "cloud_enabled"
CLOUD_BUDGET_KEY = "cloud_budget_settings"
CLOUD_BODY_CONSENT_KEY = "cloud_body_consent"

AnalysisMode = Literal["FAST", "BALANCED", "QUALITY"]

ANALYSIS_MODE_PRESETS: dict[AnalysisMode, dict[str, object]] = {
    "FAST": {
        "plus_model": "qwen3.6-flash",
        "flash_model": "qwen3.6-flash",
        "max_model": "qwen3.7-max",
        "timeout_seconds": 180,
        "max_retries": 2,
        "cloud_max_output_tokens_per_request": 2500,
        "cloud_max_input_tokens_per_request": 12000,
        "cloud_max_requests_per_run": 35,
    },
    "BALANCED": {
        "plus_model": "qwen3.7-plus",
        "flash_model": "qwen3.6-flash",
        "max_model": "qwen3.7-max",
        "timeout_seconds": 300,
        "max_retries": 3,
        "cloud_max_output_tokens_per_request": 4000,
        "cloud_max_input_tokens_per_request": 16000,
        "cloud_max_requests_per_run": 50,
    },
    "QUALITY": {
        "plus_model": "qwen3.7-max",
        "flash_model": "qwen3.6-flash",
        "max_model": "qwen3.7-max",
        "timeout_seconds": 420,
        "max_retries": 3,
        "cloud_max_output_tokens_per_request": 6000,
        "cloud_max_input_tokens_per_request": 20000,
        "cloud_max_requests_per_run": 60,
    },
}

TransportProbe = Callable[..., dict]
ModelProbe = Callable[..., dict]

_MINIMAL_SYSTEM = (
    "You are a connection-test endpoint. Return exactly one JSON object matching "
    'the schema. Do not add prose: {"status":"ok"}'
)
_MINIMAL_USER = (
    'This is an original synthetic connectivity test. Return exactly {"status":"ok"}. '
    "No user document or novel content is included."
)


@dataclass
class RecommendedAiSetupResult:
    ok: bool
    user_message: str
    persisted: bool
    credential_configured: bool
    provider_enabled: bool
    cloud_enabled: bool
    provider_eligible: bool
    selected_provider_id: str
    connection_status: str
    analysis_mode: str | None
    blockers: list[str]
    needs_cloud_consent: bool = False
    error_code: str | None = None
    raw_diagnostic: dict | None = None
    model_validated: bool = False
    analysis_ready: bool = False
    readiness_reasons: list[str] = field(default_factory=list)
    http_status: int | None = None
    error_category: str | None = None
    retryable: bool | None = None
    cloud_body_consent: bool = False
    connection_ui_state: str | None = None
    connection_ui_label: str | None = None
    connection_ui_reason: str | None = None
    validated_at: str | None = None
    validated_at_display: str | None = None
    validated_model: str | None = None
    validation_snapshot: dict | None = None


def _application_version() -> str:
    try:
        root = Path(__file__).resolve().parents[4]
        version_path = root / "VERSION"
        if version_path.is_file():
            return version_path.read_text(encoding="utf-8").strip() or "unknown"
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def _pricing_path() -> Path:
    return resolve_cloud_pricing_path(Path("config/cloud_pricing.json"))


def _attach_connection_ui(
    session: Session,
    store: CredentialStore,
    result: RecommendedAiSetupResult,
) -> RecommendedAiSetupResult:
    consent = bool(_read_setting(session, CLOUD_BODY_CONSENT_KEY, False))
    snapshot = load_validation_snapshot(session)
    current = build_current_fingerprints(
        session, store, provider_id=CANONICAL_PROVIDER_ID, cloud_key=CLOUD_KEY
    )
    state, label, reason = derive_connection_ui_state(
        credential_configured=result.credential_configured,
        provider_enabled=result.provider_enabled,
        cloud_enabled=result.cloud_enabled,
        cloud_body_consent=consent,
        provider_eligible=result.provider_eligible,
        snapshot=snapshot,
        current=current,
    )
    # Analysis ready requires verified snapshot + consent + eligibility gates.
    analysis_ready = state == "READY"
    model_validated = state in {"VERIFIED", "CONSENT_REQUIRED", "READY"}
    result.cloud_body_consent = consent
    result.connection_ui_state = state
    result.connection_ui_label = label
    result.connection_ui_reason = reason
    result.validated_at = (snapshot or {}).get("validated_at")
    result.validated_at_display = format_validated_at_local(result.validated_at)
    result.validated_model = (snapshot or {}).get("response_model") or (snapshot or {}).get(
        "model_id"
    )
    result.validation_snapshot = public_snapshot_view(snapshot)
    result.model_validated = model_validated
    result.analysis_ready = analysis_ready
    if analysis_ready:
        result.ok = True
        if not result.user_message or "配置完成" in result.user_message:
            result.user_message = "模型服务验证成功，可以开始分析。"
    result.needs_cloud_consent = state == "CONSENT_REQUIRED" or (
        result.credential_configured and not consent
    )
    return result


def _record_probe_snapshot(
    session: Session,
    store: CredentialStore,
    *,
    ok: bool,
    model_name: str | None,
    failure_category: str | None = None,
    failure_message: str | None = None,
) -> None:
    record_validation_outcome(
        session,
        store,
        provider_id=CANONICAL_PROVIDER_ID,
        ok=ok,
        model_name=model_name,
        failure_category=failure_category,
        failure_message=failure_message,
        application_version=_application_version(),
        cloud_key=CLOUD_KEY,
    )


def _save_setting(session: Session, key: str, value) -> None:
    row = session.get(ApplicationSetting, key)
    payload = json.dumps(value)
    if row is None:
        session.add(ApplicationSetting(key=key, value_json=payload))
    else:
        row.value_json = payload
        row.updated_at = datetime.now(timezone.utc)
    session.commit()


def _read_setting(session: Session, key: str, default):
    row = session.get(ApplicationSetting, key)
    if row is None:
        return default
    return json.loads(row.value_json)


def _restore_credential(store: CredentialStore, provider_id: str, previous: str | None) -> None:
    if previous is None:
        store.delete(provider_id)
    else:
        store.set(provider_id, previous)


def _apply_analysis_mode(session: Session, row: ProviderConfiguration, mode: AnalysisMode) -> None:
    preset = ANALYSIS_MODE_PRESETS[mode]
    row.plus_model = str(preset["plus_model"])
    row.flash_model = str(preset["flash_model"])
    row.max_model = str(preset["max_model"])
    row.timeout_seconds = int(preset["timeout_seconds"])
    row.max_retries = int(preset["max_retries"])
    budget = CloudBudgetUpdate.model_validate(
        _read_setting(session, CLOUD_BUDGET_KEY, {})
    ).model_dump()
    budget.update(
        {
            "cloud_max_output_tokens_per_request": preset["cloud_max_output_tokens_per_request"],
            "cloud_max_input_tokens_per_request": preset["cloud_max_input_tokens_per_request"],
            "cloud_max_requests_per_run": preset["cloud_max_requests_per_run"],
            "currency": "CNY",
        }
    )
    _save_setting(session, CLOUD_BUDGET_KEY, budget)
    _save_setting(session, ANALYSIS_MODE_KEY, mode)


def _ensure_canonical_provider(session: Session) -> ProviderConfiguration:
    row = ensure_aliyun_provider_configuration(
        session, CANONICAL_PROVIDER_ID, create_if_missing=True
    )
    assert row is not None
    cfg = get_settings()
    resolved = resolve_aliyun_compatible_base_url(
        base_url=row.base_url,
        workspace_id=row.workspace_id,
        region=row.region or CN_BEIJING,
        settings=cfg,
        allow_region_public_default=True,
    )
    if resolved and not (row.base_url or "").strip():
        row.base_url = resolved
    if not (row.display_name or "").strip():
        row.display_name = "阿里云百炼"
    if not (row.region or "").strip():
        row.region = CN_BEIJING
    row.allow_auto_route = False
    row.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(row)
    return row


def _run_coro(coro):
    """Run an async coroutine from sync setup code (FastAPI sync route / unit tests)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _eligibility_snapshot(
    session: Session,
    store: CredentialStore,
    gateway: ModelGateway,
) -> tuple[bool, list[str], bool, bool, bool, str]:
    provider = gateway.get(CANONICAL_PROVIDER_ID)
    caps = provider.capabilities()
    evaluation = evaluate_manual_boundary_candidate(
        session,
        provider_name=CANONICAL_PROVIDER_ID,
        capabilities=caps,
        store=store,
        pricing_path=_pricing_path(),
    )
    blockers = list(evaluation.get("manual_selection_blockers") or [])
    eligible = bool(evaluation.get("manual_boundary_candidate_eligible"))
    credential = bool(evaluation.get("credential_configured"))
    enabled = bool(evaluation.get("enabled"))
    cloud_enabled = bool(_read_setting(session, CLOUD_KEY, False))
    row = (
        session.query(ProviderConfiguration)
        .filter_by(provider_name=CANONICAL_PROVIDER_ID)
        .one_or_none()
    )
    plus_model = (row.plus_model if row else None) or "qwen3.7-plus"
    if eligible and not model_pricing_available(plus_model, _pricing_path()):
        blockers.append("pricing_unavailable")
        eligible = False
    if row is None:
        connection = "unconfigured"
    elif not row.enabled:
        connection = "disabled"
    elif row.disconnected:
        connection = "disconnected"
    elif not credential:
        connection = "unconfigured"
    elif eligible:
        connection = "connected"
    else:
        connection = "partial"
    return eligible, blockers, credential, enabled, cloud_enabled, connection


def _readiness_reasons(blockers: list[str], *, model: str | None = None) -> list[str]:
    return [blocker_label(code) for code in blockers] or (
        [blocker_label("SETUP_INCOMPLETE")] if blockers is not None else []
    )


def _status_message_for_snapshot(
    *,
    credential: bool,
    enabled: bool,
    cloud_enabled: bool,
    eligible: bool,
    blockers: list[str],
    model: str | None,
) -> tuple[bool, str, str | None]:
    analysis_ready = bool(credential and enabled and cloud_enabled and eligible)
    if analysis_ready:
        return True, "配置完成，可以开始分析", None
    if not credential:
        return False, "尚未填写 API Key", "CREDENTIAL_MISSING"
    if not enabled:
        return False, "API Key 已保存，但模型服务未启用", "PROVIDER_DISABLED"
    if not cloud_enabled:
        return False, "云端模型服务尚未开启", "CLOUD_DISABLED"
    primary = blockers[0] if blockers else "SETUP_INCOMPLETE"
    label = blocker_label(primary)
    guidance = blocker_guidance(primary, model=model)
    return False, f"{label}\n{guidance}" if guidance else label, primary


def get_recommended_qwen_status(
    session: Session,
    store: CredentialStore,
    gateway: ModelGateway,
) -> RecommendedAiSetupResult:
    if not is_aliyun_cloud_provider(CANONICAL_PROVIDER_ID):
        raise RuntimeError("canonical provider must be Aliyun")
    ensure_aliyun_provider_configuration(
        session, CANONICAL_PROVIDER_ID, create_if_missing=False
    )
    eligible, blockers, credential, enabled, cloud_enabled, connection = _eligibility_snapshot(
        session, store, gateway
    )
    mode = _read_setting(session, ANALYSIS_MODE_KEY, None)
    row = (
        session.query(ProviderConfiguration)
        .filter_by(provider_name=CANONICAL_PROVIDER_ID)
        .one_or_none()
    )
    model = (row.plus_model if row else None) or "qwen3.7-plus"
    ok, message, error_code = _status_message_for_snapshot(
        credential=credential,
        enabled=enabled,
        cloud_enabled=cloud_enabled,
        eligible=eligible,
        blockers=blockers,
        model=model,
    )
    result = RecommendedAiSetupResult(
        ok=ok,
        user_message=message,
        persisted=True,
        credential_configured=credential,
        provider_enabled=enabled,
        cloud_enabled=cloud_enabled,
        provider_eligible=eligible,
        selected_provider_id=CANONICAL_PROVIDER_ID,
        connection_status=connection,
        analysis_mode=mode if isinstance(mode, str) else None,
        blockers=blockers,
        needs_cloud_consent=bool(credential and enabled and not cloud_enabled),
        error_code=error_code,
        model_validated=False,
        analysis_ready=False,
        readiness_reasons=_readiness_reasons(blockers, model=model) if not ok else [],
    )
    return _attach_connection_ui(session, store, result)


def _probe_transport(
    *,
    session: Session,
    gateway: ModelGateway,
    store: CredentialStore,
    transport_probe: TransportProbe | None,
) -> dict:
    probe = transport_probe or run_transport_diagnostic
    provider = gateway.get(CANONICAL_PROVIDER_ID)
    return probe(
        provider_name=CANONICAL_PROVIDER_ID,
        provider=provider,
        session=session,
        store=store,
    )


async def _async_model_validate(
    *,
    session: Session,
    gateway: ModelGateway,
    store: CredentialStore,
    model_name: str,
) -> dict:
    provider = gateway.get(CANONICAL_PROVIDER_ID)
    apply_provider_runtime(provider, session, store)
    request = ModelRequest(
        messages=[
            {"role": "system", "content": _MINIMAL_SYSTEM},
            {"role": "user", "content": _MINIMAL_USER},
        ],
        model=model_name,
        temperature=0,
        max_output_tokens=32,
        response_format_mode="json_object",
        enable_thinking=False,
    )
    try:
        response = await provider.generate(request)
        parsed = extract_json_object(response.text)
        payload = json.loads(parsed)
        if payload.get("status") != "ok":
            return {
                "ok": False,
                "error_code": "MODEL_NOT_AVAILABLE",
                "detail": "模型返回了非预期响应",
            }
        return {
            "ok": True,
            "error_code": None,
            "model": response.model or model_name,
            "http_status": response.http_status_code,
        }
    except ProviderRequestError as exc:
        code = getattr(exc, "error_code", None) or "CREDENTIAL_INVALID"
        upper = str(code).upper()
        http_status = getattr(exc, "http_status_code", None)
        error_category = getattr(exc, "error_category", None)
        retryable = getattr(exc, "retryable", None)
        if http_status == 429 or error_category == "rate_limited":
            mapped = "RATE_LIMITED"
            error_category = "rate_limited"
            retryable = True if retryable is None else bool(retryable)
        elif "AUTH" in upper or "401" in upper or "403" in upper:
            mapped = "CREDENTIAL_INVALID"
        elif "MODEL" in upper and "NOT" in upper:
            mapped = "MODEL_NOT_AVAILABLE"
        else:
            mapped = upper
        return {
            "ok": False,
            "error_code": mapped,
            "detail": str(exc),
            "http_status": http_status,
            "error_category": error_category,
            "retryable": retryable,
        }
    except (ValidationError, json.JSONDecodeError, ValueError) as exc:
        return {
            "ok": False,
            "error_code": "MODEL_NOT_AVAILABLE",
            "detail": type(exc).__name__,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error_code": "CONNECTION_TEST_FAILED",
            "detail": type(exc).__name__,
        }


def _default_model_probe(
    *,
    session: Session,
    gateway: ModelGateway,
    store: CredentialStore,
    model_name: str,
) -> dict:
    return _run_coro(
        _async_model_validate(
            session=session,
            gateway=gateway,
            store=store,
            model_name=model_name,
        )
    )


def configure_recommended_qwen(
    *,
    session: Session,
    store: CredentialStore,
    gateway: ModelGateway,
    api_key: str | None,
    analysis_mode: AnalysisMode,
    cloud_body_consent: bool,
    persist: bool,
    transport_probe: TransportProbe | None = None,
    model_probe: ModelProbe | None = None,
) -> RecommendedAiSetupResult:
    """Validate model service and optionally persist ordinary Bailian setup.

    Order when persist=True:
    1. Validate API Key with minimal JSON request
    2. Save credential to Windows Credential Manager / keyring
    3. Persist Provider + cloud + analysis mode
    4. Re-read credential and recompute eligibility / pricing / budget
    5. Mark analysis_ready only when eligibility matches real analysis gates
    """
    if not store.available():
        return RecommendedAiSetupResult(
            ok=False,
            user_message="本机凭据保险柜不可用，无法保存 API Key。",
            persisted=False,
            credential_configured=False,
            provider_enabled=False,
            cloud_enabled=bool(_read_setting(session, CLOUD_KEY, False)),
            provider_eligible=False,
            selected_provider_id=CANONICAL_PROVIDER_ID,
            connection_status="unconfigured",
            analysis_mode=_read_setting(session, ANALYSIS_MODE_KEY, None),
            blockers=["credential_store_unavailable"],
            error_code="CREDENTIAL_STORE_UNAVAILABLE",
            readiness_reasons=[blocker_label("credential_store_unavailable")],
        )

    previous = store.get(CANONICAL_PROVIDER_ID)
    key = (api_key or "").strip() or None
    if key is None and not previous:
        return RecommendedAiSetupResult(
            ok=False,
            user_message="请填写 API Key 后再试。",
            persisted=False,
            credential_configured=False,
            provider_enabled=False,
            cloud_enabled=bool(_read_setting(session, CLOUD_KEY, False)),
            provider_eligible=False,
            selected_provider_id=CANONICAL_PROVIDER_ID,
            connection_status="unconfigured",
            analysis_mode=_read_setting(session, ANALYSIS_MODE_KEY, None),
            blockers=["credential_missing"],
            error_code="CREDENTIAL_MISSING",
            readiness_reasons=[blocker_label("credential_missing")],
        )

    if persist and not cloud_body_consent:
        return RecommendedAiSetupResult(
            ok=False,
            user_message="请先确认可将章节正文发送至所选模型服务商。",
            persisted=False,
            credential_configured=bool(previous),
            provider_enabled=False,
            cloud_enabled=bool(_read_setting(session, CLOUD_KEY, False)),
            provider_eligible=False,
            selected_provider_id=CANONICAL_PROVIDER_ID,
            connection_status="unconfigured",
            analysis_mode=_read_setting(session, ANALYSIS_MODE_KEY, None),
            blockers=["cloud_consent_required"],
            needs_cloud_consent=True,
            error_code="CLOUD_CONSENT_REQUIRED",
            readiness_reasons=[blocker_label("cloud_consent_required")],
        )

    row = _ensure_canonical_provider(session)
    preset_model = str(ANALYSIS_MODE_PRESETS[analysis_mode]["plus_model"])
    previous_enabled = bool(row.enabled)
    previous_disconnected = bool(row.disconnected)
    previous_cloud = bool(_read_setting(session, CLOUD_KEY, False))

    temporary_key = False
    if key is not None:
        try:
            store.set(CANONICAL_PROVIDER_ID, key)
        except Exception:  # noqa: BLE001
            return RecommendedAiSetupResult(
                ok=False,
                user_message="凭据保存失败，请检查 Windows 凭据管理器后重试。",
                persisted=False,
                credential_configured=bool(previous),
                provider_enabled=previous_enabled,
                cloud_enabled=previous_cloud,
                provider_eligible=False,
                selected_provider_id=CANONICAL_PROVIDER_ID,
                connection_status="unconfigured",
                analysis_mode=_read_setting(session, ANALYSIS_MODE_KEY, None),
                blockers=["credential_store_unavailable"],
                error_code="CREDENTIAL_STORE_UNAVAILABLE",
                readiness_reasons=["凭据保存失败"],
            )
        temporary_key = True
        row.credential_reference = f"keyring:{CANONICAL_PROVIDER_ID}"
        session.commit()

    # Temporarily enable provider + cloud so model validation can reach the endpoint.
    # Restored on non-persist or failure. Does not claim analysis readiness.
    row.enabled = True
    row.disconnected = False
    session.commit()
    _save_setting(session, CLOUD_KEY, True)
    apply_provider_runtime(gateway.get(CANONICAL_PROVIDER_ID), session, store)

    probe_fn = model_probe or _default_model_probe
    try:
        model_result = probe_fn(
            session=session,
            gateway=gateway,
            store=store,
            model_name=row.plus_model or preset_model,
        )
    except Exception as exc:  # noqa: BLE001
        model_result = {
            "ok": False,
            "error_code": "CONNECTION_TEST_FAILED",
            "detail": type(exc).__name__,
        }

    # Optional transport snapshot for diagnostics only (never drives success copy).
    transport: dict | None = None
    if transport_probe is not None:
        try:
            transport = _probe_transport(
                session=session,
                gateway=gateway,
                store=store,
                transport_probe=transport_probe,
            )
        except Exception:  # noqa: BLE001
            transport = {"overall_status": "failed", "error_code": "TRANSPORT_FAILED"}

    if not model_result.get("ok"):
        if temporary_key:
            _restore_credential(store, CANONICAL_PROVIDER_ID, previous)
            if previous is None:
                row.credential_reference = None
        row.enabled = previous_enabled
        row.disconnected = previous_disconnected
        session.commit()
        _save_setting(session, CLOUD_KEY, previous_cloud)
        error_code = str(model_result.get("error_code") or "CREDENTIAL_INVALID")
        http_status = model_result.get("http_status")
        error_category = model_result.get("error_category")
        retryable = model_result.get("retryable")
        if isinstance(http_status, int):
            http_status_i = http_status
        else:
            http_status_i = None
        if error_code in {"RATE_LIMITED", "PROVIDER_RATE_LIMITED"} or http_status_i == 429:
            error_code = "RATE_LIMITED"
            error_category = "rate_limited"
            retryable = True if retryable is None else bool(retryable)
            http_status_i = http_status_i or 429
            config_complete = bool(previous and previous_enabled and previous_cloud)
            if config_complete:
                user_message = (
                    "AI 服务配置已完成；Provider 已启用。"
                    "模型请求受到服务商限流（HTTP 429，error_category=rate_limited，retryable=true）。"
                    "请稍后重试；此错误不等于云端未开启或 Provider 未启用。"
                )
            else:
                user_message = (
                    "模型请求受到服务商限流（HTTP 429，error_category=rate_limited，retryable=true）。"
                    "请稍后重试；此错误与云端开关/Provider 启用状态无关。"
                )
            _record_probe_snapshot(
                session,
                store,
                ok=False,
                model_name=row.plus_model or preset_model,
                failure_category="RATE_LIMITED",
                failure_message="请求受到服务商限流",
            )
            return _attach_connection_ui(
                session,
                store,
                RecommendedAiSetupResult(
                ok=False,
                user_message=user_message,
                persisted=False,
                credential_configured=bool(previous),
                provider_enabled=previous_enabled,
                cloud_enabled=previous_cloud,
                provider_eligible=False,
                selected_provider_id=CANONICAL_PROVIDER_ID,
                connection_status="rate_limited",
                analysis_mode=_read_setting(session, ANALYSIS_MODE_KEY, None),
                blockers=["rate_limited"],
                error_code=error_code,
                raw_diagnostic={"model": model_result, "transport": transport},
                model_validated=False,
                analysis_ready=False,
                readiness_reasons=[blocker_label("RATE_LIMITED")],
                http_status=http_status_i,
                error_category=error_category,
                retryable=bool(retryable),
                ),
            )
        _record_probe_snapshot(
            session,
            store,
            ok=False,
            model_name=row.plus_model or preset_model,
            failure_category=error_code,
            failure_message=str(model_result.get("detail") or "模型服务验证失败"),
        )
        return _attach_connection_ui(
            session,
            store,
            RecommendedAiSetupResult(
            ok=False,
            user_message=(
                "模型服务验证失败\n"
                f"{blocker_guidance(error_code, model=preset_model)}"
            ),
            persisted=False,
            credential_configured=bool(previous),
            provider_enabled=previous_enabled,
            cloud_enabled=previous_cloud,
            provider_eligible=False,
            selected_provider_id=CANONICAL_PROVIDER_ID,
            connection_status="disconnected",
            analysis_mode=_read_setting(session, ANALYSIS_MODE_KEY, None),
            blockers=["connection_test_failed"],
            error_code=error_code,
            raw_diagnostic={"model": model_result, "transport": transport},
            model_validated=False,
            analysis_ready=False,
            readiness_reasons=[blocker_label(error_code)],
            http_status=http_status_i,
            error_category=str(error_category) if error_category else None,
            retryable=bool(retryable) if retryable is not None else None,
            ),
        )

    if not persist:
        # Model validation succeeded; do not leave temporary key / enablements.
        if temporary_key:
            _restore_credential(store, CANONICAL_PROVIDER_ID, previous)
            if previous is None:
                row.credential_reference = None
        row.enabled = previous_enabled
        row.disconnected = previous_disconnected
        session.commit()
        _save_setting(session, CLOUD_KEY, previous_cloud)
        # Persist snapshot only when the durable credential was the one probed.
        if not temporary_key and previous:
            _record_probe_snapshot(
                session,
                store,
                ok=True,
                model_name=str(model_result.get("model") or row.plus_model or preset_model),
            )
        return _attach_connection_ui(
            session,
            store,
            RecommendedAiSetupResult(
            ok=True,
            user_message="模型服务验证成功。",
            persisted=False,
            credential_configured=bool(previous),
            provider_enabled=previous_enabled,
            cloud_enabled=previous_cloud,
            provider_eligible=False,
            selected_provider_id=CANONICAL_PROVIDER_ID,
            connection_status="tested",
            analysis_mode=_read_setting(session, ANALYSIS_MODE_KEY, None),
            blockers=[],
            raw_diagnostic={"model": model_result, "transport": transport},
            model_validated=True,
            analysis_ready=False,
            readiness_reasons=["API Key 尚未保存"] if temporary_key else [],
            ),
        )

    # Persist full ordinary configuration atomically.
    try:
        if key is not None:
            # Re-set to confirm durable write after successful validation.
            store.set(CANONICAL_PROVIDER_ID, key)
        reloaded = store.get(CANONICAL_PROVIDER_ID)
        if not reloaded:
            raise RuntimeError("credential reload failed")
    except Exception:  # noqa: BLE001
        if temporary_key:
            _restore_credential(store, CANONICAL_PROVIDER_ID, previous)
        row.enabled = previous_enabled
        row.disconnected = previous_disconnected
        session.commit()
        _save_setting(session, CLOUD_KEY, previous_cloud)
        return RecommendedAiSetupResult(
            ok=False,
            user_message="凭据保存失败，请检查 Windows 凭据管理器后重试。",
            persisted=False,
            credential_configured=bool(previous),
            provider_enabled=previous_enabled,
            cloud_enabled=previous_cloud,
            provider_eligible=False,
            selected_provider_id=CANONICAL_PROVIDER_ID,
            connection_status="unconfigured",
            analysis_mode=_read_setting(session, ANALYSIS_MODE_KEY, None),
            blockers=["credential_store_unavailable"],
            error_code="CREDENTIAL_STORE_UNAVAILABLE",
            model_validated=True,
            analysis_ready=False,
            readiness_reasons=["凭据保存失败"],
        )

    _apply_analysis_mode(session, row, analysis_mode)
    row.enabled = True
    row.disconnected = False
    row.allow_auto_route = False
    row.credential_reference = f"keyring:{CANONICAL_PROVIDER_ID}"
    row.updated_at = datetime.now(timezone.utc)
    session.commit()

    _save_setting(session, CLOUD_KEY, True)
    _save_setting(session, CLOUD_BODY_CONSENT_KEY, True)

    ensure_aliyun_provider_configuration(
        session, CANONICAL_PROVIDER_ID, create_if_missing=False
    )
    row = (
        session.query(ProviderConfiguration)
        .filter_by(provider_name=CANONICAL_PROVIDER_ID)
        .one()
    )
    row.enabled = True
    row.disconnected = False
    session.commit()

    eligible, blockers, credential, enabled, cloud_enabled, connection = _eligibility_snapshot(
        session, store, gateway
    )
    model = row.plus_model or preset_model
    _record_probe_snapshot(
        session,
        store,
        ok=True,
        model_name=str(model_result.get("model") or model),
    )
    analysis_ready = bool(credential and enabled and cloud_enabled and eligible)
    consent = bool(_read_setting(session, CLOUD_BODY_CONSENT_KEY, False))
    if not analysis_ready or not consent:
        primary = blockers[0] if blockers else ("cloud_consent_required" if not consent else "SETUP_INCOMPLETE")
        return _attach_connection_ui(
            session,
            store,
            RecommendedAiSetupResult(
            ok=False,
            user_message="模型服务验证成功。",
            persisted=True,
            credential_configured=credential,
            provider_enabled=enabled,
            cloud_enabled=cloud_enabled,
            provider_eligible=eligible,
            selected_provider_id=CANONICAL_PROVIDER_ID,
            connection_status=connection,
            analysis_mode=analysis_mode,
            blockers=blockers,
            error_code=primary.upper() if primary.islower() else primary,
            raw_diagnostic={"model": model_result, "transport": transport},
            model_validated=True,
            analysis_ready=False,
            readiness_reasons=_readiness_reasons(blockers, model=model),
            ),
        )

    return _attach_connection_ui(
        session,
        store,
        RecommendedAiSetupResult(
        ok=True,
        user_message="模型服务验证成功。",
        persisted=True,
        credential_configured=True,
        provider_enabled=True,
        cloud_enabled=True,
        provider_eligible=True,
        selected_provider_id=CANONICAL_PROVIDER_ID,
        connection_status="connected",
        analysis_mode=analysis_mode,
        blockers=[],
        raw_diagnostic={"model": model_result, "transport": transport},
        model_validated=True,
        analysis_ready=True,
        readiness_reasons=[],
        ),
    )


def repair_recommended_qwen(
    *,
    session: Session,
    store: CredentialStore,
    gateway: ModelGateway,
    cloud_body_consent: bool | None,
) -> RecommendedAiSetupResult:
    """Repair incomplete setups from older wizards without deleting credentials."""
    status = get_recommended_qwen_status(session, store, gateway)
    if not status.credential_configured:
        return RecommendedAiSetupResult(
            ok=False,
            user_message="尚未配置 API Key，请先完成 AI 服务配置。",
            persisted=False,
            credential_configured=False,
            provider_enabled=status.provider_enabled,
            cloud_enabled=status.cloud_enabled,
            provider_eligible=False,
            selected_provider_id=CANONICAL_PROVIDER_ID,
            connection_status=status.connection_status,
            analysis_mode=status.analysis_mode,
            blockers=["credential_missing"],
            error_code="CREDENTIAL_MISSING",
            readiness_reasons=[blocker_label("credential_missing")],
        )

    row = _ensure_canonical_provider(session)
    row.enabled = True
    row.disconnected = False
    session.commit()

    consent_stored = bool(_read_setting(session, CLOUD_BODY_CONSENT_KEY, False))
    consent = True if cloud_body_consent is True else consent_stored
    if not status.cloud_enabled:
        if not consent:
            return RecommendedAiSetupResult(
                ok=False,
                user_message="检测到 AI 凭据已保存，但云端模型服务尚未开启。请确认允许发送章节正文后再修复。",
                persisted=False,
                credential_configured=True,
                provider_enabled=True,
                cloud_enabled=False,
                provider_eligible=False,
                selected_provider_id=CANONICAL_PROVIDER_ID,
                connection_status="partial",
                analysis_mode=status.analysis_mode,
                blockers=["cloud_master_switch_off"],
                needs_cloud_consent=True,
                error_code="CLOUD_CONSENT_REQUIRED",
                model_validated=True,
                analysis_ready=False,
                readiness_reasons=[blocker_label("cloud_master_switch_off")],
            )
        _save_setting(session, CLOUD_KEY, True)
        _save_setting(session, CLOUD_BODY_CONSENT_KEY, True)

    mode = status.analysis_mode if status.analysis_mode in ANALYSIS_MODE_PRESETS else "BALANCED"
    _apply_analysis_mode(session, row, mode)  # type: ignore[arg-type]
    row.enabled = True
    row.disconnected = False
    session.commit()

    return get_recommended_qwen_status(session, store, gateway)
