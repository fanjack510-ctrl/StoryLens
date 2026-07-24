"""Provider-backed Private Module Result binding (Phase 2B-R1 CHG-054).

Binds validated Provider structured output into the formal module-result channel.
Never carries raw HTTP body, prompt, credential, or full messages.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class ProviderBackedPrivateModuleResult:
    """Sole formal result source for Live / FAKE_HTTP_TEST provider paths."""

    module_key: str
    engine_id: str
    engine_version: str
    engine_kind: str
    synthetic: bool
    provider_key: str
    model_id: str
    provider_request_id: str
    transport_kind: str
    structured_output: Mapping[str, Any]
    candidate_dtos: tuple[Mapping[str, Any], ...] = ()
    evidence_locators: tuple[Mapping[str, Any], ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    validation_summary: Mapping[str, Any] = field(default_factory=dict)
    output_fingerprint: str = ""
    provider_backed: bool = True

    def __post_init__(self) -> None:
        if self.synthetic:
            raise ValueError("ProviderBackedPrivateModuleResult must have synthetic=false")
        if self.engine_kind != "PRIVATE_REAL":
            raise ValueError("ProviderBackedPrivateModuleResult requires engine_kind=PRIVATE_REAL")
        if not str(self.provider_request_id or "").strip():
            raise ValueError("provider_request_id required")
        if not str(self.transport_kind or "").strip():
            raise ValueError("transport_kind required")
        banned = ("raw_response", "prompt", "credential", "messages", "api_key", "full_text")
        for key in banned:
            if key in self.structured_output:
                raise ValueError(f"structured_output must not include {key}")
            if key in self.usage:
                raise ValueError(f"usage must not include {key}")

    def to_provider_policy(self) -> dict[str, Any]:
        """Bridge into Private Module Runner without the synthetic fixture channel."""

        structured = {
            k: v
            for k, v in dict(self.structured_output).items()
            if k not in {"_provider_audit", "raw_response", "prompt", "messages"}
        }
        structured["synthetic"] = False
        evidence = list(self.evidence_locators) or list(
            structured.get("evidence_candidates") or ()
        )
        return {
            "provider_kind": self.provider_key,
            "model_route": self.model_id or "lab-route",
            "provider_backed": True,
            "provider_structured_output": structured,
            "evidence_candidates": evidence,
            "provider_attempt": {
                "provider_request_id": self.provider_request_id,
                "transport_kind": self.transport_kind,
                "provider_key": self.provider_key,
                "model_id": self.model_id,
                "engine_kind": self.engine_kind,
                "synthetic": False,
                "provider_backed": True,
                **{
                    k: self.usage[k]
                    for k in (
                        "http_status",
                        "input_tokens",
                        "output_tokens",
                        "latency_ms",
                        "usage_source",
                        "actual_cost",
                    )
                    if k in self.usage and self.usage[k] is not None
                },
            },
        }


def build_provider_backed_module_result(
    *,
    module_key: str,
    structured_output: Mapping[str, Any],
    provider_usage: Mapping[str, Any],
    engine_id: str,
    engine_version: str,
    provider_key: str,
    model_id: str = "",
) -> ProviderBackedPrivateModuleResult:
    cleaned = {
        k: v
        for k, v in dict(structured_output).items()
        if k not in {"_provider_audit", "raw_response", "prompt", "messages", "api_key"}
    }
    if not cleaned:
        raise ValueError("PROVIDER_STRUCTURED_OUTPUT_EMPTY")
    request_id = str(
        provider_usage.get("provider_request_id") or ""
    ).strip()
    transport = str(provider_usage.get("transport_kind") or "").strip()
    if not request_id:
        raise ValueError("PROVIDER_REQUEST_ID_MISSING")
    if not transport:
        raise ValueError("PROVIDER_TRANSPORT_KIND_MISSING")
    evidence = tuple(
        dict(x) if isinstance(x, Mapping) else {"value": x}
        for x in (cleaned.get("evidence_candidates") or ())
        if x is not None
    )
    fp_payload = {
        "module_key": module_key,
        "structured_output": cleaned,
        "provider_request_id": request_id,
        "transport_kind": transport,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fp_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return ProviderBackedPrivateModuleResult(
        module_key=module_key,
        engine_id=engine_id,
        engine_version=engine_version,
        engine_kind="PRIVATE_REAL",
        synthetic=False,
        provider_key=provider_key,
        model_id=model_id or str(provider_usage.get("model_id") or ""),
        provider_request_id=request_id,
        transport_kind=transport,
        structured_output=cleaned,
        candidate_dtos=(),
        evidence_locators=evidence,
        usage={
            "provider_backed": True,
            "engine_kind": "PRIVATE_REAL",
            "synthetic": False,
            "provider_request_id": request_id,
            "transport_kind": transport,
            "http_status": provider_usage.get("http_status"),
            "input_tokens": provider_usage.get("input_tokens"),
            "output_tokens": provider_usage.get("output_tokens"),
            "latency_ms": provider_usage.get("latency_ms"),
            "usage_source": provider_usage.get("usage_source") or "provider_response",
            "actual_cost": provider_usage.get("actual_cost"),
        },
        validation_summary={"schema_valid": True, "provider_bound": True},
        output_fingerprint=fingerprint,
        provider_backed=True,
    )


__all__ = [
    "ProviderBackedPrivateModuleResult",
    "build_provider_backed_module_result",
]
