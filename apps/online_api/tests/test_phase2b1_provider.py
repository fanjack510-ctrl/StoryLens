from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError
from storylens_online.config import OnlineSettings
from storylens_online.providers.aliyun_bailian import (
    MODEL_NAME,
    AliyunBailianProvider,
    validate_chat_completions_url,
)
from storylens_online.providers.base import ModelRequest, ProviderRequestError
from storylens_online.providers.factory import create_phase2b1_provider

VALID_URL = "https://workspace-123.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions"
FAKE_API_KEY = "FAKE_PHASE2B1_KEY_FOR_TESTS_ONLY"


def _request() -> ModelRequest:
    return ModelRequest(
        messages=[{"role": "user", "content": "synthetic test input"}],
        response_schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
        max_completion_tokens=2_048,
    )


def _provider(tmp_path, handler) -> AliyunBailianProvider:
    key_file = tmp_path / "aliyun.key"
    key_file.write_text(FAKE_API_KEY + "\n", encoding="utf-8")
    return AliyunBailianProvider(
        chat_completions_url=VALID_URL,
        api_key_file=key_file,
        timeout_seconds=10,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://workspace-123.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions",
        "https://workspace-123.cn-beijing.maas.aliyuncs.com.evil.invalid/compatible-mode/v1/chat/completions",
        "https://one.two.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions",
        "https://user@workspace-123.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions",
        "https://workspace-123.cn-beijing.maas.aliyuncs.com:443/compatible-mode/v1/chat/completions",
        "https://workspace-123.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        VALID_URL + "/",
        VALID_URL + "?search=true",
        VALID_URL + "#fragment",
    ],
)
def test_endpoint_validator_fails_closed(url: str) -> None:
    with pytest.raises(ValueError, match="approved Aliyun Beijing"):
        validate_chat_completions_url(url)


def test_phase2b1_settings_defaults_are_closed_and_pricing_is_decimal() -> None:
    settings = OnlineSettings(
        database_url="postgresql+psycopg://storylens@postgres/storylens_online",
        frontend_origin="https://storylens.example.invalid",
    )

    assert settings.phase2b1_enabled is False
    assert settings.phase2b1_allowlisted_user_ids == frozenset()
    assert settings.phase2b1_provider == "aliyun_bailian"
    assert settings.phase2b1_model == MODEL_NAME
    assert settings.phase2b1_input_per_million_cny == Decimal(2)
    assert settings.phase2b1_cached_per_million_cny == Decimal("0.4")
    assert settings.phase2b1_output_per_million_cny == Decimal(8)
    assert settings.phase2b1_cost_cap_cny == Decimal("0.35")


def test_phase2b1_allowlist_is_parsed_and_validated() -> None:
    settings = OnlineSettings(
        database_url="postgresql+psycopg://storylens@postgres/storylens_online",
        frontend_origin="https://storylens.example.invalid",
        phase2b1_allowlisted_user_ids_csv="user_1, user-2,user_1",
    )
    assert settings.phase2b1_allowlisted_user_ids == frozenset({"user_1", "user-2"})

    with pytest.raises(ValidationError, match="invalid user identifier"):
        OnlineSettings(
            database_url="postgresql+psycopg://storylens@postgres/storylens_online",
            frontend_origin="https://storylens.example.invalid",
            phase2b1_allowlisted_user_ids_csv="user-1,contains whitespace",
        )


def test_enabled_request_budget_must_fit_inside_worker_lease() -> None:
    with pytest.raises(ValidationError, match="remain below the worker lease"):
        OnlineSettings(
            database_url="postgresql+psycopg://storylens@postgres/storylens_online",
            frontend_origin="https://storylens.example.invalid",
            phase2b1_enabled=True,
            worker_lease_seconds=240,
        )


@pytest.mark.asyncio
async def test_payload_is_fixed_and_usage_is_parsed(tmp_path) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test-123",
                "model": MODEL_NAME,
                "choices": [
                    {
                        "message": {"content": '{"summary":"ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 125,
                    "completion_tokens": 25,
                    "total_tokens": 150,
                    "prompt_tokens_details": {"cached_tokens": 40},
                },
            },
        )

    response = await _provider(tmp_path, handler).generate(_request())

    assert captured["url"] == VALID_URL
    assert captured["authorization"] == f"Bearer {FAKE_API_KEY}"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body == {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": "synthetic test input"}],
        "enable_thinking": False,
        "enable_search": False,
        "stream": False,
        "max_completion_tokens": 2_048,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "storylens_phase2b1_result",
                "strict": True,
                "schema": _request().response_schema,
            },
        },
    }
    assert body["enable_search"] is False
    assert "cache" not in str(body).lower()
    assert "session" not in str(body).lower()
    assert response.model == MODEL_NAME
    assert response.provider_request_id == "chatcmpl-test-123"
    assert response.usage.model_dump() == {
        "input_tokens": 125,
        "output_tokens": 25,
        "total_tokens": 150,
        "cached_tokens": 40,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "error_code", "request_sent"),
    [
        (httpx.ConnectError("fake connect failure"), "PROVIDER_CONNECT_ERROR", False),
        (httpx.ReadTimeout("fake post-send timeout"), "PROVIDER_READ_TIMEOUT", True),
        (httpx.ReadError("fake interrupted response"), "PROVIDER_CONNECTION_INTERRUPTED", True),
    ],
)
async def test_transport_errors_are_classified_without_source_details(
    tmp_path,
    failure: httpx.RequestError,
    error_code: str,
    request_sent: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        failure.request = request
        raise failure

    with pytest.raises(ProviderRequestError) as raised:
        await _provider(tmp_path, handler).generate(_request())

    assert raised.value.error_code == error_code
    assert raised.value.http_request_sent is request_sent
    assert "fake" not in str(raised.value).lower()
    assert FAKE_API_KEY not in str(raised.value.as_safe_dict())
    assert "synthetic test input" not in str(raised.value.as_safe_dict())


@pytest.mark.asyncio
async def test_429_preserves_safe_retry_metadata_and_usage(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"retry-after": "3", "x-request-id": "req-rate-limit"},
            json={
                "error": {"message": "unsafe provider detail must be discarded"},
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 0,
                    "total_tokens": 10,
                },
            },
        )

    with pytest.raises(ProviderRequestError) as raised:
        await _provider(tmp_path, handler).generate(_request())

    error = raised.value
    assert error.error_code == "PROVIDER_RATE_LIMITED"
    assert error.http_request_sent is True
    assert error.http_status_code == 429
    assert error.provider_request_id == "req-rate-limit"
    assert error.retry_after_seconds == 3
    assert error.usage is not None and error.usage.total_tokens == 10
    assert "unsafe provider detail" not in str(error.as_safe_dict())


@pytest.mark.asyncio
async def test_5xx_is_distinct_and_not_declared_retryable_by_provider(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, headers={"x-request-id": "req-server"}, json={})

    with pytest.raises(ProviderRequestError) as raised:
        await _provider(tmp_path, handler).generate(_request())

    assert raised.value.error_code == "PROVIDER_SERVER_ERROR"
    assert raised.value.http_request_sent is True
    assert raised.value.http_status_code == 503


@pytest.mark.asyncio
async def test_missing_usage_fails_closed_for_accounting(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-request-id": "req-no-usage"},
            json={
                "model": MODEL_NAME,
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            },
        )

    with pytest.raises(ProviderRequestError) as raised:
        await _provider(tmp_path, handler).generate(_request())

    assert raised.value.error_code == "PROVIDER_RESPONSE_INVALID"
    assert raised.value.http_request_sent is True
    assert raised.value.provider_request_id == "req-no-usage"
    assert raised.value.usage is None


@pytest.mark.asyncio
async def test_missing_total_tokens_fails_closed_for_accounting(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-request-id": "req-no-total"},
            json={
                "model": MODEL_NAME,
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            },
        )

    with pytest.raises(ProviderRequestError) as raised:
        await _provider(tmp_path, handler).generate(_request())

    assert raised.value.error_code == "PROVIDER_RESPONSE_INVALID"
    assert raised.value.usage is None


@pytest.mark.asyncio
async def test_unexpected_response_model_fails_with_usage_preserved(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-request-id": "req-wrong-model"},
            json={
                "model": "unexpected-model",
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 13,
                },
            },
        )

    with pytest.raises(ProviderRequestError) as raised:
        await _provider(tmp_path, handler).generate(_request())

    error = raised.value
    assert error.error_code == "PROVIDER_RESPONSE_INVALID"
    assert error.provider_request_id == "req-wrong-model"
    assert error.usage is not None
    assert error.usage.total_tokens == 13


@pytest.mark.asyncio
async def test_secret_file_is_required_and_never_returned(tmp_path) -> None:
    missing = tmp_path / "missing.key"
    provider = AliyunBailianProvider(
        chat_completions_url=VALID_URL,
        api_key_file=missing,
        timeout_seconds=10,
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    with pytest.raises(ProviderRequestError) as raised:
        await provider.generate(_request())
    assert raised.value.error_code == "PROVIDER_SECRET_UNAVAILABLE"
    assert raised.value.http_request_sent is False
    assert str(missing) not in str(raised.value.as_safe_dict())


def test_factory_fails_closed_until_worker_configuration_is_complete(tmp_path) -> None:
    settings = OnlineSettings(
        database_url="postgresql+psycopg://storylens@postgres/storylens_online",
        frontend_origin="https://storylens.example.invalid",
    )
    with pytest.raises(ProviderRequestError, match="configuration is invalid"):
        create_phase2b1_provider(settings)

    key_file = tmp_path / "key"
    key_file.write_text(FAKE_API_KEY, encoding="utf-8")
    configured = OnlineSettings(
        database_url="postgresql+psycopg://storylens@postgres/storylens_online",
        frontend_origin="https://storylens.example.invalid",
        phase2b1_enabled=True,
        phase2b1_chat_completions_url=VALID_URL,
        phase2b1_api_key_file=str(key_file),
    )
    assert create_phase2b1_provider(configured).model == MODEL_NAME
