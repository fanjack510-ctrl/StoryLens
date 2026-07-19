"""Overlay ProviderConfiguration + credentials onto runtime gateway providers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ApplicationSetting, ProviderConfiguration
from app.model_gateway.base import ModelProvider
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.services.aliyun_endpoint import resolve_aliyun_compatible_base_url
from app.services.credentials.base import CredentialStore


def cloud_master_enabled(session: Session) -> bool:
    row = session.get(ApplicationSetting, "cloud_enabled")
    if row is None:
        # Deprecated env flag maps only to cloud master switch, never per-provider health.
        return bool(get_settings().aliyun_enabled)
    try:
        import json

        return bool(json.loads(row.value_json))
    except Exception:
        return False


def apply_provider_runtime(
    provider: ModelProvider,
    session: Session,
    store: CredentialStore | None = None,
) -> ModelProvider:
    """Mutate cloud OpenAI-compatible providers to match ProviderConfiguration.

    Fact source for per-provider enablement: ProviderConfiguration.enabled.
    settings.aliyun_enabled is deprecated for per-provider health and only
    used as cloud-master fallback when ApplicationSetting is absent.
    """
    if not isinstance(provider, OpenAICompatibleProvider) or not provider.cloud:
        return provider
    row = (
        session.query(ProviderConfiguration)
        .filter_by(provider_name=provider.name)
        .one_or_none()
    )
    if row is None:
        # Do not invent a disabled row; keep registry bootstrap until user configures.
        provider.enabled = bool(provider.enabled)
        return provider
    provider.enabled = bool(row.enabled)
    resolved = resolve_aliyun_compatible_base_url(
        base_url=row.base_url,
        workspace_id=row.workspace_id,
        region=row.region,
        settings=get_settings(),
    )
    if resolved:
        provider.base_url = resolved
    if row.timeout_seconds:
        provider.timeout_seconds = int(row.timeout_seconds)
    model_by_name = {
        "aliyun_qwen_plus": row.plus_model,
        "aliyun_qwen_max": row.max_model,
        "aliyun_qwen_flash": row.flash_model,
    }
    configured_model = model_by_name.get(provider.name)
    if configured_model:
        provider.default_model = configured_model
    if store is not None and store.available():
        secret = store.get(provider.name)
        if secret:
            provider.api_key = secret
    return provider


def bind_gateway_runtime(
    gateway: ModelGateway,
    session: Session,
    store: CredentialStore | None = None,
) -> ModelGateway:
    for provider in gateway.providers():
        apply_provider_runtime(provider, session, store)
    return gateway
