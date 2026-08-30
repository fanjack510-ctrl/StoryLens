from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from storylens_online.contracts.billing import InternalModelCost, ModelPricingSnapshot

TOKEN_SCALE = Decimal(1000000)
CNY_QUANTUM = Decimal("0.000001")
ZERO_CNY = Decimal("0.000000")


def calculate_internal_model_cost(
    *,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    pricing: ModelPricingSnapshot,
    total_tokens: int | None = None,
) -> InternalModelCost:
    """Calculate Provider cost only; Phase 2B1 never creates a customer charge."""

    if min(input_tokens, cached_tokens, output_tokens) < 0:
        raise ValueError("token counts must be nonnegative")
    if total_tokens is not None and total_tokens < 0:
        raise ValueError("total token count must be nonnegative")
    if cached_tokens > input_tokens:
        raise ValueError("cached tokens must not exceed input tokens")
    uncached_tokens = input_tokens - cached_tokens
    unrounded = (
        Decimal(uncached_tokens) * pricing.input_per_million_cny
        + Decimal(cached_tokens) * pricing.cached_input_per_million_cny
        + Decimal(output_tokens) * pricing.output_per_million_cny
    ) / TOKEN_SCALE
    provider_cost = unrounded.quantize(CNY_QUANTUM, rounding=ROUND_HALF_UP)
    return InternalModelCost(
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens if total_tokens is None else total_tokens,
        provider_cost_cny=provider_cost,
        customer_charge_cny=ZERO_CNY,
    )
