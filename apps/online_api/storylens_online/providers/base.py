from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelRequest(BaseModel):
    """Provider-neutral structured generation request.

    Provider selection, endpoint, model and credentials deliberately do not
    appear here, so an API or browser payload cannot override server policy.
    """

    model_config = ConfigDict(extra="forbid")

    messages: list[dict[str, str]] = Field(min_length=1)
    max_completion_tokens: int = Field(ge=1, le=2_048)


class ModelUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    prompt_cache_hit_tokens: int = Field(ge=0)
    prompt_cache_miss_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_totals(self) -> ModelUsage:
        if self.prompt_cache_hit_tokens + self.prompt_cache_miss_tokens != self.prompt_tokens:
            raise ValueError("cache hit and miss token counts must equal prompt tokens")
        if self.prompt_tokens + self.completion_tokens != self.total_tokens:
            raise ValueError("prompt and completion token counts must equal total tokens")
        return self

    @property
    def input_tokens(self) -> int:
        return self.prompt_tokens

    @property
    def output_tokens(self) -> int:
        return self.completion_tokens

    @property
    def cached_tokens(self) -> int:
        return self.prompt_cache_hit_tokens


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    model: str
    usage: ModelUsage
    provider_request_id: str | None = None
    finish_reason: str | None = None
    system_fingerprint: str | None = None


_SAFE_ERROR_MESSAGES = {
    "PROVIDER_CONNECT_ERROR": "Provider connection could not be established.",
    "PROVIDER_CONNECT_TIMEOUT": "Provider connection could not be established in time.",
    "PROVIDER_RATE_LIMITED": "Provider rate limit was reached.",
    "PROVIDER_READ_TIMEOUT": "Provider response status is unknown.",
    "PROVIDER_CONNECTION_INTERRUPTED": "Provider response status is unknown.",
    "PROVIDER_WRITE_TIMEOUT": "Provider request status is unknown.",
    "PROVIDER_SERVER_ERROR": "Provider returned a server error.",
    "PROVIDER_HTTP_ERROR": "Provider rejected the request.",
    "PROVIDER_RESPONSE_INVALID": "Provider returned an invalid response.",
    "PROVIDER_SECRET_UNAVAILABLE": "Provider credential is unavailable.",
    "PROVIDER_CONFIGURATION_INVALID": "Provider configuration is invalid.",
}


class ProviderRequestError(RuntimeError):
    """Sanitized failure contract consumed by the Phase 2B1 worker.

    Raw response bodies, request payloads, URLs, credentials and source
    exception messages are intentionally not retained.
    """

    def __init__(
        self,
        *,
        error_code: str,
        http_request_sent: bool,
        http_status_code: int | None = None,
        provider_request_id: str | None = None,
        retry_after_seconds: float | None = None,
        usage: ModelUsage | None = None,
        response_model: str | None = None,
        system_fingerprint: str | None = None,
    ) -> None:
        super().__init__(_SAFE_ERROR_MESSAGES.get(error_code, "Provider request failed safely."))
        self.error_code = error_code
        self.http_request_sent = http_request_sent
        self.http_status_code = http_status_code
        self.provider_request_id = provider_request_id
        self.retry_after_seconds = retry_after_seconds
        self.usage = usage
        self.response_model = response_model
        self.system_fingerprint = system_fingerprint

    def as_safe_dict(self) -> dict[str, object | None]:
        return {
            "error_code": self.error_code,
            "message": str(self),
            "http_request_sent": self.http_request_sent,
            "http_status_code": self.http_status_code,
            "provider_request_id": self.provider_request_id,
            "retry_after_seconds": self.retry_after_seconds,
            "usage": self.usage.model_dump() if self.usage is not None else None,
        }


class ModelProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse: ...

    async def aclose(self) -> None:
        """Release provider resources when a long-lived client is used."""
