"""Resolve real AI provider/model for Native Overview (not Engine identity)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import ApplicationSetting, ProviderConfiguration
from app.services.analysis_execution_plan import (
    CANONICAL_PROVIDER_ID,
    MODE_DEFAULT_MODELS,
)

# Per-window prompt / state overhead used only for preflight upper-bound estimates.
_PROMPT_OVERHEAD_TOKENS_PER_WINDOW = 800
_DEFAULT_MAX_OUTPUT_TOKENS = 2048
_SYNTHESIS_OUTPUT_TOKENS = 4096


@dataclass(frozen=True, slots=True)
class NativeOverviewAiBinding:
    provider_id: str
    model_id: str
    provider_label: str
    execution_mode: str


def _read_analysis_profile(session: Session) -> str:
    import json

    row = session.get(ApplicationSetting, "recommended_analysis_mode")
    if row is None or not row.value_json:
        return "BALANCED"
    try:
        value = json.loads(row.value_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return "BALANCED"
    text = str(value or "BALANCED").strip().upper()
    return text if text in MODE_DEFAULT_MODELS else "BALANCED"


def resolve_native_overview_ai_binding(session: Session) -> NativeOverviewAiBinding:
    """Return the user-configured Aliyun binding for overview transport/preflight."""

    from app.services.execution_mode import (
        cloud_enabled_from_session,
        resolve_effective_execution_mode,
    )

    from sqlalchemy import select

    row = session.scalar(
        select(ProviderConfiguration).where(
            ProviderConfiguration.provider_name == CANONICAL_PROVIDER_ID
        )
    )
    profile = _read_analysis_profile(session)
    model = (row.plus_model if row and row.plus_model else None) or MODE_DEFAULT_MODELS.get(
        profile, "qwen3.7-plus"
    )
    cloud_enabled = cloud_enabled_from_session(session)
    mode = resolve_effective_execution_mode(
        provider_is_cloud=True,
        cloud_enabled=cloud_enabled,
        configured_execution_mode=None,
        local_provider_available=False,
    )
    return NativeOverviewAiBinding(
        provider_id=CANONICAL_PROVIDER_ID,
        model_id=str(model),
        provider_label="阿里云百炼",
        execution_mode=mode,
    )


def estimate_native_overview_usage(
    *,
    character_count: int,
    estimated_windows: int,
    model_id: str,
    max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS,
) -> dict:
    """Estimate tokens/cost for preflight. Never invent zero for non-empty books.

    Returns dict with keys:
      estimated_input_tokens, estimated_output_tokens, estimated_total_tokens,
      estimated_cost (float|None), currency, pricing_available, error_code
    """

    from app.narrative_core.services.native_overview_context_windows import (
        OverviewWindowBudget,
    )
    from app.services.cloud_pricing import estimate_cost, model_pricing_available

    windows = max(0, int(estimated_windows))
    chars = max(0, int(character_count))
    budget = OverviewWindowBudget()
    body_tokens = budget.estimate_tokens(chars) if chars > 0 else 0
    prompt_overhead = windows * _PROMPT_OVERHEAD_TOKENS_PER_WINDOW
    synthesis_in = _PROMPT_OVERHEAD_TOKENS_PER_WINDOW
    estimated_input = body_tokens + prompt_overhead + synthesis_in
    estimated_output = windows * max(1, int(max_output_tokens)) + _SYNTHESIS_OUTPUT_TOKENS
    if chars > 0 or windows > 0:
        estimated_input = max(1, estimated_input)
        estimated_output = max(1, estimated_output)
    estimated_total = estimated_input + estimated_output

    pricing_ok = model_pricing_available(model_id)
    cost, currency, _version = estimate_cost(model_id, estimated_input, estimated_output)
    if not pricing_ok or cost is None:
        return {
            "estimated_input_tokens": estimated_total and estimated_input,
            "estimated_output_tokens": estimated_output,
            "estimated_total_tokens": estimated_total,
            "estimated_cost": None,
            "currency": currency or "CNY",
            "pricing_available": False,
            "error_code": "COST_ESTIMATE_UNAVAILABLE",
        }
    return {
        "estimated_input_tokens": estimated_input,
        "estimated_output_tokens": estimated_output,
        "estimated_total_tokens": estimated_total,
        "estimated_cost": float(cost),
        "currency": currency or "CNY",
        "pricing_available": True,
        "error_code": None,
    }


def is_engine_identity(token: str | None) -> bool:
    from app.narrative_core.contracts.pro_native_overview_flags import (
        FIXTURE_ENGINE_ID,
        PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
    )

    value = (token or "").strip()
    if not value:
        return False
    return value in {FIXTURE_ENGINE_ID, PRIVATE_NATIVE_OVERVIEW_ENGINE_ID, "fixture"}


__all__ = [
    "NativeOverviewAiBinding",
    "estimate_native_overview_usage",
    "is_engine_identity",
    "resolve_native_overview_ai_binding",
]
