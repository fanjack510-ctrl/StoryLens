"""CHG-20260726-006 — native overview AI binding + cost estimate."""

from __future__ import annotations

from app.services.native_overview_ai_binding import estimate_native_overview_usage


def test_non_empty_book_estimate_nonzero_tokens_and_cost():
    usage = estimate_native_overview_usage(
        character_count=2_672_342,
        estimated_windows=2046,
        model_id="qwen3.7-plus",
    )
    assert usage["estimated_total_tokens"] > 0
    assert usage["estimated_input_tokens"] > 0
    assert usage["pricing_available"] is True
    assert usage["estimated_cost"] is not None
    assert float(usage["estimated_cost"]) > 0
    assert usage["error_code"] is None


def test_small_book_estimate_nonzero():
    usage = estimate_native_overview_usage(
        character_count=1200,
        estimated_windows=1,
        model_id="qwen3.7-plus",
    )
    assert usage["estimated_total_tokens"] > 0
    assert float(usage["estimated_cost"] or 0) > 0


def test_unknown_model_marks_unavailable():
    usage = estimate_native_overview_usage(
        character_count=1000,
        estimated_windows=1,
        model_id="not-a-real-model-zzz",
    )
    assert usage["pricing_available"] is False
    assert usage["error_code"] == "COST_ESTIMATE_UNAVAILABLE"
    assert usage["estimated_total_tokens"] > 0
