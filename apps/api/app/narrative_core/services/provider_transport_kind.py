"""Explicit Provider Transport kinds for Private Lab Live (CHG-051).

Live authorization must not rely on ``transport is None`` alone.
Capturing is test/dry-only; Fake HTTP is test-only network boundary simulation;
REAL_HTTP is the only allowed production-style Live transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ProviderTransportKind(str, Enum):
    CAPTURING_TEST = "CAPTURING_TEST"
    FAKE_HTTP_TEST = "FAKE_HTTP_TEST"
    REAL_HTTP = "REAL_HTTP"


@dataclass(frozen=True, slots=True)
class ProviderTransportCapabilities:
    kind: ProviderTransportKind
    test_only: bool
    network_capable: bool


CAPTURING_CAPS = ProviderTransportCapabilities(
    kind=ProviderTransportKind.CAPTURING_TEST,
    test_only=True,
    network_capable=False,
)
FAKE_HTTP_CAPS = ProviderTransportCapabilities(
    kind=ProviderTransportKind.FAKE_HTTP_TEST,
    test_only=True,
    network_capable=True,
)
REAL_HTTP_CAPS = ProviderTransportCapabilities(
    kind=ProviderTransportKind.REAL_HTTP,
    test_only=False,
    network_capable=True,
)


def transport_kind_of(transport: Any | None) -> ProviderTransportKind | None:
    if transport is None:
        return None
    kind = getattr(transport, "transport_kind", None)
    if isinstance(kind, ProviderTransportKind):
        return kind
    if isinstance(kind, str):
        try:
            return ProviderTransportKind(kind)
        except ValueError:
            pass
    # Legacy Capturing detection (pre-kind attribute).
    cls_name = type(transport).__name__
    if cls_name == "CapturingProviderTransport":
        return ProviderTransportKind.CAPTURING_TEST
    if cls_name in {"FakeHttpProviderTransport", "_FakeHttpTransport"}:
        return ProviderTransportKind.FAKE_HTTP_TEST
    if cls_name in {"_HttpTransport", "RealOpenAICompatibleProviderTransport"}:
        return ProviderTransportKind.REAL_HTTP
    return None


def is_capturing_transport(transport: Any | None) -> bool:
    return transport_kind_of(transport) == ProviderTransportKind.CAPTURING_TEST


def live_transport_allowed(
    *,
    transport: Any | None,
    environment: str,
    explicit_test_override: bool = False,
) -> tuple[bool, str | None, ProviderTransportKind]:
    """Return (ok, deny_reason, effective_kind) for authorized Live.

    ``transport is None`` means construct REAL_HTTP at execute boundary.
    """

    env = str(environment or "").strip().lower()
    kind = transport_kind_of(transport)
    if transport is None or kind is None:
        return True, None, ProviderTransportKind.REAL_HTTP
    if kind == ProviderTransportKind.CAPTURING_TEST:
        return False, "capturing_transport_forbidden_on_live", kind
    if kind == ProviderTransportKind.FAKE_HTTP_TEST:
        if env == "test" or explicit_test_override:
            return True, None, kind
        return False, "fake_http_requires_test_override", kind
    if kind == ProviderTransportKind.REAL_HTTP:
        return True, None, kind
    return False, "unknown_transport_kind", kind


@dataclass
class FakeHttpProviderTransport:
    """Test-only transport that simulates the formal HTTP boundary (no internet)."""

    stub_text: str = ""
    # Optional multi-response queue for schema-repair replay (first call, repair call, …).
    stub_texts: list[str] = field(default_factory=list)
    model: str = "qwen3.7-plus"
    request_id: str = "fake-http-req-1"
    request_ids: list[str] = field(default_factory=list)
    input_tokens: int = 5125
    output_tokens: int = 420
    http_status: int = 200
    finish_reason: str = "stop"
    latency_ms: int = 42
    host: str = "dashscope.aliyuncs.com"
    raise_error: bool = False
    calls: list[dict[str, Any]] = field(default_factory=list)
    cancelled_refs: set[str] = field(default_factory=set)
    transport_kind: ProviderTransportKind = ProviderTransportKind.FAKE_HTTP_TEST
    test_only: bool = True
    network_capable: bool = True
    _call_index: int = 0

    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        response_format_mode: str,
        max_tokens: int | None,
        timeout_seconds: int,
        cancellation_ref: str | None = None,
        response_schema: Mapping[str, Any] | None = None,
    ) -> Any:
        from app.narrative_core.services.whole_book_provider_gateway import (
            StubTransportResponse,
        )

        idx = int(self._call_index)
        self._call_index = idx + 1
        queue = list(self.stub_texts) if self.stub_texts else [self.stub_text]
        if idx >= len(queue):
            text = queue[-1] if queue else self.stub_text
        else:
            text = queue[idx]
        req_ids = list(self.request_ids) if self.request_ids else []
        if req_ids and idx < len(req_ids):
            request_id = req_ids[idx]
        elif idx == 0:
            request_id = self.request_id
        else:
            request_id = f"{self.request_id}-repair-{idx}"

        self.calls.append(
            {
                "message_count": len(messages),
                "roles": [m.get("role") for m in messages],
                "model": model,
                "response_format_mode": response_format_mode,
                "max_tokens": max_tokens,
                "timeout_seconds": timeout_seconds,
                "has_system": any(m.get("role") == "system" for m in messages),
                "has_user": any(m.get("role") == "user" for m in messages),
                "total_chars": sum(len(m.get("content") or "") for m in messages),
                "transport_kind": self.transport_kind.value,
                "host": self.host,
                "call_index": idx,
                "has_response_schema": response_schema is not None,
                "response_schema_title": (
                    (response_schema or {}).get("title")
                    if isinstance(response_schema, Mapping)
                    else None
                ),
            }
        )
        if cancellation_ref and cancellation_ref in self.cancelled_refs:
            from app.narrative_core.private_engine_contract.errors import (
                PrivateEngineErrorCode,
                private_engine_error,
            )

            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)
        if self.raise_error:
            from app.narrative_core.private_engine_contract.errors import (
                PrivateEngineErrorCode,
                private_engine_error,
            )

            raise private_engine_error(
                PrivateEngineErrorCode.PROVIDER_UNAVAILABLE,
                detail_code="fake_http_forced_failure",
            )
        return StubTransportResponse(
            text=text,
            model=model or self.model,
            request_id=request_id,
            input_tokens=int(self.input_tokens),
            output_tokens=int(self.output_tokens),
            finish_reason=self.finish_reason,
            http_status=int(self.http_status),
            transport_kind=self.transport_kind.value,
            latency_ms=int(self.latency_ms),
            host=self.host,
        )


def safe_transport_audit(transport: Any | None) -> Mapping[str, Any]:
    kind = transport_kind_of(transport)
    return {
        "transport_kind": kind.value if kind else None,
        "test_only": bool(getattr(transport, "test_only", kind != ProviderTransportKind.REAL_HTTP if kind else None)),
        "network_capable": bool(getattr(transport, "network_capable", kind != ProviderTransportKind.CAPTURING_TEST if kind else False)),
        "class_name": type(transport).__name__ if transport is not None else None,
    }


__all__ = [
    "ProviderTransportKind",
    "ProviderTransportCapabilities",
    "CAPTURING_CAPS",
    "FAKE_HTTP_CAPS",
    "REAL_HTTP_CAPS",
    "transport_kind_of",
    "is_capturing_transport",
    "live_transport_allowed",
    "FakeHttpProviderTransport",
    "safe_transport_audit",
]
