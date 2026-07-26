"""Native Overview Live Transport default timeout_seconds (CHG-20260726-012)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.model_gateway.base import ModelRequest, ModelResponse
from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.narrative_core.services.native_overview_live_transport import (
    AliyunNativeOverviewTransport,
)


class _FakeStore:
    def get(self, _name: str) -> str:
        return "test-key-not-real"


def _capture_provider(captured: list[OpenAICompatibleProvider], generate_captured: list[ModelRequest]):
    real_init = OpenAICompatibleProvider.__init__

    def _init(self: OpenAICompatibleProvider, *args: Any, **kwargs: Any) -> None:
        real_init(self, *args, **kwargs)
        captured.append(self)

    async def _generate(self: Any, request: ModelRequest) -> ModelResponse:
        generate_captured.append(request)
        return ModelResponse(
            text='{"contract_version":"1.0"}',
            model=request.model or "qwen3.7-plus",
            http_status_code=200,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            request_id="test-req",
            finish_reason="stop",
        )

    return _init, _generate


@pytest.fixture
def transport_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.narrative_core.services.native_overview_live_transport.get_credential_store",
        lambda: _FakeStore(),
    )
    monkeypatch.setattr(
        "app.services.aliyun_endpoint.resolve_aliyun_compatible_base_url",
        lambda **_kwargs: "https://example.invalid/v1",
    )
    monkeypatch.setattr(
        "app.services.cloud_pricing.estimate_cost",
        lambda *_a, **_k: (0.001, "CNY", "test"),
    )


def test_native_default_timeout_seconds_is_180():
    assert AliyunNativeOverviewTransport.timeout_seconds == 180
    assert AliyunNativeOverviewTransport().timeout_seconds == 180


def test_native_default_httpx_timeout_shape(transport_env, monkeypatch: pytest.MonkeyPatch):
    providers: list[OpenAICompatibleProvider] = []
    requests: list[ModelRequest] = []
    _init, _generate = _capture_provider(providers, requests)
    monkeypatch.setattr(OpenAICompatibleProvider, "__init__", _init)
    monkeypatch.setattr(OpenAICompatibleProvider, "generate", _generate)

    AliyunNativeOverviewTransport(model="qwen3.7-plus", max_auto_retries=0).request(
        "prompt-only", {"stage": "analyze_window"}
    )
    assert len(providers) == 1
    timeout = providers[0]._timeout()
    assert isinstance(timeout, httpx.Timeout)
    assert float(timeout.connect) == 30.0
    assert float(timeout.read) == 180.0
    assert float(timeout.write) == 180.0
    assert float(timeout.pool) == 30.0


def test_explicit_timeout_seconds_override_preserved(
    transport_env, monkeypatch: pytest.MonkeyPatch
):
    providers: list[OpenAICompatibleProvider] = []
    requests: list[ModelRequest] = []
    _init, _generate = _capture_provider(providers, requests)
    monkeypatch.setattr(OpenAICompatibleProvider, "__init__", _init)
    monkeypatch.setattr(OpenAICompatibleProvider, "generate", _generate)

    AliyunNativeOverviewTransport(
        model="qwen3.7-plus",
        timeout_seconds=60,
        max_auto_retries=0,
    ).request("prompt-only", {"stage": "analyze_window"})
    timeout = providers[0]._timeout()
    assert float(timeout.read) == 60.0
    assert float(timeout.write) == 60.0
    assert float(timeout.connect) == 30.0
    assert float(timeout.pool) == 30.0


def test_other_feature_timeouts_unaffected_by_native_180():
    from app.core.config import Settings

    assert AliyunNativeOverviewTransport.timeout_seconds == 180
    settings = Settings()
    assert settings.aliyun_timeout_seconds == 300
    assert settings.local_llama_timeout_seconds == 300

    from app.narrative_core.services import native_overview_smoke_fake_transport as fake

    fake_src = open(fake.__file__, encoding="utf-8").read()
    assert "timeout_seconds: int = 180" not in fake_src

    from app.services import recommended_ai_setup as setup

    setup_src = open(setup.__file__, encoding="utf-8").read()
    assert '"timeout_seconds": 300' in setup_src
    assert '"timeout_seconds": 180' in setup_src  # other preset, not Native Live default
    # Native Live default must not be wired through recommended_ai_setup.
    assert "AliyunNativeOverviewTransport" not in setup_src


def test_max_auto_retries_and_max_output_tokens_unchanged():
    t = AliyunNativeOverviewTransport()
    assert t.max_auto_retries == 1
    assert t.max_output_tokens == 8192
    assert t.timeout_seconds == 180
