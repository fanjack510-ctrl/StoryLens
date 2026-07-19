"""Aliyun Bailian OpenAI-compatible endpoint resolution (shared path).

Single resolution order used by:
- model gateway registry bootstrap
- ProviderConfiguration runtime overlay / first-enable bootstrap
- certification canary seed (after reading a persisted base_url)

Priority:
1. Explicit base_url (developer override or already persisted)
2. STORYLENS_ALIYUN_BASE_URL
3. Derive from workspace_id (row or STORYLENS_ALIYUN_WORKSPACE_ID)
   → https://{workspace}.{region}.maas.aliyuncs.com/compatible-mode/v1
4. Region public default for cn-beijing (documented Aliyun OpenAI-compatible endpoint;
   workspace-dedicated MaaS URL remains preferred when workspace_id is known)

Never invents provider-specific forks for Human UAT.
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.core.config import Settings, get_settings

CN_BEIJING = "cn-beijing"
COMPATIBLE_MODE_PATH = "/compatible-mode/v1"

# Documented Beijing public OpenAI-compatible endpoint (Model Studio).
# Aliyun still supports this host; workspace MaaS URL is preferred when known.
CN_BEIJING_PUBLIC_COMPATIBLE_BASE_URL = (
    f"https://dashscope.aliyuncs.com{COMPATIBLE_MODE_PATH}"
)

_DISABLED_SENTINEL_HOST = "disabled.invalid"


def is_disabled_sentinel_url(base_url: str | None) -> bool:
    if not base_url:
        return True
    host = (urlparse(base_url).hostname or "").lower()
    return host == _DISABLED_SENTINEL_HOST or not host


def derive_maas_compatible_base_url(
    workspace_id: str,
    *,
    region: str = CN_BEIJING,
) -> str:
    """Same formula as docs/12 and historical registry bootstrap."""
    ws = (workspace_id or "").strip()
    if not ws:
        raise ValueError("workspace_id required to derive MaaS base_url")
    reg = (region or CN_BEIJING).strip() or CN_BEIJING
    return f"https://{ws}.{reg}.maas.aliyuncs.com{COMPATIBLE_MODE_PATH}"


def region_public_compatible_base_url(region: str | None = None) -> str:
    """Public (non-workspace) OpenAI-compatible endpoint for a region."""
    reg = (region or CN_BEIJING).strip() or CN_BEIJING
    if reg == CN_BEIJING:
        return CN_BEIJING_PUBLIC_COMPATIBLE_BASE_URL
    return ""


def resolve_aliyun_compatible_base_url(
    *,
    base_url: str | None = None,
    workspace_id: str | None = None,
    region: str | None = None,
    settings: Settings | None = None,
    allow_region_public_default: bool = True,
) -> str:
    """Resolve Aliyun OpenAI-compatible base_url without secrets.

    Returns empty string only when no source applies (should not happen for
    cn-beijing when allow_region_public_default=True).
    """
    explicit = (base_url or "").strip().rstrip("/")
    if explicit and not is_disabled_sentinel_url(explicit):
        return explicit

    cfg = settings or get_settings()
    env_url = (cfg.aliyun_base_url or "").strip().rstrip("/")
    if env_url and not is_disabled_sentinel_url(env_url):
        return env_url

    reg = (region or CN_BEIJING).strip() or CN_BEIJING
    ws = (workspace_id or cfg.aliyun_workspace_id or "").strip()
    if ws:
        return derive_maas_compatible_base_url(ws, region=reg)

    if allow_region_public_default:
        return region_public_compatible_base_url(reg)

    return ""


def endpoint_host(base_url: str | None) -> str | None:
    if not base_url:
        return None
    return urlparse(base_url).hostname
