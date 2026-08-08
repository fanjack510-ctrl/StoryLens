"""Whole-Book active cloud provider resolution helpers (CHG-20260808-061)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProviderConfiguration
from app.services.credentials.keyring_store import KeyringCredentialStore
from app.services.provider_bootstrap import (
    ensure_aliyun_provider_configuration,
    ensure_deepseek_provider_configuration,
    is_deepseek_provider,
)
from app.services.provider_runtime import get_active_cloud_provider


def ensure_active_provider_row(session: Session, provider_name: str) -> ProviderConfiguration | None:
    name = str(provider_name or "").strip()
    if not name:
        return None
    if is_deepseek_provider(name):
        ensure_deepseek_provider_configuration(session, create_if_missing=True)
    elif name == "aliyun_qwen_plus" or name.startswith("aliyun_"):
        ensure_aliyun_provider_configuration(session, name, create_if_missing=True)
    return session.scalar(
        select(ProviderConfiguration).where(ProviderConfiguration.provider_name == name)
    )


def provider_credential_available(session: Session, row: ProviderConfiguration) -> bool:
    store = KeyringCredentialStore()
    if store.available():
        secret = store.get(row.provider_name)
        if secret:
            return True
    import os

    if is_deepseek_provider(row.provider_name):
        return bool(os.environ.get("STORYLENS_DEEPSEEK_API_KEY", "").strip())
    return bool(os.environ.get("STORYLENS_ALIYUN_API_KEY", "").strip())


def active_provider_availability(
    session: Session,
) -> tuple[ProviderConfiguration | None, str, list[str]]:
    """Return (row, active_name, blocking_reasons) for the selected cloud provider.

    Never silently substitutes another provider.
    """
    active = get_active_cloud_provider(session)
    row = ensure_active_provider_row(session, active)
    blockers: list[str] = []
    if row is None:
        blockers.append(f"当前服务商 {active} 尚未配置")
        return None, active, blockers
    if not bool(row.enabled) or bool(row.disconnected):
        blockers.append(f"当前服务商 {active} 未启用或已断开")
    if not provider_credential_available(session, row):
        blockers.append(f"当前服务商 {active} API Key 不可用")
    return row, active, blockers
