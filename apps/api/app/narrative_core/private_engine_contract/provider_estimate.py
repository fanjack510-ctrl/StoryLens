"""Provider estimate / cost DTOs (Phase 2B-R1 Agent U).

Estimates are derived from actual pending messages — not fixed 512/256 placeholders.
Unknown pricing must not be reported as zero.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

PROVIDER_ESTIMATE_SCHEMA = "storylens.provider_estimate_result"
PROVIDER_ESTIMATE_VERSION = "1.0.0"
OUTPUT_TOKEN_POLICY_VERSION = "1.0.0"
TOKEN_ESTIMATE_METHOD_GENERIC_V1 = "generic_char_heuristic_v1"
TOKEN_ESTIMATE_METHOD_PROVIDER = "provider_tokenizer"

# Versioned per-module output token policy (configuration fingerprint input).
MODULE_OUTPUT_TOKEN_POLICY: Mapping[str, int] = {
    "book_overview": 1200,
    "structure_stages": 1600,
    "chapter_functions": 2000,
    "storylines": 1800,
    "default": 1024,
}


@dataclass(frozen=True, slots=True)
class ProviderCostEstimate:
    currency: str | None
    pricing_version: str | None
    pricing_status: str  # known | unknown
    cost_low: float | None
    cost_expected: float | None
    cost_high: float | None
    max_retry_cost: float | None
    input_cost_expected: float | None = None
    output_cost_expected: float | None = None

    def __post_init__(self) -> None:
        if self.pricing_status == "unknown":
            if self.cost_expected == 0.0 or self.cost_low == 0.0 or self.cost_high == 0.0:
                raise ValueError("unknown pricing must not report cost as 0")
            if self.cost_expected is not None or self.cost_low is not None or self.cost_high is not None:
                raise ValueError("unknown pricing must leave cost fields as None")


@dataclass(frozen=True, slots=True)
class ProviderEstimateResult:
    schema: str
    version: str
    request_id: str
    provider_key: str
    model_id: str
    module_key: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_total_tokens: int
    estimate_method: str
    confidence: float
    warnings: tuple[str, ...]
    cost: ProviderCostEstimate
    estimate_fingerprint: str
    prompt_tokens_included: bool = True
    output_policy_version: str = OUTPUT_TOKEN_POLICY_VERSION
    context_limit_ok: bool = True
    degrade_suggestion: str | None = None
    max_retries: int = 0

    def __post_init__(self) -> None:
        if self.estimated_input_tokens < 0 or self.estimated_output_tokens < 0:
            raise ValueError("token estimates must be >= 0")
        # Guard against legacy placeholder becoming Live confirmation basis.
        if (
            self.estimated_input_tokens == 512
            and self.estimated_output_tokens == 256
            and self.estimate_method == "placeholder"
        ):
            raise ValueError("placeholder 512/256 estimate is forbidden for live readiness")

    def safe_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "version": self.version,
            "request_id": self.request_id,
            "provider_key": self.provider_key,
            "model_id": self.model_id,
            "module_key": self.module_key,
            "estimated_input_tokens": self.estimated_input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
            "estimated_total_tokens": self.estimated_total_tokens,
            "estimate_method": self.estimate_method,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "cost": {
                "currency": self.cost.currency,
                "pricing_version": self.cost.pricing_version,
                "pricing_status": self.cost.pricing_status,
                "cost_low": self.cost.cost_low,
                "cost_expected": self.cost.cost_expected,
                "cost_high": self.cost.cost_high,
                "max_retry_cost": self.cost.max_retry_cost,
                "input_cost_expected": self.cost.input_cost_expected,
                "output_cost_expected": self.cost.output_cost_expected,
            },
            "estimate_fingerprint": self.estimate_fingerprint,
            "prompt_tokens_included": self.prompt_tokens_included,
            "output_policy_version": self.output_policy_version,
            "context_limit_ok": self.context_limit_ok,
            "degrade_suggestion": self.degrade_suggestion,
            "max_retries": self.max_retries,
        }


def module_output_token_budget(module_key: str) -> int:
    return int(MODULE_OUTPUT_TOKEN_POLICY.get(module_key, MODULE_OUTPUT_TOKEN_POLICY["default"]))


def estimate_fingerprint_for(
    *,
    request_id: str,
    provider_key: str,
    model_id: str,
    module_key: str,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
    pricing_version: str | None,
    estimate_method: str,
    output_policy_version: str,
    prompt_pack_version: str = "",
    context_bundle_hash: str = "",
) -> str:
    payload = {
        "request_id": request_id,
        "provider_key": provider_key,
        "model_id": model_id,
        "module_key": module_key,
        "estimated_input_tokens": estimated_input_tokens,
        "estimated_output_tokens": estimated_output_tokens,
        "pricing_version": pricing_version,
        "estimate_method": estimate_method,
        "output_policy_version": output_policy_version,
        "prompt_pack_version": prompt_pack_version,
        "context_bundle_hash": context_bundle_hash,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def estimate_policy_fingerprint_parts() -> Mapping[str, Any]:
    """Configuration fingerprint inputs for estimate policies."""
    return {
        "output_token_policy_version": OUTPUT_TOKEN_POLICY_VERSION,
        "module_output_token_policy": dict(MODULE_OUTPUT_TOKEN_POLICY),
        "token_estimate_method_default": TOKEN_ESTIMATE_METHOD_GENERIC_V1,
        "provider_estimate_schema": PROVIDER_ESTIMATE_SCHEMA,
        "provider_estimate_version": PROVIDER_ESTIMATE_VERSION,
    }
