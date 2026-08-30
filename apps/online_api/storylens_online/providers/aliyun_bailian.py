from __future__ import annotations

import json
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from storylens_online.providers.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ProviderRequestError,
)

PROVIDER_NAME = "aliyun_bailian"
MODEL_NAME = "qwen3.7-plus-2026-05-26"
ALIYUN_HOST_SUFFIX = ".cn-beijing.maas.aliyuncs.com"
CHAT_COMPLETIONS_PATH = "/compatible-mode/v1/chat/completions"
_WORKSPACE_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,62})$")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,255}$")


def validate_chat_completions_url(value: str) -> str:
    """Accept only the frozen Bailian Beijing workspace endpoint shape."""

    parsed = urlparse(value)
    hostname = parsed.hostname or ""
    workspace = (
        hostname[: -len(ALIYUN_HOST_SUFFIX)] if hostname.endswith(ALIYUN_HOST_SUFFIX) else ""
    )
    invalid = (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or not _WORKSPACE_PATTERN.fullmatch(workspace)
        or parsed.path != CHAT_COMPLETIONS_PATH
        or bool(parsed.params)
        or bool(parsed.query)
        or bool(parsed.fragment)
    )
    if invalid:
        raise ValueError("Phase 2B1 endpoint must be the approved Aliyun Beijing workspace URL")
    return value


def _provider_request_id(response: httpx.Response, data: object | None = None) -> str | None:
    for name in ("x-request-id", "request-id", "x-acs-request-id"):
        value = response.headers.get(name)
        if value and _REQUEST_ID_PATTERN.fullmatch(value):
            return value
    if isinstance(data, dict):
        for field_name in ("request_id", "id"):
            value = data.get(field_name)
            if isinstance(value, str) and _REQUEST_ID_PATTERN.fullmatch(value):
                return value
    return None


def _integer_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _parse_usage(data: object) -> ModelUsage | None:
    if not isinstance(data, dict):
        return None
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    input_tokens = _integer_or_none(usage.get("prompt_tokens"))
    output_tokens = _integer_or_none(usage.get("completion_tokens"))
    total_tokens = _integer_or_none(usage.get("total_tokens"))
    details = usage.get("prompt_tokens_details")
    cached_tokens = None
    if isinstance(details, dict):
        cached_tokens = _integer_or_none(details.get("cached_tokens"))
    if cached_tokens is None:
        cached_tokens = _integer_or_none(usage.get("prompt_cache_hit_tokens"))
    if input_tokens is None or output_tokens is None or total_tokens is None:
        return None
    try:
        return ModelUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens or 0,
        )
    except ValidationError:
        return None


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
            return max(0.0, (parsed - datetime.now(parsed.tzinfo)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


class AliyunBailianProvider(ModelProvider):
    """Fixed Aliyun Bailian OpenAI-compatible provider for Phase 2B1."""

    name = PROVIDER_NAME
    model = MODEL_NAME

    def __init__(
        self,
        *,
        chat_completions_url: str,
        api_key_file: str | Path,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.chat_completions_url = validate_chat_completions_url(chat_completions_url)
        self.api_key_file = Path(api_key_file)
        if not self.api_key_file.is_absolute():
            raise ValueError("Phase 2B1 API key file path must be absolute")
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    def _read_api_key(self) -> str:
        try:
            size = self.api_key_file.stat().st_size
            if size <= 0 or size > 4_096 or not self.api_key_file.is_file():
                raise OSError
            value = self.api_key_file.read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as exc:
            raise ProviderRequestError(
                error_code="PROVIDER_SECRET_UNAVAILABLE",
                http_request_sent=False,
            ) from exc
        if not value or "\n" in value or "\r" in value:
            raise ProviderRequestError(
                error_code="PROVIDER_SECRET_UNAVAILABLE",
                http_request_sent=False,
            )
        return value

    def _timeout(self) -> httpx.Timeout:
        connect = min(30.0, self.timeout_seconds)
        return httpx.Timeout(
            self.timeout_seconds,
            connect=connect,
            read=self.timeout_seconds,
            write=self.timeout_seconds,
            pool=connect,
        )

    @staticmethod
    def _payload(request: ModelRequest) -> dict[str, object]:
        return {
            "model": MODEL_NAME,
            "messages": request.messages,
            "enable_thinking": False,
            "enable_search": False,
            "stream": False,
            "max_completion_tokens": request.max_completion_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "storylens_phase2b1_result",
                    "strict": True,
                    "schema": request.response_schema,
                },
            },
        }

    @staticmethod
    def _raise_http_error(response: httpx.Response) -> None:
        data: object | None = None
        try:
            data = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            pass
        status = response.status_code
        if status == 429:
            code = "PROVIDER_RATE_LIMITED"
        elif 500 <= status <= 599:
            code = "PROVIDER_SERVER_ERROR"
        else:
            code = "PROVIDER_HTTP_ERROR"
        raise ProviderRequestError(
            error_code=code,
            http_request_sent=True,
            http_status_code=status,
            provider_request_id=_provider_request_id(response, data),
            retry_after_seconds=_retry_after_seconds(response),
            usage=_parse_usage(data),
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        api_key = self._read_api_key()
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout(),
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    self.chat_completions_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=self._payload(request),
                )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            code = (
                "PROVIDER_CONNECT_ERROR"
                if isinstance(exc, httpx.ConnectError)
                else "PROVIDER_CONNECT_TIMEOUT"
            )
            raise ProviderRequestError(error_code=code, http_request_sent=False) from exc
        except httpx.ReadTimeout as exc:
            raise ProviderRequestError(
                error_code="PROVIDER_READ_TIMEOUT",
                http_request_sent=True,
            ) from exc
        except httpx.WriteTimeout as exc:
            raise ProviderRequestError(
                error_code="PROVIDER_WRITE_TIMEOUT",
                http_request_sent=True,
            ) from exc
        except (httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError) as exc:
            raise ProviderRequestError(
                error_code="PROVIDER_CONNECTION_INTERRUPTED",
                http_request_sent=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderRequestError(
                error_code="PROVIDER_CONNECTION_INTERRUPTED",
                http_request_sent=True,
            ) from exc
        finally:
            api_key = ""

        if response.status_code < 200 or response.status_code >= 300:
            self._raise_http_error(response)

        try:
            data = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise ProviderRequestError(
                error_code="PROVIDER_RESPONSE_INVALID",
                http_request_sent=True,
                http_status_code=response.status_code,
                provider_request_id=_provider_request_id(response),
            ) from exc

        request_id = _provider_request_id(response, data)
        usage = _parse_usage(data)
        if usage is None:
            raise ProviderRequestError(
                error_code="PROVIDER_RESPONSE_INVALID",
                http_request_sent=True,
                http_status_code=response.status_code,
                provider_request_id=request_id,
            )
        try:
            choice = data["choices"][0]
            text = choice["message"]["content"]
            finish_reason = choice.get("finish_reason")
            response_model = data.get("model", MODEL_NAME)
            if (
                not isinstance(text, str)
                or not isinstance(response_model, str)
                or response_model != MODEL_NAME
            ):
                raise TypeError
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ProviderRequestError(
                error_code="PROVIDER_RESPONSE_INVALID",
                http_request_sent=True,
                http_status_code=response.status_code,
                provider_request_id=request_id,
                usage=usage,
            ) from exc
        return ModelResponse(
            text=text,
            model=response_model,
            usage=usage,
            provider_request_id=request_id,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        )
