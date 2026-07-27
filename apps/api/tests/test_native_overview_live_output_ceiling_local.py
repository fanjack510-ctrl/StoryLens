"""Native Overview Live Transport default max_output_tokens (CHG-20260726-011)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.model_gateway.base import ModelRequest, ModelResponse
from app.narrative_core.services.native_overview_live_transport import (
    AliyunNativeOverviewTransport,
)


class _FakeStore:
    def get(self, _name: str) -> str:
        return "test-key-not-real"


def _capture_generate(captured: list[ModelRequest]):
    async def _generate(self: Any, request: ModelRequest) -> ModelResponse:
        captured.append(request)
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

    return _generate


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


def test_default_max_output_tokens_is_8192(transport_env, monkeypatch: pytest.MonkeyPatch):
    captured: list[ModelRequest] = []
    monkeypatch.setattr(
        "app.model_gateway.providers.openai_compatible.OpenAICompatibleProvider.generate",
        _capture_generate(captured),
    )
    transport = AliyunNativeOverviewTransport(model="qwen3.7-plus", max_auto_retries=0)
    assert transport.max_output_tokens == 8192

    transport.request("prompt-only", {"stage": "analyze_window"})
    assert len(captured) == 1
    req = captured[0]
    assert req.max_output_tokens == 8192
    # OpenAI-compatible wire mapping uses max_tokens from max_output_tokens
    assert (req.max_output_tokens or req.max_tokens) == 8192
    assert req.temperature == 0.2
    assert req.response_format_mode == "json_object"
    assert req.enable_thinking is False


def test_explicit_max_output_tokens_override_preserved(
    transport_env, monkeypatch: pytest.MonkeyPatch
):
    captured: list[ModelRequest] = []
    monkeypatch.setattr(
        "app.model_gateway.providers.openai_compatible.OpenAICompatibleProvider.generate",
        _capture_generate(captured),
    )
    transport = AliyunNativeOverviewTransport(model="qwen3.7-plus", max_auto_retries=0)
    transport.request(
        "prompt-only",
        {"stage": "analyze_window", "max_output_tokens": 2048},
    )
    assert captured[0].max_output_tokens == 2048


def test_default_non_token_parameters_unchanged(transport_env, monkeypatch: pytest.MonkeyPatch):
    captured: list[ModelRequest] = []
    monkeypatch.setattr(
        "app.model_gateway.providers.openai_compatible.OpenAICompatibleProvider.generate",
        _capture_generate(captured),
    )
    AliyunNativeOverviewTransport(model="qwen3.7-plus", max_auto_retries=0).request(
        "x", {"stage": "analyze_window"}
    )
    req = captured[0]
    assert req.temperature == 0.2
    assert req.response_format_mode == "json_object"
    assert req.enable_thinking is False


def test_smoke_fake_unaffected_by_live_default(monkeypatch: pytest.MonkeyPatch):
    from app.narrative_core.services.native_overview_smoke_fake_transport import (
        is_native_overview_smoke_fake_enabled,
    )

    monkeypatch.delenv("STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE", raising=False)
    assert is_native_overview_smoke_fake_enabled() is False
    monkeypatch.setenv("STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE", "1")
    assert is_native_overview_smoke_fake_enabled() is True
    # Live default must remain independent of Fake gate.
    assert AliyunNativeOverviewTransport.max_output_tokens == 8192
    monkeypatch.delenv("STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE", raising=False)


def test_chapter_analysis_output_limit_not_tied_to_native_8192():
    """Scene/chapter structured output uses its own limiter, not Live Transport default."""
    from app.services import structured_output as so
    from app.services import recommended_ai_setup as setup

    assert AliyunNativeOverviewTransport.max_output_tokens == 8192
    text = open(so.__file__, encoding="utf-8").read()
    assert "AliyunNativeOverviewTransport" not in text
    setup_src = open(setup.__file__, encoding="utf-8").read()
    assert '"cloud_max_output_tokens_per_request": 4000' in setup_src
