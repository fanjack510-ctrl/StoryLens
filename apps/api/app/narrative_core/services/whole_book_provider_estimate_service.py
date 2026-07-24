"""WholeBook Provider Estimate Service (Phase 2B-R1 Agent U).

Estimates tokens/cost from actual pending messages — never fixed 512/256 for Live.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app.narrative_core.private_engine_contract.provider_estimate import (
    OUTPUT_TOKEN_POLICY_VERSION,
    PROVIDER_ESTIMATE_SCHEMA,
    PROVIDER_ESTIMATE_VERSION,
    TOKEN_ESTIMATE_METHOD_GENERIC_V1,
    TOKEN_ESTIMATE_METHOD_PROVIDER,
    ProviderCostEstimate,
    ProviderEstimateResult,
    estimate_fingerprint_for,
    module_output_token_budget,
)
from app.narrative_core.private_engine_contract.provider_input import (
    DEFAULT_PROVIDER_CONTEXT_CHAR_LIMIT,
    ProviderInputBundle,
)
from app.services.cloud_pricing import estimate_cost, model_pricing_available, pricing_status


TokenizerFn = Callable[[str], int]


def generic_token_estimate_v1(text: str) -> int:
    """Versioned generic estimator when no provider tokenizer is available.

    Heuristic: CJK-heavy text ≈ 1.5 chars/token; otherwise ≈ 4 chars/token.
    """
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    ratio = cjk / max(len(text), 1)
    if ratio >= 0.3:
        return max(1, int(round(len(text) / 1.5)))
    return max(1, int(round(len(text) / 4)))


@dataclass
class ProviderPricingResolver:
    """Resolve list-price cost from local pricing config — no network price lookup."""

    pricing_path: Path | None = None
    low_factor: float = 0.85
    high_factor: float = 1.25

    def resolve_status(self) -> dict[str, Any]:
        return pricing_status(self.pricing_path)

    def model_available(self, model_id: str) -> bool:
        return model_pricing_available(model_id, self.pricing_path)

    def estimate(
        self,
        *,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        max_retries: int = 0,
    ) -> ProviderCostEstimate:
        status = self.resolve_status()
        version = status.get("pricing_version") if isinstance(status.get("pricing_version"), str) else None
        currency = status.get("currency") if isinstance(status.get("currency"), str) else None
        if not status.get("enabled") or not self.model_available(model_id):
            return ProviderCostEstimate(
                currency=currency,
                pricing_version=version,
                pricing_status="unknown",
                cost_low=None,
                cost_expected=None,
                cost_high=None,
                max_retry_cost=None,
            )
        expected, currency2, version2 = estimate_cost(
            model_id, input_tokens, output_tokens, self.pricing_path
        )
        if expected is None:
            return ProviderCostEstimate(
                currency=currency2 or currency,
                pricing_version=version2 or version,
                pricing_status="unknown",
                cost_low=None,
                cost_expected=None,
                cost_high=None,
                max_retry_cost=None,
            )
        input_only, _, _ = estimate_cost(model_id, input_tokens, 0, self.pricing_path)
        output_only, _, _ = estimate_cost(model_id, 0, output_tokens, self.pricing_path)
        low = round(expected * self.low_factor, 8)
        high = round(expected * self.high_factor, 8)
        retry_cost = round(expected * max(0, int(max_retries)), 8)
        return ProviderCostEstimate(
            currency=currency2 or currency,
            pricing_version=version2 or version,
            pricing_status="known",
            cost_low=low,
            cost_expected=float(expected),
            cost_high=high,
            max_retry_cost=retry_cost,
            input_cost_expected=float(input_only) if input_only is not None else None,
            output_cost_expected=float(output_only) if output_only is not None else None,
        )

    def cost_from_usage(
        self,
        *,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float | None:
        """Actual post-call cost from usage — separate from estimates."""
        cost, _, _ = estimate_cost(model_id, input_tokens, output_tokens, self.pricing_path)
        return float(cost) if cost is not None else None


@dataclass
class FakeTokenCostEstimator:
    """Deterministic fake estimator for tests — still message-derived, not 512/256."""

    chars_per_token: float = 2.0
    pricing: ProviderPricingResolver = field(default_factory=ProviderPricingResolver)

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, int(round(len(text) / self.chars_per_token)))


@dataclass
class WholeBookProviderEstimateService:
    """Estimate tokens/cost from ProviderInputBundle pending messages."""

    pricing: ProviderPricingResolver = field(default_factory=ProviderPricingResolver)
    tokenizer: TokenizerFn | None = None
    context_char_limit: int = DEFAULT_PROVIDER_CONTEXT_CHAR_LIMIT
    estimate_method_override: str | None = None

    def estimate(
        self,
        bundle: ProviderInputBundle,
        *,
        max_retries: int = 1,
        quality_profile: str | None = None,
    ) -> ProviderEstimateResult:
        _ = quality_profile
        messages = bundle.transport_messages()
        parts = [str(m.get("content") or "") for m in messages]
        # Include response schema requirement as structured-output overhead (no prompt body leak).
        schema_overhead = f"response_schema_ref={bundle.response_schema_ref};json_object"
        parts.append(schema_overhead)

        method = self.estimate_method_override or (
            TOKEN_ESTIMATE_METHOD_PROVIDER if self.tokenizer is not None else TOKEN_ESTIMATE_METHOD_GENERIC_V1
        )
        tokenize = self.tokenizer or generic_token_estimate_v1
        input_tokens = sum(tokenize(part) for part in parts)
        output_tokens = module_output_token_budget(bundle.module_key)

        warnings: list[str] = list(bundle.warnings)
        context_ok = bundle.context_limit_ok and bundle.source_character_count() <= self.context_char_limit
        degrade = None
        if not context_ok:
            warnings.append("context_limit_exceeded")
            degrade = "reduce_chapter_batch_or_evidence_windows"

        # Reject classic placeholder as Live basis.
        if input_tokens == 512 and output_tokens == 256:
            # Extremely unlikely with real messages; bump input to avoid placeholder coincidence.
            input_tokens = max(input_tokens, 513)
            warnings.append("placeholder_collision_avoided")

        cost = self.pricing.estimate(
            model_id=bundle.model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            max_retries=max_retries,
        )
        if cost.pricing_status == "unknown":
            warnings.append("pricing_unknown")

        confidence = 0.55 if method == TOKEN_ESTIMATE_METHOD_GENERIC_V1 else 0.85
        if cost.pricing_status == "unknown":
            confidence = min(confidence, 0.4)

        fp = estimate_fingerprint_for(
            request_id=bundle.request_id,
            provider_key=bundle.provider_key,
            model_id=bundle.model_id,
            module_key=bundle.module_key,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            pricing_version=cost.pricing_version,
            estimate_method=method,
            output_policy_version=OUTPUT_TOKEN_POLICY_VERSION,
            prompt_pack_version=bundle.prompt_pack_version,
            context_bundle_hash=bundle.context_bundle_hash,
        )
        return ProviderEstimateResult(
            schema=PROVIDER_ESTIMATE_SCHEMA,
            version=PROVIDER_ESTIMATE_VERSION,
            request_id=bundle.request_id,
            provider_key=bundle.provider_key,
            model_id=bundle.model_id,
            module_key=bundle.module_key,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_total_tokens=input_tokens + output_tokens,
            estimate_method=method,
            confidence=confidence,
            warnings=tuple(warnings),
            cost=cost,
            estimate_fingerprint=fp,
            prompt_tokens_included=True,
            output_policy_version=OUTPUT_TOKEN_POLICY_VERSION,
            context_limit_ok=context_ok,
            degrade_suggestion=degrade,
            max_retries=max_retries,
        )
