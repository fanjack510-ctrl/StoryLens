from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from app.model_gateway.provider_errors import (
    TRANSPORT_UNKNOWN,
    default_message_for,
    error_code_for_transport,
    is_retryable,
    safe_message,
    user_hint_for,
)


class ProviderCapabilities(BaseModel):
    supports_stream: bool = False
    supports_json_schema: bool = False
    supports_thinking: bool = False
    supports_batch: bool = False
    max_context_tokens: int
    default_timeout_seconds: int
    enabled: bool = True
    profile_name: str = ""
    default: bool = False
    manual_only: bool = False
    context_size: int | None = None
    structured_output_mode: str = "prompt_only"
    supports_grammar: bool = False
    supports_thinking_control: bool = False
    cloud: bool = False
    provider_family: str = "openai_compatible"
    supports_json_object: bool = False
    sends_content_to_cloud: bool = False
    region: str | None = None
    supports_structured_output: bool = False
    supports_scene_analysis: bool = False
    supports_boundary_candidates: bool = False
    automatic_boundary_routing: bool = False
    requires_boundary_review: bool = False


class ProviderHealth(BaseModel):
    provider_name: str
    status: str
    detail: str | None = None


class ModelRequest(BaseModel):
    messages: list[dict[str, str]]
    model: str | None = None
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    response_schema: dict[str, object] | None = None
    response_format_mode: str | None = None
    enable_thinking: bool = False
    extra_body: dict[str, object] = Field(default_factory=dict)


class ModelResponse(BaseModel):
    text: str
    model: str
    http_status_code: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None
    cache_hit_tokens: int | None = None
    cache_miss_tokens: int | None = None
    reasoning_tokens: int | None = None
    request_id: str | None = None
    finish_reason: str | None = None


class ProviderRequestError(RuntimeError):
    """Structured provider/transport failure. Message is never empty."""

    def __init__(
        self,
        message: str | None = None,
        http_status_code: int | None = None,
        *,
        http_request_sent: bool = False,
        error_code: str | None = None,
        exception_type: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        phase: str = "provider_request",
        retryable: bool | None = None,
        request_id: str | None = None,
        provider_request_id: str | None = None,
        timeout_kind: str | None = None,
        transport_kind: str = TRANSPORT_UNKNOWN,
        safe_details: dict[str, Any] | None = None,
        original_exception_type: str | None = None,
        user_action_hint: str | None = None,
        error_category: str | None = None,
        retry_after: float | None = None,
        endpoint_host: str | None = None,
        provider_error_code: str | None = None,
        provider_message: str | None = None,
        response_content_type: str | None = None,
        sanitized_response_excerpt: str | None = None,
        occurred_at: str | None = None,
    ) -> None:
        from app.model_gateway.provider_errors import (
            build_provider_http_error_snapshot,
            categorize_provider_error,
        )

        resolved_type = exception_type or "ProviderRequestError"
        transport = transport_kind or TRANSPORT_UNKNOWN
        code = error_code or error_code_for_transport(transport, http_status_code)
        fallback = default_message_for(transport, resolved_type)
        text = safe_message(message, fallback=fallback)
        super().__init__(text)
        self.error_code = code
        self.exception_type = resolved_type
        self.provider = provider
        self.model = model
        self.phase = phase
        self.retryable = (
            is_retryable(transport, http_status=http_status_code, explicit=retryable)
            if retryable is None
            else retryable
        )
        self.http_status_code = http_status_code
        self.http_request_sent = http_request_sent
        self.request_id = request_id
        self.provider_request_id = provider_request_id
        self.timeout_kind = timeout_kind
        self.transport_kind = transport
        self.original_exception_type = original_exception_type or resolved_type
        self.error_category = error_category or categorize_provider_error(
            transport, http_status=http_status_code, timeout_kind=timeout_kind
        )
        self.retry_after = retry_after
        self.endpoint_host = endpoint_host
        self.provider_error_code = provider_error_code
        self.provider_message = provider_message
        self.response_content_type = response_content_type
        self.sanitized_response_excerpt = sanitized_response_excerpt
        self.occurred_at = occurred_at
        snapshot = build_provider_http_error_snapshot(
            http_status=http_status_code,
            transport_kind=transport,
            timeout_kind=timeout_kind,
            endpoint_host=endpoint_host,
            retry_after=retry_after,
            provider_error_code=provider_error_code,
            provider_message=provider_message,
            provider_request_id=provider_request_id,
            response_content_type=response_content_type,
            sanitized_response_excerpt=sanitized_response_excerpt,
            retryable=self.retryable,
        )
        if occurred_at:
            snapshot["occurred_at"] = occurred_at
        self.http_error_snapshot = snapshot
        self.safe_details = safe_details or {
            "provider": provider,
            "model": model,
            "transport_kind": transport,
            "exception_type": resolved_type,
            "original_exception_type": self.original_exception_type,
            "phase": phase,
            "http_status": http_status_code,
            "timeout_kind": timeout_kind,
            "request_id": request_id,
            "provider_request_id": provider_request_id,
            "error_category": self.error_category,
            "retry_after": retry_after,
            "endpoint_host": endpoint_host,
            "provider_error_code": provider_error_code,
            "provider_message": provider_message,
            "response_content_type": response_content_type,
            "sanitized_response_excerpt": sanitized_response_excerpt,
            "occurred_at": snapshot.get("occurred_at"),
            "user_reason": snapshot.get("user_reason"),
        }
        self.user_action_hint = user_action_hint or user_hint_for(
            transport, code, category=self.error_category
        )

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": str(self),
            "exception_type": self.exception_type,
            "provider": self.provider,
            "model": self.model,
            "phase": self.phase,
            "retryable": self.retryable,
            "http_status": self.http_status_code,
            "request_id": self.request_id,
            "provider_request_id": self.provider_request_id,
            "timeout_kind": self.timeout_kind,
            "transport_kind": self.transport_kind,
            "safe_details": self.safe_details,
            "original_exception_type": self.original_exception_type,
            "user_action_hint": self.user_action_hint,
            "http_request_sent": self.http_request_sent,
            "error_category": self.error_category,
            "retry_after": self.retry_after,
            "endpoint_host": self.endpoint_host,
            "provider_error_code": self.provider_error_code,
            "provider_message": self.provider_message,
            "response_content_type": self.response_content_type,
            "sanitized_response_excerpt": self.sanitized_response_excerpt,
            "occurred_at": self.occurred_at or self.http_error_snapshot.get("occurred_at"),
            "http_error_snapshot": self.http_error_snapshot,
        }


class ModelProvider(ABC):
    name: str
    default_model: str

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse: ...

    @abstractmethod
    async def health(self) -> ProviderHealth: ...

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...
