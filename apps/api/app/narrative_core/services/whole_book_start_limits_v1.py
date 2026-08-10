"""Whole-book start limit helpers (CHG-20260808-062)."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from app.db.models import WholeBookCostEstimate
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)


def _ceil_to_step(value: int, step: int) -> int:
    if value <= 0:
        return step
    return int(math.ceil(value / step) * step)


def suggest_whole_book_limits(
    *,
    estimated_provider_calls: int | None,
    estimated_input_tokens: int | None,
    estimated_output_tokens: int | None,
    estimated_cost_max_cny: Decimal | str | float | None,
    default_budget_cny: str = "10.00",
) -> dict[str, Any]:
    """Safety caps with headroom — not the cost estimate itself."""
    calls = int(estimated_provider_calls or 0)
    in_tok = int(estimated_input_tokens or 0)
    out_tok = int(estimated_output_tokens or 0)

    sug_calls = _ceil_to_step(max(int(math.ceil(calls * 1.15)), calls + 50), 50) if calls else 50
    sug_in = (
        _ceil_to_step(max(int(math.ceil(in_tok * 1.1)), in_tok + 50_000), 100_000)
        if in_tok
        else 100_000
    )
    sug_out = (
        _ceil_to_step(max(int(math.ceil(out_tok * 1.15)), out_tok + 30_000), 50_000)
        if out_tok
        else 50_000
    )

    sug_budget = default_budget_cny
    if estimated_cost_max_cny is not None:
        needed = Decimal(str(estimated_cost_max_cny))
        floor = Decimal(str(default_budget_cny))
        if needed > floor:
            sug_budget = str((needed * Decimal("1.2")).quantize(Decimal("0.01")))
        else:
            sug_budget = str(floor.quantize(Decimal("0.01")))

    return {
        "max_provider_calls": sug_calls,
        "max_input_tokens": sug_in,
        "max_output_tokens": sug_out,
        "max_cost_budget_cny": sug_budget,
    }


def suggest_limits_from_estimate(estimate: WholeBookCostEstimate) -> dict[str, Any]:
    return suggest_whole_book_limits(
        estimated_provider_calls=estimate.estimated_provider_call_count,
        estimated_input_tokens=estimate.estimated_input_tokens,
        estimated_output_tokens=estimate.estimated_output_tokens,
        estimated_cost_max_cny=estimate.estimated_cost_max_cny,
    )


def assert_limits_cover_estimate(
    estimate: WholeBookCostEstimate,
    *,
    max_provider_calls: int | None,
    max_input_tokens: int | None,
    max_output_tokens: int | None,
    user_budget_limit_cny: Decimal | str | float | None,
) -> None:
    """Fail closed when any hard limit is below the current estimate."""
    est_calls = int(estimate.estimated_provider_call_count or 0)
    est_in = int(estimate.estimated_input_tokens or 0)
    est_out = int(estimate.estimated_output_tokens or 0)

    if max_provider_calls is not None and est_calls > 0 and int(max_provider_calls) < est_calls:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.LIMIT_PROVIDER_CALLS_TOO_LOW,
            (
                f"预计需要 {est_calls} 次模型调用，超过当前允许上限 {int(max_provider_calls)} 次。"
                f"请提高调用上限或调整分析范围。"
            ),
            details={
                "estimated_provider_calls": est_calls,
                "max_provider_calls": int(max_provider_calls),
            },
        )
    if max_input_tokens is not None and est_in > 0 and int(max_input_tokens) < est_in:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.LIMIT_INPUT_TOKENS_TOO_LOW,
            (
                f"预计需要 {est_in} 输入 Token，超过当前允许上限 {int(max_input_tokens)}。"
                f"请提高输入 Token 上限或调整分析范围。"
            ),
            details={
                "estimated_input_tokens": est_in,
                "max_input_tokens": int(max_input_tokens),
            },
        )
    if max_output_tokens is not None and est_out > 0 and int(max_output_tokens) < est_out:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.LIMIT_OUTPUT_TOKENS_TOO_LOW,
            (
                f"预计需要 {est_out} 输出 Token，超过当前允许上限 {int(max_output_tokens)}。"
                f"请提高输出 Token 上限或调整分析范围。"
            ),
            details={
                "estimated_output_tokens": est_out,
                "max_output_tokens": int(max_output_tokens),
            },
        )

    if user_budget_limit_cny is not None and estimate.estimated_cost_max_cny is not None:
        budget = Decimal(str(user_budget_limit_cny))
        needed = Decimal(str(estimate.estimated_cost_max_cny))
        if budget < needed:
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.BUDGET_TOO_LOW,
                (
                    f"预计最高费用 ¥{needed}，超过当前费用上限 ¥{budget}。"
                    f"请提高费用上限或调整分析范围。"
                ),
                details={
                    "estimated_cost_max_cny": str(needed),
                    "max_cost_budget_cny": str(budget),
                },
            )
