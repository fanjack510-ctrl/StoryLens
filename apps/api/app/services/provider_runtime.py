"""Overlay ProviderConfiguration + credentials onto runtime gateway providers."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ApplicationSetting, ProviderConfiguration
from app.model_gateway.base import ModelProvider
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.services.aliyun_endpoint import resolve_aliyun_compatible_base_url
from app.services.credentials.base import CredentialStore
from app.services.provider_pricing import DEEPSEEK_BASE_URL, DEEPSEEK_DEFAULT_MODEL, DEEPSEEK_PROVIDER

ACTIVE_CLOUD_PROVIDER_KEY = "active_cloud_provider"
FORMAL_CLOUD_PROVIDERS = frozenset({"aliyun_qwen_plus", DEEPSEEK_PROVIDER})
DEFAULT_ACTIVE_CLOUD_PROVIDER = "aliyun_qwen_plus"


def cloud_master_enabled(session: Session) -> bool:
    row = session.get(ApplicationSetting, "cloud_enabled")
    if row is None:
        # Deprecated env flag maps only to cloud master switch, never per-provider health.
        return bool(get_settings().aliyun_enabled)
    try:
        return bool(json.loads(row.value_json))
    except Exception:
        return False


def get_active_cloud_provider(session: Session) -> str:
    """Return selected formal cloud provider; default aliyun without forced migration."""
    row = session.get(ApplicationSetting, ACTIVE_CLOUD_PROVIDER_KEY)
    if row is None:
        return DEFAULT_ACTIVE_CLOUD_PROVIDER
    try:
        value = json.loads(row.value_json)
    except Exception:
        value = row.value_json
    name = str(value or "").strip()
    if name in FORMAL_CLOUD_PROVIDERS:
        return name
    return DEFAULT_ACTIVE_CLOUD_PROVIDER


def set_active_cloud_provider(session: Session, provider_name: str) -> str:
    name = str(provider_name or "").strip()
    if name not in FORMAL_CLOUD_PROVIDERS:
        raise ValueError(f"unsupported active_cloud_provider: {provider_name}")
    row = session.get(ApplicationSetting, ACTIVE_CLOUD_PROVIDER_KEY)
    payload = json.dumps(name)
    if row is None:
        session.add(ApplicationSetting(key=ACTIVE_CLOUD_PROVIDER_KEY, value_json=payload))
    else:
        row.value_json = payload
    session.flush()
    return name


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

    is_deepseek = (
        provider.provider_family == "deepseek"
        or provider.name == DEEPSEEK_PROVIDER
    )
    if is_deepseek:
        # Must NOT apply Aliyun URL resolver to DeepSeek.
        base = (row.base_url or "").strip() or get_settings().deepseek_base_url or DEEPSEEK_BASE_URL
        provider.base_url = base.rstrip("/")
        if row.plus_model:
            provider.default_model = row.plus_model
        elif not provider.default_model:
            provider.default_model = get_settings().deepseek_model or DEEPSEEK_DEFAULT_MODEL
    else:
        resolved = resolve_aliyun_compatible_base_url(
            base_url=row.base_url,
            workspace_id=row.workspace_id,
            region=row.region,
            settings=get_settings(),
        )
        if resolved:
            provider.base_url = resolved
        model_by_name = {
            "aliyun_qwen_plus": row.plus_model,
            "aliyun_qwen_max": row.max_model,
            "aliyun_qwen_flash": row.flash_model,
        }
        configured_model = model_by_name.get(provider.name)
        if configured_model:
            provider.default_model = configured_model

    if row.timeout_seconds:
        provider.timeout_seconds = int(row.timeout_seconds)
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
