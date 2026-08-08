from urllib.parse import urlparse

import httpx

from app.model_gateway.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    ProviderHealth,
    ProviderRequestError,
)
from app.model_gateway.provider_errors import (
    TRANSPORT_DISABLED,
    TRANSPORT_HTTP,
    build_provider_http_error_snapshot,
    build_safe_details,
    categorize_provider_error,
    chinese_message_for_http_status,
    classify_exception,
    endpoint_host_from_url,
    error_code_for_transport,
    exception_type_name,
    host_fingerprint,
    original_exception_type,
    parse_retry_after,
    safe_message,
    user_hint_for,
)


class OpenAICompatibleProvider(ModelProvider):
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str,
        timeout_seconds: int,
        max_context_tokens: int,
        enabled: bool = True,
        profile_name: str = "",
        default: bool = False,
        manual_only: bool = False,
        structured_output_mode: str = "prompt_only",
        supports_json_schema: bool = False,
        supports_grammar: bool = False,
        supports_thinking_control: bool = False,
        cloud: bool = False,
        provider_family: str = "openai_compatible",
        supports_json_object: bool = False,
        sends_content_to_cloud: bool = False,
        region: str | None = None,
        supports_scene_analysis: bool = False,
        supports_boundary_candidates: bool = False,
        automatic_boundary_routing: bool = False,
        requires_boundary_review: bool = False,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds
        self.max_context_tokens = max_context_tokens
        self.enabled = enabled
        self.profile_name = profile_name
        self.is_default = default
        self.manual_only = manual_only
        self.structured_output_mode = structured_output_mode
        self.supports_json_schema = supports_json_schema
        self.supports_grammar = supports_grammar
        self.supports_thinking_control = supports_thinking_control
        self.cloud = cloud
        self.provider_family = provider_family
        self.supports_json_object = supports_json_object
        self.sends_content_to_cloud = sends_content_to_cloud
        self.region = region
        self.supports_scene_analysis = supports_scene_analysis
        self.supports_boundary_candidates = supports_boundary_candidates
        self.automatic_boundary_routing = automatic_boundary_routing
        self.requires_boundary_review = requires_boundary_review

    def _timeout(self) -> httpx.Timeout:
        total = float(self.timeout_seconds)
        connect = min(30.0, total)
        return httpx.Timeout(total, connect=connect, read=total, write=total, pool=connect)

    def _host_hash(self) -> str | None:
        try:
            return host_fingerprint(urlparse(self.base_url).hostname)
        except Exception:
            return None

    def _raise_provider_error(
        self,
        exc: BaseException,
        *,
        phase: str,
        http_request_sent: bool,
        http_status: int | None = None,
        model: str | None = None,
        response: httpx.Response | None = None,
    ) -> None:
        from app.model_gateway.provider_errors import (
            RETRYABLE_HTTP_STATUSES,
            TRANSPORT_AUTH,
        )

        transport_kind, timeout_kind, retryable = classify_exception(exc)
        response = response or (exc.response if isinstance(exc, httpx.HTTPStatusError) else None)
        if http_status is not None:
            transport_kind = TRANSPORT_HTTP if transport_kind != TRANSPORT_HTTP else transport_kind
            if http_status in {401, 403}:
                transport_kind = TRANSPORT_AUTH
                retryable = False
            elif http_status == 402:
                retryable = False
            elif http_status in RETRYABLE_HTTP_STATUSES:
                retryable = True
            elif http_status is not None:
                retryable = False
        code = error_code_for_transport(transport_kind, http_status)
        exc_name = exception_type_name(exc)
        zh = chinese_message_for_http_status(http_status)
        message = zh or safe_message(
            str(exc),
            fallback=f"Provider请求失败 ({exc_name})",
        )
        endpoint_host = endpoint_host_from_url(self.base_url)
        retry_after = parse_retry_after(getattr(response, "headers", None))
        snapshot = build_provider_http_error_snapshot(
            http_status=http_status,
            transport_kind=transport_kind,
            timeout_kind=timeout_kind,
            endpoint_host=endpoint_host,
            retry_after=retry_after,
            response=response,
            retryable=retryable,
        )
        category = categorize_provider_error(
            transport_kind, http_status=http_status, timeout_kind=timeout_kind
        )
        details = build_safe_details(
            provider=self.name,
            model=model or self.default_model,
            transport_kind=transport_kind,
            exception_type=exc_name,
            original_exception_type_name=original_exception_type(exc),
            phase=phase,
            http_status=http_status,
            timeout_kind=timeout_kind,
            host_hash=self._host_hash(),
            provider_request_id=snapshot.get("provider_request_id"),
        )
        details.update(
            {
                "error_category": category,
                "retry_after": retry_after,
                "endpoint_host": endpoint_host,
                "provider_error_code": snapshot.get("provider_error_code"),
                "provider_message": snapshot.get("provider_message"),
                "response_content_type": snapshot.get("response_content_type"),
                "sanitized_response_excerpt": snapshot.get("sanitized_response_excerpt"),
                "occurred_at": snapshot.get("occurred_at"),
                "user_reason": snapshot.get("user_reason"),
            }
        )
        raise ProviderRequestError(
            message,
            http_status,
            http_request_sent=http_request_sent,
            error_code=code,
            exception_type=exc_name,
            provider=self.name,
            model=model or self.default_model,
            phase=phase,
            retryable=retryable,
            timeout_kind=timeout_kind,
            transport_kind=transport_kind,
            safe_details=details,
            original_exception_type=original_exception_type(exc),
            user_action_hint=user_hint_for(transport_kind, code, category=category),
            error_category=category,
            retry_after=retry_after,
            endpoint_host=endpoint_host,
            provider_error_code=snapshot.get("provider_error_code"),
            provider_message=snapshot.get("provider_message"),
            provider_request_id=snapshot.get("provider_request_id"),
            response_content_type=snapshot.get("response_content_type"),
            sanitized_response_excerpt=snapshot.get("sanitized_response_excerpt"),
            occurred_at=snapshot.get("occurred_at"),
        ) from exc

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            max_context_tokens=self.max_context_tokens,
            default_timeout_seconds=self.timeout_seconds,
            enabled=self.enabled,
            profile_name=self.profile_name,
            default=self.is_default,
            manual_only=self.manual_only,
            context_size=self.max_context_tokens,
            structured_output_mode=self.structured_output_mode,
            supports_json_schema=self.supports_json_schema,
            supports_grammar=self.supports_grammar,
            supports_thinking_control=self.supports_thinking_control,
            cloud=self.cloud,
            provider_family=self.provider_family,
            supports_json_object=self.supports_json_object,
            sends_content_to_cloud=self.sends_content_to_cloud,
            region=self.region,
            supports_structured_output=(
                self.supports_json_schema
                or self.supports_json_object
                or self.supports_grammar
            ),
            supports_scene_analysis=self.supports_scene_analysis,
            supports_boundary_candidates=self.supports_boundary_candidates,
            automatic_boundary_routing=self.automatic_boundary_routing,
            requires_boundary_review=self.requires_boundary_review,
        )

    async def health(self) -> ProviderHealth:
        if not self.enabled:
            return ProviderHealth(
                provider_name=self.name,
                status="disabled",
                detail="provider_disabled",
            )
        from app.services.chapter_analysis_smoke_fake_transport import (
            is_chapter_analysis_smoke_fake_enabled,
        )

        if is_chapter_analysis_smoke_fake_enabled():
            return ProviderHealth(
                provider_name=self.name,
                status="healthy",
                detail="chapter_analysis_smoke_fake",
            )
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
            return ProviderHealth(provider_name=self.name, status="healthy")
        except (httpx.HTTPError, ValueError) as exc:
            detail = safe_message(str(exc), fallback=type(exc).__name__)
            return ProviderHealth(provider_name=self.name, status="unhealthy", detail=detail)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        from app.services.chapter_analysis_smoke_fake_transport import (
            chapter_smoke_fake_generate,
            is_chapter_analysis_smoke_fake_enabled,
        )

        # Smoke Fake short-circuits before enabled/credential gates (MG / local only).
        if is_chapter_analysis_smoke_fake_enabled():
            return await chapter_smoke_fake_generate(
                request,
                provider_name=self.name,
                default_model=self.default_model,
            )
        if not self.enabled:
            raise ProviderRequestError(
                "Provider已停用，拒绝发送请求",
                http_request_sent=False,
                error_code="PROVIDER_DISABLED",
                exception_type="ProviderDisabled",
                provider=self.name,
                model=request.model or self.default_model,
                phase="pre_send",
                retryable=False,
                transport_kind=TRANSPORT_DISABLED,
                user_action_hint=user_hint_for(TRANSPORT_DISABLED, "PROVIDER_DISABLED"),
            )
        model = request.model or self.default_model
        is_deepseek = self.provider_family == "deepseek" or self.name == "deepseek"
        payload = {
            "model": model,
            "messages": request.messages,
            "temperature": request.temperature,
        }
        output_tokens = request.max_output_tokens or request.max_tokens
        if output_tokens is not None:
            payload["max_tokens"] = output_tokens
        if is_deepseek:
            # Official default is thinking enabled — always send disabled explicitly.
            payload["thinking"] = {"type": "disabled"}
        else:
            payload["chat_template_kwargs"] = {"enable_thinking": request.enable_thinking}
        if request.response_schema and request.response_format_mode == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "storylens_response", "schema": request.response_schema},
            }
        elif request.response_schema and request.response_format_mode == "native_json_schema":
            payload["json_schema"] = request.response_schema
        elif request.response_schema and request.response_format_mode == "grammar":
            from app.model_gateway.structured_constraints import schema_to_gbnf

            payload["grammar"] = schema_to_gbnf(request.response_schema)
        elif request.response_format_mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        payload.update(request.extra_body)
        if is_deepseek:
            # Never send Aliyun-only thinking control on DeepSeek requests.
            payload.pop("chat_template_kwargs", None)
            payload["thinking"] = {"type": "disabled"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            self._raise_provider_error(
                exc,
                phase="provider_request",
                http_request_sent=True,
                http_status=exc.response.status_code,
                model=model,
                response=exc.response,
            )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            self._raise_provider_error(
                exc,
                phase="provider_request",
                http_request_sent=isinstance(exc, httpx.RequestError),
                model=model,
            )
        try:
            message = data["choices"][0]["message"]
            # Never fold reasoning_content into analysis text.
            content = message.get("content")
            if content is None:
                content = ""
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            self._raise_provider_error(
                exc,
                phase="provider_response_parse",
                http_request_sent=True,
                http_status=response.status_code,
                model=model,
            )
        usage = data.get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        completion_details = usage.get("completion_tokens_details") or {}
        cache_hit = usage.get("prompt_cache_hit_tokens")
        if cache_hit is None and isinstance(details, dict):
            cache_hit = details.get("cached_tokens")
        cache_miss = usage.get("prompt_cache_miss_tokens")
        reasoning_tokens = None
        if isinstance(completion_details, dict):
            reasoning_tokens = completion_details.get("reasoning_tokens")
        if reasoning_tokens is None:
            reasoning_tokens = usage.get("reasoning_tokens")
        return ModelResponse(
            text=content or "",
            model=data.get("model", payload["model"]),
            http_status_code=response.status_code,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            cached_tokens=details.get("cached_tokens") if isinstance(details, dict) else None,
            cache_hit_tokens=int(cache_hit) if cache_hit is not None else None,
            cache_miss_tokens=int(cache_miss) if cache_miss is not None else None,
            reasoning_tokens=int(reasoning_tokens) if reasoning_tokens is not None else None,
            request_id=getattr(response, "headers", {}).get("x-request-id")
            or data.get("request_id"),
            finish_reason=data["choices"][0].get("finish_reason"),
        )
