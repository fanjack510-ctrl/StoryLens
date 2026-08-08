"""Aggregate provider usage into estimated_actual_cost_cny (never billed invoice)."""

from __future__ import annotations

from typing import Any, Iterable

from app.services.cloud_pricing import estimate_cost
from app.services.provider_pricing import estimate_actual_cost_cny, is_deepseek_model


def estimate_call_cost_cny(
    *,
    model_name: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_hit_tokens: int | None = None,
    cache_miss_tokens: int | None = None,
) -> float | None:
    model = str(model_name or "").strip()
    if not model:
        return None
    if is_deepseek_model(model):
        miss = cache_miss_tokens
        if miss is None and input_tokens is not None:
            # Conservative: treat unknown prompt tokens as cache miss.
            hit = int(cache_hit_tokens or 0)
            miss = max(0, int(input_tokens) - hit)
        return estimate_actual_cost_cny(
            model,
            cache_hit_tokens=cache_hit_tokens,
            cache_miss_tokens=miss,
            completion_tokens=output_tokens,
        )
    cost, _, _ = estimate_cost(model, int(input_tokens or 0), int(output_tokens or 0))
    return float(cost) if cost is not None else None


def aggregate_estimated_actual_cost_cny(
    calls: Iterable[dict[str, Any]],
) -> float | None:
    """Sum per-call estimated costs. Returns None when no priced call is present."""
    total = 0.0
    any_priced = False
    for call in calls:
        if not isinstance(call, dict):
            continue
        cost = call.get("estimated_actual_cost_cny")
        if cost is None:
            cost = estimate_call_cost_cny(
                model_name=str(call.get("model_name") or call.get("model") or ""),
                input_tokens=call.get("input_tokens"),
                output_tokens=call.get("output_tokens"),
                cache_hit_tokens=call.get("cache_hit_tokens"),
                cache_miss_tokens=call.get("cache_miss_tokens"),
            )
        if cost is None:
            continue
        any_priced = True
        total += float(cost)
    return round(total, 6) if any_priced else None
