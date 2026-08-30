from __future__ import annotations

import httpx

from storylens_online.config import OnlineSettings
from storylens_online.providers.base import ProviderRequestError
from storylens_online.providers.deepseek import DeepSeekProvider


def create_phase2b1_provider(
    settings: OnlineSettings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> DeepSeekProvider:
    """Create the fixed worker provider after fail-closed configuration checks."""

    if (
        not settings.phase2b1_enabled
        or settings.phase2b1_base_url is None
        or settings.phase2b1_api_key_file is None
    ):
        raise ProviderRequestError(
            error_code="PROVIDER_CONFIGURATION_INVALID",
            http_request_sent=False,
        )
    return DeepSeekProvider(
        base_url=settings.phase2b1_base_url,
        api_key_file=settings.phase2b1_api_key_file,
        timeout_seconds=settings.phase2b1_request_timeout_seconds,
        transport=transport,
    )
