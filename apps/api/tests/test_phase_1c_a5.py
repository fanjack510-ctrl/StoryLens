"""Phase 1C-A.5: provider transport errors, classification, diagnostics."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import ModelInvocation, ProviderConfiguration
from app.model_gateway.base import ProviderRequestError
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.provider_errors import (
    TRANSPORT_CONNECT_TIMEOUT,
    TRANSPORT_CONNECTION,
    TRANSPORT_DNS,
    TRANSPORT_PROXY,
    TRANSPORT_READ_TIMEOUT,
    TRANSPORT_TLS,
    classify_exception,
    safe_message,
)
from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.services.scene_pipeline import classify_pipeline_error
from app.services.structured_output import StructuredOutputError
from app.services.transport_diagnostic import run_transport_diagnostic


def test_empty_exception_message_becomes_non_empty() -> None:
    err = ProviderRequestError(
        "",
        transport_kind=TRANSPORT_CONNECTION,
        exception_type="ConnectError",
        provider="aliyun_qwen_plus",
    )
    assert str(err)
    assert "ConnectError" in str(err) or "连接" in str(err)


@pytest.mark.parametrize(
    "exc,kind",
    [
        (httpx.ConnectError("fail"), TRANSPORT_CONNECTION),
        (httpx.ConnectTimeout("fail"), TRANSPORT_CONNECT_TIMEOUT),
        (httpx.ReadTimeout("fail"), TRANSPORT_READ_TIMEOUT),
        (httpx.ProxyError("fail"), TRANSPORT_PROXY),
    ],
)
def test_classify_httpx_transport(exc, kind) -> None:
    transport, _timeout, retryable = classify_exception(exc)
    assert transport == kind
    assert retryable is True


def test_classify_tls_error() -> None:
    exc = httpx.ConnectError("SSL: CERTIFICATE_VERIFY_FAILED")
    transport, _timeout, retryable = classify_exception(exc)
    assert transport == TRANSPORT_TLS
    assert retryable is False


def test_safe_message_redacts_url_and_bearer() -> None:
    text = safe_message(
        "Client error for url https://secret.example/v1 with Bearer sk-abc123",
        fallback="fallback",
    )
    assert "secret.example" not in text
    assert "sk-abc" not in text
    assert "Bearer" not in text or "[REDACTED]" in text


def test_no_http_response_not_business_validation() -> None:
    provider_err = ProviderRequestError(
        "connection failed",
        http_request_sent=True,
        transport_kind=TRANSPORT_CONNECTION,
        error_code="PROVIDER_CONNECTION_ERROR",
        retryable=True,
        provider="aliyun_qwen_plus",
    )
    wrapped = StructuredOutputError(
        str(provider_err),
        provider_err.error_code,
        category="provider_request",
        retryable=True,
        provider_error=provider_err,
        failed_invocation_id=91,
    )
    code, stage, retryable, _hint = classify_pipeline_error(wrapped)
    assert code == "PROVIDER_CONNECTION_ERROR"
    assert stage == "provider_request"
    assert retryable is True


def test_provider_error_retryable() -> None:
    err = ProviderRequestError(
        "timeout",
        transport_kind=TRANSPORT_READ_TIMEOUT,
        error_code="PROVIDER_READ_TIMEOUT",
    )
    assert err.retryable is True
    disabled = ProviderRequestError(
        "disabled",
        transport_kind="provider_disabled",
        error_code="PROVIDER_DISABLED",
        retryable=False,
    )
    assert disabled.retryable is False


def test_json_and_schema_and_business_classification() -> None:
    json_err = StructuredOutputError("bad json", "JSON_PARSE_FAILED", category="json_validation")
    schema_err = StructuredOutputError(
        "schema boom", "SCHEMA_VALIDATION_FAILED", category="schema_validation"
    )
    business = StructuredOutputError(
        "v3.5 decisions must cover",
        "BUSINESS_VALIDATION_FAILED",
        category="business_validation",
        retryable=False,
    )
    assert classify_pipeline_error(json_err)[0] == "JSON_PARSE_FAILED"
    assert classify_pipeline_error(schema_err)[0] == "SCHEMA_VALIDATION_FAILED"
    code, stage, retryable, _ = classify_pipeline_error(business)
    assert code == "BUSINESS_VALIDATION_FAILED"
    assert stage == "business_validation"
    assert retryable is False


def test_error_cause_preserved() -> None:
    cause = httpx.ConnectTimeout("x")
    err = ProviderRequestError("timeout", transport_kind=TRANSPORT_CONNECT_TIMEOUT)
    try:
        raise err from cause
    except ProviderRequestError as raised:
        assert raised.__cause__ is cause


def test_provider_configuration_enabled_is_runtime_source(testing_session: Session) -> None:
    from app.services.provider_runtime import apply_provider_runtime

    provider = OpenAICompatibleProvider(
        name="aliyun_qwen_plus",
        base_url="https://example.invalid/compatible-mode/v1",
        api_key="x",
        default_model="qwen3.7-plus",
        timeout_seconds=30,
        max_context_tokens=1024,
        enabled=False,
        cloud=True,
        sends_content_to_cloud=True,
    )
    testing_session.add(
        ProviderConfiguration(
            provider_name="aliyun_qwen_plus",
            enabled=True,
            disconnected=False,
            base_url="https://example.invalid/compatible-mode/v1",
            allow_auto_route=False,
        )
    )
    testing_session.commit()
    apply_provider_runtime(provider, testing_session, None)
    assert provider.enabled is True
    assert provider.capabilities().enabled is True


@pytest.mark.asyncio
async def test_health_disabled_blocks_generate() -> None:
    provider = OpenAICompatibleProvider(
        name="aliyun_qwen_plus",
        base_url="https://example.invalid/compatible-mode/v1",
        api_key="x",
        default_model="qwen3.7-plus",
        timeout_seconds=5,
        max_context_tokens=1024,
        enabled=False,
        cloud=True,
    )
    health = await provider.health()
    assert health.status == "disabled"
    with pytest.raises(ProviderRequestError) as raised:
        await provider.generate(
            __import__("app.model_gateway.base", fromlist=["ModelRequest"]).ModelRequest(
                messages=[{"role": "user", "content": "hi"}]
            )
        )
    assert raised.value.error_code == "PROVIDER_DISABLED"
    assert raised.value.http_request_sent is False


def test_transport_diagnostic_no_invocation_or_tokens(
    client: TestClient, testing_session: Session
) -> None:
    from app.main import app
    from app.model_gateway.registry import get_model_gateway
    from app.db.session import get_db

    provider = OpenAICompatibleProvider(
        name="aliyun_qwen_plus",
        base_url="https://127.0.0.1:9/compatible-mode/v1",
        api_key="x",
        default_model="qwen3.7-plus",
        timeout_seconds=5,
        max_context_tokens=1024,
        enabled=True,
        cloud=True,
        sends_content_to_cloud=True,
    )
    app.dependency_overrides[get_model_gateway] = lambda: ModelGateway([provider])

    def override_db():
        yield testing_session

    app.dependency_overrides[get_db] = override_db
    testing_session.add(
        ProviderConfiguration(
            provider_name="aliyun_qwen_plus",
            enabled=True,
            disconnected=False,
            base_url="https://127.0.0.1:9/compatible-mode/v1",
            allow_auto_route=False,
        )
    )
    testing_session.commit()
    before = testing_session.query(ModelInvocation).count()
    response = client.post("/api/v1/model-providers/aliyun_qwen_plus/transport-diagnostic")
    assert response.status_code == 200
    body = response.json()
    assert body["calls_chat_completions"] is False
    assert body["creates_invocation"] is False
    assert body["generates_tokens"] is False
    assert "note" in body
    assert testing_session.query(ModelInvocation).count() == before
    app.dependency_overrides.clear()


def test_transport_diagnostic_unit_skips_chat(testing_session: Session) -> None:
    class CountingProvider(OpenAICompatibleProvider):
        def __init__(self):
            super().__init__(
                name="aliyun_qwen_plus",
                base_url="https://invalid.example/compatible-mode/v1",
                api_key="x",
                default_model="qwen3.7-plus",
                timeout_seconds=5,
                max_context_tokens=1024,
                enabled=True,
                cloud=True,
            )
            self.generate_calls = 0

        async def generate(self, request):  # type: ignore[override]
            self.generate_calls += 1
            return await super().generate(request)

    provider = CountingProvider()
    testing_session.add(
        ProviderConfiguration(
            provider_name="aliyun_qwen_plus",
            enabled=True,
            disconnected=False,
            base_url=provider.base_url,
            allow_auto_route=False,
        )
    )
    testing_session.commit()

    class FakeStore:
        def available(self):
            return True

        def get(self, name):
            return "secret"

    result = run_transport_diagnostic(
        provider_name="aliyun_qwen_plus",
        provider=provider,
        session=testing_session,
        store=FakeStore(),  # type: ignore[arg-type]
    )
    assert provider.generate_calls == 0
    assert result["calls_chat_completions"] is False
    assert result["request_endpoint_shape"]["path_redacted"]


def test_dns_failure_classification_via_fake() -> None:
    err = ProviderRequestError(
        "Name or service not known",
        http_request_sent=True,
        transport_kind=TRANSPORT_DNS,
        error_code="PROVIDER_DNS_ERROR",
        retryable=True,
    )
    code, stage, retryable, hint = classify_pipeline_error(
        StructuredOutputError(
            str(err),
            err.error_code,
            category="provider_request",
            retryable=True,
            provider_error=err,
        )
    )
    assert code == "PROVIDER_DNS_ERROR"
    assert stage == "provider_request"
    assert retryable and "诊断" in hint
