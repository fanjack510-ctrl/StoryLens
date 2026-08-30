from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from storylens_online.contracts.billing import InternalModelCost, ModelPricingSnapshot

TOKEN_SCALE = Decimal(1000000)
CNY_QUANTUM = Decimal("0.000001")
USD_QUANTUM = Decimal("0.000000001")
ZERO_CNY = Decimal("0.000000")
ZERO_USD = Decimal("0.000000000")


def calculate_internal_model_cost(
    *,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    pricing: ModelPricingSnapshot,
    total_tokens: int | None = None,
    prompt_cache_miss_tokens: int | None = None,
) -> InternalModelCost:
    """Calculate Provider cost only; Phase 2B1 never creates a customer charge."""

    if min(input_tokens, cached_tokens, output_tokens) < 0:
        raise ValueError("token counts must be nonnegative")
    if total_tokens is not None and total_tokens < 0:
        raise ValueError("total token count must be nonnegative")
    if cached_tokens > input_tokens:
        raise ValueError("cached tokens must not exceed input tokens")
    cache_miss_tokens = input_tokens - cached_tokens
    if prompt_cache_miss_tokens is not None and prompt_cache_miss_tokens != cache_miss_tokens:
        raise ValueError("cache hit and miss token counts must equal input tokens")
    if pricing.pricing_currency == "USD":
        if pricing.fx_rate_to_cny <= 0:
            raise ValueError("USD pricing requires a positive CNY exchange rate")
        unrounded_usd = (
            Decimal(cache_miss_tokens) * pricing.cache_miss_usd_per_million
            + Decimal(cached_tokens) * pricing.cache_hit_usd_per_million
            + Decimal(output_tokens) * pricing.output_usd_per_million
        ) / TOKEN_SCALE
        provider_cost_usd = unrounded_usd.quantize(USD_QUANTUM, rounding=ROUND_HALF_UP)
        provider_cost_cny = (provider_cost_usd * pricing.fx_rate_to_cny).quantize(
            CNY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
    else:
        unrounded_cny = (
            Decimal(cache_miss_tokens) * pricing.input_per_million_cny
            + Decimal(cached_tokens) * pricing.cached_input_per_million_cny
            + Decimal(output_tokens) * pricing.output_per_million_cny
        ) / TOKEN_SCALE
        provider_cost_usd = ZERO_USD
        provider_cost_cny = unrounded_cny.quantize(CNY_QUANTUM, rounding=ROUND_HALF_UP)
    return InternalModelCost(
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        prompt_cache_miss_tokens=cache_miss_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens if total_tokens is None else total_tokens,
        provider_cost_usd=provider_cost_usd,
        provider_cost_cny=provider_cost_cny,
        customer_charge_cny=ZERO_CNY,
    )
