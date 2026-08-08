"""Bootstrap ProviderConfiguration endpoint fields for cloud providers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import ProviderConfiguration
from app.services.aliyun_endpoint import (
    CN_BEIJING,
    is_disabled_sentinel_url,
    resolve_aliyun_compatible_base_url,
)
from app.services.provider_pricing import (
    DEEPSEEK_BASE_URL,
    DEEPSEEK_DEFAULT_MODEL,
    DEEPSEEK_PROVIDER,
)

_ALIYUN_FAMILY = ("aliyun_qwen_plus", "aliyun_qwen_max", "aliyun_qwen_flash")


def is_aliyun_cloud_provider(provider_name: str) -> bool:
    return provider_name in _ALIYUN_FAMILY


def is_deepseek_provider(provider_name: str) -> bool:
    return str(provider_name or "").strip() == DEEPSEEK_PROVIDER


def ensure_aliyun_provider_configuration(
    session: Session,
    provider_name: str,
    *,
    settings: Settings | None = None,
    create_if_missing: bool = False,
) -> ProviderConfiguration | None:
    """Fill missing Aliyun endpoint/config defaults on an existing (or new) row.

    Allowed fields only: provider identity, model mapping, region, base_url,
    timeout, retry, auto_route=false, enabled state (unchanged unless creating).

    Does not touch books, runs, scenes, journeys, or credentials.
    """
    if not is_aliyun_cloud_provider(provider_name):
        return None

    cfg = settings or get_settings()
    row = (
        session.query(ProviderConfiguration)
        .filter_by(provider_name=provider_name)
        .one_or_none()
    )
    if row is None:
        if not create_if_missing:
            return None
        row = ProviderConfiguration(provider_name=provider_name)
        session.add(row)

    changed = False

    if not (row.display_name or "").strip():
        row.display_name = "阿里云百炼"
        changed = True

    if not (row.region or "").strip():
        row.region = CN_BEIJING
        changed = True

    if not (row.plus_model or "").strip():
        row.plus_model = cfg.aliyun_plus_model or "qwen3.7-plus"
        changed = True
    if not (row.max_model or "").strip():
        row.max_model = cfg.aliyun_max_model or "qwen3.7-max"
        changed = True
    if not (row.flash_model or "").strip():
        row.flash_model = cfg.aliyun_flash_model or "qwen3.6-flash"
        changed = True

    if not row.timeout_seconds:
        row.timeout_seconds = int(cfg.aliyun_timeout_seconds or 300)
        changed = True
    if not row.max_retries:
        row.max_retries = int(cfg.aliyun_max_retries or 3)
        changed = True

    # Product policy: never silently enable auto-route on bootstrap.
    if row.allow_auto_route:
        row.allow_auto_route = False
        changed = True

    resolved = resolve_aliyun_compatible_base_url(
        base_url=row.base_url,
        workspace_id=row.workspace_id,
        region=row.region,
        settings=cfg,
        allow_region_public_default=True,
    )
    if resolved and (
        not (row.base_url or "").strip() or is_disabled_sentinel_url(row.base_url)
    ):
        row.base_url = resolved
        changed = True

    if changed:
        row.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(row)
    return row


def ensure_deepseek_provider_configuration(
    session: Session,
    *,
    settings: Settings | None = None,
    create_if_missing: bool = False,
) -> ProviderConfiguration | None:
    """Fill DeepSeek ProviderConfiguration defaults (independent of Aliyun)."""
    cfg = settings or get_settings()
    row = (
        session.query(ProviderConfiguration)
        .filter_by(provider_name=DEEPSEEK_PROVIDER)
        .one_or_none()
    )
    if row is None:
        if not create_if_missing:
            return None
        row = ProviderConfiguration(provider_name=DEEPSEEK_PROVIDER)
        session.add(row)

    changed = False
    if not (row.display_name or "").strip():
        row.display_name = "深度求索/DeepSeek"
        changed = True
    if not (row.base_url or "").strip() or is_disabled_sentinel_url(row.base_url):
        row.base_url = (cfg.deepseek_base_url or DEEPSEEK_BASE_URL).rstrip("/")
        changed = True
    if not (row.plus_model or "").strip() or row.plus_model in {
        "qwen3.7-plus",
        "deepseek-chat",
        "deepseek-reasoner",
    }:
        # plus_model stores the selected DeepSeek model (flash default).
        row.plus_model = cfg.deepseek_model or DEEPSEEK_DEFAULT_MODEL
        changed = True
    if not row.timeout_seconds:
        row.timeout_seconds = int(cfg.deepseek_timeout_seconds or 300)
        changed = True
    if not row.max_retries:
        row.max_retries = int(cfg.deepseek_max_retries or 3)
        changed = True
    if row.allow_auto_route:
        row.allow_auto_route = False
        changed = True

    if changed:
        row.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(row)
    return row
