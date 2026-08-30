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

PROVIDER_NAME = "deepseek"
MODEL_NAME = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com"
CHAT_COMPLETIONS_PATH = "/chat/completions"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,255}$")


def validate_base_url(value: str) -> str:
    """Accept only the frozen official DeepSeek API origin."""

    parsed = urlparse(value)
    invalid = (
        parsed.scheme != "https"
        or parsed.hostname != "api.deepseek.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.path not in {"", "/"}
        or bool(parsed.params)
        or bool(parsed.query)
        or bool(parsed.fragment)
    )
    if invalid:
        raise ValueError("Phase 2B1 base URL must be the approved DeepSeek HTTPS origin")
    return BASE_URL


def _provider_request_id(data: object | None) -> str | None:
    if not isinstance(data, dict):
        return None
    value = data.get("id")
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
    values = {
        "prompt_tokens": _integer_or_none(usage.get("prompt_tokens")),
        "completion_tokens": _integer_or_none(usage.get("completion_tokens")),
        "total_tokens": _integer_or_none(usage.get("total_tokens")),
        "prompt_cache_hit_tokens": _integer_or_none(usage.get("prompt_cache_hit_tokens")),
        "prompt_cache_miss_tokens": _integer_or_none(usage.get("prompt_cache_miss_tokens")),
    }
    if any(value is None for value in values.values()):
        return None
    try:
        return ModelUsage.model_validate(values)
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


class DeepSeekProvider(ModelProvider):
    """Fixed official DeepSeek JSON Object provider for Phase 2B1."""

    name = PROVIDER_NAME
    model = MODEL_NAME

    def __init__(
        self,
        *,
        base_url: str,
        api_key_file: str | Path,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = validate_base_url(base_url)
        self.chat_completions_url = f"{self.base_url}{CHAT_COMPLETIONS_PATH}"
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
            "thinking": {"type": "disabled"},
            "stream": False,
            "max_tokens": request.max_completion_tokens,
            "response_format": {"type": "json_object"},
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
        response_model = data.get("model") if isinstance(data, dict) else None
        system_fingerprint = data.get("system_fingerprint") if isinstance(data, dict) else None
        raise ProviderRequestError(
            error_code=code,
            http_request_sent=True,
            http_status_code=status,
            provider_request_id=_provider_request_id(data),
            retry_after_seconds=_retry_after_seconds(response),
            usage=_parse_usage(data),
            response_model=response_model if isinstance(response_model, str) else None,
            system_fingerprint=(
                system_fingerprint if isinstance(system_fingerprint, str) else None
            ),
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
            ) from exc

        request_id = _provider_request_id(data)
        usage = _parse_usage(data)
        response_model_value = data.get("model") if isinstance(data, dict) else None
        response_model = response_model_value if isinstance(response_model_value, str) else None
        fingerprint_value = data.get("system_fingerprint") if isinstance(data, dict) else None
        system_fingerprint = fingerprint_value if isinstance(fingerprint_value, str) else None
        if usage is None or request_id is None:
            raise ProviderRequestError(
                error_code="PROVIDER_RESPONSE_INVALID",
                http_request_sent=True,
                http_status_code=response.status_code,
                provider_request_id=request_id,
                usage=usage,
                response_model=response_model,
                system_fingerprint=system_fingerprint,
            )
        try:
            choice = data["choices"][0]
            text = choice["message"]["content"]
            finish_reason = choice.get("finish_reason")
            response_model = data["model"]
            system_fingerprint = data.get("system_fingerprint")
            if (
                not isinstance(text, str)
                or not isinstance(response_model, str)
                or response_model != MODEL_NAME
                or not isinstance(finish_reason, str)
                or (system_fingerprint is not None and not isinstance(system_fingerprint, str))
            ):
                raise TypeError
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ProviderRequestError(
                error_code="PROVIDER_RESPONSE_INVALID",
                http_request_sent=True,
                http_status_code=response.status_code,
                provider_request_id=request_id,
                usage=usage,
                response_model=response_model,
                system_fingerprint=system_fingerprint,
            ) from exc
        if finish_reason != "stop":
            raise ProviderRequestError(
                error_code="PROVIDER_RESPONSE_INVALID",
                http_request_sent=True,
                http_status_code=response.status_code,
                provider_request_id=request_id,
                usage=usage,
                response_model=response_model,
                system_fingerprint=system_fingerprint,
            )
        return ModelResponse(
            text=text,
            model=response_model,
            usage=usage,
            provider_request_id=request_id,
            finish_reason=finish_reason,
            system_fingerprint=system_fingerprint,
        )
