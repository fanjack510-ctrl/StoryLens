"""Central provider pricing registry (CHG-20260808-060).

DeepSeek list prices are sourced here — do not scatter CNY rates in UI/services/tests.
Aliyun continues to use config/cloud_pricing.default.json via cloud_pricing.estimate_cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CURRENCY_CNY = "CNY"
DEEPSEEK_PROVIDER = "deepseek"
DEEPSEEK_MODEL_FLASH = "deepseek-v4-flash"
DEEPSEEK_MODEL_PRO = "deepseek-v4-pro"
DEEPSEEK_DEFAULT_MODEL = DEEPSEEK_MODEL_FLASH
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_PRICING_EFFECTIVE_DATE = "2026-08-08"
DEEPSEEK_PRICING_SOURCE = "DeepSeek official Models & Pricing"
TOKEN_ESTIMATE_METHOD_HEURISTIC = "heuristic"


@dataclass(frozen=True)
class ModelPricing:
    provider: str
    model: str
    currency: str
    input_cache_hit_per_1m: float
    input_cache_miss_per_1m: float
    output_per_1m: float
    effective_date: str
    source_note: str


_DEEPSEEK_MODELS: dict[str, ModelPricing] = {
    DEEPSEEK_MODEL_FLASH: ModelPricing(
        provider=DEEPSEEK_PROVIDER,
        model=DEEPSEEK_MODEL_FLASH,
        currency=CURRENCY_CNY,
        input_cache_hit_per_1m=0.02,
        input_cache_miss_per_1m=1.00,
        output_per_1m=2.00,
        effective_date=DEEPSEEK_PRICING_EFFECTIVE_DATE,
        source_note=DEEPSEEK_PRICING_SOURCE,
    ),
    DEEPSEEK_MODEL_PRO: ModelPricing(
        provider=DEEPSEEK_PROVIDER,
        model=DEEPSEEK_MODEL_PRO,
        currency=CURRENCY_CNY,
        input_cache_hit_per_1m=0.025,
        input_cache_miss_per_1m=3.00,
        output_per_1m=6.00,
        effective_date=DEEPSEEK_PRICING_EFFECTIVE_DATE,
        source_note=DEEPSEEK_PRICING_SOURCE,
    ),
}


def is_deepseek_model(model: str | None) -> bool:
    return str(model or "").strip() in _DEEPSEEK_MODELS


def get_model_pricing(model: str) -> ModelPricing | None:
    return _DEEPSEEK_MODELS.get(str(model or "").strip())


def list_deepseek_models() -> list[str]:
    return [DEEPSEEK_MODEL_FLASH, DEEPSEEK_MODEL_PRO]


def estimate_tokens_heuristic(text: str) -> int:
    """Official-style approximation: CJK × 0.6 + Latin × 0.3. Not exact tokenizer counts."""
    if not text:
        return 0
    cjk = 0
    latin = 0
    for ch in text:
        code = ord(ch)
        if (
            0x4E00 <= code <= 0x9FFF
            or 0x3400 <= code <= 0x4DBF
            or 0xF900 <= code <= 0xFAFF
            or 0x3000 <= code <= 0x303F
            or 0xFF00 <= code <= 0xFFEF
        ):
            cjk += 1
        elif ch.isascii() and (ch.isalnum() or ch.isspace() or ch in ".,;:!?\"'()-"):
            latin += 1
        else:
            # Treat other non-space as closer to CJK density for conservative estimate.
            if not ch.isspace():
                cjk += 1
    return max(1, int(round(cjk * 0.6 + latin * 0.3)))


def estimate_pre_run_cost_cny(
    model: str,
    *,
    estimated_input_tokens: int,
    estimated_output_tokens_min: int,
    estimated_output_tokens_max: int,
) -> tuple[float | None, float | None, str | None]:
    """Conservative pre-run band: all input priced as cache miss; output min/max band."""
    pricing = get_model_pricing(model)
    if pricing is None:
        return None, None, "model_pricing_missing"
    inp = max(0, int(estimated_input_tokens))
    out_min = max(0, int(estimated_output_tokens_min))
    out_max = max(out_min, int(estimated_output_tokens_max))
    input_cost = inp / 1_000_000.0 * pricing.input_cache_miss_per_1m
    cost_min = input_cost + out_min / 1_000_000.0 * pricing.output_per_1m
    cost_max = input_cost + out_max / 1_000_000.0 * pricing.output_per_1m
    return round(cost_min, 6), round(cost_max, 6), None


def estimate_actual_cost_cny(
    model: str,
    *,
    cache_hit_tokens: int | None,
    cache_miss_tokens: int | None,
    completion_tokens: int | None,
) -> float | None:
    """Post-run estimated_actual_cost from API usage. Not a billed invoice amount."""
    pricing = get_model_pricing(model)
    if pricing is None:
        return None
    hit = int(cache_hit_tokens or 0)
    miss = int(cache_miss_tokens or 0)
    completion = int(completion_tokens or 0)
    # If hit/miss absent but we only have prompt total, caller should pass miss=prompt.
    cost = (
        hit / 1_000_000.0 * pricing.input_cache_hit_per_1m
        + miss / 1_000_000.0 * pricing.input_cache_miss_per_1m
        + completion / 1_000_000.0 * pricing.output_per_1m
    )
    return round(cost, 6)


def pricing_to_dict(model: str) -> dict[str, Any] | None:
    row = get_model_pricing(model)
    if row is None:
        return None
    return {
        "provider": row.provider,
        "model": row.model,
        "currency": row.currency,
        "input_cache_hit_per_1m": row.input_cache_hit_per_1m,
        "input_cache_miss_per_1m": row.input_cache_miss_per_1m,
        "output_per_1m": row.output_per_1m,
        "effective_date": row.effective_date,
        "source_note": row.source_note,
    }


COST_DISCLAIMER_ZH = "费用为预估值，实际收费以 DeepSeek 官方账单为准。"
ACTUAL_COST_DISCLAIMER_ZH = "根据 API 返回 Token 用量估算，实际收费以 DeepSeek 官方账单为准。"
