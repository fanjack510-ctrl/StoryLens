"""Scene boundary adjudication output budget (v1.1.2 hotfix).

Public source of truth for compute_scene_boundary_output_budget_v1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


class SceneBoundaryOutputBudgetTooLow(ValueError):
    error_code = "SCENE_BOUNDARY_OUTPUT_BUDGET_TOO_LOW"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "当前模型输出上限不足以完成边界裁决。请将最大输出 Token 调整到至少 1024 后重试。"
        )


@dataclass(frozen=True)
class SceneBoundaryOutputBudget:
    target_candidate_count: int
    user_output_hard_cap: int | None
    model_output_cap: int | None
    provider_output_cap: int | None
    effective_hard_cap: int
    raw_budget: int
    rounded_budget: int
    initial_output_limit: int


def round_up_to_256(value: float | int) -> int:
    n = int(math.ceil(float(value)))
    if n <= 0:
        return 256
    rem = n % 256
    return n if rem == 0 else n + (256 - rem)


def effective_hard_cap(
    *,
    user_output_hard_cap: int | None,
    model_output_cap: int | None = None,
    provider_output_cap: int | None = None,
) -> int:
    caps = [
        int(v)
        for v in (user_output_hard_cap, model_output_cap, provider_output_cap)
        if v is not None and int(v) > 0
    ]
    if not caps:
        raise SceneBoundaryOutputBudgetTooLow(
            "缺少有效输出硬上限，无法计算边界裁决输出预算。"
        )
    return min(caps)


def compute_scene_boundary_output_budget_v1(
    target_candidate_count: int,
    user_output_hard_cap: int | None,
    model_output_cap: int | None = None,
    provider_output_cap: int | None = None,
) -> SceneBoundaryOutputBudget:
    count = max(0, int(target_candidate_count))
    hard = effective_hard_cap(
        user_output_hard_cap=user_output_hard_cap,
        model_output_cap=model_output_cap,
        provider_output_cap=provider_output_cap,
    )
    if hard < 1024:
        raise SceneBoundaryOutputBudgetTooLow()

    raw = 512 + 128 * count
    rounded = round_up_to_256(raw)
    initial = min(hard, max(1024, rounded))
    return SceneBoundaryOutputBudget(
        target_candidate_count=count,
        user_output_hard_cap=user_output_hard_cap,
        model_output_cap=model_output_cap,
        provider_output_cap=provider_output_cap,
        effective_hard_cap=hard,
        raw_budget=raw,
        rounded_budget=rounded,
        initial_output_limit=initial,
    )


def compute_truncation_retry_limit(
    *,
    previous_limit: int,
    effective_hard_cap: int,
    attempt_no: int,
) -> int | None:
    """Return next attempt limit, or None if retry must stop.

    attempt_no is the upcoming attempt (2 = retry_1, 3 = retry_2).
    """
    prev = int(previous_limit)
    hard = int(effective_hard_cap)
    if attempt_no <= 1:
        return prev
    if attempt_no == 2:
        bumped = round_up_to_256(max(prev + 512, prev * 1.5))
        nxt = min(hard, bumped)
        if nxt <= prev:
            return None
        return nxt
    if attempt_no == 3:
        if hard > prev:
            return hard
        return None
    return None
