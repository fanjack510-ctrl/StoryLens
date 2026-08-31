from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError
from storylens_online.config import OnlineSettings
from storylens_online.providers.base import ModelRequest, ProviderRequestError
from storylens_online.providers.deepseek import (
    BASE_URL,
    MODEL_NAME,
    DeepSeekProvider,
    validate_base_url,
)
from storylens_online.providers.factory import create_phase2b1_provider

FAKE_API_KEY = "FAKE_PHASE2B1_KEY_FOR_TESTS_ONLY"


def _request() -> ModelRequest:
    return ModelRequest(
        messages=[{"role": "user", "content": "synthetic JSON test input"}],
        max_completion_tokens=2_048,
    )


def _usage() -> dict[str, int]:
    return {
        "prompt_tokens": 125,
        "completion_tokens": 25,
        "total_tokens": 150,
        "prompt_cache_hit_tokens": 40,
        "prompt_cache_miss_tokens": 85,
    }


def _provider(tmp_path, handler) -> DeepSeekProvider:
    key_file = tmp_path / "deepseek.key"
    key_file.write_text(FAKE_API_KEY + "\n", encoding="utf-8")
    return DeepSeekProvider(
        base_url=BASE_URL,
        api_key_file=key_file,
        timeout_seconds=10,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://api.deepseek.com",
        "https://api.deepseek.com.evil.invalid",
        "https://user@api.deepseek.com",
        "https://api.deepseek.com:443",
        "https://api.deepseek.com/chat/completions",
        "https://api.deepseek.com?redirect=1",
        "https://api.deepseek.com#fragment",
    ],
)
def test_base_url_validator_fails_closed(url: str) -> None:
    with pytest.raises(ValueError, match="approved DeepSeek HTTPS origin"):
        validate_base_url(url)


def test_phase2b1_settings_defaults_are_closed_and_pricing_is_decimal() -> None:
    settings = OnlineSettings(
        database_url="postgresql+psycopg://storylens@postgres/storylens_online",
        frontend_origin="https://storylens.example.invalid",
    )

    assert settings.phase2b1_enabled is False
    assert settings.phase2b1_allowlisted_user_ids == frozenset()
    assert settings.phase2b1_provider == "deepseek"
    assert settings.phase2b1_model == MODEL_NAME
    assert settings.phase2b1_off_peak_cache_hit_usd == Decimal("0.007")
    assert settings.phase2b1_off_peak_cache_miss_usd == Decimal("0.22")
    assert settings.phase2b1_off_peak_output_usd == Decimal("0.66")
    assert settings.phase2b1_peak_cache_hit_usd == Decimal("0.014")
    assert settings.phase2b1_peak_cache_miss_usd == Decimal("0.44")
    assert settings.phase2b1_peak_output_usd == Decimal("1.32")
    assert settings.phase2b1_fx_rate_to_cny == Decimal("6.7811")
    assert settings.phase2b1_cost_cap_cny == Decimal("0.50")


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
async def test_payload_is_fixed_and_deepseek_usage_is_parsed(tmp_path) -> None:
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
                "system_fingerprint": "fp_test",
                "choices": [
                    {
                        "message": {"content": '{"summary":"ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": _usage(),
            },
        )

    response = await _provider(tmp_path, handler).generate(_request())

    assert captured["url"] == f"{BASE_URL}/chat/completions"
    assert captured["authorization"] == f"Bearer {FAKE_API_KEY}"
    assert captured["body"] == {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": "synthetic JSON test input"}],
        "thinking": {"type": "disabled"},
        "stream": False,
        "max_tokens": 2_048,
        "response_format": {"type": "json_object"},
    }
    assert response.model == MODEL_NAME
    assert response.provider_request_id == "chatcmpl-test-123"
    assert response.system_fingerprint == "fp_test"
    assert response.usage.model_dump() == _usage()


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
    assert "synthetic JSON test input" not in str(raised.value.as_safe_dict())


@pytest.mark.asyncio
async def test_429_preserves_safe_retry_metadata_and_complete_usage(tmp_path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"retry-after": "3"},
            json={
                "id": "req-rate-limit",
                "error": {"message": "unsafe provider detail must be discarded"},
                "usage": _usage(),
            },
        )

    with pytest.raises(ProviderRequestError) as raised:
        await _provider(tmp_path, handler).generate(_request())

    error = raised.value
    assert error.error_code == "PROVIDER_RATE_LIMITED"
    assert error.provider_request_id == "req-rate-limit"
    assert error.retry_after_seconds == 3
    assert error.usage is not None and error.usage.total_tokens == 150
    assert "unsafe provider detail" not in str(error.as_safe_dict())


@pytest.mark.asyncio
async def test_5xx_is_ambiguous_and_not_retryable_by_provider(tmp_path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"id": "req-server"})

    with pytest.raises(ProviderRequestError) as raised:
        await _provider(tmp_path, handler).generate(_request())

    assert raised.value.error_code == "PROVIDER_SERVER_ERROR"
    assert raised.value.http_request_sent is True
    assert raised.value.provider_request_id == "req-server"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "usage",
    [
        None,
        {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
            "prompt_cache_hit_tokens": 3,
            "prompt_cache_miss_tokens": 6,
        },
    ],
)
async def test_missing_or_inconsistent_usage_fails_closed_for_accounting(
    tmp_path, usage: dict[str, int] | None
) -> None:
    payload: dict[str, object] = {
        "id": "req-incomplete-usage",
        "model": MODEL_NAME,
        "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
    }
    if usage is not None:
        payload["usage"] = usage

    with pytest.raises(ProviderRequestError) as raised:
        await _provider(tmp_path, lambda _request: httpx.Response(200, json=payload)).generate(
            _request()
        )

    assert raised.value.error_code == "PROVIDER_RESPONSE_INVALID"
    assert raised.value.provider_request_id == "req-incomplete-usage"
    assert raised.value.usage is None


@pytest.mark.asyncio
async def test_empty_content_is_returned_with_complete_usage_for_contract_retry(tmp_path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "req-empty",
                "model": MODEL_NAME,
                "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
                "usage": _usage(),
            },
        )

    response = await _provider(tmp_path, handler).generate(_request())
    assert response.text == ""
    assert response.usage.prompt_cache_miss_tokens == 85


@pytest.mark.asyncio
async def test_missing_response_id_preserves_complete_usage_for_invalid_response(tmp_path) -> None:
    with pytest.raises(ProviderRequestError) as raised:
        await _provider(
            tmp_path,
            lambda _request: httpx.Response(
                200,
                json={
                    "model": MODEL_NAME,
                    "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                    "usage": _usage(),
                },
            ),
        ).generate(_request())

    assert raised.value.error_code == "PROVIDER_RESPONSE_INVALID"
    assert raised.value.provider_request_id is None
    assert raised.value.usage is not None
    assert raised.value.usage.total_tokens == 150


@pytest.mark.asyncio
async def test_wrong_model_or_length_finish_preserves_usage(tmp_path) -> None:
    for response_model, finish_reason in (("unexpected-model", "stop"), (MODEL_NAME, "length")):
        with pytest.raises(ProviderRequestError) as raised:
            await _provider(
                tmp_path,
                lambda _request, model=response_model, finish=finish_reason: httpx.Response(
                    200,
                    json={
                        "id": "req-invalid-contract",
                        "model": model,
                        "choices": [{"message": {"content": "{}"}, "finish_reason": finish}],
                        "usage": _usage(),
                    },
                ),
            ).generate(_request())
        assert raised.value.error_code == "PROVIDER_RESPONSE_INVALID"
        assert raised.value.usage is not None
        assert raised.value.usage.total_tokens == 150


@pytest.mark.asyncio
async def test_secret_file_is_required_and_never_returned(tmp_path) -> None:
    missing = tmp_path / "missing.key"
    provider = DeepSeekProvider(
        base_url=BASE_URL,
        api_key_file=missing,
        timeout_seconds=10,
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
    )
    with pytest.raises(ProviderRequestError) as raised:
        await provider.generate(_request())
    assert raised.value.error_code == "PROVIDER_SECRET_UNAVAILABLE"
    assert raised.value.http_request_sent is False
    assert raised.value.provider_request_id is None
    assert raised.value.usage is None
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
        phase2b1_base_url=BASE_URL,
        phase2b1_api_key_file=str(key_file),
    )
    assert create_phase2b1_provider(configured).model == MODEL_NAME
