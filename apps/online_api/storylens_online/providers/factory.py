from __future__ import annotations

import httpx

from storylens_online.config import OnlineSettings
from storylens_online.providers.aliyun_bailian import AliyunBailianProvider
from storylens_online.providers.base import ProviderRequestError


def create_phase2b1_provider(
    settings: OnlineSettings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AliyunBailianProvider:
    """Create the fixed worker provider after fail-closed configuration checks."""

    if (
        not settings.phase2b1_enabled
        or settings.phase2b1_chat_completions_url is None
        or settings.phase2b1_api_key_file is None
    ):
        raise ProviderRequestError(
            error_code="PROVIDER_CONFIGURATION_INVALID",
            http_request_sent=False,
        )
    return AliyunBailianProvider(
        chat_completions_url=settings.phase2b1_chat_completions_url,
        api_key_file=settings.phase2b1_api_key_file,
        timeout_seconds=settings.phase2b1_request_timeout_seconds,
        transport=transport,
    )
