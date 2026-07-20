"""Atomic recommended Aliyun Bailian (Qwen) setup for ordinary users.

Wizard and Settings must share this path so credentials, ProviderConfiguration,
cloud master switch, and eligibility stay consistent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ApplicationSetting, ProviderConfiguration
from app.model_gateway.gateway import ModelGateway
from app.schemas.settings import CloudBudgetUpdate
from app.services.aliyun_endpoint import CN_BEIJING, resolve_aliyun_compatible_base_url
from app.services.credentials.base import CredentialStore
from app.services.provider_bootstrap import (
    ensure_aliyun_provider_configuration,
    is_aliyun_cloud_provider,
)
from app.services.provider_eligibility import evaluate_manual_boundary_candidate
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
    # Ordinary path uses explicit default provider selection; do not force auto-route.
    row.allow_auto_route = False
    row.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(row)
    return row


def _probe_connection(
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


def _connection_ok(transport: dict) -> bool:
    status = str(transport.get("overall_status") or "")
    return status in {"ok", "healthy"}


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
        pricing_path=Path("config/cloud_pricing.json"),
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
    ok = bool(credential and enabled and cloud_enabled and eligible)
    if ok:
        message = "已连接，可以开始分析"
    elif not credential:
        message = "尚未填写 API Key"
    elif not enabled:
        message = "API Key 已保存，但 AI 服务未启用"
    elif not cloud_enabled:
        message = "AI 服务已启用，但云端连接未开启"
    elif blockers:
        message = "配置尚未完成，暂时无法开始分析"
    else:
        message = "AI 服务状态未知"
    return RecommendedAiSetupResult(
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
) -> RecommendedAiSetupResult:
    """Test and optionally persist the official Bailian quick setup.

    When ``persist`` is False, only probes connectivity (may temporarily write
    the key, then restores the previous credential).
    On probe failure, never leaves a newly provided key in the store.
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
        )

    if persist and not cloud_body_consent:
        return RecommendedAiSetupResult(
            ok=False,
            user_message="请先确认可将章节正文发送至阿里云百炼。",
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
        )

    # Ensure provider row + public endpoint before probing.
    row = _ensure_canonical_provider(session)
    temporary_key = False
    if key is not None:
        store.set(CANONICAL_PROVIDER_ID, key)
        temporary_key = True
        row.credential_reference = f"keyring:{CANONICAL_PROVIDER_ID}"
        session.commit()

    try:
        transport = _probe_connection(
            session=session,
            gateway=gateway,
            store=store,
            transport_probe=transport_probe,
        )
    except Exception as exc:  # noqa: BLE001 — surface as user-facing failure
        if temporary_key:
            _restore_credential(store, CANONICAL_PROVIDER_ID, previous)
            if previous is None:
                row.credential_reference = None
                session.commit()
        return RecommendedAiSetupResult(
            ok=False,
            user_message="连接测试失败，请检查网络或 API Key。",
            persisted=False,
            credential_configured=bool(previous),
            provider_enabled=bool(row.enabled),
            cloud_enabled=bool(_read_setting(session, CLOUD_KEY, False)),
            provider_eligible=False,
            selected_provider_id=CANONICAL_PROVIDER_ID,
            connection_status="disconnected",
            analysis_mode=_read_setting(session, ANALYSIS_MODE_KEY, None),
            blockers=["connection_test_failed"],
            error_code="CONNECTION_TEST_FAILED",
            raw_diagnostic={"exception": type(exc).__name__},
        )

    if not _connection_ok(transport):
        if temporary_key:
            _restore_credential(store, CANONICAL_PROVIDER_ID, previous)
            if previous is None:
                row.credential_reference = None
                session.commit()
        eligible, blockers, credential, enabled, cloud_enabled, connection = _eligibility_snapshot(
            session, store, gateway
        )
        return RecommendedAiSetupResult(
            ok=False,
            user_message="连接测试失败，未更改原有 API Key。",
            persisted=False,
            credential_configured=credential,
            provider_enabled=enabled,
            cloud_enabled=cloud_enabled,
            provider_eligible=eligible,
            selected_provider_id=CANONICAL_PROVIDER_ID,
            connection_status=connection,
            analysis_mode=_read_setting(session, ANALYSIS_MODE_KEY, None),
            blockers=blockers or ["connection_test_failed"],
            error_code=str(transport.get("error_code") or "TRANSPORT_FAILED"),
            raw_diagnostic=transport,
        )

    if not persist:
        if temporary_key:
            _restore_credential(store, CANONICAL_PROVIDER_ID, previous)
            if previous is None:
                row.credential_reference = None
                session.commit()
        return RecommendedAiSetupResult(
            ok=True,
            user_message="连接测试成功（尚未保存配置）。",
            persisted=False,
            credential_configured=bool(previous),
            provider_enabled=bool(row.enabled),
            cloud_enabled=bool(_read_setting(session, CLOUD_KEY, False)),
            provider_eligible=False,
            selected_provider_id=CANONICAL_PROVIDER_ID,
            connection_status="tested",
            analysis_mode=_read_setting(session, ANALYSIS_MODE_KEY, None),
            blockers=[],
            raw_diagnostic=transport,
        )

    # Persist full ordinary configuration atomically.
    _apply_analysis_mode(session, row, analysis_mode)
    row.enabled = True
    row.disconnected = False
    row.allow_auto_route = False
    row.credential_reference = f"keyring:{CANONICAL_PROVIDER_ID}"
    row.updated_at = datetime.now(timezone.utc)
    session.commit()

    _save_setting(session, CLOUD_KEY, True)
    _save_setting(session, CLOUD_BODY_CONSENT_KEY, True)

    # Re-bootstrap endpoint fields without wiping intentional state.
    ensure_aliyun_provider_configuration(
        session, CANONICAL_PROVIDER_ID, create_if_missing=False
    )
    row = (
        session.query(ProviderConfiguration)
        .filter_by(provider_name=CANONICAL_PROVIDER_ID)
        .one()
    )
    # Bootstrap historically forced allow_auto_route=False; keep that product policy.
    row.enabled = True
    row.disconnected = False
    session.commit()

    eligible, blockers, credential, enabled, cloud_enabled, connection = _eligibility_snapshot(
        session, store, gateway
    )
    if not (credential and enabled and cloud_enabled and eligible):
        return RecommendedAiSetupResult(
            ok=False,
            user_message="连接测试成功，但配置保存后仍不可用于分析，请检查预算或定价设置。",
            persisted=True,
            credential_configured=credential,
            provider_enabled=enabled,
            cloud_enabled=cloud_enabled,
            provider_eligible=eligible,
            selected_provider_id=CANONICAL_PROVIDER_ID,
            connection_status=connection,
            analysis_mode=analysis_mode,
            blockers=blockers,
            error_code="SETUP_INCOMPLETE",
            raw_diagnostic=transport,
        )

    return RecommendedAiSetupResult(
        ok=True,
        user_message="保存成功，已连接，可以开始分析。",
        persisted=True,
        credential_configured=True,
        provider_enabled=True,
        cloud_enabled=True,
        provider_eligible=True,
        selected_provider_id=CANONICAL_PROVIDER_ID,
        connection_status="connected",
        analysis_mode=analysis_mode,
        blockers=[],
        raw_diagnostic=transport,
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
                user_message="检测到 AI 凭据已保存，但云端连接未开启。请确认允许发送章节正文后再修复。",
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
            )
        _save_setting(session, CLOUD_KEY, True)
        _save_setting(session, CLOUD_BODY_CONSENT_KEY, True)

    mode = status.analysis_mode if status.analysis_mode in ANALYSIS_MODE_PRESETS else "BALANCED"
    _apply_analysis_mode(session, row, mode)  # type: ignore[arg-type]
    row.enabled = True
    row.disconnected = False
    session.commit()

    return get_recommended_qwen_status(session, store, gateway)
