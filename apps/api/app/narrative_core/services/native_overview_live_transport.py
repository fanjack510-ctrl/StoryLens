"""Live ProviderTransport for native Whole-Book Overview (STEP 2.5).

Bridges Aliyun OpenAI-compatible HTTP into the Private engine ``request()``
protocol. Hard-caps automatic retries at 1 for timeout / rate-limit / network.
Never logs API keys.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Mapping

from app.model_gateway.base import ModelRequest, ProviderRequestError
from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.services.aliyun_endpoint import resolve_aliyun_compatible_base_url
from app.services.cloud_pricing import estimate_cost
from app.services.credentials.service import get_credential_store


def _private_transport_error(
    code: str,
    message: str,
    *,
    retryable: bool,
    details: dict[str, Any] | None = None,
) -> Exception:
    """Raise Private TransportError when available; else duck-typed error."""

    try:
        from storylens_private_engine.modules.book_overview.errors import (  # type: ignore
            TransportError,
        )

        return TransportError(
            code=code,
            message=message,
            retryable=retryable,
            details=dict(details or {}),
        )
    except Exception:  # noqa: BLE001
        err = RuntimeError(f"{code}: {message}")
        err.code = code  # type: ignore[attr-defined]
        err.message = message  # type: ignore[attr-defined]
        err.retryable = retryable  # type: ignore[attr-defined]
        err.details = dict(details or {})  # type: ignore[attr-defined]
        return err


@dataclass
class AliyunNativeOverviewTransport:
    """Real Provider transport for ``private-native-overview-v1`` (serial calls)."""

    provider_name: str = "aliyun_qwen_plus"
    model: str = "qwen3.6-flash"
    timeout_seconds: int = 90
    max_output_tokens: int = 2048
    max_auto_retries: int = 1  # STEP 2.5 hard cap (extra attempts after first)
    temperature: float = 0.2
    call_log: list[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        if self.call_log is None:
            self.call_log = []
        if self.max_auto_retries < 0 or self.max_auto_retries > 1:
            raise ValueError("max_auto_retries must be 0 or 1 for STEP 2.5 Live")

    def request(
        self,
        prompt: str,
        model_options: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        options = dict(model_options or {})
        model = str(options.get("model") or self.model)
        max_out = int(options.get("max_output_tokens") or options.get("max_tokens") or self.max_output_tokens)
        stage = str(options.get("stage") or "")

        store = get_credential_store()
        api_key = store.get(self.provider_name)
        if not api_key or not str(api_key).strip():
            raise _private_transport_error(
                "PROVIDER_NOT_CONFIGURED",
                f"No API key in keyring for provider {self.provider_name!r}.",
                retryable=False,
                details={"provider": self.provider_name},
            )

        from app.core.config import get_settings

        settings = get_settings()
        base_url = resolve_aliyun_compatible_base_url(
            base_url=None,
            workspace_id=getattr(settings, "aliyun_workspace_id", None),
            settings=settings,
        )
        provider = OpenAICompatibleProvider(
            name=self.provider_name,
            base_url=base_url,
            api_key=str(api_key),
            default_model=model,
            timeout_seconds=self.timeout_seconds,
            max_context_tokens=128_000,
            enabled=True,
            cloud=True,
            provider_family="aliyun_qwen",
            supports_json_object=True,
            sends_content_to_cloud=True,
            region="cn-beijing",
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a careful literary analyst. Return ONLY valid JSON "
                    "matching the requested schema. Quotes must be verbatim "
                    "substrings of the provided paragraphs."
                ),
            },
            {"role": "user", "content": str(prompt)},
        ]
        req = ModelRequest(
            messages=messages,
            model=model,
            temperature=float(options.get("temperature") or self.temperature),
            max_output_tokens=max_out,
            response_format_mode="json_object",
            enable_thinking=False,
        )

        attempts = 0
        last_exc: BaseException | None = None
        while attempts <= self.max_auto_retries:
            attempts += 1
            started = time.perf_counter()
            try:
                response = asyncio.run(provider.generate(req))
                latency_ms = max(0, int((time.perf_counter() - started) * 1000))
                in_tok = int(response.input_tokens or 0)
                out_tok = int(response.output_tokens or 0)
                if in_tok <= 0 and out_tok <= 0:
                    # Usage missing — refuse to invent; estimate input from chars only for cost gate after
                    raise _private_transport_error(
                        "PROVIDER_OUTPUT_INVALID",
                        "Provider returned no usage tokens; cannot settle Live cost.",
                        retryable=False,
                        details={"stage": stage},
                    )
                cost, currency, pricing_version = estimate_cost(model, in_tok, out_tok)
                if cost is None:
                    raise _private_transport_error(
                        "PROVIDER_UNAVAILABLE",
                        f"No pricing for model {model!r}; refusing Live call settlement.",
                        retryable=False,
                        details={"model": model},
                    )
                payload = {
                    "text": response.text or "",
                    "content": response.text or "",
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "total_tokens": int(response.total_tokens or (in_tok + out_tok)),
                    "estimated_cost": float(cost),
                    "currency": currency or "CNY",
                    "pricing_version": pricing_version,
                    "model": response.model or model,
                    "request_id": response.request_id or "",
                    "provider": self.provider_name,
                    "latency_ms": latency_ms,
                    "http_status_code": response.http_status_code,
                    "attempt_no": attempts,
                }
                assert self.call_log is not None
                self.call_log.append(
                    {
                        "stage": stage,
                        "model": model,
                        "attempt_no": attempts,
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "estimated_cost": float(cost),
                        "response": dict(payload),
                    }
                )
                return payload
            except ProviderRequestError as exc:
                last_exc = exc
                code, retryable = self._map_provider_request_error(exc)
                if retryable and attempts <= self.max_auto_retries:
                    continue
                safe = str(getattr(exc, "message", None) or str(exc))[:240]
                raise _private_transport_error(
                    code,
                    safe,
                    retryable=False,
                    details={
                        "stage": stage,
                        "http_status": getattr(exc, "http_status", None),
                        "attempts": attempts,
                        "safe": safe,
                    },
                ) from exc
            except Exception as exc:  # noqa: BLE001
                if isinstance(exc, Exception) and getattr(exc, "code", None):
                    raise
                last_exc = exc
                if attempts <= self.max_auto_retries and self._is_retryable_network(exc):
                    continue
                raise _private_transport_error(
                    "PROVIDER_UNAVAILABLE",
                    f"Provider transport failed: {type(exc).__name__}",
                    retryable=False,
                    details={"stage": stage, "cause": type(exc).__name__, "attempts": attempts},
                ) from exc

        raise _private_transport_error(
            "PROVIDER_UNAVAILABLE",
            f"Provider exhausted retries: {type(last_exc).__name__ if last_exc else 'unknown'}",
            retryable=False,
            details={"stage": stage},
        )

    @staticmethod
    def _map_provider_request_error(exc: ProviderRequestError) -> tuple[str, bool]:
        status = getattr(exc, "http_status", None) or getattr(exc, "http_status_code", None)
        code = str(getattr(exc, "error_code", "") or "")
        transport_kind = str(getattr(exc, "transport_kind", "") or "").lower()
        if status == 429 or "rate" in code.lower():
            return "PROVIDER_RATE_LIMITED", True
        if "timeout" in transport_kind or "timeout" in code.lower():
            return "PROVIDER_TIMEOUT", True
        if status in {401, 403}:
            return "PROVIDER_NOT_CONFIGURED", False
        if getattr(exc, "retryable", False):
            return "PROVIDER_UNAVAILABLE", True
        return "PROVIDER_UNAVAILABLE", False

    @staticmethod
    def _is_retryable_network(exc: BaseException) -> bool:
        name = type(exc).__name__.lower()
        return any(tok in name for tok in ("timeout", "connect", "network", "temporary"))


__all__ = ["AliyunNativeOverviewTransport"]
